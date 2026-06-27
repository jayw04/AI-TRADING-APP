"""Alpaca Trade Updates streaming.

Subscribes to Alpaca's WebSocket for order/fill events and forwards each one
to the in-process event bus on topic ``alpaca.trade_update`` with a normalized
payload.

Design notes:

* alpaca-py's ``TradingStream`` exposes both a sync ``run()`` (which internally
  calls ``asyncio.run``) and an async ``_run_forever`` coroutine. We use the
  async path so we can run inside the FastAPI event loop without spawning a
  thread.
* alpaca-py's ``_run_forever`` has only a hardcoded ``asyncio.sleep(0.01)``
  between reconnect attempts, so a socket that keeps breaking (e.g. a Norton SSL
  MITM that half-opens the connection) makes it reconnect ~100x/second — pinning
  the event-loop core at ~100% CPU and leaking sockets. We therefore do NOT call
  ``_run_forever``; we drive its own primitives (``_start_ws`` / ``_consume`` /
  ``close``) in a supervised loop with **exponential backoff** and **auto-disable
  after repeated rapid failures**. When disabled, fills are still captured by the
  account/position reconciliation polling jobs. (Depends on alpaca-py internals;
  pinned version — revisit on upgrade.)
* No translation from raw events to internal Order/Fill records happens here.
  Session 4 adds an EventBus subscriber that does that translation once the
  DB schema for orders/fills exists.
"""

from __future__ import annotations

import asyncio
import contextlib
import time
from datetime import UTC, datetime
from typing import Any

import structlog

from app.brokers.alpaca.credentials import AlpacaCredentials
from app.events.bus import EventBus

logger = structlog.get_logger(__name__)

# Supervised-reconnect policy (replaces alpaca-py's 0.01s spin). Exponential backoff
# between attempts; after this many *consecutive rapid* failures the stream auto-disables
# (it can't sustain a connection — almost always Norton MITM on this dev box) and we fall
# back to the reconciliation polling jobs for fills.
_RECONNECT_BASE_BACKOFF_S = 1.0
_RECONNECT_MAX_BACKOFF_S = 60.0
_MAX_CONSECUTIVE_FAILURES = 6
# A connection that stays up at least this long is "healthy" — reset the failure counter so a
# one-off blip after hours of uptime doesn't count toward the disable threshold.
_MIN_HEALTHY_SECONDS = 30.0


class TradeUpdatesStream:
    """Long-running subscriber to Alpaca's Trade Updates WebSocket."""

    def __init__(
        self,
        credentials: AlpacaCredentials,
        bus: EventBus,
    ) -> None:
        self._creds = credentials
        self._bus = bus
        self._stream: Any = None  # alpaca.trading.stream.TradingStream
        self._task: asyncio.Task | None = None
        self._started: bool = False
        self._last_message_at: datetime | None = None
        self._stopping: bool = False
        self._disabled: bool = False

    # ---- public surface ----

    @property
    def is_started(self) -> bool:
        return self._started

    @property
    def is_disabled(self) -> bool:
        """True once the stream auto-disabled after repeated reconnect failures
        (fills then rely on the reconciliation polling jobs)."""
        return self._disabled

    @property
    def last_message_at(self) -> datetime | None:
        return self._last_message_at

    async def start(self) -> None:
        """Open the WS connection and start the background loop.

        Idempotent: calling start() twice is a no-op after the first.
        """
        if self._started:
            logger.debug("trade_updates_stream_already_started")
            return

        from alpaca.trading.stream import TradingStream

        self._stream = TradingStream(
            api_key=self._creds.api_key,
            secret_key=self._creds.api_secret,
            paper=self._creds.paper,
        )
        # alpaca-py expects a coroutine function as the handler.
        self._stream.subscribe_trade_updates(self._handle_update)

        # _run_forever is the underlying coroutine used by TradingStream.run().
        # We embed it as a task inside the existing event loop rather than
        # calling the sync run() (which would call asyncio.run and crash).
        self._task = asyncio.create_task(
            self._run_forever_supervised(),
            name="alpaca-trade-updates",
        )
        self._started = True
        logger.info("trade_updates_stream_started", paper=self._creds.paper)
        await self._publish_status("started")

    async def stop(self) -> None:
        """Stop the background loop and close the WS connection."""
        if not self._started:
            return
        self._stopping = True
        try:
            if self._stream is not None:
                # alpaca-py's API has shifted between stop() and stop_ws();
                # use whichever is present.
                if hasattr(self._stream, "stop_ws"):
                    await _maybe_await(self._stream.stop_ws())
                elif hasattr(self._stream, "stop"):
                    await _maybe_await(self._stream.stop())
        except Exception:
            logger.exception("trade_updates_stream_stop_ws_error")
        if self._task is not None and not self._task.done():
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await self._task
        self._task = None
        self._stream = None
        self._started = False
        logger.info("trade_updates_stream_stopped")
        await self._publish_status("stopped")

    # ---- internals ----

    async def _run_forever_supervised(self) -> None:
        """Supervise the connection ourselves with real backoff + a failure cap.

        We deliberately do NOT call alpaca-py's ``_run_forever`` (its reconnect loop
        sleeps only 0.01s → a persistently-broken socket spins the event loop at ~100%
        CPU and leaks sockets). Instead we drive the SDK's own ``_start_ws`` / ``_consume``
        / ``close`` per connection, back off exponentially on failure, and **auto-disable**
        after ``_MAX_CONSECUTIVE_FAILURES`` rapid failures — at which point fills are still
        captured by the reconciliation polling jobs.
        """
        # Mirror the minimal SDK state ``_run_forever`` would set up.
        self._stream._loop = asyncio.get_running_loop()
        self._stream._should_run = True

        failures = 0
        while not self._stopping:
            connected_at = time.monotonic()
            try:
                await self._stream._start_ws()  # connect + auth + subscribe
                await self._stream._consume()   # receive until stop (clean) or error (raises)
            except asyncio.CancelledError:
                logger.info("trade_updates_stream_cancelled")
                raise
            except Exception as exc:
                with contextlib.suppress(Exception):
                    await self._stream.close()  # always close — don't leak the socket
                if self._stopping:
                    break
                # A long-lived connection that finally errored is a transient blip, not a
                # sustained failure → reset the counter.
                if time.monotonic() - connected_at >= _MIN_HEALTHY_SECONDS:
                    failures = 0
                failures += 1
                if failures >= _MAX_CONSECUTIVE_FAILURES:
                    self._disabled = True
                    logger.warning(
                        "trade_updates_stream_disabled",
                        consecutive_failures=failures,
                        last_error=str(exc)[:200],
                    )
                    await self._publish_status("disabled")
                    return
                backoff = min(
                    _RECONNECT_BASE_BACKOFF_S * 2 ** (failures - 1),
                    _RECONNECT_MAX_BACKOFF_S,
                )
                logger.warning(
                    "trade_updates_stream_reconnect",
                    attempt=failures,
                    backoff_s=backoff,
                    error=str(exc)[:200],
                )
                await asyncio.sleep(backoff)
            else:
                # _consume returned without error → a stop was signaled via the queue.
                break

    async def _handle_update(self, data: Any) -> None:
        """alpaca-py invokes this for every trade update payload."""
        self._last_message_at = datetime.now(UTC)
        payload = _normalize_trade_update(data)
        logger.info(
            "trade_update_received",
            update_event=payload.get("event"),
            symbol=payload.get("symbol"),
            broker_order_id=payload.get("broker_order_id"),
        )
        await self._bus.publish("alpaca.trade_update", payload)

    async def _publish_status(self, status: str) -> None:
        try:
            await self._bus.publish(
                "alpaca.stream_status",
                {
                    "status": status,
                    "ts": datetime.now(UTC).isoformat(),
                    "paper": self._creds.paper,
                },
            )
        except Exception:
            logger.exception("trade_updates_stream_publish_status_failed")


# ---- helpers ----


async def _maybe_await(maybe_coro: Any) -> None:
    """alpaca-py's stop methods sometimes return None, sometimes a coroutine."""
    if asyncio.iscoroutine(maybe_coro):
        await maybe_coro


def _normalize_trade_update(data: Any) -> dict[str, Any]:
    """Map alpaca-py's TradeUpdate object (or dict) to a stable shape.

    The fields we publish are the ones Session 4's OrderRouter lifecycle will
    consume to update local Order/Fill rows. Keep this surface narrow on
    purpose; preserve the full original payload under ``raw`` for forensics.
    """
    if hasattr(data, "model_dump"):
        raw = data.model_dump(mode="json")
    elif isinstance(data, dict):
        raw = data
    else:
        raw = {
            k: getattr(data, k, None)
            for k in (
                "event",
                "order",
                "execution_id",
                "qty",
                "price",
                "position_qty",
                "timestamp",
            )
        }

    order = raw.get("order") or {}
    return {
        "event": raw.get("event"),
        "broker_order_id": (order.get("id") if isinstance(order, dict) else None),
        "client_order_id": (
            order.get("client_order_id") if isinstance(order, dict) else None
        ),
        "symbol": (order.get("symbol") if isinstance(order, dict) else None),
        "side": (order.get("side") if isinstance(order, dict) else None),
        "order_status": (order.get("status") if isinstance(order, dict) else None),
        "execution_id": raw.get("execution_id"),
        "qty": raw.get("qty"),
        "price": raw.get("price"),
        "position_qty": raw.get("position_qty"),
        "timestamp": raw.get("timestamp"),
        "raw": raw,
    }
