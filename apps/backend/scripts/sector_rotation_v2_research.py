"""SEC-001 V2 — Pure Sector Baskets research (the V2 evidence package, per the approved v0.2 plan).

V1 (top-quintile of strong-sectors' *stocks*) returned verdict **B (Diversifier)**: the standalone edge
(H1 dSharpe +0.16, CI [-0.03, 0.366]) just missed zero. **V2 changes ONLY the construction** — it holds
the top-K strongest sectors as **sector-neutral equal-weight baskets** (each held sector gets a 1/K
sleeve; within a sleeve, equal-weight across that sector's names). The frozen signal (12-1 sector
momentum), universe, window, and cost are byte-for-byte V1's, so any difference is attributable to
construction alone. The thesis: diversifying away single-stock noise shrinks return variance -> tightens
the Sharpe CI -> possibly turns B into A.

Pre-registered hypotheses (none move after results):
  H1 (standalone) — V2 baskets beat an **all-sector equal-weight baskets** benchmark (primary control) and
     the equal-weight universe (V1 continuity); dSharpe CI excludes zero.
  H2 (diversifier) — corr(sector signal, single-name momentum) < 0.5; a momentum+sector blend lifts
     Sharpe and/or cuts drawdown.
  H3 (construction isolation, READ-ONLY) — dSharpe(V2 - V1) paired CI: did diversified baskets actually
     beat V1's stock-level construction? Feeds the stopping rule, not a gate.

Read-only research on the survivorship-free SEP store + the Sharadar `tickers.sector` classification.
K=3 frozen headline; {2,4} reported as a labeled robustness band (no K-tuning). All-sector baskets is the
primary H1 control. Per ADR 0014 + the SEC-001 V2 gate.

    PYTHONPATH=apps/backend apps/backend/.venv/Scripts/python.exe apps/backend/scripts/sector_rotation_v2_research.py \
        --store apps/backend/data/factor_data_full.duckdb --start 2000-01-01 --end 2026-06-12 \
        --n 200 --k 3 --windows 5 --bootstrap 2000 \
        --report-dir docs/implementation/evidence/sec_001_v2_pure_baskets
"""

from __future__ import annotations

import argparse
import json
import math
import random
import sys
import time
from collections import defaultdict
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

import pandas as pd  # noqa: E402

from app.factor_data import evidence as ev  # noqa: E402
from app.factor_data.backtest import (  # noqa: E402
    _CachedPriceStore,
    _iso_week_last_trading_days,
    _simulate,
    run_momentum_backtest,
)
from app.factor_data.factors.momentum import compute_momentum_batch  # noqa: E402
from app.factor_data.store import FactorDataStore  # noqa: E402
from app.factor_data.universe import UniverseUnavailable, universe_asof  # noqa: E402

LOOKBACK_DAYS = 252  # 12-1 momentum (frozen, identical to V1)
SKIP_DAYS = 21
TOP_QUANTILE_V1 = 0.20  # V1 construction: top-quintile of strong-sectors' stocks
MIN_NAMES = 20


# ---------------------------------------------------------------------------
# Pre-computation: sector momentum ranking per rebalance (done ONCE; the K-band,
# benchmark, walk-forward and cost-sweep all slice this cached structure).
# ---------------------------------------------------------------------------
def precompute_rankings(store: FactorDataStore, rebalances: list[date], *, n: int,
                        ) -> dict[date, tuple[list[str], dict[str, list[str]], dict[str, float]]]:
    """Per usable rebalance d -> (sectors ranked strong->weak, {sector: [names]}, {sector: momentum}).

    Thin dates (insufficient universe / no sectored names) are omitted; select_fns return {} for them
    and `_simulate` skips, matching `run_momentum_backtest`'s thin-rebalance handling."""
    out: dict[date, tuple[list[str], dict[str, list[str]], dict[str, float]]] = {}
    for d in rebalances:
        try:
            tickers = universe_asof(store, d, n=n)
        except UniverseUnavailable:
            continue
        if len(tickers) < MIN_NAMES:
            continue
        sectors = store.get_sectors(tickers)
        mom = compute_momentum_batch(store, tickers, d, lookback_days=LOOKBACK_DAYS, skip_days=SKIP_DAYS)
        moms_by_sector: dict[str, list[float]] = defaultdict(list)
        names_by_sector: dict[str, list[str]] = defaultdict(list)
        for t in tickers:
            s, m = sectors.get(t), mom.get(t)
            if s is not None and m is not None:
                moms_by_sector[s].append(m)
                names_by_sector[s].append(t)
        if not moms_by_sector:
            continue
        sec_mom = {s: sum(v) / len(v) for s, v in moms_by_sector.items()}
        ranked = sorted(sec_mom, key=lambda s: sec_mom[s], reverse=True)
        out[d] = (ranked, dict(names_by_sector), sec_mom)
    return out


def basket_weights(ranked: list[str], names_by_sector: dict[str, list[str]], k: int) -> dict[str, float]:
    """Sector-neutral top-K baskets: each of the K strongest sectors gets a 1/K sleeve, equal-weight
    within. A name's weight = (1/K)*(1/n_sector). Sum=1, long-only. K>=len(ranked) => all sectors."""
    chosen = [s for s in ranked[:k] if names_by_sector.get(s)]
    if not chosen:
        return {}
    sleeve = 1.0 / len(chosen)
    w: dict[str, float] = {}
    for s in chosen:
        names = names_by_sector[s]
        per = sleeve / len(names)
        for t in names:
            w[t] = w.get(t, 0.0) + per
    return w


def v1_weights(names_by_sector: dict[str, list[str]], sec_mom: dict[str, float],
               *, top_q: float = TOP_QUANTILE_V1) -> dict[str, float]:
    """Reproduce V1 from the cached ranking: score each ticker by ITS sector's momentum, hold the
    top-quintile, equal-weight (no momentum recompute — for the H3 paired comparison)."""
    scored: list[tuple[str, float]] = [
        (t, sec_mom[s]) for s, names in names_by_sector.items() for t in names
    ]
    if not scored:
        return {}
    scored.sort(key=lambda x: x[1], reverse=True)
    k = max(1, math.ceil(len(scored) * top_q))
    chosen = [t for t, _ in scored[:k]]
    w = 1.0 / len(chosen)
    return {t: w for t in chosen}


# ---------------------------------------------------------------------------
# Stats helpers (mirror the V1 script for an identical evidence math).
# ---------------------------------------------------------------------------
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
            idx.extend((s0 + j) % n for j in range(block))
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
    return lo == lo and lo > 0  # NaN-safe: NaN != NaN


def _blend_curve(a: list[tuple[date, float]], b: list[tuple[date, float]],
                 *, initial: float) -> list[tuple[date, float]]:
    """50/50 daily-return blend of two equity curves (a momentum + sector overlay) — the H2 blend."""
    ra, rb = ev.daily_returns(a), ev.daily_returns(b)
    n = min(len(ra), len(rb))
    dates = [d for d, _ in a[1:n + 1]]  # i-th return is the a[i]->a[i+1] transition -> label a[i+1]
    eq = initial
    out: list[tuple[date, float]] = []
    for i in range(n):
        eq *= 1.0 + 0.5 * ra[i] + 0.5 * rb[i]
        out.append((dates[i], eq))
    return out


def _git_sha() -> str:
    import subprocess
    try:
        return subprocess.run(["git", "rev-parse", "--short", "HEAD"],
                              capture_output=True, text=True, check=True).stdout.strip()
    except Exception:
        return "unknown"


def main() -> int:
    ap = argparse.ArgumentParser(description="SEC-001 V2 Pure Sector Baskets research")
    ap.add_argument("--store", default=None)
    ap.add_argument("--start", default="2000-01-01")
    ap.add_argument("--end", default="2026-06-12")
    ap.add_argument("--n", type=int, default=200)
    ap.add_argument("--k", type=int, default=3, help="sectors held (headline, frozen)")
    ap.add_argument("--k-band", type=int, nargs="*", default=[2, 4], help="robustness band (not tuned)")
    ap.add_argument("--windows", type=int, default=5)
    ap.add_argument("--bootstrap", type=int, default=2000)
    ap.add_argument("--seed", type=int, default=17)
    ap.add_argument("--initial-equity", type=float, default=100_000.0)
    ap.add_argument("--report-dir", default=None)
    args = ap.parse_args()
    try:  # never let a non-ASCII char in a verdict string kill a long run on a cp1252 pipe
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]
    except Exception:
        pass
    start, end = date.fromisoformat(args.start), date.fromisoformat(args.end)
    K, INIT = args.k, args.initial_equity
    started = time.monotonic()
    exp_id = f"EXP-{datetime.now(UTC):%Y%m%d-%H%M%S}-sec001v2"

    store = FactorDataStore(db_path=args.store, read_only=True)
    try:
        cstore: FactorDataStore = _CachedPriceStore(store)  # type: ignore[assignment]  # one shared cache
        all_days = store.trading_days(start, end)
        rebalances = _iso_week_last_trading_days(all_days)

        # --- the one expensive pass: sector momentum ranking per rebalance ---
        rankings = precompute_rankings(cstore, rebalances, n=args.n)
        usable = sorted(rankings)
        n_distinct = max((len(r[0]) for r in rankings.values()), default=0)

        def mk_basket_select(k: int):
            def sel(d: date) -> dict[str, float]:
                rk = rankings.get(d)
                return basket_weights(rk[0], rk[1], k) if rk else {}
            return sel

        def v1_select(d: date) -> dict[str, float]:
            rk = rankings.get(d)
            return v1_weights(rk[1], rk[2]) if rk else {}

        def sim(select, *, s: date = start, e: date = end, bps: float = 10.0):
            days = [d for d in all_days if s <= d <= e]
            rebs = [d for d in usable if s <= d <= e]
            curve, _ = _simulate(cstore, rebs, days, select, initial_equity=INIT,
                                 turnover_cost_bps=bps)
            return curve

        # --- books (all from cached rankings; fast) ---
        v2_curve = sim(mk_basket_select(K))                       # the V2 book (top-K baskets)
        allsec_curve = sim(mk_basket_select(n_distinct))          # primary H1 control: all-sector baskets
        v1_curve = sim(v1_select)                                 # V1 book (for H3)
        band_curves = {k: sim(mk_basket_select(k)) for k in args.k_band}

        # momentum book + equal-weight-universe baseline (one canonical run_momentum_backtest)
        mom_rep = run_momentum_backtest(cstore, start, end, n=args.n)
        mom_curve, eqw_curve = mom_rep.equity_curve, mom_rep.baseline_curve

        blend_curve = _blend_curve(mom_curve, v2_curve, initial=INIT)  # H2: momentum + sector overlay

        stats = {
            "v2_baskets": _curve_stats(v2_curve),
            "all_sector_baskets": _curve_stats(allsec_curve),
            "equal_weight_universe": _curve_stats(eqw_curve),
            "momentum": _curve_stats(mom_curve),
            "v1_stock_level": _curve_stats(v1_curve),
            "blend": _curve_stats(blend_curve),
        }
        band_stats = {f"K={k}": _curve_stats(c) for k, c in band_curves.items()}
        band_stats[f"K={K}"] = stats["v2_baskets"]

        # --- H1: V2 vs all-sector baskets (primary) + vs equal-weight universe (continuity) ---
        h1_allsec = _paired_sharpe_diff_ci(ev.daily_returns(v2_curve), ev.daily_returns(allsec_curve),
                                           n_resamples=args.bootstrap, seed=args.seed)
        h1_eqw = _paired_sharpe_diff_ci(ev.daily_returns(v2_curve), ev.daily_returns(eqw_curve),
                                        n_resamples=args.bootstrap, seed=args.seed)
        # --- H2: corr(sector signal, single-name momentum) + blend vs momentum ---
        corr_sum, n_corr = 0.0, 0
        for d in usable:
            ranked, names_by_sector, sec_mom = rankings[d]
            rows = [(t, sec_mom[s]) for s, ns in names_by_sector.items() for t in ns]
            # single-name momentum for the same names (recompute cheap from cache)
            names = [t for t, _ in rows]
            sm = compute_momentum_batch(cstore, names, d, lookback_days=LOOKBACK_DAYS, skip_days=SKIP_DAYS)
            j = pd.DataFrame({"sec": [v for _, v in rows], "mom": [sm.get(t) for t in names]}).dropna()
            if len(j) >= MIN_NAMES:
                corr_sum += float(j["sec"].corr(j["mom"]))
                n_corr += 1
        corr = round(corr_sum / n_corr, 3) if n_corr else None
        h2_blend = _paired_sharpe_diff_ci(ev.daily_returns(blend_curve), ev.daily_returns(mom_curve),
                                          n_resamples=args.bootstrap, seed=args.seed)
        # --- H3 (read): V2 vs V1 construction ---
        h3 = _paired_sharpe_diff_ci(ev.daily_returns(v2_curve), ev.daily_returns(v1_curve),
                                    n_resamples=args.bootstrap, seed=args.seed)

        # --- walk-forward: V2 baskets vs all-sector baskets per window ---
        wf, n_pos = [], 0
        for ws, we in _windows(start, end, args.windows):
            wv2 = _curve_stats(sim(mk_basket_select(K), s=ws, e=we))["sharpe"]
            wbench = _curve_stats(sim(mk_basket_select(n_distinct), s=ws, e=we))["sharpe"]
            wf.append({"window": [str(ws), str(we)], "v2_sharpe": round(wv2, 2),
                       "allsec_sharpe": round(wbench, 2), "delta": round(wv2 - wbench, 2)})
            if wv2 - wbench > 0:
                n_pos += 1

        # --- cost sweep (V2 book) ---
        costs = {f"{int(bps)}bps": round(_curve_stats(sim(mk_basket_select(K), bps=bps))["sharpe"], 2)
                 for bps in (5.0, 10.0, 20.0, 50.0)}

        # --- verdict (A/B/C/D per the V2 plan; primary H1 control = all-sector baskets) ---
        h1_real = _excludes_zero_pos(h1_allsec)
        consistent = n_pos >= (args.windows + 1) // 2 + 1
        v2 = stats["v2_baskets"]
        blend_helps = _excludes_zero_pos(h2_blend) or \
            (v2["max_drawdown"] > stats["momentum"]["max_drawdown"] and (corr or 1.0) < 0.5)
        if h1_real and consistent:
            outcome = "A — Validated standalone"
            action = "construction turned B->A: standalone Strategy #2 candidate -> governance -> paper"
        elif blend_helps:
            outcome = "B — Diversifier (confirmed)"
            action = "momentum+sector blend / overlay candidate (evidence-gated)"
        elif h1_allsec["ci_high"] < 0:
            outcome = "C — Rejected"
            action = "no edge; archive as a knowledge-base evidence package"
        else:
            outcome = "D — Inconclusive"
            action = "research debt"
        # stopping rule (owner Suggestion 2): no standalone edge AND no construction benefit -> archive
        h3_benefit = _excludes_zero_pos(h3)
        stop = (outcome not in ("A — Validated standalone",)) and not h3_benefit
        stopping_rule = (
            "ARCHIVE Sector Rotation construction: V2 did not achieve a standalone edge and H3 shows no "
            "construction benefit (dSharpe(V2-V1) CI spans zero). Per the v0.2 stopping rule, further "
            "work requires a fundamentally different hypothesis, not more construction tuning."
            if stop else
            "CONTINUE: " + ("V2 validated standalone (A)." if outcome.startswith("A") else
                            "H3 shows construction matters (V2 beats V1) -> a V3 (dynamic weighting) is "
                            "warranted." if h3_benefit else "diversifier value retained.")
        )

        result: dict[str, Any] = {
            "program": "SEC-001", "version": "V2", "experiment_id": exp_id, "git_sha": _git_sha(),
            "data": "SEP survivorship-free + Sharadar tickers.sector",
            "window": [str(start), str(end)], "n": args.n, "k": K, "n_sectors": n_distinct,
            "construction": f"V2 sector-neutral top-{K} equal-weight baskets",
            "n_rebalances": len(usable),
            "books": stats, "k_band": band_stats,
            "H1_v2_vs_allsec_baskets_ci": h1_allsec, "H1_v2_vs_eqw_universe_ci": h1_eqw,
            "H2_corr_sector_momentum": corr, "H2_blend_vs_momentum_ci": h2_blend,
            "H3_v2_vs_v1_ci": h3,
            "walk_forward": wf, "n_windows_v2_beats_allsec": f"{n_pos}/{args.windows}",
            "cost_sweep_v2_sharpe": costs,
            "outcome": outcome, "action": action, "stopping_rule": stopping_rule,
            "duration_s": round(time.monotonic() - started, 1),
        }
    finally:
        store.close()

    b = result["books"]
    print(f"[{exp_id}] SEC-001 V2 Pure Sector Baskets  {start}..{end} n={args.n} K={K}")
    print(f"  V2 baskets   Sharpe {b['v2_baskets']['sharpe']:.2f} maxDD {b['v2_baskets']['max_drawdown']:.1%}")
    print(f"  all-sector   Sharpe {b['all_sector_baskets']['sharpe']:.2f}  | V1 stock-level "
          f"Sharpe {b['v1_stock_level']['sharpe']:.2f}  | momentum Sharpe {b['momentum']['sharpe']:.2f}")
    print(f"  H1 V2-vs-allsec dSharpe {result['H1_v2_vs_allsec_baskets_ci']['delta']:+.2f} "
          f"CI [{result['H1_v2_vs_allsec_baskets_ci']['ci_low']}, "
          f"{result['H1_v2_vs_allsec_baskets_ci']['ci_high']}]; windows {result['n_windows_v2_beats_allsec']}")
    print(f"  H3 V2-vs-V1 dSharpe {result['H3_v2_vs_v1_ci']['delta']:+.2f} "
          f"CI [{result['H3_v2_vs_v1_ci']['ci_low']}, {result['H3_v2_vs_v1_ci']['ci_high']}]  "
          f"corr(sector,mom)={result['H2_corr_sector_momentum']}")
    print(f"  -> OUTCOME: {result['outcome']}: {result['action']}  ({result['duration_s']}s)")
    print(f"  STOPPING RULE: {result['stopping_rule']}")

    if args.report_dir:
        outdir = Path(args.report_dir)
        outdir.mkdir(parents=True, exist_ok=True)
        (outdir / "sector_rotation_v2.json").write_text(json.dumps(result, indent=2, default=str),
                                                        encoding="utf-8")
        (outdir / "sector_rotation_v2.md").write_text(_render(result), encoding="utf-8")
        print(f"  wrote {outdir / 'sector_rotation_v2.json'} + sector_rotation_v2.md")
    return 0


def _render(r: dict[str, Any]) -> str:
    b = r["books"]
    h1a, h1e, h3 = r["H1_v2_vs_allsec_baskets_ci"], r["H1_v2_vs_eqw_universe_ci"], r["H3_v2_vs_v1_ci"]
    h2 = r["H2_blend_vs_momentum_ci"]

    def row(label: str, key: str) -> str:
        s = b[key]
        return (f"| {label} | {s['cagr']:+.2%} | {s['sharpe']:.2f} | {s['max_drawdown']:.1%} | "
                f"{s['calmar']:.2f} |")

    lines = [
        f"# SEC-001 V2 Pure Sector Baskets — Evidence ({r['outcome']})",
        "",
        f"_git {r['git_sha']} · {r['experiment_id']} · {r['data']} · {r['window'][0]}..{r['window'][1]} · "
        f"n={r['n']} · {r['construction']} · {r['n_rebalances']} rebalances · {r['duration_s']}s_",
        "",
        "> Pre-registered (SEC-001 **V2** plan v0.2). V2 changes ONLY construction vs V1 (stock-level -> "
        "sector-neutral baskets); signal/universe/window/cost are V1's. Question: does construction turn "
        "the V1 **diversifier (B)** into a **standalone edge (A)**?",
        "",
        "## Books",
        "",
        "| Book | CAGR | Sharpe | maxDD | Calmar |",
        "|---|---|---|---|---|",
        row("All-sector baskets (H1 control)", "all_sector_baskets"),
        row("Equal-weight universe (continuity)", "equal_weight_universe"),
        row("Momentum (v1.1)", "momentum"),
        row("V1 — stock-level (prior)", "v1_stock_level"),
        row("**V2 — pure sector baskets**", "v2_baskets"),
        row("Momentum+Sector blend (50/50)", "blend"),
        "",
        "## H1 — standalone edge",
        f"- **vs all-sector baskets (primary): dSharpe {h1a['delta']:+.2f}, 95% CI "
        f"[{h1a['ci_low']}, {h1a['ci_high']}]** — "
        f"{'EXCLUDES zero (edge)' if _excludes_zero_pos(h1a) else 'includes zero -> no standalone edge'}.",
        f"- vs equal-weight universe (continuity): dSharpe {h1e['delta']:+.2f}, CI "
        f"[{h1e['ci_low']}, {h1e['ci_high']}].",
        f"- Walk-forward: V2 beats all-sector baskets in **{r['n_windows_v2_beats_allsec']}** windows.",
        "",
        "## H2 — diversifier",
        f"- corr(sector signal, single-name momentum) = **{r['H2_corr_sector_momentum']}** "
        "(low = diversifier).",
        f"- 50/50 momentum+sector blend vs momentum-alone dSharpe {h2['delta']:+.2f}, CI "
        f"[{h2['ci_low']}, {h2['ci_high']}]; V2 maxDD {b['v2_baskets']['max_drawdown']:.1%} vs "
        f"momentum {b['momentum']['max_drawdown']:.1%}.",
        "",
        "## H3 — construction isolation (read-only; informs the stopping rule)",
        f"- **dSharpe(V2 - V1) {h3['delta']:+.2f}, CI [{h3['ci_low']}, {h3['ci_high']}]** — "
        f"{'V2 beats V1 (construction matters)' if _excludes_zero_pos(h3) else 'CI spans zero (construction-neutral)'}.",
        "",
        "## Robustness band (K, NOT tuned — headline K=" + str(r["k"]) + ")",
        "  " + " · ".join(f"{k} Sharpe {s['sharpe']:.2f}" for k, s in r["k_band"].items()),
        "",
        "## Cost sweep (V2 Sharpe)",
        "  " + " · ".join(f"{k} {v}" for k, v in r["cost_sweep_v2_sharpe"].items()),
        "",
        f"## Outcome: **{r['outcome']}** → {r['action']}",
        "",
        f"**Stopping rule:** {r['stopping_rule']}",
        "",
        "_Per ADR 0014 + the SEC-001 V2 gate. No parameter introduced solely to improve historical "
        "performance. Whatever the verdict, the evidence package is the deliverable._",
    ]
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    raise SystemExit(main())
