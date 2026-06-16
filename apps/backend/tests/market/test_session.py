"""Tests for the §9A Market Session Model (app/market/session.py).

Deterministic: every case passes an explicit ET-aware instant, so `zoneinfo`
handles DST and the assertions don't depend on wall-clock time. These exercise
the network-free fallback path (pandas_market_calendars is not installed in the
test/dev env — the same path the live runtime uses)."""

from __future__ import annotations

from datetime import UTC, datetime
from zoneinfo import ZoneInfo

import pytest

from app.market.session import (
    MarketSession,
    MarketSessionType,
    default_market_session,
)

_ET = ZoneInfo("America/New_York")


def _et(year: int, month: int, day: int, hour: int, minute: int = 0) -> datetime:
    return datetime(year, month, day, hour, minute, tzinfo=_ET)


# 2026-06-17 is a Wednesday, not a holiday → a normal full trading day (EDT).
_WED = (2026, 6, 17)


@pytest.fixture
def ms() -> MarketSession:
    return MarketSession()


@pytest.mark.parametrize(
    ("hour", "minute", "expected"),
    [
        (3, 0, MarketSessionType.CLOSED),       # before pre-market open (04:00)
        (4, 0, MarketSessionType.PRE_MARKET),   # pre-market opens
        (8, 30, MarketSessionType.PRE_MARKET),
        (9, 29, MarketSessionType.PRE_MARKET),  # one minute before the bell
        (9, 30, MarketSessionType.REGULAR),     # the open
        (12, 0, MarketSessionType.REGULAR),
        (15, 59, MarketSessionType.REGULAR),    # one minute before the close
        (16, 0, MarketSessionType.AFTER_HOURS), # the close
        (19, 59, MarketSessionType.AFTER_HOURS),
        (20, 0, MarketSessionType.CLOSED),      # after-hours ends
        (23, 0, MarketSessionType.CLOSED),
    ],
)
def test_classify_full_trading_day_boundaries(
    ms: MarketSession, hour: int, minute: int, expected: MarketSessionType
) -> None:
    info = ms.classify(_et(*_WED, hour, minute))
    assert info.session is expected
    assert info.is_trading_day is True
    assert info.is_half_day is False
    # a trading day always reports its open/close in UTC
    assert info.regular_open is not None and info.regular_close is not None
    assert info.regular_open.tzinfo is not None


def test_weekend_is_closed(ms: MarketSession) -> None:
    info = ms.classify(_et(2026, 6, 20, 12))  # Saturday
    assert info.session is MarketSessionType.CLOSED
    assert info.is_trading_day is False
    assert info.regular_open is None
    assert info.regular_close is None


def test_full_holiday_is_closed(ms: MarketSession) -> None:
    # 2026-07-03 — July 4th observed (a curated full holiday).
    info = ms.classify(_et(2026, 7, 3, 11))
    assert info.session is MarketSessionType.CLOSED
    assert info.is_trading_day is False


def test_half_day_early_close(ms: MarketSession) -> None:
    # 2026-11-27 (day after Thanksgiving) — curated half-day, 13:00 ET close.
    before = ms.classify(_et(2026, 11, 27, 12))  # still regular
    after = ms.classify(_et(2026, 11, 27, 14))   # past the early close
    assert before.session is MarketSessionType.REGULAR
    assert before.is_half_day is True
    assert after.session is MarketSessionType.AFTER_HOURS
    assert after.is_half_day is True


def test_naive_datetime_treated_as_utc(ms: MarketSession) -> None:
    # 14:00 UTC on the Wednesday == 10:00 EDT == REGULAR.
    naive = datetime(*_WED, 14, 0)  # noqa: DTZ001 — intentional naive input
    aware = datetime(*_WED, 14, 0, tzinfo=UTC)
    assert ms.classify(naive).session is MarketSessionType.REGULAR
    assert ms.classify(naive).session is ms.classify(aware).session


@pytest.mark.parametrize(
    ("session", "allow_extended", "expected"),
    [
        (MarketSessionType.REGULAR, False, True),
        (MarketSessionType.REGULAR, True, True),
        (MarketSessionType.PRE_MARKET, False, False),
        (MarketSessionType.PRE_MARKET, True, True),
        (MarketSessionType.AFTER_HOURS, False, False),
        (MarketSessionType.AFTER_HOURS, True, True),
        (MarketSessionType.CLOSED, False, False),
        (MarketSessionType.CLOSED, True, False),  # CLOSED never dispatchable
    ],
)
def test_dispatchable_matrix(
    ms: MarketSession,
    session: MarketSessionType,
    allow_extended: bool,
    expected: bool,
) -> None:
    # Drive each session via a representative instant on the Wednesday.
    instants = {
        MarketSessionType.REGULAR: _et(*_WED, 12),
        MarketSessionType.PRE_MARKET: _et(*_WED, 8),
        MarketSessionType.AFTER_HOURS: _et(*_WED, 17),
        MarketSessionType.CLOSED: _et(*_WED, 23),
    }
    info = ms.classify(instants[session])
    assert info.session is session
    assert info.dispatchable(allow_extended=allow_extended) is expected


def test_is_dispatchable_default_is_rth_only(ms: MarketSession) -> None:
    # The conservative default (allow_extended=False): pre-market is blocked.
    assert ms.is_dispatchable(_et(*_WED, 8)) is False         # pre-market
    assert ms.is_dispatchable(_et(*_WED, 12)) is True         # regular
    assert ms.is_dispatchable(_et(*_WED, 17)) is False        # after-hours
    assert ms.is_dispatchable(_et(*_WED, 8), allow_extended=True) is True


def test_day_schedule_is_cached(ms: MarketSession) -> None:
    ms.classify(_et(*_WED, 12))
    from datetime import date

    assert date(*_WED) in ms._cache


def test_default_market_session_is_shared() -> None:
    assert default_market_session() is default_market_session()
