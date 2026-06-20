"""P12 §1 — Edge evidence harness (script -> JSON -> Markdown).

Runs the production momentum book on the survivorship-free store and emits a reproducible
edge-evidence package: full metrics + statistical confidence (bootstrap CIs + p-value) vs three
benchmarks (equal-weight · cash · SPY where available), a cost-sensitivity sweep, a walk-forward
across regimes with a stability label, an outlier report, and a dataset-health gate — all stamped
with an experiment id + reproducibility metadata.

> Read-only research. No order path, no strategy change. ASCII-only stdout (cp1252-safe).

From the repo root (so the default store path resolves):

    PYTHONPATH=apps/backend apps/backend/.venv/Scripts/python.exe apps/backend/scripts/edge_evidence.py \
        --store apps/backend/data/factor_data_full.duckdb --start 1997-12-31 --end 2026-06-12 \
        --n 200 --costs 5,10,20,50 --walk-forward 200x7 --bootstrap 2000 --seed 17 \
        --report-dir docs/implementation/evidence/p12_s1

Use a small window + --bootstrap 300 + --walk-forward 80x5 for a fast smoke; the full headline run
(1997-2026, n=200, 200x7) is a long job.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
import socket
import subprocess
import sys
import time
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.factor_data import evidence as ev  # noqa: E402
from app.factor_data.backtest import run_momentum_backtest  # noqa: E402
from app.factor_data.store import FactorDataStore  # noqa: E402

# Seven contiguous regime windows (the 5 from the vol-scaling walk-forward + 2 recent).
REGIME_WINDOWS: list[tuple[str, date, date]] = [
    ("GFC + 2009 reversal", date(2007, 7, 1), date(2010, 6, 30)),
    ("2010-2013 (2011 shock)", date(2010, 7, 1), date(2013, 6, 30)),
    ("2013-2016 (incl 2015)", date(2013, 7, 1), date(2016, 6, 30)),
    ("2016-2019 (calm)", date(2016, 7, 1), date(2019, 6, 30)),
    ("2019-2022 (COVID)", date(2019, 7, 1), date(2022, 6, 30)),
    ("2022-2024 (rate shock)", date(2022, 7, 1), date(2024, 6, 30)),
    ("2024-2026 (AI momentum)", date(2024, 7, 1), date(2026, 6, 12)),
]


def _git_sha() -> str:
    try:
        return subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True, check=True
        ).stdout.strip()
    except Exception:
        return "unknown"


def _period_returns(curve: list[tuple[date, float]], key: Any) -> dict[Any, float]:
    buckets: dict[Any, list[tuple[date, float]]] = {}
    for d, v in curve:
        buckets.setdefault(key(d), []).append((d, v))
    out: dict[Any, float] = {}
    for k, pts in buckets.items():
        pts.sort()
        if pts[0][1] > 0:
            out[k] = pts[-1][1] / pts[0][1] - 1.0
    return out


def _curve_stats(curve: list[tuple[date, float]]) -> dict[str, float]:
    r = ev.daily_returns(curve)
    c = ev.cagr(curve)
    dd = ev.max_drawdown(curve)
    return {
        "total_return": ev.total_return(curve),
        "cagr": c,
        "ann_volatility": ev.ann_volatility(r),
        "sharpe": ev.sharpe(r),
        "sortino": ev.sortino(r),
        "max_drawdown": dd,
        "calmar": ev.calmar(c, dd),
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="P12 §1 edge-evidence harness")
    ap.add_argument("--store", default=None, help="path to the DuckDB factor store")
    ap.add_argument("--start", required=True, help="ISO date")
    ap.add_argument("--end", required=True, help="ISO date")
    ap.add_argument("--n", type=int, default=200, help="universe size (top-N by dollar volume)")
    ap.add_argument("--universe-label", default="live200")
    ap.add_argument("--top-quantile", type=float, default=0.20)
    ap.add_argument("--base-cost", type=float, default=10.0, help="headline turnover cost bps")
    ap.add_argument("--costs", default="5,10,20,50", help="cost-sensitivity sweep, bps")
    ap.add_argument("--walk-forward", default="200x7", help="NxW: universe size x window count")
    ap.add_argument("--bootstrap", type=int, default=2000)
    ap.add_argument("--seed", type=int, default=17)
    ap.add_argument("--block", type=int, default=21, help="bootstrap block length (trading days)")
    ap.add_argument("--experiment-id", default=None)
    ap.add_argument("--report-dir", default=None)
    args = ap.parse_args()

    start, end = date.fromisoformat(args.start), date.fromisoformat(args.end)
    costs = [float(x) for x in args.costs.split(",")]
    wf_n, wf_w = (int(x) for x in args.walk_forward.lower().split("x"))
    started = time.monotonic()
    generated_at = datetime.now(UTC).isoformat()
    exp_id = args.experiment_id or f"EXP-{datetime.now(UTC):%Y%m%d-%H%M%S}"

    store = FactorDataStore(db_path=args.store, read_only=True)
    try:
        # --- dataset-health gate (before any backtest) ---
        health = ev.dataset_health(store, start, end)
        if not health["ok"]:
            print(f"[dataset-health] FLAGS: {health['flags']}", file=sys.stderr)

        # --- headline book run (base cost) ---
        rep = run_momentum_backtest(
            store, start, end, n=args.n, top_quantile=args.top_quantile,
            turnover_cost_bps=args.base_cost,
        )
        book_curve = rep.equity_curve
        ew_curve = rep.baseline_curve
        book = _curve_stats(book_curve)
        book_rets = ev.daily_returns(book_curve)

        # --- statistical confidence (bootstrap CIs + p-value) ---
        ci_sharpe = ev.block_bootstrap_ci(
            book_rets, ev.sharpe, n_resamples=args.bootstrap, seed=args.seed, block=args.block
        )
        ci_cagr = ev.block_bootstrap_ci(
            book_rets, lambda r: ev._mean(r) * ev.TRADING_DAYS,
            n_resamples=args.bootstrap, seed=args.seed, block=args.block,
        )

        # --- benchmarks: equal-weight (full history) · cash · SPY (best-effort) ---
        benchmarks = {
            "equal_weight": ev.benchmark_characteristics(ew_curve),
            "cash": {"total_return": 0.0, "cagr": 0.0, "ann_volatility": 0.0,
                     "max_drawdown": 0.0, "sharpe": 0.0},
        }
        spy_note = "equal-weight is the primary benchmark (full history); SPY best-effort"
        try:
            from app.research.engine.benchmark import benchmark_metrics, load_spy_curve
            spy = load_spy_curve()
            if spy and spy[0][0] <= end and spy[-1][0] >= start:
                benchmarks["spy"] = ev.benchmark_characteristics(spy)
                benchmarks["spy_relative"] = benchmark_metrics(book_curve, spy)
            else:
                spy_note = "SPY series unavailable/short over window -> research debt (full-history SPY)"
        except Exception as e:  # noqa: BLE001
            spy_note = f"SPY benchmark skipped: {e!r}"

        # --- cost-sensitivity sweep ---
        cost_sweep: list[dict[str, Any]] = []
        for c in costs:
            r = run_momentum_backtest(
                store, start, end, n=args.n, top_quantile=args.top_quantile, turnover_cost_bps=c
            )
            m = r.metrics
            cost_sweep.append({"bps": c, "cagr": m.cagr, "sharpe": m.sharpe,
                               "max_drawdown": m.max_drawdown, "total_return": m.total_return})

        # --- walk-forward across regimes ---
        wf: list[dict[str, Any]] = []
        for label, ws, we in REGIME_WINDOWS[:wf_w]:
            if we < start or ws > end:
                continue
            r = run_momentum_backtest(store, max(ws, start), min(we, end), n=wf_n,
                                      top_quantile=args.top_quantile, turnover_cost_bps=args.base_cost)
            m = r.metrics
            wf.append({"window": label, "rebalances": len(r.rebalances), "cagr": m.cagr,
                       "sharpe": m.sharpe, "max_drawdown": m.max_drawdown})
        stability = ev.stability_label([float(w["sharpe"]) for w in wf])

        # --- outliers ---
        held = sorted(rep.holdings, key=lambda h: h.realized_return)
        months = _period_returns(book_curve, lambda d: (d.year, d.month))
        years = _period_returns(book_curve, lambda d: d.year)
        outliers = {
            "best_rebalances": [{"date": str(h.rebalance_date), "ret": h.realized_return}
                                for h in held[-5:][::-1]],
            "worst_rebalances": [{"date": str(h.rebalance_date), "ret": h.realized_return}
                                 for h in held[:5]],
            "worst_month": (lambda k: {"period": f"{k[0]}-{k[1]:02d}", "ret": months[k]})(
                min(months, key=lambda k: months[k])) if months else None,
            "worst_year": (lambda k: {"period": str(k), "ret": years[k]})(
                min(years, key=lambda k: years[k])) if years else None,
            "largest_drawdown": book["max_drawdown"],
        }

        dataset_sha = hashlib.sha256(
            f"{health['n_sep_rows']}|{health['store_bounds']}|{health['n_tickers']}".encode()
        ).hexdigest()[:16]

        result: dict[str, Any] = {
            "experiment_id": exp_id,
            "strategy_version": "1.0 - Momentum (6-1, weekly top-quintile, equal-weight)",
            "evidence_version": {
                "dataset_version": f"{store.path}@{dataset_sha}",
                "code_version": _git_sha(),
                "factor_version": "momentum-6-1",
                "walk_forward_version": args.walk_forward,
                "report_version": "v0.1",
            },
            "repro": {
                "python": platform.python_version(),
                "duckdb": __import__("duckdb").__version__,
                "git_sha": _git_sha(),
                "dataset_sha": dataset_sha,
                "seed": args.seed,
                "host": socket.gethostname(),
                "generated_at": generated_at,
                "duration_s": None,  # set below
            },
            "config": {"start": str(start), "end": str(end), "n": args.n,
                       "universe": args.universe_label, "top_quantile": args.top_quantile,
                       "base_cost_bps": args.base_cost, "bootstrap": args.bootstrap,
                       "block": args.block},
            "dataset_health": health,
            "book": book,
            "confidence": {
                "sharpe": vars(ci_sharpe),
                "ann_return": vars(ci_cagr),
            },
            "benchmarks": benchmarks,
            "spy_note": spy_note,
            "cost_sweep": cost_sweep,
            "walk_forward": {"windows": wf, "stability": stability},
            "outliers": outliers,
            "research_debt": [
                {"item": "Full-history SPY series (SPY not in SEP store)", "status": "Outstanding"},
                {"item": "Capacity / market-impact study", "status": "Outstanding"},
                {"item": "Dividend-adjustment validation", "status": "Outstanding"},
                {"item": "Liquidity model", "status": "Outstanding"},
            ],
        }
        result["repro"]["duration_s"] = round(time.monotonic() - started, 2)
    finally:
        store.close()

    # --- emit: stdout summary + JSON + Markdown ---
    print(f"[{exp_id}] {args.universe_label} n={args.n}  {start}..{end}")
    print(f"  book : CAGR {book['cagr']:+.2%}  Sharpe {book['sharpe']:.2f} "
          f"(95% CI {ci_sharpe.ci_low:.2f}..{ci_sharpe.ci_high:.2f}, p={ci_sharpe.p_value:.3f})  "
          f"maxDD {book['max_drawdown']:.1%}")
    print(f"  vs EW: CAGR {benchmarks['equal_weight']['cagr']:+.2%}  "
          f"Sharpe {benchmarks['equal_weight']['sharpe']:.2f}")
    print(f"  walk-forward stability: {stability}  ({len(wf)} windows)")
    print(f"  dataset-health ok={health['ok']}  duration {result['repro']['duration_s']}s")

    if args.report_dir:
        d = Path(args.report_dir)
        d.mkdir(parents=True, exist_ok=True)
        (d / "edge_evidence.json").write_text(json.dumps(result, indent=2, default=str),
                                              encoding="utf-8")
        (d / "edge_evidence.md").write_text(_render_md(result), encoding="utf-8")
        print(f"  wrote {d / 'edge_evidence.json'} + edge_evidence.md")
    return 0


def _render_md(r: dict[str, Any]) -> str:
    b, ci = r["book"], r["confidence"]
    ew = r["benchmarks"]["equal_weight"]
    lines = [
        f"# Edge Evidence — {r['strategy_version']} ({r['experiment_id']})",
        "",
        f"_Generated {r['repro']['generated_at']} · git {r['repro']['git_sha']} · "
        f"seed {r['repro']['seed']} · dataset {r['repro']['dataset_sha']} · "
        f"{r['repro']['duration_s']}s on {r['repro']['host']}_",
        "",
        "## Objective",
        "Does the live momentum book carry a real, OOS, survivorship-free edge vs equal-weight / "
        "cash / SPY, robust to cost?",
        "",
        "## Dataset",
        f"- Store `{r['evidence_version']['dataset_version']}`; window {r['config']['start']}..{r['config']['end']}; "
        f"universe {r['config']['universe']} (n={r['config']['n']}).",
        f"- Health: {r['dataset_health']['n_sep_rows']:,} SEP rows, "
        f"{r['dataset_health']['n_tickers']:,} tickers, covers_window={r['dataset_health']['covers_window']}, "
        f"ok={r['dataset_health']['ok']}.",
        "",
        "## Methodology",
        "Weekly long-only top-quintile 6-1 momentum, equal-weight; equal-weight-universe baseline "
        "(ADR 0014); block bootstrap (95% CI + recentered-null p-value); walk-forward across regimes; "
        "cost-sensitivity sweep.",
        "",
        "## Results",
        "",
        "| Metric | Book | Equal-weight |",
        "|---|---|---|",
        f"| CAGR | {b['cagr']:+.2%} | {ew['cagr']:+.2%} |",
        f"| Sharpe | {b['sharpe']:.2f} | {ew['sharpe']:.2f} |",
        f"| Sortino | {b['sortino']:.2f} | — |",
        f"| Max drawdown | {b['max_drawdown']:.1%} | {ew['max_drawdown']:.1%} |",
        f"| Calmar | {b['calmar']:.2f} | — |",
        f"| Ann. vol | {b['ann_volatility']:.1%} | {ew['ann_volatility']:.1%} |",
        "",
        f"**Statistical confidence** — Sharpe {ci['sharpe']['point']:.2f} "
        f"(95% CI {ci['sharpe']['ci_low']:.2f}..{ci['sharpe']['ci_high']:.2f}, "
        f"p={ci['sharpe']['p_value']:.3f}); ann. return p={ci['ann_return']['p_value']:.3f}. "
        f"_{r['spy_note']}_",
        "",
        "### Cost sensitivity",
        "",
        "| bps | CAGR | Sharpe | maxDD |",
        "|---|---|---|---|",
        *[f"| {c['bps']:.0f} | {c['cagr']:+.2%} | {c['sharpe']:.2f} | {c['max_drawdown']:.1%} |"
          for c in r["cost_sweep"]],
        "",
        f"### Walk-forward (stability: **{r['walk_forward']['stability']}**)",
        "",
        "| Window | Rebalances | CAGR | Sharpe | maxDD |",
        "|---|---|---|---|---|",
        *[f"| {w['window']} | {w['rebalances']} | {w['cagr']:+.2%} | {w['sharpe']:.2f} | {w['max_drawdown']:.1%} |"
          for w in r["walk_forward"]["windows"]],
        "",
        "### Outliers",
        f"- Worst month: {r['outliers']['worst_month']}",
        f"- Worst year: {r['outliers']['worst_year']}",
        f"- Largest drawdown: {r['outliers']['largest_drawdown']:.1%}",
        "",
        "## Limitations",
        "- Live top-200 universe is survivorship-biased (today's names) — read book-vs-equal-weight "
        "(same-universe) as the cleaner alpha signal; broad survivorship-free run is the appendix.",
        "- " + r["spy_note"],
        "- Open research debt: " + "; ".join(x["item"] for x in r["research_debt"]) + ".",
        "",
        "## Decision",
        "Baseline established — **no enable/disable this session** (§1 measures; §2 decides). "
        "Confidence: _(set on read)_.",
        "",
        "## Recommendation",
        "Carry this baseline into §2 (vol-scaling / sector-caps lift) using the same harness.",
    ]
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    raise SystemExit(main())
