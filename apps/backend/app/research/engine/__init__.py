"""Engine layer: the orchestrator that chains existing study stages into recorded,
reproducible, content-addressed experiments (P10 Phase 2 §2)."""

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
]
