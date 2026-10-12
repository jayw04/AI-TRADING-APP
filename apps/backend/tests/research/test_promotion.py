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


def _record(store, metrics, kind="book_backtest", name="t"):
    return run_experiment(
        ExperimentConfig(kind=kind, name=name, params={"case": name}),
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


# ---- thin sample requires a recorded decision (reference, not a signature) ----


def test_thin_sample_reason_names_recorded_decision_not_signoff():
    r = evaluate(_book(trade_count=40), BOOK_BACKTEST_PROFILE)
    assert r.verdict == "GO_WARNING"
    assert any("recorded decision required" in x for x in r.reasons)
    assert not any("signoff" in x.lower() for x in r.reasons)


def test_thin_sample_without_recorded_decision_is_refused(store):
    eid = _record(store, _book(trade_count=40))
    res = gate_experiment(store, eid, profile="book_backtest")
    assert res.verdict == "GO_WARNING" and res.research_state == "RESEARCH"
    assert any("no recorded decision" in x for x in res.reasons)
    exp = store.get_experiment(eid)
    assert exp.research_state == "RESEARCH"
    assert exp.confidence_score is not None
    assert store.transitions_for(eid) == []


@pytest.mark.parametrize("blank", ["", "   ", "\n\t"])
def test_blank_recorded_decision_counts_as_absent(store, blank):
    eid = _record(store, _book(trade_count=40))
    res = gate_experiment(store, eid, profile="book_backtest", recorded_decision=blank)
    assert res.research_state == "RESEARCH"
    assert store.transitions_for(eid) == []


def test_thin_sample_with_recorded_decision_is_validated_and_logged(store):
    eid = _record(store, _book(trade_count=40))
    ref = "2026-10-12 weekly meeting item 3"
    res = gate_experiment(store, eid, profile="book_backtest", recorded_decision=ref)
    assert res.verdict == "GO_WARNING" and res.research_state == "VALIDATED"
    assert store.get_experiment(eid).research_state == "VALIDATED"
    log = store.transitions_for(eid)
    assert len(log) == 1 and ref in log[0].reason and "GO_WARNING" in log[0].reason


def test_non_string_recorded_decision_rejected(store):
    eid = _record(store, _book(trade_count=40))
    with pytest.raises(TypeError):
        gate_experiment(store, eid, profile="book_backtest",
                        recorded_decision=123)  # type: ignore[arg-type]


def test_old_signature_style_input_is_gone(store):
    eid = _record(store, _book(trade_count=40))
    for name in ("owner_signoff", "signed_by", "signoff"):
        with pytest.raises(TypeError):
            gate_experiment(store, eid, profile="book_backtest", **{name: "x"})  # type: ignore[arg-type]


def test_recorded_decision_does_not_relax_thresholds(store):
    # NO-GO and INCONCLUSIVE are unchanged by supplying a decision.
    nogo = _record(store, _book(profit_factor=1.0), name="nogo")
    assert gate_experiment(store, nogo, profile="book_backtest",
                           recorded_decision="d-1").verdict == "NO-GO"
    assert store.get_experiment(nogo).research_state == "REJECTED"
    inc = _record(store, _book(trade_count=10), name="inc")
    assert gate_experiment(store, inc, profile="book_backtest",
                           recorded_decision="d-1").verdict == "INCONCLUSIVE"
    assert store.get_experiment(inc).research_state == "RESEARCH"


def test_strong_sample_needs_no_recorded_decision(store):
    eid = _record(store, _book(trade_count=80))
    assert gate_experiment(store, eid, profile="book_backtest").research_state == "VALIDATED"
