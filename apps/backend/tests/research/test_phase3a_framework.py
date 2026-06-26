"""Phase 3A PR A (framework) — risk-model registry, experiment FK wiring, and the
transparent scorecard (gate component breakdown + min_confidence floor)."""

from __future__ import annotations

import pytest

from app.research.promotion import GateProfile, evaluate, ge, le
from app.research.registry import (
    ExperimentRecord,
    ResearchStore,
    RiskModelRecord,
)


@pytest.fixture
def store(tmp_path):
    s = ResearchStore(db_path=str(tmp_path / "research.duckdb"))
    yield s
    s.close()


# ---- risk_models registry (§4.2) ----


def test_risk_models_table_present(store: ResearchStore) -> None:
    tables = {r[0] for r in store.con.execute("SHOW TABLES").fetchall()}
    assert "risk_models" in tables
    assert store.row_count("risk_models") == 0


def test_risk_model_round_trip(store: ResearchStore) -> None:
    rid = store.record_risk_model(RiskModelRecord(
        kind="vol_target", vol_target_annual=0.15, vol_ewma_span=20,
        params={"note": "ewma realized vol"}, description="15% annual vol target"))
    assert rid.startswith("rm_")
    got = store.get_risk_model(rid)
    assert got is not None
    assert got.kind == "vol_target"
    assert got.vol_target_annual == 0.15
    assert got.vol_ewma_span == 20
    assert got.params == {"note": "ewma realized vol"}


def test_risk_model_idempotent_and_list(store: ResearchStore) -> None:
    store.record_risk_model(RiskModelRecord(risk_model_id="rm_none", kind="none"))
    store.record_risk_model(RiskModelRecord(risk_model_id="rm_none", kind="none"))
    store.record_risk_model(RiskModelRecord(kind="sector_cap", max_sector_pct=0.40))
    assert store.row_count("risk_models") == 2          # upsert, not duplicate
    kinds = {m.kind for m in store.list_risk_models()}
    assert kinds == {"none", "sector_cap"}


# ---- experiment ↔ registry FK wiring (§4.1) ----


def test_experiment_fk_round_trip(store: ResearchStore) -> None:
    store.record_experiment(ExperimentRecord(
        experiment_id="exp_fk", kind="portfolio_construction",
        portfolio_id="pf_1", benchmark_id="bm_1",
        cost_model_id="cost_1", risk_model_id="rm_1"))
    got = store.get_experiment("exp_fk")
    assert got is not None
    assert got.portfolio_id == "pf_1"
    assert got.benchmark_id == "bm_1"
    assert got.cost_model_id == "cost_1"
    assert got.risk_model_id == "rm_1"


def test_experiment_fk_default_none(store: ResearchStore) -> None:
    """Existing kinds (no FKs supplied) round-trip with NULL FKs — additive, inert."""
    store.record_experiment(ExperimentRecord(experiment_id="exp_plain", kind="factor_ic"))
    got = store.get_experiment("exp_plain")
    assert got is not None
    assert got.portfolio_id is None and got.risk_model_id is None


def test_fk_columns_added_to_preexisting_store(tmp_path) -> None:
    """A store written before Phase 3A (no FK columns) gets them additively on reopen
    via _ensure_experiment_fk_columns — simulated by dropping then reopening."""
    path = str(tmp_path / "old.duckdb")
    s = ResearchStore(db_path=path)
    for col in ("portfolio_id", "benchmark_id", "cost_model_id", "risk_model_id"):
        s.con.execute(f"ALTER TABLE experiments DROP COLUMN {col}")
    cols = {r[0] for r in s.con.execute(
        "SELECT column_name FROM information_schema.columns WHERE table_name='experiments'"
    ).fetchall()}
    assert "portfolio_id" not in cols
    s.close()

    s2 = ResearchStore(db_path=path)                    # reopen → _ensure re-adds them
    cols2 = {r[0] for r in s2.con.execute(
        "SELECT column_name FROM information_schema.columns WHERE table_name='experiments'"
    ).fetchall()}
    assert {"portfolio_id", "benchmark_id", "cost_model_id", "risk_model_id"}.issubset(cols2)
    s2.record_experiment(ExperimentRecord(experiment_id="exp_after", kind="k", risk_model_id="rm_x"))
    assert s2.get_experiment("exp_after").risk_model_id == "rm_x"
    s2.close()


# ---- transparent scorecard: component breakdown + min_confidence (§4.7/§4.7a) ----


def test_component_breakdown_groups_by_component() -> None:
    profile = GateProfile(name="t", criteria=[
        ge("a", 1.0, component="statistical", weight=2.0),
        ge("b", 1.0, component="statistical", weight=1.0),
        le("c", 1.0, component="drawdown", weight=2.0),
    ])
    # a passes (2>=1), b fails (0<1), c passes (0<=1)
    res = evaluate({"a": 2.0, "b": 0.0, "c": 0.0}, profile)
    by = {cs.component: cs for cs in res.component_scores}
    assert by["statistical"].passed_weight == 2.0 and by["statistical"].total_weight == 3.0
    assert by["drawdown"].fraction == 1.0
    # overall confidence = (2 + 2) / 5 = 80
    assert res.confidence_score == 80


def test_min_confidence_floor_forces_no_go() -> None:
    # all criteria PASS → confidence 100, but min_confidence is unreachable → still GO.
    passing = GateProfile(name="p", criteria=[ge("x", 1.0)], min_confidence=70)
    assert evaluate({"x": 5.0}, passing).verdict == "GO"
    # a profile whose floor bites when a low-weight criterion fails:
    prof = GateProfile(name="q", min_confidence=80, criteria=[
        ge("x", 1.0, weight=3.0), ge("y", 1.0, weight=2.0)])
    res = evaluate({"x": 5.0, "y": 0.0}, prof)   # y fails → confidence 60 < 80
    assert res.verdict == "NO-GO"
    assert any("min_confidence" in r for r in res.reasons)


def test_existing_profiles_unchanged_default_component() -> None:
    """Criteria without an explicit component fall in 'overall' (back-compat)."""
    prof = GateProfile(name="legacy", criteria=[ge("x", 1.0)])
    res = evaluate({"x": 2.0}, prof)
    assert [cs.component for cs in res.component_scores] == ["overall"]
