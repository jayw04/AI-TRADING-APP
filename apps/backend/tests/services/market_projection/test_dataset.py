"""MKT-PROJ-001 dataset-builder tests: row shape, targets, exclusions (synthetic, no network)."""

from __future__ import annotations

from datetime import date, time, timedelta

import pandas as pd
import pytest

from app.services.market_projection import dataset as ds
from app.services.market_projection.schemas import FEATURE_VERSION, ProjectionType

ET = "America/New_York"
DAYS = [date(2026, 7, 6), date(2026, 7, 7), date(2026, 7, 8), date(2026, 7, 9)]


def _sessions(days: list[date]) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "open_et": [pd.Timestamp(f"{d} 09:30", tz=ET) for d in days],
            "close_et": [pd.Timestamp(f"{d} 16:00", tz=ET) for d in days],
        },
        index=days,
    )


def _daily(days_back: int = 260) -> pd.DataFrame:
    all_days = sorted(
        d for d in (DAYS[-1] - timedelta(days=i) for i in range(days_back * 2))
        if d.weekday() < 5
    )[-days_back:]
    return pd.DataFrame(
        {"open": 100.0, "high": 100.7, "low": 99.3, "close": 100.0, "volume": 1e6},
        index=all_days,
    )


def _minute_for(days: list[date]) -> pd.DataFrame:
    frames = []
    for d in days:
        idx = pd.date_range(f"{d} 09:30", f"{d} 16:00", freq="min", tz=ET)
        frames.append(pd.DataFrame(
            {"open": 100.0, "high": 100.1, "low": 99.9, "close": 100.0, "volume": 1000.0},
            index=idx,
        ))
    return pd.concat(frames)


def test_build_rows_shape_and_versions() -> None:
    sessions = _sessions(DAYS)
    daily = {"SPY": _daily()}
    minute = {"SPY": _minute_for(DAYS)}
    cum = ds.spy_cum_volume_table(minute["SPY"], sessions)
    rows = ds.build_rows_for_sessions(sessions, daily, minute, spy_cum_vol_at=cum)
    assert len(rows) == 2 * len(DAYS)  # one row per horizon per session
    keys = {(r["date"], r["projection_type"]) for r in rows}
    assert len(keys) == len(rows)      # unique per (date, horizon)
    assert all(r["feature_version"] == FEATURE_VERSION for r in rows)


def test_preclose_label_not_matured_on_last_session() -> None:
    sessions = _sessions(DAYS)
    daily = {"SPY": _daily()}
    minute = {"SPY": _minute_for(DAYS)}
    rows = ds.build_rows_for_sessions(
        sessions, daily, minute,
        spy_cum_vol_at=ds.spy_cum_volume_table(minute["SPY"], sessions),
        only_days=[DAYS[-1]],
    )
    preclose = next(r for r in rows
                    if r["projection_type"] == ProjectionType.PRE_CLOSE_TOMORROW.value)
    # daily frame ends at DAYS[-1]: close(t+1) does not exist yet
    assert preclose["valid_for_training"] is False
    assert preclose["exclusion_reason"] == "label_not_matured"


def test_missing_spy_minute_data_excludes_preclose_row() -> None:
    sessions = _sessions(DAYS)
    daily = {"SPY": _daily()}
    rows = ds.build_rows_for_sessions(
        sessions, daily, {"SPY": pd.DataFrame()}, spy_cum_vol_at={}, only_days=[DAYS[1]]
    )
    preclose = next(r for r in rows
                    if r["projection_type"] == ProjectionType.PRE_CLOSE_TOMORROW.value)
    assert preclose["valid_for_training"] is False
    assert preclose["exclusion_reason"] == "missing_features"


def test_premarket_gaps_quality_flags() -> None:
    day = DAYS[1]
    daily = {"SPY": _daily(), "QQQ": _daily(), "IWM": _daily()}
    pre_idx = pd.date_range(f"{day} 08:00", f"{day} 09:15", freq="min", tz=ET)
    minute = {"SPY": pd.DataFrame(
        {"open": 101.0, "high": 101.1, "low": 100.9, "close": 101.0, "volume": 10.0},
        index=pre_idx,
    )}
    gaps = ds.premarket_gaps(minute, daily, day, forecast_et=time(9, 20))
    assert gaps["SPY"][0] == pytest.approx(1.0)   # 101 vs prior close 100
    assert gaps["SPY"][1] == len(pre_idx)
    assert gaps["QQQ"] == (None, 0)               # no premarket prints → flagged, not faked


def test_spy_cum_volume_table_time_of_day_keys() -> None:
    sessions = _sessions(DAYS[:2])
    minute = _minute_for(DAYS[:2])
    table = ds.spy_cum_volume_table(minute, sessions)
    # full-day cutoff 15:45 → 376 bars of 1000 shares... through 15:45 inclusive
    v = table[(DAYS[0], time(15, 45))]
    assert v == pytest.approx(1000.0 * len(
        [ts for ts in minute.index if ts.date() == DAYS[0] and ts.time() <= time(15, 45)]
    ))
