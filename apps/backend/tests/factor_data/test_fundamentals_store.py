"""Fundamentals table: idempotent ingest + point-in-time get_fundamentals (R2)."""

from __future__ import annotations

from datetime import date

import pandas as pd

from app.factor_data.store import FactorDataStore


def _frame() -> pd.DataFrame:
    """Two AAPL annual periods, knowable on their accepted_date."""
    return pd.DataFrame([
        {"ticker": "AAPL", "period": "FY", "fiscal_year": "2023",
         "period_end": "2023-09-30", "filing_date": "2023-11-03",
         "accepted_date": "2023-11-03 18:00:00", "revenue": 383285000000.0,
         "net_income": 96995000000.0, "total_equity": 62146000000.0,
         "enterprise_value": 2800000000000.0},
        {"ticker": "AAPL", "period": "FY", "fiscal_year": "2024",
         "period_end": "2024-09-28", "filing_date": "2024-11-01",
         "accepted_date": "2024-11-01 18:00:00", "revenue": 391035000000.0,
         "net_income": 93736000000.0, "total_equity": 56950000000.0,
         "enterprise_value": 3400000000000.0},
    ])


def test_ingest_and_get_newest_first(store: FactorDataStore) -> None:
    store.ingest_fundamentals(_frame())
    df = store.get_fundamentals("AAPL")
    assert len(df) == 2
    assert list(df["period_end"].astype(str)) == ["2024-09-28", "2023-09-30"]  # newest first
    assert store.row_count("fundamentals") == 2


def test_pit_filter_hides_not_yet_filed(store: FactorDataStore) -> None:
    store.ingest_fundamentals(_frame())
    # As of 2024-06-01, only the 2023 statement (accepted 2023-11-03) is knowable.
    df = store.get_fundamentals("AAPL", as_of=date(2024, 6, 1))
    assert len(df) == 1
    assert str(df.iloc[0]["period_end"])[:10] == "2023-09-30"
    # Before any filing → nothing knowable.
    assert store.get_fundamentals("AAPL", as_of=date(2023, 1, 1)).empty
    # After both → both.
    assert len(store.get_fundamentals("AAPL", as_of=date(2025, 1, 1))) == 2


def test_pit_falls_back_to_filing_date_when_accepted_missing(store: FactorDataStore) -> None:
    f = _frame()
    f["accepted_date"] = None  # only filing_date available
    store.ingest_fundamentals(f)
    df = store.get_fundamentals("AAPL", as_of=date(2024, 6, 1))
    assert len(df) == 1  # filing_date 2023-11-03 <= as_of; 2024-11-01 not yet


def test_ingest_is_idempotent(store: FactorDataStore) -> None:
    store.ingest_fundamentals(_frame())
    store.ingest_fundamentals(_frame())  # same (ticker, period, period_end) → upsert
    assert store.row_count("fundamentals") == 2


def test_period_filter(store: FactorDataStore) -> None:
    f = _frame()
    f.loc[len(f)] = {"ticker": "AAPL", "period": "Q4", "fiscal_year": "2024",
                     "period_end": "2024-09-28", "filing_date": "2024-11-01",
                     "accepted_date": "2024-11-01 18:00:00", "revenue": 94930000000.0}
    store.ingest_fundamentals(f)
    assert len(store.get_fundamentals("AAPL", period="FY")) == 2
    assert len(store.get_fundamentals("AAPL", period="Q4")) == 1
