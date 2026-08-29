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
from enum import StrEnum


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


# Relative floor below which return variance is rounding noise rather than signal.
_DEGENERATE_VARIANCE_REL_TOL = 1e-9


class SharpeStatus(StrEnum):
    """Why a Sharpe ratio is, or is not, a computed number.

    ``sharpe_ratio`` collapses every one of these to 0.0, which reads on a report
    as "computed, and the risk-adjusted return is exactly zero" — i.e. as a
    strategy-separation failure. Most of them mean the opposite: the statistic was
    never computable. Reporting surfaces use this to render *N/A* with a reason;
    decision surfaces keep using ``sharpe_ratio`` and are unaffected.
    """

    OK = "OK"
    # Fewer than two equity points.
    INSUFFICIENT_POINTS = "INSUFFICIENT_POINTS"
    # Fewer than two DISTINCT trading days — an intra-day curve annualizes to nonsense.
    INSUFFICIENT_TRADING_DAYS = "INSUFFICIENT_TRADING_DAYS"
    # No usable day-over-day return (every prior day's equity was <= 0).
    NO_USABLE_RETURNS = "NO_USABLE_RETURNS"
    # Returns exist but are constant — zero variance, so mean/stdev is undefined.
    # A flat or perfectly-constant-return book, NOT a book with no edge.
    INSUFFICIENT_VARIANCE = "INSUFFICIENT_VARIANCE"
    # Variance is non-zero but vanishing relative to the mean: the returns are
    # constant in intent and differ only by floating-point rounding. ``stdev == 0``
    # is an EXACT comparison and does not catch this, so the ratio is computed and
    # explodes — a book compounding at a fixed 10%/day yields Sharpe ~4.7e16.
    # ⚠ A value IS returned for this status, because the frozen decision contract
    # returns it too. Reporting must show it as unreliable rather than as a result.
    DEGENERATE_VARIANCE = "DEGENERATE_VARIANCE"


def sharpe_ratio_status(
    equity_curve: Sequence[tuple[datetime, Decimal | float]],
) -> tuple[float | None, SharpeStatus]:
    """Annualized Sharpe plus WHY it is unavailable when it is.

    Returns ``(value, OK)`` when the ratio is genuinely computed, else
    ``(None, <reason>)``. This is the diagnostic core; ``sharpe_ratio`` wraps it
    and preserves the historical 0.0 for every non-OK case, so no ranking,
    promotion gate, drift comparison or persisted ``metrics_json`` value moves.
    """
    if len(equity_curve) < 2:
        return None, SharpeStatus.INSUFFICIENT_POINTS
    by_day: dict[str, float] = {}
    for ts, eq in equity_curve:
        key = ts.date().isoformat()
        by_day[key] = float(eq)
    if len(by_day) < 2:
        return None, SharpeStatus.INSUFFICIENT_TRADING_DAYS
    sorted_eq = [by_day[k] for k in sorted(by_day.keys())]
    returns: list[float] = []
    for i in range(1, len(sorted_eq)):
        prev = sorted_eq[i - 1]
        if prev <= 0:
            continue
        returns.append((sorted_eq[i] - prev) / prev)
    if not returns:
        return None, SharpeStatus.NO_USABLE_RETURNS
    mean = sum(returns) / len(returns)
    variance = sum((r - mean) ** 2 for r in returns) / max(1, len(returns) - 1)
    stdev = math.sqrt(variance)
    if stdev == 0:
        return None, SharpeStatus.INSUFFICIENT_VARIANCE
    value = (mean / stdev) * math.sqrt(252.0)
    if stdev <= abs(mean) * _DEGENERATE_VARIANCE_REL_TOL:
        # Constant returns that are not bitwise identical. The value is returned
        # unchanged so the frozen decision contract is preserved byte-for-byte;
        # the status is what tells a report not to believe it.
        return value, SharpeStatus.DEGENERATE_VARIANCE
    return value, SharpeStatus.OK


def sharpe_ratio(equity_curve: Sequence[tuple[datetime, Decimal | float]]) -> float:
    """Annualized Sharpe from daily returns (rf=0). Intra-day returns would
    produce 60×√252 nonsense for a 1-minute strategy, so we bucket equity by
    ``ts.date()`` and use the last value of each day. Returns 0.0 for fewer than
    two distinct trading days.

    Moved verbatim from ``Backtester._sharpe``.

    ⚠ The 0.0 returned for a non-computable curve is NOT a measured zero. This
    function is the DECISION contract and its outputs are deliberately frozen —
    ranking, promotion gates and persisted ``metrics_json`` depend on them. For
    reporting, call ``sharpe_ratio_status`` and render *N/A* with the reason
    instead of a misleading 0.00.
    """
    value, _status = sharpe_ratio_status(equity_curve)
    # Keyed on ``value is None`` — which holds for exactly the four cases the
    # original body returned 0.0 for — NOT on the status, because
    # DEGENERATE_VARIANCE deliberately carries the (absurd) number the frozen
    # formula produces. See tests/strategies/test_metrics_sharpe_status.py.
    if value is None:
        return 0.0
    return value


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
