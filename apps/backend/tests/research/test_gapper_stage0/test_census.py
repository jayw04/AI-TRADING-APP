"""Census: available/partial/absent classification + the ≥250 target compare."""

from __future__ import annotations

from datetime import date

import pandas as pd

from app.research.gapper_stage0.census import (
    ABSENT,
    AVAILABLE,
    CENSUS_FIELDS,
    PARTIAL,
    RTH_EXPECTED_MINUTES,
    census_day,
    census_report,
)
from app.research.gapper_stage0.dataset_contract import DatasetContract

DAY = date(2026, 8, 14)


def _minute_frame(pm_bars: int, rth_bars: int, day: str = "2026-08-14") -> pd.DataFrame:
    recs = []
    base_pm = pd.Timestamp(f"{day} 04:00", tz="America/New_York")
    for i in range(pm_bars):
        t = (base_pm + pd.Timedelta(minutes=i)).tz_convert("UTC")
        recs.append({"t": t, "o": 10, "h": 10, "l": 10, "c": 10, "v": 100})
    base_rth = pd.Timestamp(f"{day} 09:30", tz="America/New_York")
    for i in range(rth_bars):
        t = (base_rth + pd.Timedelta(minutes=i)).tz_convert("UTC")
        recs.append({"t": t, "o": 10, "h": 10, "l": 10, "c": 10, "v": 100})
    return pd.DataFrame(recs)


def test_full_day_is_available_everywhere_core() -> None:
    row = census_day("XYZ", DAY, _minute_frame(pm_bars=60, rth_bars=RTH_EXPECTED_MINUTES))
    f = row["fields"]
    assert f["minute_bar_coverage"] == AVAILABLE
    assert f["premarket_bars"] == AVAILABLE
    assert f["first_bar_ts"] == AVAILABLE
    assert f["last_bar_ts"] == AVAILABLE
    assert f["missing_bar_count"] == AVAILABLE
    assert row["details"]["missing_bar_count"] == 0
    assert row["sufficient"] is True


def test_partial_coverage_and_partial_premarket() -> None:
    row = census_day("XYZ", DAY, _minute_frame(pm_bars=5, rth_bars=200))
    f = row["fields"]
    assert f["minute_bar_coverage"] == PARTIAL  # 200/390 < 95%
    assert f["premarket_bars"] == PARTIAL  # 0 < 5 < 30
    assert f["missing_bar_count"] == AVAILABLE
    assert row["details"]["missing_bar_count"] == RTH_EXPECTED_MINUTES - 200
    assert row["sufficient"] is False


def test_no_bars_at_all_is_absent() -> None:
    for bars in (None, pd.DataFrame(columns=["t", "o", "h", "l", "c", "v"])):
        row = census_day("XYZ", DAY, bars)
        f = row["fields"]
        assert f["minute_bar_coverage"] == ABSENT
        assert f["premarket_bars"] == ABSENT
        assert f["first_bar_ts"] == ABSENT
        assert f["last_bar_ts"] == ABSENT
        assert f["missing_bar_count"] == ABSENT
        assert row["sufficient"] is False


def test_other_days_bars_do_not_count() -> None:
    row = census_day("XYZ", DAY, _minute_frame(pm_bars=60, rth_bars=390, day="2026-08-13"))
    assert row["fields"]["minute_bar_coverage"] == ABSENT


def test_quote_halt_locate_default_absent_and_flaggable() -> None:
    row = census_day("XYZ", DAY, _minute_frame(60, 390))
    assert row["fields"]["quote_data"] == ABSENT
    assert row["fields"]["halt_data"] == ABSENT
    assert row["fields"]["locate_ssr_data"] == ABSENT
    row = census_day("XYZ", DAY, _minute_frame(60, 390), quote_data_present=True)
    assert row["fields"]["quote_data"] == AVAILABLE


def test_report_counts_and_target_shortfall() -> None:
    rows = [
        census_day("AAA", DAY, _minute_frame(60, 390)),  # sufficient
        census_day("BBB", DAY, _minute_frame(5, 200)),  # partial
        census_day("CCC", date(2026, 8, 13), None),  # absent
    ]
    contract = DatasetContract()  # target 250, incomplete (source unset)
    rep = census_report(rows, contract)
    assert rep["candidate_dates"] == 3
    assert rep["distinct_days"] == 2
    assert rep["sufficient_candidate_dates"] == 1
    assert rep["sufficient_event_days"] == 1
    assert rep["target_event_days"] == 250
    assert rep["meets_target"] is False
    assert rep["shortfall_event_days"] == 249
    assert rep["contract_complete"] is False
    for field in CENSUS_FIELDS:
        counts = rep["field_counts"][field]
        assert sum(counts.values()) == 3
    assert rep["field_counts"]["quote_data"][ABSENT] == 3
    assert rep["field_counts"]["minute_bar_coverage"] == {
        AVAILABLE: 1,
        PARTIAL: 1,
        ABSENT: 1,
    }


def test_report_meets_small_target() -> None:
    rows = [
        census_day("AAA", date(2026, 8, 13), _minute_frame(60, 390, day="2026-08-13")),
        census_day("BBB", DAY, _minute_frame(60, 390)),
    ]
    # Mechanism check with a tiny target: 2 sufficient event-days >= 2. (A
    # below-floor target flags the term unset — completeness is separate.)
    rep = census_report(rows, DatasetContract(target_event_days=2))
    assert rep["sufficient_event_days"] == 2
    assert rep["meets_target"] is True
    assert rep["shortfall_event_days"] == 0
