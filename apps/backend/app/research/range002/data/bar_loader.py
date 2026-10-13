"""Minute-bar loader: a Parquet/DuckDB ``minute_bars`` table -> ``SessionBars`` (BUILD, synthetic).

Source columns: ``symbol, ts, open, high, low, close, volume, basis``; ``basis`` is the price
basis the bar was fetched under and must equal the spec's ``data.intraday_price_basis`` on every
row (a missing column, a NULL or a different tag is a DataDefectError: a table of unknown or
split-adjusted basis is never loaded at the wrong scale). ``ts`` is the bar's START as a
UTC instant (a declared convention, checked against the spec's, never inferred). Reading values
requires a guard capability, so this cannot be pointed at real data outside an authorised run.

Minute classification is conservative (Backlog L7). A regular-session minute with no bar is a
NO_TRADE minute ONLY when independent interval-level evidence names that exact minute
(``no_trade_evidence``, e.g. an independent trade-count / quote source). Otherwise it is
unresolved missingness: DATA_GAP. A daily-volume total is NOT such evidence: volume can
reconcile while the missing minute's timing is wrong, so the total is exposed only as the
diagnostic ``volume_reconciles`` and never clears a gap. A halt is recorded only from explicit
evidence passed in. A bar is never fabricated and no fill is implied for a missing minute.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from datetime import date, datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from app.research.range002.governance.results_guard import requires_capability
from app.research.range002.screen.errors import DataDefectError
from app.research.range002.screen.types import Bar, SessionBars

_ET = ZoneInfo("America/New_York")
_UTC = ZoneInfo("UTC")
_OPEN = time(9, 30)


def _minute_range(close: time) -> list[time]:
    out: list[time] = []
    cur = datetime.combine(date(2000, 1, 1), _OPEN)
    end = datetime.combine(date(2000, 1, 1), close)
    while cur < end:
        out.append(cur.time())
        cur += timedelta(minutes=1)
    return out


@requires_capability
def load_session(
    capability: object,
    con: Any,
    params: Any,  # reads only .feed, .bar_timestamp_convention, .intraday_price_basis
    symbol: str,
    day: date,
    session_close: time,
    *,
    permaticker: str,
    source_feed: str,
    source_ts_convention: str,
    no_trade_evidence: frozenset[time],
    halt_minutes: frozenset[time],
) -> SessionBars | None:
    """One symbol-day, or None when the source holds no regular-session bar for it.

    ``permaticker`` is the issuer's stable identity (the scheduler's tie-break key); the caller
    resolves it from the identity map for ``(symbol, day)``."""
    if not isinstance(permaticker, str) or not permaticker.strip():
        raise DataDefectError(f"{symbol} {day}: a non-empty permaticker is required")
    if source_feed != params.feed:
        raise DataDefectError(f"source feed {source_feed!r} != spec feed {params.feed!r}")
    if source_ts_convention != params.bar_timestamp_convention:
        raise DataDefectError(
            f"source timestamp convention {source_ts_convention!r} != "
            f"spec {params.bar_timestamp_convention!r}"
        )
    rng = getattr(capability, "date_range", None)
    if rng is None or not (rng.start <= day <= rng.end):
        raise DataDefectError(f"{symbol} {day}: outside the authorised date range")
    lo = datetime.combine(day - timedelta(days=1), time(0, 0))  # naive UTC bounds, padded a day
    hi = datetime.combine(day + timedelta(days=2), time(0, 0))
    has_basis = any(
        str(r[0]).lower() == "basis"
        for r in con.execute('SELECT column_name FROM (DESCRIBE "minute_bars")').fetchall()
    )
    if not has_basis:
        raise DataDefectError(
            f"{symbol} {day}: minute_bars has no 'basis' column; a bar table of unknown price "
            f"basis is refused (spec requires {params.intraday_price_basis!r})"
        )
    rows = con.execute(
        'SELECT ts, open, high, low, close, volume, basis FROM "minute_bars" '
        "WHERE symbol = ? AND ts >= ? AND ts < ?",
        [symbol, lo, hi],
    ).fetchall()
    bars: dict[time, Bar] = {}
    for ts, o, h, low, c, v, basis in rows:
        if basis is None or str(basis) != params.intraday_price_basis:
            raise DataDefectError(
                f"{symbol} {day}: bar basis {basis!r} != spec data.intraday_price_basis "
                f"{params.intraday_price_basis!r} (incompatible join)"
            )
        local = (ts.replace(tzinfo=_UTC) if ts.tzinfo is None else ts).astimezone(_ET)
        if local.date() != day or not (_OPEN <= local.time() < session_close):
            continue
        key = local.time().replace(second=0, microsecond=0)
        if key in bars:
            raise DataDefectError(f"{symbol} {day}: duplicate bar at {key}")
        bars[key] = Bar(key, float(o), float(h), float(low), float(c), int(v))
    if not bars:
        return None
    contradictory = sorted(m for m in no_trade_evidence | halt_minutes if m in bars)
    if contradictory:
        raise DataDefectError(
            f"{symbol} {day}: no-trade/halt evidence for minute(s) {contradictory[:3]} that have bars"
        )
    missing = [m for m in _minute_range(session_close) if m not in bars]
    gaps = frozenset(m for m in missing if m not in no_trade_evidence and m not in halt_minutes)
    return SessionBars(
        symbol,
        day,
        source_feed,
        source_ts_convention,
        session_close,
        tuple(sorted(bars.values(), key=lambda b: b.start)),
        gaps,
        frozenset(halt_minutes),
        permaticker,
    )


def _permaticker_for(mapping: Mapping[tuple[str, date], str], sym: str, day: date) -> str:
    got = mapping.get((sym, day))
    if got is None or not got.strip():
        raise DataDefectError(f"{sym} {day}: no permaticker supplied for the symbol-day")
    return got


@requires_capability
def load_sessions(
    capability: object,
    con: Any,
    params: Any,  # reads only .feed, .bar_timestamp_convention, .intraday_price_basis
    expected: Iterable[tuple[str, date]],
    closes: Mapping[date, time],
    *,
    source_feed: str,
    source_ts_convention: str,
    no_trade_evidence: Mapping[tuple[str, date], frozenset[time]],
    permaticker_of: Mapping[tuple[str, date], str],
) -> tuple[tuple[SessionBars, ...], tuple[tuple[str, date], ...]]:
    """Every expected symbol-day is either returned or listed as missing: none disappears.
    ``permaticker_of`` maps every expected ``(symbol, day)`` to the issuer's permaticker."""
    sessions: list[SessionBars] = []
    missing: list[tuple[str, date]] = []
    for sym, day in sorted(set(expected), key=lambda k: (k[1], k[0])):
        if day not in closes:
            raise DataDefectError(f"{sym} {day}: not a session in the supplied calendar")
        got = load_session(
            capability,
            con,
            params,
            sym,
            day,
            closes[day],
            permaticker=_permaticker_for(permaticker_of, sym, day),
            source_feed=source_feed,
            source_ts_convention=source_ts_convention,
            no_trade_evidence=no_trade_evidence.get((sym, day), frozenset()),
            halt_minutes=frozenset(),
        )
        (sessions if got is not None else missing).append(got if got is not None else (sym, day))  # type: ignore[arg-type]
    return tuple(sessions), tuple(missing)


@requires_capability
def volume_reconciles(
    capability: object, session: SessionBars, daily_volume: float, tolerance: float
) -> bool:
    """DIAGNOSTIC only: does the summed bar volume reach the daily total within ``tolerance``?

    It never changes minute classification (a total cannot place a missing minute in time); it
    exists so a report can say how far the minute data is from the daily corpus."""
    if not 0 <= tolerance < 1 or daily_volume < 0:
        raise DataDefectError("tolerance must be in [0, 1) and daily_volume non-negative")
    return sum(b.volume for b in session.bars) >= daily_volume * (1 - tolerance)
