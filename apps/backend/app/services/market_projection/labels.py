"""PIT labeler for MKT-PROJ-001 (pre-registration §2, FR-002).

Pure functions over a daily-bar DataFrame (index = session date, columns
open/high/low/close/volume). The PIT rule is structural: every function takes
the *day being labeled* and slices strictly to prior sessions for threshold
inputs — feeding data past the day cannot change the output (unit-tested).
"""

from __future__ import annotations

from datetime import date

import pandas as pd

from app.services.market_projection.schemas import (
    ATR_WINDOW,
    THRESHOLD_ATR_MULT,
    THRESHOLD_FLOOR_PCT,
    Label,
)


def atr_pct_through(daily: pd.DataFrame, through: date, window: int = ATR_WINDOW) -> float | None:
    """ATR(window) as % of close, using sessions **up to and including** ``through``.

    Callers enforce PIT by passing the last completed session (t−1 for both
    horizons — pre-registration §2). Returns None with insufficient history."""
    df = daily.loc[daily.index <= through]
    if len(df) < window + 1:
        return None
    prev_close = df["close"].shift(1)
    tr = pd.concat(
        [df["high"] - df["low"], (df["high"] - prev_close).abs(), (df["low"] - prev_close).abs()],
        axis=1,
    ).max(axis=1)
    atr = tr.rolling(window).mean().iloc[-1]
    close = df["close"].iloc[-1]
    if pd.isna(atr) or not close:
        return None
    return float(atr / close * 100.0)


def prior_session(daily: pd.DataFrame, day: date) -> date | None:
    """The last completed regular session strictly before ``day``."""
    prior = daily.index[daily.index < day]
    return None if len(prior) == 0 else prior[-1]


def threshold_pct_for(daily: pd.DataFrame, day: date) -> float | None:
    """``threshold_asof_forecast_date`` for labeling ``day``'s move (both horizons):
    max(0.60%, 0.50 × ATR20_pct through t−1). None if history is insufficient."""
    prior = prior_session(daily, day)
    if prior is None:
        return None
    atr = atr_pct_through(daily, prior)
    if atr is None:
        return None
    return max(THRESHOLD_FLOOR_PCT, THRESHOLD_ATR_MULT * atr)


def label_for(realized_return_pct: float, threshold_pct: float) -> Label:
    """UP / DOWN / NEUTRAL per the frozen rule (>= threshold in either direction)."""
    if realized_return_pct >= threshold_pct:
        return Label.UP
    if realized_return_pct <= -threshold_pct:
        return Label.DOWN
    return Label.NEUTRAL


def preopen_realized_return(daily: pd.DataFrame, day: date) -> float | None:
    """PRE_OPEN_TODAY target: open-to-close on ``day`` (the v0.2 leakage fix —
    never close-to-close)."""
    if day not in daily.index:
        return None
    row = daily.loc[day]
    if not row["open"]:
        return None
    return float((row["close"] - row["open"]) / row["open"] * 100.0)


def preclose_realized_return(daily: pd.DataFrame, day: date) -> float | None:
    """PRE_CLOSE_TOMORROW target measured for forecast day ``day``: close(t+1)
    vs close(t). None when t or t+1 is absent (label matures next session)."""
    if day not in daily.index:
        return None
    later = daily.index[daily.index > day]
    if len(later) == 0:
        return None
    close_t = daily.loc[day, "close"]
    close_t1 = daily.loc[later[0], "close"]
    if not close_t:
        return None
    return float((close_t1 - close_t) / close_t * 100.0)
