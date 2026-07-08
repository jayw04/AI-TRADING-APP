"""capture_window — materializes the daily SET range levels + high/low into range_execution_records.

The buy/sell columns hold the strategy's SET daily fade levels (from its ``range_levels`` INFO signal),
not fills. Uses a stub bar cache and dates relative to *now* (yesterday = a completed day; today =
incomplete) so the test is independent of the wall clock.
"""

from __future__ import annotations

from datetime import UTC, datetime, time, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

import pandas as pd
from sqlalchemy import select

from app.db.enums import StrategyStatus, StrategyType
from app.db.models.range_execution_record import RangeExecutionRecord
from app.db.models.signal import Signal, SignalType
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
        s.add(Symbol(id=1, ticker="MU", exchange="NASDAQ", asset_class="us_equity",
                     name="Micron", active=True))
        s.add(Strategy(id=1, user_id=2, name="Range Trader Top-5", version="0.1.0",
                       type=StrategyType.PYTHON, status=StrategyStatus.PAPER, code_path="x.py",
                       params_json={}, symbols_json=["MU"], schedule="*/5 * * * *",
                       created_at=_now(), updated_at=_now()))
        # The strategy logs its SET fade levels for the day as a range_levels INFO signal (10:05 ET).
        received = datetime.combine(day, time(14, 5), tzinfo=UTC)
        s.add(Signal(user_id=2, strategy_id=1, symbol_id=1, type=SignalType.INFO,
                     payload_json={"kind": "range_levels", "buy": 909.89, "sell": 935.38,
                                   "stop": 905.34, "at_price": 918.42},
                     received_at=received))
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
        assert r.avg_buy_price == Decimal("909.89")   # the SET daily buy level (range_levels)
        assert r.avg_sell_price == Decimal("935.38")  # the SET daily sell level
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
