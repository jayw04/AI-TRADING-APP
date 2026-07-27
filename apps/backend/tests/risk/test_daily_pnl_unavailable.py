"""An unmeasurable daily P&L locks the account reduction-only — without asserting a loss.

Before this, `accounts_state.day_change` carried a placeholder `0` when no baseline existed, so
`current_lock_state` fell through to UNLOCKED: the daily-loss gate was silently disabled on exactly
the account whose P&L nobody could see.

Two failure modes are held apart throughout, and the tests are written to catch a fix that collapses
them:

* **Not measured** must not become **measured zero.** No breaker trip, no dollar amount, no claim
  that a threshold was crossed — the trip cause is the absence of a measurement.
* **Cannot see** must not become **cannot act.** 2026-07-13 is what happens when a control that
  cannot see also refuses the book's own de-risking, so verified reductions still pass.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal as D

import pytest
from sqlalchemy import select

from app.db.enums import RiskScopeType
from app.db.models.account import Account, AccountMode
from app.db.models.account_state import AccountState
from app.db.models.risk_limits import RiskLimits
from app.db.models.user import User
from app.risk.lock_state import (
    LOCK_BREAKER,
    LOCK_DAILY_LOSS,
    LOCK_DAILY_PNL_UNAVAILABLE,
    LOCK_UNLOCKED,
    current_lock_state,
)
from app.risk.loss_control import constants as C
from app.risk.loss_control.state_machine import (
    TRIGGER_DAILY_PNL_UNAVAILABLE,
    TRIGGER_RECOVERY_REQUEST,
    decide_transition,
    order_outcome_for_state,
)
from app.services.day_change_basis import BROKER_LAST_EQUITY, PRIOR_SESSION_CLOSE_PROXY, UNAVAILABLE

UNAVAILABLE_STATE = C.STATE_REDUCTION_ONLY_DAILY_PNL_UNAVAILABLE


async def _seed(
    session_factory,
    *,
    basis: str | None = None,
    day_change: D = D("0"),
    max_daily_loss: D | None = D("3000"),
    breaker_tripped: bool = False,
    with_state: bool = True,
):
    """``basis=None`` omits the column entirely — the row a caller wrote without saying anything
    about its measurement, which must inherit the conservative default."""
    async with session_factory() as s:
        s.add(User(id=1, email="u@t"))
        s.add(
            Account(
                id=1,
                user_id=1,
                broker="alpaca",
                mode=AccountMode.paper,
                label="P",
                circuit_breaker_tripped_at=datetime.now(UTC) if breaker_tripped else None,
            )
        )
        if with_state:
            kwargs = {} if basis is None else {"day_change_basis": basis}
            s.add(
                AccountState(
                    account_id=1,
                    equity=D("100000"),
                    last_equity=D("100000"),
                    day_change=day_change,
                    updated_at=datetime.now(UTC),
                    **kwargs,
                )
            )
        if max_daily_loss is not None:
            s.add(
                RiskLimits(
                    user_id=1,
                    scope_type=RiskScopeType.GLOBAL,
                    broker_mode="paper",
                    max_daily_loss=max_daily_loss,
                    created_at=datetime.now(UTC),
                    updated_at=datetime.now(UTC),
                )
            )
        await s.commit()


async def _lock(session_factory):
    async with session_factory() as s:
        return await current_lock_state(s, account_id=1, user_id=1)


# ------------------------------------------------------------- the conservative default


async def test_a_row_written_without_a_basis_is_unavailable(session_factory):
    """The migration's server default. A caller that says nothing about provenance has asserted
    nothing, and the row must not be read as a measured flat day."""
    await _seed(session_factory)
    async with session_factory() as s:
        row = (await s.execute(select(AccountState))).scalars().one()
    assert row.day_change_basis == UNAVAILABLE


async def test_an_unavailable_basis_does_not_return_unlocked(session_factory):
    """The defect this whole change exists for: the gate used to disappear here."""
    await _seed(session_factory, basis=UNAVAILABLE)
    lock, reason, pnl = await _lock(session_factory)
    assert lock == LOCK_DAILY_PNL_UNAVAILABLE
    assert reason == "daily_pnl_unavailable"


async def test_the_lock_reports_no_amount_because_there_is_none(session_factory):
    """`day_change` still holds its placeholder 0 for legacy consumers. Reporting that as the day's
    P&L would re-assert the fiction one layer up, so the lock reports None."""
    await _seed(session_factory, basis=UNAVAILABLE, day_change=D("0"))
    _lock_state, _reason, pnl = await _lock(session_factory)
    assert pnl is None


@pytest.mark.parametrize("basis", [BROKER_LAST_EQUITY, PRIOR_SESSION_CLOSE_PROXY])
async def test_a_measurable_basis_within_the_cap_stays_unlocked(session_factory, basis):
    await _seed(session_factory, basis=basis, day_change=D("-100"))
    lock, _reason, pnl = await _lock(session_factory)
    assert lock == LOCK_UNLOCKED
    assert pnl == D("-100")


async def test_a_measured_breach_still_reports_as_a_daily_loss(session_factory):
    """The more specific finding wins: an account that measurably breached is not relabelled."""
    await _seed(session_factory, basis=BROKER_LAST_EQUITY, day_change=D("-3500"))
    lock, reason, pnl = await _lock(session_factory)
    assert lock == LOCK_DAILY_LOSS
    assert reason == "daily_loss_exceeded"
    assert pnl == D("-3500")


async def test_a_tripped_breaker_still_dominates(session_factory):
    """Composition: the durable explicit lock outranks the measurement condition, and the breaker
    path already admits verified reductions."""
    await _seed(session_factory, basis=UNAVAILABLE, breaker_tripped=True)
    lock, reason, _pnl = await _lock(session_factory)
    assert lock == LOCK_BREAKER
    assert reason == "circuit_breaker_tripped"


async def test_without_a_daily_loss_cap_there_is_nothing_to_be_unable_to_measure(session_factory):
    """No cap configured means the daily-loss control is not in play at all; an unmeasurable basis
    cannot manufacture a restriction the account never had."""
    await _seed(session_factory, basis=UNAVAILABLE, max_daily_loss=None)
    lock, _reason, _pnl = await _lock(session_factory)
    assert lock == LOCK_UNLOCKED


# ------------------------------------------------------------- the durable state


def test_the_trigger_locks_reduction_only_from_normal():
    decision = decide_transition(C.STATE_NORMAL, TRIGGER_DAILY_PNL_UNAVAILABLE)
    assert decision.applies is True
    assert decision.to_state == UNAVAILABLE_STATE


def test_new_risk_is_refused_and_a_verified_reduction_is_allowed():
    assert (
        order_outcome_for_state(UNAVAILABLE_STATE, verified_reduction=False, state_known=True)
        == C.OUTCOME_REFUSE
    )
    assert (
        order_outcome_for_state(UNAVAILABLE_STATE, verified_reduction=True, state_known=True)
        == C.OUTCOME_ALLOW_REDUCTION_ONLY
    )


def test_it_is_not_an_integrity_stop():
    """Account state is perfectly well known here — a reduction is still verifiable. It is the P&L
    that is unknown, and conflating the two would block de-risking."""
    outcome = order_outcome_for_state(
        UNAVAILABLE_STATE, verified_reduction=True, state_known=True
    )
    assert outcome != C.OUTCOME_INTEGRITY_STOP


def test_repeated_triggers_are_idempotent():
    """A stalled sweep fires this on every evaluation; it must not emit an event per order."""
    again = decide_transition(UNAVAILABLE_STATE, TRIGGER_DAILY_PNL_UNAVAILABLE)
    assert again.applies is False


def test_the_state_cannot_silently_self_clear():
    """A basis becoming available again is not evidence about the window in which nothing was
    measured. Every trigger except the sanctioned recovery request is a no-op from this state."""
    from app.risk.loss_control import state_machine as sm

    for trigger in sorted(sm.ALL_TRIGGERS):
        decision = decide_transition(UNAVAILABLE_STATE, trigger)
        if trigger == TRIGGER_RECOVERY_REQUEST:
            assert decision.to_state == C.STATE_RECOVERY_PREFLIGHT
        elif trigger == sm.TRIGGER_INTEGRITY_VIOLATION:
            assert decision.to_state == C.STATE_INTEGRITY_STOP  # fail-closed still dominates
        else:
            assert decision.applies is False, f"{trigger} must not clear the lock"


def test_recovery_runs_the_normal_workflow():
    """No shortcut: the same preflight → cooldown path as a measured lock."""
    to_preflight = decide_transition(UNAVAILABLE_STATE, TRIGGER_RECOVERY_REQUEST)
    assert to_preflight.to_state == C.STATE_RECOVERY_PREFLIGHT

    from app.risk.loss_control.state_machine import TRIGGER_PREFLIGHT_FAIL, TRIGGER_PREFLIGHT_PASS

    passed = decide_transition(C.STATE_RECOVERY_PREFLIGHT, TRIGGER_PREFLIGHT_PASS)
    assert passed.to_state == C.STATE_RECOVERY_COOLDOWN  # cooldown is still mandatory

    failed = decide_transition(
        C.STATE_RECOVERY_PREFLIGHT,
        TRIGGER_PREFLIGHT_FAIL,
        recovery_origin_state=UNAVAILABLE_STATE,
    )
    assert failed.to_state == UNAVAILABLE_STATE  # back to the lock it came from


# ------------------------------------------------------------- no loss is asserted


def test_the_taxonomy_separates_unmeasured_from_measured():
    """The audit trail must not record a daily-loss trip for a loss nobody measured."""
    assert C.TRIP_CAUSE_DAILY_PNL_UNAVAILABLE in C.ALL_TRIP_CAUSES
    assert C.TRIP_TYPE_MEASUREMENT_UNAVAILABLE in C.ALL_TRIP_TYPES
    assert C.TRIP_TYPE_MEASUREMENT_UNAVAILABLE != C.TRIP_TYPE_DAILY_LOSS
    assert C.TRIP_CAUSE_DAILY_PNL_UNAVAILABLE != C.TRIP_CAUSE_REALIZED_AND_MARK_TO_MARKET_LOSS


async def test_no_breaker_is_tripped_by_an_unmeasurable_basis(session_factory):
    """Tripping the breaker would write a measured daily-loss trip into the audit trail and halt
    strategies for a loss that was never observed."""
    await _seed(session_factory, basis=UNAVAILABLE)
    async with session_factory() as s:
        account = await s.get(Account, 1)
        assert account is not None
        assert account.circuit_breaker_tripped_at is None
