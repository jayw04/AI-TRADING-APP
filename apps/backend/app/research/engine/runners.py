"""Runners — thin adapters over the EXISTING study code (P10 Phase 2 §2).

A runner does an experiment's actual computation and returns a ``RunnerResult``;
the orchestrator handles identity/caching/provenance/registry/artifacts. These
adapters call the already-shipped study functions (``scripts.factor_research``)
rather than re-implementing anything — the orchestrator's value is integration.
"""

from __future__ import annotations

import json
from dataclasses import asdict

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
