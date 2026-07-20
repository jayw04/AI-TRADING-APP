"""ADR 0043 PR4 — the LossControlGate (unit level).

Deterministic: state inserted directly, verified-reduction passed in. Pins the per-order outcome,
the precedence-driven refuse/permit, missing-state fail-closed, divergence classification,
multi-account isolation, and the provenance shape.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from app.config import LossControlMode
from app.db.models.account import Account, AccountMode
from app.db.models.risk_loss_control_state import RiskLossControlState
from app.db.models.user import User
from app.risk.loss_control import constants as C
from app.risk.loss_control.gate import (
    DIVERGENCE_ADR_LOOSER,
    DIVERGENCE_ADR_STRICTER,
    DIVERGENCE_ERROR,
    DIVERGENCE_INCOMPARABLE,
    DIVERGENCE_MATCH,
    LossControlGate,
    fail_closed_decision,
)

NOW = datetime(2026, 7, 20, 15, 0, tzinfo=UTC)


@pytest.fixture
async def acct(session_factory):
    async with session_factory() as s:
        s.add(User(id=1, email="j@t"))
        s.add(User(id=2, email="k@t"))
        s.add(Account(id=1, user_id=1, broker="alpaca", mode=AccountMode.paper, label="P1"))
        s.add(Account(id=2, user_id=2, broker="alpaca", mode=AccountMode.paper, label="P2"))
        await s.commit()
    return 1


async def _set_state(session_factory, account_id, state, *, version=0):
    async with session_factory() as s:
        s.add(RiskLossControlState(
            account_id=account_id, state=state, state_version=version,
            last_sequence_no=version, control_version=1, updated_at=NOW,
        ))
        await s.commit()


async def _gate(session_factory, account_id=1, *, mode=LossControlMode.ENFORCE,
                verified_reduction=None, legacy_permits=True, legacy_outcome="ALLOW"):
    async with session_factory() as s:
        return await LossControlGate(s, mode).evaluate(
            account_id=account_id, verified_reduction=verified_reduction,
            legacy_outcome=legacy_outcome, legacy_permits=legacy_permits,
        )


# ------------------------------------------------------------ per-state outcome


async def test_normal_permits(session_factory, acct):
    await _set_state(session_factory, 1, C.STATE_NORMAL)
    d = await _gate(session_factory)
    assert d.permits_order is True and d.outcome == C.OUTCOME_ALLOW
    assert d.divergence == DIVERGENCE_MATCH  # legacy also permitted


async def test_reduction_only_permits_verified_reduction(session_factory, acct):
    await _set_state(session_factory, 1, C.STATE_REDUCTION_ONLY_DAILY_LOSS)
    d = await _gate(session_factory, verified_reduction=True)
    assert d.permits_order is True and d.outcome == C.OUTCOME_ALLOW_REDUCTION_ONLY


async def test_reduction_only_refuses_non_reduction(session_factory, acct):
    await _set_state(session_factory, 1, C.STATE_REDUCTION_ONLY_DAILY_LOSS)
    d = await _gate(session_factory, verified_reduction=False)  # risk-neutral / risk-increasing
    assert d.permits_order is False and d.outcome == C.OUTCOME_REFUSE
    assert d.reason_code == "LOSS_CONTROL_STOP"
    assert d.divergence == DIVERGENCE_ADR_STRICTER  # ADR denies, legacy would permit


async def test_integrity_stop_refuses_even_a_reduction(session_factory, acct):
    # INTEGRITY_STOP dominates the ladder — a verified reduction cannot be verified under unknown
    # state, so it is refused (§D2). This is the precedence contract at the gate.
    await _set_state(session_factory, 1, C.STATE_INTEGRITY_STOP)
    d = await _gate(session_factory, verified_reduction=True)
    assert d.permits_order is False and d.outcome == C.OUTCOME_INTEGRITY_STOP


# ------------------------------------------------------------ missing state fails closed


async def test_missing_state_fails_closed(session_factory, acct):
    d = await _gate(session_factory)  # no state row for account 1
    assert d.state_known is False
    assert d.outcome == C.OUTCOME_INTEGRITY_STOP and d.permits_order is False


# ------------------------------------------------------------ multi-account isolation


async def test_multi_account_isolation(session_factory, acct):
    await _set_state(session_factory, 1, C.STATE_NORMAL)
    await _set_state(session_factory, 2, C.STATE_INTEGRITY_STOP)
    d1 = await _gate(session_factory, account_id=1)
    d2 = await _gate(session_factory, account_id=2, verified_reduction=True)
    assert d1.state == C.STATE_NORMAL and d1.permits_order is True
    assert d2.state == C.STATE_INTEGRITY_STOP and d2.permits_order is False


# ------------------------------------------------------------ divergence classification


async def test_divergence_looser_when_adr_permits_and_legacy_denies(session_factory, acct):
    await _set_state(session_factory, 1, C.STATE_NORMAL)
    d = await _gate(session_factory, legacy_permits=False, legacy_outcome="REFUSE")
    assert d.permits_order is True and d.divergence == DIVERGENCE_ADR_LOOSER


async def test_divergence_incomparable_when_legacy_unknown(session_factory, acct):
    await _set_state(session_factory, 1, C.STATE_NORMAL)
    d = await _gate(session_factory, legacy_permits=None, legacy_outcome=None)
    assert d.divergence == DIVERGENCE_INCOMPARABLE


# ------------------------------------------------------------ shadow non-authority + fail-closed helper


async def test_shadow_is_non_authoritative(session_factory, acct):
    await _set_state(session_factory, 1, C.STATE_INTEGRITY_STOP)
    d = await _gate(session_factory, mode=LossControlMode.SHADOW)
    assert d.authoritative is False  # SHADOW never authoritative — engine keeps legacy
    assert d.permits_order is False  # still computes the outcome, just not authoritative


def test_fail_closed_decision_by_mode():
    s = fail_closed_decision(LossControlMode.SHADOW, "ALLOW", True)
    assert s.authoritative is False and s.permits_order is False and s.divergence == DIVERGENCE_ERROR
    e = fail_closed_decision(LossControlMode.ENFORCE, "ALLOW", True)
    assert e.authoritative is True and e.reason_code == "LOSS_CONTROL_STOP"


# ------------------------------------------------------------ provenance


async def test_provenance_carries_state_version_outcome_mode_reduction(session_factory, acct):
    await _set_state(session_factory, 1, C.STATE_REDUCTION_ONLY_DAILY_LOSS, version=3)
    d = await _gate(session_factory, verified_reduction=False)
    p = d.provenance()
    assert p["loss_control_state"] == "REDUCTION_ONLY_DAILY_LOSS"
    assert p["loss_control_state_version"] == "3"
    assert p["loss_control_outcome"] == "REFUSE"
    assert p["verified_reduction"] == "False"
    assert p["loss_control_mode"] == "ENFORCE"
    assert p["reason_code"] == "LOSS_CONTROL_STOP"
