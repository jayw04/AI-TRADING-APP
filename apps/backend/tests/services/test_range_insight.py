"""P8 §5 — Range Insight computation over synthetic daily bars."""

from __future__ import annotations

from datetime import UTC, datetime

import pandas as pd

from app.services.range_insight import (
    DISCLAIMER,
    MIN_BARS,
    range_insight_from_bars,
)

NOW = datetime(2026, 6, 8, 18, 0, tzinfo=UTC)  # ET date 2026-06-08


def _bars(rows: list[tuple[float, float, float, float]], end_day: int) -> pd.DataFrame:
    """rows = [(o,h,l,c)]; daily bars at 13:00 UTC ending on 2026-06-<end_day>."""
    n = len(rows)
    end = pd.Timestamp(2026, 6, end_day, 13, tz="UTC")
    dates = [end - pd.Timedelta(days=n - 1 - i) for i in range(n)]
    return pd.DataFrame(
        {
            "t": dates,
            "o": [r[0] for r in rows],
            "h": [r[1] for r in rows],
            "l": [r[2] for r in rows],
            "c": [r[3] for r in rows],
            "v": [1_000_000] * n,
        }
    )


def test_uniform_full_window_no_today_bar() -> None:
    # 25 completed bars ending 06-05 (before NOW's date) → no today bar.
    bars = _bars([(100.0, 103.0, 98.0, 100.0)] * 25, end_day=5)
    ri = range_insight_from_bars("AAPL", bars, NOW)
    assert ri.status == "ok"
    assert ri.bars_used == 20
    assert ri.low_confidence is False
    assert ri.anchor_source == "last_close"
    assert ri.anchor == 100.0
    assert ri.intraday_range is None
    assert ri.support == 98.0
    assert ri.resistance == 103.0
    assert ri.atr20 == 5.0  # TR = max(5, 3, 2)
    assert ri.atr20_pct == 0.05
    assert ri.typical_move_up.mean == 3.0  # high - open
    assert ri.typical_move_down.median == 2.0  # open - low
    assert ri.high_band.low == 103.0 and ri.high_band.high == 103.0
    assert ri.low_band.low == 98.0 and ri.low_band.high == 98.0
    assert ri.classification == "range_bound"  # flat closes → ER 0
    assert ri.disclaimer == DISCLAIMER


def test_low_confidence_band() -> None:
    bars = _bars([(100.0, 102.0, 99.0, 100.0)] * 12, end_day=5)
    ri = range_insight_from_bars("AAPL", bars, NOW)
    assert ri.status == "ok"
    assert ri.bars_used == 12
    assert ri.low_confidence is True


def test_insufficient_data_below_floor() -> None:
    bars = _bars([(100.0, 101.0, 99.0, 100.0)] * (MIN_BARS - 1), end_day=5)
    ri = range_insight_from_bars("AAPL", bars, NOW)
    assert ri.status == "insufficient_data"
    assert ri.atr20 is None
    assert ri.high_band is None
    assert ri.disclaimer == DISCLAIMER  # disclaimer present even when insufficient


def test_today_bar_anchors_on_open_and_sets_intraday_range() -> None:
    # 20 completed bars + a today bar (06-08, == NOW's ET date).
    rows = [(100.0, 103.0, 98.0, 100.0)] * 20 + [(101.0, 105.0, 95.0, 102.0)]
    bars = _bars(rows, end_day=8)
    ri = range_insight_from_bars("AAPL", bars, NOW)
    assert ri.bars_used == 20  # today excluded from the distributions
    assert ri.anchor_source == "today_open"
    assert ri.anchor == 101.0
    assert ri.intraday_range == 10.0  # 105 - 95
    # high band = anchor + p10..p90 of (high-open)=3 → [104, 104]
    assert ri.high_band.low == 104.0


def test_trending_classification() -> None:
    # a steady ramp → efficiency ratio ≈ 1 → trending
    rows = [(100.0 + i, 100.0 + i + 1, 99.0 + i, 100.0 + i) for i in range(20)]
    ri = range_insight_from_bars("AAPL", _bars(rows, end_day=5), NOW)
    assert ri.classification == "trending"
    assert ri.efficiency_ratio > 0.5


def test_empty_bars_insufficient() -> None:
    ri = range_insight_from_bars("AAPL", pd.DataFrame(), NOW)
    assert ri.status == "insufficient_data"
    assert ri.bars_used == 0
    assert ri.as_of is None
