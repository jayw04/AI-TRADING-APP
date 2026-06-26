"""P12 §2 — parameter-sensitivity grid for the harden study (review fold).

Two independent hypotheses, swept as SENSITIVITY grids (not optimization) + a combined run,
each scored against the §1 baseline by an explicit decision matrix and the full drawdown profile:

  Hypothesis A — Vol-scaling  : lower drawdown at minimal Sharpe loss   (vol-target grid)
  Hypothesis B — Sector caps  : lower concentration / drawdown, minimal CAGR loss (cap grid)
  Combined     — Vol + caps   : interaction effect

Headline-only per grid point (full period, no walk-forward) so the breadth is feasible; the
walk-forward DEPTH on the central configs comes from the separate edge_evidence.py runs. Reuses
``run_momentum_backtest`` + ``app.factor_data.evidence``. Read-only research. ASCII stdout.

    PYTHONPATH=apps/backend apps/backend/.venv/Scripts/python.exe apps/backend/scripts/harden_grid.py \
        --store apps/backend/data/factor_data_full.duckdb --start 1997-12-31 --end 2026-06-12 \
        --vol-grid 0.10,0.12,0.15,0.18,0.20 --cap-grid 0.20,0.25,0.30,0.35,0.40 \
        --combined-vol 0.15 --combined-cap 0.30 --report-dir docs/implementation/evidence/p12_s2_grid
"""

from __future__ import annotations

import argparse
import json
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


def _stats(curve: list[tuple[date, float]]) -> dict[str, float]:
    r = ev.daily_returns(curve)
    c = ev.cagr(curve)
    prof = ev.drawdown_profile(curve)
    return {"cagr": c, "sharpe": ev.sharpe(r), "calmar": ev.calmar(c, prof["max_drawdown"]),
            "ann_vol": ev.ann_volatility(r), **prof}


def _decide(base: dict[str, float], cfg: dict[str, float], *, dd_gate: float, sharpe_tol: float
            ) -> dict[str, Any]:
    """Decision matrix vs baseline. Primary gate: DD improvement + Sharpe preservation.
    Secondary (recorded, not gating): Calmar, recovery time, worst-12m."""
    b_dd, c_dd = abs(base["max_drawdown"]), abs(cfg["max_drawdown"])
    dd_rel = (b_dd - c_dd) / b_dd if b_dd else 0.0
    d_sharpe = cfg["sharpe"] - base["sharpe"]
    if dd_rel <= 0.0 and d_sharpe <= 0.0:
        decision = "Reject"
    elif dd_rel >= dd_gate and d_sharpe >= -sharpe_tol:
        decision = "Enable"
    elif dd_rel >= dd_gate and d_sharpe < -sharpe_tol:
        decision = "Keep Off"          # DD improved but Sharpe cost too high
    else:
        decision = "More Research"
    return {"decision": decision, "dd_rel_reduction": dd_rel, "d_sharpe": d_sharpe,
            "d_calmar": cfg["calmar"] - base["calmar"]}


def main() -> int:
    ap = argparse.ArgumentParser(description="P12 §2 sensitivity grid")
    ap.add_argument("--store", default=None)
    ap.add_argument("--start", required=True)
    ap.add_argument("--end", required=True)
    ap.add_argument("--n", type=int, default=200)
    ap.add_argument("--top-quantile", type=float, default=0.20)
    ap.add_argument("--base-cost", type=float, default=10.0)
    ap.add_argument("--vol-span", type=int, default=20)
    ap.add_argument("--vol-grid", default="0.10,0.12,0.15,0.18,0.20")
    ap.add_argument("--cap-grid", default="0.20,0.25,0.30,0.35,0.40")
    ap.add_argument("--combined-vol", type=float, default=0.15)
    ap.add_argument("--combined-cap", type=float, default=0.30)
    ap.add_argument("--dd-gate", type=float, default=0.20)      # >=20% rel DD reduction
    ap.add_argument("--sharpe-tol", type=float, default=0.05)   # Sharpe may fall at most 0.05
    ap.add_argument("--report-dir", default=None)
    args = ap.parse_args()

    start, end = date.fromisoformat(args.start), date.fromisoformat(args.end)
    vol_grid = [float(x) for x in args.vol_grid.split(",")] if args.vol_grid else []
    cap_grid = [float(x) for x in args.cap_grid.split(",")] if args.cap_grid else []
    started = time.monotonic()
    exp_id = f"EXP-{datetime.now(UTC):%Y%m%d-%H%M%S}-grid"

    def bt(**kw: Any) -> Any:
        return run_momentum_backtest(store, start, end, n=args.n,
                                     top_quantile=args.top_quantile,
                                     turnover_cost_bps=args.base_cost, **kw)

    store = FactorDataStore(db_path=args.store, read_only=True)
    rows: list[dict[str, Any]] = []
    try:
        health = ev.dataset_health(store, start, end)
        base_rep = bt()
        base = _stats(base_rep.equity_curve)
        rows.append({"config": "1.0 baseline (Momentum)", "hypothesis": "-", **base,
                     "decision": "baseline", "dd_rel_reduction": 0.0, "d_sharpe": 0.0})

        for vt in vol_grid:  # Hypothesis A — vol-scaling
            s = _stats(bt(vol_target_annual=vt, vol_ewma_span=args.vol_span).vol_scaled_curve)
            rows.append({"config": f"A: vol {vt:.0%}", "hypothesis": "A vol-scaling", **s,
                         **_decide(base, s, dd_gate=args.dd_gate, sharpe_tol=args.sharpe_tol)})

        for cp in cap_grid:  # Hypothesis B — sector caps
            s = _stats(bt(max_sector_pct=cp).equity_curve)
            rows.append({"config": f"B: cap {cp:.0%}", "hypothesis": "B sector-caps", **s,
                         **_decide(base, s, dd_gate=args.dd_gate, sharpe_tol=args.sharpe_tol)})

        # Combined (interaction)
        comb = _stats(bt(vol_target_annual=args.combined_vol, vol_ewma_span=args.vol_span,
                         max_sector_pct=args.combined_cap).vol_scaled_curve)
        rows.append({"config": f"A+B: vol {args.combined_vol:.0%} + cap {args.combined_cap:.0%}",
                     "hypothesis": "combined", **comb,
                     **_decide(base, comb, dd_gate=args.dd_gate, sharpe_tol=args.sharpe_tol)})
    finally:
        store.close()

    # best-by-objective (different objectives, per review)
    scored = rows[1:]
    objectives = {
        "best_sharpe": max(scored, key=lambda r: r["sharpe"])["config"],
        "lowest_maxdd": max(scored, key=lambda r: r["max_drawdown"])["config"],  # least negative
        "best_calmar": max(scored, key=lambda r: r["calmar"])["config"],
        "lowest_worst_12m": max(scored, key=lambda r: r["worst_rolling_12m"])["config"],
    }
    result = {
        "experiment_id": exp_id, "config": {"start": str(start), "end": str(end), "n": args.n,
        "dd_gate": args.dd_gate, "sharpe_tol": args.sharpe_tol},
        "dataset_health_ok": health["ok"], "baseline": base, "grid": rows,
        "objectives": objectives, "duration_s": round(time.monotonic() - started, 2),
    }

    print(f"[{exp_id}] grid {start}..{end} n={args.n}  ({result['duration_s']}s)")
    print(f"  {'config':34s} {'CAGR':>8s} {'Shrp':>5s} {'maxDD':>7s} {'Calmar':>6s}  decision")
    for r in rows:
        print(f"  {r['config']:34s} {r['cagr']:>+7.1%} {r['sharpe']:>5.2f} "
              f"{r['max_drawdown']:>7.1%} {r['calmar']:>6.2f}  {r['decision']}")
    print(f"  objectives: {objectives}")

    if args.report_dir:
        d = Path(args.report_dir)
        d.mkdir(parents=True, exist_ok=True)
        (d / "harden_grid.json").write_text(json.dumps(result, indent=2, default=str), encoding="utf-8")
        (d / "harden_grid.md").write_text(_render(result), encoding="utf-8")
        print(f"  wrote {d / 'harden_grid.json'} + harden_grid.md")
    return 0


def _render(r: dict[str, Any]) -> str:
    lines = [
        f"# P12 §2 — Harden sensitivity grid ({r['experiment_id']})",
        "",
        f"_Window {r['config']['start']}..{r['config']['end']} · n={r['config']['n']} · "
        f"gate: DD reduced >={r['config']['dd_gate']:.0%} AND Sharpe down <={r['config']['sharpe_tol']:.2f} · "
        f"{r['duration_s']}s_",
        "",
        "Decision matrix: **Enable** (DD reduced >=gate AND Sharpe preserved) · **Keep Off** "
        "(DD reduced but Sharpe cost) · **Reject** (no improvement) · **More Research** (mixed).",
        "",
        "| Config | Hypothesis | CAGR | Sharpe | maxDD | avgDD | t.underwater | worst12m | Calmar | DD red. | dSharpe | Decision |",
        "|---|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for x in r["grid"]:
        lines.append(
            f"| {x['config']} | {x['hypothesis']} | {x['cagr']:+.1%} | {x['sharpe']:.2f} | "
            f"{x['max_drawdown']:.1%} | {x['avg_drawdown']:.1%} | {x['time_underwater']:.0%} | "
            f"{x['worst_rolling_12m']:.1%} | {x['calmar']:.2f} | "
            f"{x.get('dd_rel_reduction', 0.0):+.0%} | {x.get('d_sharpe', 0.0):+.2f} | {x['decision']} |"
        )
    o = r["objectives"]
    lines += [
        "",
        "## Best by objective (different objectives, not one 'best')",
        f"- Best Sharpe: **{o['best_sharpe']}**",
        f"- Lowest max-drawdown: **{o['lowest_maxdd']}**",
        f"- Best Calmar (risk-adjusted): **{o['best_calmar']}**",
        f"- Lowest worst-12m: **{o['lowest_worst_12m']}**",
        "",
        "## Strategy evolution",
        "",
        "| Version | Change | Status |",
        "|---|---|---|",
        "| 1.0 | Momentum (6-1, weekly top-quintile) | Validated (§1) |",
        "| 1.1 | + Vol-scaling | _decided from this grid + §2 walk-forward_ |",
        "| 1.1 | + Sector caps | _decided from this grid_ |",
        "| 1.2 | Combined (vol + caps) | _candidate if interaction clears_ |",
    ]
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    raise SystemExit(main())
