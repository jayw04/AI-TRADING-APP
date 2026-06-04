"""Equity-curve reconstruction from fill history (P6b §2b-variant).

Per settled decisions:
- Daily marks on NYSE business days (Q2 lean).
- E(t) = capital_base + realized_pnl_to_t + unrealized_pnl_at_close_t.
- capital_base passed by the caller for apples-to-apples Sharpe comparison
  (Sharpe shifts with capital_base because daily returns are dE/E, not dE — both
  sides of a variant-vs-live comparison MUST share the same capital_base).
- Skip days where any open position's close is unavailable.

Market data: daily closes come from the injected ``BarCache`` (``app.state.
bar_cache``; ``app/market_data/bar_cache.py``) via ``get_bars(ticker, "1Day",
day, day)`` → last bar's close. There is no ``app/services/market_data.py``.
``BarCache`` hits ``data.alpaca.markets``, which Norton SSL-inspects and blocks
locally, so the real-close path is NOT exercisable in the dev env — tests mock
the fetch and the live run is a deferred (non-Norton) gate.

Used by: variant comparison (P6b §2b), drift-detection live-Sharpe (P6+ when
adopted), the §3 promotion gate.
"""
from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Any

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.enums import OrderSide, OrderSourceType
from app.db.models.fill import Fill
from app.db.models.order import Order
from app.db.models.symbol import Symbol

logger = structlog.get_logger(__name__)

DEFAULT_CAPITAL_BASE = Decimal("100000")
ZERO = Decimal("0")


def _aware(dt: datetime) -> datetime:
    """Coerce a (possibly naive) datetime to aware-UTC. SQLite returns
    DateTime(tz=True) columns without tzinfo, so comparisons against aware
    bounds raise without this."""
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=UTC)


async def _close_on_day(bar_cache: Any, ticker: str, day: date) -> Decimal | None:
    """EOD close for a ticker on a date via BarCache. None if unavailable
    (missing data / Norton block / no bar_cache in tests/data-only boots)."""
    if bar_cache is None:
        return None
    start = datetime.combine(day, datetime.min.time(), tzinfo=UTC)
    end = datetime.combine(day, datetime.max.time(), tzinfo=UTC)
    bars = await bar_cache.get_bars(ticker, "1Day", start, end)
    if bars is None or getattr(bars, "empty", True):
        return None
    return Decimal(str(bars["c"].iloc[-1]))


def _get_nyse_business_days(start: date, end: date) -> list[date]:
    """NYSE business days in [start, end] inclusive.

    Uses ``pandas_market_calendars`` if installed; falls back to a weekday filter
    minus a curated NYSE holiday list when it isn't (the package needs a network
    install that Norton may block — see Candid Acknowledgment in the §2b doc)."""
    try:
        import pandas_market_calendars as mcal

        nyse = mcal.get_calendar("NYSE")
        schedule = nyse.schedule(start_date=start, end_date=end)
        return [d.date() for d in schedule.index.to_pydatetime()]
    except ImportError:
        return _fallback_nyse_business_days(start, end)


# Curated NYSE full-day closures (weekday filter handles weekends). Extend
# annually — a missing holiday just adds a spurious flat mark, not a wrong pnl.
_NYSE_HOLIDAYS: frozenset[date] = frozenset(
    {
        date(2025, 1, 1), date(2025, 1, 20), date(2025, 2, 17),
        date(2025, 4, 18), date(2025, 5, 26), date(2025, 6, 19),
        date(2025, 7, 4), date(2025, 9, 1), date(2025, 11, 27),
        date(2025, 12, 25),
        date(2026, 1, 1), date(2026, 1, 19), date(2026, 2, 16),
        date(2026, 4, 3), date(2026, 5, 25), date(2026, 6, 19),
        date(2026, 7, 3), date(2026, 9, 7), date(2026, 11, 26),
        date(2026, 12, 25),
        date(2027, 1, 1), date(2027, 1, 18), date(2027, 2, 15),
        date(2027, 3, 26), date(2027, 5, 31), date(2027, 6, 18),
        date(2027, 7, 5), date(2027, 9, 6), date(2027, 11, 25),
        date(2027, 12, 24),
    }
)


def _fallback_nyse_business_days(start: date, end: date) -> list[date]:
    """Weekdays in [start, end] minus curated NYSE holidays."""
    days: list[date] = []
    d = start
    while d <= end:
        if d.weekday() < 5 and d not in _NYSE_HOLIDAYS:
            days.append(d)
        d += timedelta(days=1)
    return days


async def reconstruct_equity_curve(
    session: AsyncSession,
    strategy_id: int,
    start: datetime,
    end: datetime,
    capital_base: Decimal = DEFAULT_CAPITAL_BASE,
    *,
    bar_cache: Any = None,
) -> list[tuple[datetime, Decimal]]:
    """Return ``[(eod_timestamp, equity)]`` for each NYSE business day in
    ``[start.date(), end.date()]``.

    Equity = capital_base + cumulative realized P&L + unrealized P&L from open
    positions marked at the end-of-day close. Days where any open position's
    close is unavailable are skipped (per the Candid Acknowledgment). ``bar_cache``
    is ``app.state.bar_cache``; None → every day with an open position is skipped
    (degenerate-but-safe), so empty-position windows still produce a flat curve.
    """
    business_days = _get_nyse_business_days(start.date(), end.date())
    if not business_days:
        return []

    # Mark each business day at its EOD, so the fill horizon is the LAST day's
    # EOD — not the (possibly mid-day) `end` instant. Otherwise a fill later on
    # the end day would be dropped though that day is still marked at close.
    end_inclusive = datetime.combine(end.date(), datetime.max.time(), tzinfo=UTC)

    # One-shot fetch: all fills for this strategy in the window, ordered by time.
    fills = list((await session.execute(
        select(Fill, Order, Symbol)
        .join(Order, Fill.order_id == Order.id)
        .join(Symbol, Order.symbol_id == Symbol.id)
        .where(Order.source_type == OrderSourceType.STRATEGY)
        .where(Order.source_id == str(strategy_id))
        .where(Fill.filled_at <= end_inclusive)
        .order_by(Fill.filled_at.asc())
    )).all())

    # Per-symbol position state, walked cumulatively.
    # symbol_id → {"qty": Decimal (signed), "avg_cost": Decimal}
    positions: dict[int, dict[str, Decimal]] = {}
    # symbol_id → ticker (BarCache is keyed by ticker, not symbol_id).
    tickers: dict[int, str] = {}
    realized_pnl = ZERO

    # Close-price cache for this computation (avoid re-fetching the same day).
    close_cache: dict[tuple[int, date], Decimal | None] = {}

    equity_curve: list[tuple[datetime, Decimal]] = []
    fill_idx = 0
    n_fills = len(fills)

    for day in business_days:
        eod = datetime.combine(day, datetime.max.time(), tzinfo=UTC)

        # Walk fills up to eod. SQLite returns DateTime(tz=True) columns naive —
        # coerce to aware-UTC before comparing to the aware `eod`.
        while fill_idx < n_fills:
            fill, order, symbol = fills[fill_idx]
            if _aware(fill.filled_at) > eod:
                break
            qty_signed = fill.qty if order.side == OrderSide.BUY else -fill.qty

            pos = positions.setdefault(symbol.id, {"qty": ZERO, "avg_cost": ZERO})
            tickers[symbol.id] = symbol.ticker
            existing_qty = pos["qty"]

            scaling_in = (
                (existing_qty >= 0 and qty_signed > 0)
                or (existing_qty <= 0 and qty_signed < 0)
                or existing_qty == 0
            )

            if scaling_in:
                # New avg cost = weighted average of existing + new at fill price.
                total_cost = existing_qty * pos["avg_cost"] + qty_signed * fill.price
                new_qty = existing_qty + qty_signed
                pos["qty"] = new_qty
                pos["avg_cost"] = total_cost / new_qty if new_qty != ZERO else ZERO
            else:
                # Reducing position; realize pnl for the closing portion.
                close_qty = min(abs(qty_signed), abs(existing_qty))
                direction_sign = Decimal("1") if existing_qty > 0 else Decimal("-1")
                pnl_per_share = (fill.price - pos["avg_cost"]) * direction_sign
                realized_pnl += pnl_per_share * close_qty - fill.commission
                pos["qty"] = existing_qty + qty_signed
                # Avg cost unchanged when reducing; reset to 0 if flat.
                if pos["qty"] == ZERO:
                    pos["avg_cost"] = ZERO

            fill_idx += 1

        # Mark open positions at eod close.
        unrealized_pnl = ZERO
        missing_close = False
        for symbol_id, pos in positions.items():
            if pos["qty"] == ZERO:
                continue
            cache_key = (symbol_id, day)
            if cache_key not in close_cache:
                close_cache[cache_key] = await _close_on_day(
                    bar_cache, tickers[symbol_id], day,
                )
            close_price = close_cache[cache_key]
            if close_price is None:
                missing_close = True
                break
            unrealized_pnl += pos["qty"] * (close_price - pos["avg_cost"])

        if missing_close:
            logger.debug(
                "equity_curve_skipping_day_missing_close",
                strategy_id=strategy_id, day=day.isoformat(),
            )
            continue

        equity = capital_base + realized_pnl + unrealized_pnl
        equity_curve.append((eod, equity))

    return equity_curve
