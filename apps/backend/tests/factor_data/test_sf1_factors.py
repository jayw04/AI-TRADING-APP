"""SF1-backed value/quality factors (P14 Factor Lab, ADR 0023) — pure-function tests."""

from __future__ import annotations

from datetime import date

import pandas as pd
import pytest

from app.factor_data.factors.sf1 import (
    SF1_FACTORS,
    sf1_factor_frame,
    sf1_factor_raw,
)
from app.factor_data.store import FactorDataStore


def _asof_frame() -> pd.DataFrame:
    """Two names, the `store.get_sf1_asof` shape (indexed by ticker)."""
    return pd.DataFrame(
        {
            "marketcap": [1000.0, 500.0],
            "netinc": [100.0, 25.0],     # earnings yield 0.10 vs 0.05 -> AAA cheaper
            "fcf": [80.0, 10.0],
            "revenue": [2000.0, 400.0],
            "equity": [600.0, 250.0],   # book yield 0.60 vs 0.50 -> AAA cheaper
            "roe": [0.25, 0.10],
            "roic": [0.18, 0.07],
            "gp": [600.0, 80.0],
            "assets": [1200.0, 800.0],   # gross profitability 0.50 vs 0.10
            "de": [0.4, 1.8],            # low_leverage -0.4 vs -1.8 -> AAA better
        },
        index=pd.Index(["AAA", "BBB"], name="ticker"),
    )


def test_value_yields_and_quality_signs():
    f = sf1_factor_frame(_asof_frame())
    assert set(SF1_FACTORS).issubset(f.columns)
    assert f.loc["AAA", "sf1_earnings_yield"] == pytest.approx(0.10)
    assert f.loc["BBB", "sf1_earnings_yield"] == pytest.approx(0.05)
    assert f.loc["AAA", "sf1_sales_yield"] == pytest.approx(2.0)
    assert f.loc["AAA", "sf1_gross_profitability"] == pytest.approx(0.5)
    # low leverage is the negative of debt/equity (less debt = higher signal)
    assert f.loc["AAA", "sf1_low_leverage"] == pytest.approx(-0.4)
    assert f.loc["AAA", "sf1_low_leverage"] > f.loc["BBB", "sf1_low_leverage"]
    # higher = more attractive: cheaper + higher-quality AAA beats BBB on every factor
    for col in SF1_FACTORS:
        assert f.loc["AAA", col] > f.loc["BBB", col]


def test_non_positive_marketcap_yields_nan_not_inf():
    df = _asof_frame()
    df.loc["BBB", "marketcap"] = 0.0
    f = sf1_factor_frame(df)
    assert pd.isna(f.loc["BBB", "sf1_earnings_yield"])  # /0 -> NaN, never inf


def test_empty_frame_in_empty_out():
    assert sf1_factor_frame(pd.DataFrame()).empty


def test_sf1_factor_raw_unknown_factor_raises(tmp_path):
    s = FactorDataStore(db_path=str(tmp_path / "sf1raw.duckdb"))
    try:
        with pytest.raises(ValueError):
            sf1_factor_raw(s, date(2023, 6, 30), ["AAA"], ["not_a_factor"])
    finally:
        s.close()
