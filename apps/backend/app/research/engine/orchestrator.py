"""Research Engine orchestrator (P10 Phase 2 §2).

One entrypoint — ``run_experiment`` — that turns a config into a recorded,
reproducible experiment: it captures provenance, runs the work, persists the result
+ its artifacts into the §1 registries, and is **content-addressed** so an
unchanged config + code + data reruns instantly (cache hit).

"Reuse, don't rebuild": the actual computation is a ``Runner`` — a thin adapter
over the *existing* study code (factor_research, the backtester). The orchestrator
owns only the cross-cutting concerns (identity, caching, provenance, registry +
artifact writes, evidence package); it does not re-implement any analysis.

No dashboard here — that is built last (plan §5).
"""

from __future__ import annotations

import hashlib
import json
import platform
import socket
import subprocess
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import structlog

from app.research.registry import (
    ArtifactRecord,
    DatasetRecord,
    ExperimentRecord,
    FeatureRecord,
    ResearchStore,
)

logger = structlog.get_logger(__name__)


@dataclass
class ExperimentConfig:
    """The reproducible inputs to an experiment. The fingerprint (→ experiment_id)
    is computed from these plus the dataset version + git commit, so identical
    inputs map to the same experiment."""
    kind: str                       # 'factor_ic' | 'book_backtest' | ...
    name: str
    params: dict[str, Any] = field(default_factory=dict)
    is_window: str | None = None
    oos_window: str | None = None
    strategy_id: str | None = None
    feature_ids: list[str] = field(default_factory=list)
    cost_model: str | None = None
    pit_mode: str = "accepted_date"        # see FMP PIT-assumptions doc
    survivorship_mode: str = "sep_universe"
    seed: int | None = None
    # Phase 3A §4.1: registry FKs. Stored as provenance on the experiment row; NOT
    # hashed into the fingerprint (the referenced records' *content* is folded into
    # ``params`` for content-addressing — §0 Q2). Random ids here would break
    # reproducibility, so identity stays content-based while these stay informational.
    portfolio_id: str | None = None
    benchmark_id: str | None = None
    cost_model_id: str | None = None
    risk_model_id: str | None = None


@dataclass
class ResearchArtifact:
    """An output file an experiment produces (report, rankings, evidence JSON).
    ``content`` is written under the run's report dir; the orchestrator checksums
    it and registers an artifacts row."""
    type: str
    filename: str
    content: str


@dataclass
class RunnerResult:
    metrics_summary: dict[str, Any] = field(default_factory=dict)
    metrics_detail: dict[str, Any] = field(default_factory=dict)
    artifacts: list[ResearchArtifact] = field(default_factory=list)
    confidence_score: int | None = None


# A Runner does the actual work for a config and returns its result. It is the
# adapter over existing study code — the orchestrator never computes metrics itself.
Runner = Callable[[ExperimentConfig], RunnerResult]


def _git_commit() -> str:
    try:
        out = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True, timeout=5
        )
        return out.stdout.strip() or "unknown"
    except Exception:  # noqa: BLE001 — provenance is best-effort, never fatal
        return "unknown"


def _package_versions(packages: tuple[str, ...] = ("pandas", "numpy", "duckdb")) -> dict[str, str]:
    import importlib.metadata as md
    out: dict[str, str] = {}
    for p in packages:
        try:
            out[p] = md.version(p)
        except Exception:  # noqa: BLE001
            out[p] = "n/a"
    return out


def fingerprint(config: ExperimentConfig, *, dataset_version: str, git_commit: str) -> str:
    """Deterministic experiment id from the reproducible inputs. Same config +
    code + data → same id (the basis for caching). Excludes wall-clock/host (those
    are provenance, not identity)."""
    payload = json.dumps(
        {
            "kind": config.kind, "params": config.params,
            "is_window": config.is_window, "oos_window": config.oos_window,
            "feature_ids": sorted(config.feature_ids), "strategy_id": config.strategy_id,
            "cost_model": config.cost_model, "pit_mode": config.pit_mode,
            "survivorship_mode": config.survivorship_mode,
            "dataset_version": dataset_version, "git_commit": git_commit,
        },
        sort_keys=True, default=str,
    )
    return "exp_" + hashlib.sha256(payload.encode()).hexdigest()[:16]


def run_experiment(
    config: ExperimentConfig,
    runner: Runner,
    *,
    store: ResearchStore,
    dataset: DatasetRecord,
    features: list[FeatureRecord] | None = None,
    report_dir: str | Path | None = None,
    force: bool = False,
) -> str:
    """Run (or cache-hit) one experiment and persist it + its artifacts.

    Steps: fingerprint → cache check → record dataset/features → run the ``runner``
    (timed) → record the experiment with full provenance → write & register each
    artifact. Returns the ``experiment_id``. With ``force=False`` (default), an
    existing experiment with the same fingerprint is returned without re-running.
    """
    git_commit = _git_commit()
    dataset_id = store.record_dataset(dataset)          # idempotent (keyed by dataset_id)
    feature_ids = [store.record_feature(f) for f in (features or [])] or list(config.feature_ids)

    experiment_id = fingerprint(config, dataset_version=dataset.version, git_commit=git_commit)
    if not force and store.get_experiment(experiment_id) is not None:
        logger.info("research_experiment_cache_hit", experiment_id=experiment_id, kind=config.kind)
        return experiment_id

    t0 = time.perf_counter()
    result = runner(config)
    duration_ms = int((time.perf_counter() - t0) * 1000)

    store.record_experiment(ExperimentRecord(
        experiment_id=experiment_id, kind=config.kind, duration_ms=duration_ms,
        strategy_id=config.strategy_id, dataset_id=dataset_id, feature_ids=feature_ids,
        git_commit=git_commit, host=socket.gethostname(), python_version=platform.python_version(),
        package_versions=_package_versions(), seed=config.seed, params=config.params,
        is_window=config.is_window, oos_window=config.oos_window, cost_model=config.cost_model,
        pit_mode=config.pit_mode, survivorship_mode=config.survivorship_mode,
        metrics_summary=result.metrics_summary, metrics_detail=result.metrics_detail,
        confidence_score=result.confidence_score, notes=config.name,
        portfolio_id=config.portfolio_id, benchmark_id=config.benchmark_id,
        cost_model_id=config.cost_model_id, risk_model_id=config.risk_model_id,
    ))

    out_dir = Path(report_dir) if report_dir is not None else None
    if out_dir is not None:
        out_dir.mkdir(parents=True, exist_ok=True)
    for art in result.artifacts:
        checksum = hashlib.sha256(art.content.encode()).hexdigest()
        path = str(out_dir / art.filename) if out_dir is not None else art.filename
        if out_dir is not None:
            (out_dir / art.filename).write_text(art.content, encoding="utf-8")
        store.record_artifact(ArtifactRecord(
            experiment_id=experiment_id, type=art.type, path=path,
            checksum=checksum, description=config.name,
        ))
    logger.info("research_experiment_recorded", experiment_id=experiment_id, kind=config.kind,
                duration_ms=duration_ms, artifacts=len(result.artifacts))
    return experiment_id
