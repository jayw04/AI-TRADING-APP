"""ADR 0042 § A — fetch a CAUSALLY COMPLETE account snapshot for a single decision.

There is **no "N seconds old" allowance**. Registering one would treat staleness as a tunable
when the requirement is *causal completeness*:

    The snapshot must be AT OR BEYOND every broker event we have already observed locally.

A snapshot that is merely *recent* but sits **behind a fill we have already recorded** is not a
stale account — **it is a different account**, and classifying against it can approve a
reduction that has, in reality, already happened.

So:

* ``broker_cursor``  — the **broker-read cursor**: newest broker-side event in THIS snapshot,
  stamped by the broker (Alpaca's own timestamps), or ``None`` when the read carried no events.
* ``observed_cursor``— the **locally observed execution cursor**: newest broker-side event we
  have ALREADY persisted.

If ``broker_cursor < observed_cursor`` the read is behind us: ``INDETERMINATE`` →
``FAIL_CLOSED``.

⚠ **These two are NOT guaranteed to share a clock**, and this module must not claim they do.
``broker_cursor`` is broker-stamped throughout, but ``observed_cursor`` is a ``max()`` over
``fills.filled_at`` (the broker's stamp) **and** ``orders.updated_at`` (ours), so the value that
wins can be locally stamped. Comparing them lexically is therefore a practical ordering test
that assumes roughly-synchronised clocks — not the clock-independent causality proof an earlier
version of this docstring asserted. Normalising the two into distinct, non-comparable cursor
domains is tracked in **#631**; it is deliberately out of scope here.

A broker read containing **no order events** has no timestamp to offer. That is the normal
state of a settled account — positions held, nothing in flight — and it is NOT evidence of
staleness. Never substitute a non-temporal identifier (an account id) for the missing stamp:
it is not a point in time, and it makes every settled account permanently stale. The states the
gate must distinguish:

===========================  ================================  =====================
broker open orders           local in-flight orders            verdict
===========================  ================================  =====================
none                         none                              causally complete
none                         present, SAME symbol              ``SNAPSHOT_STALE``
none                         present, other symbol only        depends — see below
present, no usable stamp     —                                 ``SNAPSHOT_INCOMPLETE``
stamped, < observed_cursor   —                                 ``SNAPSHOT_STALE``
===========================  ================================  =====================

The "other symbol only" row resolves to *causally complete* **only** for an order already proven
to reduce an existing position in its own symbol without crossing zero, and to ``SNAPSHOT_STALE``
for everything else. See ``AccountSnapshot.is_causally_complete``.

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
from app.db.models.symbol import Symbol
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

    # A broker-issued TIMESTAMP or nothing. NEVER fall back to a non-temporal identifier such
    # as the account id: it is not a point in time, and a UUID beginning with a digit below
    # "2" sorts before every ISO timestamp, which silently marks every settled account stale.
    broker_cursor = max((_event_time(o) for o in broker_orders), default="") or None
    observed_cursor = await _observed_cursor(session, account_id)
    observed_inflight_by_symbol = await _observed_inflight_by_symbol(session, account_id)

    return AccountSnapshot(
        account_id=account_id,
        positions=positions,
        open_orders=open_orders,
        cash=_dec(acct.get("cash")),
        equity=_dec(acct.get("equity")),
        broker_cursor=broker_cursor,
        observed_cursor=observed_cursor,
        observed_inflight_by_symbol=observed_inflight_by_symbol,
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
    """The locally observed execution cursor: newest broker-side event we have already persisted.

    The snapshot must be at or beyond this.

    ⚠ **Mixed provenance.** This is a ``max()`` over ``fills.filled_at`` — the broker's own stamp —
    and ``orders.updated_at``, which is ours. Whichever is larger wins, so the returned value is
    not reliably broker-issued and the comparison against ``broker_cursor`` is not clock-independent.
    Stated plainly because an earlier docstring claimed the opposite; see the module header and #631.
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


async def _observed_inflight_by_symbol(
    session: AsyncSession, account_id: int
) -> dict[str, str]:
    """Newest broker-side event we have persisted that could STILL BE IN FLIGHT, PER SYMBOL.

    Used only when the broker read contains no open orders at all, where there is no broker
    timestamp to compare against. The question there is not "is this read behind us" but
    "do we and the broker agree that nothing is in flight".

    Settled (terminal) fills are deliberately excluded HERE — and only here. Their economic
    effect is already carried by the positions, cash and equity fetched live in this same
    snapshot, so they are not evidence of a present disagreement. They remain in the ledger,
    and they still count in ``_observed_cursor`` whenever a broker cursor exists to compare
    against. Without this distinction an account that is flat of open orders but has ever
    filled can never be classified again, which blocks the risk-REDUCING path exactly when a
    locked account needs it (2026-07-27 incident).

    **Keyed by symbol, not collapsed to one account-wide stamp.** An account-wide scalar meant
    one unresolved local row — the documented "trade-updates flap leaves an order stuck
    SUBMITTED" mode — permanently blocked risk-reducing exits in EVERY symbol on the account.
    That is the same shape of permanent trap this module exists to remove, only narrower, and
    it bites hardest on a multi-symbol emergency exit (account 1 held four). Callers decide
    which key is relevant; see ``AccountSnapshot.is_causally_complete``.
    """
    fills = (
        await session.execute(
            select(Symbol.ticker, func.max(Fill.filled_at))
            .select_from(Fill)
            .join(Order, Order.id == Fill.order_id)
            .join(Symbol, Symbol.id == Order.symbol_id)
            .where(
                Order.account_id == account_id,
                Order.status.notin_(TERMINAL_ORDER_STATUSES),
            )
            .group_by(Symbol.ticker)
        )
    ).all()

    orders = (
        await session.execute(
            select(Symbol.ticker, func.max(Order.updated_at))
            .select_from(Order)
            .join(Symbol, Symbol.id == Order.symbol_id)
            .where(
                Order.account_id == account_id,
                Order.status.notin_(TERMINAL_ORDER_STATUSES),
            )
            .group_by(Symbol.ticker)
        )
    ).all()

    out: dict[str, str] = {}
    for ticker, stamp in list(fills) + list(orders):
        if ticker is None or stamp is None:
            continue
        key = str(ticker).upper()
        val = str(stamp)
        if key not in out or val > out[key]:
            out[key] = val
    return out
