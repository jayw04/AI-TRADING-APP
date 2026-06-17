"""FMP → store field mapping/merge (build_fundamentals_frame) — pure, no network."""

from __future__ import annotations

import pandas as pd

from scripts.ingest_fmp import build_fundamentals_frame


def _income() -> pd.DataFrame:
    return pd.DataFrame([
        {"date": "2024-09-28", "period": "FY", "fiscalYear": "2024",
         "filingDate": "2024-11-01", "acceptedDate": "2024-11-01 18:00:00",
         "revenue": 391035000000.0, "grossProfit": 180683000000.0,
         "operatingIncome": 123216000000.0, "ebitda": 134661000000.0,
         "netIncome": 93736000000.0, "weightedAverageShsOutDil": 15408095000.0},
    ])


def test_build_merges_and_renames_to_store_columns() -> None:
    income = _income()
    balance = pd.DataFrame([{"date": "2024-09-28", "period": "FY",
                             "totalDebt": 106629000000.0,
                             "totalStockholdersEquity": 56950000000.0,
                             "totalAssets": 364980000000.0}])
    cashflow = pd.DataFrame([{"date": "2024-09-28", "period": "FY",
                              "freeCashFlow": 108807000000.0}])
    km = pd.DataFrame([{"date": "2024-09-28", "period": "FY",
                        "enterpriseValue": 3400000000000.0}])

    out = build_fundamentals_frame("AAPL", income, balance, cashflow, km)
    assert len(out) == 1
    row = out.iloc[0]
    assert row["ticker"] == "AAPL"
    assert row["period_end"] == "2024-09-28"
    assert row["accepted_date"] == "2024-11-01 18:00:00"
    assert row["net_income"] == 93736000000.0
    assert row["total_debt"] == 106629000000.0
    assert row["free_cash_flow"] == 108807000000.0
    assert row["enterprise_value"] == 3400000000000.0
    assert row["shares_diluted"] == 15408095000.0


def test_missing_statement_leaves_columns_null() -> None:
    # No balance sheet for this ticker → total_* columns present but NaN.
    out = build_fundamentals_frame("XYZ", _income(), pd.DataFrame(), pd.DataFrame(), pd.DataFrame())
    assert len(out) == 1
    assert "total_debt" in out.columns
    assert pd.isna(out.iloc[0]["total_debt"])
    assert pd.isna(out.iloc[0]["enterprise_value"])
    assert out.iloc[0]["revenue"] == 391035000000.0  # income fields still mapped


def test_empty_income_yields_empty_frame() -> None:
    out = build_fundamentals_frame("AAPL", pd.DataFrame(), pd.DataFrame(), pd.DataFrame(), pd.DataFrame())
    assert out.empty
