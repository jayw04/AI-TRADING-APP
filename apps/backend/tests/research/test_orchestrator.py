"""Research Engine orchestrator (§2): identity/caching, provenance, artifact capture, linking."""

from __future__ import annotations

import pytest

from app.research.engine import (
    ExperimentConfig,
    ResearchArtifact,
    RunnerResult,
    fingerprint,
    run_experiment,
)
from app.research.registry import DatasetRecord, FeatureRecord, ResearchStore


@pytest.fixture
def store(tmp_path):
    s = ResearchStore(db_path=str(tmp_path / "research.duckdb"))
    yield s
    s.close()


def _dataset() -> DatasetRecord:
    return DatasetRecord(dataset_id="sep_2026-06-16", provider="sharadar", version="2026-06-16")


def _config(**over) -> ExperimentConfig:
    base = dict(kind="factor_ic", name="test", params={"n": 200, "split": "2023-01-01"})
    base.update(over)
    return ExperimentConfig(**base)


class _CountingRunner:
    """A fake runner that records how many times it actually ran."""

    def __init__(self):
        self.calls = 0

    def __call__(self, config: ExperimentConfig) -> RunnerResult:
        self.calls += 1
        return RunnerResult(
            metrics_summary={"mom_12": {"oos_ls_sharpe": 1.33}},
            metrics_detail={"n": config.params.get("n")},
            artifacts=[ResearchArtifact("rankings", "factor_rankings.json", '{"x":1}')],
            confidence_score=88,
        )


def test_records_experiment_with_provenance_and_metrics(store, tmp_path):
    runner = _CountingRunner()
    eid = run_experiment(_config(), runner, store=store, dataset=_dataset(), report_dir=tmp_path)
    assert runner.calls == 1
    exp = store.get_experiment(eid)
    assert exp is not None
    assert exp.kind == "factor_ic"
    assert exp.dataset_id == "sep_2026-06-16"
    assert exp.metrics_summary["mom_12"]["oos_ls_sharpe"] == 1.33
    assert exp.confidence_score == 88
    # provenance captured
    assert exp.host and exp.python_version
    assert exp.duration_ms is not None and exp.duration_ms >= 0
    assert "duckdb" in exp.package_versions


def test_content_addressed_caching(store, tmp_path):
    runner = _CountingRunner()
    eid1 = run_experiment(_config(), runner, store=store, dataset=_dataset(), report_dir=tmp_path)
    eid2 = run_experiment(_config(), runner, store=store, dataset=_dataset(), report_dir=tmp_path)
    assert eid1 == eid2           # same config+data+code → same id
    assert runner.calls == 1      # second call is a cache hit — runner not re-invoked


def test_force_reruns(store, tmp_path):
    runner = _CountingRunner()
    run_experiment(_config(), runner, store=store, dataset=_dataset(), report_dir=tmp_path)
    run_experiment(_config(), runner, store=store, dataset=_dataset(), report_dir=tmp_path, force=True)
    assert runner.calls == 2


def test_fingerprint_changes_with_params():
    a = fingerprint(_config(params={"n": 200}), dataset_version="v1", git_commit="abc")
    b = fingerprint(_config(params={"n": 500}), dataset_version="v1", git_commit="abc")
    c = fingerprint(_config(params={"n": 200}), dataset_version="v2", git_commit="abc")
    assert a != b          # different params → different id
    assert a != c          # different dataset version → different id
    assert a == fingerprint(_config(params={"n": 200}), dataset_version="v1", git_commit="abc")


def test_artifact_written_checksummed_and_linked(store, tmp_path):
    eid = run_experiment(_config(), _CountingRunner(), store=store, dataset=_dataset(), report_dir=tmp_path)
    # file written
    assert (tmp_path / "factor_rankings.json").read_text() == '{"x":1}'
    # artifact registered + reachable via the dependency walk
    dep = store.dependencies(eid)
    assert len(dep["artifact_ids"]) == 1
    assert store.row_count("artifacts") == 1


def test_features_recorded_and_linked(store, tmp_path):
    feats = [FeatureRecord(feature_id="feat_mom12", description="12m", formula="c/c.shift(252)-1")]
    eid = run_experiment(_config(), _CountingRunner(), store=store, dataset=_dataset(),
                         features=feats, report_dir=tmp_path)
    assert store.row_count("features") == 1
    assert store.dependencies(eid)["feature_ids"] == ["feat_mom12"]
