"""Factor Lab factor registry (plan v0.2 §3.2).

Maps a `ProgramSpec.factor` key + its params to a **score function** `(store, as_of) ->
DataFrame[score]` — the one genuinely program-specific input the unified runner needs.
Adding a brand-new factor is registering one builder here; no new harness.

V1 seeds the quantile-compatible factors already in the library (momentum, low_vol,
composite). The sector-basket and trend (cash-participation) scorers land with their
construction modes in a later session (plan §4/§7).
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import date
from typing import Any

import pandas as pd

from app.factor_data.factors.engine import DEFAULT_MIN_NAMES, momentum_scores
from app.factor_data.factors.low_vol import DEFAULT_VOL_LOOKBACK_DAYS, low_vol_scores
from app.factor_data.store import FactorDataStore

# A score function as the backtest consumes it: PIT, deterministic, ticker-indexed `score`.
ScoreFn = Callable[[FactorDataStore, date], pd.DataFrame]


def _momentum(n: int, *, lookback_days: int = 252, skip_days: int = 0,
              min_names: int = DEFAULT_MIN_NAMES) -> ScoreFn:
    def score_fn(store: FactorDataStore, as_of: date) -> pd.DataFrame:
        return momentum_scores(store, as_of, n=n, lookback_days=lookback_days,
                               skip_days=skip_days, min_names=min_names)
    return score_fn


def _low_vol(n: int, *, lookback_days: int = DEFAULT_VOL_LOOKBACK_DAYS,
             min_names: int = DEFAULT_MIN_NAMES) -> ScoreFn:
    def score_fn(store: FactorDataStore, as_of: date) -> pd.DataFrame:
        return low_vol_scores(store, as_of, n=n, lookback_days=lookback_days, min_names=min_names)
    return score_fn


def _composite(n: int, *, factors: list[str], weights: dict[str, float] | None = None,
               min_names: int = DEFAULT_MIN_NAMES, lookback_days: int = 105,
               skip_days: int = 21, missing: str = "impute") -> ScoreFn:
    # Imported lazily: composite pulls SF1/fundamental factors that aren't needed for the
    # price-only programs and keep the base import light.
    from app.factor_data.factors.composite import composite_scores

    def score_fn(store: FactorDataStore, as_of: date) -> pd.DataFrame:
        return composite_scores(store, as_of, factors=factors, weights=weights, n=n,
                                min_names=min_names, lookback_days=lookback_days,
                                skip_days=skip_days, missing=missing)
    return score_fn


# factor key -> builder(n, **factor_params) -> ScoreFn
FACTOR_BUILDERS: dict[str, Callable[..., ScoreFn]] = {
    "momentum": _momentum,
    "low_vol": _low_vol,
    "composite": _composite,
}


def build_score_fn(factor: str, n: int, factor_params: dict[str, Any]) -> ScoreFn:
    """Resolve a registered factor + its params to a bound score function."""
    if factor not in FACTOR_BUILDERS:
        raise KeyError(f"unknown factor {factor!r}; registered: {sorted(FACTOR_BUILDERS)}")
    return FACTOR_BUILDERS[factor](n, **factor_params)
