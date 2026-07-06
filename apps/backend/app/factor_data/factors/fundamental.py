"""Value & Quality fundamental factors (P10 R2).

Each factor is a cross-sectional signal where **higher = more attractive (long)**,
consistent with the price-factor convention in ``scripts/factor_research.py``. They
are computed **point-in-time**: on each rebalance date a ticker uses its
latest-known annual fundamentals (``accepted_date <= rebalance``, via ``merge_asof``)
joined with that date's price for market cap — no look-ahead.

Value (cheaper = higher signal): earnings yield, FCF yield, sales yield.
Quality (better business = higher signal): ROE, gross profitability
(Novy-Marx: gross profit / total assets), ROIC, negative debt/equity.

Market-cap-based value ratios are preferred over the stored ``enterprise_value``
(which is FMP's value *as of the filing*, stale at a later rebalance); market cap
uses the **current** price × latest-known diluted shares.

Pure functions over DataFrames (no store/network) so they unit-test cleanly; the
store loader is a thin wrapper.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

# factor name -> (numerator col, denominator col, sign). Market-cap ratios use the
# synthesized "market_cap" column; balance-sheet ratios use stored fields.
_VALUE = {
    "earnings_yield": ("net_income", "market_cap", +1.0),
    "fcf_yield": ("free_cash_flow", "market_cap", +1.0),
    "sales_yield": ("revenue", "market_cap", +1.0),
}
_QUALITY = {
    "roe": ("net_income", "total_equity", +1.0),
    "gross_profitability": ("gross_profit", "total_assets", +1.0),
    "roic": ("operating_income", "invested_capital", +1.0),
    "debt_to_equity": ("total_debt", "total_equity", -1.0),  # negate: less leverage = better
}
FUNDAMENTAL_FACTORS = (*_VALUE, *_QUALITY)


def _safe_ratio(num: pd.Series, den: pd.Series, sign: float) -> pd.Series:
    """num/den with non-positive or NaN denominators → NaN (never ±inf), times sign."""
    den = den.where(den > 0)
    return sign * (num / den)


def latest_known(fundamentals: pd.DataFrame, rebal_dates: list[pd.Timestamp]) -> pd.DataFrame:
    """Point-in-time fundamentals per (rebalance date, ticker) via ``merge_asof``.

    ``fundamentals`` has columns ``ticker, accepted_date, <fields>``. For each
    ticker and each rebalance date, returns the most recent statement with
    ``accepted_date <= rebalance`` (no look-ahead). Output is long:
    ``[date, ticker, <fields>]``.
    """
    if fundamentals.empty:
        return pd.DataFrame(columns=["date", "ticker"])
    fund = fundamentals.copy()
    # merge_asof requires both join keys at the SAME datetime resolution; DuckDB
    # hands back microsecond timestamps, the rebalance dates are nanosecond — pin
    # both to ns.
    fund["accepted_date"] = pd.to_datetime(fund["accepted_date"]).astype("datetime64[ns]")
    fund = fund.dropna(subset=["accepted_date"]).sort_values("accepted_date")
    rebal = pd.DataFrame({"date": pd.to_datetime(sorted(rebal_dates)).astype("datetime64[ns]")})
    out: list[pd.DataFrame] = []
    for ticker, grp in fund.groupby("ticker", sort=False):
        merged = pd.merge_asof(rebal, grp, left_on="date", right_on="accepted_date", direction="backward")
        merged = merged.dropna(subset=["accepted_date"])  # drop dates before the first filing
        merged["ticker"] = ticker
        out.append(merged)
    if not out:
        return pd.DataFrame(columns=["date", "ticker"])
    return pd.concat(out, ignore_index=True)


def compute_factor_values(pit: pd.DataFrame, close: pd.DataFrame) -> pd.DataFrame:
    """Add market_cap, invested_capital, and every fundamental factor column to the
    PIT long frame. ``close`` is a (date × ticker) price matrix; market cap on each
    rebalance date = that date's close × latest-known diluted shares."""
    if pit.empty:
        return pit
    df = pit.copy()
    # Price on each rebalance date (close index is datetime; reindex-align by date+ticker).
    px = close.reindex(pd.to_datetime(sorted(set(df["date"]))))
    df["close"] = [
        px.at[d, t] if (d in px.index and t in px.columns) else np.nan
        for d, t in zip(df["date"], df["ticker"], strict=False)
    ]
    df["market_cap"] = df["close"] * df.get("shares_diluted")
    df["invested_capital"] = df.get("total_debt", 0.0).fillna(0.0) + df.get("total_equity")
    for name, (num, den, sign) in {**_VALUE, **_QUALITY}.items():
        df[name] = _safe_ratio(df[num], df[den], sign)
    return df


def build_fundamental_factor_matrices(
    fundamentals: pd.DataFrame, close: pd.DataFrame, rebal_dates: list[pd.Timestamp]
) -> dict[str, pd.DataFrame]:
    """Each fundamental factor as a (date × ticker) matrix aligned to ``rebal_dates``
    — the shape ``scripts/factor_research.run_study`` consumes. Pure."""
    pit = latest_known(fundamentals, rebal_dates)
    vals = compute_factor_values(pit, close)
    matrices: dict[str, pd.DataFrame] = {}
    if vals.empty:
        return {name: pd.DataFrame() for name in FUNDAMENTAL_FACTORS}
    for name in FUNDAMENTAL_FACTORS:
        matrices[name] = vals.pivot_table(index="date", columns="ticker", values=name)
    return matrices
