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
import statistics
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta

import numpy as np
import pandas as pd
import structlog

from app.factor_data.factors.engine import (
    DEFAULT_LOOKBACK_DAYS,
    DEFAULT_MIN_NAMES,
    DEFAULT_SKIP_DAYS,
    FactorUnavailable,
    momentum_scores,
)
from app.factor_data.portfolio import assert_valid_weights
from app.factor_data.store import FactorDataStore
from app.factor_data.universe import UniverseUnavailable, universe_asof
from app.strategies import metrics

logger = structlog.get_logger(__name__)

# Phase 3A §4.4: trailing-window (trading days) for the inverse-vol / risk-parity
# weighting σ estimate. ~3 months — long enough to be stable, short enough to track
# regime shifts. Used only by the non-default weightings; equal_weight ignores it.
DEFAULT_VOL_LOOKBACK_DAYS = 63

# The construction methods the weigher supports (Phase 3A §4.4). ``risk_parity_diagonal``
# is INTENTIONALLY identical to ``inverse_vol`` in v1 (equal risk contribution under a
# diagonal covariance == inverse-vol); it is a named seam for a future covariance-aware
# method, not a duplicate to "fix" (Gotcha 5).
WEIGHTING_METHODS = ("equal_weight", "inverse_vol", "risk_parity_diagonal")


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
    vol_target_annual: float | None = None  # None = no vol-target overlay run
    vol_ewma_span: int = 20
    weighting: str = "equal_weight"          # Phase 3A §4.4: equal_weight | inverse_vol | risk_parity_diagonal
    vol_lookback_days: int = DEFAULT_VOL_LOOKBACK_DAYS
    max_sector_pct: float | None = None      # Phase 3A §3C: per-sector book-weight cap (None = disabled)


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
    # Phase 3A §4.5: the target weights at this rebalance (ticker -> weight). Carried
    # so the evidence bundle / stability / capacity metrics can be computed without
    # re-deriving the book. Defaults to {} for callers that don't set it.
    weights: dict[str, float] = field(default_factory=dict)


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
    # Populated only when run_momentum_backtest is given vol_target_annual: the
    # book curve after a daily EWMA-vol-target gross-exposure overlay (review
    # Priority 1), plus its summary metrics — for a before/after comparison.
    vol_scaled_curve: list[tuple[date, float]] = field(default_factory=list)
    vol_scaled_metrics: BacktestSummary | None = None


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


def _vol_target_overlay(
    curve: list[tuple[date, float]],
    *,
    vol_target_annual: float,
    span: int,
    initial_equity: float,
) -> list[tuple[date, float]]:
    """Apply a daily EWMA-vol-target gross-exposure overlay to a daily equity curve.

    Mirrors ``MomentumPortfolio._gross_scale`` at the portfolio-return level: each
    day's return is scaled by min(1, target_daily / sigma_t), where sigma_t is the
    EWMA vol of returns STRICTLY BEFORE t (shift(1) → no look-ahead) and
    target_daily = vol_target_annual / √252. The cap at 1.0 means no leverage; the
    un-invested fraction earns nothing. Warm-up days (sigma not yet estimable) get
    scale 1.0 = fail open, matching the strategy. Returns a fresh (date, equity)
    curve anchored at ``initial_equity``."""
    if not curve or vol_target_annual <= 0:
        return list(curve)
    eq_full = [initial_equity] + [e for _, e in curve]
    rets = pd.Series(eq_full, dtype=float).pct_change().dropna().reset_index(drop=True)
    sigma_prev = rets.ewm(span=span).std().shift(1)  # vol from returns before t
    target_daily = vol_target_annual / math.sqrt(252.0)
    scale = (target_daily / sigma_prev).clip(upper=1.0).fillna(1.0)
    scaled_rets = (scale * rets).fillna(0.0)
    out: list[tuple[date, float]] = []
    eq = initial_equity
    for (d, _), sr in zip(curve, scaled_rets, strict=False):
        eq *= 1.0 + float(sr)
        out.append((d, eq))
    return out


def _trailing_vol(
    store: FactorDataStore, ticker: str, d: date, lookback_days: int
) -> float | None:
    """Trailing realized daily-return volatility for ``ticker`` over ``lookback_days``
    trading days ending **strictly before** ``d`` (no look-ahead — mirrors the
    shift(1) discipline in ``_vol_target_overlay``). Returns None when there is too
    little history or σ is non-finite/≤0, so the caller can fall back to a peer median
    rather than divide by zero."""
    # Fetch a generously-wide calendar window (trading days are ~70% of calendar
    # days) so we reliably capture ``lookback_days`` returns before ``d``.
    start = d - timedelta(days=int(lookback_days * 2) + 15)
    df = store.get_prices(ticker, start, d, adjusted=True)
    if df.empty:
        return None
    closes = [
        float(c)
        for dt, c in zip(df["date"], df["close"], strict=False)
        if c is not None and float(c) > 0 and dt.date() < d  # strictly before d
    ]
    closes = closes[-(lookback_days + 1):]
    if len(closes) < 2:
        return None
    rets = pd.Series(closes, dtype=float).pct_change().dropna()
    if len(rets) < 2:
        return None
    sigma = float(rets.std())
    return sigma if math.isfinite(sigma) and sigma > 0 else None


def _apply_sector_cap(
    store: FactorDataStore,
    weights: dict[str, float],
    *,
    max_sector_pct: float | None,
) -> dict[str, float]:
    """Cap each known sector's aggregate book weight at ``max_sector_pct`` (Phase 3A
    §3C). Returns a re-normalized long-only, fully-invested (Σ=1) weight vector.

    Algorithm — iterative water-filling that *freezes* a sector once it is clamped:
    on each pass, every known sector whose aggregate weight exceeds the cap is scaled
    down to the cap (preserving intra-sector proportions), the freed weight is
    redistributed pro-rata across the names not yet in a frozen sector, and the pass
    repeats. Because each pass freezes at least one more sector, it terminates in at
    most ``#distinct sectors`` passes; redistribution that pushes an under-cap sector
    over is caught and frozen on the next pass.

    **Unknown-sector names are EXEMPT** — ``get_sectors`` → ``None`` makes a name its
    own uncapped bucket (never frozen, always an eligible receiver), matching
    ``get_sectors``' fail-open contract; unrelated names are never falsely lumped
    together.

    **FAILS OPEN** (returns ``weights`` unchanged, logged) when capping is disabled
    (``max_sector_pct`` is None / ≥ 1), no sectors are readable, or the cap is
    mathematically infeasible (every receiver is exhausted before Σ can return to 1 —
    e.g. cap 0.20 with only 3 distinct sectors and no exempt names). Failing open
    preserves the fully-invested ``gross=1`` invariant the backtest assumes rather
    than silently holding cash or producing a degenerate book."""
    if max_sector_pct is None or max_sector_pct >= 1.0 or not weights:
        return weights
    sectors = store.get_sectors(list(weights))
    distinct = {s for s in sectors.values() if s is not None}
    if not distinct:  # pre-sector store / all unknown → nothing to cap (fail open)
        return weights

    w = dict(weights)
    frozen: set[str] = set()  # sector names clamped at the cap
    eps = 1e-12
    for _ in range(len(distinct) + 1):
        sector_w: dict[str, float] = {}
        for t, wt in w.items():
            s = sectors[t]
            if s is not None:
                sector_w[s] = sector_w.get(s, 0.0) + wt
        over = [s for s, sw in sector_w.items() if s not in frozen and sw > max_sector_pct + eps]
        if not over:
            break
        freed = 0.0
        for s in over:
            scale = max_sector_pct / sector_w[s]
            for t in [t for t in w if sectors[t] == s]:
                freed += w[t] * (1.0 - scale)
                w[t] *= scale
            frozen.add(s)
        receivers = [t for t in w if sectors[t] not in frozen]
        recv_total = sum(w[t] for t in receivers)
        if not receivers or recv_total <= eps:  # infeasible → fail open
            logger.warning("sector_cap_infeasible", max_sector_pct=max_sector_pct,
                           n_sectors=len(distinct), n_names=len(weights))
            return weights
        for t in receivers:
            w[t] += freed * w[t] / recv_total
    else:  # did not converge within the freeze bound → fail open rather than ship a bad book
        logger.warning("sector_cap_no_converge", max_sector_pct=max_sector_pct,
                       n_sectors=len(distinct))
        return weights

    total = sum(w.values())  # clean float drift so assert_valid_weights' Σ=1 holds
    if total <= 0:
        return weights
    return {t: wt / total for t, wt in w.items()}


def _weigh(
    store: FactorDataStore,
    chosen: list[str],
    d: date,
    *,
    method: str,
    vol_lookback_days: int,
    max_sector_pct: float | None = None,
) -> dict[str, float]:
    """Assign target weights to ``chosen`` at rebalance ``d`` under ``method``.

    - ``equal_weight`` → ``1/len(chosen)`` (byte-for-byte identical to the legacy
      book; the §5 regression guard asserts this).
    - ``inverse_vol`` → ``w_i ∝ 1/σ_i`` normalized, σ_i the trailing realized vol
      (``_trailing_vol``); names with insufficient history / σ≈0 fall back to the
      cross-sectional median σ so we never divide by zero.
    - ``risk_parity_diagonal`` → equal risk contribution under a diagonal covariance,
      which **is** inverse-vol in v1 (Gotcha 5) — a named seam, not a duplicate.

    When ``max_sector_pct`` is set (Phase 3A §3C), the raw method weights are passed
    through ``_apply_sector_cap`` before validation; it is a no-op (and fails open)
    when the cap is disabled, sectors are unknown, or the cap is infeasible — so the
    default ``None`` leaves every legacy book byte-identical.

    Every returned vector is checked by ``assert_valid_weights`` (Phase 3A §4.3) so an
    invariant violation fails the experiment loudly instead of producing a silently
    wrong book. Long-only, fully invested (cash=0)."""
    if not chosen:
        return {}
    if method == "equal_weight":
        w = 1.0 / len(chosen)
        weights = {t: w for t in chosen}
    elif method in ("inverse_vol", "risk_parity_diagonal"):
        vols = {t: _trailing_vol(store, t, d, vol_lookback_days) for t in chosen}
        present = [v for v in vols.values() if v is not None]
        median_sigma = statistics.median(present) if present else 1.0
        inv: dict[str, float] = {}
        for t in chosen:
            sigma = vols[t]
            if sigma is None or sigma <= 0:
                sigma = median_sigma
            inv[t] = 1.0 / sigma if sigma > 0 else 1.0
        total = sum(inv.values())
        if total <= 0:  # fully degenerate → fall back to equal weight
            w = 1.0 / len(chosen)
            weights = {t: w for t in chosen}
        else:
            weights = {t: iv / total for t, iv in inv.items()}
    else:
        raise ValueError(f"unsupported weighting method: {method!r}")
    weights = _apply_sector_cap(store, weights, max_sector_pct=max_sector_pct)
    assert_valid_weights(weights, cash=0.0, target_gross=1.0, long_only=True)
    return weights


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
        holdings.append(RebalanceHoldings(d, sorted(weights), realized, dict(weights)))
        # Drifted weights for the next rebalance's turnover calc.
        prev_weights = {tk: (sv / equity if equity > 0 else 0.0) for tk, sv in sleeves.items()}

    return curve, holdings


def simulate_cash_book(
    store: FactorDataStore,
    rebalances: list[date],
    trading_days: list[date],
    select_fn: SelectFn,
    *,
    initial_equity: float = 100_000.0,
    turnover_cost_bps: float = 10.0,
) -> tuple[list[tuple[date, float]], list[tuple[date, float]]]:
    """Cash-aware book sim: like ``_simulate`` but **banks the uninvested fraction**.

    ``_simulate`` assumes a fully-invested book (Σweights = 1); any sub-1.0 weight is
    silently dropped, not held as cash, so it cannot model a *participation* book whose
    gross exposure falls in downtrends. This sibling holds ``(1 - Σweights)·equity`` as a
    constant cash sleeve (earns nothing) over each segment and charges one-way turnover on
    the **stock legs only** (cash is never traded — it is not a weight key). Daily
    per-name marking is byte-identical to ``_simulate`` (same ``closeadj`` ratio,
    same delisting→cash freeze).

    This is the shared home for the TREND-001 ``simulate_cash`` harness and the runner's
    ``construction="participation"`` / ``baseline="regime_filter"`` books. Returns
    ``(equity_curve, gross_series)`` where ``gross_series`` is ``(rebalance_date, Σweights)``
    so a caller can report the participation level. Deterministic for a given store + args.
    """
    equity = initial_equity
    curve: list[tuple[date, float]] = []
    gross_series: list[tuple[date, float]] = []
    prev_w: dict[str, float] = {}

    for i, d in enumerate(rebalances):
        next_d = rebalances[i + 1] if i + 1 < len(rebalances) else None
        seg = [t for t in trading_days if t > d and (next_d is None or t <= next_d)]
        if not seg:
            continue
        weights = select_fn(d)
        gross = sum(weights.values())
        gross_series.append((d, round(gross, 4)))

        keys = set(weights) | set(prev_w)
        turnover = 0.5 * sum(abs(weights.get(k, 0.0) - prev_w.get(k, 0.0)) for k in keys)
        equity *= 1.0 - (turnover_cost_bps / 1e4) * turnover

        seg_end = seg[-1]
        px_maps: dict[str, dict[date, float]] = {}
        prev_px: dict[str, float] = {}
        for tk in weights:
            df = store.get_prices(tk, d, seg_end, adjusted=True)
            pm = {row.date(): float(c) for row, c in zip(df["date"], df["close"], strict=False)
                  if c is not None and float(c) > 0}
            px_maps[tk] = pm
            prev_px[tk] = pm.get(d, 0.0)

        cash = (1.0 - gross) * equity  # constant over the segment (earns nothing)
        sleeves = {tk: w * equity for tk, w in weights.items()}
        for t in seg:
            for tk in weights:
                p = px_maps[tk].get(t)
                if p is not None and prev_px[tk] > 0:
                    sleeves[tk] *= p / prev_px[tk]
                    prev_px[tk] = p
                # else: no price today → sleeve frozen (delisted→cash / non-trading)
            equity = sum(sleeves.values()) + cash
            curve.append((t, equity))
        prev_w = {tk: (sv / equity if equity > 0 else 0.0) for tk, sv in sleeves.items()}

    return curve, gross_series


class _CachedPriceStore:
    """Read-through price cache over a ``FactorDataStore`` for one backtest run.

    ``compute_momentum_batch`` re-reads each universe name's *entire* price history
    (``floor..as_of``) on every weekly rebalance, and ``_simulate`` / ``_trailing_vol``
    re-query overlapping windows. Across ~1000 rebalances that is hundreds of
    thousands of redundant scans of the same rows out of the multi-GB store — the
    dominant cost of a full-history run.

    This wrapper loads each name's full history once (per ``adjusted`` flag) and
    serves every ``get_prices(ticker, start, end)`` as an in-memory date-slice. The
    slice is byte-identical to the underlying windowed query — same rows, same order
    (both are ``ORDER BY date`` and the slice preserves it) — so backtest numbers are
    unchanged; only the I/O is removed. Only ``get_prices`` is intercepted; every
    other attribute delegates to the real store, leaving the PIT/read-only
    guarantees intact. One instance per ``run_momentum_backtest`` call (no shared
    state); the store is read-only so cached frames never go stale.
    """

    def __init__(self, store: FactorDataStore) -> None:
        self._store = store
        self._floor, self._ceil = store.price_date_bounds()
        self._full: dict[tuple[str, bool], pd.DataFrame] = {}

    def __getattr__(self, name: str) -> object:
        # Everything except get_prices (and our own _-prefixed state) delegates.
        return getattr(self._store, name)

    def get_prices(
        self, ticker: str, start: date, end: date, *, adjusted: bool = True
    ) -> pd.DataFrame:
        if self._floor is None or self._ceil is None:  # empty store → no caching
            return self._store.get_prices(ticker, start, end, adjusted=adjusted)
        key = (ticker, adjusted)
        full = self._full.get(key)
        if full is None:
            full = self._store.get_prices(ticker, self._floor, self._ceil, adjusted=adjusted)
            self._full[key] = full
        # full is ORDER BY date, so [start, end] is a contiguous slice located by binary
        # search — O(log n) + a view-copy, vs an O(n) boolean mask. Same rows, same order.
        dates = full["date"].to_numpy()
        lo = int(np.searchsorted(dates, pd.Timestamp(start).to_datetime64(), side="left"))
        hi = int(np.searchsorted(dates, pd.Timestamp(end).to_datetime64(), side="right"))
        return full.iloc[lo:hi].reset_index(drop=True)


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
    vol_target_annual: float | None = None,
    vol_ewma_span: int = 20,
    weighting: str = "equal_weight",
    vol_lookback_days: int = DEFAULT_VOL_LOOKBACK_DAYS,
    max_sector_pct: float | None = None,
    score_fn: Callable[[FactorDataStore, date], pd.DataFrame] | None = None,
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
    if weighting not in WEIGHTING_METHODS:
        raise ValueError(f"unsupported weighting: {weighting!r} (one of {WEIGHTING_METHODS})")
    if max_sector_pct is not None and not (0.0 < max_sector_pct <= 1.0):
        raise ValueError("max_sector_pct must be in (0, 1] or None")

    config = BacktestRunConfig(
        start=start, end=end, n=n, lookback_days=lookback_days, skip_days=skip_days,
        top_quantile=top_quantile, turnover_cost_bps=turnover_cost_bps,
        delisting=delisting, initial_equity=initial_equity,
        vol_target_annual=vol_target_annual, vol_ewma_span=vol_ewma_span,
        weighting=weighting, vol_lookback_days=vol_lookback_days,
        max_sector_pct=max_sector_pct,
    )

    all_days = store.trading_days(start, end)
    if len(all_days) < 2:
        empty = BacktestSummary(0.0, 0.0, 0.0, 0.0)
        return MomentumBacktestReport(config, [], [], [], [], empty, empty)

    # Serve every downstream price read (momentum scoring, weighting, simulation)
    # from a per-run in-memory cache. Byte-identical to direct store reads; removes
    # the redundant re-scans that dominate a full-history run. See _CachedPriceStore.
    store = _CachedPriceStore(store)  # type: ignore[assignment]

    rebalances_all = _iso_week_last_trading_days(all_days)

    # Cache momentum scores per usable rebalance; record (and skip) thin ones.
    scores_by_date: dict[date, list[str]] = {}  # ranked tickers, best first
    universe_by_date: dict[date, list[str]] = {}
    rebalances: list[date] = []
    skipped: list[date] = []
    for d in rebalances_all:
        try:
            # P12 §3: factor-agnostic selection. Default = momentum (byte-identical to before);
            # a caller passing score_fn (e.g. a composite multi-factor score) backtests any factor.
            if score_fn is not None:
                df = score_fn(store, d)
            else:
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
        return _weigh(store, chosen, d, method=weighting, vol_lookback_days=vol_lookback_days,
                      max_sector_pct=max_sector_pct)

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

    vol_scaled_curve: list[tuple[date, float]] = []
    vol_scaled_metrics: BacktestSummary | None = None
    if vol_target_annual is not None and book_curve:
        vol_scaled_curve = _vol_target_overlay(
            book_curve, vol_target_annual=vol_target_annual,
            span=vol_ewma_span, initial_equity=initial_equity,
        )
        vol_scaled_metrics = _summary(vol_scaled_curve, initial_equity)

    return MomentumBacktestReport(
        config=config,
        rebalances=rebalances,
        equity_curve=book_curve,
        baseline_curve=base_curve,
        holdings=holdings,
        metrics=_summary(book_curve, initial_equity),
        baseline_metrics=_summary(base_curve, initial_equity),
        skipped_rebalances=skipped,
        vol_scaled_curve=vol_scaled_curve,
        vol_scaled_metrics=vol_scaled_metrics,
    )
