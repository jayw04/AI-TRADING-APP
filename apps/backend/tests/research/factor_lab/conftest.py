"""Synthetic volatile store for Factor Lab runner/registry tests.

The conftest factor stores use constant-growth prices (zero return variance), which can't
exercise low-vol scoring or a realistic backtest. This builds a deterministic store with
24 random-walk names of differing drift/volatility and ~2.5y of history — enough for the
252-day momentum/vol lookbacks and a multi-month backtest window.
"""

from __future__ import annotations

import random

import pandas as pd
import pytest

from app.factor_data.store import FactorDataStore

_N = 24
_START = pd.Timestamp("2018-01-01")
_END = pd.Timestamp("2020-06-30")


def _build() -> tuple[pd.DataFrame, pd.DataFrame]:
    bdays = pd.bdate_range(_START, _END)
    rng = random.Random(17)
    sep, tk = [], []
    for i in range(_N):
        ticker = f"VOL{i:02d}"
        drift = 0.0002 + 0.00004 * i          # mild spread in trend
        sigma = 0.006 + 0.001 * i             # ascending realized vol → orderable low-vol cross-section
        price = 100.0
        for d in bdays:
            price *= 1.0 + rng.gauss(drift, sigma)
            price = max(price, 1.0)
            sep.append(dict(ticker=ticker, date=d.strftime("%Y-%m-%d"),
                            open=price, high=price, low=price, close=price,
                            volume=2_000_000, closeadj=price, closeunadj=price,
                            lastupdated="2026-01-01"))
        tk.append(dict(ticker=ticker, name=f"{ticker} Inc", exchange="NYSE",
                       category="Domestic Common Stock", isdelisted="N",
                       firstpricedate="2017-01-01", lastpricedate="2026-01-01",
                       lastupdated="2026-01-01"))
    return pd.DataFrame(sep), pd.DataFrame(tk)


@pytest.fixture
def volatile_store(tmp_path) -> FactorDataStore:
    sep, tickers = _build()
    s = FactorDataStore(db_path=str(tmp_path / "factorlab.duckdb"))
    s.ingest_sep(sep)
    s.ingest_tickers(tickers)
    yield s
    s.close()


def _build_sectored() -> tuple[pd.DataFrame, pd.DataFrame]:
    """30 random-walk names across 5 sectors (6 each), ~2.5y — enough for the sector
    ranking (≥20 sectored names), the 252d momentum lookback, and a multi-month
    backtest. Each sector gets its own drift so the cross-sector ranking is orderable."""
    bdays = pd.bdate_range(_START, _END)
    rng = random.Random(23)
    sectors = ["TECH", "ENERGY", "HEALTH", "FIN", "UTIL"]
    sep, tk = [], []
    for si, sector in enumerate(sectors):
        drift = 0.0001 + 0.00010 * si      # sector-level trend spread
        for j in range(6):
            ticker = f"{sector[:2]}{j:02d}"
            sigma = 0.008 + 0.0008 * j
            price = 100.0
            for d in bdays:
                price *= 1.0 + rng.gauss(drift, sigma)
                price = max(price, 1.0)
                sep.append(dict(ticker=ticker, date=d.strftime("%Y-%m-%d"),
                                open=price, high=price, low=price, close=price,
                                volume=2_000_000, closeadj=price, closeunadj=price,
                                lastupdated="2026-01-01"))
            tk.append(dict(ticker=ticker, name=f"{ticker} Inc", exchange="NYSE",
                           category="Domestic Common Stock", sector=sector, industry="I",
                           isdelisted="N", firstpricedate="2017-01-01",
                           lastpricedate="2026-01-01", lastupdated="2026-01-01"))
    return pd.DataFrame(sep), pd.DataFrame(tk)


@pytest.fixture
def sectored_store(tmp_path) -> FactorDataStore:
    sep, tickers = _build_sectored()
    s = FactorDataStore(db_path=str(tmp_path / "factorlab_sector.duckdb"))
    s.ingest_sep(sep)
    s.ingest_tickers(tickers)
    yield s
    s.close()
