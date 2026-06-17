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

__all__ = [
    "ExperimentConfig",
    "ResearchArtifact",
    "Runner",
    "RunnerResult",
    "fingerprint",
    "run_experiment",
]
