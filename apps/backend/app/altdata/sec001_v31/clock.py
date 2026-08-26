"""EDGAR acceptance-time semantics.

Review finding (P1): the previous conversion hard-coded ``timezone(timedelta(hours=-4))``.
Envelope eligibility happened not to depend on the distinction — the boundary-sensitivity
measurement came out zero — but binding uses **exact** accepted timestamps across 2020-2026,
and a fixed offset is simply wrong for half the year. Envelope B's own left-bracket set is
the proof: the November-2020 filings that reach the 2021-02-08 edge are EST (-05:00), so a
fixed -04:00 mis-stamps every one of them by an hour.

EDGAR labels ``acceptanceDateTime`` with a ``Z`` suffix, but the clock is Eastern wall time.
The ``Z`` is not to be believed; the zone is.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Final
from zoneinfo import ZoneInfo

#: EDGAR acceptance stamps are Eastern wall time, with real DST transitions.
EDGAR_TZ: Final = ZoneInfo("America/New_York")


def accepted_at_utc(stamp: str) -> datetime:
    """Convert an EDGAR acceptance stamp to a true UTC instant.

    Reading the label as Eastern is also the conservative direction for an
    at-or-before-cutoff test: it can only move an instant later, never earlier, so it can
    only exclude a filing from eligibility, never admit one.
    """
    text = stamp.replace("Z", "").replace("z", "").strip()
    if not text:
        raise ValueError("empty acceptance stamp")
    return datetime.fromisoformat(text).replace(tzinfo=EDGAR_TZ).astimezone(UTC)


def is_eastern_daylight(stamp: str) -> bool:
    """Whether a stamp falls in EDT. Diagnostic only; never an eligibility input."""
    text = stamp.replace("Z", "").replace("z", "").strip()
    dt = datetime.fromisoformat(text).replace(tzinfo=EDGAR_TZ)
    return bool(dt.dst())
