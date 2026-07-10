"""PRE_OPEN_TODAY features as of 09:20 ET (pre-registration §5, FR-004).

Pure function over prior daily bars + externally computed premarket gaps. PIT
is structural: only sessions **strictly before** ``day`` are used from the
daily frame (sliced internally, so poisoned future rows cannot leak), and the
gap inputs are the caller's responsibility to compute from ≤09:20 data
(``dataset.py`` uses premarket minute bars; live inference uses IEX snapshots
with the same quality flags — the recorded provenance difference).
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import date

import pandas as pd

from app.services.market_projection.labels import atr_pct_through
from app.services.market_projection.schemas import ATR_WINDOW, PREOPEN_FEATURES

REGIME_VOL_LOOKBACK = 252


def daily_context_features(daily_spy: pd.DataFrame, day: date) -> dict[str, float | None]:
    """The daily-bar feature block shared by both horizons — everything through t−1."""
    df = daily_spy.loc[daily_spy.index < day]
    if len(df) < 2:
        return {}
    close = df["close"]
    ret = close.pct_change()
    out: dict[str, float | None] = {
        "spy_ret_1d": float(ret.iloc[-1] * 100) if pd.notna(ret.iloc[-1]) else None,
        "spy_ret_5d": float((close.iloc[-1] / close.iloc[-6] - 1) * 100) if len(close) >= 6 else None,
        "spy_realized_vol_20d": float(ret.tail(20).std() * (252 ** 0.5) * 100)
        if len(ret.dropna()) >= 20 else None,
        "atr20_pct": atr_pct_through(df, df.index[-1], ATR_WINDOW),
    }
    for n in (20, 50, 200):
        out[f"spy_dist_ma{n}"] = (
            float((close.iloc[-1] / close.tail(n).mean() - 1) * 100) if len(close) >= n else None
        )
    out["regime_trend"] = (
        1.0 if (len(close) >= 200 and close.iloc[-1] > close.tail(200).mean()) else 0.0
    )
    # ATR quintile within the trailing year of ATR readings (PIT: all through t−1)
    atr_series = _atr_pct_series(df).tail(REGIME_VOL_LOOKBACK).dropna()
    cur = out["atr20_pct"]
    out["regime_vol"] = (
        float(min(4, int((atr_series < cur).mean() * 5))) if cur is not None and len(atr_series) >= 60
        else None
    )
    return out


def _atr_pct_series(df: pd.DataFrame) -> pd.Series:
    prev_close = df["close"].shift(1)
    tr = pd.concat(
        [df["high"] - df["low"], (df["high"] - prev_close).abs(), (df["low"] - prev_close).abs()],
        axis=1,
    ).max(axis=1)
    return tr.rolling(ATR_WINDOW).mean() / df["close"] * 100.0


def preopen_features(
    daily_spy: pd.DataFrame,
    *,
    day: date,
    gaps: Mapping[str, tuple[float | None, int]],
) -> dict[str, float | None]:
    """The frozen PRE_OPEN manifest for ``day``.

    ``gaps``: symbol → (gap_pct vs prior close computed from ≤09:20 data, quality =
    number of premarket prints/bars behind it; 0 quality ⇒ gap None)."""
    out = daily_context_features(daily_spy, day)
    if not out:
        return {}
    for sym in ("spy", "qqq", "iwm"):
        gap, quality = gaps.get(sym.upper(), (None, 0))
        out[f"{sym}_gap_pct_qf"] = gap if quality > 0 else None
        out[f"{sym}_gap_quality"] = float(quality)
    return {k: out.get(k) for k in PREOPEN_FEATURES}
