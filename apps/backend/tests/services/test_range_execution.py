"""capture_window — materializes fills + daily high/low into range_execution_records, frozen.

Uses a stub bar cache and dates relative to *now* (yesterday = a completed day; today = incomplete) so
the test is independent of the wall clock.
"""

from __future__ import annotations

from datetime import UTC, datetime, time, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

import pandas as pd
from sqlalchemy import select

from app.db.enums import (
    OrderSide,
    OrderSourceType,
    OrderStatus,
    OrderType,
    StrategyStatus,
    StrategyType,
    TimeInForce,
)
from app.db.models.account import Account, AccountMode
from app.db.models.fill import Fill
from app.db.models.order import Order
from app.db.models.range_execution_record import RangeExecutionRecord
from app.db.models.strategy import Strategy
from app.db.models.symbol import Symbol
from app.db.models.user import User
from app.services.range_execution import capture_window

_ET = ZoneInfo("America/New_York")


class _StubBarCache:
    """Returns a one-row 1Day frame for each (symbol, date) it knows; empty otherwise."""

    def __init__(self, hl: dict) -> None:
        self._hl = hl  # {(symbol, date): (low, high)}

    async def get_bars(self, symbol, timeframe, start, end):  # noqa: ANN001, ARG002
        rows = [
            {"t": pd.Timestamp(d.isoformat(), tz="UTC"), "o": lo, "h": hi, "l": lo, "c": hi, "v": 1.0}
            for (sym, d), (lo, hi) in self._hl.items()
            if sym == symbol
        ]
        return pd.DataFrame(rows, columns=["t", "o", "h", "l", "c", "v"])


def _now() -> datetime:
    return datetime.now(UTC)


async def _seed(factory, day) -> None:
    async with factory() as s:
        s.add(User(id=2, email="range@test"))
        s.add(Account(id=2, user_id=2, broker="alpaca", mode=AccountMode.paper, label="Range"))
        s.add(Symbol(id=1, ticker="MU", exchange="NASDAQ", asset_class="us_equity",
                     name="Micron", active=True))
        s.add(Strategy(id=1, user_id=2, name="Range Trader Top-5", version="0.1.0",
                       type=StrategyType.PYTHON, status=StrategyStatus.PAPER, code_path="x.py",
                       params_json={}, symbols_json=["MU"], schedule="*/5 * * * *",
                       created_at=_now(), updated_at=_now()))
        created = datetime.combine(day, time(14, 15), tzinfo=UTC)  # 10:15 ET, RTH
        s.add(Order(id=100, user_id=2, account_id=2, symbol_id=1, side=OrderSide.BUY,
                    qty=Decimal("4"), type=OrderType.MARKET, tif=TimeInForce.DAY,
                    status=OrderStatus.FILLED, source_type=OrderSourceType.STRATEGY, source_id="1",
                    created_at=created, submitted_at=created, updated_at=created))
        s.add(Fill(order_id=100, qty=Decimal("4"), price=Decimal("910.81"), filled_at=created))
        await s.commit()


async def test_capture_freezes_and_is_idempotent(session_factory) -> None:
    yesterday = datetime.now(_ET).date() - timedelta(days=1)
    await _seed(session_factory, yesterday)
    bc = _StubBarCache({("MU", yesterday): (Decimal("891.75"), Decimal("941.32"))})

    async with session_factory() as s:
        n = await capture_window(s, bc, yesterday, yesterday)
    assert n == 1

    async with session_factory() as s:
        r = (await s.execute(select(RangeExecutionRecord))).scalars().one()
        assert r.symbol == "MU"
        assert r.et_date == yesterday
        assert r.avg_buy_price == Decimal("910.81")  # qty-weighted avg fill
        assert r.avg_sell_price is None
        assert r.daily_low == Decimal("891.75")
        assert r.daily_high == Decimal("941.32")

    # Freeze: a second capture over the same window inserts nothing.
    async with session_factory() as s:
        n2 = await capture_window(s, bc, yesterday, yesterday)
    assert n2 == 0


async def test_capture_skips_incomplete_today(session_factory) -> None:
    today = datetime.now(_ET).date()
    await _seed(session_factory, today)
    bc = _StubBarCache({("MU", today): (Decimal("1"), Decimal("2"))})
    async with session_factory() as s:
        n = await capture_window(s, bc, today, today)
    assert n == 0  # today has not closed → not frozen
