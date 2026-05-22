"""Smoke test for the WS gateway's topic-wrapping + heartbeat forwarding.

After P1 Session 6, every WS message is wrapped: ``{topic, type, payload, ts}``.
On connect the gateway auto-subscribes the client to the ``system`` WS topic
and pushes ``system.connected`` immediately; ``system.heartbeat`` events
follow on the same topic.
"""

import os

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def fast_heartbeat_app(monkeypatch: pytest.MonkeyPatch):
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

    app = create_app()
    try:
        yield app
    finally:
        get_settings.cache_clear()
        db_session.get_engine.cache_clear()
        db_session.get_sessionmaker.cache_clear()
        event_bus.reset_event_bus()
        ws_replay.reset_replay_buffer()
        os.environ.pop("WORKBENCH_WS_HEARTBEAT_SECONDS", None)


def test_ws_emits_connected_and_heartbeat(fast_heartbeat_app) -> None:
    with TestClient(fast_heartbeat_app) as client, client.websocket_connect("/ws") as ws:
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
