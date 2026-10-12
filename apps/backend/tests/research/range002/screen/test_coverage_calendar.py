"""Return-blind coverage report (PIT denominator) and the session calendar. Synthetic only."""

from __future__ import annotations

from datetime import date, time

import pytest

from app.research.range002.screen.coverage import (
    LEGITIMATE_EXCLUSIONS,
    DayPresence,
    coverage_report,
    presence_from_minutes,
)
from app.research.range002.screen.session_calendar import expected_sessions

D1, D2 = date(2019, 3, 4), date(2019, 3, 5)


def _p(gaps: int = 0) -> DayPresence:
    return DayPresence(bar_count=400, or_bar_count=30 - gaps, or_gap_minutes=gaps)


def _cov(expected, observed, exclusions=None, causes=None):  # type: ignore[no-untyped-def]
    return coverage_report(
        expected,
        observed,
        exclusions=exclusions or {},
        missing_causes=causes or {},
        or_max_gap_minutes=0,
        threshold=0.98,
    )


def test_completely_missing_symbol_day_stays_in_the_denominator() -> None:
    expected = [("AAA", D1), ("BBB", D1), ("CCC", D1), ("DDD", D1)]
    observed = {("AAA", D1): _p(), ("BBB", D1): _p()}  # CCC, DDD returned NO bars at all
    r = _cov(expected, observed, causes={("CCC", D1): "IDENTITY_MAPPING_FAILURE"})
    assert r.denominator == 4 and r.observed == 2
    assert r.coverage_rate == 0.5 and not r.meets_threshold
    assert r.missing_identity_mapping == 1 and r.unresolved_unexplained == 1


def test_documented_exclusions_leave_the_denominator_but_are_reported() -> None:
    expected = [("AAA", D1), ("BBB", D1), ("NEW", D1)]
    r = _cov(
        expected,
        {("AAA", D1): _p(), ("BBB", D1): _p()},
        exclusions={("NEW", D1): "NOT_YET_LISTED"},
    )
    assert r.denominator == 2 and r.legitimate_exclusions == {"NOT_YET_LISTED": 1}
    assert r.coverage_rate == 1.0 and r.meets_threshold


def test_undocumented_exclusion_reason_and_unexpected_rows_are_refused() -> None:
    with pytest.raises(ValueError, match="LEGITIMATE_EXCLUSIONS"):
        _cov([("A", D1)], {}, exclusions={("A", D1): "LOW_VOLUME"})
    with pytest.raises(ValueError, match="never expected"):
        _cov([("A", D1)], {("B", D1): _p()})
    with pytest.raises(ValueError, match="duplicate"):
        _cov([("A", D1), ("A", D1)], {})
    assert "LOW_VOLUME" not in LEGITIMATE_EXCLUSIONS


def test_or_completeness_is_a_separate_check_with_two_denominators() -> None:
    expected = [("A", D1), ("B", D1), ("C", D1), ("D", D1)]
    observed = {("A", D1): _p(0), ("B", D1): _p(1), ("C", D1): _p(0)}  # D missing entirely
    r = _cov(expected, observed)
    assert r.coverage_rate == 0.75  # dataset coverage
    assert r.or_complete_count == 2
    assert r.or_complete_of_observed == pytest.approx(2 / 3)
    assert r.or_complete_of_expected == pytest.approx(2 / 4)


def test_by_year_breakdown_and_presence_helper() -> None:
    expected = [("A", D1), ("A", date(2020, 3, 4))]
    r = _cov(expected, {("A", D1): _p()})
    assert r.by_year == {2019: {"expected": 1, "observed": 1}, 2020: {"expected": 1, "observed": 0}}
    pres = presence_from_minutes(
        [time(9, 30), time(9, 31), time(10, 5)],
        [time(9, 32), time(9, 32), time(11, 0)],
        time(9, 30),
        time(9, 59, 59),
    )
    assert pres == DayPresence(bar_count=3, or_bar_count=2, or_gap_minutes=1)


def test_calendar_marks_early_closes_and_holidays() -> None:
    s = expected_sessions(date(2019, 7, 1), date(2019, 7, 8))
    assert date(2019, 7, 4) not in s  # Independence Day
    assert s[date(2019, 7, 3)] == time(13, 0)  # early close
    assert s[date(2019, 7, 5)] == time(16, 0)
    black_friday = expected_sessions(date(2019, 11, 29), date(2019, 11, 29))
    assert black_friday[date(2019, 11, 29)] == time(13, 0)
    week = expected_sessions(D1, date(2019, 3, 10))
    assert D1 in week and date(2019, 3, 9) not in week
