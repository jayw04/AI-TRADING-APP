"""Market-regime signals derived from the PIT factor store (P10 §5, ADR 0022).

Breadth is **derived internally** from data already ingested (Sharadar `SEP`/`TICKERS`)
— no external vendor. It is computed over the **same point-in-time construction
universe the book selects from** (ADR 0022), not the whole market, so the regime
signal and the book see the same names. Read-only, off the order path (ADR 0002/0018);
point-in-time (no look-ahead); deterministic. A caller that can't get a valid reading
**fails open** (ADR 0020/0022) — a regime-data gap must never force a liquidation.

This module computes the raw signal only. How breadth (and, later, a VIX percentile)
maps into the overlay's ``desired_gross`` is the follow-on §5 wiring, governed by
ADR 0020 and gated on the ADR-0022 §7 promotion backtest before it governs a book.
"""

from __future__ import annotations

from datetime import date, timedelta

from app.factor_data.factors.engine import DEFAULT_MIN_NAMES
from app.factor_data.store import FactorDataStore
from app.factor_data.universe import (
    DEFAULT_UNIVERSE_SIZE,
    UniverseUnavailable,
    universe_asof,
)

# Default moving-average window (trading days) for the breadth reading. 200 is the
# conventional "is the name in an uptrend" line and matches the strategy's regime filter.
DEFAULT_MA_DAYS = 200

# VIX is consumed as a trailing PERCENTILE, never raw (ADR 0022): a level of 20 means
# different things across regimes, but its percentile is comparable. 252 ≈ one year.
DEFAULT_VIX_SYMBOL = "^VIX"
DEFAULT_VIX_LOOKBACK_DAYS = 252


def market_breadth(
    store: FactorDataStore,
    as_of: date,
    *,
    n: int = DEFAULT_UNIVERSE_SIZE,
    ma_days: int = DEFAULT_MA_DAYS,
    min_names: int = DEFAULT_MIN_NAMES,
) -> float | None:
    """Fraction of the as-of construction universe trading above its ``ma_days``-day MA.

    A point-in-time market-breadth signal in ``[0, 1]``: of the top-``n`` liquidity
    names tradeable as of ``as_of`` (``universe_asof``), the share whose latest close
    (≤ ``as_of``) exceeds the mean of its prior ``ma_days`` **completed** closes. Higher
    = broader participation (a healthier tape); lower = a narrow, deteriorating market.

    **Returns ``None`` (the caller fails open — ADR 0020/0022)** when the universe can't
    be formed for ``as_of`` (e.g. below the price-history floor) or fewer than
    ``min_names`` names have enough history (``ma_days`` + 1 closes) for an honest
    reading — a breadth of "2 of 3 names" is noise, not a signal.

    **Point-in-time & deterministic:** the MA uses only completed closes strictly before
    the latest bar, so it reads no data after ``as_of``; identical ``store`` + args yield
    an identical value. (Provenance — universe version, ``ma_days`` lookback, this
    computation version — is recorded by the caller/registry per ADR 0022, mirroring the
    Research Engine.)
    """
    try:
        tickers = universe_asof(store, as_of, n=n)
    except UniverseUnavailable:
        return None  # below the floor / no PIT universe → fail open

    # A generous calendar window (trading days are ~70% of calendar days) so we reliably
    # capture ma_days + 1 trading closes ending at as_of.
    start = as_of - timedelta(days=int(ma_days * 2) + 15)
    above = 0
    valid = 0
    for ticker in tickers:
        df = store.get_prices(ticker, start, as_of, adjusted=True)
        if df.empty:
            continue
        closes = [
            float(c)
            for dt, c in zip(df["date"], df["close"], strict=False)
            if c is not None and float(c) > 0 and dt.date() <= as_of
        ]
        closes = closes[-(ma_days + 1):]
        if len(closes) < ma_days + 1:
            continue  # not enough history for an honest MA on this name
        ma = sum(closes[:-1]) / ma_days  # mean of the prior ma_days completed closes
        valid += 1
        if closes[-1] > ma:  # latest close above its trend line
            above += 1

    if valid < min_names:
        return None  # too thin a cross-section → fail open
    return above / valid


def vix_percentile(
    store: FactorDataStore,
    as_of: date,
    *,
    symbol: str = DEFAULT_VIX_SYMBOL,
    lookback_days: int = DEFAULT_VIX_LOOKBACK_DAYS,
) -> float | None:
    """Trailing percentile rank of the latest VIX close within its prior
    ``lookback_days`` window, in ``[0, 1]`` (P10 §5, ADR 0022 — VIX is consumed as a
    percentile, never raw).

    The fraction of the prior ``lookback_days`` closes that sit **below** the latest
    close (≤ ``as_of``). ~1.0 = VIX at the high end of its recent range (stress, risk
    off); ~0.0 = calm. Sourced from the local ``index_prices`` store (ingested from FMP
    via ``scripts/ingest_vix.py``).

    **Returns ``None`` (the caller fails open — ADR 0020/0022)** when the series is
    absent or has fewer than ``lookback_days`` + 1 closes ending at/by ``as_of`` — e.g.
    deep-history backtest dates the ~5y FMP VIX depth doesn't reach (breadth carries
    those). **Point-in-time & deterministic:** uses only closes ≤ ``as_of``.
    """
    start = as_of - timedelta(days=int(lookback_days * 2) + 30)
    df = store.get_index_series(symbol, start, as_of)
    if df.empty:
        return None
    closes = [
        float(c)
        for dt, c in zip(df["date"], df["close"], strict=False)
        if c is not None and dt.date() <= as_of
    ]
    closes = closes[-(lookback_days + 1):]
    if len(closes) < lookback_days + 1:
        return None  # not enough history (e.g. pre-FMP-VIX-depth) → fail open
    latest = closes[-1]
    window = closes[:-1]  # the prior lookback_days closes
    below = sum(1 for v in window if v < latest)
    return below / len(window)
