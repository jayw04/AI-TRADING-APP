"""PRE_CLOSE_TOMORROW features as of close−15m (pre-registration §5, FR-003).

Pure function over minute bars + the shared daily context. PIT is structural:
every minute frame is sliced to ``<= cutoff`` INSIDE this module before any
computation, so no final-session high/low/close can leak into the feature set
(final review edit 7; unit-tested by truncated-vs-full equality). The
time-of-day-matched volume baseline is precomputed by the caller from prior
sessions only.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import date, datetime

import pandas as pd

from app.services.market_projection.features_preopen import daily_context_features
from app.services.market_projection.schemas import (
    LATE_DAY_START_ET,
    PRECLOSE_FEATURES,
    SECTOR_BASKET,
)


def _asof(minute: pd.DataFrame, cutoff: datetime) -> pd.DataFrame:
    """The structural PIT slice: nothing past the forecast timestamp exists."""
    if minute.empty:
        return minute
    return minute.loc[minute.index <= cutoff]


def _open_to_cutoff_ret(minute: pd.DataFrame, cutoff: datetime) -> float | None:
    df = _asof(minute, cutoff)
    if df.empty or not df["open"].iloc[0]:
        return None
    return float((df["close"].iloc[-1] / df["open"].iloc[0] - 1) * 100.0)


def preclose_features(
    minute_by_symbol: Mapping[str, pd.DataFrame],
    daily_spy: pd.DataFrame,
    *,
    day: date,
    cutoff: datetime,
    spy_cum_vol_20d_tod_avg: float | None,
) -> dict[str, float | None]:
    """The frozen PRE_CLOSE manifest for ``day`` at ``cutoff`` (= close−15m ET).

    ``minute_by_symbol``: RTH minute bars for SPY/QQQ/IWM + the sector basket,
    indexed by tz-aware ET timestamps; frames may extend past the cutoff — they
    are sliced here. ``spy_cum_vol_20d_tod_avg``: the caller-computed average of
    the 20 prior sessions' SPY cumulative volume through the same time of day
    (strictly prior sessions — pre-registration §5)."""
    out = daily_context_features(daily_spy, day)
    if not out:
        return {}

    spy = _asof(minute_by_symbol.get("SPY", pd.DataFrame()), cutoff)
    if spy.empty:
        return {}

    out["spy_intraday_ret"] = _open_to_cutoff_ret(minute_by_symbol.get("SPY", pd.DataFrame()), cutoff)
    out["qqq_intraday_ret"] = _open_to_cutoff_ret(minute_by_symbol.get("QQQ", pd.DataFrame()), cutoff)
    out["iwm_intraday_ret"] = _open_to_cutoff_ret(minute_by_symbol.get("IWM", pd.DataFrame()), cutoff)

    # late-day return: 14:30 ET → cutoff (None on half days, where 14:30 > cutoff)
    late_start = pd.Timestamp(f"{day} {LATE_DAY_START_ET}", tz=cutoff.tzinfo)
    late = spy.loc[spy.index >= late_start]
    out["spy_late_day_ret"] = (
        float((late["close"].iloc[-1] / late["open"].iloc[0] - 1) * 100.0) if len(late) else None
    )

    # sector breadth through the cutoff; missing sectors shrink the denominator
    ups, covered = 0, 0
    for sym in SECTOR_BASKET:
        r = _open_to_cutoff_ret(minute_by_symbol.get(sym, pd.DataFrame()), cutoff)
        if r is None:
            continue
        covered += 1
        ups += 1 if r > 0 else 0
    out["sector_breadth"] = (ups / covered) if covered else None
    out["up_sector_count"] = float(ups) if covered else None
    out["sector_coverage_count"] = float(covered)

    cum_vol = float(spy["volume"].sum())
    out["spy_volume_vs_20d_tod"] = (
        cum_vol / spy_cum_vol_20d_tod_avg
        if spy_cum_vol_20d_tod_avg and spy_cum_vol_20d_tod_avg > 0
        else None
    )

    # 5-min realized vol through the cutoff (annualized %, per the manifest)
    five = spy["close"].resample("5min").last().dropna()
    r5 = five.pct_change().dropna()
    out["spy_intraday_vol"] = (
        float(r5.std() * ((78 * 252) ** 0.5) * 100) if len(r5) >= 6 else None
    )

    hi, lo, last = float(spy["high"].max()), float(spy["low"].min()), float(spy["close"].iloc[-1])
    prior = daily_spy.loc[daily_spy.index < day]
    prev_close = float(prior["close"].iloc[-1]) if len(prior) else None
    out["spy_hl_range_pct"] = ((hi - lo) / prev_close * 100.0) if prev_close else None
    out["fade_recovery"] = ((last - lo) / (hi - lo)) if hi > lo else None

    return {k: out.get(k) for k in PRECLOSE_FEATURES}


def cum_volume_through_tod(minute: pd.DataFrame, day: date, cutoff_time) -> float | None:
    """One session's cumulative volume through a wall-clock time of day — the
    building block for the 20-session time-of-day-matched baseline."""
    if minute.empty:
        return None
    day_bars = minute.loc[[ts for ts in minute.index if ts.date() == day]]
    if day_bars.empty:
        return None
    upto = day_bars.loc[[ts for ts in day_bars.index if ts.time() <= cutoff_time]]
    return float(upto["volume"].sum()) if len(upto) else None
