"""P5.5 §3 — GET /api/v1/audit (read-only, user-scoped)."""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from app.db.base import Base
from app.db.models.user import User
from app.db.session import get_engine, get_sessionmaker
from app.services.trading_profile import TradingProfileService

AUDIT_URL = "/api/v1/audit"


@pytest.fixture
async def client_factory():
    import os

    os.environ["WORKBENCH_ALPACA_STARTUP_ENABLED"] = "0"
    from app.db import models  # noqa: F401

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


async def _seed_users(session) -> None:
    session.add(User(id=1, email="jay@test"))
    session.add(User(id=2, email="other@test"))


@pytest.mark.asyncio
async def test_audit_returns_current_user_entries_newest_first(client_factory):
    ac = await client_factory(_seed_users)
    # Two profile edits → two TRADING_PROFILE_UPDATED rows for user 1.
    await ac.put(AUDIT_URL.replace("/audit", "/users/me/trading-profile"), json={"watchlist": {"core": ["A"]}})
    await ac.put(AUDIT_URL.replace("/audit", "/users/me/trading-profile"), json={"watchlist": {"core": ["B"]}})
    resp = await ac.get(AUDIT_URL)
    assert resp.status_code == 200
    body = resp.json()
    assert body["count"] == 2
    assert all(it["action"] == "TRADING_PROFILE_UPDATED" for it in body["items"])
    # Newest first (descending id).
    assert body["items"][0]["id"] > body["items"][1]["id"]
    # Integrity internals are NOT exposed.
    assert "row_hash" not in body["items"][0]


@pytest.mark.asyncio
async def test_audit_user_isolation(client_factory):
    ac = await client_factory(_seed_users)
    # Write an audit row for user 2 directly; user 1 (the auth'd user) must not see it.
    async with get_sessionmaker()() as session:
        await TradingProfileService(session).update(
            2, changes={"watchlist_json": {"core": ["TSLA"]}}, actor_user_id=2
        )
    resp = await ac.get(AUDIT_URL)
    assert resp.status_code == 200
    assert resp.json()["count"] == 0  # user 1 has no audit rows


@pytest.mark.asyncio
async def test_audit_limit_validation(client_factory):
    ac = await client_factory(_seed_users)
    assert (await ac.get(f"{AUDIT_URL}?limit=0")).status_code == 422
    assert (await ac.get(f"{AUDIT_URL}?limit=201")).status_code == 422
    assert (await ac.get(f"{AUDIT_URL}?limit=10")).status_code == 200


@pytest.mark.asyncio
@pytest.mark.real_auth
async def test_audit_requires_auth(client_factory):
    ac = await client_factory(_seed_users)
    assert (await ac.get(AUDIT_URL)).status_code == 401
