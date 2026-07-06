"""SF1-backed Value & Quality fundamental factors (P14 Factor Lab, ADR 0023).

The complement to ``fundamental.py`` (which sources value/quality from the thin FMP layer): these
read **Sharadar SF1** — survivorship-free, point-in-time via ``datekey``, ~thousands of names,
2016+. Each factor is a cross-sectional signal where **higher = more attractive (long)**, matching
the price-factor + FMP-factor convention.

Value (cheaper = higher signal): earnings / FCF / sales / book yield = the fundamental over **current**
market cap (SF1's ``marketcap``). Quality (better business = higher signal): ROE, ROIC, gross
profitability (Novy-Marx: gross profit / total assets), and low leverage (negative debt/equity).

Pure functions over the SF1 as-of frame (``store.get_sf1_asof``, indexed by ticker) so they
unit-test cleanly; the store loader is a thin wrapper.
"""

from __future__ import annotations

from datetime import date

import pandas as pd

from app.factor_data.store import FactorDataStore

# value factor -> the SF1 numerator divided by market cap (cheaper = higher yield = better)
_VALUE_YIELD = {
    "sf1_earnings_yield": "netinc",
    "sf1_fcf_yield": "fcf",
    "sf1_sales_yield": "revenue",
    "sf1_book_yield": "equity",
}
SF1_VALUE_FACTORS = tuple(_VALUE_YIELD)
SF1_QUALITY_FACTORS = ("sf1_roe", "sf1_roic", "sf1_gross_profitability", "sf1_low_leverage")
SF1_FACTORS = (*SF1_VALUE_FACTORS, *SF1_QUALITY_FACTORS)


def _safe_ratio(num: pd.Series, den: pd.Series) -> pd.Series:
    """num/den with non-positive or NaN denominators → NaN (never ±inf)."""
    return num / den.where(den > 0)


def sf1_factor_frame(asof: pd.DataFrame) -> pd.DataFrame:
    """Every SF1 factor column for the as-of frame (indexed by ticker). Pure.

    ``asof`` is one latest-known SF1 row per ticker (the ``store.get_sf1_asof`` shape). Value
    yields divide by ``marketcap``; quality reuses SF1's pre-computed ``roe``/``roic`` and derives
    gross profitability + low-leverage. Empty frame in → empty frame out."""
    if asof.empty:
        return pd.DataFrame()
    mc = asof["marketcap"].where(asof["marketcap"] > 0)
    df = pd.DataFrame(index=asof.index)
    for name, col in _VALUE_YIELD.items():
        df[name] = asof[col] / mc
    df["sf1_roe"] = asof["roe"]
    df["sf1_roic"] = asof["roic"]
    df["sf1_gross_profitability"] = _safe_ratio(asof["gp"], asof["assets"])
    df["sf1_low_leverage"] = -asof["de"]  # less leverage = better
    return df


def sf1_factor_raw(
    store: FactorDataStore, as_of: date, tickers: list[str], factors: list[str]
) -> dict[str, dict[str, float]]:
    """Raw SF1 factor values ``{factor: {ticker: value}}`` for ``tickers`` at ``as_of`` (PIT).

    The shape ``composite.factor_zscores`` blends. Names missing a factor are simply absent from
    that factor's dict (the composite imputes z=0 or drops, per its ``missing`` arg)."""
    bad = [f for f in factors if f not in SF1_FACTORS]
    if bad:
        raise ValueError(f"unknown SF1 factor(s): {bad}")
    frame = sf1_factor_frame(store.get_sf1_asof(tickers, as_of))
    out: dict[str, dict[str, float]] = {}
    for f in factors:
        if frame.empty or f not in frame.columns:
            out[f] = {}
            continue
        s = frame[f].dropna()
        out[f] = {t: float(s.at[t]) for t in s.index}
    return out
