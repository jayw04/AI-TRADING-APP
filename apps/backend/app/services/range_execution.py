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
"""

from __future__ import annotations

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
FALLBACK_TOP5 = ["GOOGL", "MU", "INTC", "AMD", "TSLA"]
_ET = ZoneInfo("America/New_York")


async def _current_top5(session: AsyncSession) -> list[str]:
    """The Range Trader's current Top-5 (symbols_json), falling back to a constant."""
    row = await session.scalar(
        select(Strategy.symbols_json)
        .where(Strategy.name.like("Range Trader%"))
        .order_by(Strategy.id)
        .limit(1)
    )
    if row:
        try:
            syms = [str(s).upper() for s in row]
            if syms:
                return syms
        except TypeError:
            pass
    return FALLBACK_TOP5


def _dec(v: Any) -> Decimal | None:
    return Decimal(str(v)) if v is not None else None


async def _levels_by_day(
    session: AsyncSession, d_from: date, d_to: date
) -> dict[tuple[str, str], tuple[Decimal | None, Decimal | None]]:
    """{(et_date_iso, TICKER): (buy_level, sell_level)} from the Range Trader's daily ``range_levels``
    signals over the window.

    The strategy logs one ``INFO`` signal per Top-5 symbol at the open with payload
    ``{"kind": "range_levels", "buy", "sell", "stop", ...}`` — the fade levels it SET for the day. The
    ET date is matched by the UTC-date prefix of ``received_at`` (a string in SQLite); the open-range
    signals fire mid-session, when the UTC and ET calendar dates coincide. If a symbol has more than one
    such signal in a day, the first (opening-range) one wins.
    """
    strat_id = await session.scalar(
        select(Strategy.id)
        .where(Strategy.name.like("Range Trader%"))
        .order_by(Strategy.id)
        .limit(1)
    )
    if strat_id is None:
        return {}
    rows = (
        await session.execute(
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
    ).all()
    out: dict[tuple[str, str], tuple[Decimal | None, Decimal | None]] = {}
    for day_iso, ticker, payload in rows:
        p = payload if isinstance(payload, dict) else {}
        if p.get("kind") != "range_levels":
            continue
        key = (day_iso, ticker.upper())
        if key in out:
            continue  # first (opening-range) levels of the day win
        out[key] = (_dec(p.get("buy")), _dec(p.get("sell")))
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
    return {
        r["d"]: (Decimal(str(r["l"])), Decimal(str(r["h"])))
        for _, r in df.iterrows()
    }


async def capture_window(
    session: AsyncSession, bar_cache: Any, d_from: date, d_to: date
) -> int:
    """Materialize + freeze completed range-execution days in [d_from, d_to].

    Idempotent: only (symbol, et_date) rows that don't already exist are inserted, and only for days
    strictly before today ET (a day that has closed). Returns the number of rows inserted."""
    today_et = datetime.now(_ET).date()
    end = min(d_to, today_et - timedelta(days=1))
    if bar_cache is None or end < d_from:
        return 0

    levels = await _levels_by_day(session, d_from, end)
    leveled = {ticker for (_d, ticker) in levels}
    universe = sorted(leveled | set(await _current_top5(session)))

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
    hl_maps = {
        sym: await _daily_low_high_map(bar_cache, sym, d_from, end) for sym in universe
    }

    now = datetime.now(UTC)
    inserted = 0
    d = d_from
    while d <= end:
        d_iso = d.isoformat()
        for sym in universe:
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
                    avg_buy_price=buy_level,   # the SET daily buy level (range_levels), not a fill
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
