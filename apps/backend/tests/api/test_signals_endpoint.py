"""Tests for ``GET /api/v1/signals`` (cross-strategy view)."""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta

import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.db.enums import SignalType, StrategyStatus, StrategyType
from app.db.models.account import Account, AccountMode
from app.db.models.signal import Signal
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
        session.add(
            Symbol(
                id=2,
                ticker="MSFT",
                exchange="NASDAQ",
                asset_class="us_equity",
                name="Microsoft",
                active=True,
            )
        )
        strat = StrategyRow(
            user_id=1,
            name="s1",
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
        session.add(strat)
        await session.commit()
        await session.refresh(strat)

        for type_, sym_id, offset in [
            (SignalType.ENTRY, 1, -300),
            (SignalType.EXIT, 1, -200),
            (SignalType.ENTRY, 2, -100),
            (SignalType.INFO, 1, -50),
        ]:
            session.add(
                Signal(
                    user_id=1,
                    strategy_id=strat.id,
                    symbol_id=sym_id,
                    type=type_,
                    payload_json={},
                    received_at=_now() + timedelta(seconds=offset),
                )
            )
        await session.commit()


@pytest_asyncio.fixture
async def client() -> AsyncIterator[AsyncClient]:
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
    await _seed(factory)

    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac

    await engine.dispose()
    get_engine.cache_clear()
    get_sessionmaker.cache_clear()
    get_event_bus.cache_clear()


async def test_list_all_signals(client) -> None:
    resp = await client.get("/api/v1/signals")
    assert resp.status_code == 200
    body = resp.json()
    assert body["count"] == 4


async def test_list_signals_filtered_by_symbol(client) -> None:
    resp = await client.get("/api/v1/signals?symbol=MSFT")
    assert resp.status_code == 200
    body = resp.json()
    assert body["count"] == 1
    assert body["items"][0]["symbol"] == "MSFT"


async def test_list_signals_filtered_by_type(client) -> None:
    resp = await client.get("/api/v1/signals?type=entry")
    assert resp.status_code == 200
    body = resp.json()
    assert body["count"] == 2
    assert all(item["type"] == "entry" for item in body["items"])


async def test_list_signals_unknown_symbol_returns_empty(client) -> None:
    resp = await client.get("/api/v1/signals?symbol=ZZZZ")
    assert resp.status_code == 200
    assert resp.json()["count"] == 0
