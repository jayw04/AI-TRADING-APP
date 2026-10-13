"""TradingView CSV comparator: timestamp handling and discrepancy counts (synthetic files)."""

from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[4] / "scripts" / "research" / "range002"))
import compare_tv_csv as ctv  # noqa: E402


def test_time_parsing_requires_an_offset_and_converts_to_et() -> None:
    assert ctv.parse_tv_time("2017-03-01T09:30:00-05:00").strftime("%H:%M") == "09:30"
    assert ctv.parse_tv_time("2017-03-01T14:30:00Z").strftime("%H:%M") == "09:30"
    assert ctv.parse_tv_time("1488378600").strftime("%H:%M") == "09:30"
    with pytest.raises(ValueError, match="UTC offset"):
        ctv.parse_tv_time("2017-03-01 09:30:00")


def test_csv_reading_and_comparison(tmp_path: Path) -> None:
    p = tmp_path / "x.csv"
    p.write_text(
        "time,open,high,low,close,Volume\n"
        "2017-03-01T09:30:00-05:00,10,11,9,10.5,100\n"
        "2017-03-01T09:31:00-05:00,10.5,11,10,10.7,50\n"
        "2017-03-01T09:32:00-05:00,10.7,10.9,10.6,10.8,10\n"
        "2017-03-02T09:30:00-05:00,1,1,1,1,1\n",
        encoding="utf-8",
    )
    tv = ctv.read_csv(p, date(2017, 3, 1))
    assert sorted(tv) == ["09:30", "09:31", "09:32"]
    store = {
        "09:30": (10, 11, 9, 10.5, 100),
        "09:31": (10.5, 11, 10, 10.7, 55),
        "09:33": (1, 1, 1, 1, 1),
    }
    res = ctv.compare(tv, store)
    assert res["minutes_in_both"] == 2 and res["minutes_only_tradingview"] == ["09:32"]
    assert res["minutes_only_store"] == ["09:33"]
    assert res["ohlc_exact_equal_in_both"] == 2 and res["volume_exact_equal_in_both"] == 1


def test_missing_column_is_refused(tmp_path: Path) -> None:
    p = tmp_path / "bad.csv"
    p.write_text("time,open,high,low\n2017-03-01T09:30:00-05:00,1,1,1\n", encoding="utf-8")
    with pytest.raises(ValueError, match="close"):
        ctv.read_csv(p, date(2017, 3, 1))
