"""Position snapshot poller.

Pulls positions from Alpaca, upserts into the `positions` table, deletes
positions Alpaca no longer reports (closed), publishes a snapshot event.

Session 4 added DB persistence (this file). Session 5 will add a second
write path from the trade-update consumer so positions update immediately
on fill rather than waiting for the next 10s poll.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

import structlog
from sqlalchemy import delete, select
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.brokers.alpaca import AlpacaAdapter
from app.db.models.account import Account, AccountMode
from app.db.models.position import Position
from app.db.models.symbol import Symbol
from app.events.bus import EventBus

logger = structlog.get_logger(__name__)


class PositionSyncService:
    def __init__(
        self,
        adapter: AlpacaAdapter,
        session_factory: async_sessionmaker,
        bus: EventBus,
    ) -> None:
        self._adapter = adapter
        self._session_factory = session_factory
        self._bus = bus

    async def sync_once(self) -> list[dict[str, Any]]:
        """Pull positions, upsert into DB, delete stale rows, publish snapshot."""
        raw_positions = await asyncio.to_thread(self._adapter.get_positions)
        normalized = [_normalize_position(p) for p in raw_positions]

        async with self._session_factory() as session:
            mode = AccountMode.paper if self._adapter.is_paper else AccountMode.live
            account = (
                await session.execute(
                    select(Account).where(Account.broker == "alpaca", Account.mode == mode)
                )
            ).scalars().first()
            if account is None:
                logger.warning("position_sync_no_account_row")
                await self._bus.publish(
                    "positions.snapshot",
                    {"count": len(normalized), "positions": _decimals_to_str(normalized)},
                )
                return normalized

            tickers = [p["symbol"] for p in normalized if p["symbol"]]
            symbol_rows = (
                (
                    await session.execute(
                        select(Symbol).where(Symbol.ticker.in_(tickers))
                    )
                ).scalars().all()
                if tickers
                else []
            )
            symbol_id_by_ticker = {s.ticker: s.id for s in symbol_rows}

            now = datetime.now(UTC)
            seen_symbol_ids: set[int] = set()

            for p in normalized:
                ticker = p["symbol"]
                symbol_id = symbol_id_by_ticker.get(ticker)
                if symbol_id is None:
                    # Symbol not in our table — asset sync hasn't picked it up,
                    # or it's a delisted name. Skip for MVP; P4 polish can add
                    # a "create-on-demand" fallback.
                    logger.warning("position_sync_unknown_symbol", ticker=ticker)
                    continue
                seen_symbol_ids.add(symbol_id)

                stmt = sqlite_insert(Position).values(
                    user_id=account.user_id,
                    account_id=account.id,
                    symbol_id=symbol_id,
                    qty=p["qty"],
                    avg_entry_price=p["avg_entry_price"],
                    side=p["side"],
                    market_value=p["market_value"],
                    cost_basis=p["cost_basis"],
                    unrealized_pl=p["unrealized_pl"],
                    unrealized_plpc=p["unrealized_plpc"],
                    updated_at=now,
                )
                stmt = stmt.on_conflict_do_update(
                    index_elements=["account_id", "symbol_id"],
                    set_={
                        "qty": stmt.excluded.qty,
                        "avg_entry_price": stmt.excluded.avg_entry_price,
                        "side": stmt.excluded.side,
                        "market_value": stmt.excluded.market_value,
                        "cost_basis": stmt.excluded.cost_basis,
                        "unrealized_pl": stmt.excluded.unrealized_pl,
                        "unrealized_plpc": stmt.excluded.unrealized_plpc,
                        "updated_at": stmt.excluded.updated_at,
                    },
                )
                await session.execute(stmt)

            # Delete stale positions Alpaca no longer reports. The Position
            # table is the "open positions" cache; closed positions leave
            # history in orders/fills, not here.
            existing_ids = (
                await session.execute(
                    select(Position.symbol_id).where(Position.account_id == account.id)
                )
            ).scalars().all()
            stale = [sid for sid in existing_ids if sid not in seen_symbol_ids]
            if stale:
                await session.execute(
                    delete(Position).where(
                        Position.account_id == account.id,
                        Position.symbol_id.in_(stale),
                    )
                )
                logger.info("position_sync_deleted_stale", count=len(stale))

            await session.commit()

        logger.info("position_sync_completed", count=len(normalized))
        await self._bus.publish(
            "positions.snapshot",
            {"count": len(normalized), "positions": _decimals_to_str(normalized)},
        )
        return normalized


def _to_decimal(v: Any) -> Decimal:
    if v is None or v == "":
        return Decimal(0)
    try:
        return Decimal(str(v))
    except Exception:
        return Decimal(0)


def _normalize_position(raw: dict[str, Any]) -> dict[str, Any]:
    return {
        "symbol": raw.get("symbol"),
        "qty": _to_decimal(raw.get("qty")),
        "avg_entry_price": _to_decimal(raw.get("avg_entry_price")),
        "side": raw.get("side"),
        "market_value": _to_decimal(raw.get("market_value")),
        "cost_basis": _to_decimal(raw.get("cost_basis")),
        "unrealized_pl": _to_decimal(raw.get("unrealized_pl")),
        "unrealized_plpc": _to_decimal(raw.get("unrealized_plpc")),
    }


def _decimals_to_str(positions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """JSON-friendly snapshot for the event bus subscribers."""
    return [
        {k: (str(v) if isinstance(v, Decimal) else v) for k, v in p.items()}
        for p in positions
    ]
