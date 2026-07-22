"""ADR 0042 § A — fetch a CAUSALLY COMPLETE account snapshot for a single decision.

There is **no "N seconds old" allowance**. Registering one would treat staleness as a tunable
when the requirement is *causal completeness*:

    The snapshot must be AT OR BEYOND every broker event we have already observed locally.

A snapshot that is merely *recent* but sits **behind a fill we have already recorded** is not a
stale account — **it is a different account**, and classifying against it can approve a
reduction that has, in reality, already happened.

So:

* ``broker_cursor``  — the newest broker-side event in THIS snapshot (Alpaca's own timestamps).
* ``observed_cursor``— the newest broker-side event we have ALREADY persisted locally.

Both are broker-issued timestamps, so they are comparable without trusting our own clock. If
``broker_cursor < observed_cursor`` the read is behind us: ``INDETERMINATE`` → ``FAIL_CLOSED``.

A cached positions object is never sufficient here, regardless of nominal age. This module
always performs a live broker read, initiated for the decision at hand.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any

import structlog
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.enums import TERMINAL_ORDER_STATUSES, OrderSide
from app.db.models.fill import Fill
from app.db.models.order import Order
from app.risk.risk_effect import (
    AccountSnapshot,
    SnapshotOpenOrder,
    SnapshotPosition,
)

logger = structlog.get_logger(__name__)

ZERO = Decimal(0)


def _dec(v: Any, default: Decimal = ZERO) -> Decimal:
    if v is None or v == "":
        return default
    try:
        return Decimal(str(v))
    except (InvalidOperation, ValueError):
        return default


def _event_time(o: dict[str, Any]) -> str:
    """The newest broker-side timestamp on this order. Broker-issued, so comparable across
    reads without trusting our clock."""
    candidates = [
        o.get("filled_at"),
        o.get("canceled_at"),
        o.get("updated_at"),
        o.get("submitted_at"),
        o.get("created_at"),
    ]
    stamps = [str(c) for c in candidates if c]
    return max(stamps) if stamps else ""


async def fetch_snapshot(
    *,
    session: AsyncSession,
    account_id: int,
    adapter: Any,  # BrokerAdapter
    reserved_reducing_qty: dict[str, Decimal] | None = None,
    absorbed_reserved_fill_qty: dict[str, Decimal] | None = None,
) -> AccountSnapshot:
    """Live broker read + the local causality anchor. Never returns cached state.

    On ANY failure the snapshot is returned with ``complete=False``, which the classifier turns
    into ``INDETERMINATE`` → ``FAIL_CLOSED``. A broker we cannot read is not permission to
    trade.
    """
    try:
        acct = adapter.get_account()
        broker_positions = adapter.get_positions()
        broker_orders = adapter.list_orders(status="open", limit=500)
    except Exception:
        logger.exception("risk_snapshot_broker_read_failed", account_id=account_id)
        return AccountSnapshot(
            account_id=account_id,
            positions={},
            open_orders=[],
            cash=ZERO,
            equity=ZERO,
            broker_cursor=None,
            observed_cursor=None,
            complete=False,
        )

    positions: dict[str, SnapshotPosition] = {}
    for p in broker_positions:
        sym = str(p.get("symbol", "")).upper()
        if not sym:
            continue
        qty = _dec(p.get("qty"))
        # Alpaca reports a short as side="short" with a positive qty in some SDK paths; make the
        # sign explicit, because the whole classifier turns on it.
        if str(p.get("side", "long")).lower().endswith("short") and qty > ZERO:
            qty = -qty
        price = _dec(p.get("current_price")) or (
            abs(_dec(p.get("market_value"))) / abs(qty) if qty else ZERO
        )
        positions[sym] = SnapshotPosition(symbol=sym, qty=qty, price=price)

    open_orders: list[SnapshotOpenOrder] = []
    for o in broker_orders:
        sym = str(o.get("symbol", "")).upper()
        side_raw = str(o.get("side", "")).split(".")[-1].lower()
        side = OrderSide.SELL if side_raw == "sell" else OrderSide.BUY
        qty = _dec(o.get("qty"))
        filled = _dec(o.get("filled_qty"))
        remaining = max(ZERO, qty - filled)

        held = positions.get(sym)
        held_qty = held.qty if held else ZERO
        # "Reduces the position" is a projected-state question, not a verb question.
        reduces = (side == OrderSide.SELL and held_qty > ZERO) or (
            side == OrderSide.BUY and held_qty < ZERO
        )
        # A partially-filled order whose fill we have NOT yet ingested locally leaves the true
        # position ambiguous. Ambiguity is INDETERMINATE, never "probably fine".
        unresolved = filled > ZERO and not await _fill_is_known_locally(
            session, str(o.get("id", ""))
        )
        open_orders.append(
            SnapshotOpenOrder(
                order_id=str(o.get("id", "")),
                symbol=sym,
                side=side,
                remaining_qty=remaining,
                reduces_position=reduces,
                has_unresolved_partial_fill=unresolved,
            )
        )

    broker_cursor = max((_event_time(o) for o in broker_orders), default="") or str(
        acct.get("id", "")
    )
    observed_cursor = await _observed_cursor(session, account_id)

    return AccountSnapshot(
        account_id=account_id,
        positions=positions,
        open_orders=open_orders,
        cash=_dec(acct.get("cash")),
        equity=_dec(acct.get("equity")),
        broker_cursor=broker_cursor or None,
        observed_cursor=observed_cursor,
        complete=True,
        reserved_reducing_qty=reserved_reducing_qty or {},
        absorbed_reserved_fill_qty=absorbed_reserved_fill_qty or {},
    )


async def _fill_is_known_locally(session: AsyncSession, broker_order_id: str) -> bool:
    """Have we ingested a fill for this broker order?"""
    if not broker_order_id:
        return False
    n = (
        await session.execute(
            select(func.count(Fill.id))
            .join(Order, Order.id == Fill.order_id)
            .where(Order.broker_order_id == broker_order_id)
        )
    ).scalar_one()
    return bool(n)


async def _observed_cursor(session: AsyncSession, account_id: int) -> str | None:
    """The newest BROKER-side event we have already persisted.

    The snapshot must be at or beyond this. Uses broker-issued timestamps (``fills.filled_at``
    is the broker's own stamp), so the comparison never depends on our clock.
    """
    newest_fill = (
        await session.execute(
            select(func.max(Fill.filled_at))
            .join(Order, Order.id == Fill.order_id)
            .where(Order.account_id == account_id)
        )
    ).scalar_one_or_none()

    newest_order = (
        await session.execute(
            select(func.max(Order.updated_at)).where(
                Order.account_id == account_id,
                Order.status.notin_(TERMINAL_ORDER_STATUSES),
            )
        )
    ).scalar_one_or_none()

    stamps = [str(s) for s in (newest_fill, newest_order) if s is not None]
    return max(stamps) if stamps else None
