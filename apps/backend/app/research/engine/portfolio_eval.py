"""Portfolio-construction evidence shaping (P10 Phase 3A §4.5–§4.6).

Turns a ``MomentumBacktestReport`` into the *standard* Research-Engine package every
``portfolio_construction`` experiment emits — a flat ``metrics_summary`` the scorecard
reads, a richer ``metrics_detail`` (incl. per-regime slices), and the standard
**evidence bundle** of artifacts (equity / drawdown / rolling-* curves, sector weights,
top holdings, rebalance log). It also runs **health checks** that reject bad data at
run time.

This module *computes nothing about the market* — it only reshapes an already-run
backtest and reads prices/sectors the store already holds (ADR 0019 read-only; off the
order path). Capacity metrics use SEP volume we already have; the capacity *model* (§3B —
participation distribution + AUM ceiling, robust to the survivorship-free delisting tail)
lives in ``_capacity`` below.
"""

from __future__ import annotations

import json
import math
import statistics
from collections.abc import Sequence
from datetime import date, datetime, time, timedelta
from typing import Any

import pandas as pd

from app.factor_data.backtest import MomentumBacktestReport, RebalanceHoldings
from app.factor_data.store import FactorDataStore
from app.research.engine.orchestrator import ResearchArtifact, RunnerResult
from app.strategies import metrics

_ROLL_WINDOW = 63          # ~3 trading months for rolling Sharpe / vol
_ADV_LOOKBACK_DAYS = 20    # trailing window for average dollar volume (capacity)
_TOP_HOLDINGS = 10         # how many names per period in top_holdings_by_period
# §3B capacity model: a single trade is "comfortably tradeable" at <= this share of a
# name's average daily dollar volume — the standard institutional liquidity rule of thumb
# (a trade of 10% ADV clears in ~a day without dominating the tape). The capacity *ceiling*
# is the AUM at which the strategy's marginal (95th-percentile) trade reaches this share.
_TARGET_PARTICIPATION = 0.10


class PortfolioHealthError(RuntimeError):
    """A portfolio experiment failed a data-quality health check (§4.5 reviewer #11).

    Raised at run time so a bad-data experiment is rejected loudly rather than scored."""


# ---- small curve helpers --------------------------------------------------------

Curve = list[tuple[date, float]]


def _daily_returns(curve: Curve) -> list[float]:
    vals = [e for _, e in curve]
    return [vals[i] / vals[i - 1] - 1.0 for i in range(1, len(vals)) if vals[i - 1] > 0]


def _to_dt_curve(curve: Curve) -> list[tuple[datetime, float]]:
    return [(datetime.combine(d, time()), e) for d, e in curve]


def _years(curve: Curve) -> float:
    if len(curve) < 2:
        return 0.0
    return max((curve[-1][0] - curve[0][0]).days / 365.25, 0.0)


def _sortino(curve: Curve) -> float:
    """Annualized Sortino (rf=0): mean daily return over downside deviation × √252."""
    rets = _daily_returns(curve)
    if len(rets) < 2:
        return 0.0
    mean = sum(rets) / len(rets)
    downside = [min(r, 0.0) ** 2 for r in rets]
    dd = math.sqrt(sum(downside) / len(downside))
    if dd == 0:
        return 0.0
    return (mean / dd) * math.sqrt(252.0)


def _calmar(cagr: float, max_dd: float) -> float:
    """CAGR / |max drawdown| (max_dd is a negative fraction). 0 when dd is flat."""
    return cagr / abs(max_dd) if max_dd != 0 else 0.0


def _ulcer_index(curve: Curve) -> float:
    """Ulcer Index (%): RMS of the drawdown-from-peak series. Lower is calmer."""
    if not curve:
        return 0.0
    peak = curve[0][1]
    sq = []
    for _, v in curve:
        peak = max(peak, v)
        dd_pct = (v - peak) / peak * 100.0 if peak > 0 else 0.0
        sq.append(dd_pct ** 2)
    return math.sqrt(sum(sq) / len(sq))


def _worst_month(curve: Curve) -> float:
    """Worst calendar-month return (last-equity-of-month over previous month-end)."""
    if len(curve) < 2:
        return 0.0
    by_month: dict[tuple[int, int], float] = {}
    for d, v in curve:
        by_month[(d.year, d.month)] = v  # ascending → last of month wins
    eqs = [by_month[k] for k in sorted(by_month)]
    rets = [eqs[i] / eqs[i - 1] - 1.0 for i in range(1, len(eqs)) if eqs[i - 1] > 0]
    return min(rets) if rets else 0.0


def _worst_rolling_3m(curve: Curve, window: int = _ROLL_WINDOW) -> float:
    """Worst trailing-~3-month (``window`` trading-day) return over the curve."""
    vals = [e for _, e in curve]
    if len(vals) <= window:
        return 0.0
    rets = [vals[i] / vals[i - window] - 1.0 for i in range(window, len(vals)) if vals[i - window] > 0]
    return min(rets) if rets else 0.0


def _recovery_days(curve: Curve) -> int:
    """Longest underwater stretch in calendar days (peak → reclaim, or to the end if
    never reclaimed) — a recovery-time proxy."""
    if not curve:
        return 0
    peak = curve[0][1]
    peak_date = curve[0][0]
    worst = 0
    for d, v in curve:
        if v >= peak:
            peak, peak_date = v, d
        else:
            worst = max(worst, (d - peak_date).days)
    return worst


def _drawdown_curve(curve: Curve) -> Curve:
    out: Curve = []
    peak = curve[0][1] if curve else 0.0
    for d, v in curve:
        peak = max(peak, v)
        out.append((d, (v - peak) / peak if peak > 0 else 0.0))
    return out


def _rolling_sharpe(curve: Curve, window: int = _ROLL_WINDOW) -> Curve:
    df = pd.DataFrame(curve, columns=["date", "eq"]).set_index("date")
    rets = df["eq"].pct_change()
    roll = rets.rolling(window, min_periods=window)
    sharpe = (roll.mean() / roll.std()) * math.sqrt(252.0)
    return [(d.date() if hasattr(d, "date") else d, float(v))
            for d, v in sharpe.dropna().items()]


def _rolling_vol(curve: Curve, window: int = _ROLL_WINDOW) -> Curve:
    df = pd.DataFrame(curve, columns=["date", "eq"]).set_index("date")
    vol = df["eq"].pct_change().rolling(window, min_periods=window).std() * math.sqrt(252.0)
    return [(d.date() if hasattr(d, "date") else d, float(v))
            for d, v in vol.dropna().items()]


# ---- stability + turnover (from per-rebalance target weights) --------------------


def _turnover_series(holdings: Sequence[RebalanceHoldings]) -> Curve:
    """One-way turnover (0.5·Σ|Δw| vs the previous rebalance) per rebalance date."""
    out: Curve = []
    prev: dict[str, float] = {}
    for h in holdings:
        keys = set(h.weights) | set(prev)
        t = 0.5 * sum(abs(h.weights.get(k, 0.0) - prev.get(k, 0.0)) for k in keys)
        out.append((h.rebalance_date, t))
        prev = h.weights
    return out


def _stability(holdings: Sequence[RebalanceHoldings]) -> dict[str, float]:
    """Weight-stability across consecutive rebalances (§4.5): the distribution of
    single-name weight changes and names added/removed."""
    per_name_diffs: list[float] = []
    added: list[int] = []
    removed: list[int] = []
    for a, b in zip(holdings[:-1], holdings[1:], strict=False):
        keys = set(a.weights) | set(b.weights)
        per_name_diffs.extend(abs(b.weights.get(k, 0.0) - a.weights.get(k, 0.0)) for k in keys)
        sa, sb = set(a.tickers), set(b.tickers)
        added.append(len(sb - sa))
        removed.append(len(sa - sb))
    return {
        "avg_weight_change": statistics.fmean(per_name_diffs) if per_name_diffs else 0.0,
        "max_weight_change": max(per_name_diffs) if per_name_diffs else 0.0,
        "avg_names_added": statistics.fmean(added) if added else 0.0,
        "avg_names_removed": statistics.fmean(removed) if removed else 0.0,
    }


# ---- capacity (basic metrics now to avoid re-runs — §4.5) ------------------------


def _equity_asof(curve: Curve, d: date, initial: float) -> float:
    """The book equity used to size rebalance ``d`` — the last curve point on/before
    ``d`` (weights apply the next day), or ``initial`` before any return is booked."""
    eq = initial
    for cd, cv in curve:
        if cd <= d:
            eq = cv
        else:
            break
    return eq


def _adv_dollar(store: FactorDataStore, ticker: str, d: date, lookback: int = _ADV_LOOKBACK_DAYS) -> float | None:
    """Trailing average daily *dollar* volume (close·volume) over ``lookback`` trading
    days strictly before ``d``. None when unavailable (caller skips the name)."""
    start = d - timedelta(days=lookback * 2 + 10)
    df = store.get_prices(ticker, start, d, adjusted=False)  # unadjusted → real $ traded
    if df.empty:
        return None
    dv = [
        float(c) * float(v)
        for dt, c, v in zip(df["date"], df["close"], df["volume"], strict=False)
        if c is not None and v is not None and dt.date() < d
    ]
    dv = dv[-lookback:]
    if not dv:
        return None
    mean_dv = statistics.fmean(dv)
    return mean_dv if mean_dv > 0 else None


def _percentile(xs: Sequence[float], q: float) -> float:
    """Linear-interpolated ``q``-quantile (q in [0,1]) of ``xs``. Deterministic;
    0.0 on empty. Used for the capacity distribution (median / p95 / capacity floor)."""
    if not xs:
        return 0.0
    s = sorted(xs)
    if len(s) == 1:
        return s[0]
    pos = q * (len(s) - 1)
    lo = math.floor(pos)
    hi = math.ceil(pos)
    if lo == hi:
        return s[lo]
    return s[lo] * (hi - pos) + s[hi] * (pos - lo)


def _capacity(
    store: FactorDataStore, report: MomentumBacktestReport, turnover_annual: float
) -> dict[str, float]:
    """Capacity model (§3B). For every traded name at every rebalance, participation =
    traded$ / trailing-ADV$ (traded$ = |Δweight| × equity-at-rebalance).

    The survivorship-free universe carries delisting tails whose ADV collapses toward
    zero, so a plain mean of participation is meaningless — a handful of effectively
    untradeable names blow it up (the 3A ``avg 1132%`` artefact). Instead we:

    - flag **untradeable** trades (participation > 100% of a day's volume at this book
      size, or no ADV) and report their fraction separately rather than averaging them in;
    - report a robust **distribution** (notional-weighted mean, median, p95) over the
      tradeable trades — the gate's "ADV participation ≤ 2%" now measures what it intended;
    - translate to a capacity **ceiling**: ``capacity_aum`` is the AUM at which the
      95th-percentile trade would reach ``_TARGET_PARTICIPATION`` of ADV. Participation
      scales linearly with AUM, so per trade the ceiling is ``target × ADV$ / |Δweight|``,
      independent of the backtest's own equity path; the tightest 5% of trades set it.
    """
    initial = report.config.initial_equity
    position_notionals: list[float] = []
    rebalance_notionals: list[float] = []
    parts: list[tuple[float, float]] = []  # (participation_at_book, traded$) — tradeable only
    cap_aums: list[float] = []             # per-trade AUM ceiling at the target participation
    traded_count = 0
    untradeable = 0
    prev: dict[str, float] = {}
    for h in report.holdings:
        eq = _equity_asof(report.equity_curve, h.rebalance_date, initial)
        keys = set(h.weights) | set(prev)
        traded_notional = 0.0
        for tk in keys:
            dw = abs(h.weights.get(tk, 0.0) - prev.get(tk, 0.0))
            if dw <= 0:
                continue
            traded = dw * eq
            traded_notional += traded
            traded_count += 1
            adv = _adv_dollar(store, tk, h.rebalance_date)
            if adv is None or adv <= 0 or (traded / adv) > 1.0:
                untradeable += 1  # no/near-zero liquidity at this size — would be screened out
                continue
            parts.append((traded / adv, traded))
            cap_aums.append(_TARGET_PARTICIPATION * adv / dw)
        position_notionals.extend(w * eq for w in h.weights.values())
        rebalance_notionals.append(traded_notional)
        prev = h.weights

    notional_sum = sum(t for _, t in parts)
    notional_weighted = (sum(p * t for p, t in parts) / notional_sum) if notional_sum > 0 else 0.0
    participations = [p for p, _ in parts]
    return {
        "avg_position_size": statistics.fmean(position_notionals) if position_notionals else 0.0,
        # §3B: notional-weighted participation over TRADEABLE trades — the economically
        # meaningful 'average' (was a raw mean the 3A run blew up to ~1132%). Lower better.
        "avg_adv_participation": notional_weighted,
        "adv_participation_median": _percentile(participations, 0.50),
        "adv_participation_p95": _percentile(participations, 0.95),
        # AUM at which 95% of trades stay ≤ target participation. Higher = more capacity.
        "capacity_aum": _percentile(cap_aums, 0.05) if cap_aums else 0.0,
        # share of trades that are untradeable at this book size (delisting-tail surface).
        "untradeable_trade_fraction": (untradeable / traded_count) if traded_count else 0.0,
        "avg_daily_turnover": turnover_annual / 252.0,
        "max_rebalance_notional": max(rebalance_notionals) if rebalance_notionals else 0.0,
    }


# ---- regime slices (§4.6 — reporting only, never a construction switch) ----------


def _regime_returns(report: MomentumBacktestReport) -> dict[str, dict[str, float]]:
    """Slice the book's daily returns by regime, classified from the *baseline* curve:
    bull/bear = baseline above/below its 200-day MA; high/low-vol = trailing 21-day
    realized vol above/below its median. A reporting slice only — the median is a
    post-hoc labeling, it never feeds construction (§4.6, §8 #5)."""
    if not report.baseline_curve or not report.equity_curve:
        return {}
    base = pd.DataFrame(report.baseline_curve, columns=["date", "eq"]).set_index("date")
    book = pd.DataFrame(report.equity_curve, columns=["date", "eq"]).set_index("date")
    book_rets = book["eq"].pct_change()

    ma = base["eq"].rolling(200, min_periods=200).mean()
    bull = base["eq"] > ma                                  # trailing → no look-ahead
    base_rets = base["eq"].pct_change()
    rvol = base_rets.rolling(21, min_periods=21).std()
    high_vol = rvol > rvol.median()                         # median = reporting label

    slices = {
        "bull": bull, "bear": (~bull) & ma.notna(),
        "high_vol": high_vol, "low_vol": (~high_vol) & rvol.notna(),
    }
    out: dict[str, dict[str, float]] = {}
    for name, mask in slices.items():
        mask = mask.reindex(book_rets.index).fillna(False)
        rets = book_rets[mask].dropna()
        if len(rets) < 2:
            out[name] = {"days": int(len(rets)), "ann_return": 0.0, "ann_vol": 0.0, "sharpe": 0.0}
            continue
        mean, std = float(rets.mean()), float(rets.std())
        out[name] = {
            "days": int(len(rets)),
            "ann_return": mean * 252.0,
            "ann_vol": std * math.sqrt(252.0),
            "sharpe": (mean / std) * math.sqrt(252.0) if std > 0 else 0.0,
        }
    return out


# ---- evidence bundle (§4.5 / §4.9) ----------------------------------------------


def _sector_weights_over_time(
    store: FactorDataStore | None, holdings: Sequence[RebalanceHoldings]
) -> list[dict[str, Any]]:
    if store is None:
        return []
    out: list[dict[str, Any]] = []
    for h in holdings:
        secs = store.get_sectors(list(h.weights))
        agg: dict[str, float] = {}
        for tk, w in h.weights.items():
            sec = secs.get(tk) or "UNKNOWN"
            agg[sec] = agg.get(sec, 0.0) + w
        out.append({"date": h.rebalance_date.isoformat(), "sectors": agg})
    return out


def _top_holdings_by_period(holdings: Sequence[RebalanceHoldings]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for h in holdings:
        top = sorted(h.weights.items(), key=lambda kv: (-kv[1], kv[0]))[:_TOP_HOLDINGS]
        out.append({"date": h.rebalance_date.isoformat(),
                    "holdings": [{"ticker": t, "weight": round(w, 6)} for t, w in top]})
    return out


def _rebalance_log(report: MomentumBacktestReport) -> list[dict[str, Any]]:
    turnover = dict(_turnover_series(report.holdings))
    return [
        {
            "date": h.rebalance_date.isoformat(),
            "n_names": len(h.tickers),
            "turnover": round(turnover.get(h.rebalance_date, 0.0), 6),
            "realized_return": round(h.realized_return, 6),
            "tickers": h.tickers,
        }
        for h in report.holdings
    ]


def _curve_json(curve: Curve) -> str:
    return json.dumps([[d.isoformat(), round(v, 6)] for d, v in curve])


def build_evidence_bundle(
    report: MomentumBacktestReport, *, store: FactorDataStore | None = None
) -> list[ResearchArtifact]:
    """The standard evidence bundle (§4.5 reviewer #10): the SAME artifact set for
    every portfolio experiment so experiments are comparable. ``store`` is optional;
    ``sector_weights_over_time`` and the §3B attribution artifacts need it (skipped when
    absent). Reusable by any future portfolio runner."""
    bundle = [
        ResearchArtifact("equity_curve", "equity_curve.json", _curve_json(report.equity_curve)),
        ResearchArtifact("drawdown_curve", "drawdown_curve.json",
                         _curve_json(_drawdown_curve(report.equity_curve))),
        ResearchArtifact("rolling_sharpe", "rolling_sharpe.json",
                         _curve_json(_rolling_sharpe(report.equity_curve))),
        ResearchArtifact("rolling_vol", "rolling_vol.json",
                         _curve_json(_rolling_vol(report.equity_curve))),
        ResearchArtifact("rolling_turnover", "rolling_turnover.json",
                         _curve_json(_turnover_series(report.holdings))),
        ResearchArtifact("sector_weights_over_time", "sector_weights_over_time.json",
                         json.dumps(_sector_weights_over_time(store, report.holdings))),
        ResearchArtifact("top_holdings_by_period", "top_holdings_by_period.json",
                         json.dumps(_top_holdings_by_period(report.holdings))),
        ResearchArtifact("rebalance_log", "rebalance_log.json",
                         json.dumps(_rebalance_log(report))),
    ]
    if store is not None:  # §3B: who drove return / turnover / the worst drawdown
        from app.research.engine.attribution import build_attribution_artifacts
        bundle.extend(build_attribution_artifacts(report, store))
    return bundle


# ---- health checks (§4.5 reviewer #11) ------------------------------------------


def run_health_checks(
    report: MomentumBacktestReport,
    store: FactorDataStore | None = None,
    *,
    sector_completeness_min: float = 0.0,
) -> None:
    """Reject bad-data experiments at run time. Hard failures (empty curve, missing
    benchmark, no rebalances, duplicate holdings, non-finite equity) always raise;
    sector-classification completeness raises only when ``sector_completeness_min`` is
    set (>0) and a store is provided (full-history pools may legitimately lack it)."""
    if not report.equity_curve:
        raise PortfolioHealthError("empty equity curve — no book to evaluate")
    if not report.baseline_curve:
        raise PortfolioHealthError("benchmark (baseline) curve unavailable")
    if not report.holdings:
        raise PortfolioHealthError("no rebalances executed")
    for d, e in report.equity_curve:
        if not math.isfinite(e):
            raise PortfolioHealthError(f"non-finite equity at {d}")
    for h in report.holdings:
        if len(set(h.tickers)) != len(h.tickers):
            raise PortfolioHealthError(f"duplicate holdings at {h.rebalance_date}")
    if sector_completeness_min > 0 and store is not None:
        names = sorted({t for h in report.holdings for t in h.tickers})
        if names:
            secs = store.get_sectors(names)
            frac = sum(1 for t in names if secs.get(t)) / len(names)
            if frac < sector_completeness_min:
                raise PortfolioHealthError(
                    f"sector completeness {frac:.2f} < min {sector_completeness_min}")


# ---- the shaping entrypoint the runner calls ------------------------------------


def shape_portfolio_result(
    report: MomentumBacktestReport,
    store: FactorDataStore | None = None,
    *,
    is_oos_split: date | None = None,
    sector_completeness_min: float = 0.0,
    benchmark_curve: list[tuple[date, float]] | None = None,
) -> RunnerResult:
    """Reshape a ``MomentumBacktestReport`` into the standard portfolio RunnerResult:
    flat ``metrics_summary`` (scorecard input), rich ``metrics_detail`` (regimes,
    stability/capacity, IS/OOS), and the evidence bundle. Runs health checks first."""
    run_health_checks(report, store, sector_completeness_min=sector_completeness_min)

    curve = report.equity_curve
    m, bm = report.metrics, report.baseline_metrics
    yrs = _years(curve)

    sortino = _sortino(curve)
    calmar = _calmar(m.cagr, m.max_drawdown)
    ulcer = _ulcer_index(curve)
    excess_sharpe = m.sharpe - bm.sharpe
    excess_max_dd = m.max_drawdown - bm.max_drawdown  # both ≤0; ≥0 ⇒ book DD shallower

    turnover_total = sum(t for _, t in _turnover_series(report.holdings))
    turnover_annual = turnover_total / yrs if yrs > 0 else 0.0
    stability = _stability(report.holdings)
    capacity = _capacity(store, report, turnover_annual) if store is not None else {}

    # IS/OOS Sharpe ratio (oos_stability): split at ``is_oos_split`` or the midpoint.
    split = is_oos_split or (curve[len(curve) // 2][0] if curve else None)
    is_curve = [(d, e) for d, e in curve if split is None or d <= split]
    oos_curve = [(d, e) for d, e in curve if split is not None and d > split]
    is_sharpe = metrics.sharpe_ratio(_to_dt_curve(is_curve))
    oos_sharpe = metrics.sharpe_ratio(_to_dt_curve(oos_curve))
    oos_is_ratio = oos_sharpe / is_sharpe if is_sharpe > 0 else 0.0

    roll_sharpe = _rolling_sharpe(curve)
    pos_frac = (sum(1 for _, s in roll_sharpe if s > 0) / len(roll_sharpe)) if roll_sharpe else 0.0

    regimes = _regime_returns(report)

    # §3B attribution (reporting only — who drove return/turnover/drawdown; never gated).
    attribution: dict[str, Any] = {}
    if store is not None:
        from app.research.engine.attribution import attribution_summary
        attribution = attribution_summary(report, store)

    # §3B-3 SPY/Market benchmark (reporting only — excess/beta/alpha vs the market over the
    # book∩SPY overlap; the frozen gate's excess_sharpe still uses the equal-weight baseline).
    spy: dict[str, Any] = {}
    if benchmark_curve:
        from app.research.engine.benchmark import benchmark_metrics
        spy = benchmark_metrics(report.equity_curve, benchmark_curve)

    summary: dict[str, Any] = {
        "sharpe": m.sharpe, "sortino": sortino, "calmar": calmar, "ulcer_index": ulcer,
        "cagr": m.cagr, "total_return": m.total_return, "max_drawdown": m.max_drawdown,
        "worst_month": _worst_month(curve), "worst_rolling_3m": _worst_rolling_3m(curve),
        "recovery_days": _recovery_days(curve),
        "benchmark_sharpe": bm.sharpe, "benchmark_max_drawdown": bm.max_drawdown,
        "excess_sharpe": excess_sharpe, "excess_max_dd": excess_max_dd,
        "turnover_annual": turnover_annual, "n_rebalances": len(report.holdings),
        "oos_is_sharpe_ratio": oos_is_ratio, "rolling_sharpe_positive_frac": pos_frac,
        **stability, **capacity, **attribution, **spy,
    }

    detail: dict[str, Any] = {
        "weighting": report.config.weighting,
        "book_metrics": {"sharpe": m.sharpe, "cagr": m.cagr, "total_return": m.total_return,
                         "max_drawdown": m.max_drawdown},
        "baseline_metrics": {"sharpe": bm.sharpe, "cagr": bm.cagr,
                             "total_return": bm.total_return, "max_drawdown": bm.max_drawdown},
        "vol_scaled_metrics": (
            None if report.vol_scaled_metrics is None else {
                "sharpe": report.vol_scaled_metrics.sharpe,
                "max_drawdown": report.vol_scaled_metrics.max_drawdown,
                "total_return": report.vol_scaled_metrics.total_return,
            }
        ),
        "skipped_rebalances": len(report.skipped_rebalances),
        "is_oos": {"split": split.isoformat() if split else None,
                   "is_sharpe": is_sharpe, "oos_sharpe": oos_sharpe, "ratio": oos_is_ratio},
        "stability": stability,
        "capacity": capacity,
        "attribution": attribution,
        "benchmark_spy": spy,
        "regimes": regimes,
        "turnover_series": [[d.isoformat(), round(t, 6)] for d, t in _turnover_series(report.holdings)],
    }

    return RunnerResult(
        metrics_summary=summary,
        metrics_detail=detail,
        artifacts=build_evidence_bundle(report, store=store),
    )
