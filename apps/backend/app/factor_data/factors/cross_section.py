"""Cross-sectional standardization of a raw factor across a universe.

Pure pandas/numpy. The pipeline (P9 §2 §3, owner-locked): winsorize at the
1st/99th percentile, then z-score; percentile rank is exposed alongside so a
consumer can switch without recomputing the factor.
"""

from __future__ import annotations

import pandas as pd

DEFAULT_WINSOR_LOWER = 0.01
DEFAULT_WINSOR_UPPER = 0.99


def winsorize(
    s: pd.Series, lower: float = DEFAULT_WINSOR_LOWER, upper: float = DEFAULT_WINSOR_UPPER
) -> pd.Series:
    """Clip to the [lower, upper] quantiles (computed over non-NaN values).

    Tames the fat tails that would otherwise dominate a mean/std. NaNs are left
    as NaN. A degenerate (all-equal or single-value) series is returned unchanged.
    """
    if lower < 0 or upper > 1 or lower >= upper:
        raise ValueError("require 0 <= lower < upper <= 1")
    valid = s.dropna()
    if valid.empty:
        return s.copy()
    lo = valid.quantile(lower)
    hi = valid.quantile(upper)
    return s.clip(lower=lo, upper=hi)


def zscore(s: pd.Series) -> pd.Series:
    """(x - mean) / std over non-NaN values (population std, ddof=0).

    A zero-variance cross-section returns all-zeros (not inf/NaN) — every name is
    equally (un)exceptional. NaNs are preserved at their original index.
    """
    valid = s.dropna()
    if valid.empty:
        return s.copy()
    mean = valid.mean()
    std = valid.std(ddof=0)
    if std == 0 or pd.isna(std):
        return s.where(s.isna(), 0.0)
    return (s - mean) / std


def rank(s: pd.Series) -> pd.Series:
    """Percentile rank in [0, 1] over non-NaN values (average ties). NaNs kept.

    A single valid value ranks 1.0; otherwise ranks span (0, 1]. Useful as a
    distribution-shape-robust, bounded alternative to the z-score.
    """
    return s.rank(method="average", pct=True)


def standardize(
    raw: pd.Series,
    *,
    winsor_lower: float = DEFAULT_WINSOR_LOWER,
    winsor_upper: float = DEFAULT_WINSOR_UPPER,
) -> pd.DataFrame:
    """Return [raw, winsorized, zscore, rank] for a cross-section.

    `zscore` is computed on the winsorized values (the primary `score` upstream);
    `rank` is computed on the raw values (rank is order-preserving, so winsorizing
    would not change it).
    """
    wins = winsorize(raw, winsor_lower, winsor_upper)
    return pd.DataFrame(
        {
            "raw": raw,
            "winsorized": wins,
            "zscore": zscore(wins),
            "rank": rank(raw),
        }
    )
