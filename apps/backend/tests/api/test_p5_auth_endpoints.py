"""/api/v1/auth/* endpoint tests (P5 §3).

Marked ``real_auth`` so the autouse get_current_user override in conftest is
skipped — these tests drive the real cookie/session/TOTP flow. Seeding goes
through the production engine the client reaches (get_engine/get_sessionmaker),
the same pattern as tests/api/test_p5_accounts.py.
"""

from __future__ import annotations

import asyncio
import os
from datetime import UTC, datetime

import pyotp
import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from app.api.v1.auth import _reset_rate_limit_for_tests
from app.auth.passwords import hash_password
from app.auth.totp import generate_secret
from app.db.base import Base
from app.db.models.session import Session as SessionRow
from app.db.models.user import User
from app.db.session import get_engine, get_sessionmaker

pytestmark = pytest.mark.real_auth


def _now() -> datetime:
    return datetime.now(UTC)


@pytest.fixture(autouse=True)
def _reset_rate_limit():
    _reset_rate_limit_for_tests()
    yield
    _reset_rate_limit_for_tests()


@pytest_asyncio.fixture
async def secret() -> str:
    """Build a fresh DB, seed user id=1 with verified TOTP, yield the secret."""
    os.environ["WORKBENCH_ALPACA_STARTUP_ENABLED"] = "0"
    from app.db import models  # noqa: F401 - register models on Base.metadata

    get_engine.cache_clear()
    get_sessionmaker.cache_clear()

    engine = get_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    totp_secret = generate_secret()
    async with get_sessionmaker()() as session:
        session.add(
            User(
                id=1,
                email="jay@example.com",
                display_name="Jay",
                password_hash=hash_password("correctpw"),
                totp_verified_at=_now(),
            )
        )
        await session.commit()
    # P5 §4: the TOTP secret lives in the encrypted credential store.
    from app.security import CredentialKind, CredentialStore

    async with get_sessionmaker()() as session:
        await CredentialStore(session).set(
            1, CredentialKind.TOTP_SECRET, totp_secret
        )
    try:
        yield totp_secret
    finally:
        await engine.dispose()
        get_engine.cache_clear()
        get_sessionmaker.cache_clear()


@pytest_asyncio.fixture
async def client(secret: str) -> AsyncClient:
    from app.main import create_app

    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


async def test_login_happy_path(client: AsyncClient, secret: str):
    code = pyotp.TOTP(secret).now()
    r = await client.post(
        "/api/v1/auth/login",
        json={"email": "jay@example.com", "password": "correctpw", "totp_code": code},
    )
    assert r.status_code == 200
    assert r.cookies.get("workbench_session") is not None
    assert r.json()["user_id"] == 1

    async with get_sessionmaker()() as session:
        rows = (await session.execute(select(SessionRow))).scalars().all()
    assert len(rows) == 1
    assert rows[0].user_id == 1
    assert rows[0].revoked_at is None


async def test_login_wrong_password_returns_401(client: AsyncClient, secret: str):
    code = pyotp.TOTP(secret).now()
    r = await client.post(
        "/api/v1/auth/login",
        json={"email": "jay@example.com", "password": "wrongpw", "totp_code": code},
    )
    assert r.status_code == 401


async def test_login_wrong_totp_returns_401(client: AsyncClient, secret: str):
    r = await client.post(
        "/api/v1/auth/login",
        json={"email": "jay@example.com", "password": "correctpw", "totp_code": "000000"},
    )
    assert r.status_code == 401


async def test_login_unknown_email_returns_401(client: AsyncClient, secret: str):
    r = await client.post(
        "/api/v1/auth/login",
        json={"email": "ghost@example.com", "password": "anything", "totp_code": "123456"},
    )
    assert r.status_code == 401


async def test_login_rate_limit_kicks_in(client: AsyncClient, secret: str):
    """5 bad attempts → the 6th is 429 even with correct credentials."""
    for _ in range(5):
        await client.post(
            "/api/v1/auth/login",
            json={"email": "jay@example.com", "password": "wrongpw", "totp_code": "000000"},
        )
    r = await client.post(
        "/api/v1/auth/login",
        json={
            "email": "jay@example.com",
            "password": "correctpw",
            "totp_code": pyotp.TOTP(secret).now(),
        },
    )
    assert r.status_code == 429


async def test_me_requires_session(client: AsyncClient, secret: str):
    r = await client.get("/api/v1/auth/me")
    assert r.status_code == 401


async def test_me_returns_user_when_logged_in(client: AsyncClient, secret: str):
    code = pyotp.TOTP(secret).now()
    login = await client.post(
        "/api/v1/auth/login",
        json={"email": "jay@example.com", "password": "correctpw", "totp_code": code},
    )
    cookie = login.cookies.get("workbench_session")
    r = await client.get("/api/v1/auth/me", cookies={"workbench_session": cookie})
    assert r.status_code == 200
    assert r.json()["user_id"] == 1


async def test_logout_revokes_session(client: AsyncClient, secret: str):
    code = pyotp.TOTP(secret).now()
    login = await client.post(
        "/api/v1/auth/login",
        json={"email": "jay@example.com", "password": "correctpw", "totp_code": code},
    )
    cookie = login.cookies.get("workbench_session")

    r = await client.post("/api/v1/auth/logout", cookies={"workbench_session": cookie})
    assert r.status_code == 200

    async with get_sessionmaker()() as session:
        rows = (await session.execute(select(SessionRow))).scalars().all()
    assert all(row.revoked_at is not None for row in rows)

    r2 = await client.get("/api/v1/auth/me", cookies={"workbench_session": cookie})
    assert r2.status_code == 401


async def test_session_rolls_last_used_at_on_request(client: AsyncClient, secret: str):
    code = pyotp.TOTP(secret).now()
    login = await client.post(
        "/api/v1/auth/login",
        json={"email": "jay@example.com", "password": "correctpw", "totp_code": code},
    )
    cookie = login.cookies.get("workbench_session")

    async with get_sessionmaker()() as session:
        old_last_used = (await session.execute(select(SessionRow))).scalars().first().last_used_at

    await asyncio.sleep(0.01)
    await client.get("/api/v1/auth/me", cookies={"workbench_session": cookie})

    async with get_sessionmaker()() as session:
        new_last_used = (await session.execute(select(SessionRow))).scalars().first().last_used_at
    assert new_last_used > old_last_used


async def test_revoke_session_endpoint(client: AsyncClient, secret: str):
    code = pyotp.TOTP(secret).now()
    login = await client.post(
        "/api/v1/auth/login",
        json={"email": "jay@example.com", "password": "correctpw", "totp_code": code},
    )
    cookie = login.cookies.get("workbench_session")
    me = await client.get("/api/v1/auth/me", cookies={"workbench_session": cookie})
    session_id = me.json()["session_id"]

    r = await client.post(
        f"/api/v1/auth/sessions/{session_id}/revoke",
        cookies={"workbench_session": cookie},
    )
    assert r.status_code == 200

    r2 = await client.get("/api/v1/auth/me", cookies={"workbench_session": cookie})
    assert r2.status_code == 401


async def test_login_no_totp_setup_returns_403(client: AsyncClient, secret: str):
    """A user without verified TOTP cannot log in even with a correct password."""
    async with get_sessionmaker()() as session:
        session.add(
            User(
                id=2,
                email="nototp@example.com",
                password_hash=hash_password("pw2"),
                totp_verified_at=None,
            )
        )
        await session.commit()
    r = await client.post(
        "/api/v1/auth/login",
        json={"email": "nototp@example.com", "password": "pw2", "totp_code": "000000"},
    )
    assert r.status_code == 403
