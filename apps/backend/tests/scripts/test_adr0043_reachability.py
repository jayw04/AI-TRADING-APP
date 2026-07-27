"""ADR 0043 Phase-0 reachability — the ways a verdict could be wrong in the dangerous direction.

Hermetic: no broker, no database, no clock. Every input is passed in.

The three regression anchors come from defects in the staged predecessor that shipped no tests:
a vacuously BINDING verdict computed from zero usable quotes, a positive day-change floored to zero
so the distance to the target was understated, and an unknown day-change treated as a known zero.
"""

from __future__ import annotations

from decimal import Decimal as D

import pytest

from scripts.adr0043_reachability import (
    VERDICT_INDETERMINATE,
    VERDICT_REACHABLE,
    VERDICT_UNREACHABLE,
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


# ------------------------------------------------------------------- pricing one symbol


def test_a_fresh_two_sided_quote_prices_the_round_trip():
    r = price_symbol("KOKU", _quote(), CAPS)
    assert r.priced and r.fresh
    assert r.sized_shares == D("190")  # floor(25000 / 131.03)
    assert r.loss_per_round_trip == D("558.60")  # spread 2.94 x 190


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
    """Every one of these once produced a number in some form of the tool. A spread we cannot
    trust must yield no contribution and a stated reason, not an optimistic estimate."""
    r = price_symbol("IEUS", quote, CAPS)
    assert not r.priced
    assert r.unusable_reason is not None and expect in r.unusable_reason


def test_the_notional_cap_bounds_the_size_not_the_other_way_round():
    r = price_symbol("EXPENSIVE", _quote(bid="30000", ask="30001"), CAPS)
    assert not r.priced and "zero shares" in (r.unusable_reason or "")


def test_position_qty_cap_binds_when_it_is_the_tighter_one():
    r = price_symbol("CHEAP", _quote(bid="1.00", ask="1.10"), CAPS)
    assert r.sized_shares == CAPS.max_position_qty  # 1000, not floor(25000/1.10)=22727


# ------------------------------------------------------------------- signed distance


def test_a_gain_increases_the_distance_to_the_target():
    """The predecessor floored this to 3000 and understated the work by the whole gain."""
    assert remaining_to_target(D("500"), D("3000")) == D("3500")


def test_a_loss_already_taken_reduces_the_distance():
    assert remaining_to_target(D("-1200"), D("3000")) == D("1800")


def test_an_unknown_day_change_yields_an_unknown_distance():
    assert remaining_to_target(None, D("3000")) is None


# ------------------------------------------------------------------- the verdict


def test_reachable_when_the_spread_covers_the_distance_within_the_cap():
    r = assess(
        day_change=D("-145.92"),
        quotes={"KOKU": _quote(), "IEUS": _quote(bid="66.80", ask="66.94")},
        symbols=["KOKU", "IEUS"],
        caps=CAPS,
    )
    assert r.verdict == VERDICT_REACHABLE and r.binding
    assert r.remaining_to_target == D("2854.08")
    assert r.best_loss_per_round_trip == D("558.60")
    assert r.round_trips_needed == 6


def test_unreachable_is_preserved_not_engineered_around():
    """A tight spread that cannot cross the target in 12 round trips is a real answer. The note
    must say so, because the tempting response is to widen a cap."""
    r = assess(
        day_change=D("0"),
        quotes={"KOKU": _quote(bid="100.00", ask="100.02")},
        symbols=["KOKU"],
        caps=CAPS,
    )
    assert r.verdict == VERDICT_UNREACHABLE and r.binding
    assert "do not widen caps" in r.note


def test_nothing_priced_is_indeterminate_and_never_binding():
    """The predecessor's `all(... for entries that priced)` was vacuously True here, so an
    after-hours read with no usable quote at all reported a BINDING verdict on zero observations."""
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
    assert r.best_loss_per_round_trip == D("558.60")  # the spread was measured
    assert r.remaining_to_target is None  # the distance was not


def test_a_stale_symbol_alongside_a_fresh_one_does_not_make_the_verdict_non_binding():
    """Binding is about the evidence the verdict RESTS on: the stale symbol contributed nothing,
    so it cannot taint a verdict computed entirely from the fresh one."""
    r = assess(
        day_change=D("-2000"),
        quotes={"KOKU": _quote(), "IEUS": _quote(age="99999")},
        symbols=["KOKU", "IEUS"],
        caps=CAPS,
    )
    assert r.verdict == VERDICT_REACHABLE and r.binding is True
    assert [s.symbol for s in r.per_symbol if s.priced] == ["KOKU"]


def test_an_account_already_past_the_target_needs_no_round_trips():
    r = assess(day_change=D("-3200"), quotes={"KOKU": _quote()}, symbols=["KOKU"], caps=CAPS)
    assert r.verdict == VERDICT_REACHABLE and r.round_trips_needed == 0


def test_round_trips_needed_rounds_up_never_down():
    """6.01 round trips is 7. Rounding down would report a plan that stops short of the target."""
    r = assess(
        day_change=D("0"),
        quotes={"KOKU": _quote(bid="100.00", ask="102.00")},  # 2.00 x 245 = 490/RT
        symbols=["KOKU"],
        caps=CAPS,
    )
    assert r.best_loss_per_round_trip == D("490.00")
    assert r.round_trips_needed == 7  # 3000/490 = 6.12


def test_the_serialised_package_carries_every_reason():
    r = assess(
        day_change=None,
        quotes={"KOKU": None, "IEUS": _quote(age="9000")},
        symbols=["KOKU", "IEUS"],
        caps=CAPS,
    )
    blob = r.as_dict()
    assert blob["binding"] is False and blob["day_change"] is None
    assert [s["unusable_reason"] for s in blob["per_symbol"]] == [
        "no governed quote",
        "quote is 9000s old (ceiling 10s)",
    ]
