"""BuyingPowerChecker tests (P5 §5).

The OrderRequest carries `symbol_ticker` (not `symbol`); adapter.get_account()
is sync and returns dict[str, Any] (Session 2 v1.0).
"""
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

from app.db.enums import OrderSide, OrderType
from app.db.models.account import AccountMode
from app.risk.buying_power import BuyingPowerChecker


def _request(side=OrderSide.BUY, type=OrderType.MARKET, qty="10",
             limit=None, stop=None, symbol="AAPL"):
    req = MagicMock()
    req.side = side
    req.type = type
    req.qty = Decimal(qty)
    req.limit_price = Decimal(limit) if limit else None
    req.stop_price = Decimal(stop) if stop else None
    req.symbol_ticker = symbol
    return req


def _account():
    return MagicMock(id=1, mode=AccountMode.live)


def _registry(buying_power: Decimal):
    reg = MagicMock()
    adapter = MagicMock()
    adapter.get_account = MagicMock(return_value={
        "cash": "1000", "equity": "1000", "buying_power": str(buying_power),
    })
    reg.get.return_value = adapter
    return reg


async def test_sell_orders_exempt():
    checker = BuyingPowerChecker(broker_registry=_registry(Decimal("0")))
    decision = await checker.check(_account(), _request(side=OrderSide.SELL))
    assert decision.sufficient is True


async def test_limit_buy_sufficient():
    checker = BuyingPowerChecker(broker_registry=_registry(Decimal("10000")))
    decision = await checker.check(_account(),
                                   _request(type=OrderType.LIMIT, limit="100", qty="10"))
    assert decision.sufficient is True
    assert decision.required_notional == Decimal("1000")


async def test_limit_buy_insufficient():
    checker = BuyingPowerChecker(broker_registry=_registry(Decimal("500")))
    decision = await checker.check(_account(),
                                   _request(type=OrderType.LIMIT, limit="100", qty="10"))
    assert decision.sufficient is False
    assert "INSUFFICIENT_BUYING_POWER" in decision.rejection_reason


async def test_market_buy_uses_bar_cache_price():
    bar_cache = MagicMock()
    bar_cache.get_latest_bar = AsyncMock(return_value={"c": "100"})
    checker = BuyingPowerChecker(
        broker_registry=_registry(Decimal("10000")), bar_cache=bar_cache,
    )
    decision = await checker.check(_account(), _request(type=OrderType.MARKET, qty="10"))
    assert decision.required_notional == Decimal("1010.00")
    assert decision.sufficient is True


async def test_stop_buy_uses_stop_price_with_buffer():
    checker = BuyingPowerChecker(broker_registry=_registry(Decimal("10000")))
    decision = await checker.check(_account(),
                                   _request(type=OrderType.STOP, stop="100", qty="10"))
    assert decision.required_notional == Decimal("1010.00")


async def test_broker_unreachable_fails_open():
    reg = MagicMock()
    adapter = MagicMock()
    adapter.get_account = MagicMock(side_effect=RuntimeError("broker down"))
    reg.get.return_value = adapter
    checker = BuyingPowerChecker(broker_registry=reg)
    decision = await checker.check(_account(),
                                   _request(type=OrderType.LIMIT, limit="100", qty="10"))
    assert decision.sufficient is True
    assert "Broker unreachable" in (decision.rejection_reason or "")


async def test_no_adapter_fails_open():
    reg = MagicMock()
    reg.get.return_value = None
    checker = BuyingPowerChecker(broker_registry=reg)
    decision = await checker.check(_account(),
                                   _request(type=OrderType.LIMIT, limit="100", qty="10"))
    assert decision.sufficient is True
