"""Regular-session calendar for the screen: session days and each day's close time (ET).

Return-blind and pure (dates and times only). Uses the NYSE schedule from
``pandas_market_calendars`` (a declared dependency). The result must still be VERIFIED against
the vendor's session data before RUN (owner O-9: "using a verified calendar"); this module only
supplies the expected schedule and makes early closes explicit.
"""

from __future__ import annotations

from datetime import date, time

PURE_FUNCTIONS = ("expected_sessions",)


def expected_sessions(start: date, end: date) -> dict[date, time]:
    """Map each NYSE regular-session date in [start, end] to its closing time (America/New_York)."""
    import pandas_market_calendars as mcal

    cal = mcal.get_calendar("NYSE")
    sched = cal.schedule(start_date=start.isoformat(), end_date=end.isoformat())
    out: dict[date, time] = {}
    for ts, row in sched.iterrows():
        close = row["market_close"].tz_convert("America/New_York")
        out[ts.date()] = time(close.hour, close.minute)
    return out
