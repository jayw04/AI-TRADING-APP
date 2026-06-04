"""P6b §2b-variant — equity-curve reconstruction service.

Seeds Order + Fill + Symbol rows (the same fill-level source as §1a-drift). Open
positions are marked at the EOD close via an injected fake BarCache (the real
one hits Norton-blocked data.alpaca.markets). Closed-only scenarios need no
BarCache.
"""
from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import pandas as pd

from app.db.enums import OrderSide, OrderSourceType, OrderStatus, OrderType
from app.db.models.fill import Fill
from app.db.models.order import Order
from app.db.models.symbol import Symbol
from app.services import equity_curve as ec

# 2026-06-15 is a Monday; 06-19 (Fri) is Juneteenth (a curated NYSE holiday).
MON = datetime(2026, 6, 15, 10, 0, tzinfo=UTC)
_oid = 0


def _leg(session, *, strategy_id, symbol_id, side, qty, price, filled_at, commission=0.0):
    global _oid
    _oid += 1
    session.add(Order(
        id=_oid, user_id=1, account_id=1, symbol_id=symbol_id,
        side=side, qty=Decimal(str(qty)), type=OrderType.MARKET,
        status=OrderStatus.FILLED, source_type=OrderSourceType.STRATEGY,
        source_id=str(strategy_id), created_at=filled_at, updated_at=filled_at,
    ))
    session.add(Fill(
        order_id=_oid, qty=Decimal(str(qty)), price=Decimal(str(price)),
        commission=Decimal(str(commission)), filled_at=filled_at,
    ))


class _FakeBarCache:
    """Async get_bars stub. ``closes`` maps date→close (None/absent → empty)."""

    def __init__(self, closes: dict[date, float] | float | None):
        self._closes = closes
        self.calls: list[tuple[str, date]] = []

    async def get_bars(self, ticker, timeframe, start, end):
        self.calls.append((ticker, start.date()))
        price = (
            self._closes.get(start.date())
            if isinstance(self._closes, dict)
            else self._closes
        )
        if price is None:
            return pd.DataFrame(columns=["t", "o", "h", "l", "c", "v"])
        return pd.DataFrame([{"t": start, "c": price}])


# ---- NYSE business-day calendar ----


def test_business_days_excludes_weekends():
    # Sat 06-13 .. Mon 06-15 → only Monday.
    days = ec._get_nyse_business_days(date(2026, 6, 13), date(2026, 6, 15))
    assert days == [date(2026, 6, 15)]
    assert all(d.weekday() < 5 for d in days)


def test_fallback_excludes_holiday():
    # Juneteenth (Fri 06-19) is excluded; Mon-Thu remain.
    days = ec._fallback_nyse_business_days(date(2026, 6, 15), date(2026, 6, 19))
    assert date(2026, 6, 19) not in days
    assert days == [date(2026, 6, 15), date(2026, 6, 16), date(2026, 6, 17), date(2026, 6, 18)]


def test_get_business_days_uses_fallback_when_pmc_unavailable():
    # pandas_market_calendars is not a dependency → ImportError → fallback path.
    days = ec._get_nyse_business_days(date(2026, 6, 15), date(2026, 6, 18))
    assert days == ec._fallback_nyse_business_days(date(2026, 6, 15), date(2026, 6, 18))


# ---- equity reconstruction ----


async def test_empty_fills_returns_capital_base_each_day(session_factory):
    async with session_factory() as s:
        s.add(Symbol(id=1, ticker="AAPL"))
        await s.commit()
    async with session_factory() as s:
        curve = await ec.reconstruct_equity_curve(
            s, 1, MON, MON + timedelta(days=3), Decimal("100000"),
        )
    assert len(curve) == 4  # Mon-Thu
    assert all(eq == Decimal("100000") for _, eq in curve)


async def test_realized_pnl_only_no_open_positions(session_factory):
    # Buy 10 @ 100, sell 10 @ 110 same day → +100 realized, flat after.
    async with session_factory() as s:
        s.add(Symbol(id=1, ticker="AAPL"))
        _leg(s, strategy_id=1, symbol_id=1, side=OrderSide.BUY, qty=10, price=100, filled_at=MON)
        _leg(s, strategy_id=1, symbol_id=1, side=OrderSide.SELL, qty=10, price=110,
             filled_at=MON + timedelta(minutes=5))
        await s.commit()
    async with session_factory() as s:
        curve = await ec.reconstruct_equity_curve(
            s, 1, MON, MON + timedelta(days=2), Decimal("100000"),
        )
    # No open position → no close needed; every day shows the realized +100.
    assert all(eq == Decimal("100100") for _, eq in curve)


async def test_unrealized_pnl_with_open_position(session_factory):
    async with session_factory() as s:
        s.add(Symbol(id=1, ticker="AAPL"))
        _leg(s, strategy_id=1, symbol_id=1, side=OrderSide.BUY, qty=10, price=100, filled_at=MON)
        await s.commit()
    bars = _FakeBarCache(105.0)  # close 105 every day → +50 unrealized on 10 sh
    async with session_factory() as s:
        curve = await ec.reconstruct_equity_curve(
            s, 1, MON, MON, Decimal("100000"), bar_cache=bars,
        )
    assert len(curve) == 1
    assert curve[0][1] == Decimal("100050")


async def test_short_position_unrealized_pnl(session_factory):
    # Short 10 @ 100; close drops to 90 → +100 unrealized for a short.
    async with session_factory() as s:
        s.add(Symbol(id=1, ticker="AAPL"))
        _leg(s, strategy_id=1, symbol_id=1, side=OrderSide.SELL, qty=10, price=100, filled_at=MON)
        await s.commit()
    bars = _FakeBarCache(90.0)
    async with session_factory() as s:
        curve = await ec.reconstruct_equity_curve(
            s, 1, MON, MON, Decimal("100000"), bar_cache=bars,
        )
    assert curve[0][1] == Decimal("100100")


async def test_skips_day_when_close_missing(session_factory):
    async with session_factory() as s:
        s.add(Symbol(id=1, ticker="AAPL"))
        _leg(s, strategy_id=1, symbol_id=1, side=OrderSide.BUY, qty=10, price=100, filled_at=MON)
        await s.commit()
    bars = _FakeBarCache(None)  # no close available → day skipped
    async with session_factory() as s:
        curve = await ec.reconstruct_equity_curve(
            s, 1, MON, MON, Decimal("100000"), bar_cache=bars,
        )
    assert curve == []


async def test_avg_cost_basis_correct_after_scale_in(session_factory):
    # Buy 10 @ 100, buy 10 @ 120 → avg cost 110 on 20 sh. Close 115 → +100.
    async with session_factory() as s:
        s.add(Symbol(id=1, ticker="AAPL"))
        _leg(s, strategy_id=1, symbol_id=1, side=OrderSide.BUY, qty=10, price=100, filled_at=MON)
        _leg(s, strategy_id=1, symbol_id=1, side=OrderSide.BUY, qty=10, price=120,
             filled_at=MON + timedelta(minutes=1))
        await s.commit()
    bars = _FakeBarCache(115.0)
    async with session_factory() as s:
        curve = await ec.reconstruct_equity_curve(
            s, 1, MON, MON, Decimal("100000"), bar_cache=bars,
        )
    assert curve[0][1] == Decimal("100100")  # 20 * (115 - 110)


async def test_long_then_flat_after_full_exit(session_factory):
    # Buy 10 @ 100 Mon, sell 10 @ 130 Tue → realized +300; flat Wed (no close).
    async with session_factory() as s:
        s.add(Symbol(id=1, ticker="AAPL"))
        _leg(s, strategy_id=1, symbol_id=1, side=OrderSide.BUY, qty=10, price=100, filled_at=MON)
        _leg(s, strategy_id=1, symbol_id=1, side=OrderSide.SELL, qty=10, price=130,
             filled_at=MON + timedelta(days=1))
        await s.commit()
    bars = _FakeBarCache({date(2026, 6, 15): 100.0})  # Mon close flat at cost
    async with session_factory() as s:
        curve = await ec.reconstruct_equity_curve(
            s, 1, MON, MON + timedelta(days=2), Decimal("100000"), bar_cache=bars,
        )
    # Mon: open @ cost → +0; Tue+Wed: realized +300, flat.
    by_day = {ts.date(): eq for ts, eq in curve}
    assert by_day[date(2026, 6, 15)] == Decimal("100000")
    assert by_day[date(2026, 6, 16)] == Decimal("100300")
    assert by_day[date(2026, 6, 17)] == Decimal("100300")


async def test_close_price_fetched_once_per_day(session_factory):
    # One open position over 4 business days → exactly 4 get_bars calls (cache
    # prevents any redundant same-day fetch).
    async with session_factory() as s:
        s.add(Symbol(id=1, ticker="AAPL"))
        _leg(s, strategy_id=1, symbol_id=1, side=OrderSide.BUY, qty=10, price=100, filled_at=MON)
        await s.commit()
    bars = _FakeBarCache(105.0)
    async with session_factory() as s:
        await ec.reconstruct_equity_curve(
            s, 1, MON, MON + timedelta(days=3), Decimal("100000"), bar_cache=bars,
        )
    assert len(bars.calls) == 4
    assert all(t == "AAPL" for t, _ in bars.calls)


async def test_capital_base_invariance_for_comparison(session_factory):
    # Two strategies with IDENTICAL closed round-trips and the SAME capital_base
    # produce identical equity curves — the comparison-comparability contract.
    async with session_factory() as s:
        s.add(Symbol(id=1, ticker="AAPL"))
        for sid in (1, 2):
            _leg(s, strategy_id=sid, symbol_id=1, side=OrderSide.BUY, qty=10, price=100, filled_at=MON)
            _leg(s, strategy_id=sid, symbol_id=1, side=OrderSide.SELL, qty=10, price=110,
                 filled_at=MON + timedelta(minutes=5))
        await s.commit()
    async with session_factory() as s:
        c1 = await ec.reconstruct_equity_curve(s, 1, MON, MON + timedelta(days=2), Decimal("100000"))
        c2 = await ec.reconstruct_equity_curve(s, 2, MON, MON + timedelta(days=2), Decimal("100000"))
    assert [eq for _, eq in c1] == [eq for _, eq in c2]
