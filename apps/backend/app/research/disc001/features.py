"""Pure indicator helpers and the per-name feature panel for DISC-001.

No I/O. RSI is Wilder's 14-period (same convention as pandas-ta / IndicatorComputer).
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from app.research.disc001.spec import RSI_PERIOD, SMA_TREND


def sma_last(closes: np.ndarray, length: int) -> float | None:
    if length <= 0 or len(closes) < length:
        return None
    window = closes[-length:]
    if np.any(~np.isfinite(window)):
        return None
    return float(np.mean(window))


def simple_return(closes: np.ndarray, bars: int) -> float | None:
    """Close-to-close return over ``bars`` steps (needs bars+1 prices)."""
    if bars <= 0 or len(closes) < bars + 1:
        return None
    start = float(closes[-(bars + 1)])
    end = float(closes[-1])
    if start <= 0 or not np.isfinite(start) or not np.isfinite(end):
        return None
    return end / start - 1.0


def wilder_rsi_last(
    closes: np.ndarray, period: int = RSI_PERIOD
) -> tuple[float | None, float | None]:
    """Return (RSI_t, RSI_{t-1}) using Wilder smoothing. None if insufficient history."""
    if period <= 0 or len(closes) < period + 2:
        return None, None
    deltas = np.diff(closes.astype(float))
    if len(deltas) < period + 1:
        return None, None
    gains = np.clip(deltas, 0.0, None)
    losses = np.clip(-deltas, 0.0, None)

    def _rsi_at(end_idx: int) -> float | None:
        # end_idx is inclusive index into deltas; need period points ending there
        if end_idx + 1 < period:
            return None
        seed_g = float(np.mean(gains[:period]))
        seed_l = float(np.mean(losses[:period]))
        avg_g, avg_l = seed_g, seed_l
        for i in range(period, end_idx + 1):
            avg_g = (avg_g * (period - 1) + float(gains[i])) / period
            avg_l = (avg_l * (period - 1) + float(losses[i])) / period
        if avg_l == 0:
            return 100.0 if avg_g > 0 else 50.0
        rs = avg_g / avg_l
        return float(100.0 - 100.0 / (1.0 + rs))

    last_i = len(deltas) - 1
    rsi_t = _rsi_at(last_i)
    rsi_prev = _rsi_at(last_i - 1)
    return rsi_t, rsi_prev


def relative_strength(stock_ret: float | None, bench_ret: float | None) -> float | None:
    if stock_ret is None or bench_ret is None:
        return None
    if bench_ret <= -1.0:
        return None
    return float((1.0 + stock_ret) / (1.0 + bench_ret) - 1.0)


def dist_from_high(close: float, high: float) -> float | None:
    if high <= 0 or not np.isfinite(close) or not np.isfinite(high):
        return None
    return float(1.0 - close / high)


def median_dollar_volume(closes: np.ndarray, volumes: np.ndarray, window: int) -> float | None:
    n = min(len(closes), len(volumes), window)
    if n < window:
        return None
    dv = closes[-window:] * volumes[-window:]
    if np.any(~np.isfinite(dv)):
        return None
    return float(np.median(dv))


def mean_volume(volumes: np.ndarray, window: int) -> float | None:
    if len(volumes) < window or window <= 0:
        return None
    w = volumes[-window:]
    if np.any(~np.isfinite(w)):
        return None
    return float(np.mean(w))


def volume_rising(volumes: np.ndarray, window: int) -> bool | None:
    if len(volumes) < 2 * window:
        return None
    recent = float(np.sum(volumes[-window:]))
    prior = float(np.sum(volumes[-2 * window : -window]))
    if not np.isfinite(recent) or not np.isfinite(prior):
        return None
    return recent > prior


@dataclass(frozen=True)
class SymbolFeatures:
    """Deterministic as-of feature panel for one name. Missing values are None."""

    symbol: str
    name: str | None = None
    sector: str | None = None
    category: str | None = None
    close: float | None = None
    sma200: float | None = None
    rsi14: float | None = None
    rsi14_prev: float | None = None
    ret_5d: float | None = None
    ret_20d: float | None = None
    ret_60d: float | None = None
    rs_20_vs_spy: float | None = None
    rs_60_vs_spy: float | None = None
    rs_accel: float | None = None
    dist_52w: float | None = None
    high_52w: float | None = None
    adv20: float | None = None
    rvol20: float | None = None
    volume_rising_20d: bool | None = None
    market_cap: float | None = None


@dataclass(frozen=True)
class GapRow:
    rank: int
    symbol: str
    price: float | None = None
    gap_pct: float | None = None
    premarket_volume: int | None = None
    catalyst: str | None = None
    headlines: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class MomCoreRow:
    rank: int
    symbol: str
    name: str | None = None
    sector: str | None = None
    score: float | None = None
    market_cap: float | None = None
    adv20: float | None = None
    close: float | None = None


def features_from_series(
    *,
    symbol: str,
    closes: np.ndarray,
    volumes: np.ndarray,
    spy_closes: np.ndarray,
    name: str | None = None,
    sector: str | None = None,
    category: str | None = None,
    market_cap: float | None = None,
) -> SymbolFeatures:
    close = float(closes[-1]) if len(closes) else None
    rsi_t, rsi_prev = wilder_rsi_last(closes)
    spy_ret_20 = simple_return(spy_closes, 20) if len(spy_closes) else None
    spy_ret_60 = simple_return(spy_closes, 60) if len(spy_closes) else None
    ret_20 = simple_return(closes, 20)
    ret_60 = simple_return(closes, 60)
    rs20 = relative_strength(ret_20, spy_ret_20)
    rs60 = relative_strength(ret_60, spy_ret_60)
    accel = None if rs20 is None or rs60 is None else float(rs20 - rs60)
    high = float(np.max(closes[-252:])) if len(closes) >= 252 else None
    last_vol = float(volumes[-1]) if len(volumes) else None
    avg_vol = mean_volume(volumes, 20)
    rvol = None
    if last_vol is not None and avg_vol is not None and avg_vol > 0:
        rvol = last_vol / avg_vol
    return SymbolFeatures(
        symbol=symbol,
        name=name,
        sector=sector,
        category=category,
        close=close,
        sma200=sma_last(closes, SMA_TREND),
        rsi14=rsi_t,
        rsi14_prev=rsi_prev,
        ret_5d=simple_return(closes, 5),
        ret_20d=ret_20,
        ret_60d=ret_60,
        rs_20_vs_spy=rs20,
        rs_60_vs_spy=rs60,
        rs_accel=accel,
        dist_52w=dist_from_high(close, high) if close is not None and high is not None else None,
        high_52w=high,
        adv20=median_dollar_volume(closes, volumes, 20),
        rvol20=rvol,
        volume_rising_20d=volume_rising(volumes, 20),
        market_cap=market_cap,
    )
