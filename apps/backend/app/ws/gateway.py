"""WebSocket gateway.

P0: one endpoint, one auto-subscription (to `system`), one server-side
heartbeat task. Client-driven topic subscription lands in P1+.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.config import get_settings
from app.events import get_event_bus
from app.utils.logging import get_logger

router = APIRouter()
log = get_logger("ws")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


async def heartbeat_loop() -> None:
    """Background task: publish system.heartbeat every ws_heartbeat_seconds.

    Lives for the lifetime of the app (started in lifespan).
    """
    settings = get_settings()
    bus = get_event_bus()
    interval = max(0.01, float(settings.ws_heartbeat_seconds))
    log.info("heartbeat.start", interval_s=interval)
    try:
        while True:
            await bus.publish("system", {"type": "system.heartbeat", "ts": _now_iso()})
            await asyncio.sleep(interval)
    except asyncio.CancelledError:
        log.info("heartbeat.stop")
        raise


@router.websocket("/ws")
async def ws_endpoint(websocket: WebSocket) -> None:
    settings = get_settings()
    bus = get_event_bus()
    await websocket.accept()

    await websocket.send_json(
        {
            "type": "system.connected",
            "ts": _now_iso(),
            "server_version": settings.version,
        }
    )

    subscription = bus.subscribe("system")
    forwarder: asyncio.Task[None] | None = None

    async def forward() -> None:
        async for event in subscription:
            await websocket.send_json(event)

    try:
        forwarder = asyncio.create_task(forward())
        # Drain inbound messages so the socket stays healthy; we ignore client payloads in P0.
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    except Exception as exc:
        log.warning("ws.error", error=str(exc))
    finally:
        if forwarder is not None:
            forwarder.cancel()
            try:
                await forwarder
            except (asyncio.CancelledError, Exception):
                pass
        await subscription.aclose()
