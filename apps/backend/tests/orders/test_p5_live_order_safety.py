"""P5 §6 — OrderRouter live-order-safety integration.

Tested at the OrderRouter level (not via the HTTP API): the POST /orders
endpoint hardcodes the user's PAPER account and forbids unknown fields, so
manual LIVE orders are not reachable through the API until P5 §7. The router
is the single dispatch point (ADR 0002) where confirmation + cooldown + the
LIVE_ORDER_SUBMITTED audit live, so it's where they're exercised.
"""
from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest
from sqlalchemy import select

from app.db.enums import (
    OrderSide,
    OrderSourceType,
    OrderStatus,
    OrderType,
    RiskScopeType,
    StrategyStatus,
    StrategyType,
    TimeInForce,
)
from app.db.models.account import Account, AccountMode
from app.db.models.audit_log import AuditLog
from app.db.models.risk_limits import RiskLimits
from app.db.models.strategy import Strategy as StrategyRow
from app.db.models.symbol import Symbol
from app.db.models.user import User
from app.orders.router import BrokerModeError, OrderRouter
from app.risk.engine import RiskEngine
from app.risk.types import OrderRequest


class _StubAdapter:
    is_paper = True

    def submit_order(self, **kwargs):
        return {"id": "broker-123", "status": "accepted"}


class _StubBus:
    async def publish(self, topic, payload):
        return None


def _now() -> datetime:
    return datetime.now(UTC)


@pytest.fixture
async def seeded(session_factory):
    async with session_factory() as session:
        session.add(User(id=1, email="t@local"))
        session.add(Account(id=1, user_id=1, broker="alpaca",
                            mode=AccountMode.paper, label="Paper", created_at=_now()))
        session.add(Account(id=2, user_id=1, broker="alpaca",
                            mode=AccountMode.live, label="Live", created_at=_now()))
        session.add(Symbol(id=1, ticker="AAPL", exchange="NASDAQ",
                           asset_class="us_equity", name="Apple", active=True))
        session.add(RiskLimits(
            user_id=1, broker_mode=AccountMode.paper, scope_type=RiskScopeType.GLOBAL,
            max_position_qty=Decimal("1000"), max_position_notional=Decimal("1000000"),
            max_gross_exposure=Decimal("5000000"), max_daily_loss=Decimal("100000"),
            max_orders_per_minute=1000, allow_short=False,
            created_at=_now(), updated_at=_now(),
        ))
        session.add(StrategyRow(
            id=10, user_id=1, name="s10", version="0.1.0",
            type=StrategyType.PYTHON, status=StrategyStatus.PAPER,
            code_path="x.py", params_json={}, symbols_json=[],
            schedule="event", created_at=_now(), updated_at=_now(),
        ))
        await session.commit()
    return session_factory


def _router(sf):
    return OrderRouter(_StubAdapter(), RiskEngine(sf), sf, _StubBus())


def _req(*, account_id, source_type=OrderSourceType.MANUAL, source_id=None,
         symbol="AAPL", confirmation_text=None) -> OrderRequest:
    return OrderRequest(
        user_id=1, account_id=account_id, symbol_ticker=symbol,
        side=OrderSide.BUY, qty=Decimal("1"), type=OrderType.MARKET,
        tif=TimeInForce.DAY, source_type=source_type, source_id=source_id,
        confirmation_text=confirmation_text,
    )


# ---- confirmation gate ----

async def test_manual_live_no_confirmation_rejected(seeded):
    order = await _router(seeded).submit(_req(account_id=2))
    assert order.status == OrderStatus.REJECTED
    assert order.rejection_reason == "CONFIRMATION_REQUIRED"


async def test_manual_live_wrong_confirmation_rejected(seeded):
    order = await _router(seeded).submit(
        _req(account_id=2, confirmation_text="MSFT")
    )
    assert order.status == OrderStatus.REJECTED
    assert order.rejection_reason == "CONFIRMATION_MISMATCH"


async def test_manual_live_correct_confirmation_reaches_broker_mode_guard(seeded):
    # Confirmation passes → falls through to the §1 BrokerModeError (live not
    # enabled yet). The point: confirmation didn't reject it.
    with pytest.raises(BrokerModeError):
        await _router(seeded).submit(_req(account_id=2, confirmation_text="AAPL"))


async def test_confirmation_case_insensitive(seeded):
    with pytest.raises(BrokerModeError):
        await _router(seeded).submit(_req(account_id=2, confirmation_text="aapl"))


async def test_confirmation_whitespace_stripped(seeded):
    with pytest.raises(BrokerModeError):
        await _router(seeded).submit(_req(account_id=2, confirmation_text="  AAPL  "))


async def test_manual_paper_needs_no_confirmation(seeded):
    order = await _router(seeded).submit(_req(account_id=1))
    # Paper order routes normally (no confirmation gate).
    assert order.status != OrderStatus.REJECTED or order.rejection_reason not in (
        "CONFIRMATION_REQUIRED", "CONFIRMATION_MISMATCH",
    )


async def test_strategy_live_needs_no_confirmation(seeded):
    # STRATEGY source skips confirmation → falls through to BrokerModeError.
    with pytest.raises(BrokerModeError):
        await _router(seeded).submit(
            _req(account_id=2, source_type=OrderSourceType.STRATEGY, source_id="10")
        )


# ---- LIVE_ORDER_SUBMITTED audit ----

async def test_live_attempt_audits(seeded):
    await _router(seeded).submit(_req(account_id=2, confirmation_text="MSFT"))
    async with seeded() as session:
        audits = (await session.execute(
            select(AuditLog).where(AuditLog.action == "LIVE_ORDER_SUBMITTED")
        )).scalars().all()
    assert len(audits) == 1
    import json
    payload = json.loads(audits[0].payload_json)
    assert payload["symbol"] == "AAPL"
    assert payload["outcome"] == "rejected"
    assert payload["reason_code"] == "CONFIRMATION_MISMATCH"


async def test_broker_mode_refusal_audits(seeded):
    with pytest.raises(BrokerModeError):
        await _router(seeded).submit(_req(account_id=2, confirmation_text="AAPL"))
    async with seeded() as session:
        audits = (await session.execute(
            select(AuditLog).where(AuditLog.action == "LIVE_ORDER_SUBMITTED")
        )).scalars().all()
    assert len(audits) == 1
    import json
    assert json.loads(audits[0].payload_json)["reason_code"] == "BROKER_MODE_NOT_ENABLED"


async def test_paper_order_does_not_audit_live(seeded):
    await _router(seeded).submit(_req(account_id=1))
    async with seeded() as session:
        audits = (await session.execute(
            select(AuditLog).where(AuditLog.action == "LIVE_ORDER_SUBMITTED")
        )).scalars().all()
    assert len(audits) == 0


# ---- cooldown ----

async def test_strategy_in_cooldown_rejected(seeded):
    from app.services.strategy_cooldown import StrategyCooldownService
    async with seeded() as session:
        await StrategyCooldownService(session).set_cooldown(10)
    order = await _router(seeded).submit(
        _req(account_id=1, source_type=OrderSourceType.STRATEGY, source_id="10")
    )
    assert order.status == OrderStatus.REJECTED
    assert order.rejection_reason == "STRATEGY_COOLDOWN"


async def test_strategy_failure_sets_cooldown(seeded):
    # Unknown symbol → risk rejects (ephemeral) → STRATEGY cooldown set.
    order = await _router(seeded).submit(
        _req(account_id=1, source_type=OrderSourceType.STRATEGY, source_id="10",
             symbol="ZZZZ")
    )
    assert order.status == OrderStatus.REJECTED
    async with seeded() as session:
        strat = await session.get(StrategyRow, 10)
    assert strat.cooldown_until is not None


async def test_manual_failure_does_not_set_cooldown(seeded):
    # A manual order failing risk must NOT cool down any strategy.
    await _router(seeded).submit(_req(account_id=1, symbol="ZZZZ"))
    async with seeded() as session:
        strat = await session.get(StrategyRow, 10)
    assert strat.cooldown_until is None


async def test_strategy_success_does_not_set_cooldown(seeded):
    order = await _router(seeded).submit(
        _req(account_id=1, source_type=OrderSourceType.STRATEGY, source_id="10")
    )
    assert order.status != OrderStatus.REJECTED  # routed to stub broker
    async with seeded() as session:
        strat = await session.get(StrategyRow, 10)
    assert strat.cooldown_until is None
