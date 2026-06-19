"""Runners — thin adapters over the EXISTING study code (P10 Phase 2 §2).

A runner does an experiment's actual computation and returns a ``RunnerResult``;
the orchestrator handles identity/caching/provenance/registry/artifacts. These
adapters call the already-shipped study functions (``scripts.factor_research``)
rather than re-implementing anything — the orchestrator's value is integration.
"""

from __future__ import annotations

import json
from dataclasses import asdict
from datetime import date

from app.research.engine.orchestrator import ExperimentConfig, ResearchArtifact, RunnerResult


def factor_ic_runner(config: ExperimentConfig) -> RunnerResult:
    """Run the IS/OOS factor-IC study (reusing `scripts.factor_research`) and package
    it as a `RunnerResult`. ``config.params``: ``n``, ``start``, ``split``.

    metrics_summary = per-factor OOS IC + LS-Sharpe (queryable headline); detail =
    the full IS/OOS results + rolling-12m IC; artifact = the rankings JSON.
    """
    import pandas as pd

    from scripts.factor_research import _load_close, run_study

    p = config.params
    close = _load_close(int(p.get("n", 200)), str(p.get("start", "2016-01-01")))
    if close.empty:
        raise RuntimeError("no price data in the factor store — run ingest first")
    results, _ls_panel = run_study(close, split=pd.Timestamp(str(p.get("split", "2023-01-01"))))

    summary = {
        r.factor: {"oos_ic": r.mean_ic, "oos_ls_sharpe": r.ls_sharpe}
        for r in results if r.window == "OOS"
    }
    detail = {"results": [asdict(r) for r in results]}
    rankings = json.dumps(detail["results"], indent=2, default=str)
    return RunnerResult(
        metrics_summary=summary, metrics_detail=detail,
        artifacts=[ResearchArtifact("factor_rankings", "factor_rankings.json", rankings)],
    )


def portfolio_construction_runner(config: ExperimentConfig) -> RunnerResult:
    """Run one portfolio-construction backtest (a weighting method × overlay on the
    frozen momentum signal) and package the standard evidence bundle + scorecard
    metrics (Phase 3A §4.5). Reuses ``run_momentum_backtest`` — computes nothing here.

    ``config.params`` keys (all optional except the window):
      ``store_path`` (factor store; default store), ``start``/``end`` (ISO dates),
      ``n``, ``top_quantile``, ``lookback_days``, ``skip_days``, ``turnover_cost_bps``,
      ``initial_equity``, ``weighting`` (equal_weight|inverse_vol|risk_parity_diagonal),
      ``vol_lookback_days``, ``vol_target_annual`` (overlay; from the risk model),
      ``max_sector_pct`` (§3C per-sector book-weight cap; from the risk model, None = off),
      ``is_oos_split`` (ISO date for the IS/OOS Sharpe ratio),
      ``sector_completeness_min`` (health-check threshold, default 0 = off).
    """
    from app.factor_data.backtest import run_momentum_backtest
    from app.factor_data.store import FactorDataStore
    from app.research.engine.benchmark import load_spy_curve
    from app.research.engine.portfolio_eval import shape_portfolio_result

    p = config.params
    if "start" not in p or "end" not in p:
        raise ValueError("portfolio_construction_runner requires params 'start' and 'end'")

    # §3B-3: the committed SPY fixture (Market benchmark). Best-effort — absent fixture →
    # empty curve → SPY metrics omitted, never fabricated. ``benchmark_fixture`` overrides.
    benchmark_curve = load_spy_curve(p.get("benchmark_fixture")) or None

    # Only forward keys that are present, so run_momentum_backtest's own conservative
    # defaults apply for anything the caller omits.
    casts = {
        "n": int, "top_quantile": float, "lookback_days": int, "skip_days": int,
        "turnover_cost_bps": float, "initial_equity": float, "weighting": str,
        "vol_lookback_days": int, "vol_target_annual": float,
        "max_sector_pct": float,  # §3C sector-cap (from the risk model; None = disabled)
    }
    kwargs = {k: cast(p[k]) for k, cast in casts.items() if p.get(k) is not None}

    store_path = p.get("store_path")
    store = FactorDataStore(db_path=store_path, read_only=True) if store_path \
        else FactorDataStore(read_only=True)
    try:
        report = run_momentum_backtest(
            store, date.fromisoformat(str(p["start"])), date.fromisoformat(str(p["end"])),
            **kwargs,
        )
        split = date.fromisoformat(str(p["is_oos_split"])) if p.get("is_oos_split") else None
        return shape_portfolio_result(
            report, store, is_oos_split=split,
            sector_completeness_min=float(p.get("sector_completeness_min", 0.0)),
            benchmark_curve=benchmark_curve,
        )
    finally:
        store.close()
