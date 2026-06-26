"""Price-momentum factor (6-1 month total return).

Deterministic, point-in-time, survivorship-free: a name's momentum on `as_of` is a
pure function of its adjusted-close history on or before `as_of` (in fact, on or
before `as_of - skip_days`). Adding future prices cannot change a past score.

Window (P9 §2 §3, owner-locked 2026-06-14): trailing `lookback_days` trading-day
return ending `skip_days` trading days before `as_of` — defaults 105 / 21
(~5 months, skipping the most recent ~1 month to avoid short-term reversal).
"""

from __future__ import annotations

from datetime import date

import numpy as np
import pandas as pd

from app.factor_data.store import FactorDataStore

DEFAULT_LOOKBACK_DAYS = 105  # ~5 trading months (6-1 window: owner choice)
DEFAULT_SKIP_DAYS = 21  # ~1 trading month skipped (short-term reversal guard)


def compute_momentum(
    prices: pd.DataFrame,
    as_of: date,
    *,
    lookback_days: int = DEFAULT_LOOKBACK_DAYS,
    skip_days: int = DEFAULT_SKIP_DAYS,
) -> float | None:
    """Trailing total return over `[as_of - skip - lookback, as_of - skip]`.

    `prices` is one ticker's rows with at least `date` and `close` columns (the
    `close` already being the adjusted close from `FactorDataStore.get_prices(...,
    adjusted=True)`). Endpoints are **trading-day row offsets** into the slice of
    rows dated on/before `as_of`, so the score is robust to holidays and listing
    edges and never reads a price after `as_of`.

    Returns `None` (never a guess) when there are fewer than
    `lookback_days + skip_days + 1` rows on/before `as_of`, or when either endpoint
    price is missing or non-positive.
    """
    if lookback_days <= 0 or skip_days < 0:
        raise ValueError("lookback_days must be > 0 and skip_days >= 0")
    if prices.empty:
        return None

    as_of_ts = pd.Timestamp(as_of)
    dates = prices["date"]
    # Fast path for the store/cache contract (datetime64, ascending): the rows on or
    # before as_of are a prefix, located by binary search — no full-history reparse or
    # sort (which, over a multi-decade frame queried every rebalance, dominated runtime).
    # Byte-identical to the general path below; falls back for any other frame shape.
    if pd.api.types.is_datetime64_any_dtype(dates) and dates.is_monotonic_increasing:
        cut = int(np.searchsorted(dates.to_numpy(), as_of_ts.to_datetime64(), side="right"))
        closes = prices["close"].to_numpy()[:cut]
    else:
        s = prices.loc[pd.to_datetime(dates) <= as_of_ts].sort_values("date")
        closes = s["close"].to_numpy()

    needed = lookback_days + skip_days + 1
    if len(closes) < needed:
        return None

    end_px = closes[-1 - skip_days]
    start_px = closes[-1 - skip_days - lookback_days]
    if not (start_px > 0) or not (end_px > 0) or pd.isna(start_px) or pd.isna(end_px):
        return None
    return float(end_px / start_px - 1.0)


def compute_momentum_batch(
    store: FactorDataStore,
    tickers: list[str],
    as_of: date,
    *,
    lookback_days: int = DEFAULT_LOOKBACK_DAYS,
    skip_days: int = DEFAULT_SKIP_DAYS,
) -> dict[str, float | None]:
    """Momentum for each ticker, pulling each name's adjusted prices once.

    A wide enough start bound is used (the store's price floor) so the trailing
    window is always fully covered when the history exists.
    """
    floor, _ = store.price_date_bounds()
    if floor is None:
        return {t: None for t in tickers}
    out: dict[str, float | None] = {}
    for ticker in tickers:
        px = store.get_prices(ticker, floor, as_of, adjusted=True)
        out[ticker] = compute_momentum(
            px, as_of, lookback_days=lookback_days, skip_days=skip_days
        )
    return out
