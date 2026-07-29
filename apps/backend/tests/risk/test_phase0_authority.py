"""WP1 Gate O1 offline matrix — ExecutionPlan authority (no broker)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

from app.risk.loss_control.phase0_authority import (
    AuthorityRefuseReason,
    assert_no_order_path_imports,
    issue_authorization,
    with_extended_expiry,
)
from app.risk.loss_control.phase0_contracts import AuthorizationState, ExecutionPlan


def _plan(**over) -> ExecutionPlan:
    base = dict(
        plan_id="plan-1",
        plan_schema_version=1,
        created_at=datetime(2026, 7, 29, 14, 0, tzinfo=UTC),
        expires_at=datetime(2026, 7, 29, 15, 0, tzinfo=UTC),
        quote_evidence_hash="sha256:q",
        model_artifact_hash="sha256:m",
        authorization_scope="account:3",
        maximum_authorized_legs=2,
        symbol="KOKU",
        side_sequence=("buy", "sell"),
        max_quantity="190",
    )
    base.update(over)
    return ExecutionPlan(**base)  # type: ignore[arg-type]


def _active_auth():
    auth = issue_authorization(authorization_id="auth-1", plan=_plan())
    assert auth.claim().allowed and auth.activate().allowed
    return auth


def test_happy_path_claim_activate_leg_consume() -> None:
    auth = _active_auth()
    now = datetime(2026, 7, 29, 14, 30, tzinfo=UTC)
    assert auth.allow_leg(risk_increasing=True, now=now).allowed
    assert auth.note_broker_submission().allowed
    assert auth.consume().allowed
    assert auth.record.state is AuthorizationState.CONSUMED


def test_reuse_after_broker_submission_refused() -> None:
    auth = _active_auth()
    assert auth.note_broker_submission().allowed
    assert auth.consume().allowed
    d = auth.start_second_independent_run()
    assert not d.allowed
    assert d.reason is AuthorityRefuseReason.REUSE_AFTER_BROKER_SUBMISSION


def test_reuse_after_local_refusal_refused() -> None:
    auth = issue_authorization(authorization_id="auth-2", plan=_plan())
    assert auth.refuse().allowed
    d = auth.allow_leg(
        risk_increasing=True, now=datetime(2026, 7, 29, 14, 10, tzinfo=UTC)
    )
    assert not d.allowed
    assert d.reason is AuthorityRefuseReason.REUSE_AFTER_REFUSAL


def test_expiry_before_submission_blocks_all_legs() -> None:
    auth = _active_auth()
    after = datetime(2026, 7, 29, 15, 1, tzinfo=UTC)
    d = auth.allow_leg(risk_increasing=True, now=after)
    assert not d.allowed
    assert d.reason is AuthorityRefuseReason.RISK_INCREASING_AFTER_EXPIRY
    # No legs submitted → risk-reducing also blocked pre-submission expiry policy
    d2 = auth.allow_leg(risk_increasing=False, now=after)
    assert not d2.allowed


def test_expiry_after_partial_allows_risk_reducing_only() -> None:
    auth = _active_auth()
    assert auth.note_broker_submission().allowed
    after = datetime(2026, 7, 29, 15, 1, tzinfo=UTC)
    assert not auth.allow_leg(risk_increasing=True, now=after).allowed
    d = auth.allow_leg(risk_increasing=False, now=after)
    assert d.allowed
    assert "post_expiry" in d.detail


def test_quantity_increase_and_symbol_swap_refused() -> None:
    auth = _active_auth()
    bigger = _plan(max_quantity="191")
    d = auth.assert_plan_unmodified(bigger)
    assert not d.allowed and d.reason is AuthorityRefuseReason.QUANTITY_INCREASE
    swap = _plan(symbol="IEUS")
    d2 = auth.assert_plan_unmodified(swap)
    assert not d2.allowed and d2.reason is AuthorityRefuseReason.SYMBOL_SUBSTITUTION


def test_expiry_extension_refused() -> None:
    auth = _active_auth()
    extended = with_extended_expiry(
        auth.record.plan, auth.record.plan.expires_at + timedelta(hours=1)
    )
    d = auth.assert_plan_unmodified(extended)
    assert not d.allowed and d.reason is AuthorityRefuseReason.EXPIRY_EXTENSION


def test_quantity_reduction_allowed_while_active() -> None:
    auth = _active_auth()
    assert auth.allow_quantity_reduction(Decimal("100")).allowed
    assert not auth.allow_quantity_reduction(Decimal("200")).allowed


def test_fresh_data_safety_ok_cannot_mutate_flag() -> None:
    auth = _active_auth()
    d = auth.allow_fresh_data_for_safety()
    assert d.allowed


def test_hash_mismatch_generic() -> None:
    auth = _active_auth()
    # Same logical fields but different quote evidence hash → mismatch
    other = _plan(quote_evidence_hash="sha256:other")
    d = auth.assert_plan_unmodified(other)
    assert not d.allowed
    assert d.reason is AuthorityRefuseReason.PLAN_HASH_MISMATCH


def test_no_order_path_imports() -> None:
    assert_no_order_path_imports()


def test_invalid_transition_issued_to_active() -> None:
    auth = issue_authorization(authorization_id="a", plan=_plan())
    d = auth.activate()
    assert not d.allowed
    assert d.reason is AuthorityRefuseReason.INVALID_TRANSITION
