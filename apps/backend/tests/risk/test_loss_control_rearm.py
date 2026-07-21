"""ADR 0043 §D6 / §D1.4 (PR7) — the PURE re-arm / hysteresis / dwell policy.

Exhaustive, clock-free unit tests (no DB, no I/O) of the dwell classification, the class→requirement
mapping, loss-velocity hysteresis, and the RECOVERY_COOLDOWN → NORMAL / INTEGRITY_STOP decision.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from app.risk.loss_control import constants as C
from app.risk.loss_control.state_machine import (
    CooldownInputs,
    DwellRequirement,
    daily_loss_permits_same_session_rearm,
    dwell_class_for_trip,
    evaluate_cooldown,
    required_dwell,
    velocity_is_healthy,
    velocity_recovery_threshold,
)

D = Decimal


# --------------------------------------------------------------- dwell classification (§D6)


@pytest.mark.parametrize(
    ("trip_cause", "evidence", "expected"),
    [
        (C.TRIP_CAUSE_REALIZED_AND_MARK_TO_MARKET_LOSS, None, C.DWELL_CLASS_CONFIRMED_DAILY_LOSS),
        (C.TRIP_CAUSE_LOSS_VELOCITY, None, C.DWELL_CLASS_RATE_VELOCITY),
        (C.TRIP_CAUSE_BROKER_STATE_UNCERTAIN, None, C.DWELL_CLASS_INTEGRITY),
        (C.TRIP_CAUSE_POSITION_RECONCILIATION_FAILED, None, C.DWELL_CLASS_INTEGRITY),
        (C.TRIP_CAUSE_SESSION_BASELINE_MISSING, None, C.DWELL_CLASS_INTEGRITY),
        (C.TRIP_CAUSE_SESSION_BASELINE_MISMATCH, None, C.DWELL_CLASS_INTEGRITY),
        (C.TRIP_CAUSE_STALE_MARKET_DATA, None, C.DWELL_CLASS_INTEGRITY),
        (C.TRIP_CAUSE_ORDER_STATE_UNCERTAIN, None, C.DWELL_CLASS_INTEGRITY),
        (C.TRIP_CAUSE_CONTROL_CONFIGURATION_INVALID, None, C.DWELL_CLASS_INTEGRITY),
        (C.TRIP_CAUSE_REDUCTION_NOT_VERIFIABLE, None, C.DWELL_CLASS_INTEGRITY),
        # Non-serious cause CONFIRMED to be an artifact → the fast fixed dwell.
        (C.TRIP_CAUSE_UNKNOWN, C.TRIP_EVIDENCE_ARTIFACT_CONFIRMED, C.DWELL_CLASS_ARTIFACT),
        # Unrecognised / operator-emergency / bare unknown → strictest (fail safe).
        (C.TRIP_CAUSE_OPERATOR_EMERGENCY, None, C.DWELL_CLASS_INTEGRITY),
        (C.TRIP_CAUSE_UNKNOWN, None, C.DWELL_CLASS_INTEGRITY),
        (None, None, C.DWELL_CLASS_INTEGRITY),
    ],
)
def test_dwell_class_for_trip(trip_cause, evidence, expected):
    assert dwell_class_for_trip(trip_cause, evidence) == expected


def test_artifact_claim_never_downgrades_a_serious_cause():
    # A REAL loss (or an integrity cause) stays classified by its cause even if mislabeled an artifact
    # — a short dwell is the risky direction and must not be reachable by a contradictory claim.
    assert dwell_class_for_trip(
        C.TRIP_CAUSE_REALIZED_AND_MARK_TO_MARKET_LOSS, C.TRIP_EVIDENCE_ARTIFACT_CONFIRMED
    ) == C.DWELL_CLASS_CONFIRMED_DAILY_LOSS
    assert dwell_class_for_trip(
        C.TRIP_CAUSE_BROKER_STATE_UNCERTAIN, C.TRIP_EVIDENCE_ARTIFACT_CONFIRMED
    ) == C.DWELL_CLASS_INTEGRITY


# --------------------------------------------------------------- class → requirement (§D6)


def test_required_dwell_per_class():
    assert required_dwell(C.DWELL_CLASS_ARTIFACT) == DwellRequirement(
        C.DWELL_KIND_FIXED_MINUTES, C.DWELL_ARTIFACT_MINUTES)
    assert required_dwell(C.DWELL_CLASS_RATE_VELOCITY) == DwellRequirement(
        C.DWELL_KIND_FIXED_MINUTES, C.DWELL_RATE_VELOCITY_MINUTES)
    assert required_dwell(C.DWELL_CLASS_CONFIRMED_DAILY_LOSS).kind == C.DWELL_KIND_UNTIL_NEXT_SESSION
    assert required_dwell(C.DWELL_CLASS_INTEGRITY).kind == C.DWELL_KIND_UNTIL_MANUAL_REPAIR
    # Conservative defaults from the ADR.
    assert C.DWELL_ARTIFACT_MINUTES == 15 and C.DWELL_RATE_VELOCITY_MINUTES == 30


def test_required_dwell_unknown_class_is_strictest():
    assert required_dwell("NOT_A_CLASS").kind == C.DWELL_KIND_UNTIL_MANUAL_REPAIR


# --------------------------------------------------------------- loss-velocity hysteresis (§D6)


def test_velocity_recovery_threshold_is_half_the_trip_limit():
    assert velocity_recovery_threshold(D("1000")) == D("500")


def test_velocity_is_healthy_requires_below_threshold_and_sustained():
    limit = D("1000")
    mins = C.VELOCITY_HEALTHY_MIN_SECONDS
    assert velocity_is_healthy(D("500"), limit, mins) is True          # at threshold + sustained
    assert velocity_is_healthy(D("499"), limit, mins) is True
    assert velocity_is_healthy(D("501"), limit, mins) is False         # above threshold
    assert velocity_is_healthy(D("100"), limit, mins - 1) is False     # not sustained long enough


# --------------------------------------------------------------- §D1.4 cooldown decision


def _inputs(**over):
    base = dict(
        dwell_class=C.DWELL_CLASS_ARTIFACT,
        dwell_elapsed_seconds=C.DWELL_ARTIFACT_MINUTES * 60,
        new_session_started=True,
        manual_repair_complete=True,
        integrity_alerts_active=False,
        broker_reconciled=True,
        state_unchanged_since_cooldown=True,
        velocity_healthy=True,
    )
    base.update(over)
    return CooldownInputs(**base)


def test_integrity_alert_during_cooldown_regresses():
    v = evaluate_cooldown(_inputs(integrity_alerts_active=True))
    assert v.verdict == C.COOLDOWN_REGRESSED


def test_new_trip_during_cooldown_regresses():
    v = evaluate_cooldown(_inputs(state_unchanged_since_cooldown=False))
    assert v.verdict == C.COOLDOWN_REGRESSED


def test_regression_dominates_an_otherwise_complete_cooldown():
    # Even with the dwell satisfied and everything else clean, an outright regression wins.
    v = evaluate_cooldown(_inputs(integrity_alerts_active=True, broker_reconciled=True))
    assert v.verdict == C.COOLDOWN_REGRESSED


def test_fixed_dwell_not_elapsed_holds():
    v = evaluate_cooldown(_inputs(dwell_class=C.DWELL_CLASS_ARTIFACT,
                                  dwell_elapsed_seconds=C.DWELL_ARTIFACT_MINUTES * 60 - 1))
    assert v.verdict == C.COOLDOWN_HOLD


def test_broker_not_reconciled_holds():
    v = evaluate_cooldown(_inputs(broker_reconciled=False))
    assert v.verdict == C.COOLDOWN_HOLD


def test_velocity_class_not_healthy_holds():
    v = evaluate_cooldown(_inputs(dwell_class=C.DWELL_CLASS_RATE_VELOCITY,
                                  dwell_elapsed_seconds=C.DWELL_RATE_VELOCITY_MINUTES * 60,
                                  velocity_healthy=False))
    assert v.verdict == C.COOLDOWN_HOLD


def test_velocity_class_healthy_and_elapsed_completes():
    v = evaluate_cooldown(_inputs(dwell_class=C.DWELL_CLASS_RATE_VELOCITY,
                                  dwell_elapsed_seconds=C.DWELL_RATE_VELOCITY_MINUTES * 60,
                                  velocity_healthy=True))
    assert v.verdict == C.COOLDOWN_COMPLETE


def test_artifact_dwell_elapsed_completes():
    assert evaluate_cooldown(_inputs()).verdict == C.COOLDOWN_COMPLETE


def test_confirmed_daily_loss_requires_next_session():
    # Reduction-only for the rest of the session: no re-arm until a new session begins.
    hold = evaluate_cooldown(_inputs(dwell_class=C.DWELL_CLASS_CONFIRMED_DAILY_LOSS,
                                     new_session_started=False))
    assert hold.verdict == C.COOLDOWN_HOLD
    done = evaluate_cooldown(_inputs(dwell_class=C.DWELL_CLASS_CONFIRMED_DAILY_LOSS,
                                     new_session_started=True))
    assert done.verdict == C.COOLDOWN_COMPLETE


def test_integrity_requires_manual_repair():
    hold = evaluate_cooldown(_inputs(dwell_class=C.DWELL_CLASS_INTEGRITY,
                                     manual_repair_complete=False))
    assert hold.verdict == C.COOLDOWN_HOLD
    done = evaluate_cooldown(_inputs(dwell_class=C.DWELL_CLASS_INTEGRITY,
                                     manual_repair_complete=True))
    assert done.verdict == C.COOLDOWN_COMPLETE


def test_unknown_dwell_class_maps_to_strictest_repair_gate():
    # An unrecognised class maps to the strictest requirement (until manual repair): without a
    # completed repair it HOLDs (fail closed); with one it may complete like any integrity lock.
    hold = evaluate_cooldown(_inputs(dwell_class="NOT_A_CLASS", manual_repair_complete=False))
    assert hold.verdict == C.COOLDOWN_HOLD
    done = evaluate_cooldown(_inputs(dwell_class="NOT_A_CLASS", manual_repair_complete=True))
    assert done.verdict == C.COOLDOWN_COMPLETE


def test_daily_loss_no_same_session_rearm():
    assert daily_loss_permits_same_session_rearm() is False
