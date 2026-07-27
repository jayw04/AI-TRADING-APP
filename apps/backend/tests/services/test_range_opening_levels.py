"""Unit tests for opening-range level helpers (shared by UI + Range Trader)."""

from __future__ import annotations

from datetime import date, datetime
from zoneinfo import ZoneInfo

import pandas as pd

from app.services.range_opening_levels import (
    filter_bars_to_window,
    levels_from_or_bars,
    opening_range_window,
    params_or_defaults,
)

ET = ZoneInfo("America/New_York")


def test_params_or_defaults() -> None:
    assert params_or_defaults(None) == (30, 0.005)
    assert params_or_defaults({"opening_range_minutes": 15, "stop_buffer_pct": 0.01}) == (
        15,
        0.01,
    )


def test_opening_range_window_15m() -> None:
    start, end = opening_range_window(date(2026, 7, 27), opening_range_minutes=15)
    assert start == datetime(2026, 7, 27, 9, 30, tzinfo=ET)
    assert end == datetime(2026, 7, 27, 9, 45, tzinfo=ET)


def test_levels_from_or_bars() -> None:
    df = pd.DataFrame({"h": [110.0, 112.0, 111.0], "l": [100.0, 101.0, 99.5]})
    buy, sell, stop = levels_from_or_bars(df, stop_buffer_pct=0.005)  # type: ignore[misc]
    assert buy == 99.5
    assert sell == 112.0
    assert stop == round(99.5 * 0.995, 4)


def test_levels_from_or_bars_empty() -> None:
    assert levels_from_or_bars(pd.DataFrame()) is None
    assert levels_from_or_bars(pd.DataFrame({"h": [1.0], "l": [1.0]})) is None


def test_filter_bars_to_window_half_open() -> None:
    start, end = opening_range_window(date(2026, 7, 27), opening_range_minutes=15)
    rows = [
        datetime(2026, 7, 27, 9, 30, tzinfo=ET),
        datetime(2026, 7, 27, 9, 44, tzinfo=ET),
        datetime(2026, 7, 27, 9, 45, tzinfo=ET),  # excluded (half-open end)
    ]
    df = pd.DataFrame(
        {
            "t": [r.astimezone(ZoneInfo("UTC")) for r in rows],
            "h": [1.0, 2.0, 99.0],
            "l": [0.5, 1.5, 90.0],
        }
    )
    windowed = filter_bars_to_window(df, start, end)
    assert len(windowed) == 2
    assert float(windowed["h"].max()) == 2.0
