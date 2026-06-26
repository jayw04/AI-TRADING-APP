"""IndicatorComputer — pandas-ta wrapper with TTL memoization.

Supported indicators (P2 core set)::

    SMA20, SMA50, SMA200
    EMA9, EMA20, EMA21, EMA50
    RSI14
    MACD            → three series: 'macd', 'signal', 'hist'
    ATR14
    VWAP
    BB              → three series: 'bb_lower', 'bb_mid', 'bb_upper'
    RELVOL20        → volume / 20-period SMA of volume

Multi-output indicators (MACD, BB) return ``dict[str, pd.Series]``; the rest
return ``pd.Series``. Memoization is keyed by ``(symbol, timeframe,
last_bar_ts, indicator_name)`` with a 60 s TTL — same call inside the same
minute returns the cached series object; the next bar bumps the key and
triggers fresh computation.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import pandas as pd
import structlog

logger = structlog.get_logger(__name__)


CORE_INDICATORS: list[str] = [
    "SMA20",
    "SMA50",
    "SMA200",
    "EMA9",
    "EMA20",
    "EMA21",
    "EMA50",
    "RSI14",
    "MACD",
    "ATR14",
    "VWAP",
    "BB",
    "RELVOL20",
]


# Lazy pandas-ta import lives inside each computer so the module loads even
# when pandas-ta is missing (tests that don't need indicators can import
# this module without bringing in the dependency).


def _nan_series(index: pd.Index, name: str) -> pd.Series:
    """An all-NaN series aligned to ``index`` — the warmup-region shape any
    rolling indicator naturally returns when its window exceeds the bar count."""
    return pd.Series([float("nan")] * len(index), index=index, name=name)


def _named(result: pd.Series | None, index: pd.Index, name: str) -> pd.Series:
    """Normalize a single-output pandas-ta result.

    pandas-ta is inconsistent across versions when the window is longer than the
    available bars: some builds return an all-NaN ``Series``, others return
    ``None`` (seen on the CI-resolved pandas-ta/numpy, not locally). Calling
    ``.rename`` on ``None`` then raises and — on the backtest path — leaves the
    job wedged. Collapse both shapes to an all-NaN series so callers see the same
    warmup behavior everywhere."""
    if result is None:
        return _nan_series(index, name)
    return result.rename(name)


def _sma(bars: pd.DataFrame, length: int) -> pd.Series:
    import pandas_ta as ta

    return _named(ta.sma(bars["c"], length=length), bars.index, f"SMA{length}")


def _ema(bars: pd.DataFrame, length: int) -> pd.Series:
    import pandas_ta as ta

    return _named(ta.ema(bars["c"], length=length), bars.index, f"EMA{length}")


def _rsi(bars: pd.DataFrame) -> pd.Series:
    import pandas_ta as ta

    return _named(ta.rsi(bars["c"], length=14), bars.index, "RSI14")


def _macd(bars: pd.DataFrame) -> dict[str, pd.Series]:
    import pandas_ta as ta

    # pandas-ta returns a DataFrame with columns like
    # MACD_12_26_9, MACDh_12_26_9, MACDs_12_26_9. We address by position so
    # naming changes between versions don't break us. ``None`` on a too-short
    # window (version-dependent) → all-NaN warmup series for each output.
    df = ta.macd(bars["c"], fast=12, slow=26, signal=9)
    if df is None:
        return {k: _nan_series(bars.index, k) for k in ("macd", "hist", "signal")}
    return {
        "macd": df.iloc[:, 0].rename("macd"),
        "hist": df.iloc[:, 1].rename("hist"),
        "signal": df.iloc[:, 2].rename("signal"),
    }


def _atr(bars: pd.DataFrame) -> pd.Series:
    import pandas_ta as ta

    return _named(ta.atr(bars["h"], bars["l"], bars["c"], length=14), bars.index, "ATR14")


def _vwap(bars: pd.DataFrame) -> pd.Series:
    """Session VWAP. pandas-ta wants a DatetimeIndex; we set + restore."""
    import pandas_ta as ta

    tmp = bars.set_index("t")
    out = ta.vwap(high=tmp["h"], low=tmp["l"], close=tmp["c"], volume=tmp["v"])
    if out is None:
        return _nan_series(bars.index, "VWAP")
    out.index = bars.index
    return out.rename("VWAP")


def _bbands(bars: pd.DataFrame) -> dict[str, pd.Series]:
    import pandas_ta as ta

    # pandas-ta 0.4 typing stubs declare `std` as dict | None, but the
    # function genuinely accepts a float; verified at runtime. Narrow ignore.
    df = ta.bbands(bars["c"], length=20, std=2.0)  # type: ignore[arg-type]
    if df is None:  # too-short window (version-dependent) → all-NaN warmup series
        return {k: _nan_series(bars.index, k) for k in ("bb_lower", "bb_mid", "bb_upper")}
    # Columns: BBL, BBM, BBU, BBB, BBP (the latter two are width + position).
    return {
        "bb_lower": df.iloc[:, 0].rename("bb_lower"),
        "bb_mid": df.iloc[:, 1].rename("bb_mid"),
        "bb_upper": df.iloc[:, 2].rename("bb_upper"),
    }


def _relvol20(bars: pd.DataFrame) -> pd.Series:
    """Relative volume = current volume / 20-period SMA of volume."""
    sma_v = bars["v"].rolling(20).mean()
    rv = bars["v"] / sma_v
    return rv.rename("RELVOL20")


_INDICATOR_DISPATCH: dict[str, Callable[[pd.DataFrame], Any]] = {
    "SMA20": lambda b: _sma(b, 20),
    "SMA50": lambda b: _sma(b, 50),
    "SMA200": lambda b: _sma(b, 200),
    "EMA9": lambda b: _ema(b, 9),
    "EMA20": lambda b: _ema(b, 20),
    "EMA21": lambda b: _ema(b, 21),
    "EMA50": lambda b: _ema(b, 50),
    "RSI14": _rsi,
    "MACD": _macd,
    "ATR14": _atr,
    "VWAP": _vwap,
    "BB": _bbands,
    "RELVOL20": _relvol20,
}


@dataclass(frozen=True)
class _CacheKey:
    symbol: str
    timeframe: str
    end_ts_epoch: int
    name: str


class IndicatorComputer:
    """Compute curated indicators on a bars DataFrame with memoization."""

    def __init__(self) -> None:
        self._cache: dict[_CacheKey, Any] = {}
        self._cache_expiry: dict[_CacheKey, float] = {}
        self._ttl_seconds = 60.0

    def compute(
        self,
        bars: pd.DataFrame,
        names: list[str],
        symbol: str = "",
        timeframe: str = "",
    ) -> dict[str, Any]:
        """Compute the requested indicators.

        Returns a dict mapping indicator name → ``pd.Series`` (single-output)
        or ``dict[str, pd.Series]`` (multi-output, e.g. MACD / BB).

        Unknown names raise ``KeyError`` — callers should validate against
        ``CORE_INDICATORS`` before calling if they want a user-facing error.
        """
        if bars.empty:
            return {n: pd.Series(dtype="float64") for n in names}

        last_ts = bars["t"].iloc[-1]
        end_epoch = int(pd.Timestamp(last_ts).timestamp())

        out: dict[str, Any] = {}
        now = time.time()

        for name in names:
            if name not in _INDICATOR_DISPATCH:
                raise KeyError(
                    f"Unknown indicator: {name}. Supported: {CORE_INDICATORS}"
                )
            key = _CacheKey(
                symbol=symbol,
                timeframe=timeframe,
                end_ts_epoch=end_epoch,
                name=name,
            )
            if key in self._cache and self._cache_expiry.get(key, 0) > now:
                out[name] = self._cache[key]
                continue
            try:
                value = _INDICATOR_DISPATCH[name](bars)
            except Exception:
                logger.exception(
                    "indicator_compute_failed",
                    name=name,
                    symbol=symbol,
                    timeframe=timeframe,
                    bar_count=len(bars),
                )
                # Multi-output indicators yield {}, single-output yields an
                # empty series. Either way the caller sees "nothing computed"
                # without a crash.
                out[name] = {} if name in ("MACD", "BB") else pd.Series(dtype="float64")
                continue
            self._cache[key] = value
            self._cache_expiry[key] = now + self._ttl_seconds
            out[name] = value

        # Opportunistic eviction so the cache doesn't grow forever.
        if int(now) % 30 == 0:
            self._prune_expired(now)

        return out

    def _prune_expired(self, now: float) -> None:
        expired = [k for k, exp in self._cache_expiry.items() if exp <= now]
        for k in expired:
            self._cache.pop(k, None)
            self._cache_expiry.pop(k, None)
