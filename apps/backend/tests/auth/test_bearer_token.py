"""P5.5 §3 — workbench-mcp bearer-token auth on get_current_user.

These opt out of the conftest autouse auth override (``@pytest.mark.real_auth``)
so the real ``get_current_user`` + ``_resolve_from_bearer_token`` run.
"""

from __future__ import annotations

import os

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from app.db.base import Base
from app.db.models.audit_log import AuditLog
from app.db.models.user import User
from app.db.session import get_engine, get_sessionmaker
from app.security.credential_store import CredentialKind, CredentialStore

PROFILE_URL = "/api/v1/users/me/trading-profile"
MCP_KEY = "wbm-secret-key-123"


@pytest.fixture
async def app_factory():
    os.environ["WORKBENCH_ALPACA_STARTUP_ENABLED"] = "0"
    from app.db import models  # noqa: F401 - register models on Base.metadata

    get_engine.cache_clear()
    get_sessionmaker.cache_clear()
    engine = get_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async with get_sessionmaker()() as s:
        s.add(User(id=1, email="jay@test"))
        await s.commit()
        await CredentialStore(s).set(1, CredentialKind.WORKBENCH_MCP_KEY, MCP_KEY)

    clients: list[AsyncClient] = []

    async def _build() -> AsyncClient:
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


def _bearer(key: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {key}"}


@pytest.mark.asyncio
@pytest.mark.real_auth
async def test_valid_mcp_key_authenticates(app_factory):
    ac = await app_factory()
    r = await ac.get(PROFILE_URL, headers=_bearer(MCP_KEY))
    assert r.status_code == 200
    assert r.json()["user_id"] == 1


@pytest.mark.asyncio
@pytest.mark.real_auth
async def test_invalid_mcp_key_returns_401(app_factory):
    ac = await app_factory()
    assert (await ac.get(PROFILE_URL, headers=_bearer("wrong"))).status_code == 401


@pytest.mark.asyncio
@pytest.mark.real_auth
async def test_revoked_mcp_key_returns_401(app_factory):
    ac = await app_factory()
    async with get_sessionmaker()() as s:
        await CredentialStore(s).revoke(1, CredentialKind.WORKBENCH_MCP_KEY)
    assert (await ac.get(PROFILE_URL, headers=_bearer(MCP_KEY))).status_code == 401


@pytest.mark.asyncio
@pytest.mark.real_auth
async def test_no_credentials_no_auth_returns_401(app_factory):
    ac = await app_factory()
    assert (await ac.get(PROFILE_URL)).status_code == 401


@pytest.mark.asyncio
@pytest.mark.real_auth
async def test_mcp_triggered_brief_audits_as_user(app_factory):
    """MCP user → manual trigger → audit row actor_type=USER (correction #5)."""
    ac = await app_factory()
    r = await ac.post("/api/v1/morning-brief/generate", headers=_bearer(MCP_KEY))
    assert r.status_code == 200
    async with get_sessionmaker()() as s:
        rows = (
            await s.execute(
                select(AuditLog).where(AuditLog.action == "MORNING_BRIEF_GENERATED")
            )
        ).scalars().all()
    assert len(rows) == 1
    assert rows[0].actor_type == "user"


@pytest.mark.asyncio
async def test_cookie_override_path_unaffected(app_factory):
    """WITHOUT real_auth: the conftest override authenticates as user 1 — proves
    adding the bearer Header param didn't break the existing dependency."""
    ac = await app_factory()
    assert (await ac.get(PROFILE_URL)).status_code == 200
