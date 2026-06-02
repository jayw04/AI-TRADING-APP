"""P5.5 §2 — /api/v1/morning-brief endpoints.

Seeds through the production engine the client reaches (same pattern as
test_p5_accounts / test_trading_profile_endpoint). bar_cache/indicator_computer
are absent on app.state under the test app (alpaca disabled), so observations
come back empty/neutral — fine for exercising the HTTP surface.
"""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from app.db.base import Base
from app.db.models.user import User
from app.db.session import get_engine, get_sessionmaker

BASE = "/api/v1/morning-brief"


@pytest.fixture
async def client_factory():
    import os

    os.environ["WORKBENCH_ALPACA_STARTUP_ENABLED"] = "0"
    from app.db import models  # noqa: F401 - register models on Base.metadata

    get_engine.cache_clear()
    get_sessionmaker.cache_clear()
    engine = get_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    clients: list[AsyncClient] = []

    async def _build(seed=None) -> AsyncClient:
        if seed is not None:
            async with get_sessionmaker()() as session:
                await seed(session)
                await session.commit()
        from app.main import create_app

        ac = AsyncClient(transport=ASGITransport(app=create_app()), base_url="http://test")
        clients.append(ac)
        return ac

    try:
        yield _build
    finally:
        for ac in clients:
            await ac.aclose()
        await engine.dispose()
        get_engine.cache_clear()
        get_sessionmaker.cache_clear()


async def _seed_user(session) -> None:
    session.add(User(id=1, email="jay@test", display_name="Jay"))


@pytest.mark.asyncio
async def test_today_returns_null_before_generation(client_factory):
    ac = await client_factory(_seed_user)
    resp = await ac.get(f"{BASE}/today")
    assert resp.status_code == 200
    assert resp.json() is None


@pytest.mark.asyncio
async def test_generate_then_today_returns_brief(client_factory):
    ac = await client_factory(_seed_user)
    gen = await ac.post(f"{BASE}/generate")
    assert gen.status_code == 200
    body = gen.json()
    assert body["user_id"] == 1
    assert body["trigger"] == "manual"
    assert body["agent_used"] is False
    today = await ac.get(f"{BASE}/today")
    assert today.status_code == 200
    assert today.json()["brief_date"] == body["brief_date"]


@pytest.mark.asyncio
async def test_recent_limit_validation(client_factory):
    ac = await client_factory(_seed_user)
    assert (await ac.get(f"{BASE}/recent?limit=0")).status_code == 400
    assert (await ac.get(f"{BASE}/recent?limit=31")).status_code == 400
    ok = await ac.get(f"{BASE}/recent?limit=5")
    assert ok.status_code == 200
    assert ok.json() == []


@pytest.mark.asyncio
async def test_route_mounted_at_correct_path(client_factory):
    ac = await client_factory(_seed_user)
    assert (await ac.get(f"{BASE}/today")).status_code == 200
    assert (await ac.get("/api/v1/api/v1/morning-brief/today")).status_code == 404


@pytest.mark.asyncio
@pytest.mark.real_auth
async def test_endpoints_require_auth(client_factory):
    ac = await client_factory(_seed_user)
    assert (await ac.get(f"{BASE}/today")).status_code == 401
    assert (await ac.post(f"{BASE}/generate")).status_code == 401
