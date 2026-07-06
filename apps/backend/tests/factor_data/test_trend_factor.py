"""TREND-001 factor engine (factors/trend.py) — in-trend signal + participation weights."""

from __future__ import annotations

from datetime import date

import pandas as pd
import pytest

from app.factor_data.factors.trend import in_trend_names, trend_scores, trend_weights
from app.factor_data.store import FactorDataStore

_AS_OF = date(2020, 3, 2)


def _store(tmp_path) -> FactorDataStore:
    """24 names: even indices rise (in-trend), odd indices fall (out-of-trend)."""
    bdays = pd.bdate_range("2019-10-01", "2020-02-28")  # ~110 trading days (> sma 20)
    sep, tk = [], []
    for i in range(24):
        ticker = f"T{i:02d}"
        rising = i % 2 == 0
        price = 50.0 if rising else 150.0
        step = 1.0 if rising else -1.0
        for d in bdays:
            price = max(price + step, 1.0)
            sep.append(dict(ticker=ticker, date=d.strftime("%Y-%m-%d"), open=price, high=price,
                            low=price, close=price, volume=1_000_000, closeadj=price,
                            closeunadj=price, lastupdated="2026-01-01"))
        tk.append(dict(ticker=ticker, name=ticker, exchange="NYSE", category="Domestic Common Stock",
                       sector="X", industry="Y", isdelisted="N", firstpricedate="2019-01-01",
                       lastpricedate="2026-01-01", lastupdated="2026-01-01"))
    s = FactorDataStore(db_path=str(tmp_path / "trend.duckdb"))
    s.ingest_sep(pd.DataFrame(sep))
    s.ingest_tickers(pd.DataFrame(tk))
    return s


def test_in_trend_names_filters_rising(tmp_path) -> None:
    s = _store(tmp_path)
    try:
        universe, in_trend = in_trend_names(s, _AS_OF, n=30, sma_days=20)
        assert len(universe) == 24
        assert set(in_trend) == {f"T{i:02d}" for i in range(0, 24, 2)}  # the rising names
    finally:
        s.close()


def test_trend_weights_one_over_universe_for_in_trend(tmp_path) -> None:
    s = _store(tmp_path)
    try:
        w = trend_weights(s, _AS_OF, n=30, sma_days=20)
        assert len(w) == 12 and all(abs(v - 1 / 24) < 1e-9 for v in w.values())  # gross = 12/24
    finally:
        s.close()


def test_trend_scores_flags_in_trend(tmp_path) -> None:
    s = _store(tmp_path)
    try:
        df = trend_scores(s, _AS_OF, n=30, sma_days=20)
        assert set(df.columns) == {"score"}
        assert df.loc["T00", "score"] == 1.0 and df.loc["T01", "score"] == 0.0
        assert df["score"].sum() == 12.0
    finally:
        s.close()


def test_trend_scores_thin_cross_section_raises(tmp_path) -> None:
    from app.factor_data.factors.engine import FactorUnavailable
    s = _store(tmp_path)
    try:
        with pytest.raises(FactorUnavailable):
            trend_scores(s, _AS_OF, n=5, sma_days=20)  # < min_names
    finally:
        s.close()
