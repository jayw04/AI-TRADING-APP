"""EDGAR acceptance stamps are Eastern WALL TIME, with real DST transitions."""

from __future__ import annotations

from datetime import UTC

import pytest

from app.altdata.sec001_v31.clock import accepted_at_utc, is_eastern_daylight


@pytest.mark.parametrize(
    "stamp,expected_utc,dst",
    [
        # Envelope B's own left-bracket set is the proof: November 2020 is EST (-05:00),
        # so the previously hard-coded -04:00 mis-stamped every one of them by an hour.
        ("2020-11-05T01:55:35.000Z", "2020-11-05T06:55:35+00:00", False),
        ("2020-12-04T01:31:10.000Z", "2020-12-04T06:31:10+00:00", False),
        ("2021-01-28T02:13:48.000Z", "2021-01-28T07:13:48+00:00", False),
        ("2021-02-03T01:12:25.000Z", "2021-02-03T06:12:25+00:00", False),
        # summer filings are EDT (-04:00)
        ("2026-07-23T01:15:54.000Z", "2026-07-23T05:15:54+00:00", True),
        ("2026-08-11T00:42:31.000Z", "2026-08-11T04:42:31+00:00", True),
    ],
)
def test_dst_is_honoured(stamp, expected_utc, dst):
    assert accepted_at_utc(stamp).isoformat() == expected_utc
    assert is_eastern_daylight(stamp) is dst


def test_a_fixed_minus_four_offset_would_be_wrong_in_winter():
    from datetime import datetime, timedelta, timezone

    stamp = "2020-11-05T01:55:35.000Z"
    naive = datetime.fromisoformat(stamp.replace("Z", ""))
    wrong = naive.replace(tzinfo=timezone(timedelta(hours=-4))).astimezone(UTC)
    assert accepted_at_utc(stamp) != wrong
    assert (accepted_at_utc(stamp) - wrong) == timedelta(hours=1)


def test_empty_stamp_is_rejected():
    with pytest.raises(ValueError):
        accepted_at_utc("   ")
