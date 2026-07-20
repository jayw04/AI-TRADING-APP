"""Registered trading-calendar adapter (Phase 2A domain 1).

Builds the development ``RegisteredCalendar`` from the governed session-date authority (AAPL,
continuously listed) in the dev snapshot. Dates + ordinals + registered ET regular-session policy;
no calendar-day arithmetic and no fabricated per-session intraday timestamps (dates are EOD). A
duplicate / out-of-order / missing session or a wrong session count fails closed.
"""
from __future__ import annotations

from ..calendar import RegisteredCalendar
from ..refusals import refuse
from . import DEV_SESSIONS, DEV_TIMEZONE

CALENDAR_ANCHOR = "AAPL"  # continuously-listed governed calendar authority


def load_calendar(con, anchor: str = CALENDAR_ANCHOR, expect_sessions: int = DEV_SESSIONS):  # noqa: ANN001
    rows = con.execute(
        'select distinct "date" from prices where ticker = ? order by "date"', [anchor]
    ).fetchall()
    dates = tuple(str(r[0]) for r in rows)
    if not dates:
        raise refuse(
            "INTEGRITY_STOP:SESSION_CALENDAR_MISMATCH",
            f"no calendar sessions for anchor {anchor} in the dev snapshot",
        )
    if len(dates) != expect_sessions:
        raise refuse(
            "INTEGRITY_STOP:SESSION_CALENDAR_MISMATCH",
            f"development calendar has {len(dates)} sessions, expected {expect_sessions}",
        )
    return RegisteredCalendar(dates)  # validates ascending + unique


def date_to_ordinal(calendar: RegisteredCalendar, date_str: str) -> int:
    """Ordinal of the session at/before ``date_str`` (clamped to 0 for pre-window dates)."""
    if date_str <= calendar.sessions[0]:
        return 0
    if date_str >= calendar.sessions[-1]:
        return len(calendar) - 1
    lo, hi = 0, len(calendar) - 1
    while lo < hi:
        mid = (lo + hi + 1) // 2
        if calendar.sessions[mid] <= date_str:
            lo = mid
        else:
            hi = mid - 1
    return lo


REGISTERED_SESSION_POLICY = {
    "timezone": DEV_TIMEZONE,
    "regular_open": "09:30",
    "regular_close": "16:00",
    "basis": "registered ET regular-session policy (dates are EOD; no vendor intraday timestamps)",
}
