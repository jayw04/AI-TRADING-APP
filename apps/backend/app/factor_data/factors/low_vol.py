"""Cross-sectional low-volatility engine: universe → per-name realized vol → −vol score.

The factor analog of ``factors.engine.momentum_scores`` for LOW-001 (Low Volatility).
Each name is scored by the **negative** of its trailing realized volatility (lowest
realized vol → highest score), so the same top-quantile-equal-weight harness that
holds the strongest-momentum names instead holds the *calmest* names.

Faithful to the validated LOW-001 V1 research (``scripts/low_vol_research.py`` ::
``low_vol_score``): the realized-vol primitive is the **same** ``_trailing_vol`` the
research and the factor-agnostic backtest used (252-day trailing daily-return σ,
strictly point-in-time), reused here rather than re-implemented so the promoted
strategy cannot silently drift from the evidence it was validated on (the
Methodology-Transfer discipline). Prices-only, no order path / broker / DB / LLM.
"""

from __future__ import annotations

from datetime import date

import pandas as pd

from app.factor_data.factors.engine import DEFAULT_MIN_NAMES, FactorUnavailable
from app.factor_data.store import FactorDataStore
from app.factor_data.universe import universe_asof

# 252 trading days = the platform's 12-month convention; frozen from LOW-001 research
# (``VOL_LOOKBACK_DAYS`` in ``scripts/low_vol_research.py``). Not a tunable knob.
DEFAULT_VOL_LOOKBACK_DAYS = 252


def low_vol_scores(
    store: FactorDataStore,
    as_of: date,
    *,
    n: int = 500,
    lookback_days: int = DEFAULT_VOL_LOOKBACK_DAYS,
    min_names: int = DEFAULT_MIN_NAMES,
) -> pd.DataFrame:
    """Point-in-time cross-sectional low-volatility scores for the universe as of `as_of`.

    Pipeline: ``universe_asof(store, as_of, n)`` → per-name trailing realized vol
    (``_trailing_vol``, strictly before `as_of`) → drop names with no/degenerate
    history → score = −vol. Returns a DataFrame indexed by ticker with columns
    ``[volatility, score]``, sorted by ``score`` descending (lowest vol first).
    Reads no data after `as_of`.

    Raises ``FactorUnavailable`` if fewer than ``min_names`` names have a valid
    realized vol on `as_of` — standardizing a handful of names is noise, not a
    signal (mirrors ``momentum_scores``). Deterministic: identical store + args
    yield an identical frame (ties in ``score`` broken by ticker ascending).
    """
    # Reused lazily: keep the (numpy/structlog-heavy) backtest module out of the
    # base factor-accessor import path; it loads only when a low-vol book scores.
    from app.factor_data.backtest import _trailing_vol

    tickers = universe_asof(store, as_of, n=n)
    vols: dict[str, float] = {}
    for ticker in tickers:
        v = _trailing_vol(store, ticker, as_of, lookback_days)
        if v is not None and v > 0:
            vols[ticker] = v
    if len(vols) < min_names:
        raise FactorUnavailable(
            f"only {len(vols)} of {len(tickers)} names have a valid realized vol on "
            f"{as_of} (min_names={min_names}); refusing to rank a degenerate cross-section"
        )

    volatility = pd.Series(vols, name="volatility").sort_index()
    volatility.index.name = "ticker"
    df = pd.DataFrame({"volatility": volatility})
    df["score"] = -volatility
    # Deterministic order: score desc, ticker asc on ties. Sort ticker-ascending
    # first, then a STABLE sort by score desc preserves ticker order within ties.
    df = df.sort_index()
    return df.sort_values("score", ascending=False, kind="stable")
