"""Smoke test for the WS gateway's topic-wrapping + heartbeat forwarding.

After P1 Session 6, every WS message is wrapped: ``{topic, type, payload, ts}``.
On connect the gateway auto-subscribes the client to the ``system`` WS topic
and pushes ``system.connected`` immediately; ``system.heartbeat`` events
follow on the same topic.

P5 §3: the WS upgrade now requires a valid session cookie. We seed a user +
session row into a file-backed SQLite (shared across the TestClient's portal
loop, unlike ``:memory:``) and connect with the matching cookie. The
unauthenticated-rejection path (close 4401) is covered separately.
"""

import asyncio
import os
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.auth.tokens import generate_session_token, hash_session_token


async def _seed(url: str, token: str) -> None:
    from app.db import models  # noqa: F401 - register models on Base.metadata
    from app.db.base import Base
    from app.db.models.session import Session as SessionRow
    from app.db.models.user import User

    engine = create_async_engine(url)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    sm = async_sessionmaker(engine, expire_on_commit=False)
    now = datetime.now(UTC)
    async with sm() as session:
        session.add(User(id=1, email="ws@test.local", display_name="WS"))
        session.add(
            SessionRow(
                user_id=1,
                token_hash=hash_session_token(token),
                created_at=now,
                last_used_at=now,
                expires_at=now + timedelta(days=1),
            )
        )
        await session.commit()
    await engine.dispose()


@pytest.fixture
def ws_app(monkeypatch: pytest.MonkeyPatch, tmp_path):
    db_file = tmp_path / "ws.sqlite"
    monkeypatch.setenv("WORKBENCH_DB_URL", f"sqlite+aiosqlite:///{db_file.as_posix()}")
    monkeypatch.setenv("WORKBENCH_WS_HEARTBEAT_SECONDS", "0.1")

    from app.config import get_settings
    from app.db import session as db_session
    from app.events import bus as event_bus
    from app.main import create_app
    from app.ws import replay as ws_replay

    get_settings.cache_clear()
    db_session.get_engine.cache_clear()
    db_session.get_sessionmaker.cache_clear()
    event_bus.reset_event_bus()
    ws_replay.reset_replay_buffer()

    token = generate_session_token()
    asyncio.run(_seed(f"sqlite+aiosqlite:///{db_file.as_posix()}", token))

    app = create_app()
    try:
        yield app, token
    finally:
        get_settings.cache_clear()
        db_session.get_engine.cache_clear()
        db_session.get_sessionmaker.cache_clear()
        event_bus.reset_event_bus()
        ws_replay.reset_replay_buffer()
        os.environ.pop("WORKBENCH_WS_HEARTBEAT_SECONDS", None)


def test_ws_emits_connected_and_heartbeat(ws_app) -> None:
    app, token = ws_app
    client = TestClient(app)
    client.cookies.set("workbench_session", token)
    with client, client.websocket_connect("/ws") as ws:
        connected = ws.receive_json()
        assert connected["topic"] == "system"
        assert connected["type"] == "system.connected"
        assert "ts" in connected
        assert "server_version" in connected["payload"]

        saw_heartbeat = False
        for _ in range(50):
            msg = ws.receive_json()
            if msg.get("type") == "system.heartbeat":
                assert msg["topic"] == "system"
                assert "ts" in msg
                saw_heartbeat = True
                break
        assert saw_heartbeat, "did not receive a system.heartbeat within 50 messages"


def test_ws_rejects_without_cookie(ws_app) -> None:
    """No session cookie → the gateway closes with application code 4401."""
    from starlette.websockets import WebSocketDisconnect

    app, _token = ws_app
    client = TestClient(app)
    with (
        client,
        pytest.raises(WebSocketDisconnect) as exc,
        client.websocket_connect("/ws") as ws,
    ):
        ws.receive_json()
    assert exc.value.code == 4401
