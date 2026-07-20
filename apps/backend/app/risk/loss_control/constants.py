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

# --- versioning -------------------------------------------------------------------------------
# Bumped when the state model itself changes shape, so future migrations of persisted state are
# manageable the way RISK_POLICY_VERSION (ADR 0042) and the ledger already are (ADR 0043 §D1.3).
LOSS_CONTROL_STATE_VERSION = 1

# --- the six account-level states (materialized current-state, ADR 0043 §D1) ------------------
STATE_NORMAL = "NORMAL"
STATE_REDUCTION_ONLY_DAILY_LOSS = "REDUCTION_ONLY_DAILY_LOSS"
STATE_REDUCTION_ONLY_BREAKER = "REDUCTION_ONLY_BREAKER"
STATE_INTEGRITY_STOP = "INTEGRITY_STOP"
STATE_RECOVERY_PREFLIGHT = "RECOVERY_PREFLIGHT"
STATE_RECOVERY_COOLDOWN = "RECOVERY_COOLDOWN"

ALL_STATES: frozenset[str] = frozenset(
    {
        STATE_NORMAL,
        STATE_REDUCTION_ONLY_DAILY_LOSS,
        STATE_REDUCTION_ONLY_BREAKER,
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
ALL_TRIP_TYPES: frozenset[str] = frozenset(
    {
        TRIP_TYPE_DAILY_LOSS,
        TRIP_TYPE_CIRCUIT_BREAKER,
        TRIP_TYPE_MANUAL_HALT,
        TRIP_TYPE_CONTROL_INTEGRITY,
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
TRIP_CAUSE_UNKNOWN = "UNKNOWN"
ALL_TRIP_CAUSES: frozenset[str] = frozenset(
    {
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
