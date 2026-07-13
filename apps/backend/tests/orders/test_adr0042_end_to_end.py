"""ADR 0042 — end-to-end through the REAL OrderRouter, on a locked account.

Everything up to now proved that ``RiskEngine.evaluate()`` returns PASS for a verified
reduction. That is not the claim that matters. The claim that matters is:

    **the reduction actually reaches the broker.**

On 2026-07-13 the momentum book's SNDK and LITE trims were *evaluated* and then *refused*, and
no order was ever sent. So these tests assert on ``adapter.submit_order`` — the real boundary —
not on a decision object.

They run the full path: OrderRouter.submit → RiskEngine.evaluate → steps 9/13 → classifier →
snapshot → reservation → ledger → broker. Nothing is stubbed except the broker itself.
"""

from __future__ import annotations

import itertools
from datetime import UTC, datetime
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
from app.db.models.position import Position
from app.db.models.risk_decision import RiskDecision as LedgerRow
from app.db.models.risk_limits import RiskLimits
from app.db.models.risk_reservation import RESERVATION_HELD, RiskReservation
from app.db.models.symbol import Symbol
from app.db.models.user import User
from app.events.bus import EventBus
from app.orders.router import OrderRouter
from app.risk import OrderRequest, RiskEngine

D = Decimal

# The real account-1 numbers from the incident.
BREACHED_DAY_PNL = D("-6790.61")
DAILY_LOSS_CAP = D("5000")


def _now() -> datetime:
    return datetime.now(UTC)


@pytest.fixture
async def seeded(session_factory):
    """A paper account in DAILY-LOSS BREACH, holding 500 AAPL @ $100."""
    async with session_factory() as s:
        s.add(User(id=1, email="t@local"))
        s.add(Account(id=1, user_id=1, broker="alpaca", mode=AccountMode.paper,
                      label="Alpaca Paper", created_at=_now()))
        s.add(RiskLimits(
            id=1, user_id=1, broker_mode=AccountMode.paper,
            scope_type=RiskScopeType.GLOBAL,
            max_daily_loss=DAILY_LOSS_CAP, max_gross_exposure=D("1000000"),
            max_orders_per_minute=100, allow_short=False,
            created_at=_now(), updated_at=_now(),
        ))
        s.add(Symbol(id=1, ticker="AAPL", exchange="NASDAQ", asset_class="us_equity",
                     name="Apple", active=True))
        s.add(Position(user_id=1, account_id=1, symbol_id=1, qty=D("500"),
                       avg_entry_price=D("100"), side="long", updated_at=_now()))
        s.add(AccountState(
            account_id=1, cash=D("1000"), equity=D("100000") + BREACHED_DAY_PNL,
            last_equity=D("100000"), buying_power=D("1000"),
            portfolio_value=D("100000"), daytrade_count=0,
            day_change=BREACHED_DAY_PNL, day_change_pct=D("0"),
            status="ACTIVE", updated_at=_now(), raw_payload={},
        ))
        await s.commit()
    return session_factory


def _broker():
    a = MagicMock()
    a.is_paper = True
    counter = itertools.count(1)
    # A distinct broker id per call: orders.broker_order_id is UNIQUE, and a stub that
    # returns the same id twice fails the second insert for reasons that have nothing to do
    # with risk.
    a.submit_order.side_effect = lambda **kw: {
        "id": f"broker-{next(counter)}", "status": "accepted"
    }
    a.get_account.return_value = {"cash": "1000", "equity": "93209", "id": "acct"}
    a.get_positions.return_value = [
        {"symbol": "AAPL", "qty": "500", "side": "long", "current_price": "100"}
    ]
    a.list_orders.return_value = []
    return a


def _router(session_factory, adapter):
    reg = MagicMock()
    reg.get.return_value = adapter
    engine = RiskEngine(session_factory, broker_registry=reg)
    return OrderRouter(adapter, engine, session_factory, EventBus(), broker_registry=reg)


def _req(side: OrderSide, qty: str, source=OrderSourceType.STRATEGY) -> OrderRequest:
    return OrderRequest(
        user_id=1, account_id=1, symbol_ticker="AAPL", side=side, qty=D(qty),
        type=OrderType.MARKET, tif=TimeInForce.DAY, source_type=source,
    )


# ============================================================ THE CLAIM THAT MATTERS


@pytest.mark.usefixtures("_market_open")
async def test_a_verified_reduction_REACHES_THE_BROKER_on_a_locked_account(seeded):
    """2026-07-13, corrected, end to end.

    The account is in daily-loss breach. The strategy proposes a trim. The order must not merely
    'evaluate to PASS' — it must be SENT, persisted, and acknowledged.
    """
    adapter = _broker()
    router = _router(seeded, adapter)

    order = await router.submit(_req(OrderSide.SELL, "100"))

    # The boundary that actually matters.
    adapter.submit_order.assert_called_once()
    sent = adapter.submit_order.call_args.kwargs
    assert sent["symbol"] == "AAPL"
    assert str(sent["side"]).lower().endswith("sell")
    assert Decimal(str(sent["qty"])) == D("100")

    assert order.status == OrderStatus.SUBMITTED
    assert order.broker_order_id == "broker-1"

    async with seeded() as s:
        rows = list((await s.execute(select(LedgerRow))).scalars().all())
        held = list(
            (
                await s.execute(
                    select(RiskReservation).where(RiskReservation.state == RESERVATION_HELD)
                )
            ).scalars().all()
        )
    assert [r.decision for r in rows] == ["ALLOW"]
    assert rows[0].risk_effect == "RISK_REDUCING"
    assert rows[0].lock_state == "DAILY_LOSS"
    assert rows[0].daily_pnl == D("-6790.6100")
    assert len(held) == 1 and held[0].qty == D("100")


@pytest.mark.usefixtures("_market_open")
async def test_a_buy_NEVER_reaches_the_broker_on_a_locked_account(seeded):
    """Nothing loosens. The BE-shaped entry from the same 10:00 run stays blocked."""
    adapter = _broker()
    router = _router(seeded, adapter)

    order = await router.submit(_req(OrderSide.BUY, "10"))

    adapter.submit_order.assert_not_called()
    assert order.status == OrderStatus.REJECTED

    async with seeded() as s:
        rows = list((await s.execute(select(LedgerRow))).scalars().all())
    assert rows[0].decision == "REJECT"
    assert rows[0].risk_effect == "RISK_INCREASING"


@pytest.mark.usefixtures("_market_open")
async def test_an_oversell_never_reaches_the_broker(seeded):
    """600 against a long of 500 would cross zero into a short."""
    adapter = _broker()
    router = _router(seeded, adapter)

    order = await router.submit(_req(OrderSide.SELL, "600"))

    adapter.submit_order.assert_not_called()
    assert order.status == OrderStatus.REJECTED


@pytest.mark.usefixtures("_market_open")
async def test_a_manual_reduction_reaches_the_broker_too(seeded):
    """§ C — source-neutral, end to end. Trapped risk is equally dangerous regardless of who
    initiated the reduction."""
    adapter = _broker()
    router = _router(seeded, adapter)

    order = await router.submit(_req(OrderSide.SELL, "100", OrderSourceType.MANUAL))

    adapter.submit_order.assert_called_once()
    assert order.status == OrderStatus.SUBMITTED

    async with seeded() as s:
        rows = list((await s.execute(select(LedgerRow))).scalars().all())
    assert rows[0].source_type == "MANUAL"
    assert rows[0].risk_effect == "RISK_REDUCING"


# ============================================================ CAPACITY, END TO END


@pytest.mark.usefixtures("_market_open")
async def test_reductions_cannot_be_stacked_past_the_position(seeded):
    """§ D through the real router. Three 200-share trims against a long of 500: the first two
    fit (400), the third would take it to 600 — past the position, into a short.

    The broker never sees the third. Note this holds even though each order, evaluated against
    the broker's own UNCHANGED position of 500, looks individually legal — the reservations are
    what remember the first two.
    """
    adapter = _broker()
    router = _router(seeded, adapter)

    a = await router.submit(_req(OrderSide.SELL, "200"))
    b = await router.submit(_req(OrderSide.SELL, "200"))
    c = await router.submit(_req(OrderSide.SELL, "200"))

    assert a.status == OrderStatus.SUBMITTED
    assert b.status == OrderStatus.SUBMITTED
    assert c.status == OrderStatus.REJECTED

    assert adapter.submit_order.call_count == 2

    async with seeded() as s:
        held = list(
            (
                await s.execute(
                    select(RiskReservation).where(RiskReservation.state == RESERVATION_HELD)
                )
            ).scalars().all()
        )
    assert sum(r.qty for r in held) == D("400")  # never exceeds the 500 long


# ============================================================ THE UNLOCKED PATH


@pytest.mark.usefixtures("_market_open")
async def test_an_unlocked_account_submits_a_buy_with_no_ledger_row(seeded):
    """The safety property, end to end: with no lock, ADR 0042 is not in the path at all."""
    async with seeded() as s:
        st = (
            await s.execute(select(AccountState).where(AccountState.account_id == 1))
        ).scalars().first()
        # BOTH must move. CircuitBreakerService.check() does NOT trust the day_change column —
        # it RECOMPUTES the daily P&L from (equity - last_equity). Setting day_change alone
        # leaves the two disagreeing, and the breaker re-derives the breach from equity and
        # trips anyway. (Correct of the breaker; a trap for the unwary.)
        st.day_change = D("-100")
        st.equity = st.last_equity - D("100")
        await s.commit()

    adapter = _broker()
    router = _router(seeded, adapter)

    order = await router.submit(_req(OrderSide.BUY, "10"))

    assert order.status == OrderStatus.SUBMITTED
    adapter.submit_order.assert_called_once()

    async with seeded() as s:
        assert list((await s.execute(select(LedgerRow))).scalars().all()) == []


@pytest.mark.usefixtures("_market_open")
async def test_the_order_row_and_the_ledger_row_agree(seeded):
    """The durable lifecycle must actually join up: signal → proposal → RISK DECISION → order.
    A ledger the orders table cannot be reconciled against is decoration."""
    adapter = _broker()
    router = _router(seeded, adapter)

    order = await router.submit(_req(OrderSide.SELL, "100"))

    async with seeded() as s:
        row = (await s.execute(select(LedgerRow))).scalars().first()
        persisted = await s.get(Order, order.id)

    assert row.symbol == "AAPL"
    assert row.qty == persisted.qty
    assert str(row.side).lower().endswith("sell")
    assert row.account_id == persisted.account_id
    assert row.before_state_hash and row.risk_policy_version and row.correlation_id
