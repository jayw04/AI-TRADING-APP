"""Research Engine §4: continuous revalidation (edge-decay alerts) + compare_experiments."""

from __future__ import annotations

import pytest

from app.research.comparison import compare_experiments
from app.research.engine import ExperimentConfig, RunnerResult, run_experiment
from app.research.monitor import RevalidationWatch, revalidate
from app.research.registry import DatasetRecord, ResearchStore, StrategyRecord


@pytest.fixture
def store(tmp_path):
    s = ResearchStore(db_path=str(tmp_path / "research.duckdb"))
    yield s
    s.close()


# ---- continuous revalidation ----

_WATCHES = (
    RevalidationWatch("rolling_sharpe", "min", 0.5),
    RevalidationWatch("max_drawdown_abs", "max", 0.35),
)


def test_revalidate_alerts_on_decayed_edge(store):
    store.record_strategy(StrategyRecord(strategy_id="strat_mom", name="momentum",
                                         deployment_state="LIVE"))
    # rerun returns a decayed Sharpe → breach the min watch.
    alerts = revalidate(store, lambda s: {"rolling_sharpe": 0.2, "max_drawdown_abs": 0.20}, watches=_WATCHES)
    assert len(alerts) == 1
    a = alerts[0]
    assert a.strategy_id == "strat_mom" and a.metric == "rolling_sharpe"
    assert a.recommended_action == "RETIRE_REVIEW"
    assert store.row_count("alerts") == 1            # persisted
    # read-only: the strategy was NOT transitioned
    assert store.get_strategy("strat_mom").deployment_state == "LIVE"


def test_revalidate_no_alert_when_healthy(store):
    store.record_strategy(StrategyRecord(strategy_id="strat_ok", name="ok", deployment_state="PAPER"))
    alerts = revalidate(store, lambda s: {"rolling_sharpe": 1.8, "max_drawdown_abs": 0.15}, watches=_WATCHES)
    assert alerts == []
    assert store.row_count("alerts") == 0


def test_revalidate_only_active_strategies(store):
    store.record_strategy(StrategyRecord(strategy_id="s_live", name="live", deployment_state="LIVE"))
    store.record_strategy(StrategyRecord(strategy_id="s_none", name="research-only", deployment_state="NONE"))
    seen: list[str] = []

    def rerun(s):
        seen.append(s.strategy_id)
        return {"rolling_sharpe": 0.1}  # would breach, but only for active ones

    alerts = revalidate(store, rerun, watches=(RevalidationWatch("rolling_sharpe", "min", 0.5),))
    assert seen == ["s_live"]            # NONE-deployment strategy is not revalidated
    assert len(alerts) == 1


def test_revalidate_missing_metric_is_not_a_breach(store):
    store.record_strategy(StrategyRecord(strategy_id="s", name="s", deployment_state="LIVE"))
    alerts = revalidate(store, lambda s: {}, watches=_WATCHES)  # no metrics → no false alerts
    assert alerts == []


def test_max_watch_alerts_on_drawdown_blowout(store):
    store.record_strategy(StrategyRecord(strategy_id="s_dd", name="dd", deployment_state="LIVE"))
    alerts = revalidate(store, lambda s: {"rolling_sharpe": 1.0, "max_drawdown_abs": 0.45}, watches=_WATCHES)
    assert len(alerts) == 1 and alerts[0].metric == "max_drawdown_abs"


# ---- compare_experiments ----


def _exp(store, metrics):
    return run_experiment(
        ExperimentConfig(kind="book_backtest", name="t", params={"k": id(metrics)}),
        lambda c: RunnerResult(metrics_summary=metrics),
        store=store, dataset=DatasetRecord(dataset_id="d", provider="p", version="v"),
    )


def test_compare_picks_direction_aware_winners(store):
    a = _exp(store, {"sharpe": 1.85, "max_drawdown_abs": 0.13, "turnover": 5.6})
    b = _exp(store, {"sharpe": 1.40, "max_drawdown_abs": 0.39, "turnover": 8.8})
    res = compare_experiments(store, [a, b], ["sharpe", "max_drawdown_abs", "turnover"])
    by_metric = {r.metric: r for r in res.rows}
    assert by_metric["sharpe"].winner == a          # higher Sharpe wins
    assert by_metric["max_drawdown_abs"].winner == a  # lower drawdown wins
    assert by_metric["turnover"].winner == a          # lower turnover wins
    assert "winner" in res.to_markdown()


def test_compare_handles_missing_and_nested(store):
    a = _exp(store, {"mom_12": {"oos_ls_sharpe": 1.33}})
    b = _exp(store, {"mom_12": {"oos_ls_sharpe": 0.42}})
    res = compare_experiments(store, [a, b], ["mom_12.oos_ls_sharpe", "absent"])
    by_metric = {r.metric: r for r in res.rows}
    assert by_metric["mom_12.oos_ls_sharpe"].winner == a   # dotted path into nested summary
    assert by_metric["absent"].winner is None              # missing metric → no winner, no crash
