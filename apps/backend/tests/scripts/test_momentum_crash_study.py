"""Momentum-crash study — pure analysis functions (no network)."""

from __future__ import annotations

from datetime import date

from scripts.momentum_crash_study import (
    _monthly_returns,
    _to_month_end,
    drawdown_episodes,
    worst_drawdowns,
    worst_rolling_returns,
)


def _c(pairs):
    return [(date(*d), e) for d, e in pairs]


def test_drawdown_episodes_depth_and_recovery() -> None:
    curve = _c([
        ((2024, 1, 1), 100), ((2024, 1, 2), 110), ((2024, 1, 3), 99),
        ((2024, 1, 4), 105), ((2024, 1, 5), 120), ((2024, 1, 6), 90), ((2024, 1, 7), 130),
    ])
    eps = drawdown_episodes(curve)
    assert len(eps) == 2
    # First: peak 110 → trough 99 (−10%), recovered at 120.
    assert round(eps[0].depth, 4) == round(99 / 110 - 1, 4)
    assert eps[0].recovery_date == date(2024, 1, 5)
    # Second: peak 120 → trough 90 (−25%), recovered at 130.
    assert round(eps[1].depth, 4) == round(90 / 120 - 1, 4)
    assert eps[1].recovery_date == date(2024, 1, 7)


def test_unrecovered_drawdown_has_no_recovery() -> None:
    eps = drawdown_episodes(_c([((2024, 1, 1), 100), ((2024, 1, 2), 80)]))
    assert len(eps) == 1
    assert eps[0].recovery_date is None
    assert eps[0].days_underwater is None
    assert round(eps[0].depth, 4) == -0.20


def test_worst_drawdowns_orders_deepest_first() -> None:
    curve = _c([
        ((2024, 1, 1), 100), ((2024, 1, 2), 95), ((2024, 1, 3), 100),  # −5%
        ((2024, 1, 4), 70), ((2024, 1, 5), 100),                        # −30%
    ])
    w = worst_drawdowns(curve, 5)
    assert round(w[0].depth, 4) == -0.30  # deepest first
    assert round(w[1].depth, 4) == -0.05


def test_month_end_and_monthly_returns() -> None:
    curve = _c([
        ((2024, 1, 5), 100), ((2024, 1, 31), 110),  # Jan ends at 110
        ((2024, 2, 15), 120), ((2024, 2, 29), 99),   # Feb ends at 99
    ])
    me = _to_month_end(curve)
    assert [e for _, e in me] == [110, 99]
    rets = _monthly_returns(curve)
    assert round(rets[(2024, 2)], 4) == round(99 / 110 - 1, 4)


def test_worst_rolling_returns() -> None:
    monthly = _c([((2024, m, 28), e) for m, e in [(1, 100), (2, 90), (3, 120), (4, 60)]])
    assert round(worst_rolling_returns(monthly, 1), 4) == round(60 / 120 - 1, 4)  # worst 1m = −50%
    assert worst_rolling_returns(monthly, 12) is None  # not enough history
