"""Phase 3A PR B (study) — portfolio_construction runner, evidence bundle, regime
slices, health checks, and the frozen portfolio_backtest gate scorecard (§4.4–§4.8)."""

from __future__ import annotations

from datetime import date

import pytest

from app.factor_data.backtest import run_momentum_backtest
from app.factor_data.store import FactorDataStore
from app.research.engine import (
    ExperimentConfig,
    build_evidence_bundle,
    portfolio_construction_runner,
    shape_portfolio_result,
)
from app.research.engine.portfolio_eval import PortfolioHealthError, run_health_checks
from app.research.promotion import PORTFOLIO_BACKTEST_PROFILE, evaluate

from ..factor_data.conftest import build_momentum_frames

_START = date(2018, 7, 1)
_END = date(2020, 12, 31)

_EVIDENCE_TYPES = {
    "equity_curve", "drawdown_curve", "rolling_sharpe", "rolling_vol",
    "rolling_turnover", "sector_weights_over_time", "top_holdings_by_period",
    "rebalance_log",
}


@pytest.fixture
def bt_store(tmp_path) -> FactorDataStore:
    sep, tk = build_momentum_frames()
    s = FactorDataStore(db_path=str(tmp_path / "bt.duckdb"))
    s.ingest_sep(sep)
    s.ingest_tickers(tk)
    yield s
    s.close()


def _store_path(tmp_path) -> str:
    """Build + close a store, returning its path (so the runner can reopen read-only)."""
    sep, tk = build_momentum_frames()
    p = str(tmp_path / "rstore.duckdb")
    s = FactorDataStore(db_path=p)
    s.ingest_sep(sep)
    s.ingest_tickers(tk)
    s.close()
    return p


# ---- evidence bundle (§4.5/§4.9) -------------------------------------------------

def test_build_evidence_bundle_has_standard_set(bt_store: FactorDataStore) -> None:
    report = run_momentum_backtest(bt_store, _START, _END, top_quantile=0.2)
    bundle = build_evidence_bundle(report, store=bt_store)
    assert {a.type for a in bundle} == _EVIDENCE_TYPES
    # every artifact carries non-empty JSON content (the orchestrator checksums it)
    for a in bundle:
        assert a.content and a.filename.endswith(".json")


# ---- shape_portfolio_result: summary, regimes, IS/OOS, stability/capacity --------

def test_shape_summary_and_detail(bt_store: FactorDataStore) -> None:
    report = run_momentum_backtest(bt_store, _START, _END, top_quantile=0.2)
    result = shape_portfolio_result(report, bt_store)
    s = result.metrics_summary
    for key in ("sharpe", "sortino", "calmar", "ulcer_index", "excess_sharpe",
                "excess_max_dd", "turnover_annual", "n_rebalances",
                "oos_is_sharpe_ratio", "rolling_sharpe_positive_frac",
                "avg_weight_change", "max_weight_change",
                "avg_adv_participation", "max_rebalance_notional"):
        assert key in s, f"missing summary key {key}"
    assert s["n_rebalances"] == len(report.holdings)
    # regime slices present (reporting only — §4.6)
    assert set(result.metrics_detail["regimes"]) == {"bull", "bear", "high_vol", "low_vol"}
    assert {a.type for a in result.artifacts} == _EVIDENCE_TYPES


def test_excess_max_dd_sign_convention(bt_store: FactorDataStore) -> None:
    """excess_max_dd >= 0 ⇔ book max DD is no deeper than the benchmark's (both are
    negative fractions) — the gate's 'max DD <= benchmark' criterion."""
    report = run_momentum_backtest(bt_store, _START, _END, top_quantile=0.2)
    s = shape_portfolio_result(report, bt_store).metrics_summary
    assert s["excess_max_dd"] == pytest.approx(
        report.metrics.max_drawdown - report.baseline_metrics.max_drawdown)


# ---- the runner end-to-end via a store path --------------------------------------

@pytest.mark.parametrize("method", ["equal_weight", "inverse_vol", "risk_parity_diagonal"])
def test_portfolio_runner_end_to_end(tmp_path, method: str) -> None:
    path = _store_path(tmp_path)
    config = ExperimentConfig(
        kind="portfolio_construction", name=f"momentum {method}",
        params={"store_path": path, "start": _START.isoformat(), "end": _END.isoformat(),
                "n": 200, "top_quantile": 0.2, "weighting": method},
    )
    result = portfolio_construction_runner(config)
    assert result.metrics_summary["n_rebalances"] > 50
    assert {a.type for a in result.artifacts} == _EVIDENCE_TYPES


def test_runner_requires_window() -> None:
    with pytest.raises(ValueError):
        portfolio_construction_runner(ExperimentConfig(kind="portfolio_construction", name="x"))


# ---- health checks (§4.5 reviewer #11) -------------------------------------------

def test_health_checks_pass_on_good_report(bt_store: FactorDataStore) -> None:
    report = run_momentum_backtest(bt_store, _START, _END, top_quantile=0.2)
    run_health_checks(report, bt_store)  # no raise


def test_health_checks_reject_empty_curve(bt_store: FactorDataStore) -> None:
    report = run_momentum_backtest(bt_store, date(2030, 1, 1), date(2030, 12, 31))
    with pytest.raises(PortfolioHealthError):
        run_health_checks(report, bt_store)


def test_health_checks_reject_duplicate_holdings(bt_store: FactorDataStore) -> None:
    from dataclasses import replace
    report = run_momentum_backtest(bt_store, _START, _END, top_quantile=0.2)
    dup = replace(report.holdings[0], tickers=[*report.holdings[0].tickers,
                                               report.holdings[0].tickers[0]])
    bad = replace(report, holdings=[dup, *report.holdings[1:]])
    with pytest.raises(PortfolioHealthError):
        run_health_checks(bad, bt_store)


# ---- frozen portfolio_backtest gate scorecard (§4.7a) ----------------------------

_PASSING = {
    "sharpe": 1.0, "sortino": 1.2, "excess_sharpe": 0.3, "oos_is_sharpe_ratio": 0.9,
    "rolling_sharpe_positive_frac": 0.7, "excess_max_dd": 0.05, "calmar": 0.9,
    "turnover_annual": 2.0, "max_weight_change": 0.1, "avg_adv_participation": 0.005,
    "n_rebalances": 200,
}


def test_gate_go_on_all_pass_strong_evidence() -> None:
    res = evaluate(_PASSING, PORTFOLIO_BACKTEST_PROFILE)
    assert res.verdict == "GO"
    assert res.research_state == "VALIDATED"
    assert res.confidence_score == 100
    comps = {c.component for c in res.component_scores}
    assert comps == {"statistical", "oos_stability", "drawdown", "turnover", "capacity"}


def test_gate_no_go_when_turnover_too_high() -> None:
    m = {**_PASSING, "turnover_annual": 6.0}   # > 400% ceiling
    res = evaluate(m, PORTFOLIO_BACKTEST_PROFILE)
    assert res.verdict == "NO-GO"
    assert any("turnover" in label for label, ok, _ in res.checks if not ok)


def test_gate_no_go_when_drawdown_worse_than_benchmark() -> None:
    m = {**_PASSING, "excess_max_dd": -0.02}    # book DD deeper than benchmark
    assert evaluate(m, PORTFOLIO_BACKTEST_PROFILE).verdict == "NO-GO"


def test_gate_inconclusive_below_rebalance_floor() -> None:
    m = {**_PASSING, "n_rebalances": 30}        # < 52 evidence floor
    res = evaluate(m, PORTFOLIO_BACKTEST_PROFILE)
    assert res.verdict == "INCONCLUSIVE"
    assert res.research_state == "RESEARCH"


def test_gate_warning_on_thin_but_sufficient_evidence() -> None:
    m = {**_PASSING, "n_rebalances": 80}        # >= 52 floor, < 156 strong
    res = evaluate(m, PORTFOLIO_BACKTEST_PROFILE)
    assert res.verdict == "GO_WARNING"
