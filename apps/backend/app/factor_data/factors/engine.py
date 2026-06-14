"""Cross-sectional momentum engine: universe → per-name momentum → standardized scores."""

from __future__ import annotations

from datetime import date

import pandas as pd

from app.factor_data.factors.cross_section import standardize
from app.factor_data.factors.momentum import (
    DEFAULT_LOOKBACK_DAYS,
    DEFAULT_SKIP_DAYS,
    compute_momentum_batch,
)
from app.factor_data.store import FactorDataStore
from app.factor_data.universe import universe_asof

DEFAULT_MIN_NAMES = 20


class FactorUnavailable(RuntimeError):
    """Raised when too few names have a valid factor on `as_of` to form an honest
    cross-section — standardizing a handful of names is noise, not a signal."""


def momentum_scores(
    store: FactorDataStore,
    as_of: date,
    *,
    n: int = 500,
    lookback_days: int = DEFAULT_LOOKBACK_DAYS,
    skip_days: int = DEFAULT_SKIP_DAYS,
    min_names: int = DEFAULT_MIN_NAMES,
) -> pd.DataFrame:
    """Point-in-time cross-sectional momentum for the universe as of `as_of`.

    Pipeline: `universe_asof(store, as_of, n)` → per-name momentum → drop names
    with insufficient history → winsorize/z-score/rank. Returns a DataFrame indexed
    by ticker with columns `[momentum, winsorized, zscore, rank, score]`, sorted by
    `score` (== the winsorized z-score) descending. Reads no data after `as_of`.

    Raises `FactorUnavailable` if fewer than `min_names` names have a valid
    momentum. Deterministic — identical store + args yield an identical frame
    (ties in `score` broken by ticker ascending).
    """
    tickers = universe_asof(store, as_of, n=n)
    raw = compute_momentum_batch(
        store, tickers, as_of, lookback_days=lookback_days, skip_days=skip_days
    )
    valid = {t: v for t, v in raw.items() if v is not None}
    if len(valid) < min_names:
        raise FactorUnavailable(
            f"only {len(valid)} of {len(tickers)} names have a valid momentum on "
            f"{as_of} (min_names={min_names}); refusing to standardize a degenerate "
            "cross-section"
        )

    momentum = pd.Series(valid, name="momentum").sort_index()
    momentum.index.name = "ticker"
    df = standardize(momentum)
    df["momentum"] = momentum
    df["score"] = df["zscore"]
    df = df[["momentum", "winsorized", "zscore", "rank", "score"]]
    # Deterministic order: score desc, ticker asc on ties. Sort ticker-ascending
    # first, then a STABLE sort by score desc preserves ticker order within ties.
    df = df.sort_index()
    return df.sort_values("score", ascending=False, kind="stable")
