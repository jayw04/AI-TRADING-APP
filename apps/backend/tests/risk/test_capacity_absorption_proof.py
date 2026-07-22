"""ADR 0042 § D amendment — a reserved fill is credited back ONLY where the position proves it.

A held reservation keeps its FULL original quantity until its order goes terminal, so a partial
fill is otherwise charged twice: once by the broker position the fill shrank, once by the
still-full reservation. The amendment credits the filled part back — but broker positions,
broker orders and local fills are THREE NON-ATOMIC READS, so a locally recorded fill may not yet
appear in the positions endpoint.

Crediting such a fill on the strength of the local row alone would ADD REDUCIBLE CAPACITY THAT
DOES NOT EXIST and could admit a sell that crosses zero into a short — the ADR 0042 harm reached
from the opposite direction. These tests pin that the credit is bounded by an OBSERVED position
movement against the anchor recorded when the reservation was created, and that anything
unprovable is credited zero.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest
from sqlalchemy import update

from app.db.enums import OrderSide, OrderSourceType, OrderStatus, OrderType, TimeInForce
from app.db.models.account import Account, AccountMode
from app.db.models.fill import Fill
from app.db.models.order import Order
from app.db.models.risk_reservation import RESERVATION_HELD, RiskReservation
from app.db.models.symbol import Symbol
from app.db.models.user import User
from app.risk.decision_service import RiskDecisionService
from app.risk.risk_effect import AccountSnapshot, SnapshotPosition

D = Decimal


@pytest.fixture
async def acct(session_factory):
    async with session_factory() as s:
        s.add(User(id=1, email="jay@test"))
        s.add(Account(id=1, user_id=1, broker="alpaca", mode=AccountMode.paper, label="P"))
        s.add(Symbol(id=1, ticker="AAPL", exchange="NASDAQ", asset_class="us_equity",
                     name="Apple", active=True))
        await s.commit()
    return 1


def _snap(long_qty: str) -> AccountSnapshot:
    """A snapshot whose POSITION is the only thing under test here."""
    return AccountSnapshot(
        account_id=1,
        positions={"AAPL": SnapshotPosition("AAPL", D(long_qty), D("100"))},
        open_orders=[],
        cash=D("1000"),
        equity=D("100000"),
        broker_cursor="100",
        observed_cursor="100",
    )


async def _reservation(session_factory, *, res_id, qty, anchor, order_id=None, filled=None,
                       symbol="AAPL", state=RESERVATION_HELD):
    now = datetime.now(UTC)
    async with session_factory() as s:
        if order_id is not None:
            s.add(Order(id=order_id, user_id=1, account_id=1, symbol_id=1,
                        client_order_id=f"twb-{order_id}", side=OrderSide.SELL, qty=D(qty),
                        type=OrderType.MARKET, tif=TimeInForce.DAY,
                        status=OrderStatus.SUBMITTED, source_type=OrderSourceType.MANUAL,
                        created_at=now, updated_at=now))
        s.add(RiskReservation(
            id=res_id, account_id=1, symbol=symbol, qty=D(qty), state=state,
            created_at=now, order_id=order_id,
            position_qty_at_reservation=(D(anchor) if anchor is not None else None),
        ))
        if filled is not None and order_id is not None:
            s.add(Fill(id=res_id, order_id=order_id, qty=D(filled), price=D("100"),
                       filled_at=now))
        await s.commit()


async def _absorbed(session_factory, snap, *, exclude=None) -> dict:
    async with session_factory() as s:
        return await RiskDecisionService(s)._absorbed_reserved_fill_by_symbol(
            snap, 1, exclude=exclude
        )


# ---- 1. local fill AHEAD of the broker position: credit NOTHING -----------------

async def test_local_fill_ahead_of_broker_position_manufactures_no_capacity(
    session_factory, acct
):
    """200 long, 200 reserved, 75 filled LOCALLY, but the positions endpoint still says 200.

    Nothing has been proven absorbed, so nothing may be credited. Crediting the 75 here would
    admit a further 75-share reduction against a book whose true remaining capacity is zero."""
    await _reservation(session_factory, res_id=1, qty="200", anchor="200",
                       order_id=10, filled="75")
    assert await _absorbed(session_factory, _snap("200")) == {}


# ---- 2. the position HAS absorbed the fill: credit exactly once -----------------

async def test_absorbed_fill_is_credited_exactly_once(session_factory, acct):
    """Position moved 200 -> 125, which is the 75 the fill reports. Credit exactly 75."""
    await _reservation(session_factory, res_id=1, qty="200", anchor="200",
                       order_id=10, filled="75")
    assert await _absorbed(session_factory, _snap("125")) == {"AAPL": D("75")}


# ---- 3. broker position AHEAD of local fill ingestion: conservative ------------

async def test_position_ahead_of_local_fills_is_conservative_not_permissive(
    session_factory, acct
):
    """The position already shows the reduction but no Fill row has landed locally yet.

    The credit is bounded by the OBSERVED FILLS too, so it is zero — a conservative refusal.
    What must never happen is the opposite: capacity appearing from an unobserved fill."""
    await _reservation(session_factory, res_id=1, qty="200", anchor="200", order_id=10)
    assert await _absorbed(session_factory, _snap("125")) == {}


# ---- 4. multiple reservations cannot each claim the same movement --------------

async def test_one_observed_reduction_cannot_be_credited_to_two_reservations(
    session_factory, acct
):
    """Two held reservations, each reporting a 75-share fill, but the position moved only 75.

    Symbol-level aggregation caps the total credit at the single observed movement."""
    await _reservation(session_factory, res_id=1, qty="200", anchor="500",
                       order_id=10, filled="75")
    await _reservation(session_factory, res_id=2, qty="200", anchor="500",
                       order_id=11, filled="75")
    absorbed = await _absorbed(session_factory, _snap("425"))
    assert absorbed == {"AAPL": D("75")}, "the same 75 was credited twice"


async def test_the_smallest_anchor_bounds_the_claim(session_factory, acct):
    """Reservations anchored at different positions: the SMALLEST anchor is used, so the
    movement claimed is the least generous one defensible."""
    await _reservation(session_factory, res_id=1, qty="100", anchor="500",
                       order_id=10, filled="75")
    await _reservation(session_factory, res_id=2, qty="100", anchor="425",
                       order_id=11, filled="75")
    # min anchor 425 vs current 400 -> only 25 of movement is provable
    assert await _absorbed(session_factory, _snap("400")) == {"AAPL": D("25")}


# ---- 5. a position INCREASE is never proof of an absorbed sell -----------------

async def test_a_position_increase_is_not_evidence_of_an_absorbed_fill(session_factory, acct):
    """A buy or transfer raised the long above the anchor. The movement is negative, clamped to
    zero: an increase can never demonstrate that a reserved SELL filled."""
    await _reservation(session_factory, res_id=1, qty="200", anchor="200",
                       order_id=10, filled="75")
    assert await _absorbed(session_factory, _snap("300")) == {}


# ---- provenance / safety rails --------------------------------------------------

async def test_a_reservation_without_an_anchor_is_credited_zero(session_factory, acct):
    """Rows written before the anchor column existed cannot prove absorption. Unprovable is not
    absorbed — and no anchor is invented after the fact."""
    await _reservation(session_factory, res_id=1, qty="200", anchor=None,
                       order_id=10, filled="75")
    assert await _absorbed(session_factory, _snap("125")) == {}


async def test_an_overfill_cannot_manufacture_capacity(session_factory, acct):
    """A fill larger than the reservation is capped at the reservation's own quantity."""
    await _reservation(session_factory, res_id=1, qty="100", anchor="500",
                       order_id=10, filled="400")
    assert await _absorbed(session_factory, _snap("100")) == {"AAPL": D("100")}


async def test_only_held_reservations_are_considered(session_factory, acct):
    await _reservation(session_factory, res_id=1, qty="200", anchor="200", order_id=10,
                       filled="75", state="CONSUMED")
    assert await _absorbed(session_factory, _snap("125")) == {}


async def test_exclude_drops_the_named_reservation(session_factory, acct):
    await _reservation(session_factory, res_id=1, qty="200", anchor="200",
                       order_id=10, filled="75")
    assert await _absorbed(session_factory, _snap("125"), exclude=1) == {}


async def test_the_anchor_is_recorded_when_a_reservation_is_created(session_factory, acct):
    """The anchor must be captured prospectively, or nothing downstream can be proven."""
    from unittest.mock import MagicMock

    from app.risk.risk_effect import ActionType as AT
    from app.risk.risk_effect import Decision, ProposedAction

    ad = MagicMock()
    ad.get_account.return_value = {"cash": "10000", "equity": "60000", "id": "acct-x"}
    ad.get_positions.return_value = [
        {"symbol": "AAPL", "qty": "500", "side": "long", "current_price": "100.00"}
    ]
    ad.list_orders.return_value = []
    async with session_factory() as s:
        result, _ledger, res_id = await RiskDecisionService(s).decide(
            account_id=1, adapter=ad,
            action=ProposedAction(AT.ORDER_SUBMIT, "AAPL", OrderSide.SELL, D("200")),
            lock_state="DAILY_LOSS", daily_pnl=D("-6790.61"),
        )
    assert result.decision is Decision.ALLOW
    async with session_factory() as s:
        res = await s.get(RiskReservation, res_id)
        assert res.position_qty_at_reservation == D("500")


async def test_a_released_reservation_stops_contributing(session_factory, acct):
    await _reservation(session_factory, res_id=1, qty="200", anchor="200",
                       order_id=10, filled="75")
    assert await _absorbed(session_factory, _snap("125")) == {"AAPL": D("75")}
    async with session_factory() as s:
        await s.execute(update(RiskReservation).where(RiskReservation.id == 1)
                        .values(state="RELEASED"))
        await s.commit()
    assert await _absorbed(session_factory, _snap("125")) == {}
