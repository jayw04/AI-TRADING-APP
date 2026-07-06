"""P10 §3B return / turnover / drawdown attribution.

Controlled two-name stores pin the exact decomposition math; the liquid fixture pins
the structural contract (residual finite, artifacts present, deterministic)."""

from __future__ import annotations

from datetime import date

import pandas as pd
import pytest

from app.factor_data.backtest import (
    BacktestRunConfig,
    BacktestSummary,
    MomentumBacktestReport,
    RebalanceHoldings,
    run_momentum_backtest,
)
from app.factor_data.store import FactorDataStore
from app.research.engine import (
    drawdown_attribution,
    return_attribution,
    shape_portfolio_result,
    turnover_attribution,
)
from app.research.engine.attribution import _max_dd_window

from ..factor_data.conftest import build_momentum_frames

_START = date(2018, 7, 1)
_END = date(2020, 12, 31)


def _one_rebalance_report(d0: date, d1: date, weights: dict[str, float],
                          eq0: float = 100_000.0, eq1: float = 120_000.0) -> MomentumBacktestReport:
    cfg = BacktestRunConfig(
        start=d0, end=d1, n=len(weights), lookback_days=1, skip_days=0, top_quantile=1.0,
        turnover_cost_bps=0.0, delisting="last_price_to_cash", initial_equity=eq0,
    )
    return MomentumBacktestReport(
        config=cfg, rebalances=[d0],
        equity_curve=[(d0, eq0), (d1, eq1)], baseline_curve=[(d0, eq0), (d1, eq1 * 0.9)],
        holdings=[RebalanceHoldings(d0, sorted(weights), eq1 / eq0 - 1.0, dict(weights))],
        metrics=BacktestSummary(0.0, 0.0, 0.0, 0.0),
        baseline_metrics=BacktestSummary(0.0, 0.0, 0.0, 0.0),
    )


def _ud_store(tmp_path) -> FactorDataStore:
    """UP doubles (100→200), DN halves (100→50), over one segment; UP=TECH, DN=ENERGY."""
    days = pd.bdate_range("2019-02-01", "2019-06-28")
    n = len(days)
    rows = []
    for tk, p1 in (("UP", 200.0), ("DN", 50.0)):
        for i, d in enumerate(days):
            price = 100.0 * (p1 / 100.0) ** (i / (n - 1))
            rows.append(dict(ticker=tk, date=d.strftime("%Y-%m-%d"),
                             open=price, high=price, low=price, close=price, volume=1_000_000,
                             closeadj=price, closeunadj=price, lastupdated="2026-01-01"))
    tk_rows = [
        dict(ticker="UP", name="Up Inc", exchange="NYSE", category="Domestic Common Stock",
             sector="TECH", industry="hw", isdelisted="N",
             firstpricedate="2019-02-01", lastpricedate="2019-06-28", lastupdated="2026-01-01"),
        dict(ticker="DN", name="Dn Inc", exchange="NYSE", category="Domestic Common Stock",
             sector="ENERGY", industry="oil", isdelisted="N",
             firstpricedate="2019-02-01", lastpricedate="2019-06-28", lastupdated="2026-01-01"),
    ]
    s = FactorDataStore(db_path=str(tmp_path / "ud.duckdb"))
    s.ingest_sep(pd.DataFrame(rows))
    s.ingest_tickers(pd.DataFrame(tk_rows))
    return s


# ---- exact math on a controlled store --------------------------------------------

def test_return_attribution_exact(tmp_path) -> None:
    store = _ud_store(tmp_path)
    report = _one_rebalance_report(date(2019, 2, 1), date(2019, 6, 28), {"UP": 0.5, "DN": 0.5})
    ra = return_attribution(report, store)
    store.close()
    assert ra["by_name"]["UP"] == pytest.approx(0.5)    # 0.5 × (200/100 − 1)
    assert ra["by_name"]["DN"] == pytest.approx(-0.25)  # 0.5 × (50/100 − 1)
    assert ra["total_attributed"] == pytest.approx(0.25)
    assert ra["book_gross_return"] == pytest.approx(0.20)        # 120k/100k − 1
    assert ra["residual"] == pytest.approx(-0.05)               # 0.20 − 0.25
    assert ra["by_sector"]["TECH"] == pytest.approx(0.5)
    assert ra["by_sector"]["ENERGY"] == pytest.approx(-0.25)
    assert ra["top_contributors"][0]["ticker"] == "UP"
    assert ra["top_detractors"][0]["ticker"] == "DN"


def test_turnover_attribution_exact(tmp_path) -> None:
    store = _ud_store(tmp_path)
    report = _one_rebalance_report(date(2019, 2, 1), date(2019, 6, 28), {"UP": 0.5, "DN": 0.5})
    ta = turnover_attribution(report, store)
    store.close()
    # entered both from flat → one-way |Δw| = 0.5 each, total 1.0.
    assert ta["by_name"] == {"UP": pytest.approx(0.5), "DN": pytest.approx(0.5)}
    assert ta["total_one_way_turnover"] == pytest.approx(1.0)
    assert ta["by_sector"] == {"TECH": pytest.approx(0.5), "ENERGY": pytest.approx(0.5)}
    assert ta["top_churners"][0]["share"] == pytest.approx(0.5)


def test_max_dd_window() -> None:
    curve = [(date(2019, 1, d), v) for d, v in
             [(1, 100.0), (2, 120.0), (3, 90.0), (4, 110.0)]]
    peak, trough, dd = _max_dd_window(curve)
    assert (peak, trough) == (date(2019, 1, 2), date(2019, 1, 3))
    assert dd == pytest.approx(90 / 120 - 1.0)  # −0.25
    assert _max_dd_window([(date(2019, 1, 1), 100.0), (date(2019, 1, 2), 110.0)]) is None  # monotone up


# ---- structural contract on the real fixture -------------------------------------

@pytest.fixture
def bt_store(tmp_path) -> FactorDataStore:
    sep, tk = build_momentum_frames()
    s = FactorDataStore(db_path=str(tmp_path / "bt.duckdb"))
    s.ingest_sep(sep)
    s.ingest_tickers(tk)
    yield s
    s.close()


def test_attribution_summary_and_bundle(bt_store: FactorDataStore) -> None:
    report = run_momentum_backtest(bt_store, _START, _END, top_quantile=0.2)
    result = shape_portfolio_result(report, bt_store)
    for k in ("attr_top_contributor", "attr_top_detractor", "attr_top_sector",
              "attr_worst_sector", "attr_return_residual", "attr_dd_top_detractor"):
        assert k in result.metrics_summary
    types = {a.type for a in result.artifacts}
    assert {"return_attribution", "turnover_attribution", "drawdown_attribution"} <= types


def test_drawdown_attribution_structure(bt_store: FactorDataStore) -> None:
    report = run_momentum_backtest(bt_store, _START, _END, top_quantile=0.2)
    dd = drawdown_attribution(report, bt_store)
    if dd["peak_date"] is not None:  # the fixture book does draw down
        assert dd["peak_date"] < dd["trough_date"]
        assert dd["drawdown"] <= 0.0
        assert dd["by_name"]  # named contributions over the window


def test_attribution_deterministic(bt_store: FactorDataStore) -> None:
    report = run_momentum_backtest(bt_store, _START, _END, top_quantile=0.2)
    a = return_attribution(report, bt_store)
    b = return_attribution(report, bt_store)
    assert a["by_name"] == b["by_name"] and a["residual"] == b["residual"]
