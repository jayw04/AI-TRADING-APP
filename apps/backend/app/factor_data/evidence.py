"""Edge-evidence statistics (P12 §1) — pure, seeded, reproducible.

The statistical core of the edge-evidence harness: curve metrics, a block bootstrap for
confidence intervals, a recentered-null bootstrap p-value ("could this be luck?"), benchmark
characteristics, a walk-forward stability label, and a dataset-health gate.

> **Determinism (research invariant 5).** Every function here is pure given its inputs and an
> explicit ``seed`` — no clock, no ambient state. A re-run with the same seed reproduces the CIs
> byte-for-byte, which is what makes a historical evidence report trustworthy. (Python ``random``
> seeded explicitly — deterministic by construction.)

Curves are ``[(date, equity)]`` (the shape ``run_momentum_backtest`` returns). Metrics operate on
daily simple returns derived from the curve.
"""

from __future__ import annotations

import math
import random
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import date
from typing import Any

TRADING_DAYS = 252

Curve = Sequence[tuple[date, float]]
Returns = Sequence[float]

# --- curve / return metrics (pure) ------------------------------------------


def daily_returns(curve: Curve) -> list[float]:
    """Simple daily returns from an equity curve; skips non-positive prior points."""
    out: list[float] = []
    for (_, p0), (_, p1) in zip(curve, curve[1:], strict=False):
        if p0 > 0:
            out.append(p1 / p0 - 1.0)
    return out


def total_return(curve: Curve) -> float:
    if len(curve) < 2 or curve[0][1] <= 0:
        return 0.0
    return curve[-1][1] / curve[0][1] - 1.0


def cagr(curve: Curve) -> float:
    """Compound annual growth using calendar span between the first and last dates."""
    if len(curve) < 2 or curve[0][1] <= 0 or curve[-1][1] <= 0:
        return 0.0
    years = (curve[-1][0] - curve[0][0]).days / 365.25
    if years <= 0:
        return 0.0
    return (curve[-1][1] / curve[0][1]) ** (1.0 / years) - 1.0


def _mean(xs: Returns) -> float:
    return sum(xs) / len(xs) if xs else 0.0


def _std(xs: Returns) -> float:
    if len(xs) < 2:
        return 0.0
    m = _mean(xs)
    return math.sqrt(sum((x - m) ** 2 for x in xs) / (len(xs) - 1))


def ann_volatility(returns: Returns) -> float:
    return _std(returns) * math.sqrt(TRADING_DAYS)


def sharpe(returns: Returns) -> float:
    """Annualized Sharpe (rf=0). 0.0 if undefined (no dispersion)."""
    sd = _std(returns)
    if sd == 0.0:
        return 0.0
    return (_mean(returns) / sd) * math.sqrt(TRADING_DAYS)


def sortino(returns: Returns) -> float:
    """Annualized Sortino — downside deviation only (rf=0)."""
    downside = [r for r in returns if r < 0]
    if len(downside) < 2:
        return 0.0
    dd = math.sqrt(sum(r * r for r in downside) / len(downside))
    if dd == 0.0:
        return 0.0
    return (_mean(returns) / dd) * math.sqrt(TRADING_DAYS)


def max_drawdown(curve: Curve) -> float:
    """Largest peak-to-trough decline as a negative fraction (e.g. -0.35)."""
    peak = float("-inf")
    worst = 0.0
    for _, v in curve:
        peak = max(peak, v)
        if peak > 0:
            worst = min(worst, v / peak - 1.0)
    return worst


def calmar(cagr_value: float, max_dd: float) -> float:
    return cagr_value / abs(max_dd) if max_dd != 0.0 else 0.0


def avg_drawdown(curve: Curve) -> float:
    """Mean drawdown-from-peak across all days (negative). Often more telling than max DD."""
    peak = float("-inf")
    dds: list[float] = []
    for _, v in curve:
        peak = max(peak, v)
        if peak > 0:
            dds.append(v / peak - 1.0)
    return _mean(dds)


def time_underwater(curve: Curve) -> float:
    """Fraction of days the curve sits below a prior peak (0..1)."""
    peak = float("-inf")
    under = 0
    total = 0
    for _, v in curve:
        peak = max(peak, v)
        total += 1
        if v < peak:
            under += 1
    return under / total if total else 0.0


def max_recovery_days(curve: Curve) -> int:
    """Longest stretch (in curve steps) from a peak until a new high is reclaimed."""
    peak = float("-inf")
    worst = 0
    since_peak = 0
    for _, v in curve:
        if v >= peak:
            peak = v
            since_peak = 0
        else:
            since_peak += 1
            worst = max(worst, since_peak)
    return worst


def worst_rolling_return(curve: Curve, window: int = TRADING_DAYS) -> float:
    """Worst trailing-``window`` (default ~12m) return over the curve (negative)."""
    vals = [v for _, v in curve]
    if len(vals) <= window:
        return total_return(curve)
    worst = 0.0
    for i in range(window, len(vals)):
        if vals[i - window] > 0:
            worst = min(worst, vals[i] / vals[i - window] - 1.0)
    return worst


def drawdown_profile(curve: Curve) -> dict[str, float]:
    """The full drawdown picture (review fold): max + average DD, time underwater,
    recovery length, worst rolling 12m — 'often matter more than the maximum'."""
    return {
        "max_drawdown": max_drawdown(curve),
        "avg_drawdown": avg_drawdown(curve),
        "time_underwater": time_underwater(curve),
        "max_recovery_steps": max_recovery_days(curve),
        "worst_rolling_12m": worst_rolling_return(curve, TRADING_DAYS),
    }


def benchmark_characteristics(curve: Curve) -> dict[str, float]:
    """Stand-alone characteristics of a benchmark/book curve, so a comparison has context."""
    r = daily_returns(curve)
    return {
        "total_return": total_return(curve),
        "cagr": cagr(curve),
        "ann_volatility": ann_volatility(r),
        "max_drawdown": max_drawdown(curve),
        "sharpe": sharpe(r),
    }


# --- statistical confidence (seeded bootstrap) ------------------------------


@dataclass(frozen=True)
class ConfidenceResult:
    point: float          # the metric on the observed series
    ci_low: float         # bootstrap percentile lower bound
    ci_high: float        # bootstrap percentile upper bound
    p_value: float        # one-sided H0: metric <= 0 (recentered null)
    n_resamples: int
    block: int            # block length (trading days) used


def _circular_block_resample(returns: Returns, rng: random.Random, block: int) -> list[float]:
    """One circular-block-bootstrap resample of ~the same length (preserves autocorrelation)."""
    n = len(returns)
    n_blocks = math.ceil(n / block)
    series: list[float] = []
    for _ in range(n_blocks):
        start = rng.randrange(n)
        series.extend(returns[(start + j) % n] for j in range(block))
    return series[:n]


def block_bootstrap_ci(
    returns: Returns,
    metric: Callable[[Returns], float],
    *,
    n_resamples: int = 2000,
    seed: int = 17,
    block: int = 21,
    alpha: float = 0.05,
) -> ConfidenceResult:
    """Circular-block bootstrap CI + a recentered-null one-sided p-value for ``metric > 0``.

    Block bootstrap (not i.i.d.) because daily returns are autocorrelated; block≈21 ≈ one month.
    The p-value resamples a **zero-mean** (recentered) series and asks how often its metric meets
    or beats the observed — a proper one-sided bootstrap hypothesis test for "edge > 0".
    """
    if len(returns) < 2:
        return ConfidenceResult(0.0, 0.0, 0.0, 1.0, n_resamples, block)
    point = metric(returns)
    rng = random.Random(seed)
    samples = sorted(metric(_circular_block_resample(returns, rng, block)) for _ in range(n_resamples))
    lo = samples[max(0, int((alpha / 2) * n_resamples))]
    hi = samples[min(n_resamples - 1, int((1 - alpha / 2) * n_resamples))]

    mean = _mean(returns)
    centered = [r - mean for r in returns]  # H0: true metric = 0
    null_rng = random.Random(seed + 1)
    ge = sum(
        1
        for _ in range(n_resamples)
        if metric(_circular_block_resample(centered, null_rng, block)) >= point
    )
    p_value = ge / n_resamples
    return ConfidenceResult(point, lo, hi, p_value, n_resamples, block)


# --- walk-forward stability -------------------------------------------------


def stability_label(window_sharpes: Sequence[float]) -> str:
    """One-word walk-forward read. Stable: all windows positive and low dispersion;
    Unstable: a third or more negative; else Moderately stable."""
    if not window_sharpes:
        return "unknown"
    n = len(window_sharpes)
    neg = sum(1 for s in window_sharpes if s <= 0)
    if neg == 0 and _std(window_sharpes) <= _mean(window_sharpes):
        return "stable"
    if neg >= math.ceil(n / 3):
        return "unstable"
    return "moderately stable"


# --- dataset-health gate ----------------------------------------------------


def dataset_health(store: Any, start: date, end: date) -> dict[str, Any]:
    """Pre-experiment data-trust report — "can we trust the data?" answered automatically.

    Best-effort over the DuckDB store: date coverage + gaps, SEP row count, distinct tickers,
    delisted coverage (survivorship check). ``ok`` is False on a red flag (e.g. no rows / a
    coverage gap), so the harness can fail-closed.
    """
    con = store.con
    lo, hi = store.price_date_bounds()
    n_rows = con.execute(
        "SELECT COUNT(*) FROM sep WHERE date BETWEEN ? AND ?", [start, end]
    ).fetchone()[0]
    n_tickers = con.execute(
        "SELECT COUNT(DISTINCT ticker) FROM sep WHERE date BETWEEN ? AND ?", [start, end]
    ).fetchone()[0]
    try:
        n_delisted = con.execute(
            "SELECT COUNT(*) FROM tickers WHERE isdelisted = 'Y'"
        ).fetchone()[0]
    except Exception:
        n_delisted = None  # tickers table / column may be absent on a minimal store
    covered = lo is not None and hi is not None and lo <= start and hi >= end
    flags: list[str] = []
    if n_rows == 0:
        flags.append("no rows in window")
    if not covered:
        flags.append(f"store coverage [{lo}..{hi}] does not span [{start}..{end}]")
    if n_delisted == 0:
        flags.append("no delisted names — survivorship bias suspected")
    return {
        "store_bounds": [str(lo), str(hi)],
        "window": [str(start), str(end)],
        "n_sep_rows": n_rows,
        "n_tickers": n_tickers,
        "n_delisted": n_delisted,
        "covers_window": covered,
        "flags": flags,
        "ok": not flags,
    }
