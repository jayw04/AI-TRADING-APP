"""P6 §1b — GET /api/v1/strategies/{id}/history (read-only proposal context)."""
from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest

from app.db.enums import (
    OrderSide,
    OrderSourceType,
    OrderStatus,
    OrderType,
    TimeInForce,
)
from app.db.models.order import Order
from app.db.models.strategy import Strategy
from app.db.models.user import User
from app.db.session import get_sessionmaker

BASE = "/api/v1"


@pytest.fixture(autouse=True)
async def _seed(client):
    async with get_sessionmaker()() as s:
        now = datetime.now(UTC)
        s.add(User(id=1, email="jay@test", display_name="Jay"))
        s.add(User(id=2, email="other@test"))
        s.add(
            Strategy(
                id=1, user_id=1, name="S1",
                params_json={"rsi_min": 50}, symbols_json=["AAPL"],
                created_at=now, updated_at=now,
            )
        )
        s.add(
            Strategy(
                id=2, user_id=2, name="OtherS",
                params_json={}, symbols_json=[], created_at=now, updated_at=now,
            )
        )
        await s.commit()
    return client


async def test_history_returns_snapshot_and_performance(client):
    r = await client.get(f"{BASE}/strategies/1/history")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["snapshot"]["id"] == 1
    assert body["snapshot"]["params"] == {"rsi_min": 50}
    assert "performance" in body
    assert "recent_orders_considered" in body["performance"]


async def test_history_other_user_strategy_404(client):
    r = await client.get(f"{BASE}/strategies/2/history")
    assert r.status_code == 404


async def test_history_nonexistent_strategy_404(client):
    r = await client.get(f"{BASE}/strategies/9999/history")
    assert r.status_code == 404


async def test_history_includes_recent_strategy_orders(client):
    now = datetime.now(UTC)
    async with get_sessionmaker()() as s:
        s.add(
            Order(
                user_id=1, account_id=1, symbol_id=1,
                side=OrderSide.BUY, qty=Decimal("1"), type=OrderType.MARKET,
                tif=TimeInForce.DAY, status=OrderStatus.FILLED,
                source_type=OrderSourceType.STRATEGY, source_id="1",
                created_at=now, updated_at=now,
            )
        )
        await s.commit()
    r = await client.get(f"{BASE}/strategies/1/history")
    assert r.status_code == 200
    perf = r.json()["performance"]
    assert perf["recent_orders_considered"] == 1
    assert perf["recent_order_statuses"] == ["filled"]
