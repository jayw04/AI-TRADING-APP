"""Market Session Model (design doc §9A) — classify an instant into a US-equity
market session and decide whether a strategy may act in it.

Classifies a UTC instant into ``REGULAR`` / ``PRE_MARKET`` / ``AFTER_HOURS`` /
``CLOSED``, honoring weekends, full-day holidays and (early-close) half-days.

Calendar source, in order of preference:
  1. ``pandas_market_calendars`` (XNYS) — authoritative trading days + the exact
     open/close per day, including half-days. Used when installed.
  2. A network-free fallback — weekday filter minus a curated NYSE holiday list,
     plus a curated half-day (early-close) set — for environments where the
     calendar package can't be installed (Norton SSL blocks the install on the
     dev box; see ``equity_curve._get_nyse_business_days`` for the same posture).

Consumers:
  - ``StrategyEngine._dispatch_bar_tick`` / ``dispatch_event_bar`` — the primary
    dispatch gate: ticks outside a strategy's permitted sessions are skipped.
  - ``StrategyContext.session`` — strategy-visible current session + open/close.

Conservative default (§9A.4): a strategy trades **REGULAR hours only** unless it
sets the ``allow_extended_hours`` param. ``CLOSED`` is never dispatchable — the
gate fails toward *not trading*.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, time
from enum import StrEnum
from zoneinfo import ZoneInfo

import structlog

logger = structlog.get_logger(__name__)

_ET = ZoneInfo("America/New_York")

# Standard US-equity session boundaries (ET local time).
PRE_MARKET_OPEN = time(4, 0)
REGULAR_OPEN = time(9, 30)
REGULAR_CLOSE = time(16, 0)  # overridden by the early close on a half-day
AFTER_HOURS_CLOSE = time(20, 0)
HALF_DAY_CLOSE = time(13, 0)  # NYSE early-close time

# Curated NYSE full-day closures (the weekday filter handles weekends). Extend
# annually — a missing holiday only causes a spurious dispatch attempt that the
# broker/risk layer still rejects, never a wrong trade. Mirrors
# ``equity_curve._NYSE_HOLIDAYS``; install pandas_market_calendars for the
# authoritative set.
_NYSE_HOLIDAYS: frozenset[date] = frozenset(
    {
        # 2025
        date(2025, 1, 1),
        date(2025, 1, 20),
        date(2025, 2, 17),
        date(2025, 4, 18),
        date(2025, 5, 26),
        date(2025, 6, 19),
        date(2025, 7, 4),
        date(2025, 9, 1),
        date(2025, 11, 27),
        date(2025, 12, 25),
        # 2026
        date(2026, 1, 1),
        date(2026, 1, 19),
        date(2026, 2, 16),
        date(2026, 4, 3),
        date(2026, 5, 25),
        date(2026, 6, 19),
        date(2026, 7, 3),
        date(2026, 9, 7),
        date(2026, 11, 26),
        date(2026, 12, 25),
        # 2027
        date(2027, 1, 1),
        date(2027, 1, 18),
        date(2027, 2, 15),
        date(2027, 3, 26),
        date(2027, 5, 31),
        date(2027, 6, 18),
        date(2027, 7, 5),
        date(2027, 9, 6),
        date(2027, 11, 25),
        date(2027, 12, 24),
    }
)

# Curated NYSE early-close (half) days — 13:00 ET close. Best-effort; the mcal
# path detects these authoritatively when installed.
_NYSE_HALF_DAYS: frozenset[date] = frozenset(
    {
        date(2025, 7, 3),
        date(2025, 11, 28),
        date(2025, 12, 24),
        date(2026, 11, 27),
        date(2026, 12, 24),
        date(2027, 11, 26),
    }
)


class MarketSessionType(StrEnum):
    """The market session an instant falls in (US equities)."""

    REGULAR = "REGULAR"
    PRE_MARKET = "PRE_MARKET"
    AFTER_HOURS = "AFTER_HOURS"
    CLOSED = "CLOSED"


@dataclass(frozen=True)
class _DaySchedule:
    """The open/close for a single trading day (ET local times)."""

    open: time
    close: time
    half_day: bool


@dataclass(frozen=True)
class SessionInfo:
    """The classification of one instant, plus the day's boundaries (UTC)."""

    session: MarketSessionType
    as_of: datetime  # the UTC instant classified
    is_trading_day: bool
    is_half_day: bool
    regular_open: datetime | None  # UTC; None on a non-trading day
    regular_close: datetime | None  # UTC; the early close on a half-day

    @property
    def is_regular(self) -> bool:
        return self.session is MarketSessionType.REGULAR

    def dispatchable(self, *, allow_extended: bool) -> bool:
        """Whether a strategy may act now. REGULAR always; PRE/AFTER only with
        ``allow_extended``; CLOSED never (fail toward not trading)."""
        if self.session is MarketSessionType.REGULAR:
            return True
        if self.session in (
            MarketSessionType.PRE_MARKET,
            MarketSessionType.AFTER_HOURS,
        ):
            return allow_extended
        return False


class MarketSession:
    """Classifies instants into market sessions, caching the per-day schedule.

    Stateless apart from a small per-day schedule cache; safe to share. A single
    instance is exposed via :func:`default_market_session`.
    """

    def __init__(self) -> None:
        self._cache: dict[date, _DaySchedule | None] = {}

    def classify(self, instant: datetime | None = None) -> SessionInfo:
        """Classify ``instant`` (default: now, UTC). Naive datetimes are treated
        as UTC."""
        now = instant if instant is not None else datetime.now(UTC)
        if now.tzinfo is None:
            now = now.replace(tzinfo=UTC)
        now_utc = now.astimezone(UTC)
        et = now.astimezone(_ET)

        sched = self._day_schedule(et.date())
        if sched is None:
            return SessionInfo(
                session=MarketSessionType.CLOSED,
                as_of=now_utc,
                is_trading_day=False,
                is_half_day=False,
                regular_open=None,
                regular_close=None,
            )

        t = et.time()
        if sched.open <= t < sched.close:
            session = MarketSessionType.REGULAR
        elif PRE_MARKET_OPEN <= t < sched.open:
            session = MarketSessionType.PRE_MARKET
        elif sched.close <= t < AFTER_HOURS_CLOSE:
            session = MarketSessionType.AFTER_HOURS
        else:
            session = MarketSessionType.CLOSED

        open_utc = datetime.combine(et.date(), sched.open, tzinfo=_ET).astimezone(UTC)
        close_utc = datetime.combine(et.date(), sched.close, tzinfo=_ET).astimezone(UTC)
        return SessionInfo(
            session=session,
            as_of=now_utc,
            is_trading_day=True,
            is_half_day=sched.half_day,
            regular_open=open_utc,
            regular_close=close_utc,
        )

    def is_dispatchable(
        self, instant: datetime | None = None, *, allow_extended: bool = False
    ) -> bool:
        """Convenience: classify ``instant`` and return its dispatchability."""
        return self.classify(instant).dispatchable(allow_extended=allow_extended)

    def _day_schedule(self, d: date) -> _DaySchedule | None:
        if d not in self._cache:
            self._cache[d] = _compute_day_schedule(d)
        return self._cache[d]


def is_trading_day(d: date) -> bool:
    """Is ``d`` an NYSE session? (Weekends and holidays are not.)

    Public wrapper over the same XNYS calendar the dispatch gate uses, so ops tooling can
    measure data staleness in SESSIONS rather than calendar days — "3 days old" over a
    holiday weekend is current, not stale, and counting calendar days cries wolf.
    """
    return default_market_session()._day_schedule(d) is not None


def _compute_day_schedule(d: date) -> _DaySchedule | None:
    """The trading schedule for date ``d`` (None if not a trading day).

    Prefers pandas_market_calendars (XNYS); falls back to the curated lists."""
    try:
        import pandas_market_calendars as mcal
    except ImportError:
        return _fallback_day_schedule(d)

    nyse = mcal.get_calendar("XNYS")
    schedule = nyse.schedule(start_date=d, end_date=d)
    if schedule.empty:
        return None  # holiday / weekend
    row = schedule.iloc[0]
    open_et = row["market_open"].tz_convert(_ET).time()
    close_et = row["market_close"].tz_convert(_ET).time()
    return _DaySchedule(open=open_et, close=close_et, half_day=close_et < REGULAR_CLOSE)


def _fallback_day_schedule(d: date) -> _DaySchedule | None:
    """Network-free schedule: weekday minus curated holidays; curated half-days
    get a 13:00 ET close. Logs the degraded path once so the gap is visible."""
    if d.weekday() >= 5 or d in _NYSE_HOLIDAYS:
        return None
    if not _FALLBACK_WARNED:
        _warn_fallback()
    if d in _NYSE_HALF_DAYS:
        return _DaySchedule(open=REGULAR_OPEN, close=HALF_DAY_CLOSE, half_day=True)
    return _DaySchedule(open=REGULAR_OPEN, close=REGULAR_CLOSE, half_day=False)


_FALLBACK_WARNED = False


def _warn_fallback() -> None:
    global _FALLBACK_WARNED
    _FALLBACK_WARNED = True
    logger.warning(
        "market_session_calendar_fallback",
        detail=(
            "pandas_market_calendars not installed; using curated NYSE holiday/"
            "half-day lists. Half-day coverage is best-effort — install the "
            "package for authoritative early-close handling."
        ),
    )


_DEFAULT: MarketSession | None = None


def default_market_session() -> MarketSession:
    """The process-wide shared :class:`MarketSession` (schedule cache reuse)."""
    global _DEFAULT
    if _DEFAULT is None:
        _DEFAULT = MarketSession()
    return _DEFAULT
