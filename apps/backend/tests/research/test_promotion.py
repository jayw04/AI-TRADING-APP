"""Promotion gate (§3): verdicts (§5c-faithful), confidence score, experiment gating."""

from __future__ import annotations

import pytest

from app.research.engine import ExperimentConfig, RunnerResult, run_experiment
from app.research.promotion import evaluate, gate_experiment
from app.research.promotion.gate import BOOK_BACKTEST_PROFILE, FACTOR_IC_PROFILE
from app.research.registry import DatasetRecord, ResearchStore


@pytest.fixture
def store(tmp_path):
    s = ResearchStore(db_path=str(tmp_path / "research.duckdb"))
    yield s
    s.close()


def _book(**over):
    m = dict(profit_factor=1.5, win_rate=0.50, avg_win_loss=1.2, expectancy_r=0.30,
             max_drawdown=-0.05, is_pf=1.4, oos_pf=1.3, data_coverage=0.99,
             robust_pf_ratio=0.9, robust_trade_ratio=0.9, trade_count=80)
    m.update(over)
    return m


def test_book_backtest_go_when_strong_and_all_pass():
    r = evaluate(_book(), BOOK_BACKTEST_PROFILE)
    assert r.verdict == "GO" and r.research_state == "VALIDATED"
    assert r.confidence_score == 100


def test_book_backtest_go_warning_on_thin_sample():
    r = evaluate(_book(trade_count=40), BOOK_BACKTEST_PROFILE)
    assert r.verdict == "GO_WARNING" and r.research_state == "VALIDATED"  # all pass, thin sample


def test_book_backtest_no_go_on_failed_criterion():
    r = evaluate(_book(profit_factor=1.1), BOOK_BACKTEST_PROFILE)
    assert r.verdict == "NO-GO" and r.research_state == "REJECTED"
    assert any("profit_factor" in label for label, ok, _ in r.checks if not ok)
    assert r.confidence_score < 100


def test_book_backtest_inconclusive_below_trade_floor():
    r = evaluate(_book(trade_count=20), BOOK_BACKTEST_PROFILE)
    assert r.verdict == "INCONCLUSIVE" and r.research_state == "RESEARCH"


def test_oos_pf_dynamic_threshold():
    # OOS PF must clear max(1.0, 0.8*IS). IS 2.0 → needs OOS >= 1.6.
    assert evaluate(_book(is_pf=2.0, oos_pf=1.7), BOOK_BACKTEST_PROFILE).verdict in ("GO", "GO_WARNING")
    assert evaluate(_book(is_pf=2.0, oos_pf=1.4), BOOK_BACKTEST_PROFILE).verdict == "NO-GO"


def test_factor_ic_go_for_momentum_like():
    r = evaluate(dict(oos_ic=0.06, oos_ls_sharpe=1.33, ic_hit=0.63,
                      rolling_ic_pct_positive=0.71, n_periods=72), FACTOR_IC_PROFILE)
    assert r.verdict == "GO" and r.research_state == "VALIDATED"


def test_factor_ic_no_go_for_value_like():
    r = evaluate(dict(oos_ic=-0.04, oos_ls_sharpe=-1.78, ic_hit=0.41,
                      rolling_ic_pct_positive=0.28, n_periods=72), FACTOR_IC_PROFILE)
    assert r.verdict == "NO-GO" and r.research_state == "REJECTED"


def test_missing_metric_fails_closed():
    r = evaluate(_book(profit_factor=None), BOOK_BACKTEST_PROFILE)  # type: ignore[arg-type]
    assert r.verdict == "NO-GO"


def test_confidence_is_monotone():
    strong = evaluate(_book(), BOOK_BACKTEST_PROFILE).confidence_score
    one_fail = evaluate(_book(win_rate=0.1), BOOK_BACKTEST_PROFILE).confidence_score
    assert strong > one_fail


# ---- integration with the registry (gate_experiment) ----


def _record(store, metrics, kind="book_backtest"):
    return run_experiment(
        ExperimentConfig(kind=kind, name="t", params={}),
        lambda c: RunnerResult(metrics_summary=metrics),
        store=store, dataset=DatasetRecord(dataset_id="d", provider="p", version="v"),
    )


def test_gate_experiment_validates_and_logs_reason(store):
    eid = _record(store, _book())
    res = gate_experiment(store, eid, profile="book_backtest")
    assert res.verdict == "GO"
    exp = store.get_experiment(eid)
    assert exp.research_state == "VALIDATED"
    assert exp.confidence_score == 100
    log = store.transitions_for(eid)
    assert len(log) == 1
    assert log[0].to_state == "VALIDATED" and "GO" in log[0].reason


def test_gate_experiment_rejects(store):
    eid = _record(store, _book(profit_factor=1.0))
    res = gate_experiment(store, eid, profile="book_backtest")
    assert res.verdict == "NO-GO"
    assert store.get_experiment(eid).research_state == "REJECTED"


def test_gate_experiment_inconclusive_does_not_transition(store):
    eid = _record(store, _book(trade_count=10))
    res = gate_experiment(store, eid, profile="book_backtest")
    assert res.verdict == "INCONCLUSIVE"
    exp = store.get_experiment(eid)
    assert exp.research_state == "RESEARCH"          # no transition
    assert exp.confidence_score is not None          # but confidence still recorded
    assert store.transitions_for(eid) == []
