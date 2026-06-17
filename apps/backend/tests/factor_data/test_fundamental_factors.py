"""Value/Quality fundamental factors: PIT merge + ratio computation (R2)."""

from __future__ import annotations

import numpy as np
import pandas as pd

from app.factor_data.factors.fundamental import (
    FUNDAMENTAL_FACTORS,
    build_fundamental_factor_matrices,
    compute_factor_values,
    latest_known,
)


def _fundamentals() -> pd.DataFrame:
    rows = []
    for tk, base in (("AAA", 1.0), ("BBB", 2.0)):
        for yr, acc in (("2021", "2022-03-01"), ("2022", "2023-03-01")):
            rows.append({
                "ticker": tk, "accepted_date": acc, "period_end": f"{yr}-12-31",
                "revenue": 1000 * base, "gross_profit": 400 * base,
                "operating_income": 200 * base, "ebitda": 250 * base,
                "net_income": 100 * base, "free_cash_flow": 120 * base,
                "total_debt": 300 * base, "total_equity": 500 * base,
                "total_assets": 1000 * base, "shares_diluted": 100.0,
                "enterprise_value": 9e9,
            })
    return pd.DataFrame(rows)


_REBAL = [pd.Timestamp("2022-06-30"), pd.Timestamp("2023-06-30")]


def test_latest_known_is_point_in_time() -> None:
    pit = latest_known(_fundamentals(), _REBAL)
    aaa_2022 = pit[(pit["ticker"] == "AAA") & (pit["date"] == "2022-06-30")]
    # As of 2022-06-30 only the 2021 statement (accepted 2022-03-01) is knowable.
    assert len(aaa_2022) == 1
    assert aaa_2022.iloc[0]["period_end"] == "2021-12-31"
    # As of 2023-06-30 the 2022 statement is now the latest known.
    aaa_2023 = pit[(pit["ticker"] == "AAA") & (pit["date"] == "2023-06-30")]
    assert aaa_2023.iloc[0]["period_end"] == "2022-12-31"


def test_no_statement_before_first_filing_is_dropped() -> None:
    pit = latest_known(_fundamentals(), [pd.Timestamp("2021-01-01"), *_REBAL])
    assert (pit["date"] == pd.Timestamp("2021-01-01")).sum() == 0  # nothing filed yet


def test_compute_factor_values_ratios_and_market_cap() -> None:
    close = pd.DataFrame(
        {"AAA": [50.0, 60.0], "BBB": [10.0, 12.0]},
        index=[pd.Timestamp("2022-06-30"), pd.Timestamp("2023-06-30")],
    )
    vals = compute_factor_values(latest_known(_fundamentals(), _REBAL), close)
    aaa = vals[(vals["ticker"] == "AAA") & (vals["date"] == "2022-06-30")].iloc[0]
    assert aaa["market_cap"] == 50.0 * 100.0  # close × shares_diluted
    assert np.isclose(aaa["earnings_yield"], 100.0 / 5000.0)  # net_income / market_cap
    assert np.isclose(aaa["roe"], 100.0 / 500.0)  # net_income / total_equity
    assert aaa["debt_to_equity"] < 0  # negated (less leverage = better)
    assert np.isclose(aaa["roic"], 200.0 / (300.0 + 500.0))  # opinc / (debt+equity)


def test_safe_ratio_negative_denominator_is_nan() -> None:
    f = _fundamentals()
    f.loc[f["ticker"] == "AAA", "total_equity"] = -10.0  # distressed → non-positive denom
    close = pd.DataFrame({"AAA": [50.0], "BBB": [10.0]}, index=[pd.Timestamp("2022-06-30")])
    vals = compute_factor_values(latest_known(f, [pd.Timestamp("2022-06-30")]), close)
    aaa = vals[vals["ticker"] == "AAA"].iloc[0]
    assert pd.isna(aaa["roe"])  # never ±inf on a non-positive denominator


def test_build_matrices_shape_and_names() -> None:
    close = pd.DataFrame(
        {"AAA": [50.0, 60.0], "BBB": [10.0, 12.0]},
        index=_REBAL,
    )
    mats = build_fundamental_factor_matrices(_fundamentals(), close, _REBAL)
    assert set(mats) == set(FUNDAMENTAL_FACTORS)
    ey = mats["earnings_yield"]
    assert list(ey.index) == _REBAL
    assert set(ey.columns) == {"AAA", "BBB"}


def test_empty_fundamentals_yields_empty_matrices() -> None:
    mats = build_fundamental_factor_matrices(pd.DataFrame(), pd.DataFrame(), _REBAL)
    assert set(mats) == set(FUNDAMENTAL_FACTORS)
    assert all(m.empty for m in mats.values())
