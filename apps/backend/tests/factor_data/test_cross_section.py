"""Cross-sectional standardization math (P9 §2 §4.3)."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from app.factor_data.factors.cross_section import rank, standardize, winsorize, zscore


def test_zscore_mean_zero_std_one() -> None:
    s = pd.Series([1.0, 2.0, 3.0, 4.0, 5.0])
    z = zscore(s)
    assert z.mean() == pytest.approx(0.0, abs=1e-12)
    assert z.std(ddof=0) == pytest.approx(1.0, abs=1e-12)


def test_zscore_zero_variance_returns_zeros() -> None:
    z = zscore(pd.Series([7.0, 7.0, 7.0]))
    assert (z == 0.0).all()  # not inf/NaN


def test_zscore_preserves_nan_positions() -> None:
    z = zscore(pd.Series([1.0, np.nan, 3.0]))
    assert pd.isna(z.iloc[1])
    assert not pd.isna(z.iloc[0])


def test_rank_in_unit_interval_and_monotonic() -> None:
    r = rank(pd.Series([10.0, 20.0, 30.0, 40.0]))
    assert r.min() > 0.0 and r.max() == pytest.approx(1.0)
    assert list(r) == sorted(r)  # monotonic with input order (already sorted)


def test_winsorize_caps_at_quantiles() -> None:
    s = pd.Series(list(range(100)) + [10_000.0])  # one extreme outlier
    w = winsorize(s, lower=0.01, upper=0.99)
    assert w.max() < 10_000.0  # the outlier was clipped
    assert w.min() >= s.quantile(0.01)


def test_winsorize_rejects_bad_bounds() -> None:
    with pytest.raises(ValueError):
        winsorize(pd.Series([1.0, 2.0]), lower=0.9, upper=0.1)


def test_all_nan_series_passthrough() -> None:
    s = pd.Series([np.nan, np.nan, np.nan])
    assert winsorize(s).isna().all()  # nothing to clip
    assert zscore(s).isna().all()     # nothing to standardize


def test_standardize_columns_and_relationship() -> None:
    raw = pd.Series({"A": -5.0, "B": 0.0, "C": 5.0, "D": 100.0})
    df = standardize(raw)
    assert list(df.columns) == ["raw", "winsorized", "zscore", "rank"]
    # rank is order-preserving: D (largest raw) has the top rank
    assert df["rank"].idxmax() == "D"
    # zscore computed on winsorized values → mean ~0
    assert df["zscore"].mean() == pytest.approx(0.0, abs=1e-9)
