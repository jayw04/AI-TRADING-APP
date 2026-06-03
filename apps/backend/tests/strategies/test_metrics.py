"""P6b §1a-drift — shared metrics module (extracted from Backtester).

The Backtester-integration regression is covered by the existing
tests/strategies/test_backtester.py + test_backtest_reproducibility.py suites
(they exercise Backtester.run() and assert metrics_json); these unit-test the
extracted formula functions directly.
"""
from __future__ import annotations

from datetime import UTC, datetime

from app.strategies.metrics import (
    avg_return_per_trade,
    max_drawdown,
    sharpe_ratio,
    win_rate,
)


def _dt(day: int) -> datetime:
    return datetime(2026, 6, day, 16, 0, tzinfo=UTC)


# ---- win_rate ----


def test_win_rate_empty_returns_0():
    assert win_rate([]) == 0.0


def test_win_rate_all_wins_returns_1():
    assert win_rate([1.0, 2.0, 0.5]) == 1.0


def test_win_rate_all_losses_returns_0():
    assert win_rate([-1.0, -2.0]) == 0.0


def test_win_rate_mixed():
    assert win_rate([1.0, -1.0, 2.0, -3.0]) == 0.5


# ---- avg_return_per_trade ----


def test_avg_return_per_trade_mean_of_fractions():
    assert abs(avg_return_per_trade([0.10, 0.20, -0.06]) - 0.08) < 1e-9


def test_avg_return_per_trade_empty_returns_0():
    assert avg_return_per_trade([]) == 0.0


# ---- sharpe_ratio ----


def test_sharpe_ratio_under_2_days_returns_0():
    # Same calendar day → <2 distinct days → degenerate → 0.0 (documented limit).
    curve = [(_dt(1), 100.0), (_dt(1), 101.0)]
    assert sharpe_ratio(curve) == 0.0


def test_sharpe_ratio_normal_case():
    curve = [(_dt(1), 100.0), (_dt(2), 101.0), (_dt(3), 103.0), (_dt(4), 102.0)]
    s = sharpe_ratio(curve)
    assert isinstance(s, float)
    assert s != 0.0


# ---- max_drawdown ----


def test_max_drawdown_no_decline_returns_0():
    curve = [(_dt(1), 100.0), (_dt(2), 110.0), (_dt(3), 120.0)]
    assert max_drawdown(curve) == 0.0


def test_max_drawdown_typical_case():
    # Peak 120, trough 90 → (90-120)/120 = -0.25
    curve = [(_dt(1), 100.0), (_dt(2), 120.0), (_dt(3), 90.0), (_dt(4), 110.0)]
    assert round(max_drawdown(curve), 4) == -0.25
