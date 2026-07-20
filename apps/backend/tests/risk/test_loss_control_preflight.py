"""ADR 0043 PR6 — the 12 preflight checks at the unit level (each PASS/FAIL/INCOMPLETE branch)."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from unittest.mock import MagicMock

import pytest

import app.risk.loss_control.preflight as pf_mod
from app.db.enums import OrderSide, OrderSourceType, OrderStatus, OrderType, TimeInForce
from app.db.models.account import Account, AccountMode
from app.db.models.account_state import AccountState
from app.db.models.order import Order
from app.db.models.position import Position
from app.db.models.risk_control_event import RiskControlEvent
from app.db.models.risk_loss_control_state import RiskLossControlState
from app.db.models.risk_reservation import RESERVATION_HELD, RiskReservation
from app.db.models.risk_session_baseline import RiskSessionBaseline
from app.db.models.symbol import Symbol
from app.db.models.user import User
from app.risk.loss_control import constants as C
from app.risk.loss_control import preflight as pf

D = Decimal
NOW = datetime(2026, 7, 20, 15, 0, tzinfo=UTC)


@pytest.fixture(autouse=True)
def _fixed_date(monkeypatch):
    monkeypatch.setattr(pf_mod, "resolve_session_date", lambda now: "2026-07-20")


@pytest.fixture
async def base(session_factory):
    async with session_factory() as s:
        s.add(User(id=1, email="o@t"))
        s.add(Account(id=1, user_id=1, broker="alpaca", mode=AccountMode.paper, label="P"))
        s.add(Symbol(id=1, ticker="AAPL", exchange="X", asset_class="us_equity", name="A", active=True))
        s.add(RiskLossControlState(account_id=1, state=C.STATE_RECOVERY_PREFLIGHT, state_version=2,
                                   last_sequence_no=2, control_version=1, updated_at=NOW))
        await s.commit()
    return session_factory


def _ctx(session, origin=C.STATE_REDUCTION_ONLY_DAILY_LOSS, event=None, trip_cause=None, adapter=None):
    return pf.PreflightContext(session=session, account_id=1, origin_state=origin,
                               request_event=event, trip_type=None, trip_cause=trip_cause,
                               adapter=adapter)


async def test_state_known_fails_without_state_row(session_factory):
    async with session_factory() as s:
        r = await pf._state_known_and_recoverable(_ctx(s))
    assert r.status == C.CHECK_FAIL and r.reason == C.ERR_STATE_CONTRADICTION


async def test_state_known_passes(base):
    async with base() as s:
        r = await pf._state_known_and_recoverable(_ctx(s))
    assert r.passed


async def test_origin_proven_pass_and_fail(base):
    ev = RiskControlEvent(account_id=1, sequence_no=2, control_type="RECOVERY",
                          from_state=C.STATE_REDUCTION_ONLY_DAILY_LOSS,
                          to_state=C.STATE_RECOVERY_PREFLIGHT, initiator_type="SYSTEM",
                          control_version=1, created_at=NOW)
    async with base() as s:
        s.add(ev)
        await s.flush()
        good = await pf._recovery_origin_proven(_ctx(s, event=ev))
        bad = await pf._recovery_origin_proven(_ctx(s, event=None))
    assert good.passed and bad.status == C.CHECK_FAIL and bad.reason == C.ERR_ORIGIN_UNPROVEN


async def test_broker_reachable_incomplete_without_adapter(base):
    async with base() as s:
        r = await pf._broker_reachable(_ctx(s, adapter=None))
    assert r.status == C.CHECK_INCOMPLETE and r.reason == C.ERR_BROKER_UNREACHABLE


async def test_broker_account_active_pass_and_fail(base):
    ok = MagicMock()
    ok.get_account.return_value = {"status": "ACTIVE", "trading_blocked": False}
    bad = MagicMock()
    bad.get_account.return_value = {"status": "ACTIVE", "account_blocked": True}
    async with base() as s:
        assert (await pf._broker_account_active(_ctx(s, adapter=ok))).passed
        r = await pf._broker_account_active(_ctx(s, adapter=bad))
    assert r.status == C.CHECK_FAIL and r.reason == C.ERR_BROKER_ACCOUNT_INACTIVE


async def test_positions_reconcile_pass_and_mismatch(base):
    async with base() as s:
        s.add(Position(user_id=1, account_id=1, symbol_id=1, qty=D("100"), avg_entry_price=D("10"),
                       side="long", updated_at=NOW))
        await s.commit()
    match = MagicMock()
    match.get_positions.return_value = [{"symbol": "AAPL", "qty": "100"}]
    diff = MagicMock()
    diff.get_positions.return_value = [{"symbol": "AAPL", "qty": "50"}]
    async with base() as s:
        assert (await pf._positions_reconcile(_ctx(s, adapter=match))).passed
        r = await pf._positions_reconcile(_ctx(s, adapter=diff))
    assert r.status == C.CHECK_FAIL and r.reason == C.ERR_POSITION_MISMATCH


async def test_open_orders_reconcile_mismatch(base):
    async with base() as s:
        s.add(Order(id=1, user_id=1, account_id=1, symbol_id=1, client_order_id="c1",
                    side=OrderSide.BUY, qty=D("1"), type=OrderType.MARKET, tif=TimeInForce.DAY,
                    status=OrderStatus.SUBMITTED, source_type=OrderSourceType.MANUAL,
                    created_at=NOW, updated_at=NOW))
        await s.commit()
    ad = MagicMock()
    ad.list_orders.return_value = []  # broker sees 0, local sees 1 → mismatch
    async with base() as s:
        r = await pf._open_orders_reconcile(_ctx(s, adapter=ad))
    assert r.status == C.CHECK_FAIL and r.reason == C.ERR_OPEN_ORDER_MISMATCH


async def test_reservations_reconcile_orphan_fail(base):
    async with base() as s:
        s.add(RiskReservation(account_id=1, symbol="AAPL", qty=D("1"), state=RESERVATION_HELD,
                              created_at=NOW, order_id=None))  # orphan
        await s.commit()
        r = await pf._reservations_reconcile(_ctx(s))
    assert r.status == C.CHECK_FAIL and r.reason == C.ERR_RESERVATION_MISMATCH


async def test_session_baseline_valid_and_invalid(base):
    async with base() as s:
        r_missing = await pf._session_baseline_valid(_ctx(s))  # none seeded → FAIL
    assert r_missing.status == C.CHECK_FAIL
    async with base() as s:
        s.add(RiskSessionBaseline(account_id=1, market_session_date="2026-07-20",
                                  baseline_equity=D("100000"), baseline_source="RECONCILED_OPEN",
                                  captured_at=NOW, status="ACTIVE"))
        await s.commit()
        r_ok = await pf._session_baseline_valid(_ctx(s))
    assert r_ok.passed


async def test_daily_loss_recomputed(base):
    async with base() as s:
        s.add(AccountState(account_id=1, cash=D("1"), equity=D("94000"), last_equity=D("100000"),
                           buying_power=D("1"), portfolio_value=D("94000"), daytrade_count=0,
                           day_change=D("-6000"), day_change_pct=D("0"), status="ACTIVE",
                           updated_at=NOW, raw_payload={}))
        await s.commit()
        r = await pf._daily_loss_recomputed(_ctx(s))
    assert r.passed


async def test_trip_cause_classified_known_and_unknown(base):
    async with base() as s:
        assert (await pf._trip_cause_classified(
            _ctx(s, trip_cause=C.TRIP_CAUSE_REALIZED_AND_MARK_TO_MARKET_LOSS))).passed
        r = await pf._trip_cause_classified(_ctx(s, trip_cause=None))
    assert r.status == C.CHECK_FAIL and r.reason == C.ERR_TRIP_CAUSE_UNKNOWN


async def test_control_state_consistent_breaker_requires_trip(base):
    # A breaker-origin recovery with NO tripped breaker column is a contradiction.
    async with base() as s:
        r = await pf._control_state_consistent(_ctx(s, origin=C.STATE_REDUCTION_ONLY_BREAKER))
    assert r.status == C.CHECK_FAIL and r.reason == C.ERR_STATE_CONTRADICTION
    async with base() as s:
        acct = await s.get(Account, 1)
        acct.circuit_breaker_tripped_at = NOW
        await s.commit()
        ok = await pf._control_state_consistent(_ctx(s, origin=C.STATE_REDUCTION_ONLY_BREAKER))
    assert ok.passed


async def test_aggregate_and_broker_call_error_paths(base):
    from app.risk.loss_control.preflight import PreflightCheckResult as R
    assert pf.aggregate_verdict([R("a", C.CHECK_PASS), R("b", C.CHECK_FAIL)]) == C.AGG_FAIL
    assert pf.aggregate_verdict([R("a", C.CHECK_PASS), R("b", C.CHECK_INCOMPLETE)]) == C.AGG_INCOMPLETE
    assert pf.aggregate_verdict([R("a", C.CHECK_PASS)]) == C.AGG_PASS
    # A broker whose call raises → treated as unreachable (None), not a crash.
    boom = MagicMock()
    boom.get_account.side_effect = RuntimeError("x")
    async with base() as s:
        assert (await pf._broker_reachable(_ctx(s, adapter=boom))).status == C.CHECK_INCOMPLETE
    boom2 = MagicMock()
    boom2.list_orders.side_effect = RuntimeError("x")
    async with base() as s:
        assert (await pf._open_orders_reconcile(_ctx(s, adapter=boom2))).status == C.CHECK_INCOMPLETE


async def test_broker_dependent_checks_incomplete_without_adapter(base):
    async with base() as s:
        assert (await pf._broker_account_active(_ctx(s, adapter=None))).status == C.CHECK_INCOMPLETE
        assert (await pf._positions_reconcile(_ctx(s, adapter=None))).status == C.CHECK_INCOMPLETE
        assert await pf._broker_open_orders(_ctx(s, adapter=None)) is None  # no list_orders
    # A direct call into the orders helper with no adapter also yields None (defensive).
    async with base() as s:
        assert await pf._broker_call_orders(_ctx(s, adapter=None)) is None


async def test_session_baseline_incomplete_outside_trading_session(base, monkeypatch):
    monkeypatch.setattr(pf_mod, "resolve_session_date", lambda now: None)
    async with base() as s:
        r = await pf._session_baseline_valid(_ctx(s))
    assert r.status == C.CHECK_INCOMPLETE and r.reason == C.ERR_BASELINE_INVALID


async def test_control_state_consistent_fails_when_row_or_account_absent(session_factory):
    # No state row and no account for account 1 → the check FAILs (contradiction), never guesses PASS.
    async with session_factory() as s:
        r = await pf._control_state_consistent(_ctx(s))
    assert r.status == C.CHECK_FAIL and r.reason == C.ERR_STATE_CONTRADICTION


async def test_positions_reconcile_skips_unknown_symbol_id(base):
    # A local position whose symbol_id has no Symbol row is skipped (ticker unresolved), not crashed.
    async with base() as s:
        s.add(Position(user_id=1, account_id=1, symbol_id=999, qty=D("5"),
                       avg_entry_price=D("10"), side="long", updated_at=NOW))
        await s.commit()
    ad = MagicMock()
    ad.get_positions.return_value = []  # broker flat; unknown-symbol local row skipped
    async with base() as s:
        r = await pf._positions_reconcile(_ctx(s, adapter=ad))
    assert r.passed  # the unresolved local row contributed nothing → reconciles clean
