"""ADR 0043 §D1 — the PURE loss-control state machine.

No I/O, no clock, no DB — deterministic functions of their inputs, testable exhaustively like
``risk_effect.classify``. This module decides *what* a transition would be and *how* per-order
control outcomes combine; it never persists anything. Persistence, sequencing, and the
compare-and-swap that makes the machine authoritative live in ``service.py`` (§D1.1 — controls emit
transition *requests*; only the service persists). Nothing here is wired into the order path yet.

Two pure surfaces:

1. ``decide_transition(state, trigger, prior_lock_state=…)`` — the state graph (§D1 diagram).
2. ``order_outcome_for_state(...)`` + ``combine_outcomes(...)`` — what a state permits for an
   order, resolved by the normative precedence ladder (§D1) with the epistemic qualifier (§D2).
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from decimal import Decimal

from app.risk.loss_control import constants as C

# --- triggers (the events that drive transitions) ---------------------------------------------
TRIGGER_DAILY_LOSS_BREACH = "DAILY_LOSS_BREACH"  # confirmed daily-loss threshold → reduction-only
TRIGGER_BREAKER_TRIP = "BREAKER_TRIP"  # rate / velocity / emergency → reduction-only (breaker)
TRIGGER_INTEGRITY_VIOLATION = "INTEGRITY_VIOLATION"  # unknown/unreconciled state → INTEGRITY_STOP
TRIGGER_RECOVERY_REQUEST = "RECOVERY_REQUEST"  # sanctioned recovery → RECOVERY_PREFLIGHT
TRIGGER_PREFLIGHT_PASS = "PREFLIGHT_PASS"  # full preflight PASS → RECOVERY_COOLDOWN
TRIGGER_PREFLIGHT_FAIL = "PREFLIGHT_FAIL"  # a check failed → back to the lock, else INTEGRITY_STOP
TRIGGER_COOLDOWN_COMPLETE = "COOLDOWN_COMPLETE"  # all §D1.4 conditions hold → NORMAL
TRIGGER_HEALTH_REGRESSED = "HEALTH_REGRESSED"  # health regressed during cooldown → INTEGRITY_STOP

ALL_TRIGGERS: frozenset[str] = frozenset(
    {
        TRIGGER_DAILY_LOSS_BREACH,
        TRIGGER_BREAKER_TRIP,
        TRIGGER_INTEGRITY_VIOLATION,
        TRIGGER_RECOVERY_REQUEST,
        TRIGGER_PREFLIGHT_PASS,
        TRIGGER_PREFLIGHT_FAIL,
        TRIGGER_COOLDOWN_COMPLETE,
        TRIGGER_HEALTH_REGRESSED,
    }
)

# control_type recorded on the event a transition produces.
_CONTROL_DAILY_LOSS = "DAILY_LOSS"
_CONTROL_BREAKER = "CIRCUIT_BREAKER"
_CONTROL_INTEGRITY = "INTEGRITY"
_CONTROL_RECOVERY = "RECOVERY"

_REDUCTION_ONLY_STATES = frozenset(
    {C.STATE_REDUCTION_ONLY_DAILY_LOSS, C.STATE_REDUCTION_ONLY_BREAKER}
)

# A recovery can only have originated from a lock or an integrity stop. This origin is a PERSISTED
# fact — the ``from_state`` of the event that entered RECOVERY_PREFLIGHT — so the service supplies it
# deterministically (PR 6) from durable state, NEVER inferred from process memory or ambiguous
# history. ``decide_transition`` fail-closes when the origin is absent, invalid, or incompatible.
_RECOVERY_ORIGIN_STATES = frozenset(
    {
        C.STATE_REDUCTION_ONLY_DAILY_LOSS,
        C.STATE_REDUCTION_ONLY_BREAKER,
        C.STATE_INTEGRITY_STOP,
    }
)


@dataclass(frozen=True)
class TransitionDecision:
    """The pure verdict for (state, trigger): whether it transitions, and to where."""

    applies: bool
    to_state: str | None
    control_type: str | None
    reason: str


def _no_op(reason: str) -> TransitionDecision:
    return TransitionDecision(applies=False, to_state=None, control_type=None, reason=reason)


def decide_transition(
    state: str,
    trigger: str,
    *,
    recovery_origin_state: str | None = None,
) -> TransitionDecision:
    """Return the transition (state, trigger) implies, or a no-op if the trigger does not apply.

    Deterministic and total: every (state, trigger) pair yields a decision, never an exception,
    so the caller always gets an explicit result. A trigger that names the state the account is
    already in — or that has no edge from this state — is an explicit no-op, not a silent success.

    ``recovery_origin_state`` matters only for ``PREFLIGHT_FAIL``: a failed recovery returns to the
    state it came from (a reduction-only lock or an integrity stop). It is a PERSISTED input (the
    ``from_state`` of the RECOVERY_PREFLIGHT-entering event), passed in explicitly — the function
    never infers it from memory. If it is absent, not a valid origin, or otherwise incompatible, the
    transition FAILS CLOSED to INTEGRITY_STOP (§D5). The rest of the recovery graph is defined here
    but is not exercised until recovery is wired (PR 6).
    """
    if trigger not in ALL_TRIGGERS:
        return _no_op(f"unknown trigger {trigger!r}")
    if state not in C.ALL_STATES:
        return _no_op(f"unknown state {state!r}")

    # INTEGRITY_VIOLATION dominates from any state (fail-closed) — unless already stopped, in which
    # case it falls through to the shared no-op at the bottom (no duplicate event).
    if trigger == TRIGGER_INTEGRITY_VIOLATION:
        if state != C.STATE_INTEGRITY_STOP:
            return TransitionDecision(
                True, C.STATE_INTEGRITY_STOP, _CONTROL_INTEGRITY, "integrity violation"
            )

    elif state == C.STATE_NORMAL:
        if trigger == TRIGGER_DAILY_LOSS_BREACH:
            return TransitionDecision(
                True, C.STATE_REDUCTION_ONLY_DAILY_LOSS, _CONTROL_DAILY_LOSS, "daily-loss breach"
            )
        if trigger == TRIGGER_BREAKER_TRIP:
            return TransitionDecision(
                True, C.STATE_REDUCTION_ONLY_BREAKER, _CONTROL_BREAKER, "breaker trip"
            )

    elif state in _REDUCTION_ONLY_STATES or state == C.STATE_INTEGRITY_STOP:
        if trigger == TRIGGER_RECOVERY_REQUEST:
            return TransitionDecision(
                True, C.STATE_RECOVERY_PREFLIGHT, _CONTROL_RECOVERY, "recovery requested"
            )

    elif state == C.STATE_RECOVERY_PREFLIGHT:
        if trigger == TRIGGER_PREFLIGHT_PASS:
            return TransitionDecision(
                True, C.STATE_RECOVERY_COOLDOWN, _CONTROL_RECOVERY, "preflight passed"
            )
        if trigger == TRIGGER_PREFLIGHT_FAIL:
            if recovery_origin_state in _RECOVERY_ORIGIN_STATES:
                # Returning INTO the integrity stop is an integrity event; returning to a lock is a
                # recovery-flow event.
                control = (
                    _CONTROL_INTEGRITY
                    if recovery_origin_state == C.STATE_INTEGRITY_STOP
                    else _CONTROL_RECOVERY
                )
                return TransitionDecision(
                    True, recovery_origin_state, control,
                    "preflight failed — return to recovery origin",
                )
            # Origin absent, invalid, or incompatible — never guess a lock; fail closed.
            return TransitionDecision(
                True, C.STATE_INTEGRITY_STOP, _CONTROL_INTEGRITY,
                "preflight failed — origin absent/invalid, fail closed",
            )

    elif state == C.STATE_RECOVERY_COOLDOWN:
        if trigger == TRIGGER_COOLDOWN_COMPLETE:
            return TransitionDecision(True, C.STATE_NORMAL, _CONTROL_RECOVERY, "cooldown complete")
        if trigger == TRIGGER_HEALTH_REGRESSED:
            return TransitionDecision(
                True, C.STATE_INTEGRITY_STOP, _CONTROL_INTEGRITY, "health regressed in cooldown"
            )

    # Reached when a (known-state, known-trigger) pair has no edge — an explicit no-op, e.g. a lock
    # re-asserted while already held, or a recovery step requested in the wrong state.
    return _no_op(f"{trigger} does not apply in {state}")


# --- the normative precedence ladder (§D1) + epistemic qualifier (§D2) -------------------------

# States in which only verified risk-reducing orders may pass (new/neutral risk is refused).
_REDUCTION_ONLY_FOR_ORDERS = frozenset(
    {
        C.STATE_REDUCTION_ONLY_DAILY_LOSS,
        C.STATE_REDUCTION_ONLY_BREAKER,
        C.STATE_RECOVERY_PREFLIGHT,  # still locked while the preflight runs
        C.STATE_RECOVERY_COOLDOWN,  # §D6 re-arm: reductions allowed, new risk disabled
    }
)


def order_outcome_for_state(
    state: str,
    *,
    verified_reduction: bool,
    state_known: bool,
) -> str:
    """The loss-control layer's per-order outcome for an account in ``state``.

    Encodes §D2 first: if the account state is not known well enough to *verify* a reduction, the
    only safe answer is INTEGRITY_STOP — never a guessed ALLOW (``REDUCTION_NOT_VERIFIABLE``). Then
    §D1.5: in a reduction-only state, a verified reduction is ALLOW_REDUCTION_ONLY and everything
    else (risk-increasing OR risk-neutral) is REFUSE. NORMAL imposes no loss-control restriction;
    INTEGRITY_STOP blocks everything.

    This is one control's contribution; ``combine_outcomes`` resolves it against others by the
    normative ladder. It is pure and not yet consulted by the engine (that is PR 4).
    """
    if not state_known:
        return C.OUTCOME_INTEGRITY_STOP
    if state == C.STATE_INTEGRITY_STOP:
        return C.OUTCOME_INTEGRITY_STOP
    if state == C.STATE_NORMAL:
        return C.OUTCOME_ALLOW
    if state in _REDUCTION_ONLY_FOR_ORDERS:
        return C.OUTCOME_ALLOW_REDUCTION_ONLY if verified_reduction else C.OUTCOME_REFUSE
    return C.OUTCOME_INTEGRITY_STOP  # unknown state value → fail closed


def combine_outcomes(outcomes: Iterable[str]) -> str:
    """Resolve several control outcomes by the NORMATIVE precedence ladder (§D1).

        INTEGRITY_STOP > ALLOW_REDUCTION_ONLY > REFUSE > ALLOW

    The first rung any control reaches wins. The one deliberate non-monotonicity — a verified
    reduction (ALLOW_REDUCTION_ONLY) outranks a REFUSE — is what lets a de-risking order pass under
    a lock (the ADR 0042 invariant), while INTEGRITY_STOP still dominates because a reduction cannot
    be verified under unknown state (§D2). An empty set of controls imposes no restriction → ALLOW.
    """
    seen = set(outcomes)
    if not seen:
        return C.OUTCOME_ALLOW
    for rung in C.PRECEDENCE_LADDER:  # index 0 = most restrictive
        if rung in seen:
            return rung
    # Any value not on the ladder is not a sanctioned outcome — fail closed rather than pass it.
    return C.OUTCOME_INTEGRITY_STOP


# --- §D6 re-arm / hysteresis / dwell + §D1.4 cooldown completion -------------------------------
# PURE policy governing WHEN an account may re-arm from RECOVERY_COOLDOWN to NORMAL, and when it
# regresses to INTEGRITY_STOP. Asymmetric: no monetary band — re-arm requires a class-dependent
# minimum dwell AND all §D1.4 conditions. Clock-free: elapsed time / session boundary / health
# signals are passed in as explicit inputs (this module never reads a clock or DB). Nothing fires a
# transition here; a later increment maps these verdicts onto TRIGGER_COOLDOWN_COMPLETE /
# TRIGGER_HEALTH_REGRESSED through the persistence service (this stays the sanctioned home for the
# re-arm decision, per the §6 CI invariant).

# Integrity-class trip causes: an unresolved condition to be REPAIRED, not merely waited out.
_INTEGRITY_TRIP_CAUSES = frozenset(
    {
        C.TRIP_CAUSE_BROKER_STATE_UNCERTAIN,
        C.TRIP_CAUSE_POSITION_RECONCILIATION_FAILED,
        C.TRIP_CAUSE_SESSION_BASELINE_MISSING,
        C.TRIP_CAUSE_SESSION_BASELINE_MISMATCH,
        C.TRIP_CAUSE_STALE_MARKET_DATA,
        C.TRIP_CAUSE_ORDER_STATE_UNCERTAIN,
        C.TRIP_CAUSE_CONTROL_CONFIGURATION_INVALID,
        C.TRIP_CAUSE_REDUCTION_NOT_VERIFIABLE,
    }
)


@dataclass(frozen=True)
class DwellRequirement:
    """How long an account must dwell in RECOVERY_COOLDOWN before re-arm is even eligible."""

    kind: str  # one of C.DWELL_KIND_*
    minutes: int | None = None  # set iff kind == FIXED_MINUTES


def dwell_class_for_trip(trip_cause: str | None, trip_evidence_status: str | None) -> str:
    """Classify a lock by the dwell it earns (§D6). CONSERVATIVE: a serious cause is classified by
    the cause regardless of any (contradictory) artifact claim, and anything unrecognised falls to
    the strictest class (until manual repair). Only a non-serious trip CONFIRMED to be an artifact
    earns the fast fixed dwell — a short dwell is the risky direction, so it needs the strongest
    justification."""
    if trip_cause == C.TRIP_CAUSE_REALIZED_AND_MARK_TO_MARKET_LOSS:
        return C.DWELL_CLASS_CONFIRMED_DAILY_LOSS
    if trip_cause == C.TRIP_CAUSE_LOSS_VELOCITY:
        return C.DWELL_CLASS_RATE_VELOCITY
    if trip_cause in _INTEGRITY_TRIP_CAUSES:
        return C.DWELL_CLASS_INTEGRITY
    if trip_evidence_status == C.TRIP_EVIDENCE_ARTIFACT_CONFIRMED:
        return C.DWELL_CLASS_ARTIFACT
    return C.DWELL_CLASS_INTEGRITY  # UNKNOWN / OPERATOR_EMERGENCY / unmapped → strictest, fail safe


def required_dwell(dwell_class: str) -> DwellRequirement:
    """The minimum dwell for a class (§D6 conservative defaults)."""
    if dwell_class == C.DWELL_CLASS_ARTIFACT:
        return DwellRequirement(C.DWELL_KIND_FIXED_MINUTES, C.DWELL_ARTIFACT_MINUTES)
    if dwell_class == C.DWELL_CLASS_RATE_VELOCITY:
        return DwellRequirement(C.DWELL_KIND_FIXED_MINUTES, C.DWELL_RATE_VELOCITY_MINUTES)
    if dwell_class == C.DWELL_CLASS_CONFIRMED_DAILY_LOSS:
        return DwellRequirement(C.DWELL_KIND_UNTIL_NEXT_SESSION)
    # INTEGRITY and any unrecognised class → the strictest requirement (fail closed).
    return DwellRequirement(C.DWELL_KIND_UNTIL_MANUAL_REPAIR)


def velocity_recovery_threshold(trip_limit: Decimal) -> Decimal:
    """The (stricter) loss-velocity level below which the account counts as recovering (§D6)."""
    return trip_limit * C.VELOCITY_RECOVERY_FRACTION


def velocity_is_healthy(current: Decimal, trip_limit: Decimal, sustained_seconds: int) -> bool:
    """Loss velocity is 'healthy' only at ≤ the recovery threshold AND sustained long enough — the
    asymmetric hysteresis that stops a single quiet tick from re-arming the account."""
    return (
        current <= velocity_recovery_threshold(trip_limit)
        and sustained_seconds >= C.VELOCITY_HEALTHY_MIN_SECONDS
    )


@dataclass(frozen=True)
class CooldownInputs:
    """Everything the §D1.4 decision needs — all passed in (no clock, no DB)."""

    dwell_class: str
    dwell_elapsed_seconds: int  # since RECOVERY_COOLDOWN began
    new_session_started: bool  # a new trading session began since cooldown began
    manual_repair_complete: bool  # integrity repair signed off
    integrity_alerts_active: bool
    broker_reconciled: bool
    state_unchanged_since_cooldown: bool  # no new trip enqueued during the dwell
    velocity_healthy: bool = True  # ≤ recovery threshold sustained ≥ min (only used for velocity)


@dataclass(frozen=True)
class CooldownVerdict:
    verdict: str  # C.COOLDOWN_HOLD | COOLDOWN_COMPLETE | COOLDOWN_REGRESSED
    reason: str


def _dwell_satisfied(inp: CooldownInputs) -> bool:
    req = required_dwell(inp.dwell_class)
    if req.kind == C.DWELL_KIND_FIXED_MINUTES:
        return inp.dwell_elapsed_seconds >= (req.minutes or 0) * 60
    if req.kind == C.DWELL_KIND_UNTIL_NEXT_SESSION:
        return inp.new_session_started
    # ``required_dwell`` only ever yields FIXED_MINUTES, UNTIL_NEXT_SESSION, or the strictest
    # UNTIL_MANUAL_REPAIR (its default for INTEGRITY and any unrecognised class) — so the remaining
    # case is manual repair, which must be signed off before the dwell is satisfied.
    return inp.manual_repair_complete


def evaluate_cooldown(inp: CooldownInputs) -> CooldownVerdict:
    """The pure §D1.4 verdict for an account in RECOVERY_COOLDOWN.

    An OUTRIGHT regression (a fresh integrity alert, or a new trip enqueued during the dwell) fails
    closed to INTEGRITY_STOP. Otherwise every unmet condition merely HOLDs the account in cooldown —
    re-arm to NORMAL requires the full class-dependent dwell, a clean broker reconciliation, and
    (for a velocity trip) recovered loss velocity. Never a symmetric monetary band."""
    if inp.integrity_alerts_active:
        return CooldownVerdict(C.COOLDOWN_REGRESSED, "integrity alert active during cooldown")
    if not inp.state_unchanged_since_cooldown:
        return CooldownVerdict(C.COOLDOWN_REGRESSED, "new trip enqueued during cooldown")
    if not _dwell_satisfied(inp):
        return CooldownVerdict(C.COOLDOWN_HOLD, "minimum dwell not satisfied")
    if not inp.broker_reconciled:
        return CooldownVerdict(C.COOLDOWN_HOLD, "broker reconciliation not clean")
    if inp.dwell_class == C.DWELL_CLASS_RATE_VELOCITY and not inp.velocity_healthy:
        return CooldownVerdict(C.COOLDOWN_HOLD, "loss velocity not recovered")
    return CooldownVerdict(C.COOLDOWN_COMPLETE, "all D1.4 conditions hold")


def daily_loss_permits_same_session_rearm() -> bool:
    """§D6: a daily-loss lock is reduction-only for the REST OF THE SESSION — never an automatic
    same-session re-arm for new risk. (Structurally, a daily-loss trip's dwell is UNTIL_NEXT_SESSION;
    this explicit predicate documents the policy for callers.)"""
    return False
