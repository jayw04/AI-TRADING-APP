"""P5.5 §1 — /api/v1/users/me/trading-profile endpoints.

Seeds through the production engine the client reaches (get_sessionmaker), the
same pattern as test_p5_accounts.py. Auth is transparently overridden to
User(id=1) by the autouse conftest fixture; the requires-auth test opts out via
the ``real_auth`` marker.
"""

from __future__ import annotations

import json

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from app.db.base import Base
from app.db.models.audit_log import AuditLog
from app.db.models.user import User
from app.db.session import get_engine, get_sessionmaker

PROFILE_URL = "/api/v1/users/me/trading-profile"


@pytest.fixture
async def client_factory():
    """Yields a builder: seed(session) -> AsyncClient against a fresh DB."""
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

        app = create_app()
        transport = ASGITransport(app=app)
        ac = AsyncClient(transport=transport, base_url="http://test")
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


async def _audit_count(session_maker) -> int:
    async with session_maker()() as session:
        rows = (await session.execute(select(AuditLog))).scalars().all()
        return len(rows)


@pytest.mark.asyncio
async def test_get_endpoint_returns_profile(client_factory):
    ac = await client_factory(_seed_user)
    resp = await ac.get(PROFILE_URL)
    assert resp.status_code == 200
    body = resp.json()
    assert body["user_id"] == 1
    assert body["watchlist"] == {}
    assert body["bias_thresholds"] == {}
    # Response model omits created_at/updated_at.
    assert "created_at" not in body
    assert "updated_at" not in body


@pytest.mark.asyncio
async def test_route_mounted_at_correct_path(client_factory):
    """GET resolves at /api/v1/users/me/trading-profile — not a double-prefixed
    404 (catches the 'mounted in main.py with prefix=/api/v1' drift)."""
    ac = await client_factory(_seed_user)
    assert (await ac.get(PROFILE_URL)).status_code == 200
    assert (await ac.get("/api/v1/api/v1/users/me/trading-profile")).status_code == 404


@pytest.mark.asyncio
@pytest.mark.real_auth
async def test_get_endpoint_requires_auth(client_factory):
    ac = await client_factory(_seed_user)  # no override → real get_current_user
    resp = await ac.get(PROFILE_URL)
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_put_endpoint_updates_watchlist(client_factory):
    ac = await client_factory(_seed_user)
    resp = await ac.put(
        PROFILE_URL,
        json={"watchlist": {"core": ["AAPL", "MSFT"], "do_not_trade": ["GME"]}},
    )
    assert resp.status_code == 200
    assert resp.json()["watchlist"] == {
        "core": ["AAPL", "MSFT"],
        "do_not_trade": ["GME"],
    }
    # Persisted across a fresh GET.
    assert (await ac.get(PROFILE_URL)).json()["watchlist"]["core"] == ["AAPL", "MSFT"]


@pytest.mark.asyncio
async def test_put_endpoint_extra_fields_rejected(client_factory):
    ac = await client_factory(_seed_user)
    resp = await ac.put(PROFILE_URL, json={"not_a_section": {"x": 1}})
    assert resp.status_code == 422  # ConfigDict(extra="forbid")


@pytest.mark.asyncio
async def test_put_endpoint_no_op_returns_current(client_factory):
    ac = await client_factory(_seed_user)
    resp = await ac.put(PROFILE_URL, json={})
    assert resp.status_code == 200
    assert resp.json()["watchlist"] == {}
    # Empty body wrote no audit row.
    assert await _audit_count(get_sessionmaker) == 0


@pytest.mark.asyncio
async def test_put_endpoint_audit_recorded(client_factory):
    ac = await client_factory(_seed_user)
    await ac.put(PROFILE_URL, json={"bias_thresholds": {"bullish": {"rsi_min": 50}}})
    async with get_sessionmaker()() as session:
        rows = (await session.execute(select(AuditLog))).scalars().all()
    assert len(rows) == 1
    assert rows[0].action == "TRADING_PROFILE_UPDATED"
    payload = json.loads(rows[0].payload_json)
    assert payload["changes"]["new"]["bias_thresholds_json"] == {
        "bullish": {"rsi_min": 50}
    }


@pytest.mark.asyncio
async def test_get_endpoint_returns_only_my_profile(client_factory):
    """The endpoint is /users/me and auth pins to user 1, so another user's
    data is never addressable here."""

    async def seed(session) -> None:
        session.add(User(id=1, email="jay@test", display_name="Jay"))
        session.add(User(id=2, email="other@test"))

    ac = await client_factory(seed)
    # Give user 2 a populated profile directly.
    from app.services.trading_profile import TradingProfileService

    async with get_sessionmaker()() as session:
        await TradingProfileService(session).update(
            2, changes={"watchlist_json": {"core": ["TSLA"]}}, actor_user_id=2
        )
    body = (await ac.get(PROFILE_URL)).json()
    assert body["user_id"] == 1
    assert body["watchlist"] == {}  # user 1's, not user 2's TSLA
