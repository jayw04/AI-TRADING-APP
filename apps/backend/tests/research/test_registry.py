"""Research Engine registries (§1): round-trip, idempotency, dependency walk, transitions."""

from __future__ import annotations

import pytest

from app.research.registry import (
    ArtifactRecord,
    DatasetRecord,
    ExperimentRecord,
    FeatureRecord,
    ResearchStore,
    StrategyRecord,
)


@pytest.fixture
def store(tmp_path):
    s = ResearchStore(db_path=str(tmp_path / "research.duckdb"))
    yield s
    s.close()


def test_schema_has_all_registries(store: ResearchStore) -> None:
    tables = {r[0] for r in store.con.execute("SHOW TABLES").fetchall()}
    assert {"strategies", "features", "datasets", "experiments", "artifacts", "transitions"}.issubset(tables)


def test_strategy_round_trip_and_auto_id(store: ResearchStore) -> None:
    sid = store.record_strategy(StrategyRecord(name="momentum-12m", category="equity-factor"))
    assert sid.startswith("strat_")
    got = store.get_strategy(sid)
    assert got is not None
    assert got.name == "momentum-12m"
    assert got.research_state == "RESEARCH" and got.deployment_state == "NONE"  # defaults
    assert got.created_at is not None


def test_experiment_round_trip_preserves_json_fields(store: ResearchStore) -> None:
    eid = store.record_experiment(ExperimentRecord(
        kind="book_backtest", feature_ids=["feat_mom12"], seed=7,
        params={"lookback": 252, "skip": 0}, package_versions={"pandas": "2.2"},
        metrics_summary={"sharpe": 1.85, "maxdd": -0.32}, confidence_score=88,
    ))
    got = store.get_experiment(eid)
    assert got is not None
    assert got.feature_ids == ["feat_mom12"]
    assert got.params == {"lookback": 252, "skip": 0}
    assert got.metrics_summary["sharpe"] == 1.85
    assert got.seed == 7 and got.confidence_score == 88


def test_idempotent_upsert(store: ResearchStore) -> None:
    store.record_dataset(DatasetRecord(dataset_id="data_sep_2026", provider="sharadar", version="2026-06-16"))
    store.record_dataset(DatasetRecord(dataset_id="data_sep_2026", provider="sharadar", version="2026-06-16"))
    assert store.row_count("datasets") == 1  # same PK → replaced, not duplicated


def test_dependency_graph_walk(store: ResearchStore) -> None:
    sid = store.record_strategy(StrategyRecord(strategy_id="strat_mom", name="mom"))
    store.record_feature(FeatureRecord(feature_id="feat_mom12", description="12m momentum", formula="c/c.shift(252)-1"))
    did = store.record_dataset(DatasetRecord(dataset_id="data_sep", provider="sharadar", version="v1"))
    store.record_experiment(ExperimentRecord(
        experiment_id="exp_1", kind="book_backtest", strategy_id=sid,
        dataset_id=did, feature_ids=["feat_mom12"],
    ))
    store.record_artifact(ArtifactRecord(artifact_id="art_rep", experiment_id="exp_1",
                                         type="report", path="research/x.md", checksum="abc"))
    dep = store.dependencies("exp_1")
    assert dep["strategy_id"] == "strat_mom"
    assert dep["dataset_id"] == "data_sep"
    assert dep["feature_ids"] == ["feat_mom12"]
    assert dep["artifact_ids"] == ["art_rep"]


def test_parent_experiment_genealogy(store: ResearchStore) -> None:
    store.record_experiment(ExperimentRecord(experiment_id="exp_mom6", kind="factor_ic"))
    store.record_experiment(ExperimentRecord(experiment_id="exp_mom12", kind="factor_ic",
                                             parent_experiment_id="exp_mom6"))
    assert store.dependencies("exp_mom12")["parent_experiment_id"] == "exp_mom6"


def test_transition_records_reason_and_updates_state(store: ResearchStore) -> None:
    sid = store.record_strategy(StrategyRecord(strategy_id="strat_x", name="x"))
    tr = store.transition(entity_type="strategy", entity_id=sid, axis="research",
                          to_state="VALIDATED", reason="OOS Sharpe 1.85 > threshold", actor="jay")
    assert tr.from_state == "RESEARCH" and tr.to_state == "VALIDATED"
    assert store.get_strategy(sid).research_state == "VALIDATED"
    # deployment axis is independent
    store.transition(entity_type="strategy", entity_id=sid, axis="deployment",
                     to_state="PAPER", reason="promoted to paper")
    s = store.get_strategy(sid)
    assert s.research_state == "VALIDATED" and s.deployment_state == "PAPER"  # two orthogonal axes
    log = store.transitions_for(sid)
    assert len(log) == 2
    assert {t.reason for t in log} == {"OOS Sharpe 1.85 > threshold", "promoted to paper"}


def test_transition_rejects_bad_state_and_axis(store: ResearchStore) -> None:
    store.record_strategy(StrategyRecord(strategy_id="strat_y", name="y"))
    with pytest.raises(ValueError, match="not a valid research state"):
        store.transition(entity_type="strategy", entity_id="strat_y", axis="research",
                         to_state="LIVE", reason="oops")  # LIVE is a deployment state
    with pytest.raises(ValueError, match="axis must be"):
        store.transition(entity_type="strategy", entity_id="strat_y", axis="bogus",
                         to_state="VALIDATED", reason="oops")


def test_experiment_has_no_deployment_axis(store: ResearchStore) -> None:
    store.record_experiment(ExperimentRecord(experiment_id="exp_z", kind="factor_ic"))
    with pytest.raises(ValueError, match="no deployment_state"):
        store.transition(entity_type="experiment", entity_id="exp_z", axis="deployment",
                         to_state="LIVE", reason="oops")


def test_transition_unknown_entity_raises(store: ResearchStore) -> None:
    with pytest.raises(ValueError, match="not found"):
        store.transition(entity_type="strategy", entity_id="nope", axis="research",
                         to_state="VALIDATED", reason="oops")


def test_list_experiments_filters(store: ResearchStore) -> None:
    store.record_experiment(ExperimentRecord(experiment_id="e1", kind="factor_ic", strategy_id="s1"))
    store.record_experiment(ExperimentRecord(experiment_id="e2", kind="book_backtest", strategy_id="s1"))
    store.record_experiment(ExperimentRecord(experiment_id="e3", kind="book_backtest", strategy_id="s2"))
    assert set(store.list_experiments(kind="book_backtest")) == {"e2", "e3"}
    assert set(store.list_experiments(strategy_id="s1")) == {"e1", "e2"}


def test_row_count_guards_unknown_table(store: ResearchStore) -> None:
    with pytest.raises(ValueError, match="unknown table"):
        store.row_count("orders")
