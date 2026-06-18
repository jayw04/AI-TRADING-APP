"""Research dashboard (§5): renders KPIs, experiments, strategies, alerts, lineage."""

from __future__ import annotations

import pytest

from app.research.dashboard import render_dashboard, write_dashboard
from app.research.registry import (
    AlertRecord,
    ExperimentRecord,
    ResearchStore,
    StrategyRecord,
)


@pytest.fixture
def store(tmp_path):
    s = ResearchStore(db_path=str(tmp_path / "research.duckdb"))
    yield s
    s.close()


def _seed(store: ResearchStore) -> None:
    store.record_strategy(StrategyRecord(strategy_id="strat_mom", name="momentum-12m",
                                         research_state="VALIDATED", deployment_state="LIVE"))
    store.record_experiment(ExperimentRecord(experiment_id="exp_mom6", kind="factor_ic",
                                             research_state="REJECTED", confidence_score=40))
    store.record_experiment(ExperimentRecord(experiment_id="exp_mom12", kind="factor_ic",
                                             parent_experiment_id="exp_mom6",
                                             research_state="VALIDATED", confidence_score=92))
    store.record_alert(AlertRecord(strategy_id="strat_mom", kind="edge_decay",
                                   metric="rolling_sharpe", value=0.2, threshold=0.5,
                                   recommended_action="RETIRE_REVIEW"))


def test_render_contains_all_sections(store):
    _seed(store)
    md = render_dashboard(store)
    for section in ("# Research Engine — dashboard", "## KPIs", "## Recent experiments",
                    "## Strategies", "## Open alerts", "## Experiment lineage"):
        assert section in md


def test_render_shows_kpis_and_confidence(store):
    _seed(store)
    md = render_dashboard(store)
    assert "experiments: **2**" in md           # 2 experiments
    assert "LIVE 1" in md                        # one live strategy
    assert "open research alerts: **1**" in md
    assert "92" in md and "exp_mom12" in md      # confidence surfaced


def test_lineage_shows_parent_child(store):
    _seed(store)
    md = render_dashboard(store)
    # exp_mom6 (root) → exp_mom12 (child) indented beneath it
    assert "`exp_mom6`" in md and "`exp_mom12`" in md
    lines = md.splitlines()
    root_i = next(i for i, ln in enumerate(lines) if "`exp_mom6`" in ln and ln.strip().startswith("-"))
    child_i = next(i for i, ln in enumerate(lines) if "`exp_mom12`" in ln and ln.strip().startswith("-"))
    assert child_i > root_i
    assert lines[child_i].startswith("  ")        # child is indented (deeper in the DAG)


def test_empty_store_renders_without_crashing(store):
    md = render_dashboard(store)
    assert "experiments: **0**" in md
    assert "_none_" in md                         # no open alerts


def test_write_dashboard_to_file(store, tmp_path):
    _seed(store)
    out = tmp_path / "dash" / "dashboard.md"
    write_dashboard(store, str(out))
    assert out.read_text(encoding="utf-8").startswith("# Research Engine — dashboard")
