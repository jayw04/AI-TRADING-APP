"""Tests for ``/api/v1/agent`` (P3 Session 4).

Shared-singleton-DB pattern matching ``test_strategies_endpoint.py``: one
``client_and_factory`` fixture yields the httpx client + the
sessionmaker bound to the same in-memory SQLite the endpoint reaches via
``get_sessionmaker()``. The agent runtime is faked at
``app.state.agent_runtime`` so we exercise the endpoint surface without
talking to Anthropic.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime
from decimal import Decimal

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.db.enums import (
    AgentMessageRole,
    AgentSessionMode,
    AgentSessionStatus,
)
from app.db.models.agent_message import AgentMessage
from app.db.models.agent_session import AgentSession
from app.db.models.user import User


def _now() -> datetime:
    return datetime.now(UTC)


async def _seed(factory: async_sessionmaker) -> None:
    async with factory() as session:
        session.add(User(id=1, email="jay@test", display_name="Jay"))
        await session.commit()


@pytest_asyncio.fixture
async def client_and_factory() -> (
    AsyncIterator[tuple[AsyncClient, async_sessionmaker]]
):
    from app.config import get_settings
    from app.db import models  # noqa: F401 — populate Base.metadata
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

    # Fake AgentRuntime: writes rows directly so the endpoint paths
    # (which re-query after the runtime call) see the right state.
    async def fake_start_session(
        *,
        user_id: int,
        mode: AgentSessionMode,
        model: str | None = None,
    ) -> int:
        async with factory() as db:
            row = AgentSession(
                user_id=user_id,
                mode=mode,
                status=AgentSessionStatus.ACTIVE,
                model=model or "claude-haiku-4-5-20251001",
                total_input_tokens=0,
                total_output_tokens=0,
                total_cost_usd=Decimal("0"),
                daily_budget_usd=Decimal("2.0"),
                started_at=_now(),
            )
            db.add(row)
            await db.commit()
            await db.refresh(row)
            return row.id

    async def fake_append_user_message(
        *, session_id: int, text: str
    ) -> int:
        async with factory() as db:
            db.add(
                AgentMessage(
                    session_id=session_id,
                    role=AgentMessageRole.USER,
                    content_json=[{"type": "text", "text": text}],
                    ts=_now(),
                )
            )
            await db.commit()
        return session_id

    async def fake_end_session(
        *, session_id: int, reason: str = "user_end"
    ) -> None:
        async with factory() as db:
            row = await db.get(AgentSession, session_id)
            if row is None:
                return
            row.status = AgentSessionStatus.ENDED
            row.ended_at = _now()
            row.end_reason = reason
            await db.commit()

    class _FakeRuntime:
        start_session = staticmethod(fake_start_session)
        append_user_message = staticmethod(fake_append_user_message)
        end_session = staticmethod(fake_end_session)

    app.state.agent_runtime = _FakeRuntime()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac, factory

    await engine.dispose()
    get_engine.cache_clear()
    get_sessionmaker.cache_clear()
    get_event_bus.cache_clear()


@pytest_asyncio.fixture
async def client(client_and_factory) -> AsyncClient:
    return client_and_factory[0]


@pytest_asyncio.fixture
async def factory(client_and_factory) -> async_sessionmaker:
    return client_and_factory[1]


# ---------- POST /sessions ----------


async def test_start_session_returns_summary(client) -> None:
    resp = await client.post(
        "/api/v1/agent/sessions", json={"mode": "b2_interactive"}
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "active"
    assert body["mode"] == "b2_interactive"
    assert body["model"] == "claude-haiku-4-5-20251001"
    assert body["message_count"] == 0


async def test_start_session_rejects_b3_with_adr_pointer(client) -> None:
    """B3 rejected at the Pydantic layer with the ADR named."""
    resp = await client.post(
        "/api/v1/agent/sessions", json={"mode": "b3_autonomous"}
    )
    assert resp.status_code == 422
    assert "ADR 0006" in resp.text


async def test_start_session_rejects_extra_field(client) -> None:
    resp = await client.post(
        "/api/v1/agent/sessions",
        json={"mode": "b2_interactive", "fnord": "x"},
    )
    assert resp.status_code == 422


# ---------- GET /sessions ----------


async def test_list_sessions_filtered_by_status(client, factory) -> None:
    async with factory() as db:
        for status in (
            AgentSessionStatus.ACTIVE,
            AgentSessionStatus.ENDED,
            AgentSessionStatus.CAPPED,
        ):
            db.add(
                AgentSession(
                    user_id=1,
                    mode=AgentSessionMode.B2_INTERACTIVE,
                    status=status,
                    model="claude-haiku-4-5-20251001",
                    total_input_tokens=0,
                    total_output_tokens=0,
                    total_cost_usd=Decimal("0"),
                    daily_budget_usd=Decimal("2.0"),
                    started_at=_now(),
                )
            )
        await db.commit()

    resp = await client.get("/api/v1/agent/sessions?status=ended")
    assert resp.status_code == 200
    body = resp.json()
    assert body["count"] == 1
    assert body["items"][0]["status"] == "ended"


async def test_list_sessions_includes_message_count(client) -> None:
    """``message_count`` is computed per query — confirm it lands."""
    # Start a session, append two messages.
    r1 = await client.post(
        "/api/v1/agent/sessions", json={"mode": "b2_interactive"}
    )
    sid = r1.json()["id"]
    for text in ("first", "second"):
        await client.post(
            f"/api/v1/agent/sessions/{sid}/messages", json={"text": text}
        )
    r2 = await client.get("/api/v1/agent/sessions")
    body = r2.json()
    summary = next(s for s in body["items"] if s["id"] == sid)
    assert summary["message_count"] == 2


# ---------- GET /sessions/{id} ----------


async def test_get_session_detail_returns_messages_in_order(client) -> None:
    r1 = await client.post(
        "/api/v1/agent/sessions", json={"mode": "b2_interactive"}
    )
    sid = r1.json()["id"]
    for text in ("alpha", "bravo", "charlie"):
        await client.post(
            f"/api/v1/agent/sessions/{sid}/messages", json={"text": text}
        )

    resp = await client.get(f"/api/v1/agent/sessions/{sid}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["message_count"] == 3
    texts = [m["content"][0]["text"] for m in body["messages"]]
    assert texts == ["alpha", "bravo", "charlie"]


async def test_get_session_404_for_other_user(client, factory) -> None:
    """Sessions owned by another user are not visible."""
    async with factory() as db:
        db.add(User(id=2, email="other@test", display_name="Other"))
        row = AgentSession(
            user_id=2,
            mode=AgentSessionMode.B2_INTERACTIVE,
            status=AgentSessionStatus.ACTIVE,
            model="claude-haiku-4-5-20251001",
            total_input_tokens=0,
            total_output_tokens=0,
            total_cost_usd=Decimal("0"),
            daily_budget_usd=Decimal("2.0"),
            started_at=_now(),
        )
        db.add(row)
        await db.commit()
        await db.refresh(row)
        other_sid = row.id

    resp = await client.get(f"/api/v1/agent/sessions/{other_sid}")
    assert resp.status_code == 404


# ---------- POST /sessions/{id}/messages ----------


async def test_append_message_happy_path(client) -> None:
    r1 = await client.post(
        "/api/v1/agent/sessions", json={"mode": "b2_interactive"}
    )
    sid = r1.json()["id"]
    r2 = await client.post(
        f"/api/v1/agent/sessions/{sid}/messages",
        json={"text": "what is my cash?"},
    )
    assert r2.status_code == 200
    body = r2.json()
    assert body["session_id"] == sid
    assert isinstance(body["user_message_id"], int)


async def test_append_message_to_capped_returns_409(client, factory) -> None:
    async with factory() as db:
        row = AgentSession(
            user_id=1,
            mode=AgentSessionMode.B2_INTERACTIVE,
            status=AgentSessionStatus.CAPPED,
            model="claude-haiku-4-5-20251001",
            total_input_tokens=0,
            total_output_tokens=0,
            total_cost_usd=Decimal("2.0"),
            daily_budget_usd=Decimal("2.0"),
            started_at=_now(),
        )
        db.add(row)
        await db.commit()
        await db.refresh(row)
        sid = row.id

    resp = await client.post(
        f"/api/v1/agent/sessions/{sid}/messages", json={"text": "hi"}
    )
    assert resp.status_code == 409
    assert "capped" in resp.json()["detail"]


async def test_append_message_404_for_other_user(client, factory) -> None:
    async with factory() as db:
        db.add(User(id=2, email="other@test", display_name="Other"))
        row = AgentSession(
            user_id=2,
            mode=AgentSessionMode.B2_INTERACTIVE,
            status=AgentSessionStatus.ACTIVE,
            model="claude-haiku-4-5-20251001",
            total_input_tokens=0,
            total_output_tokens=0,
            total_cost_usd=Decimal("0"),
            daily_budget_usd=Decimal("2.0"),
            started_at=_now(),
        )
        db.add(row)
        await db.commit()
        await db.refresh(row)
        other_sid = row.id

    resp = await client.post(
        f"/api/v1/agent/sessions/{other_sid}/messages",
        json={"text": "intrusion attempt"},
    )
    assert resp.status_code == 404


async def test_append_message_rejects_empty_text(client) -> None:
    r1 = await client.post(
        "/api/v1/agent/sessions", json={"mode": "b2_interactive"}
    )
    sid = r1.json()["id"]
    resp = await client.post(
        f"/api/v1/agent/sessions/{sid}/messages", json={"text": ""}
    )
    assert resp.status_code == 422


# ---------- POST /sessions/{id}/end ----------


async def test_end_session_transitions_to_ended(client) -> None:
    r1 = await client.post(
        "/api/v1/agent/sessions", json={"mode": "b2_interactive"}
    )
    sid = r1.json()["id"]
    r2 = await client.post(
        f"/api/v1/agent/sessions/{sid}/end", json={"reason": "user_end"}
    )
    assert r2.status_code == 200
    body = r2.json()
    assert body["status"] == "ended"
    assert body["end_reason"] == "user_end"


# ---------- GET /budget ----------


async def test_budget_endpoint_zero_initially(client) -> None:
    resp = await client.get("/api/v1/agent/budget")
    assert resp.status_code == 200
    body = resp.json()
    assert Decimal(body["spent_usd"]) == Decimal("0")
    assert Decimal(body["remaining_usd"]) == Decimal(body["budget_usd"])
    assert body["pct_used"] == 0.0


async def test_budget_endpoint_reflects_session_cost(client, factory) -> None:
    """A session with cost should show up in spent / pct_used."""
    async with factory() as db:
        db.add(
            AgentSession(
                user_id=1,
                mode=AgentSessionMode.B2_INTERACTIVE,
                status=AgentSessionStatus.ACTIVE,
                model="claude-haiku-4-5-20251001",
                total_input_tokens=10_000,
                total_output_tokens=2_000,
                total_cost_usd=Decimal("0.50"),
                daily_budget_usd=Decimal("2.0"),
                started_at=_now(),
            )
        )
        await db.commit()

    resp = await client.get("/api/v1/agent/budget")
    body = resp.json()
    assert Decimal(body["spent_usd"]) == Decimal("0.5")
    assert body["pct_used"] == pytest.approx(25.0)
