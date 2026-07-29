"""ADR-0043 Phase-0 offline contracts (Controlling Design v1.1).

Pure vocabulary + plan/authorization helpers. **Not wired into OrderRouter or broker
submission.** Implements frozen AMD/owner rules for:

* verdict + reason-code schema (AMD-14, D1)
* non-negative loss amount (AMD-13)
* ExecutionPlan hash / immutability fields (AMD-15)
* authorization lifecycle (AMD-16) including expiry-after-partial rules (owner mod §3.3)
* false-reachable severity (AMD-01 + owner mod §3.1)

See ``docs/design/ADR0043_Phase0_Controlling_Design_v1.1.md``.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any

PHASE0_CONTRACTS_SCHEMA_VERSION = 1

# --- verdicts (canonical) --------------------------------------------------------------------

VERDICT_REACHABLE = "REACHABLE"
VERDICT_UNREACHABLE_WITHIN_CAPS = "UNREACHABLE_WITHIN_CAPS"
VERDICT_INDETERMINATE = "INDETERMINATE"

# Legacy alias used by older reachability scripts — map at boundaries, do not emit in new paths.
LEGACY_VERDICT_BREACH_UNREACHABLE = "BREACH_UNREACHABLE"

ALL_VERDICTS: frozenset[str] = frozenset(
    {
        VERDICT_REACHABLE,
        VERDICT_UNREACHABLE_WITHIN_CAPS,
        VERDICT_INDETERMINATE,
    }
)

# --- reason codes ----------------------------------------------------------------------------

REASON_INSUFFICIENT_EXECUTION_COST = "INSUFFICIENT_EXECUTION_COST"
REASON_ROUND_TRIP_CAP = "ROUND_TRIP_CAP"
REASON_NOTIONAL_CAP = "NOTIONAL_CAP"
REASON_POSITION_CAP = "POSITION_CAP"
REASON_MARKET_CLOSED = "MARKET_CLOSED"
REASON_STALE_EVIDENCE = "STALE_EVIDENCE"
REASON_TIMESTAMP_CONTRADICTION = "TIMESTAMP_CONTRADICTION"
REASON_MODEL_UNAVAILABLE = "MODEL_UNAVAILABLE"
REASON_ALREADY_BREACHED = "ALREADY_BREACHED"
REASON_CONDITIONS_CHANGED_POST_PLAN = "CONDITIONS_CHANGED_POST_PLAN"
REASON_EXECUTION_FAILURE_NON_MODEL = "EXECUTION_FAILURE_NON_MODEL"

ALL_REASON_CODES: frozenset[str] = frozenset(
    {
        REASON_INSUFFICIENT_EXECUTION_COST,
        REASON_ROUND_TRIP_CAP,
        REASON_NOTIONAL_CAP,
        REASON_POSITION_CAP,
        REASON_MARKET_CLOSED,
        REASON_STALE_EVIDENCE,
        REASON_TIMESTAMP_CONTRADICTION,
        REASON_MODEL_UNAVAILABLE,
        REASON_ALREADY_BREACHED,
        REASON_CONDITIONS_CHANGED_POST_PLAN,
        REASON_EXECUTION_FAILURE_NON_MODEL,
    }
)

# --- evidence tiers (controlling design §3.2) ------------------------------------------------

TIER_A_LIVE_MARKET_FILLS = "A"
TIER_B_PAPER_OR_EXECUTABLE_ESTIMATE = "B"
TIER_C_QUOTE_DERIVED = "C"
TIER_D_DISPLAYED_SPREAD = "D"

#: Alpaca paper-account fills on the Phase-0 stack are Tier B, never Tier A.
ALPACA_PAPER_FILL_TIER = TIER_B_PAPER_OR_EXECUTABLE_ESTIMATE

# --- false-reachable severity ----------------------------------------------------------------

CRITICAL_FALSE_REACHABLE_FRACTION = Decimal("0.80")  # below this → CRITICAL
# Initial sealed validation: zero marginal cases permitted (owner freeze).
INITIAL_MARGINAL_FALSE_REACHABLE_TOLERANCE = 0


class FalseReachableSeverity(StrEnum):
    CRITICAL = "CRITICAL"
    MARGINAL = "MARGINAL"
    NONE = "NONE"  # achieved ≥ 100% of remaining target


def classify_false_reachable(
    achieved_fraction_of_remaining_target: Decimal,
) -> FalseReachableSeverity:
    """Classify plan-level false-reachable severity.

    Any fraction strictly below 1 is a false reachable; severity splits at 80%.
    """
    if achieved_fraction_of_remaining_target >= Decimal("1"):
        return FalseReachableSeverity.NONE
    if achieved_fraction_of_remaining_target < CRITICAL_FALSE_REACHABLE_FRACTION:
        return FalseReachableSeverity.CRITICAL
    return FalseReachableSeverity.MARGINAL


def normalize_round_trip_loss_amount(amount: Decimal) -> Decimal:
    """Enforce non-negative canonical loss (AMD-13). Negative input is rejected."""
    if amount < 0:
        raise ValueError(
            "round_trip_loss_amount must be ≥ 0 (conservative minimum supported loss); "
            f"got {amount}"
        )
    return amount


# --- authorization lifecycle -----------------------------------------------------------------


class AuthorizationState(StrEnum):
    ISSUED = "ISSUED"
    CLAIMED = "CLAIMED"
    ACTIVE = "ACTIVE"
    CONSUMED = "CONSUMED"
    REFUSED = "REFUSED"
    ABORTED = "ABORTED"
    EXPIRED = "EXPIRED"


_AUTH_FORWARD: dict[AuthorizationState, frozenset[AuthorizationState]] = {
    AuthorizationState.ISSUED: frozenset(
        {
            AuthorizationState.CLAIMED,
            AuthorizationState.REFUSED,
            AuthorizationState.EXPIRED,
        }
    ),
    AuthorizationState.CLAIMED: frozenset(
        {
            AuthorizationState.ACTIVE,
            AuthorizationState.REFUSED,
            AuthorizationState.ABORTED,
            AuthorizationState.EXPIRED,
        }
    ),
    AuthorizationState.ACTIVE: frozenset(
        {
            AuthorizationState.CONSUMED,
            AuthorizationState.ABORTED,
            AuthorizationState.EXPIRED,
        }
    ),
    AuthorizationState.CONSUMED: frozenset(),
    AuthorizationState.REFUSED: frozenset(),
    AuthorizationState.ABORTED: frozenset(),
    AuthorizationState.EXPIRED: frozenset(),
}


def authorization_transition_allowed(current: AuthorizationState, nxt: AuthorizationState) -> bool:
    return nxt in _AUTH_FORWARD.get(current, frozenset())


@dataclass(frozen=True)
class ExpiryPolicyDecision:
    """Owner-mod §3.3: what expiry permits after partial execution."""

    allow_risk_increasing: bool
    allow_risk_reducing_completion: bool
    allow_emergency_flatten: bool
    record_expiry_exception: bool
    require_recovery_reconciliation: bool


def expiry_policy(*, any_leg_submitted: bool) -> ExpiryPolicyDecision:
    """Return fail-closed expiry policy.

    Before any submission: refuse further work (no new legs).
    After partial fill: block risk-increasing; allow risk-reducing / flatten.
    """
    if not any_leg_submitted:
        return ExpiryPolicyDecision(
            allow_risk_increasing=False,
            allow_risk_reducing_completion=False,
            allow_emergency_flatten=False,
            record_expiry_exception=True,
            require_recovery_reconciliation=False,
        )
    return ExpiryPolicyDecision(
        allow_risk_increasing=False,
        allow_risk_reducing_completion=True,
        allow_emergency_flatten=True,
        record_expiry_exception=True,
        require_recovery_reconciliation=True,
    )


# --- ExecutionPlan ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ExecutionPlan:
    """Immutable authorized plan fields (AMD-15). Driver may not mutate after authorize."""

    plan_id: str
    plan_schema_version: int
    created_at: datetime
    expires_at: datetime
    quote_evidence_hash: str
    model_artifact_hash: str
    authorization_scope: str
    maximum_authorized_legs: int
    symbol: str
    side_sequence: tuple[str, ...]  # e.g. ("sell", "buy") for a round trip
    max_quantity: str  # Decimal as string for stable hashing
    # plan_hash is derived; callers should use ``with_hash`` / ``compute_plan_hash``.

    def canonical_dict(self) -> dict[str, Any]:
        return {
            "plan_id": self.plan_id,
            "plan_schema_version": self.plan_schema_version,
            "created_at": self.created_at.isoformat(),
            "expires_at": self.expires_at.isoformat(),
            "quote_evidence_hash": self.quote_evidence_hash,
            "model_artifact_hash": self.model_artifact_hash,
            "authorization_scope": self.authorization_scope,
            "maximum_authorized_legs": self.maximum_authorized_legs,
            "symbol": self.symbol,
            "side_sequence": list(self.side_sequence),
            "max_quantity": self.max_quantity,
        }


def compute_plan_hash(plan: ExecutionPlan | Mapping[str, Any]) -> str:
    payload = plan.canonical_dict() if isinstance(plan, ExecutionPlan) else dict(plan)
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def fresh_data_may_mutate_plan() -> bool:
    """Controlling design §3.4 — always False; safety reads cannot expand authority."""
    return False


def o4a_expected_verdict_and_reason(*, model_available: bool) -> tuple[str, str]:
    """D1 decision-time expectation when only Tier-D / insufficient cost evidence exists."""
    if not model_available:
        return VERDICT_INDETERMINATE, REASON_MODEL_UNAVAILABLE
    return VERDICT_INDETERMINATE, REASON_INSUFFICIENT_EXECUTION_COST


def o4b_expected_verdict() -> str:
    return VERDICT_UNREACHABLE_WITHIN_CAPS


def sample_planning_floors() -> dict[str, int]:
    """D2 provisional floors (planning only)."""
    return {
        "pooled_binding_reachable_plans": 59,
        "per_intended_symbol_stratum": 20,
        "shadow_sessions": 10,
        "initial_marginal_false_reachable_tolerance": INITIAL_MARGINAL_FALSE_REACHABLE_TOLERANCE,
    }


def contracts_manifest() -> dict[str, Any]:
    return {
        "schema_version": PHASE0_CONTRACTS_SCHEMA_VERSION,
        "controlling_design_id": "ADR0043-PH0-CTRL-001 v1.1",
        "verdicts": sorted(ALL_VERDICTS),
        "reason_codes": sorted(ALL_REASON_CODES),
        "alpaca_paper_fill_tier": ALPACA_PAPER_FILL_TIER,
        "sample_floors": sample_planning_floors(),
        "fresh_data_may_mutate_plan": fresh_data_may_mutate_plan(),
    }


__all__ = [
    "ALPACA_PAPER_FILL_TIER",
    "ALL_REASON_CODES",
    "ALL_VERDICTS",
    "AuthorizationState",
    "ExecutionPlan",
    "ExpiryPolicyDecision",
    "FalseReachableSeverity",
    "LEGACY_VERDICT_BREACH_UNREACHABLE",
    "PHASE0_CONTRACTS_SCHEMA_VERSION",
    "authorization_transition_allowed",
    "classify_false_reachable",
    "compute_plan_hash",
    "contracts_manifest",
    "expiry_policy",
    "fresh_data_may_mutate_plan",
    "normalize_round_trip_loss_amount",
    "o4a_expected_verdict_and_reason",
    "o4b_expected_verdict",
    "sample_planning_floors",
]
