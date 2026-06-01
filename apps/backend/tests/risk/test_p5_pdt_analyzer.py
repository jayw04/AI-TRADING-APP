"""PdtAnalyzer tests (P5 §5).

Adapted to live schema: Order uses symbol_id (not a symbol string), so the
fixture seeds Symbol rows; Fill has no signed_direction.
"""
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from unittest.mock import MagicMock

import pytest

from app.db.enums import (
    OrderSide,
    OrderSourceType,
    OrderStatus,
    OrderType,
    TimeInForce,
)
from app.db.models.account import Account, AccountMode
from app.db.models.fill import Fill
from app.db.models.order import Order
from app.db.models.symbol import Symbol
from app.db.models.user import User
from app.risk.pdt_analyzer import PdtAnalyzer

_TICKERS = {"AAPL": 1, "MSFT": 2, "GOOG": 3}


def _now() -> datetime:
    return datetime.now(UTC)


@pytest.fixture
async def seeded(session_factory):
    async with session_factory() as session:
        session.add(User(id=1, email="t@local"))
        session.add(Account(id=1, user_id=1, broker="alpaca",
                            mode=AccountMode.paper, label="Paper", created_at=_now()))
        for ticker, sid in _TICKERS.items():
            session.add(Symbol(id=sid, ticker=ticker, exchange="NASDAQ",
                               asset_class="us_equity", name=ticker, active=True))
        await session.commit()
    return session_factory


@pytest.fixture
def broker_registry_factory():
    def _make(equity: Decimal):
        reg = MagicMock()
        adapter = MagicMock()
        adapter.get_account = MagicMock(return_value={
            "cash": "10000", "equity": str(equity), "buying_power": str(equity),
        })
        reg.get.return_value = adapter
        return reg
    return _make


async def _add_day_trade(session, symbol: str, hours_ago: int):
    """Seed a buy + sell of the same symbol within one day (a day trade)."""
    sid = _TICKERS[symbol]
    base = _now() - timedelta(hours=hours_ago)
    buy = Order(
        account_id=1, user_id=1, symbol_id=sid, side=OrderSide.BUY,
        type=OrderType.MARKET, qty=Decimal("10"), tif=TimeInForce.DAY,
        status=OrderStatus.FILLED, source_type=OrderSourceType.MANUAL,
        created_at=base, updated_at=base,
    )
    sell = Order(
        account_id=1, user_id=1, symbol_id=sid, side=OrderSide.SELL,
        type=OrderType.MARKET, qty=Decimal("10"), tif=TimeInForce.DAY,
        status=OrderStatus.FILLED, source_type=OrderSourceType.MANUAL,
        created_at=base + timedelta(hours=2), updated_at=base + timedelta(hours=2),
    )
    session.add_all([buy, sell])
    await session.flush()
    session.add_all([
        Fill(order_id=buy.id, qty=Decimal("10"), price=Decimal("100"), filled_at=base),
        Fill(order_id=sell.id, qty=Decimal("10"), price=Decimal("101"),
             filled_at=base + timedelta(hours=2)),
    ])


async def test_no_day_trades_not_at_risk(seeded, broker_registry_factory):
    reg = broker_registry_factory(Decimal("10000"))
    async with seeded() as session:
        status = await PdtAnalyzer(session=session, broker_registry=reg).compute(1)
    assert status.day_trade_count == 0
    assert status.is_at_risk is False


async def test_two_day_trades_below_threshold(seeded, broker_registry_factory):
    reg = broker_registry_factory(Decimal("10000"))
    async with seeded() as session:
        await _add_day_trade(session, "AAPL", 24)
        await _add_day_trade(session, "MSFT", 48)
        await session.commit()
    async with seeded() as session:
        status = await PdtAnalyzer(session=session, broker_registry=reg).compute(1)
    assert status.day_trade_count == 2
    assert status.is_at_risk is False


async def test_three_day_trades_low_equity_at_risk(seeded, broker_registry_factory):
    reg = broker_registry_factory(Decimal("10000"))
    async with seeded() as session:
        await _add_day_trade(session, "AAPL", 24)
        await _add_day_trade(session, "MSFT", 48)
        await _add_day_trade(session, "GOOG", 72)
        await session.commit()
    async with seeded() as session:
        status = await PdtAnalyzer(session=session, broker_registry=reg).compute(1)
    assert status.day_trade_count == 3
    assert status.is_at_risk is True


async def test_three_day_trades_high_equity_not_at_risk(seeded, broker_registry_factory):
    reg = broker_registry_factory(Decimal("50000"))
    async with seeded() as session:
        await _add_day_trade(session, "AAPL", 24)
        await _add_day_trade(session, "MSFT", 48)
        await _add_day_trade(session, "GOOG", 72)
        await session.commit()
    async with seeded() as session:
        status = await PdtAnalyzer(session=session, broker_registry=reg).compute(1)
    assert status.day_trade_count == 3
    assert status.is_at_risk is False


async def test_buy_only_not_a_day_trade(seeded, broker_registry_factory):
    reg = broker_registry_factory(Decimal("10000"))
    async with seeded() as session:
        buy = Order(
            account_id=1, user_id=1, symbol_id=1, side=OrderSide.BUY,
            type=OrderType.MARKET, qty=Decimal("10"), tif=TimeInForce.DAY,
            status=OrderStatus.FILLED, source_type=OrderSourceType.MANUAL,
            created_at=_now(), updated_at=_now(),
        )
        session.add(buy)
        await session.flush()
        session.add(Fill(order_id=buy.id, qty=Decimal("10"),
                         price=Decimal("100"), filled_at=_now()))
        await session.commit()
    async with seeded() as session:
        status = await PdtAnalyzer(session=session, broker_registry=reg).compute(1)
    assert status.day_trade_count == 0


async def test_equity_none_when_no_registry(seeded):
    async with seeded() as session:
        await _add_day_trade(session, "AAPL", 24)
        await _add_day_trade(session, "MSFT", 48)
        await _add_day_trade(session, "GOOG", 72)
        await session.commit()
    async with seeded() as session:
        status = await PdtAnalyzer(session=session, broker_registry=None).compute(1)
    # equity unknown → at risk (conservative) once over the day-trade threshold.
    assert status.account_equity is None
    assert status.is_at_risk is True
