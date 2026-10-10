from __future__ import annotations

from datetime import date

import pytest

from app.research.range002.governance.model import (
    R2_EXCLUDED_WINDOW,
    DateRange,
)


def test_date_range_validation() -> None:
    with pytest.raises(ValueError, match="after end"):
        DateRange(date(2020, 1, 2), date(2020, 1, 1))
    with pytest.raises(TypeError):
        DateRange("2020-01-01", date(2020, 1, 2))  # type: ignore[arg-type]


def test_overlap_contains_and_dict() -> None:
    a = DateRange(date(2020, 1, 1), date(2020, 1, 10))
    assert a.overlaps(DateRange(date(2020, 1, 10), date(2020, 2, 1)))
    assert not a.overlaps(DateRange(date(2020, 1, 11), date(2020, 2, 1)))
    assert a.contains(DateRange(date(2020, 1, 2), date(2020, 1, 3)))
    assert not a.contains(DateRange(date(2019, 12, 31), date(2020, 1, 3)))
    assert a.as_dict() == {"start": "2020-01-01", "end": "2020-01-10"}


def test_r2_window_is_the_plan_window() -> None:
    assert (R2_EXCLUDED_WINDOW.start, R2_EXCLUDED_WINDOW.end) == (
        date(2026, 1, 1),
        date(2026, 7, 31),
    )
