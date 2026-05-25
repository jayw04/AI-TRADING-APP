"""Tests for ``/api/v1/strategies`` and its sub-resources.

Uses the same shared-singleton-DB pattern as ``test_orders_endpoint.py``
and ``test_tv_alerts.py``: a single fixture yields the httpx client +
the sessionmaker bound to the same in-memory SQLite the endpoint
reaches via ``get_sessionmaker()``.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pandas as pd
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.db.enums import StrategyStatus, StrategyType
from app.db.models.account import Account, AccountMode
from app.db.models.strategy import Strategy as StrategyRow
from app.db.models.symbol import Symbol
from app.db.models.user import User


def _now() -> datetime:
    return datetime.now(UTC)


async def _seed(factory: async_sessionmaker) -> None:
    async with factory() as session:
        session.add(User(id=1, email="jay@test", display_name="Jay"))
        session.add(
            Account(
                id=1, user_id=1, broker="alpaca", mode=AccountMode.paper, label="Paper"
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
async def client_and_factory() -> (
    AsyncIterator[tuple[AsyncClient, async_sessionmaker]]
):
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
    # Endpoints look these up on app.state via getattr(..., default=None);
    # mock them out so list/get/update don't hit the 503 path.
    app.state.strategy_engine = MagicMock()
    app.state.strategy_engine.register = AsyncMock()
    app.state.strategy_engine.unregister = AsyncMock()
    app.state.bar_cache = MagicMock()
    app.state.bar_cache.get_bars = AsyncMock(
        return_value=pd.DataFrame(columns=["t", "o", "h", "l", "c", "v"])
    )
    app.state.indicator_computer = MagicMock()

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


# ---------- POST /strategies ----------


async def test_create_rejects_extra_field(client) -> None:
    resp = await client.post(
        "/api/v1/strategies",
        json={
            "name": "test",
            "code_path": "examples/rsi_meanreversion.py",
            "fnord": "extra-field",
        },
    )
    assert resp.status_code == 422


async def test_create_rejects_pine_type(client) -> None:
    resp = await client.post(
        "/api/v1/strategies",
        json={"name": "pine-later", "code_path": None, "type": "pine"},
    )
    assert resp.status_code == 400
    assert "reserved" in resp.json()["detail"].lower()


async def test_create_rejects_missing_file(client) -> None:
    resp = await client.post(
        "/api/v1/strategies",
        json={
            "name": "missing",
            "code_path": "does/not/exist.py",
            "type": "python",
        },
    )
    assert resp.status_code == 400


async def test_create_succeeds_with_real_reference_strategy(client) -> None:
    """Uses the actual reference RSI strategy file as the create target."""
    resp = await client.post(
        "/api/v1/strategies",
        json={
            "name": "rsi-test-1",
            "code_path": "examples/rsi_meanreversion.py",
            "type": "python",
            "symbols": ["AAPL"],
            "params": {"entry_threshold": 25.0},
        },
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["status"] == "idle"
    assert body["symbols"] == ["AAPL"]
    assert body["params"]["entry_threshold"] == 25.0


# ---------- GET /strategies ----------


async def test_list_filters_by_status(client, factory) -> None:
    async with factory() as session:
        session.add(
            StrategyRow(
                user_id=1,
                name="active",
                version="0.1.0",
                type=StrategyType.PYTHON,
                status=StrategyStatus.PAPER,
                code_path="examples/rsi_meanreversion.py",
                params_json={},
                symbols_json=["AAPL"],
                schedule="*/1 * * * *",
                risk_limits_id=None,
                created_at=_now(),
                updated_at=_now(),
            )
        )
        session.add(
            StrategyRow(
                user_id=1,
                name="idle",
                version="0.1.0",
                type=StrategyType.PYTHON,
                status=StrategyStatus.IDLE,
                code_path="examples/rsi_meanreversion.py",
                params_json={},
                symbols_json=["AAPL"],
                schedule="*/1 * * * *",
                risk_limits_id=None,
                created_at=_now(),
                updated_at=_now(),
            )
        )
        await session.commit()

    resp = await client.get("/api/v1/strategies?status=paper")
    assert resp.status_code == 200
    body = resp.json()
    assert body["count"] == 1
    assert body["items"][0]["name"] == "active"


async def test_get_strategy_returns_404_for_unknown(client) -> None:
    resp = await client.get("/api/v1/strategies/9999")
    assert resp.status_code == 404


# ---------- PUT /strategies/{id} ----------


async def test_update_rejects_when_active(client, factory) -> None:
    async with factory() as session:
        row = StrategyRow(
            user_id=1,
            name="busy",
            version="0.1.0",
            type=StrategyType.PYTHON,
            status=StrategyStatus.PAPER,
            code_path="examples/rsi_meanreversion.py",
            params_json={},
            symbols_json=["AAPL"],
            schedule="*/1 * * * *",
            risk_limits_id=None,
            created_at=_now(),
            updated_at=_now(),
        )
        session.add(row)
        await session.commit()
        await session.refresh(row)
        sid = row.id

    resp = await client.put(
        f"/api/v1/strategies/{sid}", json={"params": {"entry_threshold": 20}}
    )
    assert resp.status_code == 409


async def test_update_succeeds_when_idle(client, factory) -> None:
    async with factory() as session:
        row = StrategyRow(
            user_id=1,
            name="editable",
            version="0.1.0",
            type=StrategyType.PYTHON,
            status=StrategyStatus.IDLE,
            code_path="examples/rsi_meanreversion.py",
            params_json={"entry_threshold": 30},
            symbols_json=["AAPL"],
            schedule="*/1 * * * *",
            risk_limits_id=None,
            created_at=_now(),
            updated_at=_now(),
        )
        session.add(row)
        await session.commit()
        await session.refresh(row)
        sid = row.id

    resp = await client.put(
        f"/api/v1/strategies/{sid}",
        json={"params": {"entry_threshold": 25}, "symbols": ["AAPL", "MSFT"]},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["params"]["entry_threshold"] == 25
    assert body["symbols"] == ["AAPL", "MSFT"]


# ---------- POST /start | /stop ----------


async def test_start_calls_engine_register(client, factory) -> None:
    async with factory() as session:
        row = StrategyRow(
            user_id=1,
            name="to-start",
            version="0.1.0",
            type=StrategyType.PYTHON,
            status=StrategyStatus.IDLE,
            code_path="examples/rsi_meanreversion.py",
            params_json={},
            symbols_json=["AAPL"],
            schedule="*/1 * * * *",
            risk_limits_id=None,
            created_at=_now(),
            updated_at=_now(),
        )
        session.add(row)
        await session.commit()
        await session.refresh(row)
        sid = row.id

    async def fake_register(strategy_id: int):
        async with factory() as s:
            r = await s.get(StrategyRow, strategy_id)
            r.status = StrategyStatus.PAPER
            await s.commit()
        result = MagicMock()
        result.run_id = 42
        return result

    client._transport.app.state.strategy_engine.register = fake_register

    resp = await client.post(f"/api/v1/strategies/{sid}/start")
    assert resp.status_code == 200
    body = resp.json()
    assert body["action"] == "start"
    assert body["new_status"] == "paper"
    assert body["run_id"] == 42


async def test_start_is_idempotent_when_already_active(client, factory) -> None:
    async with factory() as session:
        row = StrategyRow(
            user_id=1,
            name="already-running",
            version="0.1.0",
            type=StrategyType.PYTHON,
            status=StrategyStatus.PAPER,
            code_path="examples/rsi_meanreversion.py",
            params_json={},
            symbols_json=["AAPL"],
            schedule="*/1 * * * *",
            risk_limits_id=None,
            created_at=_now(),
            updated_at=_now(),
        )
        session.add(row)
        await session.commit()
        await session.refresh(row)
        sid = row.id

    register_mock = AsyncMock()
    client._transport.app.state.strategy_engine.register = register_mock

    resp = await client.post(f"/api/v1/strategies/{sid}/start")
    assert resp.status_code == 200
    assert resp.json()["new_status"] == "paper"
    # No-op: engine.register must not be called when already active.
    register_mock.assert_not_awaited()


async def test_stop_calls_engine_unregister(client, factory) -> None:
    async with factory() as session:
        row = StrategyRow(
            user_id=1,
            name="to-stop",
            version="0.1.0",
            type=StrategyType.PYTHON,
            status=StrategyStatus.PAPER,
            code_path="examples/rsi_meanreversion.py",
            params_json={},
            symbols_json=["AAPL"],
            schedule="*/1 * * * *",
            risk_limits_id=None,
            created_at=_now(),
            updated_at=_now(),
        )
        session.add(row)
        await session.commit()
        await session.refresh(row)
        sid = row.id

    async def fake_unregister(strategy_id: int, *, reason: str | None = None) -> None:
        async with factory() as s:
            r = await s.get(StrategyRow, strategy_id)
            r.status = StrategyStatus.IDLE
            await s.commit()

    client._transport.app.state.strategy_engine.unregister = fake_unregister

    resp = await client.post(f"/api/v1/strategies/{sid}/stop")
    assert resp.status_code == 200
    assert resp.json()["new_status"] == "idle"


# ---------- ownership ----------


async def test_other_user_strategy_returns_404(client, factory) -> None:
    async with factory() as session:
        session.add(User(id=2, email="other@test", display_name="Other"))
        await session.commit()
        row = StrategyRow(
            user_id=2,
            name="someone-elses",
            version="0.1.0",
            type=StrategyType.PYTHON,
            status=StrategyStatus.IDLE,
            code_path="examples/rsi_meanreversion.py",
            params_json={},
            symbols_json=["AAPL"],
            schedule="*/1 * * * *",
            risk_limits_id=None,
            created_at=_now(),
            updated_at=_now(),
        )
        session.add(row)
        await session.commit()
        await session.refresh(row)
        other_sid = row.id

    resp = await client.get(f"/api/v1/strategies/{other_sid}")
    assert resp.status_code == 404
