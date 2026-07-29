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
from app.risk.loss_control.phase0_contracts import (
    PLAN_SCHEMA_VERSION,
    AuthorizationState,
    ExecutionPlan,
)


def _plan(**over) -> ExecutionPlan:
    base = dict(
        plan_id="plan-1",
        plan_schema_version=PLAN_SCHEMA_VERSION,
        created_at=datetime(2026, 7, 29, 14, 0, tzinfo=UTC),
        expires_at=datetime(2026, 7, 29, 15, 0, tzinfo=UTC),
        quote_evidence_hash="sha256:q",
        model_artifact_hash="sha256:m",
        authorization_id="auth-1",
        authorization_scope="account:3",
        account_id=3,
        broker_account_id="PA34USW0Q8UO",
        session_date="2026-07-29",
        symbol="KOKU",
        side_sequence=("buy", "sell"),
        quantity="190",
        order_type="limit",
        time_in_force="day",
        route="alpaca",
        max_round_trips=12,
        maximum_authorized_legs=2,
        max_setup_notional="25000",
        max_position_qty="1000",
        baseline_id="baseline-1",
        loss_target="3000",
        remaining_target_at_verdict="3000",
        limits_digest="sha256:limits",
        loss_control_state_version=4,
        deployment_commit="deadbeef",
        implementation_commit="cafebabe",
    )
    base.update(over)
    return ExecutionPlan(**base)  # type: ignore[arg-type]


def _active_auth(**plan_over):
    auth = issue_authorization(authorization_id="auth-1", plan=_plan(**plan_over))
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
    auth = issue_authorization(authorization_id="auth-2", plan=_plan(authorization_id="auth-2"))
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
    assert auth.record.state is AuthorizationState.EXPIRED_UNEXECUTED
    d2 = auth.allow_leg(risk_increasing=False, now=after)
    assert not d2.allowed


def test_expiry_after_partial_allows_risk_reducing_lifecycle() -> None:
    auth = _active_auth()
    assert auth.note_broker_submission().allowed
    after = datetime(2026, 7, 29, 15, 1, tzinfo=UTC)
    assert not auth.allow_leg(risk_increasing=True, now=after).allowed
    d = auth.allow_leg(risk_increasing=False, now=after)
    assert d.allowed
    assert auth.record.state is AuthorizationState.ACTIVE_RISK_REDUCING_ONLY
    assert auth.note_broker_submission().allowed
    assert auth.consume().allowed
    assert auth.record.state is AuthorizationState.CONSUMED


def test_quantity_increase_and_symbol_swap_refused() -> None:
    auth = _active_auth()
    bigger = _plan(quantity="191")
    d = auth.assert_plan_unmodified(bigger)
    assert not d.allowed and d.reason is AuthorityRefuseReason.QUANTITY_INCREASE
    swap = _plan(symbol="IEUS")
    d2 = auth.assert_plan_unmodified(swap)
    assert not d2.allowed and d2.reason is AuthorityRefuseReason.SYMBOL_SUBSTITUTION


def test_route_and_order_type_in_hash_and_refused() -> None:
    auth = _active_auth()
    assert not auth.assert_plan_unmodified(_plan(route="other")).allowed
    assert (
        auth.assert_plan_unmodified(_plan(route="other")).reason
        is AuthorityRefuseReason.ROUTE_CHANGE
    )
    assert (
        auth.assert_plan_unmodified(_plan(order_type="market")).reason
        is AuthorityRefuseReason.ORDER_TYPE_CHANGE
    )


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
    assert auth.allow_fresh_data_for_safety().allowed


def test_hash_mismatch_generic() -> None:
    auth = _active_auth()
    other = _plan(quote_evidence_hash="sha256:other")
    d = auth.assert_plan_unmodified(other)
    assert not d.allowed
    assert d.reason is AuthorityRefuseReason.PLAN_HASH_MISMATCH


def test_maximum_authorized_legs_enforced() -> None:
    auth = _active_auth(maximum_authorized_legs=2)
    now = datetime(2026, 7, 29, 14, 30, tzinfo=UTC)
    assert auth.allow_leg(risk_increasing=True, now=now).allowed
    assert auth.note_broker_submission().allowed  # leg 1
    assert auth.allow_leg(risk_increasing=True, now=now).allowed
    assert auth.note_broker_submission().allowed  # leg 2 (exact final)
    d = auth.allow_leg(risk_increasing=True, now=now)
    assert not d.allowed
    assert d.reason is AuthorityRefuseReason.MAXIMUM_AUTHORIZED_LEGS_EXHAUSTED
    d2 = auth.note_broker_submission()
    assert not d2.allowed
    assert d2.reason is AuthorityRefuseReason.MAXIMUM_AUTHORIZED_LEGS_EXHAUSTED


def test_no_order_path_imports() -> None:
    assert_no_order_path_imports()


def test_invalid_transition_issued_to_active() -> None:
    auth = issue_authorization(authorization_id="auth-1", plan=_plan())
    d = auth.activate()
    assert not d.allowed
    assert d.reason is AuthorityRefuseReason.INVALID_TRANSITION
