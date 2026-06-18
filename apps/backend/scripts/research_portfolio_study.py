"""CLI: the first portfolio-construction comparison study (P10 Phase 3A §4.8).

Runs the frozen momentum signal under each construction method × {no overlay,
vol-target 15%} through the Research Engine, gates each with the pre-registered
``portfolio_backtest`` scorecard (§4.7a), compares them across risk-adjusted /
downside / turnover / capacity metrics **and per regime**, and writes a single
decision-oriented comparison report — registered as a first-class registry artifact
(§4.9) — ending with the result-interpretation block (§4.10).

    cd apps/backend
    .venv/Scripts/python.exe scripts/research_portfolio_study.py \
        --store data/factor_data_full.duckdb \
        --start 2007-01-01 --end 2026-06-12 --n 200 --top-quantile 0.20

After it runs, all six registries hold real rows and the experiments carry the four
FKs + component scores — the §3.0 registries are no longer inert.

⚠ A GO verdict here means research-VALIDATED, NOT deployable. It transitions only an
experiment's research_state → VALIDATED; deployment stays an owner decision via the
promotion-workflow runbook (ADR 0019). This study never routes an order.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path
from typing import TYPE_CHECKING

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

if TYPE_CHECKING:
    from app.research.promotion import GateResult

# v1 construction methods (§0 Q4). risk_parity_diagonal == inverse_vol in v1 (Gotcha 5)
# — kept as a labeled future seam, so the study is *materially* a two-method comparison.
_METHODS = ("equal_weight", "inverse_vol", "risk_parity_diagonal")
_STUDY_VERSION = "momentum_v0.3"          # the frozen alpha signal version
_COMPARE_METRICS = ["sharpe", "sortino", "calmar", "max_drawdown", "turnover_annual"]
_REGIMES = ("bull", "bear", "high_vol", "low_vol")


def _dataset_from_store(store_path: str | None):
    from app.factor_data.store import FactorDataStore
    from app.research.registry import DatasetRecord
    store = FactorDataStore(db_path=store_path, read_only=True) if store_path \
        else FactorDataStore(read_only=True)
    try:
        floor, latest = store.price_date_bounds()
        row = store.con.execute("SELECT COUNT(DISTINCT ticker) FROM sep").fetchone()
        ntk = int(row[0]) if row else 0
    finally:
        store.close()
    return DatasetRecord(
        dataset_id=f"sep_{latest}", provider="sharadar", version=str(latest),
        coverage=f"{floor}..{latest}", row_count=int(ntk),
    )


def _record_benchmarks(rstore) -> dict[str, str]:
    """Versioned benchmark rows by class (§4.8 step 2; SPY deferred — §0 Q5). The
    registry has no version column, so the version rides in the definition/description
    text and (via the experiment's benchmark spec) in the content fingerprint, so a
    methodology change can't silently alter historical comparisons."""
    from app.research.registry import BenchmarkRecord
    classes = {
        "factor": BenchmarkRecord(definition="equal_weight_universe", source="sep",
                                  rebalance="weekly",
                                  description="class=Factor version=v1 (in-backtest baseline)"),
        "version": BenchmarkRecord(definition=_STUDY_VERSION, source="research",
                                   rebalance="weekly",
                                   description="class=Version (frozen momentum signal)"),
        "portfolio": BenchmarkRecord(definition="previous_best_experiment", source="research",
                                     rebalance="weekly",
                                     description="class=Portfolio (prior best book)"),
    }
    return {k: rstore.record_benchmark(v) for k, v in classes.items()}


def _run_one(rstore, dataset, *, store_path, start, end, n, top_quantile, split,
             method, vol_target, benchmark_ids, report_root):
    """Record the FK rows + run one (method × overlay) experiment, content-addressed by
    the referenced records' *content* (§0 Q2 — the random FK ids are provenance only)."""
    from app.research.engine import ExperimentConfig, portfolio_construction_runner, run_experiment
    from app.research.registry import (
        CostModelRecord,
        PortfolioModelRecord,
        RiskModelRecord,
        StrategyRecord,
    )

    strat_id = rstore.record_strategy(StrategyRecord(
        strategy_id="strat_momentum_v0_3", name="Momentum 12-1 (frozen)",
        category="factor", current_version=_STUDY_VERSION))

    overlay = "voltgt15" if vol_target else "nooverlay"
    pf_id = rstore.record_portfolio_model(PortfolioModelRecord(
        strategy_id=strat_id, construction_method=method, weighting=method,
        rebalance="weekly", risk_model=("vol_target_15" if vol_target else "none"),
        params={"top_quantile": top_quantile, "vol_lookback_days": 63}))
    cost_id = rstore.record_cost_model(CostModelRecord(
        commission=0.0, slippage=10.0, spread=0.0, market_impact="linear_turnover",
        description="10bps one-way turnover cost"))
    rm_id = rstore.record_risk_model(
        RiskModelRecord(kind="vol_target", vol_target_annual=0.15, vol_ewma_span=20,
                        description="15% annual vol target")
        if vol_target else RiskModelRecord(kind="none", description="no risk overlay"))

    # Operational keys the runner reads + the *content* spec folded in for the
    # fingerprint (so identity is content-based, not random-id-based — §0 Q2 / Gotcha 4).
    params = {
        "store_path": store_path, "start": start.isoformat(), "end": end.isoformat(),
        "n": n, "top_quantile": top_quantile, "weighting": method,
        "vol_lookback_days": 63, "turnover_cost_bps": 10.0,
        "vol_target_annual": (0.15 if vol_target else None),
        "is_oos_split": split.isoformat() if split else None,
        "portfolio_spec": {"method": method, "rebalance": "weekly", "overlay": overlay},
        "cost_spec": {"slippage_bps": 10.0},
        "risk_spec": {"kind": "vol_target" if vol_target else "none",
                      "vol_target_annual": 0.15 if vol_target else None},
        "benchmark_spec": {"class": "Factor", "definition": "equal_weight_universe",
                           "version": "v1"},
    }
    config = ExperimentConfig(
        kind="portfolio_construction", name=f"momentum {method} / {overlay}",
        params=params, strategy_id=strat_id,
        is_window=f"{start}..{split}" if split else None,
        oos_window=f"{split}..{end}" if split else None,
        cost_model="10bps_one_way", survivorship_mode="sep_universe", pit_mode="n/a",
        portfolio_id=pf_id, benchmark_id=benchmark_ids["factor"],
        cost_model_id=cost_id, risk_model_id=rm_id,
    )
    # Per-run report dir so each experiment's bundle is isolated (§4.9c) — the bundle
    # filenames are identical across methods, so a shared dir would overwrite.
    run_dir = Path(report_root) / f"{method}__{overlay}"
    eid = run_experiment(config, portfolio_construction_runner, store=rstore,
                         dataset=dataset, report_dir=str(run_dir))
    return eid, f"{method}/{overlay}"


def _scorecard_block(rstore, gate_results: dict[str, GateResult]) -> list[str]:
    lines = ["## Scorecards (portfolio_backtest gate — frozen §4.7a)\n",
             "| experiment | verdict | confidence | components |",
             "|---|---|---|---|"]
    for label, res in gate_results.items():
        comps = " · ".join(f"{cs.component} {cs.passed_weight:g}/{cs.total_weight:g}"
                           for cs in res.component_scores)
        lines.append(f"| {label} | {res.verdict} | {res.confidence_score} | {comps} |")
    return lines + [""]


def _regime_table(rstore, ids: list[str], labels: dict[str, str]) -> list[str]:
    lines = ["## Per-regime book Sharpe (§4.6 reporting slice)\n",
             "| regime | " + " | ".join(labels[e] for e in ids) + " |",
             "|---" * (len(ids) + 1) + "|"]
    for regime in _REGIMES:
        cells = []
        for e in ids:
            exp = rstore.get_experiment(e)
            r = (exp.metrics_detail.get("regimes", {}) if exp else {}).get(regime, {})
            cells.append(f"{r.get('sharpe', float('nan')):.3g}" if r else "n/a")
        lines.append(f"| {regime} | " + " | ".join(cells) + " |")
    return lines + [""]


def _interpretation(rstore, ids: list[str], labels: dict[str, str],
                    gate_results: dict[str, GateResult], store_label: str) -> list[str]:
    """The fixed §4.10 decision-oriented block. 'Recommended action' may recommend
    further research only — NEVER deployment (owner-gated, ADR 0019)."""
    def conf(e: str) -> int:
        exp = rstore.get_experiment(e)
        return exp.confidence_score or 0 if exp else 0

    def sharpe(e: str) -> float:
        exp = rstore.get_experiment(e)
        return float(exp.metrics_summary.get("sharpe", 0.0)) if exp else 0.0

    best = max(ids, key=lambda e: (conf(e), sharpe(e)))
    bexp = rstore.get_experiment(best)
    bs = bexp.metrics_summary if bexp else {}
    regimes = bexp.metrics_detail.get("regimes", {}) if bexp else {}
    worst_regime = min(regimes, key=lambda r: regimes[r].get("sharpe", 0.0)) if regimes else "n/a"
    return [
        f"## Result interpretation — momentum construction study, {date.today()}, "
        f"{store_label}\n",
        f"- **Best method:**            {labels[best]} "
        f"(confidence {conf(best)}, Sharpe {bs.get('sharpe', 0):.2f})",
        "- **Why:**                    highest gate confidence; see the component "
        "breakdown above for which dimensions decided it",
        f"- **Risk tradeoff:**          maxDD {bs.get('max_drawdown', 0):.2%} vs benchmark "
        f"{bs.get('benchmark_max_drawdown', 0):.2%} (excess {bs.get('excess_max_dd', 0):+.2%}); "
        f"Sortino {bs.get('sortino', 0):.2f}",
        f"- **Turnover impact:**        annual turnover {bs.get('turnover_annual', 0):.0%}, "
        f"max single-name weight change {bs.get('max_weight_change', 0):.2f}",
        f"- **Capacity impact:**        avg ADV participation "
        f"{bs.get('avg_adv_participation', 0):.2%}, max rebalance notional "
        f"${bs.get('max_rebalance_notional', 0):,.0f}",
        f"- **Regime weakness:**        weakest in the **{worst_regime}** slice",
        "- **Recommended action:**     carry the winner to §3B (capacity model + "
        "attribution) — NOT deploy; deployment is owner-gated (ADR 0019)",
        "- **Do NOT do:**              do not enable on the live book on this study "
        "alone; the deep-history pool is survivorship-biased (read ΔmaxDD *relatively*, "
        "§0 Q6 / Gotcha 6)",
        "",
    ]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Portfolio construction comparison study (P10 §3A).")
    ap.add_argument("--store", default=None, help="factor store path (default: configured store)")
    ap.add_argument("--start", required=True)
    ap.add_argument("--end", required=True)
    ap.add_argument("--split", default=None, help="IS/OOS split date (default: midpoint)")
    ap.add_argument("--n", type=int, default=200)
    ap.add_argument("--top-quantile", type=float, default=0.20)
    ap.add_argument("--report-dir", default="../../research/portfolio_study")
    args = ap.parse_args(argv)

    from app.research.comparison import compare_experiments
    from app.research.dashboard import render_dashboard
    from app.research.engine import ExperimentConfig, run_experiment
    from app.research.promotion import gate_experiment
    from app.research.registry import ResearchStore

    start, end = date.fromisoformat(args.start), date.fromisoformat(args.end)
    split = date.fromisoformat(args.split) if args.split else None

    dataset = _dataset_from_store(args.store)
    store_label = f"{Path(args.store).name if args.store else 'default'} {start}..{end}"
    rstore = ResearchStore()
    try:
        benchmark_ids = _record_benchmarks(rstore)
        ids: list[str] = []
        labels: dict[str, str] = {}
        for method in _METHODS:
            for vol_target in (False, True):
                eid, label = _run_one(
                    rstore, dataset, store_path=args.store, start=start, end=end,
                    n=args.n, top_quantile=args.top_quantile, split=split,
                    method=method, vol_target=vol_target, benchmark_ids=benchmark_ids,
                    report_root=args.report_dir)
                ids.append(eid)
                labels[eid] = label
                print(f"ran {label} -> {eid}")

        gate_results = {labels[e]: gate_experiment(rstore, e, profile="portfolio_backtest")
                        for e in ids}
        cmp = compare_experiments(rstore, ids, _COMPARE_METRICS)

        report = ["# Portfolio Construction Study — momentum, v1 (3A)\n",
                  f"_Store: {store_label}. Methods: {', '.join(_METHODS)} × "
                  "{no overlay, vol-target 15%}. risk_parity_diagonal == inverse_vol in "
                  "v1 (Gotcha 5) — materially a two-method comparison._\n"]
        report += _scorecard_block(rstore, gate_results)
        report += ["## Cross-method metrics\n", cmp.to_markdown()]
        report += _regime_table(rstore, ids, labels)
        report += _interpretation(rstore, ids, labels, gate_results, store_label)
        report_md = "\n".join(report) + "\n"

        # Register the comparison report as a first-class artifact on a dedicated
        # comparison experiment (§4.9 — committed decision doc, checksummed by the
        # orchestrator), not just a loose MD file.
        from app.research.engine.orchestrator import ResearchArtifact, RunnerResult

        def _comparison_runner(_cfg: ExperimentConfig) -> RunnerResult:
            return RunnerResult(
                metrics_summary={"n_methods": len(ids)},
                metrics_detail={"experiment_ids": ids, "labels": labels},
                artifacts=[ResearchArtifact("comparison_report",
                                            "portfolio_study_comparison.md", report_md)])

        cmp_id = run_experiment(
            ExperimentConfig(kind="portfolio_comparison",
                             name="momentum construction comparison (3A)",
                             params={"experiment_ids": sorted(ids), "metrics": _COMPARE_METRICS}),
            _comparison_runner, store=rstore, dataset=dataset,
            report_dir=args.report_dir)
        print(f"comparison report -> experiment {cmp_id}")

        dash = render_dashboard(rstore)
        Path(args.report_dir).mkdir(parents=True, exist_ok=True)
        (Path(args.report_dir) / "dashboard.md").write_text(dash, encoding="utf-8")
        print(json.dumps({"experiments": ids, "comparison": cmp_id,
                          "report_dir": args.report_dir}, indent=2))
    finally:
        rstore.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
