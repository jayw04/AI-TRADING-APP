"""ADR 0043 Phase-0 reachability — hermetic regressions + WP2 Tier-D gating.

Controlling Design v1.1: displayed-spread (Tier D) never yields a binding verdict.
Would-be REACHABLE → INDETERMINATE + INSUFFICIENT_EXECUTION_COST.
"""

from __future__ import annotations

from decimal import Decimal as D

import pytest

from app.risk.loss_control.phase0_contracts import (
    REASON_INSUFFICIENT_EXECUTION_COST,
    REASON_ROUND_TRIP_CAP,
    TIER_C_QUOTE_DERIVED,
    TIER_D_DISPLAYED_SPREAD,
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
    """WP2: Tier D cannot authorize REACHABLE — refuse with INDETERMINATE."""
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
    assert r.remaining_to_target == D("2854.08")
    assert r.best_loss_per_round_trip == D("558.60")
    assert r.round_trips_needed == 6


def test_tier_c_can_bind_reachable():
    r = assess(
        day_change=D("-145.92"),
        quotes={"KOKU": _quote()},
        symbols=["KOKU"],
        caps=CAPS,
        evidence_tier=TIER_C_QUOTE_DERIVED,
    )
    assert r.verdict == VERDICT_REACHABLE and r.binding is True
    assert r.reason_code is None


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
    assert "do not widen caps" in r.note


def test_nothing_priced_is_indeterminate_and_never_binding():
    r = assess(
        day_change=D("-145.92"),
        quotes={"KOKU": _quote(age="78583"), "IEUS": {"bid": "66.87", "age_s": "56248"}},
        symbols=["KOKU", "IEUS"],
        caps=CAPS,
    )
    assert r.verdict == VERDICT_INDETERMINATE
    assert r.binding is False
    assert r.best_loss_per_round_trip is None
    assert "nothing was measured" in r.note


def test_a_priced_spread_with_an_unknown_baseline_is_indeterminate():
    r = assess(day_change=None, quotes={"KOKU": _quote()}, symbols=["KOKU"], caps=CAPS)
    assert r.verdict == VERDICT_INDETERMINATE and r.binding is False
    assert r.best_loss_per_round_trip == D("558.60")
    assert r.remaining_to_target is None


def test_tier_d_already_past_target_still_non_binding():
    r = assess(day_change=D("-3200"), quotes={"KOKU": _quote()}, symbols=["KOKU"], caps=CAPS)
    assert r.verdict == VERDICT_INDETERMINATE and r.binding is False
    assert r.round_trips_needed == 0


def test_round_trips_needed_rounds_up_never_down():
    r = assess(
        day_change=D("0"),
        quotes={"KOKU": _quote(bid="100.00", ask="102.00")},
        symbols=["KOKU"],
        caps=CAPS,
        evidence_tier=TIER_C_QUOTE_DERIVED,
    )
    assert r.best_loss_per_round_trip == D("490.00")
    assert r.round_trips_needed == 7


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
    assert "reason_code" in blob
    assert [s["unusable_reason"] for s in blob["per_symbol"]] == [
        "no governed quote",
        "quote is 9000s old (ceiling 10s)",
    ]
