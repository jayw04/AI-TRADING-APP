"""Daily asset/symbol universe sync.

Pulls Alpaca's active US-equity tradable assets and upserts into the local
`symbols` table. Symbols no longer in Alpaca's active list are marked
inactive (active=False) — never deleted, so historical references remain
joinable.
"""

from __future__ import annotations

import asyncio
from typing import Any

import structlog
from sqlalchemy import select, update
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.brokers.alpaca import AlpacaAdapter
from app.db.models.symbol import Symbol
from app.events.bus import EventBus

logger = structlog.get_logger(__name__)


class AssetSyncService:
    """Syncs the local `symbols` table against Alpaca's asset universe.

    Designed to be called from the scheduler — not from a request handler.
    """

    def __init__(
        self,
        adapter: AlpacaAdapter,
        session_factory: async_sessionmaker,
        bus: EventBus,
    ) -> None:
        self._adapter = adapter
        self._session_factory = session_factory
        self._bus = bus

    async def sync_once(self) -> dict[str, int]:
        """Run one full sync. Returns counts for observability/testing.

        Strategy:
          1. Fetch the active US-equity asset list from Alpaca (sync call,
             wrapped in `asyncio.to_thread` so we don't block the event loop).
          2. Upsert active rows.
          3. Deactivate locals that are no longer in Alpaca's active list.
          4. Publish `system.symbols_synced` event.
        """
        logger.info("asset_sync_started")
        alpaca_assets = await asyncio.to_thread(self._adapter.list_assets, True)
        alpaca_by_ticker = {a["symbol"]: a for a in alpaca_assets if a.get("symbol")}

        added = 0
        updated = 0
        deactivated = 0

        async with self._session_factory() as session:
            existing = (await session.execute(select(Symbol))).scalars().all()
            existing_by_ticker = {s.ticker: s for s in existing}

            # Upsert active assets
            for ticker, asset in alpaca_by_ticker.items():
                payload = _alpaca_asset_to_symbol_payload(asset)
                stmt = sqlite_insert(Symbol).values(**payload)
                stmt = stmt.on_conflict_do_update(
                    index_elements=["ticker"],
                    set_={
                        "exchange": stmt.excluded.exchange,
                        "asset_class": stmt.excluded.asset_class,
                        "name": stmt.excluded.name,
                        "active": True,
                    },
                )
                await session.execute(stmt)
                if ticker in existing_by_ticker:
                    updated += 1
                else:
                    added += 1

            # Deactivate locals not in the Alpaca active list (only those still active)
            tickers_to_deactivate = [
                t
                for t in existing_by_ticker
                if t not in alpaca_by_ticker and existing_by_ticker[t].active
            ]
            if tickers_to_deactivate:
                await session.execute(
                    update(Symbol)
                    .where(Symbol.ticker.in_(tickers_to_deactivate))
                    .values(active=False)
                )
                deactivated = len(tickers_to_deactivate)

            await session.commit()

        counts = {
            "count_total": len(alpaca_by_ticker),
            "count_added": added,
            "count_updated": updated,
            "count_deactivated": deactivated,
        }
        logger.info("asset_sync_completed", **counts)
        await self._bus.publish("system.symbols_synced", counts)
        return counts


def _alpaca_asset_to_symbol_payload(asset: dict[str, Any]) -> dict[str, Any]:
    """Translate one Alpaca asset record into the columns of `symbols`."""
    exchange = (asset.get("exchange") or "")[:20]  # Symbol.exchange is String(20)
    return {
        "ticker": asset["symbol"],
        "exchange": exchange,
        "asset_class": (asset.get("class") or asset.get("asset_class") or "us_equity")[:20],
        "name": (asset.get("name") or asset["symbol"])[:255],
        "active": True,
    }
