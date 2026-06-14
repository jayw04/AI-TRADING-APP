"""Survivorship-free weekly cross-sectional momentum backtest (P9 §3).

Standalone — does NOT touch the single-name `Backtester` (Direction §7). Consumes
the §1 PIT store + the §2 momentum engine directly, and reuses the shared metric
formulas (`app/strategies/metrics.py`) so factor and single-name backtests report
identical math.

Decisions (owner-locked 2026-06-14, §3 doc):
- Weekly rebalance on the last trading day of each ISO week; weights apply to the
  NEXT trading day onward (no same-bar look-ahead).
- Long-only, equal-weight the top quintile by momentum `score`.
- Delisting return = final price → cash: a held name earns daily returns to its
  last trading day, then its sleeve is frozen as cash until the next rebalance.
  (Falls out of the per-name sleeve mark-to-market — see `_simulate`.)
- A passive equal-weight-universe baseline runs alongside for comparison (ADR 0014).
"""

from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date, datetime, time

import structlog

from app.factor_data.factors.engine import (
    DEFAULT_LOOKBACK_DAYS,
    DEFAULT_MIN_NAMES,
    DEFAULT_SKIP_DAYS,
    FactorUnavailable,
    momentum_scores,
)
from app.factor_data.store import FactorDataStore
from app.factor_data.universe import UniverseUnavailable, universe_asof
from app.strategies import metrics

logger = structlog.get_logger(__name__)


@dataclass(frozen=True)
class BacktestRunConfig:
    start: date
    end: date
    n: int
    lookback_days: int
    skip_days: int
    top_quantile: float
    turnover_cost_bps: float
    delisting: str
    initial_equity: float


@dataclass(frozen=True)
class BacktestSummary:
    total_return: float
    cagr: float
    sharpe: float
    max_drawdown: float


@dataclass(frozen=True)
class RebalanceHoldings:
    rebalance_date: date
    tickers: list[str]
    realized_return: float  # the sleeve set's return over the following segment


@dataclass(frozen=True)
class MomentumBacktestReport:
    config: BacktestRunConfig
    rebalances: list[date]
    equity_curve: list[tuple[date, float]]
    baseline_curve: list[tuple[date, float]]
    holdings: list[RebalanceHoldings]
    metrics: BacktestSummary
    baseline_metrics: BacktestSummary
    skipped_rebalances: list[date] = field(default_factory=list)


# A selection function: given a rebalance date, return {ticker: target_weight}.
SelectFn = Callable[[date], "dict[str, float]"]


def _iso_week_last_trading_days(trading_days: list[date]) -> list[date]:
    """The last trading day within each ISO (year, week) — the weekly rebalances."""
    last_by_week: dict[tuple[int, int], date] = {}
    for d in trading_days:
        iso = d.isocalendar()
        last_by_week[(iso[0], iso[1])] = d  # trading_days ascending → last wins
    return sorted(last_by_week.values())


def _equity_to_curve(curve: list[tuple[date, float]]) -> list[tuple[datetime, float]]:
    """Adapt a (date, equity) curve to the (datetime, equity) the shared metrics
    helpers expect. Midnight UTC-naive is fine — they bucket by .date()."""
    return [(datetime.combine(d, time()), eq) for d, eq in curve]


def _summary(curve: list[tuple[date, float]], initial_equity: float) -> BacktestSummary:
    if not curve:
        return BacktestSummary(0.0, 0.0, 0.0, 0.0)
    dt_curve = _equity_to_curve(curve)
    final = curve[-1][1]
    total_return = final / initial_equity - 1.0 if initial_equity > 0 else 0.0
    days = (curve[-1][0] - curve[0][0]).days
    years = days / 365.25 if days > 0 else 0.0
    cagr = (final / initial_equity) ** (1.0 / years) - 1.0 if years > 0 and initial_equity > 0 else 0.0
    return BacktestSummary(
        total_return=total_return,
        cagr=cagr,
        sharpe=metrics.sharpe_ratio(dt_curve),
        max_drawdown=metrics.max_drawdown(dt_curve),
    )


def _simulate(
    store: FactorDataStore,
    rebalances: list[date],
    trading_days: list[date],
    select_fn: SelectFn,
    *,
    initial_equity: float,
    turnover_cost_bps: float,
) -> tuple[list[tuple[date, float]], list[RebalanceHoldings]]:
    """Run one book: weekly weights from `select_fn`, daily mark-to-market.

    Per-name sleeves are marked daily by `closeadj[t]/closeadj[prev_traded]`. A
    name whose prices end mid-segment simply stops being marked — its sleeve is
    frozen at its last value (= final price → cash). Equity each day = Σ sleeves.
    """
    equity = initial_equity
    curve: list[tuple[date, float]] = []
    holdings: list[RebalanceHoldings] = []
    prev_weights: dict[str, float] = {}  # drifted weights carried into next rebalance

    # Map each rebalance to the segment of trading days strictly after it, up to
    # (and including) the next rebalance — or the end of the calendar for the last.
    for i, d in enumerate(rebalances):
        next_d = rebalances[i + 1] if i + 1 < len(rebalances) else None
        seg = [t for t in trading_days if t > d and (next_d is None or t <= next_d)]
        if not seg:
            continue

        weights = select_fn(d)
        if not weights:
            continue

        # Turnover cost on the one-way change from the drifted prior book.
        keys = set(weights) | set(prev_weights)
        turnover = 0.5 * sum(abs(weights.get(k, 0.0) - prev_weights.get(k, 0.0)) for k in keys)
        equity *= 1.0 - (turnover_cost_bps / 1e4) * turnover

        # Preload each held name's closeadj from the rebalance day through the segment.
        seg_end = seg[-1]
        px_maps: dict[str, dict[date, float]] = {}
        ref: dict[str, float] = {}
        for ticker in weights:
            df = store.get_prices(ticker, d, seg_end, adjusted=True)
            pm = {row.date(): float(c) for row, c in zip(df["date"], df["close"], strict=False)
                  if c is not None and float(c) > 0}
            px_maps[ticker] = pm
            ref[ticker] = pm.get(d, 0.0)

        seg_start_equity = equity
        sleeves = {tk: w * equity for tk, w in weights.items()}
        prev_px = dict(ref)
        for t in seg:
            for tk in weights:
                p = px_maps[tk].get(t)
                if p is not None and prev_px[tk] > 0:
                    sleeves[tk] *= p / prev_px[tk]
                    prev_px[tk] = p
                # else: no price today → sleeve frozen (delisted→cash / non-trading)
            equity = sum(sleeves.values())
            curve.append((t, equity))

        realized = equity / seg_start_equity - 1.0 if seg_start_equity > 0 else 0.0
        holdings.append(RebalanceHoldings(d, sorted(weights), realized))
        # Drifted weights for the next rebalance's turnover calc.
        prev_weights = {tk: (sv / equity if equity > 0 else 0.0) for tk, sv in sleeves.items()}

    return curve, holdings


def run_momentum_backtest(
    store: FactorDataStore,
    start: date,
    end: date,
    *,
    n: int = 500,
    lookback_days: int = DEFAULT_LOOKBACK_DAYS,
    skip_days: int = DEFAULT_SKIP_DAYS,
    top_quantile: float = 0.20,
    turnover_cost_bps: float = 10.0,
    delisting: str = "last_price_to_cash",
    min_names: int = DEFAULT_MIN_NAMES,
    initial_equity: float = 100_000.0,
) -> MomentumBacktestReport:
    """Weekly long-only top-quintile momentum backtest, survivorship-free.

    Returns a `MomentumBacktestReport` with daily equity curves + summary metrics
    for the momentum book and a passive equal-weight-universe baseline. Rebalance
    dates whose cross-section is too thin (`FactorUnavailable`/`UniverseUnavailable`)
    are skipped and recorded in `report.skipped_rebalances` rather than silently
    shortening the window. Deterministic for a given store + args.
    """
    if delisting != "last_price_to_cash":
        raise ValueError(f"unsupported delisting mechanism: {delisting!r}")
    if not (0.0 < top_quantile <= 1.0):
        raise ValueError("top_quantile must be in (0, 1]")

    config = BacktestRunConfig(
        start=start, end=end, n=n, lookback_days=lookback_days, skip_days=skip_days,
        top_quantile=top_quantile, turnover_cost_bps=turnover_cost_bps,
        delisting=delisting, initial_equity=initial_equity,
    )

    all_days = store.trading_days(start, end)
    if len(all_days) < 2:
        empty = BacktestSummary(0.0, 0.0, 0.0, 0.0)
        return MomentumBacktestReport(config, [], [], [], [], empty, empty)

    rebalances_all = _iso_week_last_trading_days(all_days)

    # Cache momentum scores per usable rebalance; record (and skip) thin ones.
    scores_by_date: dict[date, list[str]] = {}  # ranked tickers, best first
    universe_by_date: dict[date, list[str]] = {}
    rebalances: list[date] = []
    skipped: list[date] = []
    for d in rebalances_all:
        try:
            df = momentum_scores(store, d, n=n, lookback_days=lookback_days,
                                 skip_days=skip_days, min_names=min_names)
            scores_by_date[d] = list(df.index)
            universe_by_date[d] = universe_asof(store, d, n=n)
            rebalances.append(d)
        except (FactorUnavailable, UniverseUnavailable):
            skipped.append(d)
    if skipped:
        logger.info("backtest_skipped_thin_rebalances", count=len(skipped),
                    first=str(skipped[0]), last=str(skipped[-1]))

    if not rebalances:
        empty = BacktestSummary(0.0, 0.0, 0.0, 0.0)
        return MomentumBacktestReport(config, [], [], [], [], empty, empty,
                                      skipped_rebalances=skipped)

    def book_select(d: date) -> dict[str, float]:
        ranked = scores_by_date[d]
        k = max(1, math.ceil(len(ranked) * top_quantile))
        chosen = ranked[:k]
        w = 1.0 / len(chosen)
        return {t: w for t in chosen}

    def baseline_select(d: date) -> dict[str, float]:
        names = universe_by_date[d]
        w = 1.0 / len(names)
        return {t: w for t in names}

    book_curve, holdings = _simulate(
        store, rebalances, all_days, book_select,
        initial_equity=initial_equity, turnover_cost_bps=turnover_cost_bps,
    )
    base_curve, _ = _simulate(
        store, rebalances, all_days, baseline_select,
        initial_equity=initial_equity, turnover_cost_bps=turnover_cost_bps,
    )

    return MomentumBacktestReport(
        config=config,
        rebalances=rebalances,
        equity_curve=book_curve,
        baseline_curve=base_curve,
        holdings=holdings,
        metrics=_summary(book_curve, initial_equity),
        baseline_metrics=_summary(base_curve, initial_equity),
        skipped_rebalances=skipped,
    )
