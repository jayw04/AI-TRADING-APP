"""Point-in-time, survivorship-free tradeable universe.

P9 §1 was drafted against an S&P 500 membership universe, but the Sharadar
`SP500` constituents datatable in this subscription is a 28-name free sample (the
Dow blue-chips), not the full ~500-name index — confirmed live during §1's
"pin the recipe first" step. SEP (prices) and TICKERS (21,853 names, with
firstpricedate/lastpricedate lifetime bounds) ARE full and survivorship-free.

Per the owner's decision (2026-06-14), the v1 universe is therefore a **PIT
liquidity universe**: the top-N US names by trailing dollar volume that were
tradeable as of the rebalance date. This is price-only (honoring "v1 is
price-only"), point-in-time, survivorship-free, and needs no extra subscription.
See docs/runbook/factor-data.md and the §1 doc's reconciliation note.
"""

from __future__ import annotations

from datetime import date

from app.factor_data.store import FactorDataStore

# Defaults: a broad large-cap-ish cross-section over ~one quarter of liquidity.
DEFAULT_UNIVERSE_SIZE = 500
DEFAULT_LOOKBACK_DAYS = 63


class UniverseUnavailable(RuntimeError):
    """Raised when a universe cannot be reconstructed for `as_of` — e.g. the date
    predates the price history (below the data floor). Raising beats returning a
    wrong (look-ahead or empty-but-silent) universe."""


def universe_asof(
    store: FactorDataStore,
    as_of: date,
    *,
    n: int = DEFAULT_UNIVERSE_SIZE,
    lookback_days: int = DEFAULT_LOOKBACK_DAYS,
) -> list[str]:
    """Top-`n` tradeable US tickers by trailing dollar volume as of `as_of`.

    Survivorship-free and point-in-time:
    - a name **added to the listings after** `as_of` is **absent** (its
      firstpricedate is later than `as_of`);
    - a name **present then but since delisted** is **included** if it was
      tradeable and liquid as of `as_of` (its lifetime bounds straddle `as_of`
      and it has SEP volume in the trailing window);
    - ranking uses only data on or before `as_of` — no look-ahead.

    Bounded below by the price-history floor: `as_of` earlier than the first SEP
    date raises `UniverseUnavailable` rather than returning a wrong/empty set.
    Deterministic — repeated calls return the identical ordered list.
    """
    if n <= 0:
        raise ValueError("n must be positive")

    floor, _ = store.price_date_bounds()
    if floor is None:
        raise UniverseUnavailable("factor-data store has no price history; ingest first")
    if as_of < floor:
        raise UniverseUnavailable(
            f"as_of {as_of} is before the price-history floor {floor}; "
            "no point-in-time universe can be reconstructed"
        )

    return store.dollar_volume_universe(as_of, n=n, lookback_days=lookback_days)
