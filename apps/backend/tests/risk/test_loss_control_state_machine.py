"""ADR 0043 §D1 — the PURE loss-control state machine.

No DB, no clock. Exhaustively pins the transition graph, the normative precedence ladder, and the
per-state order outcome (including the §D2 epistemic qualifier).
"""

from __future__ import annotations

import pytest

from app.risk.loss_control import constants as C
from app.risk.loss_control import state_machine as sm

# --------------------------------------------------------------- transition graph (applies)


@pytest.mark.parametrize(
    ("state", "trigger", "to_state", "control"),
    [
        (C.STATE_NORMAL, sm.TRIGGER_DAILY_LOSS_BREACH, C.STATE_REDUCTION_ONLY_DAILY_LOSS, "DAILY_LOSS"),
        (C.STATE_NORMAL, sm.TRIGGER_BREAKER_TRIP, C.STATE_REDUCTION_ONLY_BREAKER, "CIRCUIT_BREAKER"),
        (C.STATE_NORMAL, sm.TRIGGER_INTEGRITY_VIOLATION, C.STATE_INTEGRITY_STOP, "INTEGRITY"),
        (C.STATE_REDUCTION_ONLY_DAILY_LOSS, sm.TRIGGER_INTEGRITY_VIOLATION, C.STATE_INTEGRITY_STOP, "INTEGRITY"),
        (C.STATE_REDUCTION_ONLY_BREAKER, sm.TRIGGER_INTEGRITY_VIOLATION, C.STATE_INTEGRITY_STOP, "INTEGRITY"),
        (C.STATE_REDUCTION_ONLY_DAILY_LOSS, sm.TRIGGER_RECOVERY_REQUEST, C.STATE_RECOVERY_PREFLIGHT, "RECOVERY"),
        (C.STATE_REDUCTION_ONLY_BREAKER, sm.TRIGGER_RECOVERY_REQUEST, C.STATE_RECOVERY_PREFLIGHT, "RECOVERY"),
        (C.STATE_INTEGRITY_STOP, sm.TRIGGER_RECOVERY_REQUEST, C.STATE_RECOVERY_PREFLIGHT, "RECOVERY"),
        (C.STATE_RECOVERY_PREFLIGHT, sm.TRIGGER_PREFLIGHT_PASS, C.STATE_RECOVERY_COOLDOWN, "RECOVERY"),
        (C.STATE_RECOVERY_COOLDOWN, sm.TRIGGER_COOLDOWN_COMPLETE, C.STATE_NORMAL, "RECOVERY"),
        (C.STATE_RECOVERY_COOLDOWN, sm.TRIGGER_HEALTH_REGRESSED, C.STATE_INTEGRITY_STOP, "INTEGRITY"),
    ],
)
def test_transitions_that_apply(state, trigger, to_state, control):
    d = sm.decide_transition(state, trigger)
    assert d.applies is True
    assert d.to_state == to_state
    assert d.control_type == control


def test_preflight_fail_returns_to_prior_lock_when_known():
    d = sm.decide_transition(
        C.STATE_RECOVERY_PREFLIGHT,
        sm.TRIGGER_PREFLIGHT_FAIL,
        prior_lock_state=C.STATE_REDUCTION_ONLY_DAILY_LOSS,
    )
    assert d.applies and d.to_state == C.STATE_REDUCTION_ONLY_DAILY_LOSS


def test_preflight_fail_fails_closed_when_prior_lock_unknown():
    d = sm.decide_transition(C.STATE_RECOVERY_PREFLIGHT, sm.TRIGGER_PREFLIGHT_FAIL)
    assert d.applies and d.to_state == C.STATE_INTEGRITY_STOP


# --------------------------------------------------------------- transition graph (no-ops)


@pytest.mark.parametrize(
    ("state", "trigger"),
    [
        (C.STATE_NORMAL, sm.TRIGGER_RECOVERY_REQUEST),  # no edge
        (C.STATE_NORMAL, sm.TRIGGER_PREFLIGHT_PASS),
        (C.STATE_INTEGRITY_STOP, sm.TRIGGER_INTEGRITY_VIOLATION),  # already stopped
        (C.STATE_REDUCTION_ONLY_DAILY_LOSS, sm.TRIGGER_DAILY_LOSS_BREACH),  # already locked
        (C.STATE_REDUCTION_ONLY_BREAKER, sm.TRIGGER_BREAKER_TRIP),
        (C.STATE_INTEGRITY_STOP, sm.TRIGGER_COOLDOWN_COMPLETE),
        (C.STATE_RECOVERY_PREFLIGHT, sm.TRIGGER_DAILY_LOSS_BREACH),
        (C.STATE_RECOVERY_COOLDOWN, sm.TRIGGER_RECOVERY_REQUEST),
    ],
)
def test_transitions_that_are_no_ops(state, trigger):
    d = sm.decide_transition(state, trigger)
    assert d.applies is False
    assert d.to_state is None


def test_unknown_trigger_is_no_op():
    assert sm.decide_transition(C.STATE_NORMAL, "WAT").applies is False


def test_unknown_state_is_no_op():
    assert sm.decide_transition("WAT", sm.TRIGGER_DAILY_LOSS_BREACH).applies is False


def test_every_state_and_trigger_pair_is_total_and_deterministic():
    # Never raises, always returns a decision; identical inputs give identical outputs.
    for state in C.ALL_STATES:
        for trigger in sm.ALL_TRIGGERS:
            a = sm.decide_transition(state, trigger)
            b = sm.decide_transition(state, trigger)
            assert a == b
            if a.applies:
                assert a.to_state in C.ALL_STATES


# --------------------------------------------------------------- order outcome per state (§D1/§D2)


def test_unknown_state_forces_integrity_stop_even_when_reducing():
    # §D2: a reduction cannot be verified under unknown state → INTEGRITY_STOP, never a guessed pass.
    assert (
        sm.order_outcome_for_state(
            C.STATE_REDUCTION_ONLY_DAILY_LOSS, verified_reduction=True, state_known=False
        )
        == C.OUTCOME_INTEGRITY_STOP
    )


def test_normal_allows():
    assert (
        sm.order_outcome_for_state(C.STATE_NORMAL, verified_reduction=False, state_known=True)
        == C.OUTCOME_ALLOW
    )


def test_integrity_stop_blocks_everything():
    assert (
        sm.order_outcome_for_state(C.STATE_INTEGRITY_STOP, verified_reduction=True, state_known=True)
        == C.OUTCOME_INTEGRITY_STOP
    )


@pytest.mark.parametrize(
    "state",
    [
        C.STATE_REDUCTION_ONLY_DAILY_LOSS,
        C.STATE_REDUCTION_ONLY_BREAKER,
        C.STATE_RECOVERY_PREFLIGHT,
        C.STATE_RECOVERY_COOLDOWN,
    ],
)
def test_reduction_only_states(state):
    assert (
        sm.order_outcome_for_state(state, verified_reduction=True, state_known=True)
        == C.OUTCOME_ALLOW_REDUCTION_ONLY
    )
    # §D1.5: risk-neutral / risk-increasing (anything not a verified reduction) is REFUSED.
    assert (
        sm.order_outcome_for_state(state, verified_reduction=False, state_known=True)
        == C.OUTCOME_REFUSE
    )


def test_unknown_state_value_fails_closed():
    assert (
        sm.order_outcome_for_state("WAT", verified_reduction=True, state_known=True)
        == C.OUTCOME_INTEGRITY_STOP
    )


# --------------------------------------------------------------- combine_outcomes (the ladder)


def test_empty_outcomes_allow():
    assert sm.combine_outcomes([]) == C.OUTCOME_ALLOW


@pytest.mark.parametrize(
    ("outcomes", "expected"),
    [
        ([C.OUTCOME_ALLOW, C.OUTCOME_ALLOW], C.OUTCOME_ALLOW),
        ([C.OUTCOME_ALLOW, C.OUTCOME_REFUSE], C.OUTCOME_REFUSE),
        # The deliberate non-monotonicity: a verified reduction outranks a refusal.
        ([C.OUTCOME_REFUSE, C.OUTCOME_ALLOW_REDUCTION_ONLY], C.OUTCOME_ALLOW_REDUCTION_ONLY),
        # ...but INTEGRITY_STOP dominates the reduction.
        ([C.OUTCOME_ALLOW_REDUCTION_ONLY, C.OUTCOME_INTEGRITY_STOP], C.OUTCOME_INTEGRITY_STOP),
        ([C.OUTCOME_INTEGRITY_STOP, C.OUTCOME_ALLOW, C.OUTCOME_REFUSE], C.OUTCOME_INTEGRITY_STOP),
    ],
)
def test_combine_follows_the_ladder(outcomes, expected):
    assert sm.combine_outcomes(outcomes) == expected


def test_combine_unknown_value_fails_closed():
    assert sm.combine_outcomes(["BOGUS"]) == C.OUTCOME_INTEGRITY_STOP
