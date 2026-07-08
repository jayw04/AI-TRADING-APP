"""RangeExecutionRecord model — round-trip, nullable fills, unique (symbol, et_date), window query."""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.db.models.range_execution_record import RangeExecutionRecord


def _now() -> datetime:
    return datetime.now(UTC)


def _rec(**kw) -> RangeExecutionRecord:
    base = dict(
        et_date=date(2026, 7, 7),
        symbol="MU",
        avg_buy_price=None,
        avg_sell_price=None,
        daily_low=Decimal("891.75"),
        daily_high=Decimal("941.32"),
        captured_at=_now(),
    )
    base.update(kw)
    return RangeExecutionRecord(**base)


async def test_round_trip_and_nullable_fills(session_factory) -> None:
    async with session_factory() as s:
        s.add(_rec(avg_buy_price=Decimal("910.81")))  # bought, never sold
        await s.commit()
    async with session_factory() as s:
        r = (
            await s.execute(select(RangeExecutionRecord).where(RangeExecutionRecord.symbol == "MU"))
        ).scalars().one()
        assert r.et_date == date(2026, 7, 7)
        assert r.avg_buy_price == Decimal("910.81")
        assert r.avg_sell_price is None  # nullable — no sell that day
        assert r.daily_low == Decimal("891.75")
        assert r.daily_high == Decimal("941.32")


async def test_unique_symbol_et_date(session_factory) -> None:
    async with session_factory() as s:
        s.add(_rec())
        await s.commit()
    with pytest.raises(IntegrityError):
        async with session_factory() as s:
            s.add(_rec())  # same (MU, 2026-07-07)
            await s.commit()


async def test_window_query(session_factory) -> None:
    async with session_factory() as s:
        for d in (date(2026, 7, 6), date(2026, 7, 7), date(2026, 7, 8)):
            s.add(_rec(et_date=d))
        await s.commit()
    async with session_factory() as s:
        rows = (
            await s.execute(
                select(RangeExecutionRecord)
                .where(
                    RangeExecutionRecord.et_date >= date(2026, 7, 7),
                    RangeExecutionRecord.et_date <= date(2026, 7, 8),
                )
                .order_by(RangeExecutionRecord.et_date)
            )
        ).scalars().all()
        assert [r.et_date for r in rows] == [date(2026, 7, 7), date(2026, 7, 8)]
