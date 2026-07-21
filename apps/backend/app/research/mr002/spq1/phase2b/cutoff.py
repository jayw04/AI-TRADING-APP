"""Registered ET market-close decision cutoff (2B-1 correction).

The decision cutoff is the registered regular-session close: 16:00 America/New_York, converted to a
timezone-aware UTC timestamp via the real tz database. This yields 21:00Z during standard time and
20:00Z during daylight-saving time, per the historical session date — closing the DST leakage channel
that a fabricated fixed 21:00Z cutoff opened (which would admit 4-5pm ET evidence in summer).
"""
from __future__ import annotations

from datetime import datetime, time
from zoneinfo import ZoneInfo

_NY = ZoneInfo("America/New_York")
_UTC = ZoneInfo("UTC")


def et_close_cutoff_iso(session_date: str) -> str:
    """Registered close-t cutoff as UTC ISO-8601 'YYYY-MM-DDTHH:MM:SSZ' for a session date."""
    d = datetime.strptime(session_date[:10], "%Y-%m-%d").date()
    dt = datetime.combine(d, time(16, 0), tzinfo=_NY)
    return dt.astimezone(_UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
