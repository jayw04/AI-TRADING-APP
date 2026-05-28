"""BarStreamService — Alpaca bar-stream subscription with cron fallback.

Subscribes to the union of symbols across active event-scheduled strategies,
forwards each bar to BarCache + StrategyEngine.dispatch_event_bar, and
activates an APScheduler cron fallback while the WS is disconnected. The
broker bindings live in :class:`BarStreamAdapter` implementations; this
service is broker-agnostic.

Lifecycle:
    * ``start()`` spawns the outer connect/run/reconnect loop.
    * ``stop()`` cancels the loop, disconnects the adapter, stops the
      fallback job, and publishes a final ``system.bar_stream_status``.
    * ``on_strategies_changed()`` is called by the engine on register /
      unregister to recompute the desired symbol set and diff-subscribe.
"""

from __future__ import annotations

import asyncio
import contextlib
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.enums import ACTIVE_STRATEGY_STATUSES
from app.db.models.strategy import Strategy as StrategyRow

logger = structlog.get_logger(__name__)


EVENT_SCHEDULE_SENTINEL = "event"

# Reconnect backoff schedule (seconds). Capped at 60s; after the cap it
# stays at 60s indefinitely.
RECONNECT_BACKOFF_STEPS: tuple[float, ...] = (1.0, 2.0, 5.0, 10.0, 30.0, 60.0)


@dataclass
class StreamedBar:
    """Broker-agnostic OHLCV bar pushed by a BarStreamAdapter."""

    symbol: str
    ts: datetime
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: Decimal


class BarStreamService:
    """Subscribes to bar pushes and notifies the engine on each bar."""

    def __init__(
        self,
        *,
        session_factory: async_sessionmaker[AsyncSession],
        engine: Any,  # app.strategies.engine.StrategyEngine
        bar_cache: Any,  # app.market_data.bar_cache.BarCache
        bus: Any | None,  # app.events.bus.EventBus
        adapter: Any | None = None,
    ) -> None:
        self._session_factory = session_factory
        self._engine = engine
        self._bar_cache = bar_cache
        self._bus = bus
        self._adapter = adapter
        self._connected = False
        self._stop_event = asyncio.Event()
        self._task: asyncio.Task[None] | None = None
        self._subscribed_symbols: set[str] = set()
        self._fallback_job_id: str | None = None

    # ---------------- public API ----------------

    @property
    def connected(self) -> bool:
        return self._connected

    @property
    def subscribed_symbols(self) -> set[str]:
        return set(self._subscribed_symbols)

    async def start(self) -> None:
        """Spawn the connect/run/reconnect loop. Idempotent."""
        if self._task is not None:
            return
        if self._adapter is None:
            from app.services.bar_stream_adapter_alpaca import AlpacaBarStreamAdapter

            self._adapter = AlpacaBarStreamAdapter(on_bar=self._on_bar_async)
        self._stop_event.clear()
        self._task = asyncio.create_task(self._run(), name="bar_stream_service")
        logger.info("bar_stream_service_started")

    async def stop(self) -> None:
        """Tear down the loop, adapter, fallback job. Idempotent."""
        self._stop_event.set()
        if self._adapter is not None:
            try:
                await self._adapter.disconnect()
            except Exception:
                logger.exception("bar_stream_disconnect_failed")
        if self._task is not None:
            try:
                await asyncio.wait_for(self._task, timeout=5.0)
            except TimeoutError:
                self._task.cancel()
                with contextlib.suppress(asyncio.CancelledError, Exception):
                    await self._task
            self._task = None
        await self._stop_fallback_job()
        await self._publish_status(False, reason="service stopped")
        logger.info("bar_stream_service_stopped")

    async def on_strategies_changed(self) -> None:
        """Recompute the desired symbol set and diff-subscribe.

        Called by :class:`StrategyEngine` on register / unregister. While
        disconnected we just remember the new set; the next reconnect picks
        it up.
        """
        desired = await self._compute_desired_symbols()
        if not self._connected or self._adapter is None:
            self._subscribed_symbols = desired
            return
        to_add = desired - self._subscribed_symbols
        to_remove = self._subscribed_symbols - desired
        if to_add:
            try:
                await self._adapter.subscribe(sorted(to_add))
                logger.info("bar_stream_subscribed", symbols=sorted(to_add))
            except Exception:
                logger.exception(
                    "bar_stream_subscribe_failed", symbols=sorted(to_add)
                )
        if to_remove:
            try:
                await self._adapter.unsubscribe(sorted(to_remove))
                logger.info("bar_stream_unsubscribed", symbols=sorted(to_remove))
            except Exception:
                logger.exception(
                    "bar_stream_unsubscribe_failed", symbols=sorted(to_remove)
                )
        self._subscribed_symbols = desired

    # ---------------- internal ----------------

    async def _run(self) -> None:
        """Outer loop: connect, run until disconnected, back off, retry."""
        attempt = 0
        while not self._stop_event.is_set():
            try:
                await self._connect_and_run()
                attempt = 0
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.warning("bar_stream_disconnected", error=str(exc))
                self._connected = False
                await self._publish_status(False, reason=str(exc)[:200])
                await self._start_fallback_job()
                backoff = RECONNECT_BACKOFF_STEPS[
                    min(attempt, len(RECONNECT_BACKOFF_STEPS) - 1)
                ]
                attempt += 1
                logger.info(
                    "bar_stream_reconnect_scheduled",
                    attempt=attempt,
                    backoff_sec=backoff,
                )
                try:
                    await asyncio.wait_for(
                        self._stop_event.wait(), timeout=backoff
                    )
                    break
                except TimeoutError:
                    pass

    async def _connect_and_run(self) -> None:
        """One connection lifetime: connect → subscribe → run until error."""
        assert self._adapter is not None
        await self._adapter.connect()
        self._subscribed_symbols = await self._compute_desired_symbols()
        if self._subscribed_symbols:
            await self._adapter.subscribe(sorted(self._subscribed_symbols))
        self._connected = True
        await self._stop_fallback_job()
        await self._publish_status(True, reason="connected")
        logger.info(
            "bar_stream_connected",
            symbols=sorted(self._subscribed_symbols),
        )
        await self._adapter.run_until_disconnected(stop_event=self._stop_event)

    async def _on_bar_async(self, bar: StreamedBar) -> None:
        """Adapter callback: update cache, dispatch to engine, publish."""
        try:
            await self._bar_cache.append_streamed_bar(bar.symbol, bar)
        except Exception:
            logger.exception(
                "bar_stream_bar_cache_append_failed",
                symbol=bar.symbol,
                ts=bar.ts.isoformat(),
            )

        try:
            await self._engine.dispatch_event_bar(symbol=bar.symbol, bar=bar)
        except Exception:
            logger.exception(
                "bar_stream_dispatch_failed",
                symbol=bar.symbol,
                ts=bar.ts.isoformat(),
            )

        if self._bus is not None:
            with contextlib.suppress(Exception):
                await self._bus.publish(
                    "bar.received",
                    {
                        "symbol": bar.symbol,
                        "ts": bar.ts.isoformat(),
                        "close": str(bar.close),
                    },
                )

    async def _compute_desired_symbols(self) -> set[str]:
        """Union of symbols across active event-scheduled strategies."""
        async with self._session_factory() as session:
            rows = (
                await session.execute(
                    select(StrategyRow).where(
                        StrategyRow.schedule == EVENT_SCHEDULE_SENTINEL,
                        StrategyRow.status.in_(list(ACTIVE_STRATEGY_STATUSES)),
                    )
                )
            ).scalars().all()
        symbols: set[str] = set()
        for r in rows:
            for s in r.symbols_json or []:
                symbols.add(str(s).strip().upper())
        return symbols

    async def _publish_status(self, connected: bool, *, reason: str) -> None:
        if self._bus is None:
            return
        with contextlib.suppress(Exception):
            await self._bus.publish(
                "system.bar_stream_status",
                {
                    "connected": connected,
                    "reason": reason,
                    "subscribed_symbols": sorted(self._subscribed_symbols),
                },
            )

    async def _start_fallback_job(self) -> None:
        """Activate the engine's cron-fallback dispatcher while WS is down."""
        if self._fallback_job_id is not None:
            return
        try:
            self._fallback_job_id = await self._engine.start_event_fallback(
                interval_seconds=60,
            )
            logger.info(
                "bar_stream_fallback_started", job_id=self._fallback_job_id
            )
        except Exception:
            logger.exception("bar_stream_fallback_start_failed")

    async def _stop_fallback_job(self) -> None:
        if self._fallback_job_id is None:
            return
        try:
            await self._engine.stop_event_fallback(self._fallback_job_id)
            logger.info(
                "bar_stream_fallback_stopped", job_id=self._fallback_job_id
            )
        except Exception:
            logger.exception("bar_stream_fallback_stop_failed")
        finally:
            self._fallback_job_id = None
