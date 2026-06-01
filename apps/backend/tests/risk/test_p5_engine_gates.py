"""RiskEngine integration of the P5 §5 gates (per-day cap, circuit breaker,
buying power) — exercises the new branches inside evaluate()."""
from datetime import UTC, datetime
from decimal import Decimal
from unittest.mock import MagicMock

import pytest

from app.db.enums import (
    OrderSide,
    OrderSourceType,
    OrderStatus,
    OrderType,
    RiskScopeType,
    TimeInForce,
)
from app.db.models.account import Account, AccountMode
from app.db.models.order import Order
from app.db.models.position import Position
from app.db.models.risk_limits import RiskLimits
from app.db.models.symbol import Symbol
from app.db.models.user import User
from app.risk.engine import RiskEngine
from app.risk.reason_codes import ReasonCode
from app.risk.types import OrderRequest


def _now() -> datetime:
    return datetime.now(UTC)


@pytest.fixture
async def seeded(session_factory):
    async with session_factory() as session:
        session.add(User(id=1, email="jay@test"))
        session.add(Account(id=1, user_id=1, broker="alpaca",
                            mode=AccountMode.paper, label="Paper", created_at=_now()))
        session.add(Account(id=2, user_id=1, broker="alpaca",
                            mode=AccountMode.live, label="Live", created_at=_now()))
        session.add(Symbol(id=1, ticker="AAPL", exchange="NASDAQ",
                           asset_class="us_equity", name="Apple", active=True))
        # Paper + live GLOBAL limits (generous, so only the gate under test fires).
        common = dict(
            scope_type=RiskScopeType.GLOBAL, max_position_qty=Decimal("100"),
            max_position_notional=Decimal("25000"), max_gross_exposure=Decimal("100000"),
            max_daily_loss=Decimal("2000"), max_orders_per_minute=10,
            allow_short=False, created_at=_now(), updated_at=_now(),
        )
        session.add(RiskLimits(user_id=1, broker_mode=AccountMode.paper, **common))
        session.add(RiskLimits(user_id=1, broker_mode=AccountMode.live, **common))
        await session.commit()
    return session_factory


def _req(**overrides) -> OrderRequest:
    base = dict(
        user_id=1, account_id=1, symbol_ticker="AAPL", side=OrderSide.BUY,
        qty=Decimal("10"), type=OrderType.MARKET, tif=TimeInForce.DAY,
        source_type=OrderSourceType.MANUAL,
    )
    base.update(overrides)
    return OrderRequest(**base)


async def _set_paper_limit(sf, **vals):
    from sqlalchemy import select
    async with sf() as s:
        rl = (await s.execute(
            select(RiskLimits).where(RiskLimits.broker_mode == AccountMode.paper)
        )).scalars().first()
        for k, v in vals.items():
            setattr(rl, k, v)
        await s.commit()


# ---- per-day order cap ----

async def test_per_day_cap_passes_when_under(seeded):
    await _set_paper_limit(seeded, max_orders_per_day=5)
    eng = RiskEngine(seeded)
    out = await eng.evaluate(_req(), trading_mode="paper")
    assert out.passed


async def test_per_day_cap_rejects_when_reached(seeded):
    await _set_paper_limit(seeded, max_orders_per_day=1)
    async with seeded() as s:
        s.add(Order(
            user_id=1, account_id=1, symbol_id=1, side=OrderSide.BUY,
            type=OrderType.MARKET, qty=Decimal("1"), tif=TimeInForce.DAY,
            status=OrderStatus.FILLED, source_type=OrderSourceType.MANUAL,
            created_at=_now(), updated_at=_now(),
        ))
        await s.commit()
    eng = RiskEngine(seeded)
    out = await eng.evaluate(_req(), trading_mode="paper")
    assert not out.passed
    assert ReasonCode.MAX_ORDERS_PER_DAY in out.reason_codes


# ---- circuit breaker ----

async def test_circuit_breaker_already_tripped_rejects(seeded):
    async with seeded() as s:
        acc = await s.get(Account, 1)
        acc.circuit_breaker_tripped_at = _now()
        await s.commit()
    eng = RiskEngine(seeded)
    out = await eng.evaluate(_req(), trading_mode="paper")
    assert not out.passed
    assert ReasonCode.CIRCUIT_BREAKER in out.reason_codes


async def test_circuit_breaker_trips_on_loss_during_evaluate(seeded):
    async with seeded() as s:
        s.add(Position(user_id=1, account_id=1, symbol_id=1,
                       unrealized_pl=Decimal("-3000"), updated_at=_now()))
        await s.commit()
    eng = RiskEngine(seeded)
    out = await eng.evaluate(_req(), trading_mode="paper")
    assert not out.passed
    assert ReasonCode.CIRCUIT_BREAKER in out.reason_codes
    # The breaker tripped: account timestamp is now set.
    async with seeded() as s:
        acc = await s.get(Account, 1)
    assert acc.circuit_breaker_tripped_at is not None


# ---- buying power (LIVE only) ----

def _live_registry(buying_power: str):
    reg = MagicMock()
    adapter = MagicMock()
    adapter.get_account = MagicMock(return_value={"buying_power": buying_power})
    reg.get.return_value = adapter
    return reg


async def test_buying_power_live_insufficient_rejects(seeded):
    eng = RiskEngine(seeded, broker_registry=_live_registry("100"))
    out = await eng.evaluate(
        _req(account_id=2, type=OrderType.LIMIT, limit_price=Decimal("100"), qty=Decimal("10")),
        trading_mode="live", broker_mode=AccountMode.live,
    )
    assert not out.passed
    assert ReasonCode.INSUFFICIENT_BUYING_POWER in out.reason_codes


async def test_buying_power_live_sufficient_passes(seeded):
    eng = RiskEngine(seeded, broker_registry=_live_registry("100000"))
    out = await eng.evaluate(
        _req(account_id=2, type=OrderType.LIMIT, limit_price=Decimal("100"), qty=Decimal("10")),
        trading_mode="live", broker_mode=AccountMode.live,
    )
    assert out.passed


async def test_buying_power_skipped_for_paper(seeded):
    # Paper never calls the broker even when a registry is present.
    reg = _live_registry("1")  # would reject if consulted
    eng = RiskEngine(seeded, broker_registry=reg)
    out = await eng.evaluate(
        _req(type=OrderType.LIMIT, limit_price=Decimal("100"), qty=Decimal("10")),
        trading_mode="paper",
    )
    assert out.passed
    reg.get.assert_not_called()
