"""ADR 0043 §D1.1/§D1.2 — the loss-control persistence service.

Pins: race-safe bootstrap, an applied transition (state + version + sequence advance atomically
with an appended event), the three EXPLICIT non-applied outcomes (no-change / stale / conflict),
the compare-and-swap mechanics, and monotonic per-account sequencing.
"""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import func, select

from app.db.models.account import Account, AccountMode
from app.db.models.risk_control_event import RiskControlEvent
from app.db.models.risk_loss_control_state import RiskLossControlState
from app.db.models.user import User
from app.risk.loss_control import constants as C
from app.risk.loss_control import service as svc_mod
from app.risk.loss_control import state_machine as sm
from app.risk.loss_control.service import (
    APPLIED,
    NOT_APPLIED_CONFLICT,
    NOT_APPLIED_NO_CHANGE,
    NOT_APPLIED_STALE,
    LossControlService,
    TransitionContext,
)

D = Decimal


@pytest.fixture
async def acct(session_factory):
    async with session_factory() as s:
        s.add(User(id=1, email="jay@test"))
        s.add(Account(id=1, user_id=1, broker="alpaca", mode=AccountMode.paper, label="P"))
        await s.commit()
    return 1


async def _event_count(session_factory, account_id: int) -> int:
    async with session_factory() as s:
        return await s.scalar(
            select(func.count())
            .select_from(RiskControlEvent)
            .where(RiskControlEvent.account_id == account_id)
        )


# --------------------------------------------------------------- bootstrap


async def test_get_state_row_bootstraps_normal(session_factory, acct):
    async with session_factory() as s:
        row = await LossControlService(s).get_state_row(acct)
    assert row.state == C.STATE_NORMAL
    assert row.state_version == 0
    assert row.last_sequence_no == 0
    assert row.control_version == C.LOSS_CONTROL_STATE_VERSION


async def test_bootstrap_is_idempotent(session_factory, acct):
    async with session_factory() as s:
        svc = LossControlService(s)
        await svc.get_state_row(acct)
        await svc.get_state_row(acct)  # second call must not create a second row
    async with session_factory() as s:
        n = await s.scalar(
            select(func.count())
            .select_from(RiskLossControlState)
            .where(RiskLossControlState.account_id == acct)
        )
    assert n == 1


# --------------------------------------------------------------- applied transition


async def test_apply_advances_state_version_sequence_and_writes_event(session_factory, acct):
    async with session_factory() as s:
        result = await LossControlService(s).request_transition(
            account_id=acct,
            trigger=sm.TRIGGER_DAILY_LOSS_BREACH,
            context=TransitionContext(
                trip_type=C.TRIP_TYPE_DAILY_LOSS,
                trip_cause=C.TRIP_CAUSE_REALIZED_AND_MARK_TO_MARKET_LOSS,
                trip_evidence_status=C.TRIP_EVIDENCE_CONFIRMED,
                trigger_value=D("-3200.00"),
                threshold_value=D("-3000.00"),
                session_date="2026-07-20",
            ),
        )
    assert result.outcome == APPLIED
    assert result.applied
    assert result.state == C.STATE_REDUCTION_ONLY_DAILY_LOSS
    assert result.state_version == 1
    assert result.sequence_no == 1
    assert result.event_id is not None

    async with session_factory() as s:
        row = await s.scalar(
            select(RiskLossControlState).where(RiskLossControlState.account_id == acct)
        )
        ev = await s.scalar(select(RiskControlEvent).where(RiskControlEvent.id == result.event_id))
    assert row.state == C.STATE_REDUCTION_ONLY_DAILY_LOSS
    assert row.state_version == 1
    assert row.last_sequence_no == 1
    assert ev.from_state == C.STATE_NORMAL
    assert ev.to_state == C.STATE_REDUCTION_ONLY_DAILY_LOSS
    assert ev.sequence_no == 1
    assert ev.control_type == "DAILY_LOSS"
    assert ev.requested_transition == sm.TRIGGER_DAILY_LOSS_BREACH
    assert ev.trip_cause == C.TRIP_CAUSE_REALIZED_AND_MARK_TO_MARKET_LOSS
    assert ev.trigger_value == D("-3200.00")
    assert ev.control_version == C.LOSS_CONTROL_STATE_VERSION


async def test_sequence_is_monotonic_across_transitions(session_factory, acct):
    seqs = []
    async with session_factory() as s:
        svc = LossControlService(s)
        r1 = await svc.request_transition(account_id=acct, trigger=sm.TRIGGER_DAILY_LOSS_BREACH)
        r2 = await svc.request_transition(account_id=acct, trigger=sm.TRIGGER_INTEGRITY_VIOLATION)
        r3 = await svc.request_transition(account_id=acct, trigger=sm.TRIGGER_RECOVERY_REQUEST)
        seqs = [r1.sequence_no, r2.sequence_no, r3.sequence_no]
    assert seqs == [1, 2, 3]
    assert [r.state for r in (r1, r2, r3)] == [
        C.STATE_REDUCTION_ONLY_DAILY_LOSS,
        C.STATE_INTEGRITY_STOP,
        C.STATE_RECOVERY_PREFLIGHT,
    ]
    # every event's sequence is unique and dense
    async with session_factory() as s:
        rows = (
            await s.execute(
                select(RiskControlEvent.sequence_no)
                .where(RiskControlEvent.account_id == acct)
                .order_by(RiskControlEvent.sequence_no)
            )
        ).scalars().all()
    assert list(rows) == [1, 2, 3]


# --------------------------------------------------------------- explicit non-applied outcomes


async def test_no_change_when_trigger_has_no_edge(session_factory, acct):
    async with session_factory() as s:
        result = await LossControlService(s).request_transition(
            account_id=acct, trigger=sm.TRIGGER_RECOVERY_REQUEST  # no edge from NORMAL
        )
    assert result.outcome == NOT_APPLIED_NO_CHANGE
    assert not result.applied
    assert result.state == C.STATE_NORMAL
    assert result.sequence_no is None
    assert await _event_count(session_factory, acct) == 0


async def test_stale_expected_version_is_rejected(session_factory, acct):
    async with session_factory() as s:
        svc = LossControlService(s)
        await svc.get_state_row(acct)  # version 0
        result = await svc.request_transition(
            account_id=acct,
            trigger=sm.TRIGGER_DAILY_LOSS_BREACH,
            expected_state_version=99,  # stale
        )
    assert result.outcome == NOT_APPLIED_STALE
    assert result.state_version == 0
    assert await _event_count(session_factory, acct) == 0


async def test_expected_version_replay_is_stale_after_first_apply(session_factory, acct):
    async with session_factory() as s:
        svc = LossControlService(s)
        first = await svc.request_transition(
            account_id=acct, trigger=sm.TRIGGER_DAILY_LOSS_BREACH, expected_state_version=0
        )
        assert first.applied
        # Replaying the SAME request (still naming version 0) is now stale — idempotent, not double.
        replay = await svc.request_transition(
            account_id=acct, trigger=sm.TRIGGER_DAILY_LOSS_BREACH, expected_state_version=0
        )
    assert replay.outcome == NOT_APPLIED_STALE
    assert await _event_count(session_factory, acct) == 1


async def test_conflict_when_cas_loses_writes_no_event(session_factory, acct, monkeypatch):
    async with session_factory() as s:
        svc = LossControlService(s)
        await svc.get_state_row(acct)
        # Simulate losing the compare-and-swap to a concurrent writer: the UPDATE hits 0 rows.
        svc._cas_advance = AsyncMock(return_value=0)
        result = await svc.request_transition(
            account_id=acct, trigger=sm.TRIGGER_DAILY_LOSS_BREACH
        )
    assert result.outcome == NOT_APPLIED_CONFLICT
    assert not result.applied
    assert await _event_count(session_factory, acct) == 0


# --------------------------------------------------------------- CAS mechanics


async def test_cas_advance_updates_one_row_on_match_zero_on_mismatch(session_factory, acct):
    async with session_factory() as s:
        svc = LossControlService(s)
        await svc.get_state_row(acct)  # version 0
        assert (
            await svc._cas_advance(
                account_id=acct, expected_version=99, to_state=C.STATE_INTEGRITY_STOP
            )
            == 0
        )
        assert (
            await svc._cas_advance(
                account_id=acct, expected_version=0, to_state=C.STATE_INTEGRITY_STOP
            )
            == 1
        )
        await s.commit()
    async with session_factory() as s:
        row = await s.scalar(
            select(RiskLossControlState).where(RiskLossControlState.account_id == acct)
        )
    assert row.state == C.STATE_INTEGRITY_STOP
    assert row.state_version == 1
    assert row.last_sequence_no == 1  # the sequence increment rode inside the same CAS


def test_service_exposes_explicit_outcome_constants():
    # The four outcomes are distinct strings — callers switch on them, never on truthiness.
    assert len({APPLIED, NOT_APPLIED_STALE, NOT_APPLIED_CONFLICT, NOT_APPLIED_NO_CHANGE}) == 4
    assert svc_mod.APPLIED == "APPLIED"
