"""ADR 0043 §D6 / §D1.4 (PR7) — the recovery-cooldown evaluator (the sanctioned path out of cooldown).

Exercises the full lifecycle end of ADR 0043: an account in RECOVERY_COOLDOWN is advanced to NORMAL
(COOLDOWN_COMPLETE) or regressed to INTEGRITY_STOP (HEALTH_REGRESSED) — only through
LossControlService, only when the §D1.4 policy allows, idempotently, and fail-closed.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from unittest.mock import MagicMock

import pytest
from sqlalchemy import func, select

import app.risk.loss_control.cooldown as cool_mod
from app.db.models.account import Account, AccountMode
from app.db.models.position import Position
from app.db.models.risk_control_event import RiskControlEvent
from app.db.models.risk_loss_control_state import RiskLossControlState
from app.db.models.risk_recovery_preflight import RiskRecoveryPreflight
from app.db.models.symbol import Symbol
from app.db.models.user import User
from app.risk.loss_control import constants as C
from app.risk.loss_control.cooldown import CooldownEvaluator, VelocityReading

D = Decimal
ENTRY_AT = datetime(2026, 7, 20, 18, 0, tzinfo=UTC)
ENTRY_SESSION = "2026-07-20"


@pytest.fixture
async def seeded(session_factory):
    async with session_factory() as s:
        s.add(User(id=1, email="o@t"))
        s.add(Account(id=1, user_id=1, broker="alpaca", mode=AccountMode.paper, label="P"))
        s.add(Symbol(id=1, ticker="AAPL", exchange="X", asset_class="us_equity", name="A",
                     active=True))
        await s.commit()
    return session_factory


def _healthy_adapter():
    a = MagicMock()
    a.get_account.return_value = {"status": "ACTIVE", "trading_blocked": False}
    a.get_positions.return_value = []
    a.list_orders.return_value = []
    return a


_UNSET = object()


async def _seed_cooldown(
    seeded, *, origin=C.STATE_REDUCTION_ONLY_BREAKER, trip_cause=C.TRIP_CAUSE_UNKNOWN,
    trip_evidence=None, authorized_by=None, state_version=4, last_sequence_no=3,
    extra_event_control_type=None, create_preflight=True, preflight_origin=_UNSET,
    entry_session_date=ENTRY_SESSION,
):
    """Build a durable RECOVERY_COOLDOWN history: trip → recovery-request → preflight-pass → cooldown,
    plus the PASSED preflight bound to the cooldown-entry event. Returns the cooldown-entry event id."""
    p_origin = origin if preflight_origin is _UNSET else preflight_origin
    async with seeded() as s:
        s.add(RiskLossControlState(account_id=1, state=C.STATE_RECOVERY_COOLDOWN,
                                   state_version=state_version, last_sequence_no=last_sequence_no,
                                   control_version=1, updated_at=ENTRY_AT))
        s.add(RiskControlEvent(account_id=1, sequence_no=1, control_type="CIRCUIT_BREAKER",
                               from_state=C.STATE_NORMAL, to_state=origin,
                               requested_transition="BREAKER_TRIP", trip_cause=trip_cause,
                               trip_evidence_status=trip_evidence, initiator_type="SYSTEM",
                               control_version=1, created_at=ENTRY_AT - timedelta(hours=1)))
        s.add(RiskControlEvent(account_id=1, sequence_no=2, control_type="RECOVERY",
                               from_state=origin, to_state=C.STATE_RECOVERY_PREFLIGHT,
                               requested_transition="RECOVERY_REQUEST", initiator_type="SYSTEM",
                               control_version=1, created_at=ENTRY_AT - timedelta(minutes=30)))
        entry = RiskControlEvent(account_id=1, sequence_no=3, control_type="RECOVERY",
                                 from_state=C.STATE_RECOVERY_PREFLIGHT,
                                 to_state=C.STATE_RECOVERY_COOLDOWN,
                                 requested_transition="PREFLIGHT_PASS", initiator_type="SYSTEM",
                                 control_version=1, created_at=ENTRY_AT,
                                 session_date=entry_session_date)
        s.add(entry)
        await s.flush()
        if create_preflight:
            s.add(RiskRecoveryPreflight(
                account_id=1, idempotency_key="k", requested_transition="RECOVERY_REQUEST",
                expected_state_version=state_version - 1, requested_by_actor_type=C.ACTOR_OWNER,
                requested_by_actor_id="1", requested_at=ENTRY_AT, origin_state=p_origin,
                origin_state_version=state_version - 1, transition_event_id=entry.id,
                trip_cause=trip_cause, authority_class=C.AUTHORITY_CLASS_OWNER_OR_OPERATOR,
                authorized_by_actor_id=authorized_by,
                status=C.PREFLIGHT_STATUS_PASSED, result=C.PREFLIGHT_STATUS_PASSED,
                initiator_type=C.ACTOR_OWNER, initiator_id="1", control_version=1, evidence_version=1,
                created_at=ENTRY_AT))
        if extra_event_control_type is not None:  # a fresh event AFTER cooldown entry
            s.add(RiskControlEvent(account_id=1, sequence_no=4,
                                   control_type=extra_event_control_type,
                                   from_state=C.STATE_RECOVERY_COOLDOWN, to_state=origin,
                                   requested_transition="BREAKER_TRIP", initiator_type="SYSTEM",
                                   control_version=1, created_at=ENTRY_AT + timedelta(minutes=1)))
        await s.commit()
        return entry.id


async def _state(seeded):
    async with seeded() as s:
        return await s.scalar(select(RiskLossControlState).where(
            RiskLossControlState.account_id == 1))


def _now_after(minutes):
    return ENTRY_AT + timedelta(minutes=minutes)


# --------------------------------------------------------------- artifact (15 min fixed dwell)


async def test_artifact_completes_after_15_minutes(seeded, monkeypatch):
    monkeypatch.setattr(cool_mod, "resolve_session_date", lambda now: ENTRY_SESSION)
    await _seed_cooldown(seeded, trip_cause=C.TRIP_CAUSE_UNKNOWN,
                         trip_evidence=C.TRIP_EVIDENCE_ARTIFACT_CONFIRMED)
    out = await CooldownEvaluator(seeded).evaluate(1, adapter=_healthy_adapter(), now=_now_after(15))
    assert out.verdict == C.COOLDOWN_COMPLETE and out.transitioned_to == C.STATE_NORMAL
    assert (await _state(seeded)).state == C.STATE_NORMAL


async def test_artifact_holds_at_14_59(seeded, monkeypatch):
    monkeypatch.setattr(cool_mod, "resolve_session_date", lambda now: ENTRY_SESSION)
    await _seed_cooldown(seeded, trip_cause=C.TRIP_CAUSE_UNKNOWN,
                         trip_evidence=C.TRIP_EVIDENCE_ARTIFACT_CONFIRMED)
    now = ENTRY_AT + timedelta(minutes=14, seconds=59)
    out = await CooldownEvaluator(seeded).evaluate(1, adapter=_healthy_adapter(), now=now)
    assert out.verdict == C.COOLDOWN_HOLD
    assert (await _state(seeded)).state == C.STATE_RECOVERY_COOLDOWN


# --------------------------------------------------------------- rate/velocity (30 min + recovery)


async def test_velocity_holds_above_recovery_threshold(seeded, monkeypatch):
    monkeypatch.setattr(cool_mod, "resolve_session_date", lambda now: ENTRY_SESSION)
    await _seed_cooldown(seeded, trip_cause=C.TRIP_CAUSE_LOSS_VELOCITY)
    vel = VelocityReading(current=D("600"), trip_limit=D("1000"),
                          sustained_seconds=C.VELOCITY_HEALTHY_MIN_SECONDS)  # > 50%
    out = await CooldownEvaluator(seeded).evaluate(1, adapter=_healthy_adapter(),
                                                   velocity=vel, now=_now_after(30))
    assert out.verdict == C.COOLDOWN_HOLD


async def test_velocity_holds_before_10_sustained_minutes(seeded, monkeypatch):
    monkeypatch.setattr(cool_mod, "resolve_session_date", lambda now: ENTRY_SESSION)
    await _seed_cooldown(seeded, trip_cause=C.TRIP_CAUSE_LOSS_VELOCITY)
    vel = VelocityReading(current=D("100"), trip_limit=D("1000"),
                          sustained_seconds=C.VELOCITY_HEALTHY_MIN_SECONDS - 1)  # not sustained
    out = await CooldownEvaluator(seeded).evaluate(1, adapter=_healthy_adapter(),
                                                   velocity=vel, now=_now_after(30))
    assert out.verdict == C.COOLDOWN_HOLD


async def test_velocity_missing_reading_holds(seeded, monkeypatch):
    monkeypatch.setattr(cool_mod, "resolve_session_date", lambda now: ENTRY_SESSION)
    await _seed_cooldown(seeded, trip_cause=C.TRIP_CAUSE_LOSS_VELOCITY)
    out = await CooldownEvaluator(seeded).evaluate(1, adapter=_healthy_adapter(),
                                                   velocity=None, now=_now_after(30))
    assert out.verdict == C.COOLDOWN_HOLD  # no authoritative velocity → fail closed


async def test_velocity_completes_after_dwell_and_sustained_recovery(seeded, monkeypatch):
    monkeypatch.setattr(cool_mod, "resolve_session_date", lambda now: ENTRY_SESSION)
    await _seed_cooldown(seeded, trip_cause=C.TRIP_CAUSE_LOSS_VELOCITY)
    vel = VelocityReading(current=D("400"), trip_limit=D("1000"),
                          sustained_seconds=C.VELOCITY_HEALTHY_MIN_SECONDS)
    out = await CooldownEvaluator(seeded).evaluate(1, adapter=_healthy_adapter(),
                                                   velocity=vel, now=_now_after(30))
    assert out.verdict == C.COOLDOWN_COMPLETE and out.transitioned_to == C.STATE_NORMAL


# --------------------------------------------------------------- confirmed daily loss (next session)


async def test_daily_loss_cannot_rearm_same_session(seeded, monkeypatch):
    monkeypatch.setattr(cool_mod, "resolve_session_date", lambda now: ENTRY_SESSION)  # same session
    await _seed_cooldown(seeded, origin=C.STATE_REDUCTION_ONLY_DAILY_LOSS,
                         trip_cause=C.TRIP_CAUSE_REALIZED_AND_MARK_TO_MARKET_LOSS)
    out = await CooldownEvaluator(seeded).evaluate(1, adapter=_healthy_adapter(),
                                                   now=_now_after(600))  # 10h later, same session
    assert out.verdict == C.COOLDOWN_HOLD
    assert (await _state(seeded)).state == C.STATE_RECOVERY_COOLDOWN


async def test_daily_loss_completes_next_session_with_health(seeded, monkeypatch):
    monkeypatch.setattr(cool_mod, "resolve_session_date", lambda now: "2026-07-21")  # next session
    await _seed_cooldown(seeded, origin=C.STATE_REDUCTION_ONLY_DAILY_LOSS,
                         trip_cause=C.TRIP_CAUSE_REALIZED_AND_MARK_TO_MARKET_LOSS)
    out = await CooldownEvaluator(seeded).evaluate(1, adapter=_healthy_adapter(),
                                                   now=_now_after(600))
    assert out.verdict == C.COOLDOWN_COMPLETE and out.transitioned_to == C.STATE_NORMAL


# --------------------------------------------------------------- integrity (until manual repair)


async def test_integrity_holds_without_manual_repair(seeded, monkeypatch):
    monkeypatch.setattr(cool_mod, "resolve_session_date", lambda now: ENTRY_SESSION)
    await _seed_cooldown(seeded, origin=C.STATE_INTEGRITY_STOP,
                         trip_cause=C.TRIP_CAUSE_BROKER_STATE_UNCERTAIN, authorized_by=None)
    out = await CooldownEvaluator(seeded).evaluate(1, adapter=_healthy_adapter(), now=_now_after(999))
    assert out.verdict == C.COOLDOWN_HOLD


async def test_integrity_completes_with_durable_manual_repair(seeded, monkeypatch):
    monkeypatch.setattr(cool_mod, "resolve_session_date", lambda now: ENTRY_SESSION)
    await _seed_cooldown(seeded, origin=C.STATE_INTEGRITY_STOP,
                         trip_cause=C.TRIP_CAUSE_BROKER_STATE_UNCERTAIN, authorized_by="2")
    out = await CooldownEvaluator(seeded).evaluate(1, adapter=_healthy_adapter(), now=_now_after(999))
    assert out.verdict == C.COOLDOWN_COMPLETE and out.transitioned_to == C.STATE_NORMAL


# --------------------------------------------------------------- regressions (→ INTEGRITY_STOP)


async def test_active_integrity_alert_regresses(seeded, monkeypatch):
    monkeypatch.setattr(cool_mod, "resolve_session_date", lambda now: ENTRY_SESSION)
    await _seed_cooldown(seeded, trip_cause=C.TRIP_CAUSE_UNKNOWN,
                         trip_evidence=C.TRIP_EVIDENCE_ARTIFACT_CONFIRMED,
                         extra_event_control_type="INTEGRITY", last_sequence_no=4)
    out = await CooldownEvaluator(seeded).evaluate(1, adapter=_healthy_adapter(), now=_now_after(30))
    assert out.verdict == C.COOLDOWN_REGRESSED and out.transitioned_to == C.STATE_INTEGRITY_STOP


async def test_new_trip_after_entry_regresses(seeded, monkeypatch):
    monkeypatch.setattr(cool_mod, "resolve_session_date", lambda now: ENTRY_SESSION)
    await _seed_cooldown(seeded, trip_cause=C.TRIP_CAUSE_UNKNOWN,
                         trip_evidence=C.TRIP_EVIDENCE_ARTIFACT_CONFIRMED,
                         extra_event_control_type="CIRCUIT_BREAKER", last_sequence_no=4)
    out = await CooldownEvaluator(seeded).evaluate(1, adapter=_healthy_adapter(), now=_now_after(30))
    assert out.verdict == C.COOLDOWN_REGRESSED and out.transitioned_to == C.STATE_INTEGRITY_STOP


async def test_missing_cooldown_provenance_fails_closed(seeded, monkeypatch):
    monkeypatch.setattr(cool_mod, "resolve_session_date", lambda now: ENTRY_SESSION)
    # State says RECOVERY_COOLDOWN but there is NO cooldown-entry event → regress, never guess NORMAL.
    async with seeded() as s:
        s.add(RiskLossControlState(account_id=1, state=C.STATE_RECOVERY_COOLDOWN, state_version=4,
                                   last_sequence_no=3, control_version=1, updated_at=ENTRY_AT))
        await s.commit()
    out = await CooldownEvaluator(seeded).evaluate(1, adapter=_healthy_adapter(), now=_now_after(99))
    assert out.verdict == C.COOLDOWN_REGRESSED and out.transitioned_to == C.STATE_INTEGRITY_STOP


# --------------------------------------------------------------- broker reconciliation


async def test_broker_mismatch_holds(seeded, monkeypatch):
    monkeypatch.setattr(cool_mod, "resolve_session_date", lambda now: ENTRY_SESSION)
    await _seed_cooldown(seeded, trip_cause=C.TRIP_CAUSE_UNKNOWN,
                         trip_evidence=C.TRIP_EVIDENCE_ARTIFACT_CONFIRMED)
    async with seeded() as s:  # a local position the broker won't confirm
        s.add(Position(user_id=1, account_id=1, symbol_id=1, qty=D("100"), avg_entry_price=D("10"),
                       side="long", updated_at=ENTRY_AT))
        await s.commit()
    ad = MagicMock()
    ad.get_positions.return_value = []  # broker flat → mismatch
    ad.list_orders.return_value = []
    out = await CooldownEvaluator(seeded).evaluate(1, adapter=ad, now=_now_after(30))
    assert out.verdict == C.COOLDOWN_HOLD


async def test_no_adapter_holds(seeded, monkeypatch):
    monkeypatch.setattr(cool_mod, "resolve_session_date", lambda now: ENTRY_SESSION)
    await _seed_cooldown(seeded, trip_cause=C.TRIP_CAUSE_UNKNOWN,
                         trip_evidence=C.TRIP_EVIDENCE_ARTIFACT_CONFIRMED)
    out = await CooldownEvaluator(seeded).evaluate(1, adapter=None, now=_now_after(30))
    assert out.verdict == C.COOLDOWN_HOLD  # broker health unverifiable → fail closed


# --------------------------------------------------------------- idempotency / isolation / bypass


async def test_not_in_cooldown_is_noop(seeded, monkeypatch):
    monkeypatch.setattr(cool_mod, "resolve_session_date", lambda now: ENTRY_SESSION)
    async with seeded() as s:
        s.add(RiskLossControlState(account_id=1, state=C.STATE_NORMAL, state_version=1,
                                   last_sequence_no=0, control_version=1, updated_at=ENTRY_AT))
        await s.commit()
    out = await CooldownEvaluator(seeded).evaluate(1, adapter=_healthy_adapter(), now=_now_after(30))
    assert out.verdict == CooldownEvaluator.NO_OP and out.transitioned_to is None


async def test_duplicate_evaluations_create_one_transition(seeded, monkeypatch):
    monkeypatch.setattr(cool_mod, "resolve_session_date", lambda now: ENTRY_SESSION)
    await _seed_cooldown(seeded, trip_cause=C.TRIP_CAUSE_UNKNOWN,
                         trip_evidence=C.TRIP_EVIDENCE_ARTIFACT_CONFIRMED)
    ev = CooldownEvaluator(seeded)
    first = await ev.evaluate(1, adapter=_healthy_adapter(), now=_now_after(15))
    second = await ev.evaluate(1, adapter=_healthy_adapter(), now=_now_after(20))
    assert first.verdict == C.COOLDOWN_COMPLETE
    assert second.verdict == CooldownEvaluator.NO_OP  # already NORMAL — no second transition
    async with seeded() as s:  # exactly one COOLDOWN_COMPLETE event
        n = await s.scalar(select(func.count()).select_from(RiskControlEvent).where(
            RiskControlEvent.requested_transition == "COOLDOWN_COMPLETE"))
    assert n == 1


async def test_stale_version_cannot_rearm(seeded, monkeypatch):
    # If the state version advanced under us between read and write, the CAS refuses — no NORMAL.
    monkeypatch.setattr(cool_mod, "resolve_session_date", lambda now: ENTRY_SESSION)
    await _seed_cooldown(seeded, trip_cause=C.TRIP_CAUSE_UNKNOWN,
                         trip_evidence=C.TRIP_EVIDENCE_ARTIFACT_CONFIRMED)
    ev = CooldownEvaluator(seeded)
    real_transition = ev._transition

    async def _bump_then_transition(account_id, trigger, expected_version, verdict, reason):
        async with seeded() as s:  # a concurrent writer advances the version first
            row = await s.scalar(select(RiskLossControlState).where(
                RiskLossControlState.account_id == 1))
            row.state_version = expected_version + 5
            await s.commit()
        return await real_transition(account_id, trigger, expected_version, verdict, reason)

    monkeypatch.setattr(ev, "_transition", _bump_then_transition)
    out = await ev.evaluate(1, adapter=_healthy_adapter(), now=_now_after(15))
    assert out.transitioned_to is None  # not applied — never a silent NORMAL
    assert (await _state(seeded)).state == C.STATE_RECOVERY_COOLDOWN


async def test_account_isolation_in_evaluate_all(seeded, monkeypatch):
    monkeypatch.setattr(cool_mod, "resolve_session_date", lambda now: ENTRY_SESSION)
    await _seed_cooldown(seeded, trip_cause=C.TRIP_CAUSE_UNKNOWN,
                         trip_evidence=C.TRIP_EVIDENCE_ARTIFACT_CONFIRMED)
    async with seeded() as s:  # a second account also in cooldown but with NO provenance
        s.add(User(id=2, email="b@t"))
        s.add(Account(id=2, user_id=2, broker="alpaca", mode=AccountMode.paper, label="P2"))
        s.add(RiskLossControlState(account_id=2, state=C.STATE_RECOVERY_COOLDOWN, state_version=1,
                                   last_sequence_no=0, control_version=1, updated_at=ENTRY_AT))
        await s.commit()
    results = await CooldownEvaluator(seeded).evaluate_all(adapter=_healthy_adapter(),
                                                           now=_now_after(15))
    by_acct = {r.account_id: r.verdict for r in results}
    assert by_acct[1] == C.COOLDOWN_COMPLETE          # acct 1 advances
    assert by_acct[2] == C.COOLDOWN_REGRESSED         # acct 2 fails closed, independently


async def test_evaluator_only_transitions_via_service(seeded, monkeypatch):
    # No path reaches NORMAL without a COOLDOWN_COMPLETE transition committed by the service.
    monkeypatch.setattr(cool_mod, "resolve_session_date", lambda now: ENTRY_SESSION)
    await _seed_cooldown(seeded, trip_cause=C.TRIP_CAUSE_UNKNOWN,
                         trip_evidence=C.TRIP_EVIDENCE_ARTIFACT_CONFIRMED)
    out = await CooldownEvaluator(seeded).evaluate(1, adapter=_healthy_adapter(), now=_now_after(15))
    async with seeded() as s:
        row = await s.scalar(select(RiskLossControlState).where(
            RiskLossControlState.account_id == 1))
        ev = await s.scalar(select(RiskControlEvent).where(
            RiskControlEvent.requested_transition == "COOLDOWN_COMPLETE"))
    assert out.transitioned_to == C.STATE_NORMAL and row.state == C.STATE_NORMAL
    assert ev is not None and ev.from_state == C.STATE_RECOVERY_COOLDOWN  # a real service event


async def test_internal_error_never_advances(seeded, monkeypatch):
    monkeypatch.setattr(cool_mod, "resolve_session_date", lambda now: ENTRY_SESSION)
    await _seed_cooldown(seeded, trip_cause=C.TRIP_CAUSE_UNKNOWN,
                         trip_evidence=C.TRIP_EVIDENCE_ARTIFACT_CONFIRMED)
    ev = CooldownEvaluator(seeded)

    async def _boom(*a, **k):
        raise RuntimeError("evidence gather failed")

    monkeypatch.setattr(ev, "_evaluate", _boom)
    out = await ev.evaluate(1, adapter=_healthy_adapter(), now=_now_after(15))
    assert out.verdict == CooldownEvaluator.NO_OP and out.transitioned_to is None
    assert (await _state(seeded)).state == C.STATE_RECOVERY_COOLDOWN


async def test_no_bound_preflight_fails_closed(seeded, monkeypatch):
    # The cooldown-entry event exists, but no PASSED preflight is bound to it → regress, never guess.
    monkeypatch.setattr(cool_mod, "resolve_session_date", lambda now: ENTRY_SESSION)
    await _seed_cooldown(seeded, trip_evidence=C.TRIP_EVIDENCE_ARTIFACT_CONFIRMED,
                         create_preflight=False)
    out = await CooldownEvaluator(seeded).evaluate(1, adapter=_healthy_adapter(), now=_now_after(30))
    assert out.verdict == C.COOLDOWN_REGRESSED and out.transitioned_to == C.STATE_INTEGRITY_STOP


async def test_invalid_cooldown_entry_shape_fails_closed(seeded, monkeypatch):
    # The latest RECOVERY_COOLDOWN event did not come from RECOVERY_PREFLIGHT via PREFLIGHT_PASS —
    # unusable provenance → regress.
    monkeypatch.setattr(cool_mod, "resolve_session_date", lambda now: ENTRY_SESSION)
    async with seeded() as s:
        s.add(RiskLossControlState(account_id=1, state=C.STATE_RECOVERY_COOLDOWN, state_version=4,
                                   last_sequence_no=3, control_version=1, updated_at=ENTRY_AT))
        s.add(RiskControlEvent(account_id=1, sequence_no=3, control_type="RECOVERY",
                               from_state=C.STATE_NORMAL, to_state=C.STATE_RECOVERY_COOLDOWN,
                               requested_transition="SOMETHING_ELSE", initiator_type="SYSTEM",
                               control_version=1, created_at=ENTRY_AT))
        await s.commit()
    out = await CooldownEvaluator(seeded).evaluate(1, adapter=_healthy_adapter(), now=_now_after(30))
    assert out.verdict == C.COOLDOWN_REGRESSED and out.transitioned_to == C.STATE_INTEGRITY_STOP


async def test_null_origin_and_null_session_date_still_evaluates(seeded, monkeypatch):
    # A preflight with no durable origin and an entry with no session date: evidence lookup and
    # new-session both resolve to their null/False paths; an integrity-class lock with a durable
    # manual-repair approval still completes cleanly.
    monkeypatch.setattr(cool_mod, "resolve_session_date", lambda now: ENTRY_SESSION)
    await _seed_cooldown(seeded, trip_cause=C.TRIP_CAUSE_UNKNOWN, preflight_origin=None,
                         entry_session_date=None, authorized_by="2")
    out = await CooldownEvaluator(seeded).evaluate(1, adapter=_healthy_adapter(), now=_now_after(30))
    assert out.verdict == C.COOLDOWN_COMPLETE and out.transitioned_to == C.STATE_NORMAL
