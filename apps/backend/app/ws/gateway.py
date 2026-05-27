"""WebSocket gateway with topic subscriptions and per-topic replay.

Client → server messages (JSON):
    {"action": "subscribe",   "topics": ["orders", "positions", "system"]}
    {"action": "unsubscribe", "topics": [...]}
    {"action": "ping"}

Server → client messages (JSON):
    {"topic": "orders", "type": "order.submitted", "payload": {...}, "ts": "..."}

A WS connection auto-subscribes to "system" on accept and receives a
``system.connected`` event immediately. Subsequent subscriptions replay the
recent buffer for the requested topic before live events start flowing.

Bus → WS topic mapping is in ``_bus_to_ws_topic``. The set of bus topics we
forward is ``_BUS_TOPICS``; a single process-global replay populator task
subscribes to each of them and writes to the global ReplayBuffer (one entry
per published event, not per connection).
"""

from __future__ import annotations

import asyncio
import contextlib
import json
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.config import get_settings
from app.events import get_event_bus
from app.utils.logging import get_logger
from app.ws.replay import get_replay_buffer

router = APIRouter()
log = get_logger("ws")


# ---- Bus topics we forward to WS clients ----

# Bus topics emitted by Sessions 2–5. The mapping function below routes each
# to a stable WS topic. If you add a new bus topic, add it here and update
# _bus_to_ws_topic.
_BUS_TOPICS: tuple[str, ...] = (
    # system
    "system.heartbeat",
    "system.symbols_synced",
    "system.reconciliation_drift",
    "alpaca.stream_status",
    "account.snapshot",
    # orders
    "order.submitted",
    "order.rejected",
    "order.canceled",
    "order.expired",
    "order.replaced",
    "order.filled",
    "order.partially_filled",
    "order.updated",
    "order.cancel_requested",
    "order.replace_requested",
    "order.submit_transient_error",
    # fills
    "fill.created",
    "alpaca.trade_update",
    # positions
    "positions.snapshot",
    "position.updated",
    # strategies (P2 S4)
    "strategy.status_changed",
    "strategy.run_started",
    "strategy.run_ended",
    "strategy.error",
    # strategies (P4 §4: hot-reload signaling)
    "strategy.pending_reload",
    # signals (P2 S4)
    "signal.new",
    # backtests (P2 S4 + P4 §2)
    "backtest.queued",
    "backtest.started",
    "backtest.progress",
    "backtest.completed",
    "backtest.failed",
    "backtest.cancelled",
)


def _bus_to_ws_topic(bus_topic: str) -> str | None:
    """Translate a bus topic to its WS topic. None means "don't forward"."""
    if bus_topic.startswith("order."):
        return "orders"
    if bus_topic.startswith("fill.") or bus_topic == "alpaca.trade_update":
        return "fills"
    if bus_topic in ("positions.snapshot", "position.updated"):
        return "positions"
    if (
        bus_topic.startswith("system.")
        or bus_topic == "alpaca.stream_status"
        or bus_topic == "account.snapshot"
    ):
        return "system"
    if bus_topic.startswith("strategy."):
        return "strategies"
    if bus_topic == "signal.new":
        return "signals"
    if bus_topic.startswith("backtest."):
        return "backtests"
    return None


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _wrap(topic: str, type_: str, payload: dict[str, Any]) -> str:
    return json.dumps(
        {
            "topic": topic,
            "type": type_,
            "payload": payload,
            "ts": _now_iso(),
        }
    )


# ---- Heartbeat (published on bus topic "system.heartbeat") ----


async def heartbeat_loop() -> None:
    """Publish ``system.heartbeat`` to the bus every ``ws_heartbeat_seconds``.

    Lives for the lifetime of the app (started in lifespan). The WS gateway
    forwards it to clients subscribed to the ``system`` WS topic.
    """
    settings = get_settings()
    bus = get_event_bus()
    interval = max(0.01, float(settings.ws_heartbeat_seconds))
    log.info("heartbeat.start", interval_s=interval)
    try:
        while True:
            await bus.publish("system.heartbeat", {"ts": _now_iso()})
            await asyncio.sleep(interval)
    except asyncio.CancelledError:
        log.info("heartbeat.stop")
        raise


# ---- Replay populator (process-global) ----


async def _populate_replay_loop(bus_topic: str) -> None:
    """One task per bus topic — writes each event to the global ReplayBuffer.

    Started by ``start_replay_populator()`` in the lifespan. Separate from
    per-connection forwarders so we don't duplicate-append on every connect.
    """
    bus = get_event_bus()
    buf = get_replay_buffer()
    ws_topic = _bus_to_ws_topic(bus_topic)
    if ws_topic is None:
        return
    async for event in bus.subscribe(bus_topic):
        buf.append(ws_topic, {"__event__": bus_topic, **event})


_populator_tasks: list[asyncio.Task[None]] = []


def start_replay_populator() -> None:
    """Spawn one populator task per bus topic. Idempotent."""
    if _populator_tasks:
        return
    for bus_topic in _BUS_TOPICS:
        t = asyncio.create_task(
            _populate_replay_loop(bus_topic),
            name=f"ws-replay-populator:{bus_topic}",
        )
        _populator_tasks.append(t)
    log.info("ws.replay_populator_started", count=len(_populator_tasks))


async def stop_replay_populator() -> None:
    """Cancel all populator tasks. Idempotent."""
    if not _populator_tasks:
        return
    for t in _populator_tasks:
        t.cancel()
    for t in _populator_tasks:
        with contextlib.suppress(asyncio.CancelledError, Exception):
            await t
    _populator_tasks.clear()
    log.info("ws.replay_populator_stopped")


# ---- WS endpoint ----


@router.websocket("/ws")
async def ws_endpoint(websocket: WebSocket) -> None:
    settings = get_settings()
    bus = get_event_bus()
    buf = get_replay_buffer()
    await websocket.accept()

    # Per-connection state.
    subscriptions: set[str] = {"system"}  # heartbeat + connected events always on

    # Send the connected event first.
    await websocket.send_text(
        _wrap(
            "system",
            "system.connected",
            {"server_version": settings.version},
        )
    )

    # Spawn one forwarder task per bus topic. Each forwards live events to
    # the WS if its mapped WS topic is currently subscribed.
    forwarder_tasks: list[asyncio.Task[None]] = []

    async def _forward(bus_topic: str) -> None:
        ws_topic = _bus_to_ws_topic(bus_topic)
        if ws_topic is None:
            return
        async for event in bus.subscribe(bus_topic):
            if ws_topic not in subscriptions:
                continue
            try:
                await websocket.send_text(_wrap(ws_topic, bus_topic, event))
            except Exception:
                # Socket closed mid-send; let the receive_text loop unwind.
                return

    for bus_topic in _BUS_TOPICS:
        forwarder_tasks.append(
            asyncio.create_task(
                _forward(bus_topic), name=f"ws-forward:{bus_topic}"
            )
        )

    try:
        while True:
            msg = await websocket.receive_text()
            try:
                data = json.loads(msg)
            except json.JSONDecodeError:
                continue
            action = data.get("action")
            topics = data.get("topics") or []
            if action == "subscribe":
                for t in topics:
                    if not isinstance(t, str):
                        continue
                    subscriptions.add(t)
                    # Replay any buffered events for this WS topic.
                    for evt in buf.get_recent(t):
                        type_ = evt.get("__event__", t)
                        # Strip internal __event__ marker before sending.
                        payload = {k: v for k, v in evt.items() if k != "__event__"}
                        try:
                            await websocket.send_text(_wrap(t, type_, payload))
                        except Exception:
                            break
            elif action == "unsubscribe":
                for t in topics:
                    if isinstance(t, str):
                        subscriptions.discard(t)
            elif action == "ping":
                await websocket.send_text(_wrap("system", "system.pong", {}))
    except WebSocketDisconnect:
        pass
    except Exception as exc:
        log.warning("ws.error", error=str(exc))
    finally:
        for t in forwarder_tasks:
            t.cancel()
        for t in forwarder_tasks:
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await t
