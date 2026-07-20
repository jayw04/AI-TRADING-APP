"""Registered trading-calendar adapter (Phase 2A domain 1).

Builds the development ``RegisteredCalendar`` from the governed session-date authority (AAPL,
continuously listed) in the dev snapshot and ENFORCES the frozen development-calendar SHA-256 — the
governed hash, not a mere count, is the authority. Dates + ordinals + registered ET regular-session
policy; no calendar-day arithmetic and no fabricated intraday timestamps. The identity effective-date
mapper is a frozen on-or-after rule (never at-or-before clamping) with explicit PRE_WINDOW handling.
"""
from __future__ import annotations

import hashlib

from ..calendar import RegisteredCalendar
from ..refusals import refuse
from . import DEV_CALENDAR_SHA256, DEV_SESSIONS, DEV_TIMEZONE

CALENDAR_ANCHOR = "AAPL"  # continuously-listed governed calendar authority
PRE_WINDOW = "PRE_WINDOW"
IN_WINDOW = "IN_WINDOW"


def dev_calendar_sha256(dates: tuple[str, ...]) -> str:
    """Frozen serialization: newline-joined ISO dates + trailing newline."""
    return hashlib.sha256(("\n".join(dates) + "\n").encode("utf-8")).hexdigest()


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
    computed = dev_calendar_sha256(dates)
    if computed != DEV_CALENDAR_SHA256:
        raise refuse(
            "INTEGRITY_STOP:SESSION_CALENDAR_MISMATCH",
            f"development calendar hash {computed} != frozen {DEV_CALENDAR_SHA256} "
            "(a missing/inserted/reordered session at the same count is rejected)",
        )
    return RegisteredCalendar(dates)  # validates ascending + unique


def map_effective_session(calendar: RegisteredCalendar, date_str: str) -> tuple[int, str]:
    """Frozen identity effective-session rule. Returns (ordinal, disposition).

    - missing/blank                       -> INTEGRITY_STOP:SECURITY_IDENTITY_AMBIGUOUS
    - before the first dev session        -> (0, PRE_WINDOW)   [pre-existing lineage]
    - after the last dev session          -> INTEGRITY_STOP:SECURITY_IDENTITY_AMBIGUOUS  [must be excluded upstream]
    - in-window: first registered session ON OR AFTER the effective date (never at-or-before clamp)
    """
    s = (date_str or "").strip()
    if not s or s.lower() in ("none", "nat"):
        raise refuse(
            "INTEGRITY_STOP:SECURITY_IDENTITY_AMBIGUOUS", "missing identity effective date"
        )
    day = s[:10]
    if day < calendar.sessions[0]:
        return 0, PRE_WINDOW
    if day > calendar.sessions[-1]:
        raise refuse(
            "INTEGRITY_STOP:SECURITY_IDENTITY_AMBIGUOUS",
            f"identity effective date {day} is after development end (must be excluded)",
        )
    # first registered session >= day (on-or-after)
    lo, hi = 0, len(calendar) - 1
    while lo < hi:
        mid = (lo + hi) // 2
        if calendar.sessions[mid] < day:
            lo = mid + 1
        else:
            hi = mid
    return lo, IN_WINDOW


REGISTERED_SESSION_POLICY = {
    "timezone": DEV_TIMEZONE,
    "regular_open": "09:30",
    "regular_close": "16:00",
    "shortened_session_policy": "date-membership only (EOD data; no per-session intraday times)",
    "basis": "registered ET regular-session policy (dates are EOD; no vendor intraday timestamps)",
}
