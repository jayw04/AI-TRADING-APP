"""Total-Return Adapter math (PORT-001 §1) — pure, deterministic."""

from __future__ import annotations

import pandas as pd

from app.factor_data.total_return import total_return_bars, total_return_index


def _idx(n: int) -> pd.DatetimeIndex:
    return pd.date_range("2026-01-01", periods=n, freq="D")


def test_no_actions_is_identity():
    # With no distributions/splits, the total-return index == the raw close.
    c = pd.Series([100.0, 101.0, 99.0, 103.0], index=_idx(4))
    tri = total_return_index(c)
    assert list(tri.round(6)) == [100.0, 101.0, 99.0, 103.0]


def test_dividend_is_reinvested():
    # Flat price with a $1 dividend on day 1 → that day's total return is +1%.
    idx = _idx(3)
    c = pd.Series([100.0, 100.0, 100.0], index=idx)
    div = pd.Series({idx[1]: 1.0})
    tri = total_return_index(c, dividends=div)
    assert list(tri.round(6)) == [100.0, 101.0, 101.0]  # +1% on the ex-date, flat after


def test_split_does_not_change_total_return():
    # A 2:1 split halves the raw close but leaves total return unchanged.
    idx = _idx(3)
    c = pd.Series([100.0, 50.0, 50.0], index=idx)  # price halves on the split ex-date
    spl = pd.Series({idx[1]: 2.0})
    tri = total_return_index(c, splits=spl)
    assert list(tri.round(6)) == [100.0, 100.0, 100.0]


def test_dividend_and_split_combined():
    # 2:1 split AND a $0.50 (post-split) dividend on the same ex-date:
    # r = 2·(50 + 0.5)/100 − 1 = +1%.
    idx = _idx(2)
    c = pd.Series([100.0, 50.0], index=idx)
    tri = total_return_index(
        c, dividends=pd.Series({idx[1]: 0.5}), splits=pd.Series({idx[1]: 2.0})
    )
    assert round(float(tri.iloc[1]), 6) == 101.0


def test_total_return_bars_wrapper_adds_tr_close():
    idx = _idx(3)
    bars = pd.DataFrame({"t": idx, "c": [100.0, 100.0, 100.0], "v": [1, 1, 1]})
    out = total_return_bars(bars, dividends=pd.Series({idx[1]: 2.0}))
    assert list(out.columns) == ["t", "tr_close"]
    assert list(out["tr_close"].round(6)) == [100.0, 102.0, 102.0]  # +2% on the ex-date


def test_empty_is_safe():
    assert total_return_index(pd.Series([], dtype="float64")).empty
    assert total_return_bars(pd.DataFrame(columns=["t", "c"])).empty
