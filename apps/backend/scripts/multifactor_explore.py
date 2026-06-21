"""P12 §3 Deliverable B — EXPLORATORY value/quality validation (FMP fundamentals).

> **Exploratory, NOT a verdict.** Fundamentals are FMP (~5-yr, top-liquid names, not
> survivorship-free) — one regime. This produces *current evidence*; the decisive value/quality
> verdict is deferred to SF1 (research debt). Read-only research.

Two artifacts (the reason §3 exists):
1. **Factor-correlation matrix** — momentum × value × quality × multi-factor, averaged cross-section.
   Does value/quality *diversify* momentum (low/negative-and-helpful) or is it just its *opposite*?
2. **Composite vs momentum backtest** — the multi-factor book through the §1 harness vs momentum-only,
   mapped to the §3 success matrix.

    PYTHONPATH=apps/backend apps/backend/.venv/Scripts/python.exe apps/backend/scripts/multifactor_explore.py \
        --store apps/backend/data/factor_data_full.duckdb --start 2021-06-01 --end 2026-06-12 \
        --n 200 --report-dir docs/implementation/evidence/p12_s3_explore
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

import pandas as pd  # noqa: E402

from app.factor_data import evidence as ev  # noqa: E402
from app.factor_data.backtest import run_momentum_backtest  # noqa: E402
from app.factor_data.factors.composite import composite_scores, factor_zscores  # noqa: E402
from app.factor_data.factors.engine import FactorUnavailable  # noqa: E402
from app.factor_data.store import FactorDataStore  # noqa: E402

VALUE = ["earnings_yield", "fcf_yield", "sales_yield"]
QUALITY = ["roe", "gross_profitability", "roic", "debt_to_equity"]
ALL = ["momentum", *VALUE, *QUALITY]


def _grouped(z: pd.DataFrame) -> pd.DataFrame:
    """Collapse the 8 factor z-scores into momentum · value · quality · multifactor columns."""
    out = pd.DataFrame(index=z.index)
    out["momentum"] = z["momentum"]
    out["value"] = z[VALUE].mean(axis=1)
    out["quality"] = z[QUALITY].mean(axis=1)
    out["multifactor"] = z.mean(axis=1)  # equal-weight blend (matches the backtest composite)
    return out


def _curve_stats(curve: list[tuple[date, float]]) -> dict[str, float]:
    r = ev.daily_returns(curve)
    c = ev.cagr(curve)
    dd = ev.max_drawdown(curve)
    return {"cagr": c, "sharpe": ev.sharpe(r), "max_drawdown": dd, "calmar": ev.calmar(c, dd)}


def main() -> int:
    ap = argparse.ArgumentParser(description="P12 §3 exploratory multi-factor study")
    ap.add_argument("--store", default=None)
    ap.add_argument("--start", required=True)
    ap.add_argument("--end", required=True)
    ap.add_argument("--n", type=int, default=200)
    ap.add_argument("--bootstrap", type=int, default=2000)
    ap.add_argument("--seed", type=int, default=17)
    ap.add_argument("--report-dir", default=None)
    args = ap.parse_args()
    start, end = date.fromisoformat(args.start), date.fromisoformat(args.end)
    started = time.monotonic()
    exp_id = f"EXP-{datetime.now(UTC):%Y%m%d-%H%M%S}-mf"

    store = FactorDataStore(db_path=args.store, read_only=True)
    try:
        health = ev.dataset_health(store, start, end)

        # 1) factor-correlation matrix — monthly sample of the cross-section
        sample = [d.date() for d in pd.date_range(start, end, freq="MS")]
        corr_sum: pd.DataFrame | None = None
        n_corr = 0
        for d in sample:
            try:
                z = factor_zscores(store, d, factors=ALL, n=args.n)
            except FactorUnavailable:
                continue
            g = _grouped(z).dropna(how="any")
            if len(g) < 20:
                continue
            c = g.corr()
            corr_sum = c if corr_sum is None else corr_sum + c
            n_corr += 1
        corr: pd.DataFrame = (corr_sum / n_corr) if corr_sum is not None else pd.DataFrame()
        mom_value = float(corr.at["momentum", "value"]) if n_corr else float("nan")
        mom_quality = float(corr.at["momentum", "quality"]) if n_corr else float("nan")

        # 2) momentum-only vs multi-factor composite backtest
        mom_rep = run_momentum_backtest(store, start, end, n=args.n)
        mom = _curve_stats(mom_rep.equity_curve)

        def comp_score(s: FactorDataStore, d: date) -> pd.DataFrame:
            return composite_scores(s, d, factors=ALL, n=args.n, missing="impute")

        mf_rep = run_momentum_backtest(store, start, end, n=args.n, score_fn=comp_score)
        mf = _curve_stats(mf_rep.equity_curve)
        mf_ci = ev.block_bootstrap_ci(ev.daily_returns(mf_rep.equity_curve), ev.sharpe,
                                      n_resamples=args.bootstrap, seed=args.seed)
        d_sharpe = mf["sharpe"] - mom["sharpe"]

        # success-matrix mapping
        if d_sharpe > 0.10 and mf_ci.ci_low > mom["sharpe"]:
            state, action = "Validated", "candidate v2.0"
        elif abs(d_sharpe) <= 0.05:
            state, action = "Inconclusive/Rejected", "momentum stands alone (keep v1.1)"
        else:
            state, action = "Inconclusive", "further research / acquire SF1"

        result: dict[str, Any] = {
            "experiment_id": exp_id,
            "EXPLORATORY": "FMP ~5yr / one regime / not survivorship-free — current evidence, not a verdict",
            "window": [str(start), str(end)], "n": args.n,
            "dataset_health_ok": health["ok"],
            "correlation_matrix": corr.round(3).to_dict() if n_corr else {},
            "n_correlation_samples": n_corr,
            "momentum_value_corr": round(mom_value, 3), "momentum_quality_corr": round(mom_quality, 3),
            "momentum_book": mom, "multifactor_book": mf,
            "multifactor_sharpe_ci": vars(mf_ci),
            "delta_sharpe": round(d_sharpe, 3),
            "research_state": state, "action": action,
            "duration_s": round(time.monotonic() - started, 2),
        }
    finally:
        store.close()

    print(f"[{exp_id}] EXPLORATORY multi-factor  {start}..{end} n={args.n}")
    print(f"  corr(momentum,value)={result['momentum_value_corr']}  "
          f"corr(momentum,quality)={result['momentum_quality_corr']}  (n={result['n_correlation_samples']})")
    print(f"  momentum   : CAGR {mom['cagr']:+.2%} Sharpe {mom['sharpe']:.2f} maxDD {mom['max_drawdown']:.1%}")
    print(f"  multifactor: CAGR {mf['cagr']:+.2%} Sharpe {mf['sharpe']:.2f} maxDD {mf['max_drawdown']:.1%} "
          f"(dSharpe {result['delta_sharpe']:+.2f})")
    print(f"  -> {result['research_state']}: {result['action']}  ({result['duration_s']}s)")

    if args.report_dir:
        d = Path(args.report_dir)
        d.mkdir(parents=True, exist_ok=True)
        (d / "multifactor_explore.json").write_text(json.dumps(result, indent=2, default=str),
                                                    encoding="utf-8")
        (d / "multifactor_explore.md").write_text(_render(result), encoding="utf-8")
        print(f"  wrote {d / 'multifactor_explore.json'} + .md")
    return 0


def _render(r: dict[str, Any]) -> str:
    mom, mf = r["momentum_book"], r["multifactor_book"]
    lines = [
        f"# P12 §3 — EXPLORATORY multi-factor study ({r['experiment_id']})",
        "",
        f"> **{r['EXPLORATORY']}**",
        "",
        f"Window {r['window'][0]}..{r['window'][1]} · n={r['n']} · {r['duration_s']}s",
        "",
        "## Factor-correlation matrix (avg cross-section, momentum × value × quality × multifactor)",
        "",
        f"- corr(momentum, value) = **{r['momentum_value_corr']}**",
        f"- corr(momentum, quality) = **{r['momentum_quality_corr']}**",
        f"- (averaged over {r['n_correlation_samples']} monthly cross-sections)",
        "",
        "_A diversifier needs low/near-zero correlation that *helps*; a strongly **negative** "
        "correlation means value/quality is momentum's opposite, not a complement._",
        "",
        "## Composite vs momentum (the multi-factor book)",
        "",
        "| Book | CAGR | Sharpe | maxDD | Calmar |",
        "|---|---|---|---|---|",
        f"| Momentum (v1.1 base) | {mom['cagr']:+.2%} | {mom['sharpe']:.2f} | {mom['max_drawdown']:.1%} | {mom['calmar']:.2f} |",
        f"| Multi-factor (mom+value+quality) | {mf['cagr']:+.2%} | {mf['sharpe']:.2f} | {mf['max_drawdown']:.1%} | {mf['calmar']:.2f} |",
        "",
        f"ΔSharpe = **{r['delta_sharpe']:+.2f}**; multi-factor Sharpe 95% CI "
        f"[{r['multifactor_sharpe_ci']['ci_low']:.2f}, {r['multifactor_sharpe_ci']['ci_high']:.2f}].",
        "",
        f"## Research state: **{r['research_state']}** → {r['action']}",
        "",
        "_Exploratory only. The decisive verdict is **Deferred → SF1** (deep, broad, survivorship-free "
        "fundamentals) — the research-debt blocker. The platform win (composite engine + factor-agnostic "
        "backtest) holds regardless of this outcome._",
    ]
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    raise SystemExit(main())
