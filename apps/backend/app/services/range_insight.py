"""Range Insight (P8 §5): a per-symbol statistical range panel.

Deterministic, descriptive summaries of a symbol's recent daily behavior — ATR,
typical open→high / open→low moves, support/resistance, an 80% confidence band
for today's high/low, today's range so far, and a range-bound vs trending
classification. **Descriptive, not predictive** (Direction Decision 2): the
payload always carries a disclaimer and the service never forecasts.

Never raises — insufficiency / degeneracy is reported via ``status``.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

import pandas as pd

from app.utils.time import EASTERN

WINDOW = 20  # ideal completed-daily-bar window
MIN_BARS = 10  # fewer completed bars than this → insufficient_data
_FETCH_DAYS = 120  # calendar lookback to gather ~WINDOW trading days

STATUS_OK = "ok"
STATUS_INSUFFICIENT = "insufficient_data"

DISCLAIMER = "Statistical descriptions of recent behavior, not forecasts."


@dataclass(frozen=True)
class MoveStats:
    mean: float
    median: float
    p80: float


@dataclass(frozen=True)
class Band:
    low: float
    high: float


@dataclass(frozen=True)
class RangeInsight:
    symbol: str
    status: str
    bars_used: int
    low_confidence: bool
    as_of: datetime | None
    anchor: float | None
    anchor_source: str | None  # "today_open" | "last_close"
    last_close: float | None
    atr20: float | None
    atr20_pct: float | None
    typical_move_up: MoveStats | None
    typical_move_down: MoveStats | None
    support: float | None
    resistance: float | None
    high_band: Band | None
    low_band: Band | None
    intraday_range: float | None
    classification: str | None  # "range_bound" | "trending" | "mixed"
    efficiency_ratio: float | None
    disclaimer: str = DISCLAIMER


def _insufficient(
    symbol: str, *, bars_used: int, as_of: datetime | None
) -> RangeInsight:
    return RangeInsight(
        symbol=symbol,
        status=STATUS_INSUFFICIENT,
        bars_used=bars_used,
        low_confidence=True,
        as_of=as_of,
        anchor=None,
        anchor_source=None,
        last_close=None,
        atr20=None,
        atr20_pct=None,
        typical_move_up=None,
        typical_move_down=None,
        support=None,
        resistance=None,
        high_band=None,
        low_band=None,
        intraday_range=None,
        classification=None,
        efficiency_ratio=None,
    )


def _move_stats(series: pd.Series) -> MoveStats:
    return MoveStats(
        mean=float(series.mean()),
        median=float(series.quantile(0.5)),
        p80=float(series.quantile(0.8)),
    )


def _efficiency_ratio(closes: pd.Series) -> float:
    if len(closes) < 2:
        return 0.0
    net = abs(float(closes.iloc[-1]) - float(closes.iloc[0]))
    path = float(closes.diff().abs().sum())
    return net / path if path > 0 else 0.0


def _classify(er: float) -> str:
    if er < 0.3:
        return "range_bound"
    if er > 0.5:
        return "trending"
    return "mixed"


def _as_et_date(ts: Any) -> Any:
    """ET calendar date of a (tz-aware) bar timestamp."""
    dt = pd.Timestamp(ts)
    if dt.tzinfo is None:
        dt = dt.tz_localize("UTC")
    return dt.tz_convert(EASTERN).date()


def range_insight_from_bars(
    symbol: str, bars: pd.DataFrame, now: datetime
) -> RangeInsight:
    """Pure core: compute Range Insight from a daily-bar frame (cols t,o,h,l,c,v)."""
    if bars is None or bars.empty:
        return _insufficient(symbol, bars_used=0, as_of=None)

    bars = bars.sort_values("t").reset_index(drop=True)
    as_of = bars["t"].iloc[-1]
    today_et = now.astimezone(EASTERN).date()

    # Separate today's (partial) bar — it must not pollute the completed-day
    # distributions; it feeds only the anchor + intraday range.
    has_today = _as_et_date(bars["t"].iloc[-1]) == today_et
    today_bar = bars.iloc[-1] if has_today else None
    hist = bars.iloc[:-1] if has_today else bars

    if len(hist) < MIN_BARS:
        return _insufficient(symbol, bars_used=len(hist), as_of=as_of)

    stats = hist.tail(WINDOW)
    bars_used = len(stats)

    last_close = float(hist["c"].iloc[-1])
    up = stats["h"] - stats["o"]  # open → high
    down = stats["o"] - stats["l"]  # open → low

    # ATR(20): mean of the last WINDOW valid true ranges.
    prev_c = hist["c"].shift(1)
    tr = pd.concat(
        [hist["h"] - hist["l"], (hist["h"] - prev_c).abs(), (hist["l"] - prev_c).abs()],
        axis=1,
    ).max(axis=1)
    atr20 = float(tr.dropna().tail(WINDOW).mean())

    if today_bar is not None:
        anchor = float(today_bar["o"])
        anchor_source = "today_open"
        intraday_range: float | None = float(today_bar["h"]) - float(today_bar["l"])
    else:
        anchor = last_close
        anchor_source = "last_close"
        intraday_range = None

    high_band = Band(
        low=anchor + float(up.quantile(0.1)),
        high=anchor + float(up.quantile(0.9)),
    )
    low_band = Band(
        low=anchor - float(down.quantile(0.9)),
        high=anchor - float(down.quantile(0.1)),
    )

    er = _efficiency_ratio(stats["c"])

    return RangeInsight(
        symbol=symbol,
        status=STATUS_OK,
        bars_used=bars_used,
        low_confidence=bars_used < WINDOW,
        as_of=as_of,
        anchor=anchor,
        anchor_source=anchor_source,
        last_close=last_close,
        atr20=atr20,
        atr20_pct=(atr20 / last_close if last_close else None),
        typical_move_up=_move_stats(up),
        typical_move_down=_move_stats(down),
        support=float(stats["l"].min()),
        resistance=float(stats["h"].max()),
        high_band=high_band,
        low_band=low_band,
        intraday_range=intraday_range,
        classification=_classify(er),
        efficiency_ratio=er,
    )


async def compute_range_insight(
    symbol: str, *, bar_cache: Any, now: datetime
) -> RangeInsight:
    """Fetch daily bars and compute Range Insight. Never raises."""
    symbol = symbol.upper()
    start = now - timedelta(days=_FETCH_DAYS)
    try:
        bars = await bar_cache.get_bars(symbol, "1Day", start, now)
    except Exception:
        return _insufficient(symbol, bars_used=0, as_of=None)
    return range_insight_from_bars(symbol, bars, now)
