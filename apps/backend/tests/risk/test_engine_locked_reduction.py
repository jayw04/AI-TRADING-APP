"""ADR 0042 — steps 9 and 13, wired.

This is the test that would have changed 2026-07-13. The momentum book, in daily-loss breach,
proposed trimming SNDK and LITE. Both were rejected — not because they added risk, but because
the gate rejected *everything*. The book stayed 98% invested through a −7% day while the loss
grew by another ~$2,000.

    A risk control may stop trading, but it must not prevent verified reduction of the risk it
    is intended to control.

What must hold, once locked:

    REDUCING       ALLOW  (through BOTH step 9 and step 13)
    INCREASING     REJECT
    INDETERMINATE  FAIL_CLOSED

and — the property that keeps this change safe — **the unlocked path is untouched**. It never
reaches the classifier, never fetches a snapshot, never writes a ledger row.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from unittest.mock import MagicMock

import pytest
from sqlalchemy import select

from app.db.enums import (
    OrderSide,
    OrderSourceType,
    OrderType,
    RiskDecision,
    RiskScopeType,
    TimeInForce,
)
from app.db.models.account import Account, AccountMode
from app.db.models.account_state import AccountState
from app.db.models.position import Position
from app.db.models.risk_decision import RiskDecision as LedgerRow
from app.db.models.risk_limits import RiskLimits
from app.db.models.symbol import Symbol
from app.db.models.user import User
from app.risk.engine import RiskEngine
from app.risk.types import OrderRequest
from app.services.day_change_basis import BROKER_LAST_EQUITY

D = Decimal


def _now() -> datetime:
    return datetime.now(UTC)


@pytest.fixture
async def seeded(session_factory):
    """A paper account, $5,000 daily-loss cap, holding 500 AAPL @ $100."""
    async with session_factory() as s:
        s.add(User(id=1, email="t@local"))
        s.add(Account(id=1, user_id=1, broker="alpaca", mode=AccountMode.paper,
                      label="Paper", created_at=_now()))
        s.add(RiskLimits(id=1, user_id=1, broker_mode=AccountMode.paper,
                         scope_type=RiskScopeType.GLOBAL, max_daily_loss=D("5000"),
                         created_at=_now(), updated_at=_now()))
        s.add(Symbol(id=1, ticker="AAPL", exchange="NASDAQ", asset_class="us_equity",
                     name="Apple", active=True))
        # The engine's OWN long-only guard reads the LOCAL positions table and rejects
        # SHORT_NOT_ALLOWED before step 9 is ever reached. That is a second, independent
        # barrier against opening a short — the ADR 0042 classifier does not replace it, and
        # this row is what makes the reduction reachable at all.
        s.add(Position(user_id=1, account_id=1, symbol_id=1, qty=D("500"),
                       avg_entry_price=D("100"), side="long", updated_at=_now()))
        await s.commit()
    return session_factory


async def _set_day_change(session_factory, day_change: Decimal) -> None:
    async with session_factory() as s:
        s.add(AccountState(
            day_change_basis=BROKER_LAST_EQUITY,
            account_id=1, cash=D("0"), equity=D("100000") + day_change,
            last_equity=D("100000"), buying_power=D("0"),
            portfolio_value=D("100000"), daytrade_count=0,
            day_change=day_change, day_change_pct=D("0"),
            status="ACTIVE", updated_at=_now(), raw_payload={},
        ))
        await s.commit()


def _registry(qty="500", price="100.00"):
    ad = MagicMock()
    ad.get_account.return_value = {"cash": "1000", "equity": "50000", "id": "a"}
    ad.get_positions.return_value = [
        {"symbol": "AAPL", "qty": qty, "side": "long", "current_price": price}
    ]
    ad.list_orders.return_value = []
    reg = MagicMock()
    reg.get.return_value = ad
    return reg


def _req(side: OrderSide, qty: str, source=OrderSourceType.STRATEGY) -> OrderRequest:
    return OrderRequest(
        user_id=1, account_id=1, symbol_ticker="AAPL", side=side, qty=D(qty),
        type=OrderType.MARKET, tif=TimeInForce.DAY, source_type=source,
    )


async def _ledger(session_factory) -> list[LedgerRow]:
    async with session_factory() as s:
        return list(
            (await s.execute(select(LedgerRow).order_by(LedgerRow.id))).scalars().all()
        )


async def _evaluate(session_factory, req, registry=None):
    engine = RiskEngine(session_factory, broker_registry=registry)
    return await engine.evaluate(req, trading_mode="paper")


# ================================================================ THE FIX


@pytest.mark.usefixtures("_market_open")
async def test_a_verified_reduction_PASSES_the_daily_loss_gate(seeded):
    """2026-07-13, corrected. In breach, the SNDK/LITE-shaped trim now passes."""
    await _set_day_change(seeded, D("-6790.61"))  # the real number from account 1

    out = await _evaluate(seeded, _req(OrderSide.SELL, "100"), _registry())

    assert out.decision == RiskDecision.PASS


@pytest.mark.usefixtures("_market_open")
async def test_a_buy_is_STILL_rejected_while_locked(seeded):
    """Nothing loosens. Reductions pass; additions do not."""
    await _set_day_change(seeded, D("-6790.61"))

    out = await _evaluate(seeded, _req(OrderSide.BUY, "10"), _registry())

    assert out.decision == RiskDecision.REJECT


@pytest.mark.usefixtures("_market_open")
async def test_an_oversell_that_would_cross_zero_is_rejected(seeded):
    """A SELL is not a reduction just because it is a SELL. 600 from a long of 500 opens a
    short."""
    await _set_day_change(seeded, D("-6790.61"))

    out = await _evaluate(seeded, _req(OrderSide.SELL, "600"), _registry())

    assert out.decision == RiskDecision.REJECT


@pytest.mark.usefixtures("_market_open")
async def test_a_verified_reduction_passes_the_BREAKER_gate_too(seeded):
    """Step 13, not just step 9. Both gates call the same classifier — and the breaker stays
    tripped throughout. We are not resetting the lock; we are letting a reduction out of it."""
    await _set_day_change(seeded, D("0"))  # no daily-loss breach...
    async with seeded() as s:
        acct = await s.get(Account, 1)
        acct.circuit_breaker_tripped_at = _now()  # ...but the breaker IS tripped
        await s.commit()

    out = await _evaluate(seeded, _req(OrderSide.SELL, "100"), _registry())
    assert out.decision == RiskDecision.PASS

    buy = await _evaluate(seeded, _req(OrderSide.BUY, "10"), _registry())
    assert buy.decision == RiskDecision.REJECT

    async with seeded() as s:
        assert (await s.get(Account, 1)).circuit_breaker_tripped_at is not None


# ================================================================ FAIL-CLOSED


@pytest.mark.usefixtures("_market_open")
async def test_no_broker_registry_fails_closed(seeded):
    """Without a registry we cannot obtain a causally-complete snapshot, so we cannot PROVE the
    reduction. Unproven is not permitted. (This is also why every pre-existing test — none of
    which passes a registry — keeps its old reject behaviour.)"""
    await _set_day_change(seeded, D("-6790.61"))

    out = await _evaluate(seeded, _req(OrderSide.SELL, "100"), registry=None)

    assert out.decision == RiskDecision.REJECT


@pytest.mark.usefixtures("_market_open")
async def test_an_unreadable_broker_fails_closed(seeded):
    """A broker we cannot read is not permission to trade."""
    await _set_day_change(seeded, D("-6790.61"))
    reg = _registry()
    reg.get.return_value.get_positions.side_effect = RuntimeError("broker down")

    out = await _evaluate(seeded, _req(OrderSide.SELL, "100"), reg)

    assert out.decision == RiskDecision.REJECT


# ================================================================ LEDGER (§ 7)


@pytest.mark.usefixtures("_market_open")
async def test_both_the_allowed_reduction_and_the_refused_buy_are_on_the_ledger(seeded):
    """THE 2026-07-13 HOLE. Eighteen proposals refused; zero durable rows anywhere."""
    await _set_day_change(seeded, D("-6790.61"))
    reg = _registry()

    await _evaluate(seeded, _req(OrderSide.SELL, "100"), reg)
    await _evaluate(seeded, _req(OrderSide.BUY, "10"), reg)

    rows = await _ledger(seeded)
    assert len(rows) == 2

    allow, reject = rows
    assert (allow.decision, allow.risk_effect) == ("ALLOW", "RISK_REDUCING")
    assert (reject.decision, reject.risk_effect) == ("REJECT", "RISK_INCREASING")
    for r in rows:
        assert r.lock_state == "DAILY_LOSS"
        assert r.daily_pnl == D("-6790.6100")
        assert r.before_state_hash and r.risk_policy_version
        assert r.correlation_id


@pytest.mark.usefixtures("_market_open")
async def test_source_neutrality_manual_and_strategy_are_treated_identically(seeded):
    """§ C. Trapped risk is equally dangerous regardless of who initiated the reduction — and a
    human cannot self-assert a risk effect."""
    await _set_day_change(seeded, D("-6790.61"))
    reg = _registry()

    strat = await _evaluate(seeded, _req(OrderSide.SELL, "10", OrderSourceType.STRATEGY), reg)
    manual = await _evaluate(seeded, _req(OrderSide.SELL, "10", OrderSourceType.MANUAL), reg)

    assert strat.decision == manual.decision == RiskDecision.PASS

    rows = await _ledger(seeded)
    assert {r.source_type for r in rows} == {"STRATEGY", "MANUAL"}
    assert {r.risk_effect for r in rows} == {"RISK_REDUCING"}


# ================================================================ THE UNLOCKED PATH IS UNTOUCHED


@pytest.mark.usefixtures("_market_open")
async def test_an_unlocked_account_never_reaches_the_classifier(seeded):
    """The safety property of this whole change: normal trading pays NOTHING for it.

    No lock → no snapshot fetch, no broker read, no ledger row. If this ever fails, ADR 0042
    has leaked into the hot path.
    """
    await _set_day_change(seeded, D("-100"))  # well inside the $5,000 cap
    reg = _registry()

    out = await _evaluate(seeded, _req(OrderSide.BUY, "10"), reg)

    assert out.decision == RiskDecision.PASS
    reg.get.assert_not_called()          # the broker was never read
    assert await _ledger(seeded) == []   # no decision row written


# ================================================================ ONE CLASSIFICATION PER ORDER


@pytest.mark.usefixtures("_market_open")
async def test_one_order_produces_exactly_one_decision_and_one_reservation(seeded):
    """REGRESSION. Step 9 TRIPS the breaker, so step 13 then finds it tripped and would ask the
    classifier again — for the very same order.

    That is not merely a duplicate log line. It takes a SECOND RESERVATION: one 100-share sell
    would consume 200 of reducible capacity and wrongly block the next legitimate reduction.
    Found by the ledger count, which is exactly the sort of thing a ledger is for.
    """
    from app.db.models.risk_reservation import RESERVATION_HELD, RiskReservation

    await _set_day_change(seeded, D("-6790.61"))

    out = await _evaluate(seeded, _req(OrderSide.SELL, "100"), _registry())
    assert out.decision == RiskDecision.PASS

    assert len(await _ledger(seeded)) == 1, "the order was classified twice"

    async with seeded() as s:
        held = list(
            (
                await s.execute(
                    select(RiskReservation).where(RiskReservation.state == RESERVATION_HELD)
                )
            ).scalars().all()
        )
    assert len(held) == 1
    assert held[0].qty == D("100"), "capacity was double-consumed for a single order"
