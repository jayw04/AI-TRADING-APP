"""[DEPRECATED 2026-06-25 — superseded by the Factor Lab, ADR 0026]

Author new work as a ``ProgramSpec`` and run it through
``app.research.factor_lab.runner.run_program(app.research.factor_lab.configs.LOW_001, store=…)``
instead. ``run_program`` reproduces this harness's committed evidence package byte-for-byte
(equivalence proven 2026-06-25; ADR 0026 §5). This bespoke script is **retained, not deleted**, as
the immutable scientific record — its tests stay green and its evidence package stands. Do not add
new programs here.

LOW-001 — Low Volatility research (the evidence package, per the approved pre-registration v0.2).

Tests whether a low-volatility book — hold the lowest-realized-volatility names — (H1) earns a standalone
risk-adjusted OOS edge vs an equal-weight benchmark, (H2) diversifies single-name momentum (low/negative
correlation, blend lifts Sharpe / cuts drawdown), and (H3) delivers genuine downside protection (shallower
drawdown than momentum + the benchmark). Read-only research on the survivorship-free SEP store.

Honest prior: the P10 factor study (PR #142) found low-vol NEGATIVE on the top-200 liquid mega-cap
universe over 2016-2026 — a single momentum regime with no real bear market. LOW-001 is the proper test:
full-cycle survivorship-free 2000-2026 (dot-com, 2008, COVID, 2022), where the anomaly should earn its
keep.

Construction (frozen, V1): each ticker scored by -(trailing 252-day realized volatility) (lowest vol ->
highest score); the factor-agnostic `run_momentum_backtest` holds the top-quintile = the lowest-vol names.
Only the *score* differs from momentum -- a clean A/B. 252-day realized vol is frozen (no optimization).

    PYTHONPATH=apps/backend apps/backend/.venv/Scripts/python.exe apps/backend/scripts/low_vol_research.py \
        --store apps/backend/data/factor_data_full.duckdb --start 2000-01-01 --end 2026-06-12 \
        --n 200 --windows 5 --bootstrap 2000 --report-dir docs/implementation/evidence/low_001_low_volatility
"""

from __future__ import annotations

import argparse
import contextlib
import json
import random
import sys
import time
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

import pandas as pd  # noqa: E402

from app.factor_data import evidence as ev  # noqa: E402
from app.factor_data.backtest import _trailing_vol, run_momentum_backtest  # noqa: E402
from app.factor_data.factors.engine import FactorUnavailable  # noqa: E402
from app.factor_data.factors.momentum import compute_momentum_batch  # noqa: E402
from app.factor_data.store import FactorDataStore  # noqa: E402
from app.factor_data.universe import universe_asof  # noqa: E402

VOL_LOOKBACK_DAYS = 252  # trailing realized vol window (frozen)
MOM_LOOKBACK_DAYS = 252  # 12-1 momentum (for the correlation + blend)
MOM_SKIP_DAYS = 21
MIN_NAMES = 20


def low_vol_score(store: FactorDataStore, as_of: date, *, n: int = 200,
                  min_names: int = MIN_NAMES) -> pd.DataFrame:
    """Score each ticker by -(trailing 252-day realized vol) (lowest vol -> highest score). PIT."""
    tickers = universe_asof(store, as_of, n=n)
    if len(tickers) < min_names:
        raise FactorUnavailable(f"universe too thin at {as_of}: {len(tickers)}")
    scores: dict[str, float] = {}
    for t in tickers:
        v = _trailing_vol(store, t, as_of, VOL_LOOKBACK_DAYS)
        if v is not None and v > 0:
            scores[t] = -v
    ser = pd.Series(scores, dtype="float64").dropna().sort_values(ascending=False)
    if len(ser) < min_names:
        raise FactorUnavailable(f"low-vol score too thin at {as_of}: {len(ser)}")
    return pd.DataFrame({"score": ser})


def single_momentum_score(store: FactorDataStore, as_of: date, *, n: int = 200,
                          min_names: int = MIN_NAMES) -> pd.DataFrame:
    """Single-name 12-1 momentum score (for the correlation + blend)."""
    tickers = universe_asof(store, as_of, n=n)
    mom = compute_momentum_batch(store, tickers, as_of, lookback_days=MOM_LOOKBACK_DAYS,
                                 skip_days=MOM_SKIP_DAYS)
    ser = pd.Series({t: v for t, v in mom.items() if v is not None}, dtype="float64").dropna()
    if len(ser) < min_names:
        raise FactorUnavailable(f"momentum too thin at {as_of}")
    return pd.DataFrame({"score": ser.sort_values(ascending=False)})


def blend_score(store: FactorDataStore, as_of: date, *, n: int = 200) -> pd.DataFrame:
    """Equal-weight blend of (single-name momentum rank + low-vol rank) — the H2 blend book."""
    sm = single_momentum_score(store, as_of, n=n)["score"].rank()
    lv = low_vol_score(store, as_of, n=n)["score"].rank()
    blended = (sm.add(lv, fill_value=sm.mean())).dropna()
    return pd.DataFrame({"score": blended.sort_values(ascending=False)})


def _curve_stats(curve: list[tuple[date, float]]) -> dict[str, float]:
    r = ev.daily_returns(curve)
    c = ev.cagr(curve)
    dd = ev.max_drawdown(curve)
    return {"cagr": c, "sharpe": ev.sharpe(r), "max_drawdown": dd, "calmar": ev.calmar(c, dd)}


def _paired_sharpe_diff_ci(a_r: list[float], b_r: list[float], *, n_resamples: int, seed: int,
                           block: int = 21) -> dict[str, float]:
    """Circular-block paired bootstrap of Sharpe(a) - Sharpe(b) (a=strategy, b=benchmark)."""
    n = min(len(a_r), len(b_r))
    point = ev.sharpe(a_r[:n]) - ev.sharpe(b_r[:n])
    if n < block * 2:
        return {"delta": round(point, 3), "ci_low": float("nan"), "ci_high": float("nan")}
    rng = random.Random(seed)
    diffs: list[float] = []
    for _ in range(n_resamples):
        idx: list[int] = []
        while len(idx) < n:
            s0 = rng.randrange(n)
            idx.extend((s0 + k) % n for k in range(block))
        idx = idx[:n]
        diffs.append(ev.sharpe([a_r[i] for i in idx]) - ev.sharpe([b_r[i] for i in idx]))
    diffs.sort()
    return {"delta": round(point, 3), "ci_low": round(diffs[int(0.025 * n_resamples)], 3),
            "ci_high": round(diffs[min(int(0.975 * n_resamples), n_resamples - 1)], 3)}


def _windows(start: date, end: date, k: int) -> list[tuple[date, date]]:
    step = max(1, (end - start).days // k)
    out = []
    for i in range(k):
        ws = date.fromordinal(start.toordinal() + i * step)
        we = end if i == k - 1 else date.fromordinal(start.toordinal() + (i + 1) * step)
        out.append((ws, we))
    return out


def _excludes_zero_pos(ci: dict[str, float]) -> bool:
    lo = ci["ci_low"]
    return lo == lo and lo > 0  # NaN-safe


def main() -> int:
    with contextlib.suppress(Exception):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]
    ap = argparse.ArgumentParser(description="LOW-001 Low Volatility research")
    ap.add_argument("--store", default=None)
    ap.add_argument("--start", default="2000-01-01")
    ap.add_argument("--end", default="2026-06-12")
    ap.add_argument("--n", type=int, default=200)
    ap.add_argument("--windows", type=int, default=5)
    ap.add_argument("--bootstrap", type=int, default=2000)
    ap.add_argument("--seed", type=int, default=17)
    ap.add_argument("--report-dir", default=None)
    args = ap.parse_args()
    start, end = date.fromisoformat(args.start), date.fromisoformat(args.end)
    started = time.monotonic()
    exp_id = f"EXP-{datetime.now(UTC):%Y%m%d-%H%M%S}-low001"

    store = FactorDataStore(db_path=args.store, read_only=True)
    try:
        n = args.n
        def lv(s: FactorDataStore, d: date) -> pd.DataFrame:
            return low_vol_score(s, d, n=n)
        def bln(s: FactorDataStore, d: date) -> pd.DataFrame:
            return blend_score(s, d, n=n)

        mom_rep = run_momentum_backtest(store, start, end, n=n)
        lv_rep = run_momentum_backtest(store, start, end, n=n, score_fn=lv)
        bln_rep = run_momentum_backtest(store, start, end, n=n, score_fn=bln)
        eq_curve = mom_rep.baseline_curve
        mom, lvs, bln_s = (_curve_stats(mom_rep.equity_curve), _curve_stats(lv_rep.equity_curve),
                           _curve_stats(bln_rep.equity_curve))
        eqw = _curve_stats(eq_curve)

        # H1: low-vol vs equal-weight (risk-adjusted, decisive)
        h1 = _paired_sharpe_diff_ci(ev.daily_returns(lv_rep.equity_curve), ev.daily_returns(eq_curve),
                                    n_resamples=args.bootstrap, seed=args.seed)
        # H2: blend vs momentum-alone + correlation (expect negative/low)
        h2_blend = _paired_sharpe_diff_ci(ev.daily_returns(bln_rep.equity_curve),
                                          ev.daily_returns(mom_rep.equity_curve),
                                          n_resamples=args.bootstrap, seed=args.seed)
        corr_sum, n_corr = 0.0, 0
        for d in (x.date() for x in pd.date_range(start, end, freq="MS")):
            try:
                sm = single_momentum_score(store, d, n=n)["score"]
                lvc = low_vol_score(store, d, n=n)["score"]
            except FactorUnavailable:
                continue
            j = pd.concat([sm.rename("mom"), lvc.rename("lv")], axis=1).dropna()
            if len(j) >= MIN_NAMES:
                corr_sum += float(j["mom"].corr(j["lv"]))
                n_corr += 1
        corr = round(corr_sum / n_corr, 3) if n_corr else None

        # H3: downside protection — drawdown vs benchmarks + per-window low-vol-vs-eqw maxDD
        dd_vs_mom = round(lvs["max_drawdown"] - mom["max_drawdown"], 4)   # >0 => shallower than momentum
        dd_vs_eqw = round(lvs["max_drawdown"] - eqw["max_drawdown"], 4)

        # walk-forward (low-vol vs equal-weight): Sharpe delta + drawdown
        wf, n_pos, n_dd_better = [], 0, 0
        for ws, we in _windows(start, end, args.windows):
            try:
                wr = run_momentum_backtest(store, ws, we, n=n, score_fn=lv)
                w_eqw = _curve_stats(wr.baseline_curve)
                w_lv = _curve_stats(wr.equity_curve)
                wf.append({"window": [str(ws), str(we)], "lv_sharpe": round(w_lv["sharpe"], 2),
                           "eqw_sharpe": round(w_eqw["sharpe"], 2),
                           "delta": round(w_lv["sharpe"] - w_eqw["sharpe"], 2),
                           "lv_maxdd": round(w_lv["max_drawdown"], 3),
                           "eqw_maxdd": round(w_eqw["max_drawdown"], 3)})
                if w_lv["sharpe"] - w_eqw["sharpe"] > 0:
                    n_pos += 1
                if w_lv["max_drawdown"] > w_eqw["max_drawdown"]:  # shallower
                    n_dd_better += 1
            except Exception as exc:
                wf.append({"window": [str(ws), str(we)], "error": repr(exc)})

        # cost sweep (low-vol book)
        costs = {}
        for bps in (5.0, 10.0, 20.0, 50.0):
            cr = run_momentum_backtest(store, start, end, n=n, score_fn=lv, turnover_cost_bps=bps)
            costs[f"{int(bps)}bps"] = round(_curve_stats(cr.equity_curve)["sharpe"], 2)

        # verdict (A/B/C/D per the plan)
        h1_real = _excludes_zero_pos(h1)
        consistent = bool([w for w in wf if "delta" in w]) and n_pos >= (args.windows + 1) // 2 + 1
        # H3 defensive value: materially shallower drawdown than BOTH momentum and eqw, low corr
        defensive = dd_vs_mom > 0.0 and dd_vs_eqw > 0.0 and (corr or 1.0) < 0.5
        blend_helps = _excludes_zero_pos(h2_blend)
        if h1_real and consistent:
            outcome = "A - Validated"
            action = "standalone defensive book candidate -> governance -> paper"
        elif blend_helps or defensive:
            outcome = "B - Diversifier / Defensive"
            action = "defensive sleeve / momentum+low-vol blend candidate (evidence-gated)"
        elif h1["ci_high"] < 0 and not defensive:
            outcome = "C - Rejected"
            action = "no edge; the #142 negative generalizes at full breadth -> knowledge base"
        else:
            outcome = "D - Inconclusive"
            action = "research debt -> broader-universe V2"

        result: dict[str, Any] = {
            "program": "LOW-001", "experiment_id": exp_id, "git_sha": _git_sha(),
            "data": "SEP survivorship-free (full-cycle 2000-2026)",
            "window": [str(start), str(end)], "n": n,
            "construction": "V1 top-quintile lowest 252d realized vol, equal-weight",
            "books": {"momentum": mom, "low_vol": lvs, "blend": bln_s, "equal_weight": eqw},
            "H1_lowvol_vs_eqw_sharpe_ci": h1,
            "H2_corr_mom_lowvol": corr, "H2_blend_vs_momentum_sharpe_ci": h2_blend,
            "H3_maxdd_vs_momentum": dd_vs_mom, "H3_maxdd_vs_eqw": dd_vs_eqw,
            "H3_windows_lowvol_shallower_dd": f"{n_dd_better}/{args.windows}",
            "walk_forward": wf, "n_windows_lowvol_beats_eqw": f"{n_pos}/{args.windows}",
            "cost_sweep_lowvol_sharpe": costs,
            "outcome": outcome, "action": action,
            "duration_s": round(time.monotonic() - started, 1),
        }
    finally:
        store.close()

    b = result["books"]
    print(f"[{exp_id}] LOW-001 Low Volatility  {start}..{end} n={n}")
    print(f"  momentum  Sharpe {b['momentum']['sharpe']:.2f} maxDD {b['momentum']['max_drawdown']:.1%}")
    print(f"  low-vol   Sharpe {b['low_vol']['sharpe']:.2f} maxDD {b['low_vol']['max_drawdown']:.1%}  "
          f"(vs eqw Sharpe {b['equal_weight']['sharpe']:.2f} maxDD {b['equal_weight']['max_drawdown']:.1%})")
    print(f"  H1 lowvol-vs-eqw dSharpe {h1['delta']:+.2f} CI [{h1['ci_low']}, {h1['ci_high']}]; "
          f"windows won {result['n_windows_lowvol_beats_eqw']}")
    print(f"  H2 corr(mom,lowvol)={corr}  blend-vs-mom dSharpe {h2_blend['delta']:+.2f} "
          f"CI [{h2_blend['ci_low']}, {h2_blend['ci_high']}]")
    print(f"  H3 maxDD vs mom {dd_vs_mom:+.1%} vs eqw {dd_vs_eqw:+.1%}; shallower in "
          f"{result['H3_windows_lowvol_shallower_dd']} windows")
    print(f"  -> OUTCOME: {outcome}: {action}  ({result['duration_s']}s)")

    if args.report_dir:
        outdir = Path(args.report_dir)
        outdir.mkdir(parents=True, exist_ok=True)
        (outdir / "low_volatility.json").write_text(json.dumps(result, indent=2, default=str),
                                                    encoding="utf-8")
        (outdir / "low_volatility.md").write_text(_render(result), encoding="utf-8")
        print(f"  wrote {outdir / 'low_volatility.json'} + low_volatility.md")
    return 0


def _git_sha() -> str:
    import subprocess
    try:
        return subprocess.run(["git", "rev-parse", "--short", "HEAD"],
                              capture_output=True, text=True, check=True).stdout.strip()
    except Exception:
        return "unknown"


def _render(r: dict[str, Any]) -> str:
    b = r["books"]
    h1, h2 = r["H1_lowvol_vs_eqw_sharpe_ci"], r["H2_blend_vs_momentum_sharpe_ci"]

    def row(label: str, key: str) -> str:
        s = b[key]
        return (f"| {label} | {s['cagr']:+.2%} | {s['sharpe']:.2f} | {s['max_drawdown']:.1%} | "
                f"{s['calmar']:.2f} |")

    lines = [
        f"# LOW-001 Low Volatility — Evidence ({r['outcome']})",
        "",
        f"_git {r['git_sha']} · {r['experiment_id']} · {r['data']} · {r['window'][0]}..{r['window'][1]} · "
        f"n={r['n']} · {r['construction']} · {r['duration_s']}s_",
        "",
        "> Pre-registered (LOW-001 plan v0.2). The question: *does Low Volatility add value to the "
        "platform?* — standalone risk-adjusted edge (H1), a diversifier of momentum (H2), or downside "
        "protection (H3). Honest prior: low-vol was negative on the narrow 2016-26 mega-cap window; this "
        "is the full-cycle 2000-2026 test.",
        "",
        "## Books",
        "",
        "| Book | CAGR | Sharpe | maxDD | Calmar |",
        "|---|---|---|---|---|",
        row("Equal-weight (benchmark)", "equal_weight"),
        row("Momentum (v1.1)", "momentum"),
        row("**Low Volatility**", "low_vol"),
        row("Momentum+LowVol blend", "blend"),
        "",
        "## H1 — standalone risk-adjusted edge (low-vol vs equal-weight)",
        f"- **dSharpe {h1['delta']:+.2f}, paired 95% CI [{h1['ci_low']}, {h1['ci_high']}]** — "
        f"{'EXCLUDES zero (edge)' if _excludes_zero_pos(h1) else 'includes zero -> no standalone edge'}.",
        f"- Walk-forward: low-vol beats equal-weight in **{r['n_windows_lowvol_beats_eqw']}** windows.",
        "",
        "## H2 — diversifier (correlation / blend)",
        f"- corr(momentum, low-vol) = **{r['H2_corr_mom_lowvol']}** (negative/low = defensive diversifier).",
        f"- blend vs momentum-alone dSharpe {h2['delta']:+.2f}, CI [{h2['ci_low']}, {h2['ci_high']}].",
        "",
        "## H3 — downside protection (the low-vol signature)",
        f"- low-vol maxDD vs momentum: **{r['H3_maxdd_vs_momentum']:+.1%}** "
        f"(positive = shallower than momentum's {b['momentum']['max_drawdown']:.1%}).",
        f"- low-vol maxDD vs equal-weight: **{r['H3_maxdd_vs_eqw']:+.1%}**.",
        f"- Shallower drawdown than equal-weight in **{r['H3_windows_lowvol_shallower_dd']}** windows.",
        "",
        "## Cost sweep (low-vol Sharpe)",
        "  " + " · ".join(f"{k} {v}" for k, v in r["cost_sweep_lowvol_sharpe"].items()),
        "",
        f"## Outcome: **{r['outcome']}** → {r['action']}",
        "",
        "_Per ADR 0014 + the LOW-001 gate. 252-day realized vol frozen (no optimization). No parameter "
        "introduced solely to improve historical performance. The evidence package is the deliverable._",
    ]
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    raise SystemExit(main())
