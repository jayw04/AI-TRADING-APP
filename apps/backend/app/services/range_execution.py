"""Range Trader daily execution-vs-range capture — materializes daily high/low into the DB.

For a date window this records one *frozen* row per (symbol, ET trading day): our qty-weighted average
BUY/SELL fill (from orders/fills, user 2) alongside the stock's RTH daily low/high (from the 1Day bar
cache). Only COMPLETED days (< today ET) are captured, and each (symbol, date) is inserted once — a
re-query never recomputes. This is the read-through populate behind ``GET /api/v1/range-execution``:
querying a window backfills any completed days the table doesn't have yet, so there is no cron and no
daily file.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Any
from zoneinfo import ZoneInfo

import structlog
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.fill import Fill
from app.db.models.order import Order
from app.db.models.range_execution_record import RangeExecutionRecord
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


async def _fills_by_day(
    session: AsyncSession, d_from: date, d_to: date
) -> dict[tuple[str, str, str], Decimal]:
    """{(et_date_iso, TICKER, 'BUY'|'SELL'): qty-weighted avg fill price} over the window.

    Matches the ET date by the UTC-date prefix of ``created_at`` (a string in SQLite); during RTH the
    UTC and ET calendar dates coincide, which is when the intraday range book trades.
    """
    rows = (
        await session.execute(
            select(
                func.substr(Order.created_at, 1, 10),
                Symbol.ticker,
                Order.side,
                Fill.qty,
                Fill.price,
            )
            .join(Fill, Fill.order_id == Order.id)
            .join(Symbol, Symbol.id == Order.symbol_id)
            .where(
                Order.user_id == RANGE_USER_ID,
                func.substr(Order.created_at, 1, 10) >= d_from.isoformat(),
                func.substr(Order.created_at, 1, 10) <= d_to.isoformat(),
            )
        )
    ).all()
    agg: dict[tuple[str, str, str], list[Decimal]] = {}
    for day_iso, ticker, side, qty, price in rows:
        s = getattr(side, "value", str(side)).upper()
        key = (day_iso, ticker.upper(), s)
        q, n = agg.get(key, [Decimal(0), Decimal(0)])
        agg[key] = [q + Decimal(qty), n + Decimal(qty) * Decimal(price)]
    return {k: (n / q) for k, (q, n) in agg.items() if q > 0}


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

    fills = await _fills_by_day(session, d_from, end)
    traded = {ticker for (_d, ticker, _s) in fills}
    universe = sorted(traded | set(await _current_top5(session)))

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
            session.add(
                RangeExecutionRecord(
                    et_date=d,
                    symbol=sym,
                    avg_buy_price=fills.get((d_iso, sym, "BUY")),
                    avg_sell_price=fills.get((d_iso, sym, "SELL")),
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
