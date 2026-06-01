"""Shared time/datetime helpers.

ensure_aware: coerce a possibly-naive datetime to aware-UTC. SQLite returns
DateTime(timezone=True) columns without tzinfo; comparisons against
datetime.now(timezone.utc) raise TypeError ("can't compare naive and
aware") if not coerced. This helper is the single canonical fix — Session 3
first hit it in app/auth/stub.py, Session 4 in app/security/credential_store.py,
Session 5 in the risk gates. Extracted here so there's one copy.
"""
from __future__ import annotations

from datetime import UTC, datetime


def ensure_aware(dt: datetime | None) -> datetime | None:
    """Coerce a possibly-naive datetime to aware-UTC. None passes through."""
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt
