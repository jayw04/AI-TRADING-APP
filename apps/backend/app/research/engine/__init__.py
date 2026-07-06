"""Engine layer: the orchestrator that chains existing study stages into recorded,
reproducible, content-addressed experiments (P10 Phase 2 §2)."""

from app.research.engine.attribution import (
    build_attribution_artifacts,
    drawdown_attribution,
    return_attribution,
    turnover_attribution,
)
from app.research.engine.benchmark import benchmark_metrics, load_spy_curve
from app.research.engine.orchestrator import (
    ExperimentConfig,
    ResearchArtifact,
    Runner,
    RunnerResult,
    fingerprint,
    run_experiment,
)
from app.research.engine.portfolio_eval import build_evidence_bundle, shape_portfolio_result
from app.research.engine.runners import factor_ic_runner, portfolio_construction_runner

__all__ = [
    "ExperimentConfig",
    "ResearchArtifact",
    "Runner",
    "RunnerResult",
    "fingerprint",
    "run_experiment",
    "factor_ic_runner",
    "portfolio_construction_runner",
    "build_evidence_bundle",
    "shape_portfolio_result",
    "return_attribution",
    "turnover_attribution",
    "drawdown_attribution",
    "build_attribution_artifacts",
    "benchmark_metrics",
    "load_spy_curve",
]
