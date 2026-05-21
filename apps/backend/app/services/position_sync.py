"""Position snapshot poller.

For Session 2: pulls positions from Alpaca and publishes them as a snapshot
event. No DB persistence — the `positions` table lands in P1 Session 4 along
with orders/fills, and this service will be extended then to upsert into it.
"""

from __future__ import annotations

import asyncio
from typing import Any

import structlog

from app.brokers.alpaca import AlpacaAdapter
from app.events.bus import EventBus

logger = structlog.get_logger(__name__)


class PositionSyncService:
    def __init__(self, adapter: AlpacaAdapter, bus: EventBus) -> None:
        self._adapter = adapter
        self._bus = bus

    async def sync_once(self) -> list[dict[str, Any]]:
        """Pull positions, publish snapshot, return them.

        Session 4 will add the side-effect of upserting into the `positions`
        table; for now this is read-and-publish.
        """
        positions = await asyncio.to_thread(self._adapter.get_positions)
        normalized = [_normalize_position(p) for p in positions]
        logger.info("position_sync_completed", count=len(normalized))
        await self._bus.publish(
            "positions.snapshot",
            {"count": len(normalized), "positions": normalized},
        )
        return normalized


def _normalize_position(raw: dict[str, Any]) -> dict[str, Any]:
    """Pick the fields the UI / event subscribers care about."""
    return {
        "symbol": raw.get("symbol"),
        "qty": _maybe_number(raw.get("qty")),
        "avg_entry_price": _maybe_number(raw.get("avg_entry_price")),
        "side": raw.get("side"),
        "market_value": _maybe_number(raw.get("market_value")),
        "cost_basis": _maybe_number(raw.get("cost_basis")),
        "unrealized_pl": _maybe_number(raw.get("unrealized_pl")),
        "unrealized_plpc": _maybe_number(raw.get("unrealized_plpc")),
        "current_price": _maybe_number(raw.get("current_price")),
        "lastday_price": _maybe_number(raw.get("lastday_price")),
        "change_today": _maybe_number(raw.get("change_today")),
        "asset_class": raw.get("asset_class"),
    }


def _maybe_number(v: Any) -> str | None:
    """Keep as a string to preserve precision; the consumer can Decimal it.

    Alpaca returns numeric fields as strings in JSON; we propagate that.
    """
    if v is None or v == "":
        return None
    return str(v)
