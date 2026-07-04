"""Total-Return Adapter (PORT-001 §1 · ADR 0030 #2 · a Market-Data platform capability).

Builds a **total-return** daily price series from RAW (unadjusted) closes + corporate
actions (cash distributions + splits). The platform's Alpaca bars are unadjusted
(DCAP-003); PORT-001's cross-asset sleeve needs total-return bars because distributions
are a material part of return for bond/commodity ETFs (IEF/TLT/DBC). We **post-process
ourselves** rather than add a new data vendor (ADR 0030 #2), and the adjustment is
**explicit and reproducible** (ADR 0014) — not an opaque vendor adjustment flag.

The math is pure and deterministic (trivially testable). The LIVE corporate-actions
source is injected via the ``DistributionsProvider`` seam; the live implementation is
``app/market_data/alpaca_distributions.py::AlpacaDistributionsProvider`` (Alpaca
corporate-actions API — the Sharadar ``actions`` table has zero coverage for the
cross-asset ETFs). The original Norton-SSL deferral applied only to the dev laptop; the
live runtime is AWS, where the fetch works (PORT-001 #3).

Total-return one-day holding return (the standard formulation, handling a same-day split):

    r_t = s_t · (c_t + d_t) / c_{t-1} − 1

where ``s_t`` is the share multiplier of a split with ex-date t (e.g. 2.0 for a 2:1 split;
1.0 if none) and ``d_t`` is the cash distribution per (post-split) share with ex-date t.
The total-return index is ``TRI_t = TRI_{t-1}·(1 + r_t)``, normalized so ``TRI_0`` equals the
first raw close (so TRI ≈ raw close when there are no distributions).
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Protocol

import pandas as pd


def total_return_index(
    close: pd.Series,
    dividends: Mapping[pd.Timestamp, float] | pd.Series | None = None,
    splits: Mapping[pd.Timestamp, float] | pd.Series | None = None,
) -> pd.Series:
    """Total-return index from a raw close series + (optional) per-date cash distributions
    and split share-multipliers. Index is the same as ``close`` (sorted ascending); the
    result is normalized so its first value equals the first raw close. Pure/deterministic.

    ``dividends`` — cash per (post-split) share, keyed by ex-date.
    ``splits`` — share multiplier, keyed by ex-date (2.0 = 2:1 split; 0.5 = 1:2 reverse).
    """
    c = pd.Series(close, dtype="float64").sort_index()
    if c.empty:
        return c
    div = _as_series(dividends, c.index)
    spl = _as_series(splits, c.index, fill=1.0)

    prev = c.shift(1)
    # r_t = s_t·(c_t + d_t)/c_{t-1} − 1 ; first row has no prior close → 0 return.
    r = (spl * (c + div) / prev) - 1.0
    r.iloc[0] = 0.0
    tri = (1.0 + r).cumprod()
    return tri * float(c.iloc[0])  # normalize TRI_0 to the first raw close


def total_return_bars(
    bars: pd.DataFrame,
    dividends: Mapping[pd.Timestamp, float] | pd.Series | None = None,
    splits: Mapping[pd.Timestamp, float] | pd.Series | None = None,
    *,
    close_col: str = "c",
    date_col: str = "t",
) -> pd.DataFrame:
    """Add a ``tr_close`` total-return column to a raw daily-bar frame (cols incl. ``t``,``c``).
    Returns a copy with ``t`` and ``tr_close`` (sorted by date). Empty-safe."""
    if bars is None or bars.empty:
        return pd.DataFrame(columns=[date_col, "tr_close"])
    df = bars.sort_values(date_col).reset_index(drop=True)
    s = pd.Series(df[close_col].to_numpy(dtype="float64"), index=pd.Index(df[date_col]))
    tri = total_return_index(s, dividends, splits)
    return pd.DataFrame({date_col: df[date_col].to_numpy(), "tr_close": tri.to_numpy()})


def _as_series(
    m: Mapping[pd.Timestamp, float] | pd.Series | None,
    index: pd.Index,
    *,
    fill: float = 0.0,
) -> pd.Series:
    """Align a date→value mapping/series onto ``index``, filling absent dates with ``fill``."""
    base = pd.Series(fill, index=index, dtype="float64")
    if m is None:
        return base
    src = m if isinstance(m, pd.Series) else pd.Series(m, dtype="float64")
    src = src.reindex(index)
    return src.where(src.notna(), base)


class DistributionsProvider(Protocol):
    """The live corporate-actions seam. An implementation returns the per-share cash
    distributions and split multipliers (keyed by ex-date) for a symbol over a window.
    Live providers (Alpaca corporate-actions / Sharadar `actions`) are wired separately;
    the live fetch is Norton-gated and deferred."""

    def distributions(
        self, symbol: str, start: pd.Timestamp, end: pd.Timestamp
    ) -> tuple[pd.Series, pd.Series]:  # (dividends, splits)
        ...


class TotalReturnAdapter:
    """Composes a raw-bar source with a ``DistributionsProvider`` to yield total-return bars
    — the read-only Market-Data capability PORT-001's cross-asset sleeve consumes. Both
    sources are injected so the adapter is testable offline with fakes; the live bar source
    is the Alpaca ``bar_cache`` and the live distributions source is Norton-gated (deferred).
    """

    def __init__(self, bar_provider: object, dist_provider: DistributionsProvider) -> None:
        self._bars = bar_provider
        self._dist = dist_provider

    async def get_total_return_bars(
        self, symbol: str, start: pd.Timestamp, end: pd.Timestamp
    ) -> pd.DataFrame:
        raw = await self._bars.get_bars(symbol, "1Day", start, end)  # type: ignore[attr-defined]
        div, spl = self._dist.distributions(symbol, start, end)
        return total_return_bars(raw, div, spl)
