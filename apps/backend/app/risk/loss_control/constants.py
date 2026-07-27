"""ADR 0043 — the loss-control vocabulary (states, outcomes, trip taxonomy).

Single source of truth for the string values persisted by the five loss-control tables and,
in later increments, consumed by the state machine and the CI invariant. The columns store
these as plain strings (the codebase stores enums as strings, not SQL enums — see
``risk_decision.py``); these constants keep every producer and consumer agreeing on the spellings.

PR 1 uses only the values needed to define and exercise the schema. The transition *logic*
(which state a trigger moves to, how outcomes combine) lives in the pure state machine landed
in a later increment — NOT here. This module is data, not behavior.
"""

from __future__ import annotations

from decimal import Decimal

# --- versioning -------------------------------------------------------------------------------
# Bumped when the state model itself changes shape, so future migrations of persisted state are
# manageable the way RISK_POLICY_VERSION (ADR 0042) and the ledger already are (ADR 0043 §D1.3).
LOSS_CONTROL_STATE_VERSION = 1

# --- the six account-level states (materialized current-state, ADR 0043 §D1) ------------------
STATE_NORMAL = "NORMAL"
STATE_REDUCTION_ONLY_DAILY_LOSS = "REDUCTION_ONLY_DAILY_LOSS"
STATE_REDUCTION_ONLY_BREAKER = "REDUCTION_ONLY_BREAKER"
# The day-change basis is UNAVAILABLE: no broker prior-close and no eligible prior-close snapshot,
# so today's P&L is UNKNOWN. Distinct from REDUCTION_ONLY_DAILY_LOSS on purpose — nothing here
# asserts a measured loss or a crossed threshold. It is the protection you apply when you cannot
# see, not the one you apply when you have seen something bad.
STATE_REDUCTION_ONLY_DAILY_PNL_UNAVAILABLE = "REDUCTION_ONLY_DAILY_PNL_UNAVAILABLE"
STATE_INTEGRITY_STOP = "INTEGRITY_STOP"
STATE_RECOVERY_PREFLIGHT = "RECOVERY_PREFLIGHT"
STATE_RECOVERY_COOLDOWN = "RECOVERY_COOLDOWN"

ALL_STATES: frozenset[str] = frozenset(
    {
        STATE_NORMAL,
        STATE_REDUCTION_ONLY_DAILY_LOSS,
        STATE_REDUCTION_ONLY_BREAKER,
        STATE_REDUCTION_ONLY_DAILY_PNL_UNAVAILABLE,
        STATE_INTEGRITY_STOP,
        STATE_RECOVERY_PREFLIGHT,
        STATE_RECOVERY_COOLDOWN,
    }
)

# --- the normative precedence ladder (ADR 0043 §D1) -------------------------------------------
# Combined per-order outcomes, MOST restrictive first. This ordering is NORMATIVE: an
# implementation that resolves combined outcomes any other way is non-conforming. The one
# deliberate non-monotonicity is that ALLOW_REDUCTION_ONLY outranks REFUSE — a verified reduction
# under a lock must pass (the ADR 0042 invariant) — while INTEGRITY_STOP dominates everything
# because a reduction cannot be *verified* under unknown state (§D2).
OUTCOME_INTEGRITY_STOP = "INTEGRITY_STOP"
OUTCOME_ALLOW_REDUCTION_ONLY = "ALLOW_REDUCTION_ONLY"
OUTCOME_REFUSE = "REFUSE"
OUTCOME_ALLOW = "ALLOW"

# Index 0 = most restrictive. Ordering is the contract; do not reorder without an ADR revision.
PRECEDENCE_LADDER: tuple[str, ...] = (
    OUTCOME_INTEGRITY_STOP,
    OUTCOME_ALLOW_REDUCTION_ONLY,
    OUTCOME_REFUSE,
    OUTCOME_ALLOW,
)

# --- three-field trip taxonomy (ADR 0043 §D4) -------------------------------------------------
# WHAT kind of control tripped.
TRIP_TYPE_DAILY_LOSS = "DAILY_LOSS"
TRIP_TYPE_CIRCUIT_BREAKER = "CIRCUIT_BREAKER"
TRIP_TYPE_MANUAL_HALT = "MANUAL_HALT"
TRIP_TYPE_CONTROL_INTEGRITY = "CONTROL_INTEGRITY"
# The control could not MEASURE, as opposed to having measured something bad. Deliberately not
# TRIP_TYPE_DAILY_LOSS: recording an unmeasurable P&L as a daily-loss trip would put a loss that
# was never observed into the audit trail and into every downstream reading of it.
TRIP_TYPE_MEASUREMENT_UNAVAILABLE = "MEASUREMENT_UNAVAILABLE"
ALL_TRIP_TYPES: frozenset[str] = frozenset(
    {
        TRIP_TYPE_DAILY_LOSS,
        TRIP_TYPE_CIRCUIT_BREAKER,
        TRIP_TYPE_MANUAL_HALT,
        TRIP_TYPE_CONTROL_INTEGRITY,
        TRIP_TYPE_MEASUREMENT_UNAVAILABLE,
    }
)

# WHY it tripped. Note: CONCENTRATION_EVENT is deliberately EXCLUDED — concentration risk is a
# separate portfolio-risk ADR; this taxonomy identifies the loss-control trigger, not portfolio
# attribution (ADR 0043 scope boundary). MANUAL is a trip_type/initiator, never a cause.
TRIP_CAUSE_REALIZED_AND_MARK_TO_MARKET_LOSS = "REALIZED_AND_MARK_TO_MARKET_LOSS"
TRIP_CAUSE_LOSS_VELOCITY = "LOSS_VELOCITY"
TRIP_CAUSE_BROKER_STATE_UNCERTAIN = "BROKER_STATE_UNCERTAIN"
TRIP_CAUSE_POSITION_RECONCILIATION_FAILED = "POSITION_RECONCILIATION_FAILED"
TRIP_CAUSE_SESSION_BASELINE_MISSING = "SESSION_BASELINE_MISSING"
TRIP_CAUSE_SESSION_BASELINE_MISMATCH = "SESSION_BASELINE_MISMATCH"
TRIP_CAUSE_STALE_MARKET_DATA = "STALE_MARKET_DATA"
TRIP_CAUSE_ORDER_STATE_UNCERTAIN = "ORDER_STATE_UNCERTAIN"
TRIP_CAUSE_CONTROL_CONFIGURATION_INVALID = "CONTROL_CONFIGURATION_INVALID"
TRIP_CAUSE_REDUCTION_NOT_VERIFIABLE = "REDUCTION_NOT_VERIFIABLE"
TRIP_CAUSE_OPERATOR_EMERGENCY = "OPERATOR_EMERGENCY"
#: No usable day-change basis: the amount is UNKNOWN and no threshold is asserted to have been
#: crossed. The trip reason is the absence of a measurement, never a measurement.
TRIP_CAUSE_DAILY_PNL_UNAVAILABLE = "DAILY_PNL_UNAVAILABLE"
TRIP_CAUSE_UNKNOWN = "UNKNOWN"
ALL_TRIP_CAUSES: frozenset[str] = frozenset(
    {
        TRIP_CAUSE_DAILY_PNL_UNAVAILABLE,
        TRIP_CAUSE_REALIZED_AND_MARK_TO_MARKET_LOSS,
        TRIP_CAUSE_LOSS_VELOCITY,
        TRIP_CAUSE_BROKER_STATE_UNCERTAIN,
        TRIP_CAUSE_POSITION_RECONCILIATION_FAILED,
        TRIP_CAUSE_SESSION_BASELINE_MISSING,
        TRIP_CAUSE_SESSION_BASELINE_MISMATCH,
        TRIP_CAUSE_STALE_MARKET_DATA,
        TRIP_CAUSE_ORDER_STATE_UNCERTAIN,
        TRIP_CAUSE_CONTROL_CONFIGURATION_INVALID,
        TRIP_CAUSE_REDUCTION_NOT_VERIFIABLE,
        TRIP_CAUSE_OPERATOR_EMERGENCY,
        TRIP_CAUSE_UNKNOWN,
    }
)

# HOW WELL the cause is established — drives recovery authority (a real loss needs a human; a
# confirmed artifact may self-heal after a full preflight PASS).
TRIP_EVIDENCE_CONFIRMED = "CONFIRMED"
TRIP_EVIDENCE_SUSPECTED = "SUSPECTED"
TRIP_EVIDENCE_ARTIFACT_CONFIRMED = "ARTIFACT_CONFIRMED"
TRIP_EVIDENCE_UNRESOLVED = "UNRESOLVED"
ALL_TRIP_EVIDENCE_STATUSES: frozenset[str] = frozenset(
    {
        TRIP_EVIDENCE_CONFIRMED,
        TRIP_EVIDENCE_SUSPECTED,
        TRIP_EVIDENCE_ARTIFACT_CONFIRMED,
        TRIP_EVIDENCE_UNRESOLVED,
    }
)

# --- recovery preflight (ADR 0043 §D5) --------------------------------------------------------
# Overall preflight verdict (immutable once written).
PREFLIGHT_PASS = "PREFLIGHT_PASS"
PREFLIGHT_FAIL = "PREFLIGHT_FAIL"
PREFLIGHT_INCOMPLETE = "PREFLIGHT_INCOMPLETE"

# Per-check status.
CHECK_PASS = "PASS"
CHECK_FAIL = "FAIL"
CHECK_INCOMPLETE = "INCOMPLETE"

# Recovery authority classes — who may clear a trip of a given evidence class.
AUTHORITY_ARTIFACT_AUTO = "ARTIFACT_AUTO"  # self-heal (ADR 0035) after a full PASS
AUTHORITY_HUMAN_REQUIRED = "HUMAN_REQUIRED"  # real loss / loss-velocity
AUTHORITY_REPAIR_FIRST = "REPAIR_FIRST"  # broker/recon/integrity — fix the condition, not approve it
AUTHORITY_MANUAL_SAME_OR_HIGHER = "MANUAL_SAME_OR_HIGHER"  # manual emergency
ALL_AUTHORITY_CLASSES: frozenset[str] = frozenset(
    {
        AUTHORITY_ARTIFACT_AUTO,
        AUTHORITY_HUMAN_REQUIRED,
        AUTHORITY_REPAIR_FIRST,
        AUTHORITY_MANUAL_SAME_OR_HIGHER,
    }
)

# ==============================================================================================
# ADR 0043 PR6 — the recovery preflight WORKFLOW vocabulary (control-plane, not the order path).
# ==============================================================================================

# Bumped when the check registry / evidence shape changes so a stale evidence package is legible.
RECOVERY_EVIDENCE_VERSION = 1

# Parent preflight lifecycle status. Distinct from the aggregate VERDICT (PASS/FAIL/INCOMPLETE) and
# from the transition-commit outcome — a PASS verdict is NOT the same as "the transition committed".
PREFLIGHT_STATUS_REQUESTED = "REQUESTED"
PREFLIGHT_STATUS_RUNNING = "RUNNING"
PREFLIGHT_STATUS_PASSED = "PASSED"  # aggregate PASS + authority satisfied + PREFLIGHT_PASS committed
PREFLIGHT_STATUS_FAILED = "FAILED"  # aggregate FAIL → PREFLIGHT_FAIL committed
PREFLIGHT_STATUS_INCOMPLETE = "INCOMPLETE"  # aggregate INCOMPLETE → PREFLIGHT_FAIL committed
PREFLIGHT_STATUS_AUTHORIZATION_REQUIRED = "AUTHORIZATION_REQUIRED"  # PASS but a human must approve
PREFLIGHT_STATUS_COMMIT_FAILED = "COMMIT_FAILED"  # a transition write raised — nothing authoritative
ALL_PREFLIGHT_STATUSES: frozenset[str] = frozenset(
    {
        PREFLIGHT_STATUS_REQUESTED,
        PREFLIGHT_STATUS_RUNNING,
        PREFLIGHT_STATUS_PASSED,
        PREFLIGHT_STATUS_FAILED,
        PREFLIGHT_STATUS_INCOMPLETE,
        PREFLIGHT_STATUS_AUTHORIZATION_REQUIRED,
        PREFLIGHT_STATUS_COMMIT_FAILED,
    }
)
# Statuses in which a preflight is still "active" — an account may have at most one active preflight.
ACTIVE_PREFLIGHT_STATUSES: frozenset[str] = frozenset(
    {PREFLIGHT_STATUS_REQUESTED, PREFLIGHT_STATUS_RUNNING, PREFLIGHT_STATUS_AUTHORIZATION_REQUIRED}
)

# Aggregate verdict of the 12 checks (fail-closed). Same value set as the per-check status.
AGG_PASS = CHECK_PASS
AGG_FAIL = CHECK_FAIL
AGG_INCOMPLETE = CHECK_INCOMPLETE

# The 12 stable, versioned preflight check names (§D5). Exactly twelve — do not add/remove without
# bumping RECOVERY_EVIDENCE_VERSION and updating tests + runbook + authority policy.
CHECK_STATE_KNOWN_AND_RECOVERABLE = "state_known_and_recoverable"
CHECK_RECOVERY_ORIGIN_PROVEN = "recovery_origin_proven"
CHECK_BROKER_REACHABLE = "broker_reachable"
CHECK_BROKER_ACCOUNT_ACTIVE = "broker_account_active"
CHECK_POSITIONS_RECONCILE = "positions_reconcile"
CHECK_OPEN_ORDERS_RECONCILE = "open_orders_reconcile"
CHECK_RESERVATIONS_RECONCILE = "reservations_reconcile"
CHECK_SESSION_BASELINE_VALID = "session_baseline_valid"
CHECK_DAILY_LOSS_RECOMPUTED = "daily_loss_recomputed"
CHECK_TRIP_CAUSE_CLASSIFIED = "trip_cause_classified"
CHECK_CONTROL_STATE_CONSISTENT = "control_state_consistent"
CHECK_NO_UNRESOLVED_INTEGRITY_CONDITION = "no_unresolved_integrity_condition"
PREFLIGHT_CHECK_REGISTRY: tuple[str, ...] = (
    CHECK_STATE_KNOWN_AND_RECOVERABLE,
    CHECK_RECOVERY_ORIGIN_PROVEN,
    CHECK_BROKER_REACHABLE,
    CHECK_BROKER_ACCOUNT_ACTIVE,
    CHECK_POSITIONS_RECONCILE,
    CHECK_OPEN_ORDERS_RECONCILE,
    CHECK_RESERVATIONS_RECONCILE,
    CHECK_SESSION_BASELINE_VALID,
    CHECK_DAILY_LOSS_RECOMPUTED,
    CHECK_TRIP_CAUSE_CLASSIFIED,
    CHECK_CONTROL_STATE_CONSISTENT,
    CHECK_NO_UNRESOLVED_INTEGRITY_CONDITION,
)

# Actor types for request / authorization. A SYSTEM actor may run checks but may NOT self-authorize
# an INTEGRITY_STOP recovery (§D5 authority matrix).
ACTOR_OWNER = "OWNER"
ACTOR_RISK_OPERATOR = "RISK_OPERATOR"
ACTOR_SYSTEM = "SYSTEM"

# Stable error / blocked codes for evidence (never raw exception text, no credentials/tokens).
ERR_BROKER_UNREACHABLE = "ERR_BROKER_UNREACHABLE"
ERR_BROKER_ACCOUNT_INACTIVE = "ERR_BROKER_ACCOUNT_INACTIVE"
ERR_POSITION_MISMATCH = "ERR_POSITION_MISMATCH"
ERR_OPEN_ORDER_MISMATCH = "ERR_OPEN_ORDER_MISMATCH"
ERR_RESERVATION_MISMATCH = "ERR_RESERVATION_MISMATCH"
ERR_BASELINE_INVALID = "ERR_BASELINE_INVALID"
ERR_LOSS_NOT_RECOMPUTABLE = "ERR_LOSS_NOT_RECOMPUTABLE"
ERR_ORIGIN_UNPROVEN = "ERR_ORIGIN_UNPROVEN"
ERR_STATE_CONTRADICTION = "ERR_STATE_CONTRADICTION"
ERR_TRIP_CAUSE_UNKNOWN = "ERR_TRIP_CAUSE_UNKNOWN"
ERR_UNRESOLVED_INTEGRITY = "ERR_UNRESOLVED_INTEGRITY"
ERR_AUTHORIZATION_REQUIRED = "ERR_AUTHORIZATION_REQUIRED"
ERR_TRANSITION_COMMIT_FAILED = "ERR_TRANSITION_COMMIT_FAILED"
ERR_INTERNAL = "ERR_INTERNAL"  # unexpected exception, bounded — raw text stays in internal logs
ERR_NOT_ELIGIBLE = "ERR_NOT_ELIGIBLE"  # request from NORMAL / cooldown / unknown / missing state
ERR_NOT_AUTHORIZED = "ERR_NOT_AUTHORIZED"  # actor may not request/authorize this origin
ERR_IDEMPOTENCY_CONFLICT = "ERR_IDEMPOTENCY_CONFLICT"  # same key, conflicting payload
ERR_ACTIVE_PREFLIGHT_EXISTS = "ERR_ACTIVE_PREFLIGHT_EXISTS"  # one active per account

# Authority-class labels (what authority a given origin's PREFLIGHT_PASS requires).
AUTHORITY_CLASS_OWNER_OR_OPERATOR = "OWNER_OR_OPERATOR"
AUTHORITY_CLASS_OPERATOR_OR_OWNER_IF_DAILY_LOSS = "OPERATOR_OR_OWNER_IF_DAILY_LOSS"
AUTHORITY_CLASS_OPERATOR_HUMAN_APPROVAL = "OPERATOR_HUMAN_APPROVAL"  # INTEGRITY_STOP

# --- re-arm / hysteresis / dwell (ADR 0043 §D6 + §D1.4) ---------------------------------------
# Asymmetric re-arm: NO symmetric monetary band. Once locked, an account only re-arms to NORMAL
# after a class-dependent minimum dwell AND all §D1.4 conditions hold. Values are the ADR's
# conservative defaults (house convention: dwell defaults tight; a later increment may make them
# configurable — this vocabulary is data, not behaviour). The policy logic lives in
# ``state_machine.py`` (§D6), the sole sanctioned home for re-arm decisions.

# Dwell CLASS — how long an account must dwell in RECOVERY_COOLDOWN before it may re-arm, keyed to
# what it is recovering from.
DWELL_CLASS_ARTIFACT = "ARTIFACT"  # confirmed measurement artifact — fast, fixed dwell
DWELL_CLASS_RATE_VELOCITY = "RATE_VELOCITY"  # rate / loss-velocity trip — longer fixed dwell
DWELL_CLASS_CONFIRMED_DAILY_LOSS = "CONFIRMED_DAILY_LOSS"  # real daily loss — until the next session
DWELL_CLASS_INTEGRITY = "INTEGRITY"  # broker/recon/config integrity — until manual repair completes
ALL_DWELL_CLASSES: frozenset[str] = frozenset(
    {
        DWELL_CLASS_ARTIFACT,
        DWELL_CLASS_RATE_VELOCITY,
        DWELL_CLASS_CONFIRMED_DAILY_LOSS,
        DWELL_CLASS_INTEGRITY,
    }
)

# Dwell KIND — how the requirement is satisfied.
DWELL_KIND_FIXED_MINUTES = "FIXED_MINUTES"
DWELL_KIND_UNTIL_NEXT_SESSION = "UNTIL_NEXT_SESSION"
DWELL_KIND_UNTIL_MANUAL_REPAIR = "UNTIL_MANUAL_REPAIR"

# Fixed-dwell minutes (ADR §D6 conservative defaults).
DWELL_ARTIFACT_MINUTES = 15
DWELL_RATE_VELOCITY_MINUTES = 30

# Loss-velocity hysteresis (§D6): trip at the configured limit; "healthy" is a SEPARATE, stricter
# recovery threshold — at most this fraction of the trip limit, sustained for a minimum duration.
VELOCITY_RECOVERY_FRACTION = Decimal("0.5")
VELOCITY_HEALTHY_MIN_SECONDS = 600  # 10 minutes

# §D1.4 cooldown-completion verdicts (the pure policy's answer for RECOVERY_COOLDOWN).
COOLDOWN_HOLD = "HOLD"  # conditions not yet met — stay in cooldown, no re-arm
COOLDOWN_COMPLETE = "COMPLETE"  # all §D1.4 conditions hold — may transition to NORMAL
COOLDOWN_REGRESSED = "REGRESSED"  # an outright regression — fail closed to INTEGRITY_STOP
