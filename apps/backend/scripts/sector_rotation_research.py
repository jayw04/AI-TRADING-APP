"""SEC-001 — Sector Rotation research (the V1 evidence package, per the approved pre-registration).

Tests whether a sector-level relative-strength signal — rotate into the strongest-momentum sectors —
(H1) earns a standalone OOS edge vs an equal-weight benchmark, and/or (H2) diversifies single-name
momentum (low correlation / blend lifts return / cuts drawdown). Read-only research on the
survivorship-free SEP store + the Sharadar `tickers.sector` classification already in the store.

Construction (frozen, V1): each ticker is scored by **its sector's 12-1 momentum** (sector momentum =
equal-weight mean of constituent 12-1 momentum); the factor-agnostic `run_momentum_backtest` then holds
the top-quintile = the strongest sectors' stocks. Only the *score* differs from single-name momentum —
a clean A/B. 12-1 is frozen (no optimization, owner decision).

    PYTHONPATH=apps/backend apps/backend/.venv/Scripts/python.exe apps/backend/scripts/sector_rotation_research.py \
        --store apps/backend/data/factor_data_full.duckdb --start 2000-01-01 --end 2026-06-12 \
        --n 200 --windows 5 --bootstrap 2000 --report-dir docs/implementation/evidence/sec_001_sector_rotation
"""

from __future__ import annotations

import argparse
import json
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
from app.factor_data.backtest import run_momentum_backtest  # noqa: E402
from app.factor_data.factors.engine import FactorUnavailable  # noqa: E402
from app.factor_data.factors.momentum import compute_momentum_batch  # noqa: E402
from app.factor_data.store import FactorDataStore  # noqa: E402
from app.factor_data.universe import universe_asof  # noqa: E402

LOOKBACK_DAYS = 252  # 12-1 momentum (frozen)
SKIP_DAYS = 21


def sector_momentum_score(store: FactorDataStore, as_of: date, *, n: int = 200,
                          min_names: int = 20) -> pd.DataFrame:
    """Score each ticker by its SECTOR's 12-1 momentum (the sector-rotation signal). PIT."""
    tickers = universe_asof(store, as_of, n=n)
    if len(tickers) < min_names:
        raise FactorUnavailable(f"universe too thin at {as_of}: {len(tickers)}")
    sectors = store.get_sectors(tickers)
    mom = compute_momentum_batch(store, tickers, as_of, lookback_days=LOOKBACK_DAYS, skip_days=SKIP_DAYS)
    by_sector: dict[str, list[float]] = defaultdict(list)
    for t in tickers:
        s, m = sectors.get(t), mom.get(t)
        if s and m is not None:
            by_sector[s].append(m)
    sec_mom = {s: sum(v) / len(v) for s, v in by_sector.items() if v}
    scores: dict[str, float] = {}
    for t in tickers:
        s = sectors.get(t)
        if s is not None and s in sec_mom and mom.get(t) is not None:
            scores[t] = sec_mom[s]
    ser = pd.Series(scores, dtype="float64").dropna().sort_values(ascending=False)
    if len(ser) < min_names:
        raise FactorUnavailable(f"sector score too thin at {as_of}: {len(ser)}")
    return pd.DataFrame({"score": ser})


def single_momentum_score(store: FactorDataStore, as_of: date, *, n: int = 200,
                          min_names: int = 20) -> pd.DataFrame:
    """Single-name 12-1 momentum score (for the correlation + blend)."""
    tickers = universe_asof(store, as_of, n=n)
    mom = compute_momentum_batch(store, tickers, as_of, lookback_days=LOOKBACK_DAYS, skip_days=SKIP_DAYS)
    ser = pd.Series({t: v for t, v in mom.items() if v is not None}, dtype="float64").dropna()
    if len(ser) < min_names:
        raise FactorUnavailable(f"momentum too thin at {as_of}")
    return pd.DataFrame({"score": ser.sort_values(ascending=False)})


def blend_score(store: FactorDataStore, as_of: date, *, n: int = 200) -> pd.DataFrame:
    """Equal-weight blend of (single-name momentum rank + sector-rotation rank) — the H2 blend book."""
    sm = single_momentum_score(store, as_of, n=n)["score"].rank()
    sr = sector_momentum_score(store, as_of, n=n)["score"].rank()
    blended = (sm.add(sr, fill_value=sm.mean())).dropna()
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


def main() -> int:
    ap = argparse.ArgumentParser(description="SEC-001 Sector Rotation research")
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
    exp_id = f"EXP-{datetime.now(UTC):%Y%m%d-%H%M%S}-sec001"

    store = FactorDataStore(db_path=args.store, read_only=True)
    try:
        n = args.n
        def sec(s: FactorDataStore, d: date) -> pd.DataFrame:
            return sector_momentum_score(s, d, n=n)
        def bln(s: FactorDataStore, d: date) -> pd.DataFrame:
            return blend_score(s, d, n=n)

        # full-window books: momentum, sector-rotation, blend; equal-weight = baseline_curve
        mom_rep = run_momentum_backtest(store, start, end, n=n)
        sec_rep = run_momentum_backtest(store, start, end, n=n, score_fn=sec)
        bln_rep = run_momentum_backtest(store, start, end, n=n, score_fn=bln)
        eq_curve = mom_rep.baseline_curve  # passive equal-weight universe
        mom, secs, bln_s = (_curve_stats(mom_rep.equity_curve), _curve_stats(sec_rep.equity_curve),
                            _curve_stats(bln_rep.equity_curve))
        eqw = _curve_stats(eq_curve)

        # H1: sector-rotation vs equal-weight (decisive)
        h1 = _paired_sharpe_diff_ci(ev.daily_returns(sec_rep.equity_curve), ev.daily_returns(eq_curve),
                                    n_resamples=args.bootstrap, seed=args.seed)
        # H2: blend vs momentum-alone + correlation
        h2_blend = _paired_sharpe_diff_ci(ev.daily_returns(bln_rep.equity_curve),
                                          ev.daily_returns(mom_rep.equity_curve),
                                          n_resamples=args.bootstrap, seed=args.seed)
        corr_sum, n_corr = 0.0, 0
        for d in (x.date() for x in pd.date_range(start, end, freq="MS")):
            try:
                sm = single_momentum_score(store, d, n=n)["score"]
                sr = sector_momentum_score(store, d, n=n)["score"]
            except FactorUnavailable:
                continue
            j = pd.concat([sm.rename("mom"), sr.rename("sec")], axis=1).dropna()
            if len(j) >= 20:
                corr_sum += float(j["mom"].corr(j["sec"]))
                n_corr += 1
        corr = round(corr_sum / n_corr, 3) if n_corr else None

        # walk-forward (sector vs equal-weight)
        wf = []
        n_pos = 0
        for ws, we in _windows(start, end, args.windows):
            try:
                wr = run_momentum_backtest(store, ws, we, n=n, score_fn=sec)
                ws_eqw = _curve_stats(wr.baseline_curve)["sharpe"]
                ws_sec = _curve_stats(wr.equity_curve)["sharpe"]
                wf.append({"window": [str(ws), str(we)], "sector_sharpe": round(ws_sec, 2),
                           "eqw_sharpe": round(ws_eqw, 2), "delta": round(ws_sec - ws_eqw, 2)})
                if ws_sec - ws_eqw > 0:
                    n_pos += 1
            except Exception as exc:
                wf.append({"window": [str(ws), str(we)], "error": repr(exc)})

        # cost sweep (sector book)
        costs = {}
        for bps in (5.0, 10.0, 20.0, 50.0):
            cr = run_momentum_backtest(store, start, end, n=n, score_fn=sec, turnover_cost_bps=bps)
            costs[f"{int(bps)}bps"] = round(_curve_stats(cr.equity_curve)["sharpe"], 2)

        # verdict (A/B/C/D per the plan)
        h1_real = h1["ci_low"] == h1["ci_low"] and h1["ci_low"] > 0
        consistent = bool([w for w in wf if "delta" in w]) and n_pos >= (args.windows + 1) // 2 + 1
        blend_helps = (h2_blend["ci_low"] == h2_blend["ci_low"] and h2_blend["ci_low"] > 0) or \
                      (secs["max_drawdown"] > mom["max_drawdown"] and (corr or 1.0) < 0.5)
        if h1_real and consistent:
            outcome, action = "A — Validated", "standalone Strategy #2 candidate -> governance -> paper"
        elif blend_helps:
            outcome, action = "B — Diversifier", "momentum+sector blend candidate (evidence-gated)"
        elif (h1["ci_high"] < 0):
            outcome, action = "C — Rejected", "no edge; archive as a knowledge-base evidence package"
        else:
            outcome, action = "D — Inconclusive", "research debt -> future ADR / V2 (baskets)"

        result: dict[str, Any] = {
            "program": "SEC-001", "experiment_id": exp_id, "git_sha": _git_sha(),
            "data": "SEP survivorship-free + Sharadar tickers.sector (11 sectors)",
            "window": [str(start), str(end)], "n": n, "construction": "V1 top-quintile of strong sectors",
            "books": {"momentum": mom, "sector_rotation": secs, "blend": bln_s, "equal_weight": eqw},
            "H1_sector_vs_eqw_sharpe_ci": h1,
            "H2_corr_mom_sector": corr, "H2_blend_vs_momentum_sharpe_ci": h2_blend,
            "walk_forward": wf, "n_windows_sector_beats_eqw": f"{n_pos}/{args.windows}",
            "cost_sweep_sector_sharpe": costs,
            "outcome": outcome, "action": action,
            "duration_s": round(time.monotonic() - started, 1),
        }
    finally:
        store.close()

    print(f"[{exp_id}] SEC-001 Sector Rotation  {start}..{end} n={n}")
    print(f"  momentum  Sharpe {mom['sharpe']:.2f} maxDD {mom['max_drawdown']:.1%}")
    print(f"  sector    Sharpe {secs['sharpe']:.2f} maxDD {secs['max_drawdown']:.1%}  "
          f"(vs eqw Sharpe {eqw['sharpe']:.2f})")
    print(f"  H1 sector-vs-eqw dSharpe {h1['delta']:+.2f} CI [{h1['ci_low']}, {h1['ci_high']}]; "
          f"windows won {result['n_windows_sector_beats_eqw']}")
    print(f"  H2 corr(mom,sector)={corr}  blend-vs-mom dSharpe {h2_blend['delta']:+.2f} "
          f"CI [{h2_blend['ci_low']}, {h2_blend['ci_high']}]")
    print(f"  -> OUTCOME: {outcome}: {action}  ({result['duration_s']}s)")

    if args.report_dir:
        d = Path(args.report_dir)
        d.mkdir(parents=True, exist_ok=True)
        (d / "sector_rotation.json").write_text(json.dumps(result, indent=2, default=str), encoding="utf-8")
        (d / "sector_rotation.md").write_text(_render(result), encoding="utf-8")
        print(f"  wrote {d / 'sector_rotation.json'} + sector_rotation.md")
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
    h1, h2 = r["H1_sector_vs_eqw_sharpe_ci"], r["H2_blend_vs_momentum_sharpe_ci"]
    lines = [
        f"# SEC-001 Sector Rotation — Evidence ({r['outcome']})",
        "",
        f"_git {r['git_sha']} · {r['experiment_id']} · {r['data']} · {r['window'][0]}..{r['window'][1]} · "
        f"n={r['n']} · {r['construction']} · {r['duration_s']}s_",
        "",
        "> Pre-registered (SEC-001 plan v0.2). The question: *does Sector Rotation add value to the "
        "platform?* — as a standalone strategy (H1) or a diversifier of momentum (H2).",
        "",
        "## Books",
        "",
        "| Book | CAGR | Sharpe | maxDD | Calmar |",
        "|---|---|---|---|---|",
        f"| Equal-weight (benchmark) | {b['equal_weight']['cagr']:+.2%} | {b['equal_weight']['sharpe']:.2f} | {b['equal_weight']['max_drawdown']:.1%} | {b['equal_weight']['calmar']:.2f} |",
        f"| Momentum (v1.1) | {b['momentum']['cagr']:+.2%} | {b['momentum']['sharpe']:.2f} | {b['momentum']['max_drawdown']:.1%} | {b['momentum']['calmar']:.2f} |",
        f"| **Sector Rotation** | {b['sector_rotation']['cagr']:+.2%} | {b['sector_rotation']['sharpe']:.2f} | {b['sector_rotation']['max_drawdown']:.1%} | {b['sector_rotation']['calmar']:.2f} |",
        f"| Momentum+Sector blend | {b['blend']['cagr']:+.2%} | {b['blend']['sharpe']:.2f} | {b['blend']['max_drawdown']:.1%} | {b['blend']['calmar']:.2f} |",
        "",
        "## H1 — standalone edge (sector vs equal-weight)",
        f"- **dSharpe {h1['delta']:+.2f}, paired 95% CI [{h1['ci_low']}, {h1['ci_high']}]** — "
        f"{'EXCLUDES zero (edge)' if (h1['ci_low'] == h1['ci_low'] and h1['ci_low'] > 0) else 'includes zero -> no standalone edge'}.",
        f"- Walk-forward: sector beats equal-weight in **{r['n_windows_sector_beats_eqw']}** windows.",
        "",
        "## H2 — diversifier (correlation / blend)",
        f"- corr(momentum, sector) = **{r['H2_corr_mom_sector']}** (low = diversifier).",
        f"- blend vs momentum-alone dSharpe {h2['delta']:+.2f}, CI [{h2['ci_low']}, {h2['ci_high']}]; "
        f"sector maxDD {b['sector_rotation']['max_drawdown']:.1%} vs momentum {b['momentum']['max_drawdown']:.1%}.",
        "",
        "## Cost sweep (sector Sharpe)",
        "  " + " · ".join(f"{k} {v}" for k, v in r["cost_sweep_sector_sharpe"].items()),
        "",
        f"## Outcome: **{r['outcome']}** → {r['action']}",
        "",
        "_Per ADR 0014 + the SEC-001 gate. 12-1 frozen (no optimization). Whatever the verdict, the "
        "evidence package is the deliverable — the Evidence Engineering moat._",
    ]
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    raise SystemExit(main())
