"""ADR 0042 § B — cancellation is not automatically risk-reducing.

Before this, ``OrderRouter.cancel()`` reached the broker with **no risk evaluation of any
kind**. On a locked account an operator could cancel a pending sell-to-close — removing the one
protective reduction that was de-risking the book — and nothing would stop them. That is
precisely the trapped-risk move the whole ADR was written to prevent, available as a one-click
operation.

A blanket "cancels always pass" exemption would have shipped that hole deliberately.

    Cancel a pending BUY-to-open      → reducing   → ALLOW
    Cancel a pending SELL-to-close    → INCREASING → REJECT   (removes a protective reduction)
    Cancel with unresolved partials   → INDETERMINATE → FAIL_CLOSED
    Unlocked account                  → not classified at all; unchanged behaviour
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from unittest.mock import MagicMock

import pytest
from sqlalchemy import select

from app.db.enums import (
    OrderSide,
    OrderSourceType,
    OrderStatus,
    OrderType,
    RiskScopeType,
    TimeInForce,
)
from app.db.models.account import Account, AccountMode
from app.db.models.account_state import AccountState
from app.db.models.order import Order
from app.db.models.risk_decision import RiskDecision as LedgerRow
from app.db.models.risk_limits import RiskLimits
from app.db.models.symbol import Symbol
from app.db.models.user import User
from app.events.bus import EventBus
from app.orders.router import CancelRejectedByRisk, OrderRouter

D = Decimal

# The real account-1 day_change at the moment the gate refused its own SNDK/LITE trims.
BREACHED = D("-6790.61")


def _now() -> datetime:
    return datetime.now(UTC)


@pytest.fixture
async def seeded(session_factory):
    async with session_factory() as s:
        s.add(User(id=1, email="t@local"))
        s.add(Account(id=1, user_id=1, broker="alpaca", mode=AccountMode.paper,
                      label="Paper", created_at=_now()))
        s.add(RiskLimits(id=1, user_id=1, broker_mode=AccountMode.paper,
                         scope_type=RiskScopeType.GLOBAL, max_daily_loss=D("5000"),
                         created_at=_now(), updated_at=_now()))
        s.add(Symbol(id=1, ticker="AAPL", exchange="NASDAQ", asset_class="us_equity",
                     name="Apple", active=True))
        await s.commit()
    return session_factory


async def _lock(session_factory, day_change: Decimal = BREACHED) -> None:
    async with session_factory() as s:
        s.add(AccountState(
            account_id=1, cash=D("0"), equity=D("100000") + day_change,
            last_equity=D("100000"), buying_power=D("0"),
            portfolio_value=D("100000"), daytrade_count=0,
            day_change=day_change, day_change_pct=D("0"),
            status="ACTIVE", updated_at=_now(), raw_payload={},
        ))
        await s.commit()


async def _open_order(session_factory, side: OrderSide) -> int:
    async with session_factory() as s:
        o = Order(
            user_id=1, account_id=1, symbol_id=1, broker_order_id="bo-1",
            side=side, qty=D("50"), type=OrderType.MARKET, tif=TimeInForce.DAY,
            status=OrderStatus.SUBMITTED, source_type=OrderSourceType.MANUAL,
            created_at=_now(), updated_at=_now(),
        )
        s.add(o)
        await s.commit()
        return o.id


def _router(session_factory, *, held="500", open_side="sell", filled="0"):
    """A router whose broker holds 500 AAPL and has one open order `bo-1`."""
    ad = MagicMock()
    ad.get_account.return_value = {"cash": "1000", "equity": "50000", "id": "a"}
    ad.get_positions.return_value = [
        {"symbol": "AAPL", "qty": held, "side": "long", "current_price": "100"}
    ]
    # ⚠ The broker cursor must be RELATIVE to the seeded local rows, never a fixed date.
    #
    # This previously read "2026-07-13T20:00:00Z". The local orders/positions are seeded with
    # `_now()`, so from 2026-07-14 onward the LOCAL rows became newer than the hard-coded broker
    # timestamp — `observed_cursor > broker_cursor` — and the causal-completeness guard correctly
    # reported SNAPSHOT_STALE, failing both tests. The engine was right; the fixture was a time
    # bomb, of exactly the same species as the canary's hard-coded deadline.
    broker_cursor = (datetime.now(UTC) + timedelta(minutes=1)).strftime("%Y-%m-%dT%H:%M:%SZ")
    ad.list_orders.return_value = [{
        "id": "bo-1", "symbol": "AAPL", "side": open_side, "qty": "50",
        "filled_qty": filled, "updated_at": broker_cursor,
    }]
    reg = MagicMock()
    reg.get.return_value = ad

    r = OrderRouter(ad, MagicMock(), session_factory, EventBus(), broker_registry=reg)
    return r, ad


async def _ledger(session_factory):
    async with session_factory() as s:
        return list((await s.execute(select(LedgerRow))).scalars().all())


# ---------------------------------------------------------------- THE HOLE § B CLOSES


async def test_cancelling_a_protective_sell_to_close_is_REFUSED_while_locked(seeded):
    """THE ONE THAT MATTERS. The account is in daily-loss breach and holds 500 AAPL. A
    sell-to-close for 50 is working — it is the only thing reducing the book.

    Cancelling it removes that reduction and traps the exposure. Refused. And the broker is
    never called: the order stays working.
    """
    await _lock(seeded)
    order_id = await _open_order(seeded, OrderSide.SELL)
    router, adapter = _router(seeded, open_side="sell")

    with pytest.raises(CancelRejectedByRisk) as exc:
        await router.cancel(order_id)

    assert "CANCEL_REMOVES_PROTECTIVE_REDUCTION" in exc.value.reasons
    adapter.cancel_order.assert_not_called()  # the protective order is still working

    rows = await _ledger(seeded)
    assert len(rows) == 1
    assert rows[0].action_type == "ORDER_CANCEL"
    assert rows[0].decision == "REJECT"
    assert rows[0].risk_effect == "RISK_INCREASING"
    assert rows[0].lock_state == "DAILY_LOSS"


async def test_cancelling_a_pending_buy_to_open_is_ALLOWED_while_locked(seeded):
    """Removing a risk-INCREASING order weakly reduces worst-case exposure. Permitted."""
    await _lock(seeded)
    order_id = await _open_order(seeded, OrderSide.BUY)
    router, adapter = _router(seeded, open_side="buy")

    await router.cancel(order_id)

    adapter.cancel_order.assert_called_once()
    rows = await _ledger(seeded)
    assert rows[0].decision == "ALLOW"
    assert rows[0].risk_effect == "RISK_REDUCING"


async def test_a_cancel_with_an_unresolved_partial_fill_fails_closed(seeded):
    """The broker reports a partial we have not ingested — the true position is ambiguous, so
    the effect of the cancel is unknowable. Unknowable is not permitted."""
    await _lock(seeded)
    order_id = await _open_order(seeded, OrderSide.BUY)
    router, adapter = _router(seeded, open_side="buy", filled="20")

    with pytest.raises(CancelRejectedByRisk):
        await router.cancel(order_id)

    adapter.cancel_order.assert_not_called()


async def test_no_broker_registry_fails_closed(seeded):
    """We cannot prove the cancel is reducing, so we do not permit it."""
    await _lock(seeded)
    order_id = await _open_order(seeded, OrderSide.SELL)
    router = OrderRouter(MagicMock(), MagicMock(), seeded, EventBus(), broker_registry=None)

    with pytest.raises(CancelRejectedByRisk):
        await router.cancel(order_id)


async def test_the_breaker_lock_gates_cancels_too(seeded):
    """Not just the daily-loss lock. Same rule, same classifier."""
    await _lock(seeded, day_change=D("0"))  # no daily-loss breach...
    async with seeded() as s:
        (await s.get(Account, 1)).circuit_breaker_tripped_at = _now()
        await s.commit()

    order_id = await _open_order(seeded, OrderSide.SELL)
    router, adapter = _router(seeded, open_side="sell")

    with pytest.raises(CancelRejectedByRisk):
        await router.cancel(order_id)

    adapter.cancel_order.assert_not_called()
    assert (await _ledger(seeded))[0].lock_state == "BREAKER"


# ---------------------------------------------------------------- UNLOCKED IS UNTOUCHED


async def test_an_unlocked_account_cancels_exactly_as_before(seeded):
    """The safety property. No lock → no classification, no broker read for a snapshot, no
    ledger row. Ordinary cancellation is completely unchanged."""
    await _lock(seeded, day_change=D("-100"))  # well inside the $5,000 cap
    order_id = await _open_order(seeded, OrderSide.SELL)
    router, adapter = _router(seeded, open_side="sell")

    await router.cancel(order_id)  # the protective sell CAN be cancelled when not locked

    adapter.cancel_order.assert_called_once()
    assert await _ledger(seeded) == []
