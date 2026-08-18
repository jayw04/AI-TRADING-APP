"""Opening-range buy/sell/stop levels — shared by Range Trader + /range-levels UI.

Everyday rule (owner 2026-07-27): the Range Levels UI must always be able to show
**today's** ET levels after the opening-range window closes. Prefer the strategy's
published ``range_levels`` INFO signal; if missing (cold start / restore / missed
OR window), compute the same formula from 1Min bars:

  buy  = OR low
  sell = OR high
  stop = OR low × (1 − stop_buffer_pct)
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo

import pandas as pd

ET = ZoneInfo("America/New_York")
SESSION_OPEN = time(9, 30)
DEFAULT_OR_MINUTES = 30
DEFAULT_STOP_BUFFER = 0.005


def opening_range_window(
    day: date,
    *,
    opening_range_minutes: int = DEFAULT_OR_MINUTES,
) -> tuple[datetime, datetime]:
    """Return tz-aware ET ``[start, end)`` for today's opening-range window."""
    start = datetime.combine(day, SESSION_OPEN, tzinfo=ET)
    end = start + timedelta(minutes=int(opening_range_minutes))
    return start, end


def levels_from_or_bars(
    df: pd.DataFrame,
    *,
    stop_buffer_pct: float = DEFAULT_STOP_BUFFER,
) -> tuple[float, float, float] | None:
    """Derive ``(buy, sell, stop)`` from OR-window bars (columns ``h``/``l``).

    Returns ``None`` when the frame is empty or the range is degenerate.
    """
    if df is None or df.empty:
        return None
    cols = {str(c).lower(): c for c in df.columns}
    hcol = cols.get("h") or cols.get("high")
    lcol = cols.get("l") or cols.get("low")
    if hcol is None or lcol is None:
        return None
    hi = float(df[hcol].max())
    lo = float(df[lcol].min())
    if not (hi > lo > 0):
        return None
    buf = float(stop_buffer_pct)
    if buf < 0 or buf >= 1:
        buf = DEFAULT_STOP_BUFFER
    return (round(lo, 4), round(hi, 4), round(lo * (1.0 - buf), 4))


def filter_bars_to_window(
    df: pd.DataFrame,
    start: datetime,
    end: datetime,
) -> pd.DataFrame:
    """Keep bars whose timestamp ``t`` is in ``[start, end)`` (tz-normalized)."""
    if df is None or df.empty or "t" not in df.columns:
        return df.iloc[0:0].copy() if df is not None else pd.DataFrame()
    t = pd.to_datetime(df["t"], utc=True)
    start_utc = start.astimezone(ZoneInfo("UTC"))
    end_utc = end.astimezone(ZoneInfo("UTC"))
    mask = (t >= start_utc) & (t < end_utc)
    return df.loc[mask].reset_index(drop=True)


def params_or_defaults(params: dict[str, Any] | None) -> tuple[int, float]:
    p = params or {}
    minutes = int(p.get("opening_range_minutes", DEFAULT_OR_MINUTES) or DEFAULT_OR_MINUTES)
    buf = float(p.get("stop_buffer_pct", DEFAULT_STOP_BUFFER) or DEFAULT_STOP_BUFFER)
    return max(1, minutes), buf


async def compute_opening_levels_from_cache(
    bar_cache: Any,
    symbol: str,
    *,
    day: date | None = None,
    opening_range_minutes: int = DEFAULT_OR_MINUTES,
    stop_buffer_pct: float = DEFAULT_STOP_BUFFER,
) -> tuple[float, float, float] | None:
    """Fetch 1Min bars for the OR window and return ``(buy, sell, stop)`` or ``None``."""
    if bar_cache is None:
        return None
    et_day = day or datetime.now(ET).date()
    start, end = opening_range_window(et_day, opening_range_minutes=opening_range_minutes)
    # Still forming — callers should not compute final levels yet.
    if datetime.now(ET) < end:
        return None
    try:
        # get_bars is inclusive on ``end``; filter keeps ``[start, end)`` to match
        # the live strategy (SESSION_OPEN <= tod < or_end).
        df = await bar_cache.get_bars(symbol.upper(), "1Min", start, end)
    except Exception:  # noqa: BLE001 — UI/trading must degrade, not crash
        return None
    windowed = filter_bars_to_window(df, start, end)
    return levels_from_or_bars(windowed, stop_buffer_pct=stop_buffer_pct)
