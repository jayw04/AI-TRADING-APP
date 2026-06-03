"""Shared strategy-performance metric formulas (P6b §1a-drift).

Single source of truth for the formulas used by BOTH the Backtester (with an
equity curve) and drift detection (without). The ``_sharpe`` / ``_max_drawdown``
bodies are moved verbatim from ``Backtester``, and ``win_rate`` is the inline
fraction the backtester computed — extracted so the live drift comparison and
the backtest use bit-identical math.

We intentionally do NOT define a metrics dataclass here:
``app/strategies/backtest_models.py::BacktestMetrics`` stays the on-disk
(``metrics_json``) contract and the backtester construction site. These
functions take PRIMITIVES — a list of pnls, a list of per-trade fractional
returns, or an equity curve — so the backtest's ``BacktestTrade`` and a live
round-trip feed identical formulas with no shared trade type.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from datetime import datetime
from decimal import Decimal


def win_rate(pnls: Sequence[float]) -> float:
    """Fraction of trades with pnl > 0. Empty → 0.0. Sizing-invariant."""
    p = list(pnls)
    if not p:
        return 0.0
    return sum(1 for x in p if x > 0) / len(p)


def avg_return_per_trade(returns: Sequence[float]) -> float:
    """Mean per-trade FRACTIONAL return (pnl / notional). Empty → 0.0.

    Sizing-invariant: comparable across the backtest (initial_equity=100000) and
    a live account of any size. Absolute dollar avg-pnl is NOT — it would breach
    on position sizing alone (a $10k account trades ~10x smaller than a $100k
    backtest), so the caller divides each trade's pnl by its notional first.
    """
    r = list(returns)
    if not r:
        return 0.0
    return sum(r) / len(r)


def sharpe_ratio(equity_curve: Sequence[tuple[datetime, Decimal | float]]) -> float:
    """Annualized Sharpe from daily returns (rf=0). Intra-day returns would
    produce 60×√252 nonsense for a 1-minute strategy, so we bucket equity by
    ``ts.date()`` and use the last value of each day. Returns 0.0 for fewer than
    two distinct trading days.

    Moved verbatim from ``Backtester._sharpe``.
    """
    if len(equity_curve) < 2:
        return 0.0
    by_day: dict[str, float] = {}
    for ts, eq in equity_curve:
        key = ts.date().isoformat()
        by_day[key] = float(eq)
    if len(by_day) < 2:
        return 0.0
    sorted_eq = [by_day[k] for k in sorted(by_day.keys())]
    returns: list[float] = []
    for i in range(1, len(sorted_eq)):
        prev = sorted_eq[i - 1]
        if prev <= 0:
            continue
        returns.append((sorted_eq[i] - prev) / prev)
    if not returns:
        return 0.0
    mean = sum(returns) / len(returns)
    variance = sum((r - mean) ** 2 for r in returns) / max(1, len(returns) - 1)
    stdev = math.sqrt(variance)
    if stdev == 0:
        return 0.0
    return (mean / stdev) * math.sqrt(252.0)


def max_drawdown(equity_curve: Sequence[tuple[datetime, Decimal | float]]) -> float:
    """Max drawdown as a negative fraction (e.g. -0.123 for a 12.3% dd).

    Moved verbatim from ``Backtester._max_drawdown``.
    """
    if not equity_curve:
        return 0.0
    peak = float(equity_curve[0][1])
    max_dd = 0.0
    for _, eq in equity_curve:
        v = float(eq)
        if v > peak:
            peak = v
        if peak > 0:
            dd = (v - peak) / peak
            if dd < max_dd:
                max_dd = dd
    return max_dd
