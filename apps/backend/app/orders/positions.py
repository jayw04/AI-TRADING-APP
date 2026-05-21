"""Position recomputer.

Aggregates all fills for an ``(account, symbol)`` pair into ``qty +
avg_entry_price + cost_basis`` and upserts the ``positions`` row. Called by
the trade-update consumer on every fill so the UI sees position changes
immediately rather than waiting for the next 10-second position sync.

The periodic ``PositionSyncService`` also writes to the same row — that's
intentional belt-and-suspenders. The sync owns ``market_value`` and
``unrealized_pl`` (live quote-derived); this recomputer owns ``qty``,
``avg_entry_price``, ``cost_basis``, and ``side`` (fill-derived).
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import structlog
from sqlalchemy import delete, select
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.db.enums import OrderSide
from app.db.models.fill import Fill
from app.db.models.order import Order
from app.db.models.position import Position
from app.events.bus import EventBus

logger = structlog.get_logger(__name__)


class PositionRecomputer:
    def __init__(self, session_factory: async_sessionmaker, bus: EventBus) -> None:
        self._session_factory = session_factory
        self._bus = bus

    async def recompute(self, account_id: int, symbol_id: int) -> None:
        async with self._session_factory() as session:
            rows = (
                await session.execute(
                    select(Fill, Order)
                    .join(Order, Fill.order_id == Order.id)
                    .where(
                        Order.account_id == account_id,
                        Order.symbol_id == symbol_id,
                    )
                    .order_by(Fill.filled_at)
                )
            ).all()

            qty = Decimal(0)
            cost_basis = Decimal(0)

            for fill, order in rows:
                signed = fill.qty if order.side == OrderSide.BUY else -fill.qty
                new_qty = qty + signed

                # Flip through zero: reset cost basis using the remainder.
                if (qty > 0 and new_qty < 0) or (qty < 0 and new_qty > 0):
                    cost_basis = abs(new_qty) * fill.price
                    qty = new_qty
                    continue
                # Closed out exactly:
                if new_qty == 0:
                    qty = new_qty
                    cost_basis = Decimal(0)
                    continue
                # Opening from flat:
                if qty == 0:
                    cost_basis = abs(signed) * fill.price
                # Adding to position (same direction):
                elif (qty > 0 and signed > 0) or (qty < 0 and signed < 0):
                    cost_basis += abs(signed) * fill.price
                # Reducing (opposite direction, not crossing zero):
                else:
                    avg = cost_basis / abs(qty)
                    cost_basis -= abs(signed) * avg
                qty = new_qty

            now = datetime.now(UTC)
            if qty == 0:
                await session.execute(
                    delete(Position).where(
                        Position.account_id == account_id,
                        Position.symbol_id == symbol_id,
                    )
                )
            else:
                avg_entry_price = cost_basis / abs(qty)
                side = "long" if qty > 0 else "short"
                user_id = rows[0][1].user_id if rows else None
                if user_id is None:
                    await session.commit()
                    return

                stmt = sqlite_insert(Position).values(
                    user_id=user_id,
                    account_id=account_id,
                    symbol_id=symbol_id,
                    qty=qty,
                    avg_entry_price=avg_entry_price,
                    side=side,
                    # market_value / unrealized_pl owned by PositionSyncService
                    market_value=Decimal(0),
                    cost_basis=cost_basis,
                    unrealized_pl=Decimal(0),
                    unrealized_plpc=Decimal(0),
                    updated_at=now,
                )
                stmt = stmt.on_conflict_do_update(
                    index_elements=["account_id", "symbol_id"],
                    set_={
                        "qty": stmt.excluded.qty,
                        "avg_entry_price": stmt.excluded.avg_entry_price,
                        "side": stmt.excluded.side,
                        "cost_basis": stmt.excluded.cost_basis,
                        "updated_at": stmt.excluded.updated_at,
                    },
                )
                await session.execute(stmt)

            await session.commit()

        await self._bus.publish(
            "position.updated",
            {"account_id": account_id, "symbol_id": symbol_id, "qty": str(qty)},
        )
        logger.info(
            "position_recomputed",
            account_id=account_id,
            symbol_id=symbol_id,
            qty=str(qty),
        )
