"""Range Trader daily levels-vs-range capture — materializes the daily SET levels + high/low into the DB.

For a date window this records one *frozen* row per (symbol, ET trading day): the **buy/sell levels the
strategy SET that day** (the opening-range fade entry/exit — from its ``range_levels`` INFO signal, NOT
the executed fill prices) alongside the stock's RTH daily low/high (from the 1Day bar cache). This lets
the user see how well each day's *planned* fade levels sat inside the realized range. Only COMPLETED days
(< today ET) are captured, and each (symbol, date) is inserted once — a re-query never recomputes. This
is the read-through populate behind ``GET /api/v1/range-execution``: querying a window backfills any
completed days the table doesn't have yet, so there is no cron and no daily file.

``avg_buy_price`` / ``avg_sell_price`` hold the SET daily buy/sell level (column names retained for API/
schema stability); they are the strategy's planned levels, not fill averages.

A day's rows cover the symbols that were *in the book that day* — reconstructed from that day's
``range_levels`` signals, not from the book's current roster. The Top-5 rotates its slots, so a
window-wide symbol union would retroactively mint blank rows for every rotated-out name on every day it
was never held (and freeze them). See ``_membership_by_day``.

**No membership evidence → no historical row creation.** A day's book is only ever established from
contemporaneous ``range_levels`` signals, or carried forward along a chain rooted in them. Days before
the strategy ever published (the emit began 2026-07-06) have no authoritative membership, so capture
skips them entirely rather than guessing. Substituting today's roster backwards is the wrong semantic:
it rewrites history to name whoever holds the rotating slot *now*.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Any
from zoneinfo import ZoneInfo

import structlog
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.range_execution_record import RangeExecutionRecord
from app.db.models.signal import Signal, SignalType
from app.db.models.strategy import Strategy
from app.db.models.symbol import Symbol

logger = structlog.get_logger(__name__)

RANGE_USER_ID = 2  # the Range Trader paper book (user 2 / account 2)
_ET = ZoneInfo("America/New_York")


def _dec(v: Any) -> Decimal | None:
    return Decimal(str(v)) if v is not None else None


def _range_levels_rows(rows: Sequence[Any]) -> list[tuple[str, str, dict]]:
    """Keep only the ``range_levels`` payloads, as (et_date_iso, TICKER, payload)."""
    out: list[tuple[str, str, dict]] = []
    for day_iso, ticker, payload in rows:
        p = payload if isinstance(payload, dict) else {}
        if p.get("kind") == "range_levels":
            out.append((day_iso, ticker.upper(), p))
    return out


def _levels_query(strat_id: int, d_from: date, d_to: date) -> Any:
    """``range_levels`` INFO signals for the Range Trader, ordered oldest-first.

    The ET date is matched by the UTC-date prefix of ``received_at`` (a string in SQLite); the
    opening-range signals fire mid-session, when the UTC and ET calendar dates coincide."""
    return (
        select(
            func.substr(Signal.received_at, 1, 10),
            Symbol.ticker,
            Signal.payload_json,
        )
        .join(Symbol, Symbol.id == Signal.symbol_id)
        .where(
            Signal.strategy_id == strat_id,
            Signal.type == SignalType.INFO,
            func.substr(Signal.received_at, 1, 10) >= d_from.isoformat(),
            func.substr(Signal.received_at, 1, 10) <= d_to.isoformat(),
        )
        .order_by(Signal.received_at)
    )


async def _levels_by_day(
    session: AsyncSession, strat_id: int, d_from: date, d_to: date
) -> dict[tuple[str, str], tuple[Decimal | None, Decimal | None]]:
    """{(et_date_iso, TICKER): (buy_level, sell_level)} from the Range Trader's daily ``range_levels``
    signals over the window.

    The strategy logs one ``INFO`` signal per Top-5 symbol at the open with payload
    ``{"kind": "range_levels", "buy", "sell", "stop", ...}`` — the fade levels it SET for the day. If a
    symbol has more than one such signal in a day, the first (opening-range) one wins.
    """
    rows = (await session.execute(_levels_query(strat_id, d_from, d_to))).all()
    out: dict[tuple[str, str], tuple[Decimal | None, Decimal | None]] = {}
    for day_iso, ticker, p in _range_levels_rows(rows):
        key = (day_iso, ticker)
        if key in out:
            continue  # first (opening-range) levels of the day win
        out[key] = (_dec(p.get("buy")), _dec(p.get("sell")))
    return out


async def _membership_before(
    session: AsyncSession, strat_id: int, before: date, *, lookback_days: int = 30
) -> set[str]:
    """The book's symbols on the most recent day that published levels *before* ``before``.

    Seeds the carry-forward so a window that opens on an outage day attributes that day to the book
    that was actually running then, rather than to today's roster."""
    rows = (
        await session.execute(
            _levels_query(
                strat_id, before - timedelta(days=lookback_days), before - timedelta(days=1)
            )
        )
    ).all()
    parsed = _range_levels_rows(rows)
    if not parsed:
        return set()
    last_day = parsed[-1][0]  # oldest-first → the last row is the most recent day
    return {ticker for day_iso, ticker, _p in parsed if day_iso == last_day}


def _members_for_day(published: set[str], carried: set[str]) -> set[str]:
    """The book's membership for one day, given the symbols that published levels that day.

    - Nothing published (stack down / market holiday) → carry the previous membership forward, so an
      outage stays visible as a row with blank levels instead of vanishing from the history.
    - A strict subset of the previous membership published → one name failed to emit; keep it as a
      blank-level gap rather than silently dropping the row.
    - Anything else (including a rotation, which introduces a name the previous membership lacked) →
      the day's own signals are the truth. A rotation *and* an emit failure on the same day resolves as
      a rotation; the failed name loses its gap row that day.
    """
    if not published:
        return set(carried)
    if carried and published < carried:
        return set(carried)
    return set(published)


async def _membership_by_day(
    session: AsyncSession,
    strat_id: int,
    levels: dict[tuple[str, str], Any],
    d_from: date,
    d_to: date,
) -> dict[date, set[str]]:
    """{et_date: symbols in the book that day} across the window, carrying membership forward.

    A day maps to the EMPTY set when its membership cannot be established from evidence — no signals
    that day and no carry-forward chain reaching back to a day that had them. The caller must read
    that as "unknown", never as "the book held nothing", and never as an invitation to substitute the
    current roster: the ``range_levels`` emit only began 2026-07-06, so every earlier day is
    evidence-free, and guessing today's Top-5 backwards names a symbol the book did not hold (proven
    2026-08-18 — 06-24..07-02 ran TSLA in the rotating slot while the live roster had moved to NVDA).
    """
    published_by_day: dict[str, set[str]] = {}
    for day_iso, ticker in levels:
        published_by_day.setdefault(day_iso, set()).add(ticker)

    carried = await _membership_before(session, strat_id, d_from)

    out: dict[date, set[str]] = {}
    d = d_from
    while d <= d_to:
        members = _members_for_day(published_by_day.get(d.isoformat(), set()), carried)
        out[d] = members
        if members:
            carried = members
        d += timedelta(days=1)
    return out


async def _daily_low_high_map(
    bar_cache: Any, symbol: str, d_from: date, d_to: date
) -> dict[str, tuple[Decimal, Decimal]]:
    """{et_date_iso: (low, high)} for the symbol over the window, from the 1Day bar cache.

    One ``get_bars`` call for the whole window (it re-fetches missing days from Alpaca)."""
    start = datetime(d_from.year, d_from.month, d_from.day, tzinfo=UTC)
    end = datetime(d_to.year, d_to.month, d_to.day, tzinfo=UTC) + timedelta(days=1)
    try:
        df = await bar_cache.get_bars(symbol, "1Day", start, end)
    except Exception:
        logger.warning("range_capture_bar_fetch_failed", symbol=symbol)
        return {}
    if df is None or getattr(df, "empty", True):
        return {}
    import pandas as pd

    df = df.copy()
    df["d"] = pd.to_datetime(df["t"]).dt.strftime("%Y-%m-%d")
    return {r["d"]: (Decimal(str(r["l"])), Decimal(str(r["h"]))) for _, r in df.iterrows()}


async def capture_window(session: AsyncSession, bar_cache: Any, d_from: date, d_to: date) -> int:
    """Materialize + freeze completed range-execution days in [d_from, d_to].

    Each day is captured for the symbols that were in the book *that day* (``_membership_by_day``), so a
    Top-5 rotation never mints blank rows for a name on days it was not held. A day whose membership
    rests on no signal evidence is skipped outright — see the module docstring.

    Idempotent: only (symbol, et_date) rows that don't already exist are inserted, and only for days
    strictly before today ET (a day that has closed). Returns the number of rows inserted."""
    today_et = datetime.now(_ET).date()
    end = min(d_to, today_et - timedelta(days=1))
    if bar_cache is None or end < d_from:
        return 0

    strat_id = await session.scalar(
        select(Strategy.id)
        .where(Strategy.name.like("Range Trader%"))
        .order_by(Strategy.id)
        .limit(1)
    )
    if strat_id is None:
        return 0

    levels = await _levels_by_day(session, strat_id, d_from, end)
    members_by_day = await _membership_by_day(session, strat_id, levels, d_from, end)
    universe = sorted(set().union(*members_by_day.values()) if members_by_day else set())
    if not universe:
        return 0

    # Prefetch already-captured (symbol, et_date) pairs and the daily bars per symbol.
    existing = {
        (sym, dt)
        for sym, dt in (
            await session.execute(
                select(RangeExecutionRecord.symbol, RangeExecutionRecord.et_date).where(
                    RangeExecutionRecord.et_date >= d_from,
                    RangeExecutionRecord.et_date <= end,
                )
            )
        ).all()
    }
    hl_maps = {sym: await _daily_low_high_map(bar_cache, sym, d_from, end) for sym in universe}

    existing_by_day: dict[date, set[str]] = {}
    for sym, dt in existing:
        existing_by_day.setdefault(dt, set()).add(sym)

    now = datetime.now(UTC)
    inserted = 0
    d = d_from
    while d <= end:
        d_iso = d.isoformat()
        members = members_by_day.get(d, set())
        if not members:
            # No evidence for that day's book. Unknown is not empty — skip rather than guess.
            d += timedelta(days=1)
            continue

        # Invariant: capture never takes a date past its evidence-backed membership count. Only
        # members are ever inserted, so an overflow means rows already on file name symbols the book
        # did not hold that day — the signature the pre-#638 window-union defect left behind, and
        # what a roster-guessed pre-history day would look like. Fail closed: report, insert nothing.
        unexpected = existing_by_day.get(d, set()) - members
        if unexpected:
            logger.error(
                "range_capture_membership_overflow",
                et_date=d_iso,
                unexpected=sorted(unexpected),
                members=sorted(members),
            )
            d += timedelta(days=1)
            continue

        for sym in sorted(members):
            if (sym, d) in existing:
                continue  # frozen — never recompute
            lh = hl_maps.get(sym, {}).get(d_iso)
            if lh is None:
                continue  # non-trading day / no bar → retry on a later query
            low, high = lh
            buy_level, sell_level = levels.get((d_iso, sym), (None, None))
            session.add(
                RangeExecutionRecord(
                    et_date=d,
                    symbol=sym,
                    avg_buy_price=buy_level,  # the SET daily buy level (range_levels), not a fill
                    avg_sell_price=sell_level,  # the SET daily sell level
                    daily_low=low,
                    daily_high=high,
                    captured_at=now,
                )
            )
            inserted += 1
        d += timedelta(days=1)

    if inserted:
        await session.commit()
    return inserted
