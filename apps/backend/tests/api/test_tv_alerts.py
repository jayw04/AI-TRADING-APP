"""Tests for ``POST /api/v1/alerts/tv``.

Uses a fixture that seeds the production DB engine the endpoint will reach
(the same pattern as ``test_orders_endpoint.py``). The shared in-memory
SQLite is created once per test; the throttle/dedup state is reset around
each test via the autouse ``reset_throttle`` fixture.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.alerts import throttle as th
from app.db.enums import SignalType, StrategyStatus, StrategyType
from app.db.models.signal import Signal
from app.db.models.strategy import Strategy as StrategyRow
from app.db.models.symbol import Symbol
from app.db.models.user import User


def _now() -> datetime:
    return datetime.now(UTC)


@pytest.fixture(autouse=True)
def reset_throttle():
    th._reset_for_tests()
    yield
    th._reset_for_tests()


async def _seed(factory: async_sessionmaker) -> None:
    async with factory() as session:
        session.add(
            User(
                id=1,
                email="jay@test",
                display_name="Jay",
                pine_webhook_secret="test-secret-abc123",
            )
        )
        session.add(
            User(
                id=2,
                email="other@test",
                display_name="Other",
                pine_webhook_secret="other-secret-xyz789",
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
        session.add(
            StrategyRow(
                id=1,
                user_id=1,
                name="user1-strat",
                version="0.1.0",
                type=StrategyType.PYTHON,
                status=StrategyStatus.IDLE,
                code_path="examples/rsi_meanreversion.py",
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
                user_id=2,
                name="user2-strat",
                version="0.1.0",
                type=StrategyType.PYTHON,
                status=StrategyStatus.IDLE,
                code_path="examples/rsi_meanreversion.py",
                params_json={},
                symbols_json=["AAPL"],
                schedule="event",
                risk_limits_id=None,
                created_at=_now(),
                updated_at=_now(),
            )
        )
        await session.commit()


@pytest_asyncio.fixture
async def client_and_factory() -> AsyncIterator[tuple[AsyncClient, async_sessionmaker]]:
    """Yields (httpx client, shared-singleton sessionmaker) bound to the same
    in-memory DB the alerts endpoint will reach via ``get_sessionmaker()``."""
    from app.config import get_settings
    from app.db import models  # noqa: F401 — populate Base.metadata
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
    await _seed(factory)

    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac, factory

    await engine.dispose()
    get_engine.cache_clear()
    get_sessionmaker.cache_clear()
    get_event_bus.cache_clear()


@pytest_asyncio.fixture
async def client(client_and_factory) -> AsyncClient:
    return client_and_factory[0]


@pytest_asyncio.fixture
async def factory(client_and_factory) -> async_sessionmaker:
    return client_and_factory[1]


async def test_valid_alert_creates_signal(client, factory) -> None:
    resp = await client.post(
        "/api/v1/alerts/tv",
        json={
            "secret": "test-secret-abc123",
            "symbol": "AAPL",
            "side": "buy",
            "payload": {"price": "190.5", "rsi": "28.1"},
        },
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["signal_id"] is not None
    assert body["deduped"] is False

    async with factory() as session:
        sig = await session.get(Signal, body["signal_id"])
        assert sig is not None
        assert sig.user_id == 1
        assert sig.type == SignalType.PINE_ALERT
        assert sig.strategy_id is None
        assert sig.payload_json["price"] == "190.5"
        assert sig.payload_json["side"] == "buy"
        assert sig.payload_json["source"] == "tradingview"


async def test_bad_secret_returns_401(client) -> None:
    resp = await client.post(
        "/api/v1/alerts/tv",
        json={"secret": "nope-not-a-real-secret", "symbol": "AAPL"},
    )
    assert resp.status_code == 401


async def test_unknown_symbol_returns_400(client) -> None:
    resp = await client.post(
        "/api/v1/alerts/tv",
        json={"secret": "test-secret-abc123", "symbol": "ZZZZZZ"},
    )
    assert resp.status_code == 400
    assert "Unknown symbol" in resp.json()["detail"]


async def test_strategy_ownership_mismatch_returns_404(client) -> None:
    """user1's secret + user2's strategy_id → 404."""
    resp = await client.post(
        "/api/v1/alerts/tv",
        json={
            "secret": "test-secret-abc123",
            "symbol": "AAPL",
            "strategy_id": 2,
        },
    )
    assert resp.status_code == 404


async def test_strategy_id_binds_correctly(client, factory) -> None:
    resp = await client.post(
        "/api/v1/alerts/tv",
        json={
            "secret": "test-secret-abc123",
            "symbol": "AAPL",
            "strategy_id": 1,
            "side": "sell",
            "payload": {"rsi": "75.0"},
        },
    )
    assert resp.status_code == 200
    sid = resp.json()["signal_id"]
    async with factory() as session:
        sig = await session.get(Signal, sid)
        assert sig.strategy_id == 1


async def test_dedup_within_window(client) -> None:
    body = {
        "secret": "test-secret-abc123",
        "symbol": "AAPL",
        "side": "buy",
        "payload": {"price": "190.5"},
    }
    r1 = await client.post("/api/v1/alerts/tv", json=body)
    assert r1.status_code == 200
    assert r1.json()["deduped"] is False

    r2 = await client.post("/api/v1/alerts/tv", json=body)
    assert r2.status_code == 200
    assert r2.json()["deduped"] is True
    assert r2.json()["signal_id"] is None


async def test_dedup_does_not_apply_to_different_payloads(client) -> None:
    r1 = await client.post(
        "/api/v1/alerts/tv",
        json={
            "secret": "test-secret-abc123",
            "symbol": "AAPL",
            "side": "buy",
            "payload": {"price": "190.5"},
        },
    )
    r2 = await client.post(
        "/api/v1/alerts/tv",
        json={
            "secret": "test-secret-abc123",
            "symbol": "AAPL",
            "side": "buy",
            "payload": {"price": "190.6"},
        },
    )
    assert r1.json()["deduped"] is False
    assert r2.json()["deduped"] is False


async def test_rate_limit_kicks_in_after_threshold(client) -> None:
    """``RATE_LIMIT_MAX_PER_WINDOW=20``. 21st request → 429."""
    for i in range(20):
        resp = await client.post(
            "/api/v1/alerts/tv",
            json={
                "secret": "test-secret-abc123",
                "symbol": "AAPL",
                "side": "buy",
                "payload": {"i": i},  # vary to avoid dedup
            },
        )
        assert resp.status_code == 200, f"failed at i={i}: {resp.text}"

    resp = await client.post(
        "/api/v1/alerts/tv",
        json={
            "secret": "test-secret-abc123",
            "symbol": "AAPL",
            "side": "buy",
            "payload": {"i": 999},
        },
    )
    assert resp.status_code == 429


async def test_extra_fields_rejected(client) -> None:
    resp = await client.post(
        "/api/v1/alerts/tv",
        json={
            "secret": "test-secret-abc123",
            "symbol": "AAPL",
            "fnord": "extra",
        },
    )
    assert resp.status_code == 422


async def test_publishes_signal_new_on_bus(client) -> None:
    from app.events import get_event_bus

    bus = get_event_bus()
    bus.publish = AsyncMock()
    resp = await client.post(
        "/api/v1/alerts/tv",
        json={"secret": "test-secret-abc123", "symbol": "AAPL", "side": "buy"},
    )
    assert resp.status_code == 200
    bus.publish.assert_called()
    args = bus.publish.call_args.args
    assert args[0] == "signal.new"
    assert args[1]["type"] == "pine_alert"
    assert args[1]["symbol"] == "AAPL"


async def test_symbol_is_uppercased(client, factory) -> None:
    resp = await client.post(
        "/api/v1/alerts/tv",
        json={"secret": "test-secret-abc123", "symbol": "aapl"},
    )
    assert resp.status_code == 200
    sid = resp.json()["signal_id"]
    async with factory() as session:
        sig = await session.get(Signal, sid)
        sym = await session.get(Symbol, sig.symbol_id)
        assert sym.ticker == "AAPL"


async def test_failed_auth_ip_throttle(client) -> None:
    """10 bad-secret POSTs from the same IP allowed; the 11th throttled."""
    for _ in range(10):
        r = await client.post(
            "/api/v1/alerts/tv",
            json={"secret": "wrong-secret-attempt", "symbol": "AAPL"},
        )
        assert r.status_code == 401

    r = await client.post(
        "/api/v1/alerts/tv",
        json={"secret": "wrong-secret-attempt", "symbol": "AAPL"},
    )
    assert r.status_code == 429
