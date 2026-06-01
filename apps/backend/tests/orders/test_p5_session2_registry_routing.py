"""P5 §2 — OrderRouter resolves a per-account adapter via BrokerRegistry.

Builds on the P5 §1 live-refusal seed. The load-bearing assertions:
  - a paper order routes through the registry-resolved adapter (not the
    default fallback);
  - with no registry / no registered adapter, behavior falls back to the
    default adapter (byte-identical to P5 §1);
  - a LIVE account is refused by the §1 BrokerModeError BEFORE the registry is
    ever consulted.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest

from app.brokers.registry import BrokerRegistry
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
    """Minimal BrokerAdapter for the submit path — records calls."""

    def __init__(self, name: str, is_paper: bool = True) -> None:
        self.name = name
        self.is_paper = is_paper
        self.is_connected = True
        self.submitted: list[dict] = []

    def submit_order(self, **kwargs):
        self.submitted.append(kwargs)
        return {"id": f"{self.name}-broker-1", "status": "accepted"}

    def disconnect(self) -> None:  # pragma: no cover - not exercised here
        pass


class _StubBus:
    def __init__(self) -> None:
        self.events: list[tuple] = []

    async def publish(self, topic, payload):
        self.events.append((topic, payload))


class _ExplodingRegistry:
    """A registry whose .get() must never be called (live path asserts this)."""

    def __init__(self) -> None:
        self.get_calls = 0

    def get(self, account_id: int):
        self.get_calls += 1
        raise AssertionError("registry.get must not run for a LIVE account")


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
    # P5 §6: MANUAL+LIVE now passes the typed-ticker confirmation gate before
    # the §1 BrokerModeError guard; the live test supplies a matching ticker.
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
async def test_paper_order_routes_to_registered_adapter(session_factory):
    async with session_factory() as session:
        await _seed(session)
    fallback = _StubAdapter("fallback")
    registered = _StubAdapter("registered")
    registry = BrokerRegistry(session_factory)
    registry.register(1, registered)

    engine = RiskEngine(session_factory)
    router = OrderRouter(fallback, engine, session_factory, _StubBus(),
                         broker_registry=registry)

    order = await router.submit(_req(account_id=1))

    assert order.broker_order_id == "registered-broker-1"
    assert len(registered.submitted) == 1
    assert registered.submitted[0]["symbol"] == "AAPL"
    assert len(fallback.submitted) == 0  # the default adapter was NOT used


@pytest.mark.asyncio
async def test_falls_back_to_default_adapter_when_unregistered(session_factory):
    async with session_factory() as session:
        await _seed(session)
    fallback = _StubAdapter("fallback")
    registry = BrokerRegistry(session_factory)  # empty — account 1 not registered

    engine = RiskEngine(session_factory)
    router = OrderRouter(fallback, engine, session_factory, _StubBus(),
                         broker_registry=registry)

    order = await router.submit(_req(account_id=1))

    assert order.broker_order_id == "fallback-broker-1"
    assert len(fallback.submitted) == 1


@pytest.mark.asyncio
async def test_live_account_refused_before_registry_lookup(session_factory):
    async with session_factory() as session:
        await _seed(session)
    fallback = _StubAdapter("fallback")
    exploding = _ExplodingRegistry()

    engine = RiskEngine(session_factory)
    router = OrderRouter(fallback, engine, session_factory, _StubBus(),
                         broker_registry=exploding)

    with pytest.raises(BrokerModeError):
        await router.submit(_req(account_id=2, confirmation_text="AAPL"))
    assert exploding.get_calls == 0       # registry never consulted
    assert len(fallback.submitted) == 0   # no broker call
