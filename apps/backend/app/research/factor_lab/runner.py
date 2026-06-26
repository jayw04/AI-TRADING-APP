"""Factor Lab unified runner (plan v0.2 §3.3).

`run_program(spec, store)` executes the shared research pipeline — score → backtest →
H1/H2/H3 → walk-forward → cost sweep → verdict → evidence package — for any quantile
factor program, driven entirely by a `ProgramSpec`. It is **equivalent by construction**
to the bespoke harnesses: it calls the *same* `run_momentum_backtest`, the *same*
`evidence` stats (incl. the promoted `paired_sharpe_diff_ci`), the *same* 12-1 momentum
reference + rank-blend + monthly cross-sectional correlation the diversifier studies use.
The real-data byte-equivalence acceptance (reproducing the committed verdicts) is the
§5 gate, run offline.

Supports three constructions: `quantile` + `baseline="equal_weight"` (LOW-001 / any
single-factor quantile book); `participation` + `baseline="regime_filter"` (TREND-001:
a cash-aware trend book whose gross exposure falls in downtrends, vs the portfolio-level
regime filter); and `sector_baskets` (SEC-001: top-K sector-neutral equal-weight baskets
vs an all-sector-baskets control, with a V2-vs-V1 construction-isolation H3).

Read-only research (ADR 0019); no order path, no broker, no DB session, no LLM.
"""

from __future__ import annotations

from datetime import date
from typing import Any

import pandas as pd

from app.factor_data import evidence as ev
from app.factor_data.backtest import (
    _CachedPriceStore,
    _iso_week_last_trading_days,
    _simulate,
    run_momentum_backtest,
    simulate_cash_book,
)
from app.factor_data.factors.engine import FactorUnavailable
from app.factor_data.factors.momentum import compute_momentum_batch
from app.factor_data.factors.sector import (
    basket_weights_from_ranking,
    sector_ranking,
    v1_quantile_weights_from_ranking,
)
from app.factor_data.factors.trend import trend_weights
from app.factor_data.regime import market_breadth
from app.factor_data.store import FactorDataStore
from app.factor_data.universe import UniverseUnavailable, universe_asof
from app.research.factor_lab.registry import ScoreFn, build_score_fn
from app.research.factor_lab.spec import ProgramSpec
from app.research.factor_lab.verdict import classify

# The regime-filter control's market-breadth MA window (TREND-001: = the SMA window).
_BREADTH_MA_DAYS = 200

# The platform's diversification reference is the 12-1 single-name momentum cross-section
# (matches the bespoke diversifier studies' MOM_LOOKBACK_DAYS / MOM_SKIP_DAYS).
_MOM_LOOKBACK_DAYS = 252
_MOM_SKIP_DAYS = 21
_MIN_NAMES = 20


def _curve_stats(curve: list[tuple[date, float]]) -> dict[str, float]:
    r = ev.daily_returns(curve)
    c = ev.cagr(curve)
    dd = ev.max_drawdown(curve)
    return {"cagr": c, "sharpe": ev.sharpe(r), "max_drawdown": dd, "calmar": ev.calmar(c, dd)}


def _windows(start: date, end: date, k: int) -> list[tuple[date, date]]:
    step = max(1, (end - start).days // k)
    out = []
    for i in range(k):
        ws = date.fromordinal(start.toordinal() + i * step)
        we = end if i == k - 1 else date.fromordinal(start.toordinal() + (i + 1) * step)
        out.append((ws, we))
    return out


def _single_momentum(store: FactorDataStore, as_of: date, *, n: int) -> pd.Series:
    """12-1 single-name momentum cross-section (the diversification reference)."""
    tickers = universe_asof(store, as_of, n=n)
    mom = compute_momentum_batch(store, tickers, as_of,
                                 lookback_days=_MOM_LOOKBACK_DAYS, skip_days=_MOM_SKIP_DAYS)
    ser = pd.Series({t: v for t, v in mom.items() if v is not None}, dtype="float64").dropna()
    if len(ser) < _MIN_NAMES:
        raise FactorUnavailable(f"momentum reference too thin at {as_of}")
    return ser.sort_values(ascending=False)


def _rank_blend_fn(n: int, score_fn: ScoreFn) -> ScoreFn:
    """A score_fn for the 50/50 momentum+factor rank blend (the H2 blend book)."""
    def blend(store: FactorDataStore, as_of: date) -> pd.DataFrame:
        sm = _single_momentum(store, as_of, n=n).rank()
        fc = score_fn(store, as_of)["score"].rank()
        blended = sm.add(fc, fill_value=sm.mean()).dropna()
        return pd.DataFrame({"score": blended.sort_values(ascending=False)})
    return blend


def _returns_blend(a: list[tuple[date, float]], b: list[tuple[date, float]],
                   *, initial: float) -> list[tuple[date, float]]:
    """A 50/50 daily-rebalanced blend of two equity curves (returns-averaged) — the
    participation/trend H2 blend. Faithful to ``trend_research._blend_curve``."""
    ar, br = ev.daily_returns(a), ev.daily_returns(b)
    dates = [d for d, _ in a][1:]  # daily_returns drops the first point
    n = min(len(ar), len(br), len(dates))
    eq = initial
    out: list[tuple[date, float]] = []
    for i in range(n):
        eq *= 1.0 + 0.5 * (ar[i] + br[i])
        out.append((dates[i], eq))
    return out


def _returns_corr(a: list[float], b: list[float]) -> float | None:
    """Pearson corr of two daily-return series (NaN-safe; None if < 30 paired points).
    Faithful to ``trend_research._returns_corr`` — the trend↔momentum H2 correlation."""
    n = min(len(a), len(b))
    if n < 30:
        return None
    s = pd.concat([pd.Series(a[:n]), pd.Series(b[:n])], axis=1)
    c = float(s.corr().iloc[0, 1])
    return round(c, 3) if c == c else None  # NaN-safe


def _monthly_corr(store: FactorDataStore, spec: ProgramSpec, score_fn: ScoreFn) -> float | None:
    """Average monthly cross-sectional corr(12-1 momentum, factor) — H2 diversification."""
    total, count = 0.0, 0
    for ts in pd.date_range(spec.start, spec.end, freq="MS"):
        d = ts.date()
        try:
            sm = _single_momentum(store, d, n=spec.n)
            fc = score_fn(store, d)["score"]
        except FactorUnavailable:
            continue
        joined = pd.concat([sm.rename("mom"), fc.rename("factor")], axis=1).dropna()
        if len(joined) >= _MIN_NAMES:
            total += float(joined["mom"].corr(joined["factor"]))
            count += 1
    return round(total / count, 3) if count else None


def run_program(spec: ProgramSpec, *, store: FactorDataStore) -> dict[str, Any]:
    """Run a research program end-to-end and return its evidence package dict.

    Dispatches on ``spec.construction``: ``quantile`` (LOW-001 / any single-factor
    quantile book) and ``participation`` (TREND-001 cash-aware trend book + regime-filter
    control). ``sector_baskets`` (SEC-001) lands next. Equivalent by construction — each
    branch calls the same library backtest + ``evidence`` stats the bespoke harnesses do.
    """
    if spec.construction == "quantile":
        return _run_quantile(spec, store=store)
    if spec.construction == "participation":
        return _run_participation(spec, store=store)
    if spec.construction == "sector_baskets":
        return _run_sector_baskets(spec, store=store)
    raise NotImplementedError(
        f"unknown construction {spec.construction!r}; supported = "
        "'quantile' | 'participation' | 'sector_baskets'")


def _run_sector_baskets(spec: ProgramSpec, *, store: FactorDataStore) -> dict[str, Any]:
    """SEC-001 V2 sector-baskets pipeline: top-K sector-neutral equal-weight baskets vs an
    **all-sector-baskets** primary control (H1), a momentum diversifier blend (H2), and a
    V2-vs-V1 construction-isolation comparison + stopping rule (H3). Faithful to
    ``scripts/sector_rotation_v2_research.py`` — one precomputed sector ranking per
    rebalance, same ``_simulate`` book mechanics, same ``evidence`` stats. The K-band is
    reported (robustness, NOT tuned). ``baseline='equal_weight'`` (the continuity
    benchmark, from ``run_momentum_backtest``)."""
    if spec.baseline != "equal_weight":
        raise NotImplementedError(
            f"sector_baskets requires baseline='equal_weight'; got {spec.baseline!r}")
    fp = spec.factor_params
    n = spec.n
    k = int(fp.get("k", 3))
    k_band = [int(x) for x in fp.get("k_band", (2, 4))]
    lookback_days = int(fp.get("lookback_days", 252))
    skip_days = int(fp.get("skip_days", 21))
    top_q_v1 = spec.top_quantile  # V1 stock-level construction quantile (continuity)
    init = spec.initial_equity

    cached: FactorDataStore = _CachedPriceStore(store)  # type: ignore[assignment]
    all_days = cached.trading_days(spec.start, spec.end)
    rebalances_all = _iso_week_last_trading_days(all_days)

    # The one expensive pass: the sector momentum ranking per usable rebalance.
    rankings: dict[date, tuple[list[str], dict[str, list[str]], dict[str, float]]] = {}
    for d in rebalances_all:
        try:
            rankings[d] = sector_ranking(cached, d, n=n, lookback_days=lookback_days,
                                         skip_days=skip_days)
        except (FactorUnavailable, UniverseUnavailable):
            continue
    usable = sorted(rankings)
    n_distinct = max((len(r[0]) for r in rankings.values()), default=0)

    def mk_basket_select(kk: int):
        def sel(d: date) -> dict[str, float]:
            rk = rankings.get(d)
            return basket_weights_from_ranking(rk[0], rk[1], k=kk) if rk else {}
        return sel

    def v1_select(d: date) -> dict[str, float]:
        rk = rankings.get(d)
        return v1_quantile_weights_from_ranking(rk[1], rk[2], top_q=top_q_v1) if rk else {}

    def sim(select, *, s: date = spec.start, e: date = spec.end, bps: float | None = None):
        days = [d for d in all_days if s <= d <= e]
        rebs = [d for d in usable if s <= d <= e]
        curve, _ = _simulate(cached, rebs, days, select, initial_equity=init,
                             turnover_cost_bps=spec.turnover_cost_bps if bps is None else bps)
        return curve

    v2_curve = sim(mk_basket_select(k))                  # the V2 book (top-K baskets)
    allsec_curve = sim(mk_basket_select(n_distinct))     # primary H1 control: all-sector
    v1_curve = sim(v1_select)                            # V1 stock-level (for H3)
    band_curves = {kk: sim(mk_basket_select(kk)) for kk in k_band}

    mom_rep = run_momentum_backtest(cached, spec.start, spec.end, n=n)
    mom_curve, eqw_curve = mom_rep.equity_curve, mom_rep.baseline_curve
    blend_curve = _returns_blend(mom_curve, v2_curve, initial=init)  # H2 momentum+sector

    v2, allsec = _curve_stats(v2_curve), _curve_stats(allsec_curve)
    eqw, mom = _curve_stats(eqw_curve), _curve_stats(mom_curve)
    v1, blend = _curve_stats(v1_curve), _curve_stats(blend_curve)
    band_stats = {f"K={kk}": _curve_stats(c) for kk, c in band_curves.items()}
    band_stats[f"K={k}"] = v2

    # H1: V2 vs all-sector baskets (primary) + vs equal-weight universe (continuity)
    h1_allsec = ev.paired_sharpe_diff_ci(ev.daily_returns(v2_curve), ev.daily_returns(allsec_curve),
                                         n_resamples=spec.bootstrap, seed=spec.seed)
    h1_eqw = ev.paired_sharpe_diff_ci(ev.daily_returns(v2_curve), ev.daily_returns(eqw_curve),
                                      n_resamples=spec.bootstrap, seed=spec.seed)
    # H2: corr(sector signal, single-name momentum) + blend vs momentum-alone
    corr_sum, n_corr = 0.0, 0
    for d in usable:
        _ranked, names_by_sector, sec_mom = rankings[d]
        rows = [(t, sec_mom[s]) for s, ns in names_by_sector.items() for t in ns]
        names = [t for t, _ in rows]
        sm = compute_momentum_batch(cached, names, d, lookback_days=lookback_days,
                                    skip_days=skip_days)
        j = pd.DataFrame({"sec": [v for _, v in rows], "mom": [sm.get(t) for t in names]}).dropna()
        if len(j) >= _MIN_NAMES:
            corr_sum += float(j["sec"].corr(j["mom"]))
            n_corr += 1
    corr = round(corr_sum / n_corr, 3) if n_corr else None
    h2_blend = ev.paired_sharpe_diff_ci(ev.daily_returns(blend_curve), ev.daily_returns(mom_curve),
                                        n_resamples=spec.bootstrap, seed=spec.seed)
    # H3 (read-only): V2 vs V1 construction isolation → feeds the stopping rule, not a gate
    h3 = ev.paired_sharpe_diff_ci(ev.daily_returns(v2_curve), ev.daily_returns(v1_curve),
                                  n_resamples=spec.bootstrap, seed=spec.seed)

    # walk-forward: V2 baskets vs all-sector baskets per window
    wf: list[dict[str, Any]] = []
    n_pos = 0
    for ws, we in _windows(spec.start, spec.end, spec.windows):
        wv2 = _curve_stats(sim(mk_basket_select(k), s=ws, e=we))["sharpe"]
        wbench = _curve_stats(sim(mk_basket_select(n_distinct), s=ws, e=we))["sharpe"]
        wf.append({"window": [str(ws), str(we)], "delta": round(wv2 - wbench, 2)})
        if wv2 - wbench > 0:
            n_pos += 1

    costs = {f"{int(bps)}bps": round(_curve_stats(sim(mk_basket_select(k), bps=bps))["sharpe"], 2)
             for bps in (5.0, 10.0, 20.0, 50.0)}

    h1_real = h1_allsec.excludes_zero_positive()
    consistent = bool([w for w in wf if "delta" in w]) and n_pos >= (spec.windows + 1) // 2 + 1
    blend_helps = (h2_blend.excludes_zero_positive()
                   or (v2["max_drawdown"] > mom["max_drawdown"] and (corr or 1.0) < 0.5))
    h3_benefit = h3.excludes_zero_positive()

    metrics: dict[str, Any] = {
        "h1_real": h1_real, "h1_ci_low": h1_allsec.ci_low, "h1_ci_high": h1_allsec.ci_high,
        "consistent": consistent, "n_windows_pos": n_pos,
        "blend_helps": blend_helps, "corr": corr,
        "h3_benefit": h3_benefit,
    }
    outcome, action = classify(metrics, spec.verdict)
    # stopping rule (informational): no standalone edge AND no construction benefit → archive
    stop = not outcome.startswith("A") and not h3_benefit

    return {
        "program": spec.id, "name": spec.name, "philosophy": spec.philosophy,
        "window": [str(spec.start), str(spec.end)], "n": n, "k": k, "n_sectors": n_distinct,
        "construction": f"sector-neutral top-{k} equal-weight baskets",
        "n_rebalances": len(usable),
        "factor": spec.factor, "factor_params": dict(spec.factor_params),
        "books": {"v2_baskets": v2, "all_sector_baskets": allsec, "equal_weight": eqw,
                  "momentum": mom, "v1_stock_level": v1, "blend": blend},
        "k_band": band_stats,
        "H1_vs_allsec": {"delta": h1_allsec.delta, "ci_low": h1_allsec.ci_low,
                         "ci_high": h1_allsec.ci_high},
        "H1_vs_eqw": {"delta": h1_eqw.delta, "ci_low": h1_eqw.ci_low, "ci_high": h1_eqw.ci_high},
        "H2_corr_with_momentum": corr,
        "H2_blend_vs_momentum": {"delta": h2_blend.delta,
                                 "ci_low": h2_blend.ci_low, "ci_high": h2_blend.ci_high},
        "H3_v2_vs_v1": {"delta": h3.delta, "ci_low": h3.ci_low, "ci_high": h3.ci_high},
        "walk_forward": wf, "n_windows_beats_allsec": f"{n_pos}/{spec.windows}",
        "cost_sweep_sharpe": costs,
        "stop": stop, "h3_construction_benefit": h3_benefit,
        "metrics": metrics, "outcome": outcome, "action": action,
    }


def _run_participation(spec: ProgramSpec, *, store: FactorDataStore) -> dict[str, Any]:
    """TREND-001 participation pipeline: a cash-aware trend book (gross falls in
    downtrends) vs equal-weight (H1), a momentum blend (H2), and downside vs the
    portfolio-level regime filter (H3). Faithful to ``scripts/trend_research.py`` —
    same ``simulate_cash_book`` mechanics, same ``evidence`` stats, same verdict shape.
    The ``baseline='regime_filter'`` competing-explanation control is required."""
    if spec.baseline != "regime_filter":
        raise NotImplementedError(
            f"participation requires baseline='regime_filter'; got {spec.baseline!r}")
    n = spec.n
    sma_days = int(spec.factor_params.get("sma_days", 200))

    def _trend_select(s: FactorDataStore):
        def sel(d: date) -> dict[str, float]:
            return trend_weights(s, d, n=n, sma_days=sma_days)
        return sel

    def _regime_select(s: FactorDataStore):
        def sel(d: date) -> dict[str, float]:
            universe = universe_asof(s, d, n=n)
            if not universe:
                return {}
            breadth = market_breadth(s, d, n=n, ma_days=_BREADTH_MA_DAYS)
            if breadth is None or breadth < 0.5:
                return {}  # risk-off → cash
            w = 1.0 / len(universe)
            return {t: w for t in universe}
        return sel

    def run_trend(s_start: date, s_end: date, *, cost_bps: float | None = None):
        cached: FactorDataStore = _CachedPriceStore(store)  # type: ignore[assignment]
        days = cached.trading_days(s_start, s_end)
        rebs = _iso_week_last_trading_days(days)
        return simulate_cash_book(
            cached, rebs, days, _trend_select(cached), initial_equity=spec.initial_equity,
            turnover_cost_bps=spec.turnover_cost_bps if cost_bps is None else cost_bps)

    def run_regime(s_start: date, s_end: date) -> list[tuple[date, float]]:
        cached: FactorDataStore = _CachedPriceStore(store)  # type: ignore[assignment]
        days = cached.trading_days(s_start, s_end)
        rebs = _iso_week_last_trading_days(days)
        curve, _ = simulate_cash_book(
            cached, rebs, days, _regime_select(cached), initial_equity=spec.initial_equity)
        return curve

    mom_rep = run_momentum_backtest(store, spec.start, spec.end, n=n)
    eq_curve = mom_rep.baseline_curve
    trend_curve, gross = run_trend(spec.start, spec.end)
    regime_curve = run_regime(spec.start, spec.end)
    blend_curve = _returns_blend(trend_curve, mom_rep.equity_curve, initial=spec.initial_equity)

    mom, eqw = _curve_stats(mom_rep.equity_curve), _curve_stats(eq_curve)
    trend = _curve_stats(trend_curve)
    regime, blend = _curve_stats(regime_curve), _curve_stats(blend_curve)

    tr = ev.daily_returns(trend_curve)
    mr = ev.daily_returns(mom_rep.equity_curve)
    er = ev.daily_returns(eq_curve)
    # H1: trend vs equal-weight (standalone risk-adjusted)
    h1 = ev.paired_sharpe_diff_ci(tr, er, n_resamples=spec.bootstrap, seed=spec.seed)
    # H2: corr(trend, momentum) + blend vs momentum-alone
    corr = _returns_corr(tr, mr)
    h2_blend = ev.paired_sharpe_diff_ci(ev.daily_returns(blend_curve), mr,
                                        n_resamples=spec.bootstrap, seed=spec.seed)
    # H3: downside + the competing-explanation A/B vs the regime filter
    dd_vs_mom = round(trend["max_drawdown"] - mom["max_drawdown"], 4)   # >0 ⇒ shallower
    dd_vs_eqw = round(trend["max_drawdown"] - eqw["max_drawdown"], 4)
    dd_vs_regime = round(trend["max_drawdown"] - regime["max_drawdown"], 4)
    sharpe_vs_regime = round(trend["sharpe"] - regime["sharpe"], 3)
    gross_vals = [g for _, g in gross]
    gross_mean = round(sum(gross_vals) / len(gross_vals), 3) if gross_vals else None
    gross_min = round(min(gross_vals), 3) if gross_vals else None

    wf: list[dict[str, Any]] = []
    n_pos = n_dd_better = 0
    for ws, we in _windows(spec.start, spec.end, spec.windows):
        try:
            w_trend_curve, _ = run_trend(ws, we)
            w_rep = run_momentum_backtest(store, ws, we, n=n)
            w_eqw = _curve_stats(w_rep.baseline_curve)
            w_tr = _curve_stats(w_trend_curve)
            wf.append({"window": [str(ws), str(we)],
                       "delta": round(w_tr["sharpe"] - w_eqw["sharpe"], 2),
                       "trend_maxdd": round(w_tr["max_drawdown"], 3),
                       "eqw_maxdd": round(w_eqw["max_drawdown"], 3)})
            if w_tr["sharpe"] - w_eqw["sharpe"] > 0:
                n_pos += 1
            if w_tr["max_drawdown"] > w_eqw["max_drawdown"]:  # shallower
                n_dd_better += 1
        except Exception as exc:  # noqa: BLE001
            wf.append({"window": [str(ws), str(we)], "error": repr(exc)})

    costs = {}
    for bps in (5.0, 10.0, 20.0, 50.0):
        cc, _ = run_trend(spec.start, spec.end, cost_bps=bps)
        costs[f"{int(bps)}bps"] = round(_curve_stats(cc)["sharpe"], 2)

    h1_real = h1.excludes_zero_positive()
    consistent = bool([w for w in wf if "delta" in w]) and n_pos >= (spec.windows + 1) // 2 + 1
    blend_helps = h2_blend.excludes_zero_positive()
    beats_regime = sharpe_vs_regime > 0.0 or dd_vs_regime > 0.0

    # verdict metrics — the flat dict the TREND VerdictSpec predicates read
    metrics: dict[str, Any] = {
        "h1_real": h1_real, "h1_ci_low": h1.ci_low, "h1_ci_high": h1.ci_high,
        "consistent": consistent, "n_windows_pos": n_pos,
        "blend_helps": blend_helps, "corr": corr,
        "dd_vs_mom": dd_vs_mom, "dd_vs_eqw": dd_vs_eqw,
        "beats_regime": beats_regime, "subsumed": not beats_regime,
    }
    outcome, action = classify(metrics, spec.verdict)

    return {
        "program": spec.id, "name": spec.name, "philosophy": spec.philosophy,
        "window": [str(spec.start), str(spec.end)], "n": n,
        "construction": f"participation per-name close>{sma_days}d SMA, in-trend 1/N, cash rest",
        "factor": spec.factor, "factor_params": dict(spec.factor_params),
        "books": {"momentum": mom, "trend": trend, "blend": blend,
                  "equal_weight": eqw, "regime_eqw": regime},
        "H1_vs_eqw": {"delta": h1.delta, "ci_low": h1.ci_low, "ci_high": h1.ci_high},
        "H2_corr_with_momentum": corr,
        "H2_blend_vs_momentum": {"delta": h2_blend.delta,
                                 "ci_low": h2_blend.ci_low, "ci_high": h2_blend.ci_high},
        "H3_maxdd_vs_momentum": dd_vs_mom, "H3_maxdd_vs_eqw": dd_vs_eqw,
        "H3_maxdd_vs_regime_filter": dd_vs_regime, "H3_sharpe_vs_regime_filter": sharpe_vs_regime,
        "H3_windows_shallower_dd": f"{n_dd_better}/{spec.windows}",
        "participation_gross_mean": gross_mean, "participation_gross_min": gross_min,
        "walk_forward": wf, "n_windows_beats_eqw": f"{n_pos}/{spec.windows}",
        "cost_sweep_sharpe": costs,
        "beats_regime_filter": beats_regime, "subsumed_by_regime_filter": not beats_regime,
        "metrics": metrics, "outcome": outcome, "action": action,
    }


def _run_quantile(spec: ProgramSpec, *, store: FactorDataStore) -> dict[str, Any]:
    """Run a quantile factor program end-to-end and return its evidence package dict."""
    if spec.baseline != "equal_weight":
        raise NotImplementedError(
            f"baseline {spec.baseline!r} lands with sector_baskets; quantile = 'equal_weight'")

    n = spec.n
    score_fn = build_score_fn(spec.factor, n, dict(spec.factor_params))

    # books: program (quantile), momentum reference (harness default), 50/50 rank blend
    book_rep = run_momentum_backtest(
        store, spec.start, spec.end, n=n, score_fn=score_fn,
        top_quantile=spec.top_quantile, weighting=spec.weighting,
        turnover_cost_bps=spec.turnover_cost_bps,
        vol_target_annual=spec.vol_target_annual, max_sector_pct=spec.max_sector_pct)
    mom_rep = run_momentum_backtest(store, spec.start, spec.end, n=n)
    blend_rep = run_momentum_backtest(
        store, spec.start, spec.end, n=n, score_fn=_rank_blend_fn(n, score_fn),
        turnover_cost_bps=spec.turnover_cost_bps)
    eq_curve = book_rep.baseline_curve

    book, mom = _curve_stats(book_rep.equity_curve), _curve_stats(mom_rep.equity_curve)
    eqw, blend = _curve_stats(eq_curve), _curve_stats(blend_rep.equity_curve)

    book_r = ev.daily_returns(book_rep.equity_curve)
    eq_r = ev.daily_returns(eq_curve)
    mom_r = ev.daily_returns(mom_rep.equity_curve)

    # H1: program vs equal-weight (standalone risk-adjusted)
    h1 = ev.paired_sharpe_diff_ci(book_r, eq_r, n_resamples=spec.bootstrap, seed=spec.seed)
    # H2: correlation (monthly cross-section) + blend vs momentum-alone
    corr = _monthly_corr(store, spec, score_fn)
    h2_blend = ev.paired_sharpe_diff_ci(ev.daily_returns(blend_rep.equity_curve), mom_r,
                                        n_resamples=spec.bootstrap, seed=spec.seed)
    # H3: downside vs momentum + equal-weight; walk-forward (book vs eqw); cost sweep
    dd_vs_mom = round(book["max_drawdown"] - mom["max_drawdown"], 4)
    dd_vs_eqw = round(book["max_drawdown"] - eqw["max_drawdown"], 4)

    wf: list[dict[str, Any]] = []
    n_pos = n_dd_better = 0
    for ws, we in _windows(spec.start, spec.end, spec.windows):
        try:
            wr = run_momentum_backtest(store, ws, we, n=n, score_fn=score_fn,
                                       top_quantile=spec.top_quantile, weighting=spec.weighting)
            w_book, w_eqw = _curve_stats(wr.equity_curve), _curve_stats(wr.baseline_curve)
            wf.append({"window": [str(ws), str(we)],
                       "delta": round(w_book["sharpe"] - w_eqw["sharpe"], 2),
                       "book_maxdd": round(w_book["max_drawdown"], 3),
                       "eqw_maxdd": round(w_eqw["max_drawdown"], 3)})
            if w_book["sharpe"] - w_eqw["sharpe"] > 0:
                n_pos += 1
            if w_book["max_drawdown"] > w_eqw["max_drawdown"]:  # shallower
                n_dd_better += 1
        except Exception as exc:  # noqa: BLE001
            wf.append({"window": [str(ws), str(we)], "error": repr(exc)})

    costs = {}
    for bps in (5.0, 10.0, 20.0, 50.0):
        cr = run_momentum_backtest(store, spec.start, spec.end, n=n, score_fn=score_fn,
                                   top_quantile=spec.top_quantile, weighting=spec.weighting,
                                   turnover_cost_bps=bps)
        costs[f"{int(bps)}bps"] = round(_curve_stats(cr.equity_curve)["sharpe"], 2)

    # verdict metrics — the standard flat dict the spec's VerdictSpec predicates read
    metrics: dict[str, Any] = {
        "h1_real": h1.excludes_zero_positive(),
        "h1_ci_low": h1.ci_low, "h1_ci_high": h1.ci_high,
        "consistent": bool([w for w in wf if "delta" in w])
        and n_pos >= (spec.windows + 1) // 2 + 1,
        "n_windows_pos": n_pos,
        "blend_helps": h2_blend.excludes_zero_positive(),
        "corr": corr,
        "dd_vs_mom": dd_vs_mom, "dd_vs_eqw": dd_vs_eqw,
        "beats_regime": False,   # set by the regime baseline (trend) in a later session
        "subsumed": False,
    }
    outcome, action = classify(metrics, spec.verdict)

    return {
        "program": spec.id, "name": spec.name, "philosophy": spec.philosophy,
        "window": [str(spec.start), str(spec.end)], "n": n,
        "construction": f"{spec.construction} top_quantile={spec.top_quantile} {spec.weighting}",
        "factor": spec.factor, "factor_params": dict(spec.factor_params),
        "books": {"program": book, "momentum": mom, "equal_weight": eqw, "blend": blend},
        "H1_vs_eqw": {"delta": h1.delta, "ci_low": h1.ci_low, "ci_high": h1.ci_high},
        "H2_corr_with_momentum": corr,
        "H2_blend_vs_momentum": {"delta": h2_blend.delta,
                                 "ci_low": h2_blend.ci_low, "ci_high": h2_blend.ci_high},
        "H3_maxdd_vs_momentum": dd_vs_mom, "H3_maxdd_vs_eqw": dd_vs_eqw,
        "H3_windows_shallower_dd": f"{n_dd_better}/{spec.windows}",
        "walk_forward": wf, "n_windows_beats_eqw": f"{n_pos}/{spec.windows}",
        "cost_sweep_sharpe": costs,
        "metrics": metrics, "outcome": outcome, "action": action,
    }
