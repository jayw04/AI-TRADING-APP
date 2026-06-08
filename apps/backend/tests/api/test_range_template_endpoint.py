"""P8 §7 — POST /api/v1/range-template/apply."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

import pandas as pd
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker


def _bars() -> pd.DataFrame:
    end = pd.Timestamp(2026, 6, 5, 13, tz="UTC")
    dates = [end - pd.Timedelta(days=24 - i) for i in range(25)]
    return pd.DataFrame(
        {
            "t": dates,
            "o": [100.0] * 25,
            "h": [103.0] * 25,
            "l": [98.0] * 25,
            "c": [100.0] * 25,
            "v": [1_000_000] * 25,
        }
    )


class _FakeBarCache:
    async def get_bars(self, symbol: str, tf: str, start: Any, end: Any) -> pd.DataFrame:
        return _bars()


@pytest_asyncio.fixture
async def tmpl_app() -> AsyncIterator[tuple[AsyncClient, Any, async_sessionmaker]]:
    from app.config import get_settings
    from app.db import models  # noqa: F401
    from app.db.base import Base
    from app.db.models.user import User
    from app.db.session import get_engine, get_sessionmaker
    from app.main import create_app

    get_settings.cache_clear()
    get_engine.cache_clear()
    get_sessionmaker.cache_clear()
    engine = get_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = get_sessionmaker()
    async with factory() as s:
        s.add(User(id=1, email="dev@workbench.local", display_name="Dev"))
        await s.commit()

    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac, app, factory

    await engine.dispose()
    get_engine.cache_clear()
    get_sessionmaker.cache_clear()


async def _strategy(factory, sid):
    from app.db.models.strategy import Strategy as StrategyRow

    async with factory() as s:
        return (
            await s.execute(select(StrategyRow).where(StrategyRow.id == sid))
        ).scalar_one()


async def test_apply_prefills_from_range_insight(tmpl_app) -> None:
    client, app, factory = tmpl_app
    app.state.bar_cache = _FakeBarCache()
    r = await client.post("/api/v1/range-template/apply", json={"symbol": "aapl"})
    assert r.status_code == 200
    body = r.json()
    assert body["authoring_method"] == "template"
    assert body["status"] == "idle"
    assert body["code_path"] == "templates/range_trader.py"
    assert body["symbol"] == "AAPL"
    assert body["prefilled_from_range_insight"] is True

    row = await _strategy(factory, body["id"])
    assert row.symbols_json == ["AAPL"]
    # low_band.high 98 / high_band.low 103 / support 98 − 1.5×ATR(5) = 90.5
    assert row.params_json["entry_price"] == 98.0
    assert row.params_json["exit_price"] == 103.0
    assert row.params_json["stop_price"] == 90.5


async def test_apply_without_bar_cache_uses_static_defaults(tmpl_app) -> None:
    client, app, factory = tmpl_app
    app.state.bar_cache = None
    r = await client.post(
        "/api/v1/range-template/apply", json={"symbol": "MSFT", "name": "My Range"}
    )
    assert r.status_code == 200
    body = r.json()
    assert body["prefilled_from_range_insight"] is False
    assert body["name"] == "My Range"
    row = await _strategy(factory, body["id"])
    assert row.params_json["entry_price"] == 0.0  # static default → inert


async def test_apply_writes_strategy_registered_audit(tmpl_app) -> None:
    from app.db.models.audit_log import AuditLog

    client, app, factory = tmpl_app
    app.state.bar_cache = _FakeBarCache()
    await client.post("/api/v1/range-template/apply", json={"symbol": "AAPL"})
    async with factory() as s:
        rows = (
            await s.execute(
                select(AuditLog).where(AuditLog.action == "STRATEGY_REGISTERED")
            )
        ).scalars().all()
    assert len(rows) == 1
