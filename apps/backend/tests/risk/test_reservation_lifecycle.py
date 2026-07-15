"""ADR 0042 — the reservation LIFECYCLE.

A reduction is approved, so it RESERVES the reducible capacity it was approved for (§ D). That
reservation must then be settled when the order it reserved for reaches a terminal state:

* FILLED    → CONSUMED   (the reduction is now real in the position)
* CANCELED / REJECTED / EXPIRED → RELEASED (the reduction never happened)

Before this fix the reservation was created HELD and only ever released on a version conflict —
there was NO release on fill/cancel/reject and no garbage collection. So every approved reduction
leaked a HELD reservation forever, and once the leaked reservations for a symbol reached the held
position, ``available_reducible_quantity`` hit 0 and the account could NEVER de-risk that symbol
again — the exact "risk gate traps its own de-risking" failure ADR 0042 exists to prevent
(reproduced live on account 3 by the 2026-07-15 canary).

These tests pin the two settle transitions, the leak-fix (freed capacity is reusable), and the
reaper safety net.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from unittest.mock import MagicMock

import pytest
from sqlalchemy import update

from app.db.enums import (
    OrderSide,
    OrderSourceType,
    OrderStatus,
    OrderType,
    TimeInForce,
)
from app.db.models.account import Account, AccountMode
from app.db.models.order import Order
from app.db.models.risk_reservation import (
    RESERVATION_CONSUMED,
    RESERVATION_HELD,
    RESERVATION_RELEASED,
    RiskReservation,
)
from app.db.models.symbol import Symbol
from app.db.models.user import User
from app.risk.decision_service import (
    LOCK_DAILY_LOSS,
    RiskDecisionService,
    run_reservation_reaper_pass,
)
from app.risk.risk_effect import ActionType as AT
from app.risk.risk_effect import Decision, ProposedAction

D = Decimal


def _adapter(qty="500", price="100.00"):
    ad = MagicMock()
    ad.get_account.return_value = {"cash": "10000", "equity": "60000", "id": "acct-x"}
    ad.get_positions.return_value = [
        {"symbol": "AAPL", "qty": qty, "side": "long", "current_price": price}
    ]
    ad.list_orders.return_value = []
    return ad


def _sell(qty: str) -> ProposedAction:
    return ProposedAction(AT.ORDER_SUBMIT, "AAPL", OrderSide.SELL, D(qty))


@pytest.fixture
async def acct(session_factory):
    async with session_factory() as s:
        s.add(User(id=1, email="jay@test"))
        s.add(Account(id=1, user_id=1, broker="alpaca", mode=AccountMode.paper, label="P"))
        s.add(Symbol(id=1, ticker="AAPL", exchange="NASDAQ", asset_class="us_equity",
                     name="Apple", active=True))
        await s.commit()
    return 1


async def _one(session_factory, res_id: int) -> RiskReservation:
    async with session_factory() as s:
        return await s.get(RiskReservation, res_id)


async def _allow_reduction(session_factory, acct, qty: str) -> int:
    """Approve a reduction of `qty` and return its (HELD) reservation id."""
    ad = _adapter(qty="500")
    async with session_factory() as s:
        result, _ledger, res_id = await RiskDecisionService(s).decide(
            account_id=acct, adapter=ad, action=_sell(qty),
            lock_state=LOCK_DAILY_LOSS, daily_pnl=D("-6790.61"),
        )
    assert result.decision is Decision.ALLOW
    assert res_id is not None
    return res_id


async def _link_order(session_factory, res_id: int, order_id: int) -> None:
    """Simulate the router back-linking the reservation to its order."""
    async with session_factory() as s:
        await s.execute(
            update(RiskReservation).where(RiskReservation.id == res_id).values(order_id=order_id)
        )
        await s.commit()


def _order(order_id: int, status: OrderStatus, **kw) -> Order:
    now = datetime.now(UTC)
    return Order(
        id=order_id, user_id=1, account_id=1, symbol_id=1,
        client_order_id=f"twb-{order_id}", side=OrderSide.SELL, qty=D("1"),
        type=OrderType.MARKET, tif=TimeInForce.DAY, status=status,
        source_type=OrderSourceType.MANUAL, created_at=now, updated_at=now, **kw,
    )


# --------------------------------------------------------------- settle transitions


async def test_fill_consumes_the_reservation(session_factory, acct):
    res_id = await _allow_reduction(session_factory, acct, "400")
    await _link_order(session_factory, res_id, order_id=77)
    async with session_factory() as s:
        settled = await RiskDecisionService(s).settle_reservation_for_order(
            77, filled=True, reason="ORDER_FILLED"
        )
    assert settled is True
    res = await _one(session_factory, res_id)
    assert res.state == RESERVATION_CONSUMED
    assert res.released_at is not None
    assert res.release_reason == "ORDER_FILLED"


async def test_cancel_releases_the_reservation(session_factory, acct):
    res_id = await _allow_reduction(session_factory, acct, "400")
    await _link_order(session_factory, res_id, order_id=88)
    async with session_factory() as s:
        settled = await RiskDecisionService(s).settle_reservation_for_order(
            88, filled=False, reason="ORDER_CANCELED_LOCAL"
        )
    assert settled is True
    res = await _one(session_factory, res_id)
    assert res.state == RESERVATION_RELEASED


async def test_settle_is_noop_without_a_held_reservation(session_factory, acct):
    async with session_factory() as s:
        settled = await RiskDecisionService(s).settle_reservation_for_order(
            999, filled=True, reason="ORDER_FILLED"
        )
    assert settled is False


async def test_settling_frees_capacity_for_the_next_reduction(session_factory, acct):
    """THE LEAK FIX. A 400 reduction reserves 400 of a 500 long, so a further 200 reduction is
    refused (only 100 reducible). Once the first order settles, the capacity is reusable and the
    200 reduction is approved. Before the fix the reservation never left HELD, so the 200 stayed
    refused forever — the account could not de-risk."""
    res_id = await _allow_reduction(session_factory, acct, "400")

    ad = _adapter(qty="500")
    async with session_factory() as s:
        blocked, _, _ = await RiskDecisionService(s).decide(
            account_id=acct, adapter=ad, action=_sell("200"),
            lock_state=LOCK_DAILY_LOSS, daily_pnl=D("-6790.61"),
        )
    assert blocked.decision is Decision.FAIL_CLOSED  # only 100 reducible under the HELD 400

    await _link_order(session_factory, res_id, order_id=101)
    async with session_factory() as s:
        await RiskDecisionService(s).settle_reservation_for_order(
            101, filled=True, reason="ORDER_FILLED"
        )

    async with session_factory() as s:
        now_ok, _, _ = await RiskDecisionService(s).decide(
            account_id=acct, adapter=ad, action=_sell("200"),
            lock_state=LOCK_DAILY_LOSS, daily_pnl=D("-6790.61"),
        )
    assert now_ok.decision is Decision.ALLOW  # capacity was freed — de-risking works again


# --------------------------------------------------------------- reaper safety net


async def test_reaper_releases_orphan_with_no_order_past_grace(session_factory, acct):
    old = datetime.now(UTC) - timedelta(seconds=600)
    recent = datetime.now(UTC)
    async with session_factory() as s:
        s.add(RiskReservation(id=1, account_id=1, symbol="AAPL", qty=D("100"),
                              state=RESERVATION_HELD, created_at=old))
        s.add(RiskReservation(id=2, account_id=1, symbol="AAPL", qty=D("50"),
                              state=RESERVATION_HELD, created_at=recent))
        await s.commit()

    reaped = await run_reservation_reaper_pass(session_factory, older_than_seconds=300)
    assert reaped == 1
    assert (await _one(session_factory, 1)).state == RESERVATION_RELEASED
    assert (await _one(session_factory, 1)).release_reason == "REAP_NO_ORDER"
    assert (await _one(session_factory, 2)).state == RESERVATION_HELD  # within grace — kept


async def test_reaper_releases_when_order_is_terminal_but_keeps_live_ones(session_factory, acct):
    async with session_factory() as s:
        s.add(_order(10, OrderStatus.FILLED, terminal_at=datetime.now(UTC)))
        s.add(_order(11, OrderStatus.SUBMITTED))
        s.add(RiskReservation(id=1, account_id=1, symbol="AAPL", qty=D("100"),
                              state=RESERVATION_HELD, created_at=datetime.now(UTC), order_id=10))
        s.add(RiskReservation(id=2, account_id=1, symbol="AAPL", qty=D("100"),
                              state=RESERVATION_HELD, created_at=datetime.now(UTC), order_id=11))
        s.add(RiskReservation(id=3, account_id=1, symbol="AAPL", qty=D("100"),
                              state=RESERVATION_HELD, created_at=datetime.now(UTC), order_id=999))
        await s.commit()

    reaped = await run_reservation_reaper_pass(session_factory, older_than_seconds=300)
    assert reaped == 2  # terminal order + missing order
    assert (await _one(session_factory, 1)).release_reason == "REAP_ORDER_TERMINAL"
    assert (await _one(session_factory, 2)).state == RESERVATION_HELD  # live order — kept
    assert (await _one(session_factory, 3)).release_reason == "REAP_ORDER_MISSING"
