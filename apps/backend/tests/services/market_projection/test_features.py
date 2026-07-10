"""MKT-PROJ-001 feature-builder tests: PIT truncation equality + frozen manifest math."""

from __future__ import annotations

from datetime import date, timedelta

import pandas as pd
import pytest

from app.services.market_projection.features_preclose import preclose_features
from app.services.market_projection.features_preopen import preopen_features
from app.services.market_projection.schemas import (
    PRECLOSE_FEATURES,
    PREOPEN_FEATURES,
    SECTOR_BASKET,
)

ET = "America/New_York"
DAY = date(2026, 7, 9)  # a Thursday


def _daily(n: int = 260, last: float = 100.0) -> pd.DataFrame:
    days = sorted(
        d for d in (DAY - timedelta(days=i) for i in range(1, n * 2)) if d.weekday() < 5
    )[-n:]
    closes = [last - 0.01 * (len(days) - 1 - i) for i in range(len(days))]  # gentle uptrend
    return pd.DataFrame(
        {"open": closes, "high": [c + 0.5 for c in closes], "low": [c - 0.5 for c in closes],
         "close": closes, "volume": 1_000_000.0},
        index=days,
    )


def _minute(day: date, *, o: float, c: float, bars: int = 375, vol: float = 1000.0) -> pd.DataFrame:
    """RTH minute bars 09:30→close, linear from o to c."""
    idx = pd.date_range(f"{day} 09:30", periods=bars, freq="min", tz=ET)
    px = [o + (c - o) * i / (bars - 1) for i in range(bars)]
    return pd.DataFrame(
        {"open": px, "high": [p + 0.02 for p in px], "low": [p - 0.02 for p in px],
         "close": px, "volume": vol},
        index=idx,
    )


CUTOFF = pd.Timestamp(f"{DAY} 15:45", tz=ET)


def test_preopen_manifest_and_gap_quality() -> None:
    daily = _daily()
    out = preopen_features(
        daily, day=DAY,
        gaps={"SPY": (0.8, 12), "QQQ": (1.1, 9), "IWM": (None, 0)},
    )
    assert tuple(out.keys()) == PREOPEN_FEATURES
    assert out["spy_gap_pct_qf"] == 0.8
    assert out["iwm_gap_pct_qf"] is None          # zero quality → flagged missing, never faked
    assert out["iwm_gap_quality"] == 0.0
    assert out["regime_trend"] == 1.0             # gentle uptrend > MA200
    assert out["spy_dist_ma20"] == pytest.approx(
        (daily["close"].iloc[-1] / daily["close"].tail(20).mean() - 1) * 100
    )


def test_preopen_is_pit_future_row_cannot_leak() -> None:
    daily = _daily()
    poisoned = daily.copy()
    poisoned.loc[DAY] = [500.0, 500.0, 500.0, 500.0, 1.0]  # absurd same-day row
    a = preopen_features(daily, day=DAY, gaps={"SPY": (0.5, 5)})
    b = preopen_features(poisoned, day=DAY, gaps={"SPY": (0.5, 5)})
    assert a == b


def test_preclose_manifest_and_math() -> None:
    daily = _daily()
    minute = {"SPY": _minute(DAY, o=100.0, c=101.0)}
    for i, sym in enumerate(SECTOR_BASKET[:8]):  # 8 of 11 sectors present
        minute[sym] = _minute(DAY, o=50.0, c=50.5 if i < 5 else 49.5)  # 5 up, 3 down
    out = preclose_features(minute, daily, day=DAY, cutoff=CUTOFF,
                            spy_cum_vol_20d_tod_avg=300_000.0)
    assert tuple(out.keys()) == PRECLOSE_FEATURES
    assert out["sector_coverage_count"] == 8.0    # missing sectors shrink the denominator
    assert out["up_sector_count"] == 5.0
    assert out["sector_breadth"] == pytest.approx(5 / 8)
    assert out["qqq_intraday_ret"] is None        # no QQQ minute data → None, not fabricated
    assert out["fade_recovery"] == pytest.approx(1.0, abs=0.05)  # closing at the high so far
    assert out["spy_volume_vs_20d_tod"] == pytest.approx(
        minute["SPY"].loc[:CUTOFF, "volume"].sum() / 300_000.0
    )


def test_preclose_truncation_equality_no_final_session_leak() -> None:
    """Final-review edit 7: bars past close−15m must not change ANY feature —
    including a fake end-of-day spike that would move high/low/fade if leaked."""
    daily = _daily()
    full = _minute(DAY, o=100.0, c=101.0)
    spiked = full.copy()
    late = pd.Timestamp(f"{DAY} 15:55", tz=ET)
    spiked.loc[late] = [140.0, 150.0, 90.0, 140.0, 9e9]  # absurd post-cutoff bar
    kw = dict(day=DAY, cutoff=CUTOFF, spy_cum_vol_20d_tod_avg=300_000.0)
    a = preclose_features({"SPY": full}, daily, **kw)
    b = preclose_features({"SPY": spiked.sort_index()}, daily, **kw)
    assert a == b


def test_preclose_late_day_return_window() -> None:
    daily = _daily()
    out = preclose_features({"SPY": _minute(DAY, o=100.0, c=101.0)}, daily,
                            day=DAY, cutoff=CUTOFF, spy_cum_vol_20d_tod_avg=None)
    # linear 100→101 over 09:30–15:45: 14:30 price ≈ 100.80 → late-day ≈ +0.199%
    assert out["spy_late_day_ret"] == pytest.approx(0.199, abs=0.02)
    assert out["spy_volume_vs_20d_tod"] is None   # no baseline → None, not fabricated


def test_preclose_half_day_cutoff_before_1430_gives_no_late_day() -> None:
    half_cutoff = pd.Timestamp(f"{DAY} 12:45", tz=ET)
    out = preclose_features({"SPY": _minute(DAY, o=100.0, c=101.0)}, _daily(),
                            day=DAY, cutoff=half_cutoff, spy_cum_vol_20d_tod_avg=None)
    assert out["spy_late_day_ret"] is None
