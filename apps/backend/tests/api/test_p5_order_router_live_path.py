"""P5 §7 — the lifted §1 guard. Tested at the OrderRouter level (the order_router
is not on app.state when alpaca-startup is disabled in tests, same as the §6
live-safety tests). The guard returns an ephemeral REJECTED Order carrying the
typed reason in `rejection_reason`. Plus one API-level test for LIVE account
creation requiring TOTP."""
from datetime import UTC, datetime
from decimal import Decimal

import pytest

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
from app.db.models.strategy import Strategy as StrategyRow
from app.db.models.symbol import Symbol
from app.db.models.user import User
from app.orders.router import OrderRouter
from app.risk.engine import RiskEngine
from app.risk.types import OrderRequest


class _StubAdapter:
    is_paper = False  # this stub stands in for a LIVE adapter

    def submit_order(self, **kwargs):
        return {"id": "broker-1", "status": "accepted"}


class _StubBus:
    async def publish(self, topic, payload):
        return None


def _now() -> datetime:
    return datetime.now(UTC)


@pytest.fixture
async def seeded(session_factory):
    async with session_factory() as session:
        session.add(User(id=1, email="t@local"))
        session.add(Account(id=1, user_id=1, broker="alpaca", mode=AccountMode.live,
                            label="MyLive", created_at=_now()))
        session.add(Symbol(id=1, ticker="AAPL", exchange="NASDAQ",
                           asset_class="us_equity", name="Apple", active=True))
        session.add(StrategyRow(id=10, user_id=1, name="pending", version="0.1.0",
                                type=StrategyType.PYTHON, status=StrategyStatus.PENDING_LIVE,
                                live_activation_initiated_at=_now(), code_path="x.py",
                                params_json={}, symbols_json=[], schedule="event",
                                created_at=_now(), updated_at=_now()))
        session.add(StrategyRow(id=11, user_id=1, name="livestrat", version="0.1.0",
                                type=StrategyType.PYTHON, status=StrategyStatus.LIVE,
                                code_path="x.py", params_json={}, symbols_json=[],
                                schedule="event", created_at=_now(), updated_at=_now()))
        await session.commit()
    return session_factory


def _router(sf):
    return OrderRouter(_StubAdapter(), RiskEngine(sf), sf, _StubBus())


def _req(sf_unused=None, *, source_type=OrderSourceType.MANUAL, source_id=None,
         confirmation_text=None) -> OrderRequest:
    return OrderRequest(
        user_id=1, account_id=1, symbol_ticker="AAPL", side=OrderSide.BUY,
        qty=Decimal("1"), type=OrderType.MARKET, tif=TimeInForce.DAY,
        source_type=source_type, source_id=source_id, confirmation_text=confirmation_text,
    )


async def test_strategy_pending_live_rejected(seeded):
    order = await _router(seeded).submit(
        _req(source_type=OrderSourceType.STRATEGY, source_id="10")
    )
    assert order.status == OrderStatus.REJECTED
    assert order.rejection_reason == "STRATEGY_PENDING_LIVE"


async def test_strategy_id_required(seeded):
    order = await _router(seeded).submit(_req(source_type=OrderSourceType.STRATEGY))
    assert order.rejection_reason == "STRATEGY_ID_REQUIRED"


async def test_strategy_not_found(seeded):
    order = await _router(seeded).submit(
        _req(source_type=OrderSourceType.STRATEGY, source_id="999")
    )
    assert order.rejection_reason == "STRATEGY_NOT_FOUND"


async def test_agent_live_rejected(seeded):
    order = await _router(seeded).submit(
        _req(source_type=OrderSourceType.AGENT_PROPOSAL)
    )
    assert order.status == OrderStatus.REJECTED
    assert order.rejection_reason == "AGENT_LIVE_DISABLED"


async def test_strategy_live_passes_guard(seeded):
    # status=LIVE passes the §7 guard; downstream risk rejects (no live limits)
    # but NOT with a guard code.
    order = await _router(seeded).submit(
        _req(source_type=OrderSourceType.STRATEGY, source_id="11")
    )
    assert order.rejection_reason not in (
        "STRATEGY_PENDING_LIVE", "STRATEGY_NOT_LIVE", "STRATEGY_ID_REQUIRED",
        "STRATEGY_NOT_FOUND",
    )


async def test_manual_live_requires_confirmation(seeded):
    order = await _router(seeded).submit(_req(source_type=OrderSourceType.MANUAL))
    assert order.status == OrderStatus.REJECTED
    assert order.rejection_reason == "CONFIRMATION_REQUIRED"


async def test_manual_live_with_confirmation_passes_guard(seeded):
    order = await _router(seeded).submit(
        _req(source_type=OrderSourceType.MANUAL, confirmation_text="AAPL")
    )
    assert order.rejection_reason not in (
        "CONFIRMATION_REQUIRED", "CONFIRMATION_MISMATCH", "AGENT_LIVE_DISABLED",
    )


# ---- API-level: LIVE account creation requires TOTP ----

async def test_live_account_creation_requires_totp(client):
    from app.db.session import get_sessionmaker
    async with get_sessionmaker()() as session:
        session.add(User(id=1, email="jay@test", display_name="Jay"))
        await session.commit()
    r = await client.post("/api/v1/accounts",
                          json={"broker": "alpaca", "mode": "live", "label": "L"})
    assert r.status_code == 400
