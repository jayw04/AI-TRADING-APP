"""Synthetic factor-data fixture for P9 §1 tests.

The store is built at test time from **fabricated** prices for fake tickers — no
raw Sharadar bytes are committed (raw-table re-export is disallowed, ADR 0018 §6;
the §0 licensing finding). Fabricating the slice also makes the tests
deterministic and DuckDB-version-proof (no committed binary), while exercising
exactly the survivorship/PIT properties that matter.

The synthetic universe (per-day dollar volume = close × volume):
  BIGA  alive whole window, close 100  vol 10M  -> 1.0e9/day
  NEW1  FIRST PRICED 2010-06-01,  close 200  vol  8M -> 1.6e9/day (added later)
  DEAD1 DELISTED 2008-09-15,      close  50  vol 30M -> 1.5e9/day (since removed)
  BIGB  alive whole window, close  80  vol  5M  -> 4.0e8/day
  MIDC  alive whole window, close  30  vol  3M  -> 9.0e7/day
"""

from __future__ import annotations

from datetime import date

import pandas as pd
import pytest

from app.factor_data.store import FactorDataStore

# (ticker, close, volume, firstpricedate, lastpricedate)
_SPEC = [
    ("BIGA", 100, 10_000_000, date(1999, 1, 1), date(2026, 1, 1)),
    ("NEW1", 200, 8_000_000, date(2010, 6, 1), date(2026, 1, 1)),
    ("DEAD1", 50, 30_000_000, date(1999, 1, 1), date(2008, 9, 15)),
    ("BIGB", 80, 5_000_000, date(1999, 1, 1), date(2026, 1, 1)),
    ("MIDC", 30, 3_000_000, date(1999, 1, 1), date(2026, 1, 1)),
]

_WINDOW_START = pd.Timestamp("2000-01-03")
_WINDOW_END = pd.Timestamp("2020-12-31")


def _build_frames() -> tuple[pd.DataFrame, pd.DataFrame]:
    bdays = pd.bdate_range(_WINDOW_START, _WINDOW_END)
    sep_rows, tk_rows = [], []
    for ticker, close, vol, first, last in _SPEC:
        for d in bdays:
            if d.date() < first or d.date() > last:
                continue
            sep_rows.append(
                dict(
                    ticker=ticker,
                    date=d.strftime("%Y-%m-%d"),
                    open=close,
                    high=close,
                    low=close,
                    close=close,
                    volume=vol,
                    closeadj=close * 0.9,  # adjusted differs from raw, deterministically
                    closeunadj=close,
                    lastupdated="2026-01-01",
                )
            )
        tk_rows.append(
            dict(
                ticker=ticker,
                name=f"{ticker} Inc",
                exchange="NYSE",
                category="Domestic Common Stock",
                isdelisted="Y" if last < date(2020, 1, 1) else "N",
                firstpricedate=first.strftime("%Y-%m-%d"),
                lastpricedate=last.strftime("%Y-%m-%d"),
                lastupdated="2026-01-01",
            )
        )
    return pd.DataFrame(sep_rows), pd.DataFrame(tk_rows)


@pytest.fixture
def store(tmp_path) -> FactorDataStore:
    """A populated DuckDB factor-data store on a throwaway path."""
    sep, tickers = _build_frames()
    s = FactorDataStore(db_path=str(tmp_path / "factor_test.duckdb"))
    s.ingest_sep(sep)
    s.ingest_tickers(tickers)
    yield s
    s.close()


@pytest.fixture
def synthetic_frames() -> tuple[pd.DataFrame, pd.DataFrame]:
    """Raw synthetic (sep, tickers) frames for ingest/idempotency tests."""
    return _build_frames()
