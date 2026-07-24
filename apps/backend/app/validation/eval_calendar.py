"""Forward-validation eligibility calendar — authoritative XNYS sessions, no silent fallback (R4).

Which dates are eligible sessions is not a convenience question here: the forward record's session
count, its §5.1 minima (252 completed sessions, 40 rebalances, one complete year) and the strictly
increasing session dates of the committed chain are all defined against this calendar. A degraded
calendar would silently change what the record means.

`app/market/session.py` deliberately falls back to curated holiday/half-day lists when
`pandas_market_calendars` is unavailable — the right behaviour for a dispatch gate on a dev box behind
an SSL-inspecting proxy. It is the WRONG behaviour for a governed research record, so this module does
not reuse that path: it requires the authoritative XNYS calendar and FAILS CLOSED when it cannot be
loaded, when the schedule cannot be read, or when a date cannot be resolved.

Eligibility is exactly: an XNYS trading session on or after the frozen `FORWARD_START` (§0 no-backdating
floor). The governing timezone is America/New_York; this module answers about session DATES only — the
intraday timing of the run is the scheduler's business, not the record's.
"""

from __future__ import annotations

from datetime import date, timedelta

from app.validation.forward_window import FORWARD_START, GOVERNING_TZ, IntegrityStop

__all__ = [
    "EvalCalendarError",
    "eligible_sessions",
    "is_eligible_session",
    "is_trading_session",
    "next_eligible_session",
]


class EvalCalendarError(IntegrityStop):
    """The authoritative session calendar could not be consulted. The run FAILS CLOSED: no session is
    treated as eligible or ineligible on a guess, and nothing is written."""


def _xnys():
    """The authoritative XNYS calendar, or fail closed. Never falls back to a curated list."""
    try:
        import pandas_market_calendars as mcal
    except ImportError as exc:                      # pragma: no cover - dependency is pinned
        raise EvalCalendarError(
            "pandas_market_calendars is not installed — the forward-validation calendar has no "
            "authoritative source and must not fall back to a curated holiday list") from exc
    try:
        return mcal.get_calendar("XNYS")
    except Exception as exc:                        # pragma: no cover - defensive
        raise EvalCalendarError(f"could not load the XNYS calendar: {exc}") from exc


def is_trading_session(d: date) -> bool:
    """True iff `d` is an XNYS trading session (America/New_York). Fails closed on any calendar error."""
    cal = _xnys()
    try:
        schedule = cal.schedule(start_date=d, end_date=d)
    except Exception as exc:
        raise EvalCalendarError(f"XNYS schedule lookup failed for {d.isoformat()}: {exc}") from exc
    return not schedule.empty


def is_eligible_session(d: date) -> bool:
    """True iff `d` is an eligible forward-validation session: an XNYS trading session on or after the
    frozen forward start. Dates before the start are ineligible (the §0 no-backdating floor), never an
    error — the scheduler may legitimately fire before the window's first session."""
    if d.isoformat() < FORWARD_START:
        return False
    return is_trading_session(d)


def eligible_sessions(start: date, end: date) -> list[date]:
    """Every eligible session in [start, end], ascending. Used by operational reporting (how many
    sessions SHOULD the record contain by now) — never to back-fill a missed session, which the
    committed chain's strictly-increasing session dates would refuse anyway."""
    if end < start:
        raise EvalCalendarError(f"eligible_sessions: end {end} precedes start {start}")
    floor = date.fromisoformat(FORWARD_START)
    lo = max(start, floor)
    if end < lo:
        return []
    cal = _xnys()
    try:
        schedule = cal.schedule(start_date=lo, end_date=end)
    except Exception as exc:
        raise EvalCalendarError(
            f"XNYS schedule lookup failed for {lo.isoformat()}..{end.isoformat()}: {exc}") from exc
    return [ts.date() for ts in schedule.index]


def next_eligible_session(after: date) -> date:
    """The first eligible session STRICTLY after `after` (never `after` itself).

    This is what makes "one governed observation per eligible session" enforceable: the runner requires
    the session it is asked to record to be exactly this date, so a session that was never run cannot be
    stepped over silently. Weekends and holidays are not gaps — they are simply not sessions.
    """
    floor = date.fromisoformat(FORWARD_START)
    lo = max(after + timedelta(days=1), floor)
    for span in (14, 60, 400):                      # widen rather than assume a maximum market closure
        found = eligible_sessions(lo, lo + timedelta(days=span))
        if found:
            return found[0]
    raise EvalCalendarError(
        f"no XNYS session found within 400 days after {after.isoformat()} — the calendar cannot be "
        f"trusted to advance the record")


def governing_timezone() -> str:
    """The governing session timezone (§0). Recorded in operational output for provenance."""
    return GOVERNING_TZ
