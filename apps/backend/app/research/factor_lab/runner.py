"""Factor Lab unified runner (plan v0.2 §3.3).

`run_program(spec, store)` executes the shared research pipeline — score → backtest →
H1/H2/H3 → walk-forward → cost sweep → verdict → evidence package — for any quantile
factor program, driven entirely by a `ProgramSpec`. It is **equivalent by construction**
to the bespoke harnesses: it calls the *same* `run_momentum_backtest`, the *same*
`evidence` stats (incl. the promoted `paired_sharpe_diff_ci`), the *same* 12-1 momentum
reference + rank-blend + monthly cross-sectional correlation the diversifier studies use.
The real-data byte-equivalence acceptance (reproducing the committed verdicts) is the
§5 gate, run offline.

V1 supports `construction="quantile"` + `baseline="equal_weight"` (covers LOW-001 /
SEC-quintile / any single-factor quantile book). `sector_baskets`, `participation`, and
the `regime_filter` baseline land with the sector/trend scorers in the next session.

Read-only research (ADR 0019); no order path, no broker, no DB session, no LLM.
"""

from __future__ import annotations

from datetime import date
from typing import Any

import pandas as pd

from app.factor_data import evidence as ev
from app.factor_data.backtest import run_momentum_backtest
from app.factor_data.factors.engine import FactorUnavailable
from app.factor_data.factors.momentum import compute_momentum_batch
from app.factor_data.store import FactorDataStore
from app.factor_data.universe import universe_asof
from app.research.factor_lab.registry import ScoreFn, build_score_fn
from app.research.factor_lab.spec import ProgramSpec
from app.research.factor_lab.verdict import classify

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
    """Run a quantile factor program end-to-end and return its evidence package dict."""
    if spec.construction != "quantile":
        raise NotImplementedError(
            f"construction {spec.construction!r} lands in a later session; V1 = 'quantile'")
    if spec.baseline != "equal_weight":
        raise NotImplementedError(
            f"baseline {spec.baseline!r} lands with the trend scorer; V1 = 'equal_weight'")

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
