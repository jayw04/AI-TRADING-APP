"""P5 §1 — OrderRouter refuses LIVE accounts before the risk engine runs."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest

from app.db.enums import (
    OrderSide,
    OrderSourceType,
    OrderType,
    RiskScopeType,
    TimeInForce,
)
from app.db.models.account import Account, AccountMode
from app.db.models.risk_limits import RiskLimits
from app.db.models.symbol import Symbol
from app.db.models.user import User
from app.orders.router import BrokerModeError, OrderRouter
from app.risk.engine import RiskEngine
from app.risk.types import OrderRequest


class _StubAdapter:
    def __init__(self, is_paper=True):
        self.is_paper = is_paper
        self.submitted = []

    def submit_order(self, **kwargs):
        self.submitted.append(kwargs)
        return {"id": "broker-123", "status": "accepted"}


class _StubBus:
    def __init__(self):
        self.events = []

    async def publish(self, topic, payload):
        self.events.append((topic, payload))


class _SpyEngine:
    """Records whether evaluate() was called; never reached on the LIVE path."""

    def __init__(self):
        self.called = False

    async def evaluate(self, req, *, trading_mode, broker_mode=AccountMode.paper):
        self.called = True
        raise AssertionError("risk engine should not run for a refused LIVE order")


def _now() -> datetime:
    return datetime.now(UTC)


async def _seed(session) -> None:
    session.add(User(id=1, email="t@t.test", display_name="T"))
    await session.flush()
    session.add(
        Account(id=1, user_id=1, broker="alpaca", mode=AccountMode.paper, label="paper")
    )
    session.add(
        Account(
            id=2, user_id=1, broker="alpaca", mode=AccountMode.live, label="live",
            broker_mode_locked_at=_now(),
        )
    )
    session.add(
        Symbol(id=1, ticker="AAPL", name="Apple", asset_class="us_equity", active=True)
    )
    session.add(
        RiskLimits(
            id=1, user_id=1, scope_type=RiskScopeType.GLOBAL,
            max_position_qty=Decimal("1000"),
            max_position_notional=Decimal("1000000"),
            max_gross_exposure=Decimal("5000000"),
            max_daily_loss=Decimal("100000"),
            max_orders_per_minute=1000, allow_short=False,
            created_at=_now(), updated_at=_now(),
        )
    )
    await session.commit()


def _req(account_id: int, confirmation_text: str | None = None) -> OrderRequest:
    # P5 §6: a MANUAL+LIVE order now hits the typed-ticker confirmation gate
    # before the §1 BrokerModeError guard. The live-refusal tests pass a matching
    # confirmation so confirmation passes and the BrokerModeError path is reached.
    return OrderRequest(
        user_id=1,
        account_id=account_id,
        symbol_ticker="AAPL",
        side=OrderSide.BUY,
        qty=Decimal("10"),
        type=OrderType.MARKET,
        tif=TimeInForce.DAY,
        source_type=OrderSourceType.MANUAL,
        confirmation_text=confirmation_text,
    )


@pytest.mark.asyncio
async def test_paper_account_routes_normally(session_factory):
    """Routing to a PAPER account does NOT raise BrokerModeError."""
    async with session_factory() as session:
        await _seed(session)
    engine = RiskEngine(session_factory)
    router = OrderRouter(_StubAdapter(), engine, session_factory, _StubBus())

    order = await router.submit(_req(account_id=1))
    # Paper path completes through the stub broker.
    assert order.id is not None


@pytest.mark.asyncio
async def test_live_account_refused_with_clear_error(session_factory):
    async with session_factory() as session:
        await _seed(session)
    engine = RiskEngine(session_factory)
    router = OrderRouter(_StubAdapter(), engine, session_factory, _StubBus())

    with pytest.raises(BrokerModeError) as exc_info:
        await router.submit(_req(account_id=2, confirmation_text="AAPL"))
    assert "Live trading is not yet enabled" in str(exc_info.value)
    assert "P5 §2" in str(exc_info.value)


@pytest.mark.asyncio
async def test_live_refusal_happens_before_risk_check(session_factory):
    """The LIVE refusal must short-circuit before the risk engine runs."""
    async with session_factory() as session:
        await _seed(session)
    spy = _SpyEngine()
    router = OrderRouter(_StubAdapter(), spy, session_factory, _StubBus())

    with pytest.raises(BrokerModeError):
        await router.submit(_req(account_id=2, confirmation_text="AAPL"))
    assert spy.called is False
