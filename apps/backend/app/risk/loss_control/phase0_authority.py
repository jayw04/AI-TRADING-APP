"""ADR-0043 Phase-0 WP1 — ExecutionPlan authority engine (offline).

Enforces AMD-15 / AMD-16 and Controlling Design v1.1 §5:

* authorized plans are immutable (except safety reduce/terminate);
* authorization lifecycle with fail-closed transitions;
* expiry and fresh-data rules from the owner freeze;
* no second independent run after a broker submission under the same authorization.

**Does not** import the order dispatch path, broker adapters, or submit orders.
"""

from __future__ import annotations

import inspect
from dataclasses import dataclass, field, replace
from datetime import datetime
from decimal import Decimal
from enum import StrEnum

from app.risk.loss_control.phase0_contracts import (
    AuthorizationState,
    ExecutionPlan,
    authorization_transition_allowed,
    compute_plan_hash,
    expiry_policy,
    fresh_data_may_mutate_plan,
)


class AuthorityRefuseReason(StrEnum):
    INVALID_TRANSITION = "INVALID_TRANSITION"
    PLAN_HASH_MISMATCH = "PLAN_HASH_MISMATCH"
    QUANTITY_INCREASE = "QUANTITY_INCREASE"
    SYMBOL_SUBSTITUTION = "SYMBOL_SUBSTITUTION"
    SIDE_SEQUENCE_CHANGE = "SIDE_SEQUENCE_CHANGE"
    EXPIRY_EXTENSION = "EXPIRY_EXTENSION"
    PLAN_REGENERATION = "PLAN_REGENERATION"
    FRESH_DATA_MUTATION = "FRESH_DATA_MUTATION"
    RISK_INCREASING_AFTER_EXPIRY = "RISK_INCREASING_AFTER_EXPIRY"
    REUSE_AFTER_BROKER_SUBMISSION = "REUSE_AFTER_BROKER_SUBMISSION"
    REUSE_AFTER_REFUSAL = "REUSE_AFTER_REFUSAL"
    NOT_ACTIVE = "NOT_ACTIVE"
    ALREADY_TERMINAL = "ALREADY_TERMINAL"


@dataclass
class AuthorityDecision:
    allowed: bool
    reason: AuthorityRefuseReason | None = None
    detail: str = ""


@dataclass
class AuthorizationRecord:
    """One authorization bound to one frozen plan hash."""

    authorization_id: str
    plan: ExecutionPlan
    plan_hash: str
    state: AuthorizationState = AuthorizationState.ISSUED
    broker_submission_count: int = 0
    legs_submitted: int = 0
    expired: bool = False
    notes: list[str] = field(default_factory=list)

    def is_terminal(self) -> bool:
        return self.state in {
            AuthorizationState.CONSUMED,
            AuthorizationState.REFUSED,
            AuthorizationState.ABORTED,
            AuthorizationState.EXPIRED,
        }


def _qty(plan: ExecutionPlan) -> Decimal:
    return Decimal(plan.max_quantity)


class PlanAuthority:
    """Guardian for a single AuthorizationRecord."""

    def __init__(self, record: AuthorizationRecord) -> None:
        if record.plan_hash != compute_plan_hash(record.plan):
            raise ValueError("AuthorizationRecord.plan_hash does not match plan contents")
        self._rec = record

    @property
    def record(self) -> AuthorizationRecord:
        return self._rec

    def transition(self, nxt: AuthorizationState) -> AuthorityDecision:
        if self._rec.is_terminal() and nxt != self._rec.state:
            return AuthorityDecision(False, AuthorityRefuseReason.ALREADY_TERMINAL)
        if not authorization_transition_allowed(self._rec.state, nxt):
            return AuthorityDecision(
                False,
                AuthorityRefuseReason.INVALID_TRANSITION,
                f"{self._rec.state} → {nxt}",
            )
        self._rec.state = nxt
        if nxt == AuthorizationState.EXPIRED:
            self._rec.expired = True
        return AuthorityDecision(True)

    def claim(self) -> AuthorityDecision:
        return self.transition(AuthorizationState.CLAIMED)

    def activate(self) -> AuthorityDecision:
        return self.transition(AuthorizationState.ACTIVE)

    def refuse(self) -> AuthorityDecision:
        return self.transition(AuthorizationState.REFUSED)

    def abort(self) -> AuthorityDecision:
        if self._rec.state == AuthorizationState.ACTIVE:
            return self.transition(AuthorizationState.ABORTED)
        if self._rec.state == AuthorizationState.CLAIMED:
            return self.transition(AuthorizationState.ABORTED)
        return AuthorityDecision(
            False,
            AuthorityRefuseReason.INVALID_TRANSITION,
            f"abort from {self._rec.state}",
        )

    def mark_expired(self) -> AuthorityDecision:
        return self.transition(AuthorizationState.EXPIRED)

    def note_broker_submission(self) -> AuthorityDecision:
        """Record a broker submission under this authorization (simulated offline)."""
        if self._rec.state != AuthorizationState.ACTIVE:
            return AuthorityDecision(False, AuthorityRefuseReason.NOT_ACTIVE)
        self._rec.broker_submission_count += 1
        self._rec.legs_submitted += 1
        return AuthorityDecision(True)

    def consume(self) -> AuthorityDecision:
        return self.transition(AuthorizationState.CONSUMED)

    def assert_plan_unmodified(self, candidate: ExecutionPlan) -> AuthorityDecision:
        """Refuse any material mutation of the frozen plan under this authorization."""
        cand_hash = compute_plan_hash(candidate)
        if cand_hash == self._rec.plan_hash:
            return AuthorityDecision(True)
        base = self._rec.plan
        if candidate.symbol != base.symbol:
            return AuthorityDecision(False, AuthorityRefuseReason.SYMBOL_SUBSTITUTION)
        if candidate.side_sequence != base.side_sequence:
            return AuthorityDecision(False, AuthorityRefuseReason.SIDE_SEQUENCE_CHANGE)
        if _qty(candidate) > _qty(base):
            return AuthorityDecision(False, AuthorityRefuseReason.QUANTITY_INCREASE)
        if candidate.expires_at > base.expires_at:
            return AuthorityDecision(False, AuthorityRefuseReason.EXPIRY_EXTENSION)
        if candidate.plan_id != base.plan_id:
            return AuthorityDecision(False, AuthorityRefuseReason.PLAN_REGENERATION)
        return AuthorityDecision(False, AuthorityRefuseReason.PLAN_HASH_MISMATCH)

    def allow_quantity_reduction(self, new_qty: Decimal) -> AuthorityDecision:
        if self._rec.state != AuthorizationState.ACTIVE:
            return AuthorityDecision(False, AuthorityRefuseReason.NOT_ACTIVE)
        if new_qty < 0 or new_qty > _qty(self._rec.plan):
            return AuthorityDecision(False, AuthorityRefuseReason.QUANTITY_INCREASE)
        return AuthorityDecision(True)

    def allow_fresh_data_for_safety(self) -> AuthorityDecision:
        if fresh_data_may_mutate_plan():
            return AuthorityDecision(False, AuthorityRefuseReason.FRESH_DATA_MUTATION)
        return AuthorityDecision(True, detail="safety_reads_ok_no_authority_expansion")

    def allow_leg(self, *, risk_increasing: bool, now: datetime) -> AuthorityDecision:
        """Gate a proposed leg under current auth state / expiry policy."""
        if self._rec.state == AuthorizationState.REFUSED:
            return AuthorityDecision(False, AuthorityRefuseReason.REUSE_AFTER_REFUSAL)

        if self._rec.state == AuthorizationState.CONSUMED:
            return AuthorityDecision(False, AuthorityRefuseReason.REUSE_AFTER_BROKER_SUBMISSION)

        expired = self._rec.expired or now >= self._rec.plan.expires_at
        if expired:
            if (
                self._rec.state == AuthorizationState.ACTIVE
                and not self._rec.expired
            ):
                tr = self.transition(AuthorizationState.EXPIRED)
                if not tr.allowed and self._rec.state != AuthorizationState.EXPIRED:
                    return tr
            self._rec.expired = True
            policy = expiry_policy(any_leg_submitted=self._rec.legs_submitted > 0)
            if risk_increasing and not policy.allow_risk_increasing:
                return AuthorityDecision(
                    False, AuthorityRefuseReason.RISK_INCREASING_AFTER_EXPIRY
                )
            if not risk_increasing and not (
                policy.allow_risk_reducing_completion or policy.allow_emergency_flatten
            ):
                return AuthorityDecision(
                    False, AuthorityRefuseReason.RISK_INCREASING_AFTER_EXPIRY
                )
            return AuthorityDecision(True, detail="post_expiry_risk_reducing_only")

        if self._rec.state != AuthorizationState.ACTIVE:
            return AuthorityDecision(False, AuthorityRefuseReason.NOT_ACTIVE)
        return AuthorityDecision(True)

    def start_second_independent_run(self) -> AuthorityDecision:
        """AMD-16: auth that produced a broker submission may not authorize a second run."""
        if self._rec.broker_submission_count > 0:
            return AuthorityDecision(False, AuthorityRefuseReason.REUSE_AFTER_BROKER_SUBMISSION)
        if self._rec.state == AuthorizationState.REFUSED:
            return AuthorityDecision(False, AuthorityRefuseReason.REUSE_AFTER_REFUSAL)
        return AuthorityDecision(False, AuthorityRefuseReason.ALREADY_TERMINAL)


def issue_authorization(*, authorization_id: str, plan: ExecutionPlan) -> PlanAuthority:
    rec = AuthorizationRecord(
        authorization_id=authorization_id,
        plan=plan,
        plan_hash=compute_plan_hash(plan),
        state=AuthorizationState.ISSUED,
    )
    return PlanAuthority(rec)


def with_extended_expiry(plan: ExecutionPlan, new_expires: datetime) -> ExecutionPlan:
    """Test helper — produces a mutated plan (must be refused by authority)."""
    return replace(plan, expires_at=new_expires)


def assert_no_order_path_imports() -> None:
    """Structural guard: this module must not import order-path packages."""
    import app.risk.loss_control.phase0_authority as mod

    src = inspect.getsource(mod)
    # Build needles without embedding the forbidden import lines verbatim in this function
    # (otherwise the guard would match itself).
    needles = [
        "from app." + "services.order_router",
        "import app." + "services.order_router",
        "from app." + "brokers",
        "import app." + "brokers",
        "from app." + "orders",
        "submit_" + "order(",
    ]
    for needle in needles:
        if needle in src:
            raise AssertionError(f"phase0_authority must not reference {needle}")


__all__ = [
    "AuthorityDecision",
    "AuthorityRefuseReason",
    "AuthorizationRecord",
    "PlanAuthority",
    "assert_no_order_path_imports",
    "issue_authorization",
    "with_extended_expiry",
]
