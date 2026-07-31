"""Offline tests for ADR-0043 Phase-0 controlling-design contracts."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest

from app.risk.loss_control.phase0_contracts import (
    ALPACA_PAPER_FILL_TIER,
    PLAN_SCHEMA_VERSION,
    TIER_B_PAPER_OR_EXECUTABLE_ESTIMATE,
    VERDICT_INDETERMINATE,
    VERDICT_UNREACHABLE_WITHIN_CAPS,
    AuthorizationState,
    ExecutionPlan,
    FalseReachableSeverity,
    authorization_transition_allowed,
    classify_false_reachable,
    compute_plan_hash,
    contracts_manifest,
    expiry_policy,
    fresh_data_may_mutate_plan,
    normalize_round_trip_loss_amount,
    o4a_expected_verdict_and_reason,
    o4b_expected_verdict,
    sample_planning_floors,
)


def _plan(**over) -> ExecutionPlan:
    base = dict(
        plan_id="p1",
        plan_schema_version=PLAN_SCHEMA_VERSION,
        created_at=datetime(2026, 7, 29, 15, 0, tzinfo=UTC),
        expires_at=datetime(2026, 7, 29, 16, 0, tzinfo=UTC),
        quote_evidence_hash="sha256:abc",
        model_artifact_hash="sha256:def",
        authorization_id="auth-1",
        authorization_scope="account:3",
        account_id=3,
        broker_account_id="PA34",
        session_date="2026-07-29",
        symbol="SPY",
        side_sequence=("sell", "buy"),
        quantity="10",
        order_type="limit",
        time_in_force="day",
        route="alpaca",
        max_round_trips=12,
        maximum_authorized_legs=2,
        max_setup_notional="25000",
        max_position_qty="1000",
        baseline_id="b1",
        loss_target="3000",
        remaining_target_at_verdict="3000",
        limits_digest="sha256:lim",
        loss_control_state_version=0,
        deployment_commit="d1",
        implementation_commit="i1",
    )
    base.update(over)
    return ExecutionPlan(**base)  # type: ignore[arg-type]


def test_false_reachable_severity_splits() -> None:
    assert classify_false_reachable(Decimal("1")) is FalseReachableSeverity.NONE
    assert classify_false_reachable(Decimal("0.90")) is FalseReachableSeverity.MARGINAL
    assert classify_false_reachable(Decimal("0.80")) is FalseReachableSeverity.MARGINAL
    assert classify_false_reachable(Decimal("0.799")) is FalseReachableSeverity.CRITICAL


def test_non_negative_loss_rejects_signed_optimistic() -> None:
    assert normalize_round_trip_loss_amount(Decimal("12.5")) == Decimal("12.5")
    with pytest.raises(ValueError, match="≥ 0"):
        normalize_round_trip_loss_amount(Decimal("-1"))


def test_alpaca_paper_fills_are_tier_b() -> None:
    assert ALPACA_PAPER_FILL_TIER == TIER_B_PAPER_OR_EXECUTABLE_ESTIMATE


def test_d1_o4_expectations() -> None:
    v, r = o4a_expected_verdict_and_reason(model_available=True)
    assert v == VERDICT_INDETERMINATE
    assert r == "INSUFFICIENT_EXECUTION_COST"
    v2, r2 = o4a_expected_verdict_and_reason(model_available=False)
    assert v2 == VERDICT_INDETERMINATE and r2 == "MODEL_UNAVAILABLE"
    assert o4b_expected_verdict() == VERDICT_UNREACHABLE_WITHIN_CAPS


def test_expiry_policy_partial_vs_pre_submit() -> None:
    pre = expiry_policy(any_leg_submitted=False)
    assert pre.allow_risk_reducing_completion is False
    post = expiry_policy(any_leg_submitted=True)
    assert post.allow_risk_reducing_completion is True


def test_auth_lifecycle_includes_risk_reducing_state() -> None:
    assert authorization_transition_allowed(
        AuthorizationState.ACTIVE, AuthorizationState.ACTIVE_RISK_REDUCING_ONLY
    )
    assert authorization_transition_allowed(
        AuthorizationState.ACTIVE_RISK_REDUCING_ONLY, AuthorizationState.CONSUMED
    )
    assert not authorization_transition_allowed(
        AuthorizationState.EXPIRED_UNEXECUTED, AuthorizationState.ACTIVE
    )


def test_plan_hash_includes_route_caps_and_account() -> None:
    plan = _plan()
    h1 = compute_plan_hash(plan)
    assert h1 == compute_plan_hash(plan) and h1.startswith("sha256:")
    assert compute_plan_hash(_plan(route="other")) != h1
    assert compute_plan_hash(_plan(account_id=1)) != h1
    assert compute_plan_hash(_plan(loss_target="2999")) != h1
    assert fresh_data_may_mutate_plan() is False


def test_sample_floors_and_manifest() -> None:
    floors = sample_planning_floors()
    assert floors["pooled_binding_reachable_plans"] == 59
    m = contracts_manifest()
    assert m["plan_schema_version"] == PLAN_SCHEMA_VERSION
    assert "REACHABLE" in m["verdicts"]
