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
    prior_lock_state: str | None = None,
) -> TransitionDecision:
    """Return the transition (state, trigger) implies, or a no-op if the trigger does not apply.

    Deterministic and total: every (state, trigger) pair yields a decision, never an exception,
    so the caller always gets an explicit result. A trigger that names the state the account is
    already in — or that has no edge from this state — is an explicit no-op, not a silent success.

    ``prior_lock_state`` matters only for ``PREFLIGHT_FAIL``: a failed recovery returns to the lock
    it came from when that is known, else fails closed to INTEGRITY_STOP (§D5). The rest of the
    recovery graph is defined here but is not exercised until recovery is wired (PR 6).
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
            if prior_lock_state in _REDUCTION_ONLY_STATES:
                return TransitionDecision(
                    True, prior_lock_state, _CONTROL_RECOVERY,
                    "preflight failed — return to prior lock",
                )
            return TransitionDecision(
                True, C.STATE_INTEGRITY_STOP, _CONTROL_INTEGRITY, "preflight failed — fail closed"
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
