"""Tests for the Opportunities aggregator endpoint (P4 §3).

Covers:
- Empty-state ⇒ all six widgets report count=0.
- Per-widget window filtering (signals 30 min, pine 30 min, risk 60 min,
  fills 15 min).
- Signal/pine separation (PINE_ALERT only in pine_alerts).
- Strategies in error: only ``status=='error'`` rows surface.
- Open orders nearing expiry: GTC age threshold + filled orders excluded.
- Risk rejections: only ``decision=='reject'`` rows.
- Per-user scoping: user 2's signals invisible to user 1.
- ``as_of`` timestamps on every widget + on the envelope.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.db.enums import (
    OrderSide,
    OrderSourceType,
    OrderStatus,
    OrderType,
    RiskDecision,
    SignalType,
    StrategyStatus,
    StrategyType,
    TimeInForce,
)
from app.db.models.account import Account, AccountMode
from app.db.models.fill import Fill
from app.db.models.order import Order
from app.db.models.risk_check import RiskCheck
from app.db.models.signal import Signal
from app.db.models.strategy import Strategy as StrategyRow
from app.db.models.symbol import Symbol
from app.db.models.user import User


def _now() -> datetime:
    return datetime.now(UTC)


async def _seed_base(factory: async_sessionmaker) -> None:
    async with factory() as session:
        session.add(User(id=1, email="jay@test", display_name="Jay"))
        session.add(
            Account(
                id=1,
                user_id=1,
                broker="alpaca",
                mode=AccountMode.paper,
                label="Paper",
            )
        )
        session.add(
            Symbol(
                id=1,
                ticker="AAPL",
                exchange="NASDAQ",
                asset_class="us_equity",
                name="Apple",
                active=True,
            )
        )
        await session.commit()


@pytest_asyncio.fixture
async def client_and_factory() -> AsyncIterator[tuple[AsyncClient, async_sessionmaker]]:
    from app.config import get_settings
    from app.db import models  # noqa: F401
    from app.db.base import Base
    from app.db.session import get_engine, get_sessionmaker
    from app.events.bus import get_event_bus
    from app.main import create_app

    get_settings.cache_clear()
    get_engine.cache_clear()
    get_sessionmaker.cache_clear()
    get_event_bus.cache_clear()

    engine = get_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = get_sessionmaker()
    await _seed_base(factory)

    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac, factory

    await engine.dispose()
    get_engine.cache_clear()
    get_sessionmaker.cache_clear()
    get_event_bus.cache_clear()


async def test_empty_state_returns_zeros(client_and_factory) -> None:
    client, _ = client_and_factory
    resp = await client.get("/api/v1/opportunities")
    assert resp.status_code == 200
    body = resp.json()
    for key in (
        "live_signals",
        "pine_alerts",
        "strategy_errors",
        "open_orders_expiring",
        "risk_rejections",
        "recent_fills",
    ):
        assert body[key]["count"] == 0
        assert body[key]["items"] == []
        assert body[key]["as_of"] is not None
    assert body["as_of"] is not None


async def test_live_signals_window_includes_recent_excludes_old(
    client_and_factory,
) -> None:
    client, factory = client_and_factory
    async with factory() as session:
        strat = StrategyRow(
            id=1,
            user_id=1,
            name="rsi",
            version="0.1.0",
            type=StrategyType.PYTHON,
            status=StrategyStatus.IDLE,
            code_path="examples/rsi.py",
            params_json={},
            symbols_json=["AAPL"],
            schedule="event",
            risk_limits_id=None,
            created_at=_now(),
            updated_at=_now(),
        )
        session.add(strat)
        session.add(
            Signal(
                user_id=1,
                strategy_id=1,
                symbol_id=1,
                type=SignalType.ENTRY,
                payload_json={"reason": "rsi_oversold", "side": "buy"},
                received_at=_now() - timedelta(minutes=5),
            )
        )
        session.add(
            Signal(
                user_id=1,
                strategy_id=1,
                symbol_id=1,
                type=SignalType.EXIT,
                payload_json={"reason": "rsi_exit"},
                received_at=_now() - timedelta(hours=2),
            )
        )
        await session.commit()

    resp = await client.get("/api/v1/opportunities")
    body = resp.json()
    assert body["live_signals"]["count"] == 1
    item = body["live_signals"]["items"][0]
    assert item["symbol"] == "AAPL"
    assert item["strategy_name"] == "rsi"
    assert item["reason"] == "rsi_oversold"
    assert item["side"] == "buy"


async def test_pine_alerts_widget_is_separate_from_live_signals(
    client_and_factory,
) -> None:
    client, factory = client_and_factory
    async with factory() as session:
        session.add(
            Signal(
                user_id=1,
                strategy_id=None,
                symbol_id=1,
                type=SignalType.PINE_ALERT,
                payload_json={"comment": "RSI cross", "side": "long"},
                received_at=_now() - timedelta(minutes=10),
            )
        )
        await session.commit()

    resp = await client.get("/api/v1/opportunities")
    body = resp.json()
    assert body["live_signals"]["count"] == 0
    assert body["pine_alerts"]["count"] == 1
    pa = body["pine_alerts"]["items"][0]
    assert pa["strategy_name"] is None
    assert pa["reason"] == "RSI cross"
    assert pa["side"] == "long"


async def test_strategy_errors_widget_shows_only_error_status(
    client_and_factory,
) -> None:
    client, factory = client_and_factory
    async with factory() as session:
        session.add(
            StrategyRow(
                id=1,
                user_id=1,
                name="healthy",
                version="0.1.0",
                type=StrategyType.PYTHON,
                status=StrategyStatus.PAPER,
                code_path="examples/ok.py",
                params_json={},
                symbols_json=["AAPL"],
                schedule="event",
                risk_limits_id=None,
                created_at=_now(),
                updated_at=_now(),
            )
        )
        session.add(
            StrategyRow(
                id=2,
                user_id=1,
                name="broken",
                version="0.1.0",
                type=StrategyType.PYTHON,
                status=StrategyStatus.ERROR,
                code_path="examples/broken.py",
                params_json={},
                symbols_json=["AAPL"],
                schedule="event",
                risk_limits_id=None,
                error_text="loader failed: import broken_dep",
                created_at=_now(),
                updated_at=_now(),
            )
        )
        await session.commit()

    resp = await client.get("/api/v1/opportunities")
    body = resp.json()
    assert body["strategy_errors"]["count"] == 1
    item = body["strategy_errors"]["items"][0]
    assert item["name"] == "broken"
    assert "loader failed" in item["error_text"]


async def test_gtc_order_flagged_when_older_than_threshold(
    client_and_factory,
) -> None:
    client, factory = client_and_factory
    async with factory() as session:
        eight_days_ago = _now() - timedelta(days=8)
        session.add(
            Order(
                id=1,
                user_id=1,
                account_id=1,
                symbol_id=1,
                broker_order_id="b1",
                side=OrderSide.BUY,
                qty=Decimal("10"),
                type=OrderType.LIMIT,
                limit_price=Decimal("100"),
                tif=TimeInForce.GTC,
                status=OrderStatus.SUBMITTED,
                source_type=OrderSourceType.MANUAL,
                source_id=None,
                created_at=eight_days_ago,
                updated_at=eight_days_ago,
            )
        )
        await session.commit()

    resp = await client.get("/api/v1/opportunities")
    body = resp.json()
    assert body["open_orders_expiring"]["count"] == 1
    item = body["open_orders_expiring"]["items"][0]
    assert "GTC age" in item["expiry_reason"]
    assert item["symbol"] == "AAPL"


async def test_filled_orders_excluded_from_expiring_widget(
    client_and_factory,
) -> None:
    client, factory = client_and_factory
    async with factory() as session:
        eight_days_ago = _now() - timedelta(days=8)
        session.add(
            Order(
                id=1,
                user_id=1,
                account_id=1,
                symbol_id=1,
                broker_order_id="b1",
                side=OrderSide.BUY,
                qty=Decimal("10"),
                type=OrderType.MARKET,
                tif=TimeInForce.GTC,
                status=OrderStatus.FILLED,
                source_type=OrderSourceType.MANUAL,
                source_id=None,
                created_at=eight_days_ago,
                updated_at=eight_days_ago,
            )
        )
        await session.commit()

    resp = await client.get("/api/v1/opportunities")
    body = resp.json()
    assert body["open_orders_expiring"]["count"] == 0


async def test_risk_rejects_widget_filters_by_decision_and_window(
    client_and_factory,
) -> None:
    client, factory = client_and_factory
    async with factory() as session:
        # An order under user 1 so the rejections are scoped to him.
        order = Order(
            id=1,
            user_id=1,
            account_id=1,
            symbol_id=1,
            broker_order_id=None,
            side=OrderSide.BUY,
            qty=Decimal("10"),
            type=OrderType.MARKET,
            tif=TimeInForce.DAY,
            status=OrderStatus.REJECTED,
            source_type=OrderSourceType.MANUAL,
            source_id=None,
            created_at=_now(),
            updated_at=_now(),
        )
        session.add(order)
        await session.flush()
        # Recent reject — should appear.
        session.add(
            RiskCheck(
                order_id=1,
                decision=RiskDecision.REJECT,
                reason_codes=["POSITION_CAP_NOTIONAL"],
                evaluated_at=_now() - timedelta(minutes=15),
            )
        )
        # Recent pass — should NOT appear.
        session.add(
            RiskCheck(
                order_id=1,
                decision=RiskDecision.PASS,
                reason_codes=[],
                evaluated_at=_now() - timedelta(minutes=10),
            )
        )
        # Old reject — outside window.
        session.add(
            RiskCheck(
                order_id=1,
                decision=RiskDecision.REJECT,
                reason_codes=["DAILY_LOSS"],
                evaluated_at=_now() - timedelta(hours=3),
            )
        )
        await session.commit()

    resp = await client.get("/api/v1/opportunities")
    body = resp.json()
    assert body["risk_rejections"]["count"] == 1
    item = body["risk_rejections"]["items"][0]
    assert item["reason_codes"] == ["POSITION_CAP_NOTIONAL"]
    assert item["symbol"] == "AAPL"


async def test_recent_fills_window_filters(client_and_factory) -> None:
    client, factory = client_and_factory
    async with factory() as session:
        session.add(
            Order(
                id=1,
                user_id=1,
                account_id=1,
                symbol_id=1,
                broker_order_id="b1",
                side=OrderSide.BUY,
                qty=Decimal("10"),
                type=OrderType.MARKET,
                tif=TimeInForce.DAY,
                status=OrderStatus.FILLED,
                source_type=OrderSourceType.MANUAL,
                source_id=None,
                created_at=_now(),
                updated_at=_now(),
            )
        )
        await session.flush()
        session.add(
            Fill(
                order_id=1,
                broker_fill_id="f1",
                qty=Decimal("10"),
                price=Decimal("190.50"),
                filled_at=_now() - timedelta(minutes=5),
            )
        )
        session.add(
            Fill(
                order_id=1,
                broker_fill_id="f2",
                qty=Decimal("5"),
                price=Decimal("191.00"),
                filled_at=_now() - timedelta(hours=1),
            )
        )
        await session.commit()

    resp = await client.get("/api/v1/opportunities")
    body = resp.json()
    assert body["recent_fills"]["count"] == 1
    item = body["recent_fills"]["items"][0]
    assert item["symbol"] == "AAPL"
    assert item["side"] == "buy"


async def test_recent_fills_resolves_strategy_name(client_and_factory) -> None:
    """A strategy-sourced order resolves its strategy_name in the fills feed."""
    client, factory = client_and_factory
    async with factory() as session:
        session.add(
            StrategyRow(
                id=42,
                user_id=1,
                name="rsi-bot",
                version="0.1.0",
                type=StrategyType.PYTHON,
                status=StrategyStatus.PAPER,
                code_path="examples/rsi.py",
                params_json={},
                symbols_json=["AAPL"],
                schedule="event",
                risk_limits_id=None,
                created_at=_now(),
                updated_at=_now(),
            )
        )
        session.add(
            Order(
                id=1,
                user_id=1,
                account_id=1,
                symbol_id=1,
                broker_order_id="b1",
                side=OrderSide.SELL,
                qty=Decimal("3"),
                type=OrderType.MARKET,
                tif=TimeInForce.DAY,
                status=OrderStatus.FILLED,
                source_type=OrderSourceType.STRATEGY,
                source_id="42",
                created_at=_now(),
                updated_at=_now(),
            )
        )
        await session.flush()
        session.add(
            Fill(
                order_id=1,
                broker_fill_id="f1",
                qty=Decimal("3"),
                price=Decimal("190.00"),
                filled_at=_now() - timedelta(minutes=2),
            )
        )
        await session.commit()

    resp = await client.get("/api/v1/opportunities")
    body = resp.json()
    item = body["recent_fills"]["items"][0]
    assert item["strategy_id"] == 42
    assert item["strategy_name"] == "rsi-bot"


async def test_other_user_signals_not_visible(client_and_factory) -> None:
    client, factory = client_and_factory
    async with factory() as session:
        session.add(User(id=2, email="other@test", display_name="Other"))
        await session.flush()
        session.add(
            Signal(
                user_id=2,
                strategy_id=None,
                symbol_id=1,
                type=SignalType.ENTRY,
                payload_json={},
                received_at=_now() - timedelta(minutes=5),
            )
        )
        await session.commit()

    resp = await client.get("/api/v1/opportunities")
    body = resp.json()
    assert body["live_signals"]["count"] == 0
    assert body["pine_alerts"]["count"] == 0
