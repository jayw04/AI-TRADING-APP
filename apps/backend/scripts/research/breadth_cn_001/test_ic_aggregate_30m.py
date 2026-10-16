"""Tests for ic_aggregate_30m (synthetic 1-minute bars; no vendor access).  Run: python3 test_ic_aggregate_30m.py"""

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
import ic_aggregate_30m as A  # noqa: E402


def day_minutes(day: str) -> pd.DatetimeIndex:
    d = pd.Timestamp(day)
    morning = pd.date_range(
        d + pd.Timedelta(hours=9, minutes=31), d + pd.Timedelta(hours=11, minutes=30), freq="1min"
    )
    afternoon = pd.date_range(
        d + pd.Timedelta(hours=13, minutes=1), d + pd.Timedelta(hours=15), freq="1min"
    )
    return morning.append(afternoon)


def make(days: list[str], drop: list[str] | None = None) -> pd.DataFrame:
    t = day_minutes(days[0])
    for d in days[1:]:
        t = t.append(day_minutes(d))
    if drop:
        t = t.difference(pd.DatetimeIndex(drop))
    n = len(t)
    px = 100 + np.arange(n, dtype=float)
    return pd.DataFrame(
        {"eob": t, "open": px, "high": px + 1, "low": px - 1, "close": px, "volume": 1.0}
    )


def test_full_day_has_eight_complete_bars() -> None:
    m1 = make(["2026-05-04"])
    bars = A.aggregate_30m(m1)
    assert bars["label"].dt.strftime("%H:%M").tolist() == A.SESSION_ENDS
    assert bars["complete"].all() and (bars["n_1m"] == 30).all()
    # label at close: the 10:00 bar uses 09:31..10:00; its open is the 09:31 bar's open, close the 10:00 bar's close
    first = bars.iloc[0]
    assert (
        first["open"] == m1.iloc[0]["open"]
        and first["close"] == m1[m1["eob"].dt.strftime("%H:%M") == "10:00"].iloc[0]["close"]
    )
    assert bars["volume"].sum() == len(m1)


def test_missing_minute_is_flagged_not_filled() -> None:
    m1 = make(["2026-05-04"], drop=["2026-05-04 10:15:00"])
    bars = A.aggregate_30m(m1)
    b = bars[bars["label"] == pd.Timestamp("2026-05-04 10:30:00")].iloc[0]
    assert b["n_1m"] == 29 and not b["complete"] and b["volume"] == 29.0  # nothing interpolated
    rep = A.completeness(m1, pd.DatetimeIndex(["2026-05-04"]))
    assert (
        rep["bars_with_fewer_than_30_minutes"] == 1
        and rep["complete_30m_bars"] == 7
        and rep["missing_30m_bars"] == 0
    )


def test_missing_whole_bar_and_unexpected_minutes() -> None:
    m1 = make(["2026-05-04", "2026-05-05"])
    gone = [
        t
        for t in m1["eob"]
        if t.date() == pd.Timestamp("2026-05-05").date() and 780 < t.hour * 60 + t.minute <= 810
    ]  # the 13:30 bar
    m1 = m1[~m1["eob"].isin(gone)]
    extra = pd.DataFrame(
        {
            "eob": [pd.Timestamp("2026-05-04 09:30:00"), pd.Timestamp("2026-05-04 15:01:00")],
            "open": 1.0,
            "high": 1.0,
            "low": 1.0,
            "close": 1.0,
            "volume": 1.0,
        }
    )
    rep = A.completeness(pd.concat([m1, extra]), pd.DatetimeIndex(["2026-05-04", "2026-05-05"]))
    assert rep["missing_30m_bars"] == 1 and rep["missing_examples"] == ["2026-05-05 13:30:00"]
    assert rep["one_minute_bars_outside_sessions"] == 2 and rep["expected_30m_bars"] == 16


def test_pre_2016_refused() -> None:
    m1 = make(["2015-12-31"])
    try:
        A.aggregate_30m(m1)
    except ValueError:
        return
    raise AssertionError("pre-2016 bars must be refused")


if __name__ == "__main__":
    for n, f in list(globals().items()):
        if n.startswith("test_"):
            f()
            print("ok", n)
    print("ALL TESTS PASSED")
