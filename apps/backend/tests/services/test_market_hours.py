from datetime import datetime
from zoneinfo import ZoneInfo

from app.services.market_hours import (
    is_extended_session,
    is_regular_session,
    is_weekday,
    session_label,
)

ET = ZoneInfo("America/New_York")


def _et(year: int, month: int, day: int, hour: int, minute: int) -> datetime:
    return datetime(year, month, day, hour, minute, tzinfo=ET)


def test_regular_session_at_10am_tuesday() -> None:
    t = _et(2026, 5, 19, 10, 0)
    assert is_regular_session(t) is True
    assert is_extended_session(t) is False
    assert session_label(t) == "regular"


def test_extended_premarket_at_5am() -> None:
    t = _et(2026, 5, 19, 5, 0)
    assert is_regular_session(t) is False
    assert is_extended_session(t) is True
    assert session_label(t) == "extended"


def test_extended_afterhours_at_6pm() -> None:
    t = _et(2026, 5, 19, 18, 0)
    assert is_regular_session(t) is False
    assert is_extended_session(t) is True


def test_closed_at_3am() -> None:
    t = _et(2026, 5, 19, 3, 0)
    assert session_label(t) == "closed"


def test_weekend_always_closed() -> None:
    sat = _et(2026, 5, 23, 10, 0)
    sun = _et(2026, 5, 24, 10, 0)
    assert is_weekday(sat) is False
    assert is_weekday(sun) is False
    assert session_label(sat) == "closed"
    assert session_label(sun) == "closed"


def test_exact_open_inclusive() -> None:
    t = _et(2026, 5, 19, 9, 30)
    assert is_regular_session(t) is True


def test_exact_close_exclusive() -> None:
    t = _et(2026, 5, 19, 16, 0)
    assert is_regular_session(t) is False
    assert is_extended_session(t) is True  # 16:00 starts afterhours
