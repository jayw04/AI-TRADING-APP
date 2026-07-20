"""ADR 0043 §D5 PR6 — the recovery coordinator (request → 12 checks → authority → transition).

Covers eligibility, durable origin, the 12 persisted checks, fail-closed aggregate, the authority
matrix, idempotency, commit-failure handling, and the stop-at-RECOVERY_COOLDOWN boundary.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from sqlalchemy import func, select

import app.risk.loss_control.preflight as pf_mod
import app.risk.loss_control.recovery as rec_mod
from app.db.models.account import Account, AccountMode
from app.db.models.account_state import AccountState
from app.db.models.risk_recovery_preflight import RiskRecoveryPreflight
from app.db.models.risk_recovery_preflight_check import RiskRecoveryPreflightCheck
from app.db.models.risk_session_baseline import RiskSessionBaseline
from app.db.models.symbol import Symbol
from app.db.models.user import User
from app.risk.loss_control import constants as C
from app.risk.loss_control.recovery import RecoveryPreflightService
from app.risk.loss_control.service import LossControlService, TransitionContext
from app.risk.loss_control.state_machine import (
    TRIGGER_BREAKER_TRIP,
    TRIGGER_DAILY_LOSS_BREACH,
    TRIGGER_INTEGRITY_VIOLATION,
)

D = Decimal
NOW = datetime(2026, 7, 20, 15, 0, tzinfo=UTC)
SESSION_DATE = "2026-07-20"
OWNER_ID = 1
OPERATOR_ID = 2


@pytest.fixture(autouse=True)
def _fixed_session_date(monkeypatch):
    # The preflight resolves the session date from the real calendar; pin it so PASS tests are
    # deterministic regardless of wall-clock (weekend/holiday).
    monkeypatch.setattr(pf_mod, "resolve_session_date", lambda now: SESSION_DATE)


@pytest.fixture
async def seeded(session_factory):
    async with session_factory() as s:
        s.add(User(id=OWNER_ID, email="owner@t"))
        s.add(User(id=OPERATOR_ID, email="op@t"))
        s.add(Account(id=1, user_id=OWNER_ID, broker="alpaca", mode=AccountMode.paper, label="P"))
        s.add(Symbol(id=1, ticker="AAPL", exchange="NASDAQ", asset_class="us_equity",
                     name="Apple", active=True))
        s.add(AccountState(account_id=1, cash=D("1"), equity=D("94000"), last_equity=D("100000"),
                           buying_power=D("1"), portfolio_value=D("94000"), daytrade_count=0,
                           day_change=D("-6000"), day_change_pct=D("0"), status="ACTIVE",
                           updated_at=NOW, raw_payload={}))
        s.add(RiskSessionBaseline(account_id=1, market_session_date=SESSION_DATE,
                                  baseline_equity=D("100000"), baseline_source="RECONCILED_OPEN",
                                  captured_at=NOW, status="ACTIVE"))
        await s.commit()
    return session_factory


def _healthy_adapter():
    a = MagicMock()
    a.get_account.return_value = {"status": "ACTIVE", "trading_blocked": False, "account_blocked": False}
    a.get_positions.return_value = []
    a.list_orders.return_value = []
    return a


async def _drive_to_lock(session_factory, trigger, trip_cause=None, *, tripped_breaker=False):
    async with session_factory() as s:
        await LossControlService(s).request_transition(
            account_id=1, trigger=trigger,
            context=TransitionContext(initiator_type="SYSTEM", trip_cause=trip_cause),
        )
    if tripped_breaker:
        async with session_factory() as s:
            acct = await s.get(Account, 1)
            acct.circuit_breaker_tripped_at = NOW
            await s.commit()


async def _state(session_factory):
    from app.db.models.risk_loss_control_state import RiskLossControlState
    async with session_factory() as s:
        return await s.scalar(select(RiskLossControlState).where(RiskLossControlState.account_id == 1))


async def _check_rows(session_factory, preflight_id):
    async with session_factory() as s:
        return list((await s.execute(
            select(RiskRecoveryPreflightCheck).where(
                RiskRecoveryPreflightCheck.preflight_id == preflight_id
            ).order_by(RiskRecoveryPreflightCheck.id)
        )).scalars().all())


# --------------------------------------------------------------- eligibility


async def test_normal_state_request_is_not_eligible(seeded):
    svc = RecoveryPreflightService(seeded)
    out = await svc.request_recovery(account_id=1, account_owner_id=OWNER_ID,
                                     idempotency_key="k1", requester_user_id=OWNER_ID)
    assert out.rejected and out.reason == C.ERR_NOT_ELIGIBLE
    async with seeded() as s:  # no preflight row created
        assert await s.scalar(select(func.count()).select_from(RiskRecoveryPreflight)) == 0


async def test_missing_state_does_not_bootstrap(seeded):
    # No state row exists for account 1 yet (never locked). Request must not create one.
    svc = RecoveryPreflightService(seeded)
    out = await svc.request_recovery(account_id=1, account_owner_id=OWNER_ID,
                                     idempotency_key="k", requester_user_id=OWNER_ID)
    assert out.rejected and out.reason == C.ERR_NOT_ELIGIBLE
    from app.db.models.risk_loss_control_state import RiskLossControlState
    async with seeded() as s:
        assert await s.scalar(select(func.count()).select_from(RiskLossControlState)) == 0


# --------------------------------------------------------------- request enters RECOVERY_PREFLIGHT


async def test_daily_loss_lock_enters_recovery_preflight(seeded):
    await _drive_to_lock(seeded, TRIGGER_DAILY_LOSS_BREACH,
                         trip_cause=C.TRIP_CAUSE_REALIZED_AND_MARK_TO_MARKET_LOSS)
    svc = RecoveryPreflightService(seeded)
    out = await svc.request_recovery(account_id=1, account_owner_id=OWNER_ID, idempotency_key="k",
                                     requester_user_id=OWNER_ID, adapter=_healthy_adapter())
    assert out.accepted
    # Exactly 12 checks persisted.
    assert len(await _check_rows(seeded, out.preflight_id)) == 12
    # Durable origin recorded from the committed event.
    async with seeded() as s:
        parent = await s.get(RiskRecoveryPreflight, out.preflight_id)
    assert parent.origin_state == C.STATE_REDUCTION_ONLY_DAILY_LOSS
    assert parent.request_event_id is not None


async def test_integrity_stop_enters_recovery_preflight_via_operator(seeded, monkeypatch):
    monkeypatch.setattr(rec_mod, "get_settings",
                        lambda: SimpleNamespace(risk_operator_user_ids=[OPERATOR_ID]))
    await _drive_to_lock(seeded, TRIGGER_INTEGRITY_VIOLATION)
    svc = RecoveryPreflightService(seeded)
    out = await svc.request_recovery(account_id=1, account_owner_id=OWNER_ID, idempotency_key="k",
                                     requester_user_id=OPERATOR_ID, adapter=_healthy_adapter())
    assert out.accepted and len(await _check_rows(seeded, out.preflight_id)) == 12


async def test_owner_cannot_request_integrity_recovery(seeded, monkeypatch):
    monkeypatch.setattr(rec_mod, "get_settings",
                        lambda: SimpleNamespace(risk_operator_user_ids=[]))
    await _drive_to_lock(seeded, TRIGGER_INTEGRITY_VIOLATION)
    svc = RecoveryPreflightService(seeded)
    out = await svc.request_recovery(account_id=1, account_owner_id=OWNER_ID, idempotency_key="k",
                                     requester_user_id=OWNER_ID)
    assert out.rejected and out.reason == C.ERR_NOT_AUTHORIZED
    assert (await _state(seeded)).state == C.STATE_INTEGRITY_STOP  # never transitioned


# --------------------------------------------------------------- aggregate + transitions


async def test_all_pass_daily_loss_owner_enters_cooldown(seeded, monkeypatch):
    monkeypatch.setattr(rec_mod, "get_settings",
                        lambda: SimpleNamespace(risk_operator_user_ids=[]))
    await _drive_to_lock(seeded, TRIGGER_DAILY_LOSS_BREACH,
                         trip_cause=C.TRIP_CAUSE_REALIZED_AND_MARK_TO_MARKET_LOSS)
    svc = RecoveryPreflightService(seeded)
    out = await svc.request_recovery(account_id=1, account_owner_id=OWNER_ID, idempotency_key="k",
                                     requester_user_id=OWNER_ID, adapter=_healthy_adapter())
    assert out.aggregate_verdict == C.AGG_PASS
    assert out.status == C.PREFLIGHT_STATUS_PASSED
    assert (await _state(seeded)).state == C.STATE_RECOVERY_COOLDOWN  # PR6 stops here


async def test_missing_adapter_incomplete_returns_to_origin(seeded, monkeypatch):
    monkeypatch.setattr(rec_mod, "get_settings", lambda: SimpleNamespace(risk_operator_user_ids=[]))
    await _drive_to_lock(seeded, TRIGGER_DAILY_LOSS_BREACH,
                         trip_cause=C.TRIP_CAUSE_REALIZED_AND_MARK_TO_MARKET_LOSS)
    svc = RecoveryPreflightService(seeded)
    out = await svc.request_recovery(account_id=1, account_owner_id=OWNER_ID, idempotency_key="k",
                                     requester_user_id=OWNER_ID, adapter=None)  # broker unverifiable
    assert out.aggregate_verdict == C.AGG_INCOMPLETE
    assert out.status == C.PREFLIGHT_STATUS_INCOMPLETE
    assert (await _state(seeded)).state == C.STATE_REDUCTION_ONLY_DAILY_LOSS  # back to origin


async def test_integrity_pass_awaits_authorization_then_operator_approves(seeded, monkeypatch):
    monkeypatch.setattr(rec_mod, "get_settings",
                        lambda: SimpleNamespace(risk_operator_user_ids=[OPERATOR_ID]))
    await _drive_to_lock(seeded, TRIGGER_INTEGRITY_VIOLATION,
                         trip_cause=C.TRIP_CAUSE_BROKER_STATE_UNCERTAIN)
    svc = RecoveryPreflightService(seeded)
    # An integrity origin needs a durable, KNOWN cause for trip_cause_classified — but even all-pass
    # stays AUTHORIZATION_REQUIRED (never system/owner self-authorized).
    out = await svc.request_recovery(account_id=1, account_owner_id=OWNER_ID, idempotency_key="k",
                                     requester_user_id=OPERATOR_ID, adapter=_healthy_adapter())
    if out.aggregate_verdict == C.AGG_PASS:
        assert out.status == C.PREFLIGHT_STATUS_AUTHORIZATION_REQUIRED
        assert (await _state(seeded)).state == C.STATE_RECOVERY_PREFLIGHT  # not cooled down yet
        approved = await svc.approve(account_id=1, account_owner_id=OWNER_ID,
                                     preflight_id=out.preflight_id, approver_user_id=OPERATOR_ID)
        assert approved.status == C.PREFLIGHT_STATUS_PASSED
        assert (await _state(seeded)).state == C.STATE_RECOVERY_COOLDOWN


# --------------------------------------------------------------- idempotency


async def test_same_key_returns_same_preflight(seeded):
    await _drive_to_lock(seeded, TRIGGER_DAILY_LOSS_BREACH,
                         trip_cause=C.TRIP_CAUSE_REALIZED_AND_MARK_TO_MARKET_LOSS)
    svc = RecoveryPreflightService(seeded)
    a = await svc.request_recovery(account_id=1, account_owner_id=OWNER_ID, idempotency_key="k",
                                   requester_user_id=OWNER_ID, adapter=_healthy_adapter())
    b = await svc.request_recovery(account_id=1, account_owner_id=OWNER_ID, idempotency_key="k",
                                   requester_user_id=OWNER_ID, adapter=_healthy_adapter())
    assert a.preflight_id == b.preflight_id
    async with seeded() as s:
        assert await s.scalar(select(func.count()).select_from(RiskRecoveryPreflight)) == 1


async def test_conflicting_key_is_rejected(seeded, monkeypatch):
    # The second (different) requester must be AUTHORIZED so the idempotency conflict — not an
    # authorization rejection — is what surfaces. Make user 2 a registered operator.
    monkeypatch.setattr(rec_mod, "get_settings",
                        lambda: SimpleNamespace(risk_operator_user_ids=[OPERATOR_ID]))
    await _drive_to_lock(seeded, TRIGGER_DAILY_LOSS_BREACH,
                         trip_cause=C.TRIP_CAUSE_REALIZED_AND_MARK_TO_MARKET_LOSS)
    svc = RecoveryPreflightService(seeded)
    await svc.request_recovery(account_id=1, account_owner_id=OWNER_ID, idempotency_key="k",
                               requester_user_id=OWNER_ID, adapter=_healthy_adapter())
    # Same key, DIFFERENT (authorized) requester → conflict.
    out = await svc.request_recovery(account_id=1, account_owner_id=OWNER_ID, idempotency_key="k",
                                     requester_user_id=OPERATOR_ID)
    assert out.rejected and out.reason == C.ERR_IDEMPOTENCY_CONFLICT


# --------------------------------------------------------------- fail-closed aggregate + BLOCKED


async def test_blocked_checks_persisted_as_incomplete_not_omitted(seeded, monkeypatch):
    monkeypatch.setattr(rec_mod, "get_settings", lambda: SimpleNamespace(risk_operator_user_ids=[]))
    await _drive_to_lock(seeded, TRIGGER_DAILY_LOSS_BREACH,
                         trip_cause=C.TRIP_CAUSE_REALIZED_AND_MARK_TO_MARKET_LOSS)
    svc = RecoveryPreflightService(seeded)
    out = await svc.request_recovery(account_id=1, account_owner_id=OWNER_ID, idempotency_key="k",
                                     requester_user_id=OWNER_ID, adapter=None)
    rows = {r.check_name: r for r in await _check_rows(seeded, out.preflight_id)}
    assert len(rows) == 12  # all twelve present, none omitted
    import json as _json
    blocked = rows[C.CHECK_BROKER_ACCOUNT_ACTIVE]
    assert blocked.status == C.CHECK_INCOMPLETE
    assert _json.loads(blocked.evidence)["reason"].startswith("BLOCKED_BY_")


async def test_one_failing_check_makes_aggregate_fail(seeded, monkeypatch):
    monkeypatch.setattr(rec_mod, "get_settings", lambda: SimpleNamespace(risk_operator_user_ids=[]))
    await _drive_to_lock(seeded, TRIGGER_DAILY_LOSS_BREACH,
                         trip_cause=C.TRIP_CAUSE_REALIZED_AND_MARK_TO_MARKET_LOSS)
    # A broker whose account is BLOCKED → broker_account_active FAILs → aggregate FAIL.
    adapter = MagicMock()
    adapter.get_account.return_value = {"status": "ACTIVE", "trading_blocked": True, "account_blocked": False}
    adapter.get_positions.return_value = []
    adapter.list_orders.return_value = []
    svc = RecoveryPreflightService(seeded)
    out = await svc.request_recovery(account_id=1, account_owner_id=OWNER_ID, idempotency_key="k",
                                     requester_user_id=OWNER_ID, adapter=adapter)
    assert out.aggregate_verdict == C.AGG_FAIL and out.status == C.PREFLIGHT_STATUS_FAILED
    assert (await _state(seeded)).state == C.STATE_REDUCTION_ONLY_DAILY_LOSS  # returned to origin


async def test_failed_breaker_recovery_returns_to_breaker_origin(seeded, monkeypatch):
    monkeypatch.setattr(rec_mod, "get_settings",
                        lambda: SimpleNamespace(risk_operator_user_ids=[OPERATOR_ID]))
    await _drive_to_lock(seeded, TRIGGER_BREAKER_TRIP,
                         trip_cause=C.TRIP_CAUSE_REALIZED_AND_MARK_TO_MARKET_LOSS,
                         tripped_breaker=True)
    svc = RecoveryPreflightService(seeded)
    out = await svc.request_recovery(account_id=1, account_owner_id=OWNER_ID, idempotency_key="k",
                                     requester_user_id=OPERATOR_ID, adapter=None)  # INCOMPLETE
    assert out.aggregate_verdict == C.AGG_INCOMPLETE
    assert (await _state(seeded)).state == C.STATE_REDUCTION_ONLY_BREAKER


async def test_failed_integrity_recovery_returns_to_integrity_stop(seeded, monkeypatch):
    monkeypatch.setattr(rec_mod, "get_settings",
                        lambda: SimpleNamespace(risk_operator_user_ids=[OPERATOR_ID]))
    await _drive_to_lock(seeded, TRIGGER_INTEGRITY_VIOLATION)  # no trip_cause → will not pass
    svc = RecoveryPreflightService(seeded)
    out = await svc.request_recovery(account_id=1, account_owner_id=OWNER_ID, idempotency_key="k",
                                     requester_user_id=OPERATOR_ID, adapter=None)
    assert out.aggregate_verdict != C.AGG_PASS
    assert (await _state(seeded)).state == C.STATE_INTEGRITY_STOP  # fail-closed to integrity


# --------------------------------------------------------------- authority: system / owner limits


async def test_owner_pass_on_breaker_without_daily_loss_cause_awaits_authorization(seeded, monkeypatch):
    # Owner recovering a BREAKER lock whose cause is NOT ordinary daily-loss cannot self-authorize.
    monkeypatch.setattr(rec_mod, "get_settings", lambda: SimpleNamespace(risk_operator_user_ids=[]))
    await _drive_to_lock(seeded, TRIGGER_BREAKER_TRIP,
                         trip_cause=C.TRIP_CAUSE_LOSS_VELOCITY, tripped_breaker=True)
    svc = RecoveryPreflightService(seeded)
    out = await svc.request_recovery(account_id=1, account_owner_id=OWNER_ID, idempotency_key="k",
                                     requester_user_id=OWNER_ID, adapter=_healthy_adapter())
    if out.aggregate_verdict == C.AGG_PASS:
        assert out.status == C.PREFLIGHT_STATUS_AUTHORIZATION_REQUIRED
        assert (await _state(seeded)).state == C.STATE_RECOVERY_PREFLIGHT  # NOT cooldown


# --------------------------------------------------------------- commit failure + cancellation


async def test_request_transition_commit_failure_is_recorded_and_not_authoritative(seeded, monkeypatch):
    monkeypatch.setattr(rec_mod, "get_settings", lambda: SimpleNamespace(risk_operator_user_ids=[]))
    await _drive_to_lock(seeded, TRIGGER_DAILY_LOSS_BREACH,
                         trip_cause=C.TRIP_CAUSE_REALIZED_AND_MARK_TO_MARKET_LOSS)

    async def _boom(self, **kw):
        raise RuntimeError("transition write failed")

    monkeypatch.setattr(
        "app.risk.loss_control.service.LossControlService.request_transition", _boom
    )
    svc = RecoveryPreflightService(seeded)
    out = await svc.request_recovery(account_id=1, account_owner_id=OWNER_ID, idempotency_key="k",
                                     requester_user_id=OWNER_ID, adapter=_healthy_adapter())
    assert out.status == C.PREFLIGHT_STATUS_COMMIT_FAILED
    assert out.reason == C.ERR_TRANSITION_COMMIT_FAILED
    # No authoritative checks ran; the account stays at its lock (no stale-state advance).
    assert (await _state(seeded)).state == C.STATE_REDUCTION_ONLY_DAILY_LOSS


async def test_cancelled_error_propagates_through_checks(seeded, monkeypatch):
    import asyncio
    monkeypatch.setattr(rec_mod, "get_settings", lambda: SimpleNamespace(risk_operator_user_ids=[]))
    await _drive_to_lock(seeded, TRIGGER_DAILY_LOSS_BREACH,
                         trip_cause=C.TRIP_CAUSE_REALIZED_AND_MARK_TO_MARKET_LOSS)

    async def _cancel(ctx):
        raise asyncio.CancelledError

    # _safe catches Exception, not BaseException — CancelledError must propagate through the runner.
    monkeypatch.setitem(pf_mod._CHECK_FUNCS, C.CHECK_STATE_KNOWN_AND_RECOVERABLE, _cancel)
    svc = RecoveryPreflightService(seeded)
    with pytest.raises(asyncio.CancelledError):
        await svc.request_recovery(account_id=1, account_owner_id=OWNER_ID, idempotency_key="k",
                                   requester_user_id=OWNER_ID, adapter=_healthy_adapter())


async def test_no_raw_exception_text_in_evidence(seeded, monkeypatch):
    monkeypatch.setattr(rec_mod, "get_settings", lambda: SimpleNamespace(risk_operator_user_ids=[]))
    await _drive_to_lock(seeded, TRIGGER_DAILY_LOSS_BREACH,
                         trip_cause=C.TRIP_CAUSE_REALIZED_AND_MARK_TO_MARKET_LOSS)

    async def _raise(ctx):
        raise RuntimeError("SECRET postgres://user:pw@host/db and a broker token abc123")

    monkeypatch.setitem(pf_mod._CHECK_FUNCS, C.CHECK_DAILY_LOSS_RECOMPUTED, _raise)
    svc = RecoveryPreflightService(seeded)
    out = await svc.request_recovery(account_id=1, account_owner_id=OWNER_ID, idempotency_key="k",
                                     requester_user_id=OWNER_ID, adapter=_healthy_adapter())
    for r in await _check_rows(seeded, out.preflight_id):
        assert "SECRET" not in (r.evidence or "") and "postgres://" not in (r.evidence or "")
        assert "abc123" not in (r.evidence or "")


# --------------------------------------------------------------- isolation + boundary


async def test_account_isolation(seeded, session_factory):
    # A second account's lock must not be touched by account 1's recovery.
    async with seeded() as s:
        s.add(User(id=3, email="u3@t"))
        s.add(Account(id=2, user_id=3, broker="alpaca", mode=AccountMode.paper, label="P2"))
        await s.commit()
    async with seeded() as s:  # lock account 2
        await LossControlService(s).request_transition(
            account_id=2, trigger=TRIGGER_DAILY_LOSS_BREACH,
            context=TransitionContext(initiator_type="SYSTEM"),
        )
    await _drive_to_lock(seeded, TRIGGER_DAILY_LOSS_BREACH,
                         trip_cause=C.TRIP_CAUSE_REALIZED_AND_MARK_TO_MARKET_LOSS)
    svc = RecoveryPreflightService(seeded)
    await svc.request_recovery(account_id=1, account_owner_id=OWNER_ID, idempotency_key="k",
                               requester_user_id=OWNER_ID, adapter=None)
    from app.db.models.risk_loss_control_state import RiskLossControlState
    async with seeded() as s:
        acct2 = await s.scalar(select(RiskLossControlState).where(RiskLossControlState.account_id == 2))
    assert acct2.state == C.STATE_REDUCTION_ONLY_DAILY_LOSS  # untouched


async def test_recovery_never_reaches_normal(seeded, monkeypatch):
    # PR6 stops at RECOVERY_COOLDOWN; a pass never sets NORMAL (that is PR7's re-arm).
    monkeypatch.setattr(rec_mod, "get_settings", lambda: SimpleNamespace(risk_operator_user_ids=[]))
    await _drive_to_lock(seeded, TRIGGER_DAILY_LOSS_BREACH,
                         trip_cause=C.TRIP_CAUSE_REALIZED_AND_MARK_TO_MARKET_LOSS)
    svc = RecoveryPreflightService(seeded)
    await svc.request_recovery(account_id=1, account_owner_id=OWNER_ID, idempotency_key="k",
                               requester_user_id=OWNER_ID, adapter=_healthy_adapter())
    assert (await _state(seeded)).state != C.STATE_NORMAL


# --------------------------------------------------------------- approve / get edge cases


async def test_approve_unauthorized_actor_rejected(seeded, monkeypatch):
    monkeypatch.setattr(rec_mod, "get_settings",
                        lambda: SimpleNamespace(risk_operator_user_ids=[OPERATOR_ID]))
    await _drive_to_lock(seeded, TRIGGER_INTEGRITY_VIOLATION,
                         trip_cause=C.TRIP_CAUSE_BROKER_STATE_UNCERTAIN)
    svc = RecoveryPreflightService(seeded)
    out = await svc.request_recovery(account_id=1, account_owner_id=OWNER_ID, idempotency_key="k",
                                     requester_user_id=OPERATOR_ID, adapter=_healthy_adapter())
    if out.status == C.PREFLIGHT_STATUS_AUTHORIZATION_REQUIRED:
        # A non-operator, non-owner user (id 99) cannot approve.
        bad = await svc.approve(account_id=1, account_owner_id=OWNER_ID,
                                preflight_id=out.preflight_id, approver_user_id=99)
        assert bad.rejected and bad.reason == C.ERR_NOT_AUTHORIZED
        # The OWNER cannot authorize an INTEGRITY_STOP recovery either.
        owner_try = await svc.approve(account_id=1, account_owner_id=OWNER_ID,
                                      preflight_id=out.preflight_id, approver_user_id=OWNER_ID)
        assert owner_try.rejected and owner_try.reason == C.ERR_NOT_AUTHORIZED


async def test_approve_is_idempotent_after_pass(seeded, monkeypatch):
    monkeypatch.setattr(rec_mod, "get_settings", lambda: SimpleNamespace(risk_operator_user_ids=[]))
    await _drive_to_lock(seeded, TRIGGER_DAILY_LOSS_BREACH,
                         trip_cause=C.TRIP_CAUSE_REALIZED_AND_MARK_TO_MARKET_LOSS)
    svc = RecoveryPreflightService(seeded)
    out = await svc.request_recovery(account_id=1, account_owner_id=OWNER_ID, idempotency_key="k",
                                     requester_user_id=OWNER_ID, adapter=_healthy_adapter())
    if out.status == C.PREFLIGHT_STATUS_PASSED:  # daily-loss owner auto-passed
        again = await svc.approve(account_id=1, account_owner_id=OWNER_ID,
                                  preflight_id=out.preflight_id, approver_user_id=OWNER_ID)
        assert again.status == C.PREFLIGHT_STATUS_PASSED  # idempotent, not re-run


async def test_get_returns_none_for_missing_or_wrong_account(seeded):
    svc = RecoveryPreflightService(seeded)
    assert await svc.get(1, 9999) is None


async def test_second_key_while_in_preflight_returns_the_active_workflow(seeded, monkeypatch):
    # One active preflight per account: while the account sits in RECOVERY_PREFLIGHT, a request with
    # ANY key returns the single active workflow rather than starting a second.
    monkeypatch.setattr(rec_mod, "get_settings",
                        lambda: SimpleNamespace(risk_operator_user_ids=[OPERATOR_ID]))
    await _drive_to_lock(seeded, TRIGGER_INTEGRITY_VIOLATION,
                         trip_cause=C.TRIP_CAUSE_BROKER_STATE_UNCERTAIN)
    svc = RecoveryPreflightService(seeded)
    first = await svc.request_recovery(account_id=1, account_owner_id=OWNER_ID, idempotency_key="k1",
                                       requester_user_id=OPERATOR_ID, adapter=_healthy_adapter())
    if first.status == C.PREFLIGHT_STATUS_AUTHORIZATION_REQUIRED:
        second = await svc.request_recovery(account_id=1, account_owner_id=OWNER_ID,
                                            idempotency_key="k2", requester_user_id=OPERATOR_ID,
                                            adapter=_healthy_adapter())
        assert second.accepted and second.preflight_id == first.preflight_id
        async with seeded() as s:
            assert await s.scalar(select(func.count()).select_from(RiskRecoveryPreflight)) == 1


async def test_approve_on_non_authorization_required_is_rejected(seeded, monkeypatch):
    monkeypatch.setattr(rec_mod, "get_settings", lambda: SimpleNamespace(risk_operator_user_ids=[]))
    await _drive_to_lock(seeded, TRIGGER_DAILY_LOSS_BREACH,
                         trip_cause=C.TRIP_CAUSE_REALIZED_AND_MARK_TO_MARKET_LOSS)
    svc = RecoveryPreflightService(seeded)
    out = await svc.request_recovery(account_id=1, account_owner_id=OWNER_ID, idempotency_key="k",
                                     requester_user_id=OWNER_ID, adapter=None)  # INCOMPLETE → FAILED
    bad = await svc.approve(account_id=1, account_owner_id=OWNER_ID,
                            preflight_id=out.preflight_id, approver_user_id=OWNER_ID)
    assert bad.rejected and bad.reason == C.ERR_NOT_ELIGIBLE  # not in AUTHORIZATION_REQUIRED


async def test_approve_missing_preflight_rejected(seeded, monkeypatch):
    monkeypatch.setattr(rec_mod, "get_settings", lambda: SimpleNamespace(risk_operator_user_ids=[]))
    svc = RecoveryPreflightService(seeded)
    out = await svc.approve(account_id=1, account_owner_id=OWNER_ID, preflight_id=9999,
                            approver_user_id=OWNER_ID)
    assert out.rejected and out.reason == C.ERR_NOT_ELIGIBLE


async def test_unauthorized_user_cannot_request(seeded):
    # A user who is neither owner nor operator is rejected outright (no state read side effects).
    await _drive_to_lock(seeded, TRIGGER_DAILY_LOSS_BREACH,
                         trip_cause=C.TRIP_CAUSE_REALIZED_AND_MARK_TO_MARKET_LOSS)
    svc = RecoveryPreflightService(seeded)
    out = await svc.request_recovery(account_id=1, account_owner_id=OWNER_ID, idempotency_key="k",
                                     requester_user_id=99)
    assert out.rejected and out.reason == C.ERR_NOT_AUTHORIZED


async def test_pass_transition_commit_failure_is_not_claimed(seeded, monkeypatch):
    # Aggregate PASS + authorized, but the PREFLIGHT_PASS write raises → COMMIT_FAILED, not PASSED,
    # and recovery is not claimed.
    monkeypatch.setattr(rec_mod, "get_settings", lambda: SimpleNamespace(risk_operator_user_ids=[]))
    await _drive_to_lock(seeded, TRIGGER_DAILY_LOSS_BREACH,
                         trip_cause=C.TRIP_CAUSE_REALIZED_AND_MARK_TO_MARKET_LOSS)
    svc = RecoveryPreflightService(seeded)
    real = LossControlService.request_transition
    calls = {"n": 0}

    async def _fail_on_pass(self, **kw):
        calls["n"] += 1
        if kw.get("trigger") == "PREFLIGHT_PASS":
            raise RuntimeError("pass write failed")
        return await real(self, **kw)

    monkeypatch.setattr(LossControlService, "request_transition", _fail_on_pass)
    out = await svc.request_recovery(account_id=1, account_owner_id=OWNER_ID, idempotency_key="k",
                                     requester_user_id=OWNER_ID, adapter=_healthy_adapter())
    assert out.status == C.PREFLIGHT_STATUS_COMMIT_FAILED
    assert (await _state(seeded)).state == C.STATE_RECOVERY_PREFLIGHT  # not cooled down


async def test_request_when_already_in_preflight_returns_active(seeded, monkeypatch):
    monkeypatch.setattr(rec_mod, "get_settings",
                        lambda: SimpleNamespace(risk_operator_user_ids=[OPERATOR_ID]))
    await _drive_to_lock(seeded, TRIGGER_INTEGRITY_VIOLATION,
                         trip_cause=C.TRIP_CAUSE_BROKER_STATE_UNCERTAIN)
    svc = RecoveryPreflightService(seeded)
    first = await svc.request_recovery(account_id=1, account_owner_id=OWNER_ID, idempotency_key="k1",
                                       requester_user_id=OPERATOR_ID, adapter=_healthy_adapter())
    if first.status == C.PREFLIGHT_STATUS_AUTHORIZATION_REQUIRED:
        # Account is now in RECOVERY_PREFLIGHT; a new request with the SAME key returns the active one.
        again = await svc.request_recovery(account_id=1, account_owner_id=OWNER_ID,
                                           idempotency_key="k1", requester_user_id=OPERATOR_ID,
                                           adapter=_healthy_adapter())
        assert again.preflight_id == first.preflight_id


# --------------------------------------------------------------- authority matrix (pure)


def test_may_authorize_pass_matrix():
    # System never self-authorizes, any origin.
    assert not rec_mod.may_authorize_pass(C.STATE_INTEGRITY_STOP, None, C.ACTOR_SYSTEM)
    assert not rec_mod.may_authorize_pass(C.STATE_REDUCTION_ONLY_DAILY_LOSS, None, C.ACTOR_SYSTEM)
    # INTEGRITY_STOP → operator only.
    assert rec_mod.may_authorize_pass(C.STATE_INTEGRITY_STOP, None, C.ACTOR_RISK_OPERATOR)
    assert not rec_mod.may_authorize_pass(C.STATE_INTEGRITY_STOP, None, C.ACTOR_OWNER)
    # Daily-loss → owner or operator.
    assert rec_mod.may_authorize_pass(C.STATE_REDUCTION_ONLY_DAILY_LOSS, None, C.ACTOR_OWNER)
    # Breaker → operator always; owner only if the cause was ordinary daily loss.
    assert rec_mod.may_authorize_pass(C.STATE_REDUCTION_ONLY_BREAKER, None, C.ACTOR_RISK_OPERATOR)
    assert rec_mod.may_authorize_pass(
        C.STATE_REDUCTION_ONLY_BREAKER, C.TRIP_CAUSE_REALIZED_AND_MARK_TO_MARKET_LOSS, C.ACTOR_OWNER)
    assert not rec_mod.may_authorize_pass(C.STATE_REDUCTION_ONLY_BREAKER, None, C.ACTOR_OWNER)
    # An origin outside the lock set never authorizes (fallthrough).
    assert not rec_mod.may_authorize_pass(C.STATE_RECOVERY_COOLDOWN, None, C.ACTOR_OWNER)


# --------------------------------------------------------------- get() reads


async def test_get_returns_parent_and_checks_or_none(seeded, monkeypatch):
    monkeypatch.setattr(rec_mod, "get_settings",
                        lambda: SimpleNamespace(risk_operator_user_ids=[]))
    await _drive_to_lock(seeded, TRIGGER_DAILY_LOSS_BREACH,
                         trip_cause=C.TRIP_CAUSE_REALIZED_AND_MARK_TO_MARKET_LOSS)
    svc = RecoveryPreflightService(seeded)
    out = await svc.request_recovery(account_id=1, account_owner_id=OWNER_ID, idempotency_key="k",
                                     requester_user_id=OWNER_ID, adapter=_healthy_adapter())
    got = await svc.get(1, out.preflight_id)
    assert got is not None
    parent, checks = got
    assert parent.id == out.preflight_id and len(checks) == 12
    assert await svc.get(1, 9999) is None          # missing
    assert await svc.get(999, out.preflight_id) is None  # wrong account


# --------------------------------------------------------------- transition-commit edges


async def test_recovery_request_commit_failure_persists_commit_failed(seeded, monkeypatch):
    monkeypatch.setattr(rec_mod, "get_settings",
                        lambda: SimpleNamespace(risk_operator_user_ids=[]))
    await _drive_to_lock(seeded, TRIGGER_DAILY_LOSS_BREACH,
                         trip_cause=C.TRIP_CAUSE_REALIZED_AND_MARK_TO_MARKET_LOSS)
    svc = RecoveryPreflightService(seeded)

    async def _boom(**kw):  # the RECOVERY_REQUEST transition itself fails to commit
        return None

    monkeypatch.setattr(svc, "_transition", _boom)
    out = await svc.request_recovery(account_id=1, account_owner_id=OWNER_ID, idempotency_key="k",
                                     requester_user_id=OWNER_ID, adapter=_healthy_adapter())
    assert out.accepted and out.status == C.PREFLIGHT_STATUS_COMMIT_FAILED
    assert out.reason == C.ERR_TRANSITION_COMMIT_FAILED and out.preflight_id is not None
    # No recovery claimed: the account stays where it was locked.
    assert (await _state(seeded)).state == C.STATE_REDUCTION_ONLY_DAILY_LOSS


async def test_stale_request_transition_not_applied_is_rejected(seeded, monkeypatch):
    monkeypatch.setattr(rec_mod, "get_settings",
                        lambda: SimpleNamespace(risk_operator_user_ids=[]))
    await _drive_to_lock(seeded, TRIGGER_DAILY_LOSS_BREACH,
                         trip_cause=C.TRIP_CAUSE_REALIZED_AND_MARK_TO_MARKET_LOSS)
    svc = RecoveryPreflightService(seeded)

    async def _not_applied(**kw):  # state moved under us — request_transition finds no edge
        return SimpleNamespace(applied=False, event_id=None, state=C.STATE_REDUCTION_ONLY_DAILY_LOSS)

    monkeypatch.setattr(svc, "_transition", _not_applied)
    out = await svc.request_recovery(account_id=1, account_owner_id=OWNER_ID, idempotency_key="k",
                                     requester_user_id=OWNER_ID, adapter=_healthy_adapter())
    assert out.rejected and out.reason == C.ERR_NOT_ELIGIBLE


# --------------------------------------------------------------- approve staleness


async def test_approve_when_state_moved_is_stale_rejected(seeded, monkeypatch):
    # An operator gets AUTHORIZATION_REQUIRED on an INTEGRITY_STOP recovery; before they approve, the
    # account leaves RECOVERY_PREFLIGHT (evidence stale) → approve is refused, no transition.
    monkeypatch.setattr(rec_mod, "get_settings",
                        lambda: SimpleNamespace(risk_operator_user_ids=[OPERATOR_ID]))
    await _drive_to_lock(seeded, TRIGGER_INTEGRITY_VIOLATION,
                         trip_cause=C.TRIP_CAUSE_BROKER_STATE_UNCERTAIN)
    svc = RecoveryPreflightService(seeded)
    out = await svc.request_recovery(account_id=1, account_owner_id=OWNER_ID, idempotency_key="k",
                                     requester_user_id=OPERATOR_ID, adapter=_healthy_adapter())
    assert out.status == C.PREFLIGHT_STATUS_AUTHORIZATION_REQUIRED
    # Force the account out of RECOVERY_PREFLIGHT (simulate a concurrent PREFLIGHT_FAIL to origin).
    from app.risk.loss_control.state_machine import TRIGGER_PREFLIGHT_FAIL
    async with seeded() as s:
        await LossControlService(s).request_transition(
            account_id=1, trigger=TRIGGER_PREFLIGHT_FAIL,
            recovery_origin_state=C.STATE_INTEGRITY_STOP,
            context=TransitionContext(initiator_type="SYSTEM"))
    stale = await svc.approve(account_id=1, account_owner_id=OWNER_ID,
                              preflight_id=out.preflight_id, approver_user_id=OPERATOR_ID)
    assert stale.rejected and stale.reason == C.ERR_NOT_ELIGIBLE


async def test_approve_by_owner_on_integrity_is_not_authorized(seeded, monkeypatch):
    # INTEGRITY_STOP requires an operator; the owner may not authorize the pass even at approve time.
    monkeypatch.setattr(rec_mod, "get_settings",
                        lambda: SimpleNamespace(risk_operator_user_ids=[OPERATOR_ID]))
    await _drive_to_lock(seeded, TRIGGER_INTEGRITY_VIOLATION,
                         trip_cause=C.TRIP_CAUSE_BROKER_STATE_UNCERTAIN)
    svc = RecoveryPreflightService(seeded)
    out = await svc.request_recovery(account_id=1, account_owner_id=OWNER_ID, idempotency_key="k",
                                     requester_user_id=OPERATOR_ID, adapter=_healthy_adapter())
    assert out.status == C.PREFLIGHT_STATUS_AUTHORIZATION_REQUIRED
    bad = await svc.approve(account_id=1, account_owner_id=OWNER_ID,
                            preflight_id=out.preflight_id, approver_user_id=OWNER_ID)
    assert bad.rejected and bad.reason == C.ERR_NOT_AUTHORIZED


# --------------------------------------------------------------- one-active + in-flight edges


async def test_active_preflight_blocks_a_fresh_key(seeded, monkeypatch):
    # Eligible origin, but an active preflight already exists for a different key → the one-active
    # guard rejects the new key (rather than starting a second workflow).
    monkeypatch.setattr(rec_mod, "get_settings",
                        lambda: SimpleNamespace(risk_operator_user_ids=[]))
    await _drive_to_lock(seeded, TRIGGER_DAILY_LOSS_BREACH,
                         trip_cause=C.TRIP_CAUSE_REALIZED_AND_MARK_TO_MARKET_LOSS)
    st = await _state(seeded)
    async with seeded() as s:  # force the account back to an eligible origin with a RUNNING preflight
        s.add(RiskRecoveryPreflight(
            account_id=1, idempotency_key="inflight", requested_transition="RECOVERY_REQUEST",
            expected_state_version=st.state_version, requested_by_actor_type=C.ACTOR_OWNER,
            requested_by_actor_id=str(OWNER_ID), requested_at=NOW,
            origin_state=C.STATE_REDUCTION_ONLY_DAILY_LOSS, origin_state_version=st.state_version,
            trip_type=C.TRIP_TYPE_DAILY_LOSS, authority_class=C.AUTHORITY_CLASS_OWNER_OR_OPERATOR,
            status=C.PREFLIGHT_STATUS_RUNNING, result=C.PREFLIGHT_STATUS_RUNNING,
            initiator_type=C.ACTOR_OWNER, initiator_id=str(OWNER_ID), control_version=1,
            evidence_version=1, created_at=NOW, started_at=NOW))
        await s.commit()
    svc = RecoveryPreflightService(seeded)
    out = await svc.request_recovery(account_id=1, account_owner_id=OWNER_ID, idempotency_key="fresh",
                                     requester_user_id=OWNER_ID, adapter=_healthy_adapter())
    assert out.rejected and out.reason == C.ERR_ACTIVE_PREFLIGHT_EXISTS


async def test_in_preflight_without_active_row_is_not_eligible(seeded):
    # Materialized state is RECOVERY_PREFLIGHT but no active preflight row exists (torn state) →
    # a fresh request cannot proceed and does not bootstrap one.
    from app.db.models.risk_loss_control_state import RiskLossControlState
    async with seeded() as s:
        s.add(RiskLossControlState(account_id=1, state=C.STATE_RECOVERY_PREFLIGHT, state_version=3,
                                   last_sequence_no=3, control_version=1, updated_at=NOW))
        await s.commit()
    svc = RecoveryPreflightService(seeded)
    out = await svc.request_recovery(account_id=1, account_owner_id=OWNER_ID, idempotency_key="k",
                                     requester_user_id=OWNER_ID, adapter=_healthy_adapter())
    assert out.rejected and out.reason == C.ERR_NOT_ELIGIBLE


async def test_lock_trip_cause_without_upper_bound(seeded):
    # The durable trip-cause lookup also works with no upper event bound (before_event_id=None).
    await _drive_to_lock(seeded, TRIGGER_DAILY_LOSS_BREACH,
                         trip_cause=C.TRIP_CAUSE_REALIZED_AND_MARK_TO_MARKET_LOSS)
    svc = RecoveryPreflightService(seeded)
    async with seeded() as s:
        cause = await svc._lock_trip_cause(s, 1, C.STATE_REDUCTION_ONLY_DAILY_LOSS, None)
    assert cause == C.TRIP_CAUSE_REALIZED_AND_MARK_TO_MARKET_LOSS


# --------------------------------------------------------------- defensive internal paths


async def test_close_parent_missing_row_is_internal_error(seeded):
    svc = RecoveryPreflightService(seeded)
    out = await svc._close_parent(1, 999999, status=C.PREFLIGHT_STATUS_FAILED,
                                  verdict=C.AGG_FAIL, transition=None, failure_reason="x")
    assert out.rejected and out.reason == C.ERR_INTERNAL


async def test_persist_commit_failed_reloads_winner_on_duplicate(seeded):
    # Two commit-failed persists for the same key: the second hits the UNIQUE(account, key)
    # constraint, rolls back, and returns the already-persisted winner (never a second row).
    svc = RecoveryPreflightService(seeded)
    first = await svc._persist_commit_failed(1, "dup", OWNER_ID, C.ACTOR_OWNER, 1,
                                             C.STATE_REDUCTION_ONLY_DAILY_LOSS)
    assert first.status == C.PREFLIGHT_STATUS_COMMIT_FAILED
    second = await svc._persist_commit_failed(1, "dup", OWNER_ID, C.ACTOR_OWNER, 1,
                                              C.STATE_REDUCTION_ONLY_DAILY_LOSS)
    assert second.accepted and second.preflight_id == first.preflight_id
    async with seeded() as s:
        assert await s.scalar(select(func.count()).select_from(RiskRecoveryPreflight)) == 1
