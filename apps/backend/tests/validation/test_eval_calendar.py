"""Forward-validation eligibility calendar (R4) — authoritative XNYS, no silent fallback.

Eligibility defines the record's session count and the §5.1 minima, so the calendar must be the
authoritative one and must fail closed when it cannot be consulted — unlike `app/market/session.py`,
whose curated fallback is correct for a dispatch gate but not for a governed research record.
"""

from __future__ import annotations

import builtins
from datetime import date

import pytest

from app.validation import eval_calendar as ec
from app.validation.eval_calendar import (
    EvalCalendarError,
    eligible_sessions,
    is_eligible_session,
    is_trading_session,
)
from app.validation.forward_window import FORWARD_START, GOVERNING_TZ

START = date.fromisoformat(FORWARD_START)


def test_the_frozen_forward_start_is_an_eligible_session():
    assert is_eligible_session(START) is True


@pytest.mark.parametrize("session", [
    date(2026, 7, 25),                       # Saturday
    date(2026, 7, 26),                       # Sunday
    date(2026, 9, 7),                        # Labor Day
    date(2026, 11, 26),                      # Thanksgiving
    date(2026, 12, 25),                      # Christmas
])
def test_non_sessions_are_ineligible(session):
    assert is_eligible_session(session) is False


@pytest.mark.parametrize("session", [date(2026, 7, 23), date(2020, 1, 2), date(2026, 7, 22)])
def test_dates_before_the_frozen_start_are_ineligible_not_errors(session):
    """The §0 floor is no-backdating: a scheduler firing before the window's first session is a
    legitimate no-op, not a failure."""
    assert is_eligible_session(session) is False


def test_a_trading_day_before_the_start_is_still_a_trading_session():
    """`is_trading_session` answers about the calendar; `is_eligible_session` also applies the floor."""
    assert is_trading_session(date(2026, 7, 23)) is True
    assert is_eligible_session(date(2026, 7, 23)) is False


def test_eligible_sessions_are_ascending_trading_days_from_the_floor():
    sessions = eligible_sessions(date(2026, 7, 20), date(2026, 7, 31))
    assert sessions == [date(2026, 7, 24), date(2026, 7, 27), date(2026, 7, 28),
                        date(2026, 7, 29), date(2026, 7, 30), date(2026, 7, 31)]
    assert sessions == sorted(sessions)


def test_eligible_sessions_before_the_floor_is_empty():
    assert eligible_sessions(date(2026, 7, 1), date(2026, 7, 23)) == []


def test_reversed_range_fails_closed():
    with pytest.raises(EvalCalendarError):
        eligible_sessions(date(2026, 7, 31), date(2026, 7, 24))


def test_missing_calendar_package_fails_closed(monkeypatch):
    """No silent fallback to a curated holiday list: without the authoritative calendar the run stops."""
    real_import = builtins.__import__

    def blocked(name, *a, **kw):
        if name == "pandas_market_calendars":
            raise ImportError("blocked for test")
        return real_import(name, *a, **kw)

    monkeypatch.setattr(builtins, "__import__", blocked)
    with pytest.raises(EvalCalendarError, match="authoritative"):
        is_eligible_session(START)


def test_calendar_lookup_failure_fails_closed(monkeypatch):
    class _Boom:
        def schedule(self, **kw):
            raise RuntimeError("calendar backend unavailable")

    monkeypatch.setattr(ec, "_xnys", lambda: _Boom())
    with pytest.raises(EvalCalendarError, match="schedule lookup failed"):
        is_trading_session(START)


def test_governing_timezone_is_the_frozen_one():
    assert ec.governing_timezone() == GOVERNING_TZ == "America/New_York"
