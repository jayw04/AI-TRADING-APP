"""Phase 3 §3.0 — portfolio / benchmark / cost-model registries: round-trip + list."""

from __future__ import annotations

import pytest

from app.research.registry import (
    BenchmarkRecord,
    CostModelRecord,
    PortfolioModelRecord,
    ResearchStore,
)


@pytest.fixture
def store(tmp_path):
    s = ResearchStore(db_path=str(tmp_path / "research.duckdb"))
    yield s
    s.close()


def test_schema_has_phase3_registries(store: ResearchStore) -> None:
    tables = {r[0] for r in store.con.execute("SHOW TABLES").fetchall()}
    assert {"portfolio_models", "benchmarks", "cost_models"}.issubset(tables)


def test_portfolio_model_round_trip(store: ResearchStore) -> None:
    pid = store.record_portfolio_model(PortfolioModelRecord(
        strategy_id="strat_mom", construction_method="top_quintile",
        weighting="inverse_vol", rebalance="weekly", buffer="rank_hysteresis_5pct",
        params={"max_names": 10, "vol_target": 0.15}))
    assert pid.startswith("pf_")
    got = store.get_portfolio_model(pid)
    assert got is not None
    assert got.weighting == "inverse_vol"
    assert got.params == {"max_names": 10, "vol_target": 0.15}
    assert got.status == "RESEARCH"


def test_benchmark_round_trip(store: ResearchStore) -> None:
    bid = store.record_benchmark(BenchmarkRecord(benchmark_id="bm_spy", definition="SPY",
                                                 source="fmp", rebalance="none",
                                                 description="S&P 500 ETF"))
    got = store.get_benchmark(bid)
    assert got is not None and got.definition == "SPY" and got.source == "fmp"


def test_cost_model_round_trip(store: ResearchStore) -> None:
    cid = store.record_cost_model(CostModelRecord(commission=0.0, slippage=0.0005,
                                                  spread=0.0002, market_impact="sqrt_adv"))
    got = store.get_cost_model(cid)
    assert got is not None and got.slippage == 0.0005 and got.market_impact == "sqrt_adv"


def test_idempotent_and_list(store: ResearchStore) -> None:
    store.record_portfolio_model(PortfolioModelRecord(portfolio_id="pf_a", strategy_id="s1",
                                                      construction_method="ew", weighting="equal"))
    store.record_portfolio_model(PortfolioModelRecord(portfolio_id="pf_a", strategy_id="s1",
                                                      construction_method="ew", weighting="equal"))
    store.record_portfolio_model(PortfolioModelRecord(portfolio_id="pf_b", strategy_id="s2",
                                                      construction_method="ew"))
    assert store.row_count("portfolio_models") == 2          # upsert, not duplicate
    assert {m.portfolio_id for m in store.list_portfolio_models(strategy_id="s1")} == {"pf_a"}

    store.record_benchmark(BenchmarkRecord(definition="QQQ"))
    store.record_cost_model(CostModelRecord(commission=0.0))
    assert len(store.list_benchmarks()) == 1
    assert len(store.list_cost_models()) == 1


def test_row_count_allows_new_tables(store: ResearchStore) -> None:
    for t in ("portfolio_models", "benchmarks", "cost_models"):
        assert store.row_count(t) == 0
