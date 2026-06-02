"""Shared time/datetime helpers.

ensure_aware: coerce a possibly-naive datetime to aware-UTC. SQLite returns
DateTime(timezone=True) columns without tzinfo; comparisons against
datetime.now(timezone.utc) raise TypeError ("can't compare naive and
aware") if not coerced. This helper is the single canonical fix — Session 3
first hit it in app/auth/stub.py, Session 4 in app/security/credential_store.py,
Session 5 in the risk gates. Extracted here so there's one copy.
"""
from __future__ import annotations

from datetime import UTC, date, datetime
from zoneinfo import ZoneInfo

# The market timezone. The APScheduler instances already run in this zone
# (app/services/scheduler.py, the morning-brief cron). Using ZoneInfo here makes
# the brief's "today" DST-correct — no fixed -5h offset that drifts ~7 months/yr.
EASTERN = ZoneInfo("America/New_York")


def ensure_aware(dt: datetime | None) -> datetime | None:
    """Coerce a possibly-naive datetime to aware-UTC. None passes through."""
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt


def today_eastern() -> date:
    """Today's calendar date in US/Eastern (DST-aware).

    Used by the morning brief (P5.5 §2) to key one brief per (user, trading
    day). The 09:00-ET scheduled run and a manual run on the same day land on
    the same ``brief_date``.
    """
    return datetime.now(EASTERN).date()
