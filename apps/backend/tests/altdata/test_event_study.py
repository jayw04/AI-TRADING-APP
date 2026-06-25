"""Event-Study Engine (§3) — de-overlap, per-event drift, equal-weight book, significance.

Synthetic deterministic price paths (no DB), so the engine is exercised purely as the reusable,
event-type-agnostic harness it is meant to be.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

import pytest

from app.altdata.event_study import run_event_study

D0 = date(2026, 1, 5)


def _day(i: int) -> date:
    return D0 + timedelta(days=i)


@dataclass(frozen=True)
class Hit:
    ticker: str
    entry_date: date


def _linear_path(start_price: float, step: float, n: int, *, every: int = 1, base: int = 0):
    """A price path of ``n`` rows at ``every``-day spacing: price = start + step*i."""
    return [(_day(base + i * every), start_price + step * i) for i in range(n)]


def _price_fn(paths: dict[str, list[tuple[date, float]]]):
    def fn(ticker: str, start: date, end: date):
        return [(d, p) for d, p in paths.get(ticker, []) if start <= d <= end]
    return fn


def test_single_event_drift_and_curve():
    paths = {"AAA": [(_day(i), 100.0 + i) for i in range(7)]}  # 100..106
    res = run_event_study([Hit("AAA", _day(0))], _price_fn(paths), hold_trading_days=5)
    assert res.n_taken == 1 and res.n_skipped_overlap == 0 and res.n_no_data == 0
    d = res.drifts[0]
    assert d.entry_price == 100.0 and d.exit_price == 105.0
    assert d.ret == pytest.approx(0.05) and d.n_trading_days == 5
    assert res.total_return == pytest.approx(0.05)
    assert res.hit_rate == 1.0 and res.mean_event_return == pytest.approx(0.05)


def test_de_overlap_skips_already_held():
    paths = {"AAA": [(_day(i), 100.0 + i) for i in range(10)]}
    hits = [Hit("AAA", _day(0)), Hit("AAA", _day(2))]  # 2nd fires inside the 1st hold -> skipped
    res = run_event_study(hits, _price_fn(paths), hold_trading_days=5)
    assert res.n_taken == 1 and res.n_skipped_overlap == 1


def test_re_entry_allowed_after_exit():
    paths = {"AAA": [(_day(i), 100.0 + i) for i in range(20)]}
    hits = [Hit("AAA", _day(0)), Hit("AAA", _day(8))]  # 2nd fires after the 1st exit (day 5)
    res = run_event_study(hits, _price_fn(paths), hold_trading_days=5)
    assert res.n_taken == 2 and res.n_skipped_overlap == 0


def test_two_names_equal_weight_and_hit_rate():
    paths = {
        "AAA": [(_day(i), 100.0 + i) for i in range(7)],     # +6% over the window
        "BBB": [(_day(i), 100.0 - i) for i in range(7)],     # -6% over the window
    }
    res = run_event_study([Hit("AAA", _day(0)), Hit("BBB", _day(0))],
                          _price_fn(paths), hold_trading_days=5)
    assert res.n_taken == 2
    assert res.hit_rate == 0.5                       # one up, one down
    # equal-weight long of a +x and a -x symmetric pair nets slightly negative (return drag)
    assert res.total_return == pytest.approx(0.0, abs=0.01)


def test_no_price_data_is_counted_not_fatal():
    res = run_event_study([Hit("ZZZ", _day(0))], _price_fn({}), hold_trading_days=5)
    assert res.n_taken == 0 and res.n_no_data == 1 and res.curve == []


def test_entry_anchors_to_first_tradable_day_on_or_after():
    # prices only on even days; an odd-day entry anchor enters on the next available day (PIT)
    paths = {"AAA": _linear_path(100.0, 2.0, 6, every=2)}  # days 0,2,4,6,8,10
    res = run_event_study([Hit("AAA", _day(1))], _price_fn(paths), hold_trading_days=3)
    assert res.drifts[0].entry_date == _day(2) and res.drifts[0].entry_price == 102.0


def test_benchmark_significance_populated():
    # a long monotonic winner vs a flat benchmark -> positive, non-degenerate paired CI
    paths = {"AAA": [(_day(i), 100.0 * (1.003 ** i)) for i in range(70)]}
    bench = [(_day(i), 100.0) for i in range(70)]  # flat
    res = run_event_study([Hit("AAA", _day(0))], _price_fn(paths),
                          benchmark_fn=lambda s, e: [(d, p) for d, p in bench if s <= d <= e],
                          hold_trading_days=60)
    assert res.sharpe > 0
    assert res.sharpe_p_value is not None
    assert res.sharpe_diff_vs_benchmark is not None
    assert res.sharpe_diff_ci_low is not None and res.sharpe_diff_ci_low == res.sharpe_diff_ci_low
    assert res.benchmark_curve and res.benchmark_curve[-1][1] == pytest.approx(1.0)
