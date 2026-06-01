"""P5 §1 — /api/v1/accounts endpoint + BrokerMode invariants.

Seeds through the production engine the client reaches (get_sessionmaker), the
same pattern as test_orders_endpoint.py. The accounts endpoints need no order
router, so none is installed on app.state.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from httpx import ASGITransport, AsyncClient

from app.db.base import Base
from app.db.models.account import Account, AccountMode
from app.db.models.user import User
from app.db.session import get_engine, get_sessionmaker


def _now() -> datetime:
    return datetime.now(UTC)


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


@pytest.mark.asyncio
async def test_list_returns_empty_for_new_user(client_factory):
    client = await client_factory(_seed_user)
    r = await client.get("/api/v1/accounts")
    assert r.status_code == 200
    assert r.json()["count"] == 0


@pytest.mark.asyncio
async def test_create_paper_account(client_factory):
    client = await client_factory(_seed_user)
    r = await client.post(
        "/api/v1/accounts",
        json={"broker": "alpaca", "mode": "paper", "label": "My Paper"},
    )
    assert r.status_code == 201
    body = r.json()
    assert body["mode"] == "paper"
    assert body["broker"] == "alpaca"
    assert body["broker_mode_locked_at"] is None

    async with get_sessionmaker()() as session:
        row = await session.get(Account, body["id"])
    assert row is not None
    assert row.mode == AccountMode.paper


@pytest.mark.asyncio
async def test_create_live_account_requires_totp(client_factory):
    """P5 §7: live account creation is permitted but requires a TOTP code.
    Without one, the request is rejected with 400."""
    client = await client_factory(_seed_user)
    r = await client.post(
        "/api/v1/accounts",
        json={"broker": "alpaca", "mode": "live", "label": "My Live"},
    )
    assert r.status_code == 400
    assert "totp_code" in r.json()["detail"]


@pytest.mark.asyncio
async def test_duplicate_paper_account_rejected(client_factory):
    async def seed(session):
        await _seed_user(session)
        session.add(
            Account(
                user_id=1, broker="alpaca", mode=AccountMode.paper,
                label="First", created_at=_now(),
            )
        )

    client = await client_factory(seed)
    r = await client.post(
        "/api/v1/accounts",
        json={"broker": "alpaca", "mode": "paper", "label": "Second"},
    )
    assert r.status_code == 409


@pytest.mark.asyncio
async def test_list_exposes_broker_mode_locked_at(client_factory):
    locked_at = _now()

    async def seed(session):
        await _seed_user(session)
        session.add(
            Account(
                user_id=1, broker="alpaca", mode=AccountMode.paper, label="paper-x",
                broker_mode_locked_at=None, created_at=_now(),
            )
        )
        session.add(
            Account(
                user_id=1, broker="ibkr", mode=AccountMode.live, label="live-x",
                broker_mode_locked_at=locked_at, created_at=_now(),
            )
        )

    client = await client_factory(seed)
    r = await client.get("/api/v1/accounts")
    body = r.json()
    paper = next(a for a in body["items"] if a["mode"] == "paper")
    live = next(a for a in body["items"] if a["mode"] == "live")
    assert paper["broker_mode_locked_at"] is None
    assert live["broker_mode_locked_at"] is not None


@pytest.mark.asyncio
async def test_extra_fields_rejected_on_create(client_factory):
    client = await client_factory(_seed_user)
    r = await client.post(
        "/api/v1/accounts",
        json={"broker": "alpaca", "mode": "paper", "label": "x", "fnord": 1},
    )
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_invalid_mode_rejected_on_create(client_factory):
    client = await client_factory(_seed_user)
    r = await client.post(
        "/api/v1/accounts",
        json={"broker": "alpaca", "mode": "demo", "label": "x"},
    )
    assert r.status_code == 422
