"""US equity market hours awareness.

Simple time-of-day check against US/Eastern. Does NOT handle exchange holidays
in MVP — Alpaca will reject orders on closed days anyway, and the holiday
calendar can be layered in during P4 polish.
"""

from __future__ import annotations

from datetime import datetime, time
from zoneinfo import ZoneInfo

NYSE_TZ = ZoneInfo("America/New_York")
REGULAR_OPEN = time(9, 30)
REGULAR_CLOSE = time(16, 0)
PREMARKET_OPEN = time(4, 0)
AFTERHOURS_CLOSE = time(20, 0)


def is_weekday(now: datetime | None = None) -> bool:
    now = (now or datetime.now(NYSE_TZ)).astimezone(NYSE_TZ)
    return now.weekday() < 5  # Mon=0 .. Fri=4


def is_regular_session(now: datetime | None = None) -> bool:
    """True during regular trading hours (09:30-16:00 ET, Mon-Fri)."""
    now = (now or datetime.now(NYSE_TZ)).astimezone(NYSE_TZ)
    return is_weekday(now) and REGULAR_OPEN <= now.time() < REGULAR_CLOSE


def is_extended_session(now: datetime | None = None) -> bool:
    """True during extended hours (04:00-09:30 and 16:00-20:00 ET)."""
    now = (now or datetime.now(NYSE_TZ)).astimezone(NYSE_TZ)
    if not is_weekday(now):
        return False
    t = now.time()
    return (PREMARKET_OPEN <= t < REGULAR_OPEN) or (REGULAR_CLOSE <= t < AFTERHOURS_CLOSE)


def session_label(now: datetime | None = None) -> str:
    """Return 'regular' | 'extended' | 'closed'."""
    if is_regular_session(now):
        return "regular"
    if is_extended_session(now):
        return "extended"
    return "closed"
