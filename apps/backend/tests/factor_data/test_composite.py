"""Composite multi-factor engine + factor-agnostic backtest (P12 §3)."""

from __future__ import annotations

from datetime import date

import pandas as pd
import pytest

from app.factor_data.backtest import run_momentum_backtest
from app.factor_data.factors.composite import composite_scores, factor_zscores
from app.factor_data.factors.engine import FactorUnavailable, momentum_scores
from app.factor_data.store import FactorDataStore


# ---- composite: momentum path (reuse the 25-name momentum fixture) -------------

def test_composite_momentum_only_matches_momentum_order(momentum_store) -> None:
    as_of = date(2020, 6, 1)
    comp = composite_scores(momentum_store, as_of, factors=["momentum"], n=25, min_names=20)
    mom = momentum_scores(momentum_store, as_of, n=25, min_names=20)
    assert list(comp.index) == list(mom.index)  # same ranking (best momentum first)


def test_composite_impute_missing_factor_preserves_momentum_order(momentum_store) -> None:
    # roe has no fundamentals here -> all missing -> impute z=0 -> composite == 0.5*z_mom.
    as_of = date(2020, 6, 1)
    comp = composite_scores(momentum_store, as_of, factors=["momentum", "roe"], n=25,
                            min_names=20, missing="impute")
    mom = momentum_scores(momentum_store, as_of, n=25, min_names=20)
    assert list(comp.index) == list(mom.index)


def test_composite_drop_when_factor_entirely_missing_raises(momentum_store) -> None:
    # missing='drop' + a fully-absent factor -> every name dropped -> FactorUnavailable.
    with pytest.raises(FactorUnavailable):
        composite_scores(momentum_store, date(2020, 6, 1), factors=["momentum", "roe"],
                         n=25, min_names=20, missing="drop")


def test_composite_thin_universe_raises(momentum_store) -> None:
    with pytest.raises(FactorUnavailable):
        composite_scores(momentum_store, date(2020, 6, 1), factors=["momentum"], n=25,
                         min_names=99)


def test_composite_rejects_unknown_factor(momentum_store) -> None:
    with pytest.raises(ValueError, match="unknown factor"):
        composite_scores(momentum_store, date(2020, 6, 1), factors=["bogus"], n=25, min_names=2)


# ---- composite: value/quality path (seed a tiny prices + fundamentals store) ----

@pytest.fixture
def fund_store(tmp_path) -> FactorDataStore:
    days = [d.date() for d in pd.bdate_range("2021-01-01", periods=120)]
    specs = {"AAA": 50.0, "BBB": 30.0, "CCC": 20.0, "DDD": 10.0}  # net_income (total_equity=100 -> roe)
    sep, tk, fund = [], [], []
    for t, ni in specs.items():
        for d in days:
            sep.append(dict(ticker=t, date=d.strftime("%Y-%m-%d"), open=100, high=100, low=100,
                            close=100, volume=2_000_000, closeadj=100.0, closeunadj=100.0,
                            lastupdated="2026-01-01"))
        tk.append(dict(ticker=t, name=t, exchange="NYSE", category="Domestic Common Stock",
                       isdelisted="N", firstpricedate="2020-01-01", lastpricedate="2026-01-01",
                       lastupdated="2026-01-01"))
        fund.append(dict(ticker=t, period="FY", fiscal_year="2020", period_end="2020-12-31",
                         filing_date="2021-02-01", accepted_date="2021-02-01 00:00:00",
                         revenue=1000.0, gross_profit=400.0, operating_income=200.0, ebitda=300.0,
                         net_income=ni, free_cash_flow=ni, total_debt=10.0, total_equity=100.0,
                         total_assets=500.0, shares_diluted=1_000_000.0, enterprise_value=1.0,
                         lastupdated="2026-01-01"))
    s = FactorDataStore(db_path=str(tmp_path / "fund.duckdb"))
    s.ingest_sep(pd.DataFrame(sep))
    s.ingest_tickers(pd.DataFrame(tk))
    s.ingest_fundamentals(pd.DataFrame(fund))
    yield s
    s.close()


def test_composite_roe_ranks_by_fundamentals(fund_store) -> None:
    # roe = net_income / total_equity (100): AAA(0.5) > BBB(0.3) > CCC(0.2) > DDD(0.1).
    comp = composite_scores(fund_store, date(2021, 6, 1), factors=["roe"], n=4, min_names=3)
    assert list(comp.index) == ["AAA", "BBB", "CCC", "DDD"]


def test_factor_zscores_matrix_shape(fund_store) -> None:
    # tickers × factors z-score matrix (the correlation-matrix input).
    z = factor_zscores(fund_store, date(2021, 6, 1), factors=["momentum", "roe"], n=4, min_names=3)
    assert list(z.columns) == ["momentum", "roe"]
    assert not z["roe"].isna().all()  # roe present from fundamentals
    assert z["roe"].idxmax() == "AAA"  # highest roe


# ---- factor-agnostic backtest --------------------------------------------------

def test_backtest_default_is_momentum_unchanged(momentum_store) -> None:
    # score_fn=None must be byte-identical to the existing momentum backtest.
    start, end = date(2020, 1, 1), date(2020, 12, 31)
    a = run_momentum_backtest(momentum_store, start, end, n=25, min_names=20)
    b = run_momentum_backtest(momentum_store, start, end, n=25, min_names=20, score_fn=None)
    assert a.metrics == b.metrics
    assert a.equity_curve == b.equity_curve


def test_backtest_accepts_composite_score_fn(momentum_store) -> None:
    start, end = date(2020, 1, 1), date(2020, 12, 31)

    def score(store, d):
        return composite_scores(store, d, factors=["momentum"], n=25, min_names=20)

    rep = run_momentum_backtest(momentum_store, start, end, n=25, min_names=20, score_fn=score)
    assert rep.rebalances  # ran
    # composite(momentum-only) == momentum, so it reproduces the momentum book.
    base = run_momentum_backtest(momentum_store, start, end, n=25, min_names=20)
    assert rep.metrics == base.metrics
