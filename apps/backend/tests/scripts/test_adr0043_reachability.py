"""ADR 0043 Phase-0 reachability — hermetic regressions + WP2 plan-binding (CORR-02).

Tier D never binding. Tier A–C binding requires a frozen ExecutionPlan; multi-symbol
max-over-symbols is diagnostic only.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal as D

import pytest

from app.risk.loss_control.phase0_contracts import (
    PLAN_SCHEMA_VERSION,
    REASON_INSUFFICIENT_EXECUTION_COST,
    REASON_ROUND_TRIP_CAP,
    TIER_C_QUOTE_DERIVED,
    TIER_D_DISPLAYED_SPREAD,
    ExecutionPlan,
    compute_plan_hash,
)
from scripts.adr0043_reachability import (
    VERDICT_INDETERMINATE,
    VERDICT_REACHABLE,
    VERDICT_UNREACHABLE,
    VERDICT_UNREACHABLE_WITHIN_CAPS,
    Caps,
    assess,
    price_symbol,
    remaining_to_target,
)

CAPS = Caps(
    loss_target=D("3000"),
    max_round_trips=12,
    max_setup_notional=D("25000"),
    max_position_qty=D("1000"),
)


def _quote(bid="128.09", ask="131.03", age="2"):
    return {"bid": bid, "ask": ask, "age_s": age}


def _plan(**over) -> ExecutionPlan:
    base = dict(
        plan_id="plan-koku",
        plan_schema_version=PLAN_SCHEMA_VERSION,
        created_at=datetime(2026, 7, 29, 14, 0, tzinfo=UTC),
        expires_at=datetime(2026, 7, 29, 15, 0, tzinfo=UTC),
        quote_evidence_hash="sha256:q",
        model_artifact_hash="sha256:m",
        authorization_id="auth-1",
        authorization_scope="account:3",
        account_id=3,
        broker_account_id="PA34",
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
        baseline_id="b1",
        loss_target="3000",
        remaining_target_at_verdict="2854.08",
        limits_digest="sha256:lim",
        loss_control_state_version=4,
        deployment_commit="d1",
        implementation_commit="i1",
    )
    base.update(over)
    return ExecutionPlan(**base)  # type: ignore[arg-type]


def test_a_fresh_two_sided_quote_prices_the_round_trip():
    r = price_symbol("KOKU", _quote(), CAPS)
    assert r.priced and r.fresh
    assert r.sized_shares == D("190")
    assert r.loss_per_round_trip == D("558.60")


@pytest.mark.parametrize(
    ("quote", "expect"),
    [
        (None, "no governed quote"),
        (_quote(ask=None), "one-sided"),
        (_quote(bid=None), "one-sided"),
        (_quote(age="45"), "old"),
        (_quote(age=None), "no age"),
        (_quote(bid="0"), "non-positive"),
        (_quote(bid="140", ask="130"), "crossed"),
    ],
)
def test_an_untrustworthy_quote_prices_nothing(quote, expect):
    r = price_symbol("IEUS", quote, CAPS)
    assert not r.priced
    assert r.unusable_reason is not None and expect in r.unusable_reason


def test_the_notional_cap_bounds_the_size_not_the_other_way_round():
    r = price_symbol("EXPENSIVE", _quote(bid="30000", ask="30001"), CAPS)
    assert not r.priced and "zero shares" in (r.unusable_reason or "")


def test_position_qty_cap_binds_when_it_is_the_tighter_one():
    r = price_symbol("CHEAP", _quote(bid="1.00", ask="1.10"), CAPS)
    assert r.sized_shares == CAPS.max_position_qty


def test_a_gain_increases_the_distance_to_the_target():
    assert remaining_to_target(D("500"), D("3000")) == D("3500")


def test_a_loss_already_taken_reduces_the_distance():
    assert remaining_to_target(D("-1200"), D("3000")) == D("1800")


def test_an_unknown_day_change_yields_an_unknown_distance():
    assert remaining_to_target(None, D("3000")) is None


def test_tier_d_projected_reachable_is_indeterminate_non_binding():
    r = assess(
        day_change=D("-145.92"),
        quotes={"KOKU": _quote(), "IEUS": _quote(bid="66.80", ask="66.94")},
        symbols=["KOKU", "IEUS"],
        caps=CAPS,
    )
    assert r.evidence_tier == TIER_D_DISPLAYED_SPREAD
    assert r.verdict == VERDICT_INDETERMINATE
    assert r.binding is False
    assert r.reason_code == REASON_INSUFFICIENT_EXECUTION_COST


def test_tier_c_cannot_bind_without_execution_plan():
    r = assess(
        day_change=D("-145.92"),
        quotes={"KOKU": _quote()},
        symbols=["KOKU"],
        caps=CAPS,
        evidence_tier=TIER_C_QUOTE_DERIVED,
    )
    assert r.binding is False
    assert r.plan_id is None


def test_tier_c_binds_with_frozen_execution_plan():
    plan = _plan()
    r = assess(
        day_change=D("-145.92"),
        quotes={"KOKU": _quote()},
        symbols=["KOKU"],
        caps=CAPS,
        evidence_tier=TIER_C_QUOTE_DERIVED,
        execution_plan=plan,
    )
    assert r.verdict == VERDICT_REACHABLE and r.binding is True
    assert r.plan_id == plan.plan_id
    assert r.plan_hash == compute_plan_hash(plan)
    assert r.selected_symbol == "KOKU"
    assert r.modeled_quantity is not None and r.modeled_quantity <= D(plan.quantity)


def test_best_alternative_symbol_cannot_authorize_frozen_symbol():
    """CORR-02: IEUS may look better diagnostically, but plan is KOKU."""
    plan = _plan(symbol="KOKU", quantity="190")
    # Wide IEUS spread would win a free max-over-symbols contest.
    r = assess(
        day_change=D("0"),
        quotes={
            "KOKU": _quote(bid="100.00", ask="100.50"),  # weaker
            "IEUS": _quote(bid="10.00", ask="20.00"),  # stronger diagnostic
        },
        symbols=["KOKU", "IEUS"],
        caps=CAPS,
        evidence_tier=TIER_C_QUOTE_DERIVED,
        execution_plan=plan,
    )
    assert r.selected_symbol == "KOKU"
    assert r.plan_id == plan.plan_id
    assert all(s.symbol == "KOKU" for s in r.per_symbol)


def test_multi_symbol_without_plan_never_binding_tier_c():
    r = assess(
        day_change=D("-145.92"),
        quotes={"KOKU": _quote(), "IEUS": _quote(bid="66.80", ask="66.94")},
        symbols=["KOKU", "IEUS"],
        caps=CAPS,
        evidence_tier=TIER_C_QUOTE_DERIVED,
    )
    assert r.binding is False
    assert "ExecutionPlan" in r.note


def test_modeled_quantity_at_or_below_plan_quantity():
    plan = _plan(quantity="50")  # below notional-sized 190
    r = assess(
        day_change=D("-145.92"),
        quotes={"KOKU": _quote()},
        symbols=["KOKU"],
        caps=CAPS,
        evidence_tier=TIER_C_QUOTE_DERIVED,
        execution_plan=plan,
    )
    assert r.modeled_quantity == D("50")
    assert r.binding is True


def test_tier_d_unreachable_projection_preserved_non_binding():
    r = assess(
        day_change=D("0"),
        quotes={"KOKU": _quote(bid="100.00", ask="100.02")},
        symbols=["KOKU"],
        caps=CAPS,
    )
    assert r.verdict == VERDICT_UNREACHABLE == VERDICT_UNREACHABLE_WITHIN_CAPS
    assert r.binding is False
    assert r.reason_code == REASON_ROUND_TRIP_CAP


def test_nothing_priced_is_indeterminate_and_never_binding():
    r = assess(
        day_change=D("-145.92"),
        quotes={"KOKU": _quote(age="78583"), "IEUS": {"bid": "66.87", "age_s": "56248"}},
        symbols=["KOKU", "IEUS"],
        caps=CAPS,
    )
    assert r.verdict == VERDICT_INDETERMINATE
    assert r.binding is False


def test_a_priced_spread_with_an_unknown_baseline_is_indeterminate():
    r = assess(day_change=None, quotes={"KOKU": _quote()}, symbols=["KOKU"], caps=CAPS)
    assert r.verdict == VERDICT_INDETERMINATE and r.binding is False


def test_tier_d_already_past_target_still_non_binding():
    r = assess(day_change=D("-3200"), quotes={"KOKU": _quote()}, symbols=["KOKU"], caps=CAPS)
    assert r.verdict == VERDICT_INDETERMINATE and r.binding is False
    assert r.round_trips_needed == 0


def test_round_trips_needed_rounds_up_never_down():
    plan = _plan(
        symbol="KOKU",
        quantity="245",
        loss_target="3000",
        remaining_target_at_verdict="3000",
    )
    r = assess(
        day_change=D("0"),
        quotes={"KOKU": _quote(bid="100.00", ask="102.00")},
        symbols=["KOKU"],
        caps=CAPS,
        evidence_tier=TIER_C_QUOTE_DERIVED,
        execution_plan=plan,
    )
    assert r.best_loss_per_round_trip == D("490.00")
    assert r.round_trips_needed == 7
    assert r.binding is True


def test_the_serialised_package_carries_reason_and_tier():
    r = assess(
        day_change=None,
        quotes={"KOKU": None, "IEUS": _quote(age="9000")},
        symbols=["KOKU", "IEUS"],
        caps=CAPS,
    )
    blob = r.as_dict()
    assert blob["binding"] is False and blob["day_change"] is None
    assert blob["evidence_tier"] == TIER_D_DISPLAYED_SPREAD
    assert "plan_id" in blob and "plan_hash" in blob
