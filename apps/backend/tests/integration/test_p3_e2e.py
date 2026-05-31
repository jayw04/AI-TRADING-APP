"""End-to-end P3: REST → real runtime → mocked Anthropic → DB rows
(P3 Session 6).

These tests bring the whole agent pipeline together: the FastAPI app, a
real :class:`AgentRuntime`, the session/message ORM, and a mocked
Anthropic call. They verify that a user message hitting
``POST /api/v1/agent/sessions/{id}/messages`` produces the right chain
of rows (USER message, ASSISTANT message with the right content blocks,
``AgentToolInvocation`` rows for any tool_use blocks) and updates the
session totals — and that a subsequent over-budget message returns 409.

If a future change breaks one of the lower layers in isolation
(runtime, schemas, WS gateway), the unit tests in ``tests/agent/`` and
``tests/api/test_agent_endpoints.py`` catch it first. This file's job is
to catch *seam* bugs — wiring that's correct in unit tests but wrong
when the whole pipeline runs together.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.agent.anthropic_client import AnthropicCall
from app.db.enums import AgentMessageRole, AgentSessionStatus
from app.db.models.account import Account, AccountMode
from app.db.models.account_state import AccountState
from app.db.models.agent_message import AgentMessage
from app.db.models.agent_session import AgentSession
from app.db.models.agent_tool_invocation import AgentToolInvocation
from app.db.models.user import User


def _now() -> datetime:
    return datetime.now(UTC)


def _make_call(
    blocks: list[dict],
    in_tok: int = 1500,
    out_tok: int = 300,
) -> AnthropicCall:
    """Build an ``AnthropicCall`` whose raw response mirrors the SDK shape."""
    raw = MagicMock()
    raw.usage.input_tokens = in_tok
    raw.usage.output_tokens = out_tok
    raw.content = []
    for b in blocks:
        m = MagicMock()
        m.type = b["type"]
        if b["type"] == "text":
            m.text = b["text"]
        elif b["type"] == "tool_use":
            m.id = b.get("id", "tu_1")
            m.name = b.get("name", "list_positions")
            m.input = b.get("input", {})
        raw.content.append(m)
    raw.stop_reason = "end_turn"
    return AnthropicCall(raw_response=raw)


async def _seed(factory: async_sessionmaker) -> None:
    async with factory() as db:
        db.add(User(id=1, email="jay@test", display_name="Jay"))
        db.add(
            Account(
                id=1, user_id=1, broker="alpaca",
                mode=AccountMode.paper, label="Paper",
            )
        )
        db.add(
            AccountState(
                account_id=1,
                cash=Decimal("50000"),
                equity=Decimal("100000"),
                last_equity=Decimal("100000"),
                buying_power=Decimal("100000"),
                portfolio_value=Decimal("100000"),
                day_change=Decimal("0"),
                day_change_pct=Decimal("0"),
                status="ACTIVE",
                raw_payload={},
                updated_at=_now(),
            )
        )
        await db.commit()
    # P5 §4: the agent reads its Anthropic key from the credential store.
    async with factory() as db:
        from app.security import CredentialKind, CredentialStore

        await CredentialStore(db).set(
            1, CredentialKind.ANTHROPIC_API_KEY, "sk-test"
        )


@pytest_asyncio.fixture
async def wired_app() -> AsyncIterator[
    tuple[AsyncClient, async_sessionmaker, MagicMock]
]:
    """A FastAPI app with a real ``AgentRuntime`` and seeded DB.

    Settings are a MagicMock so individual tests can override the daily
    budget. The Anthropic ``create_message`` is *not* patched at the
    fixture level — each test patches it with the response shape it
    wants for that scenario.
    """
    from app.agent.runtime import AgentRuntime
    from app.config import get_settings
    from app.db import models  # noqa: F401 — populate Base.metadata
    from app.db.base import Base
    from app.db.session import get_engine, get_sessionmaker
    from app.events.bus import EventBus, get_event_bus
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

    settings = MagicMock()
    settings.anthropic_api_key = "sk-test"
    settings.agent_default_model = "claude-haiku-4-5-20251001"
    settings.agent_daily_budget_usd = 2.0

    bus = EventBus()
    runtime = AgentRuntime(settings, factory, bus, mcp_server_url=None)

    app = create_app()
    app.state.agent_runtime = runtime

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac, factory, settings

    await engine.dispose()
    get_engine.cache_clear()
    get_sessionmaker.cache_clear()
    get_event_bus.cache_clear()


async def test_full_agent_conversation_e2e(wired_app) -> None:
    """User message → assistant turn with tool_use AND text → all rows persisted."""
    client, factory, _settings = wired_app

    # Assistant response bundles a tool_use call AND a final text summary in
    # one turn (Anthropic's MCP connector resolves tool_use server-side and
    # threads the result back into the same response).
    call = _make_call(
        [
            {
                "type": "tool_use",
                "id": "tu_account",
                "name": "get_account_state",
                "input": {},
            },
            {"type": "text", "text": "Your cash balance is $50,000."},
        ]
    )

    with patch("app.agent.runtime.create_message", new=AsyncMock(return_value=call)):
        r_start = await client.post(
            "/api/v1/agent/sessions", json={"mode": "b2_interactive"}
        )
        assert r_start.status_code == 200, r_start.text
        sid = r_start.json()["id"]

        r_msg = await client.post(
            f"/api/v1/agent/sessions/{sid}/messages",
            json={"text": "what's my cash?"},
        )
        assert r_msg.status_code == 200, r_msg.text
        assert r_msg.json()["session_id"] == sid
        assert isinstance(r_msg.json()["user_message_id"], int)

    # Verify the chain of rows the runtime wrote.
    async with factory() as db:
        rows = (
            await db.execute(
                select(AgentMessage)
                .where(AgentMessage.session_id == sid)
                .order_by(AgentMessage.ts)
            )
        ).scalars().all()
        assert [r.role for r in rows] == [
            AgentMessageRole.USER,
            AgentMessageRole.ASSISTANT,
        ]
        assistant_blocks = rows[1].content_json
        types = {b["type"] for b in assistant_blocks}
        assert {"tool_use", "text"}.issubset(types)
        text_block = next(b for b in assistant_blocks if b["type"] == "text")
        assert "$50,000" in text_block["text"]

        invs = (
            await db.execute(
                select(AgentToolInvocation).where(
                    AgentToolInvocation.session_id == sid
                )
            )
        ).scalars().all()
        assert len(invs) == 1
        assert invs[0].tool_name == "get_account_state"
        # MCP tool dispatch is server-side at Anthropic; the runtime never
        # sees the tool result, so output_json is intentionally None.
        assert invs[0].output_json is None

        session_row = await db.get(AgentSession, sid)
        assert session_row is not None
        assert session_row.status == AgentSessionStatus.ACTIVE
        assert session_row.total_input_tokens == 1500
        assert session_row.total_output_tokens == 300
        assert session_row.total_cost_usd > Decimal("0")

    # The detail endpoint should also see the conversation through the API.
    r_detail = await client.get(f"/api/v1/agent/sessions/{sid}")
    assert r_detail.status_code == 200
    detail = r_detail.json()
    assert detail["message_count"] == 2
    assert detail["messages"][1]["role"] == "assistant"
    assert any(
        b.get("type") == "tool_use" for b in detail["messages"][1]["content"]
    )


async def test_full_e2e_cap_path_returns_409(wired_app) -> None:
    """Bilateral cost cap exercised at the REST seam.

    Budget tuned so first call passes the pre-call gate and the second
    call's pre-call gate refuses (see also test_runtime.py).
    """
    client, factory, settings = wired_app
    settings.agent_daily_budget_usd = 0.010

    call = _make_call(
        [{"type": "text", "text": "first answer"}],
        in_tok=2000,
        out_tok=500,
    )

    with patch(
        "app.agent.runtime.create_message", new=AsyncMock(return_value=call)
    ):
        r_start = await client.post(
            "/api/v1/agent/sessions", json={"mode": "b2_interactive"}
        )
        sid = r_start.json()["id"]

        # First message lands; sets session.total_cost_usd ≈ $0.0036.
        r1 = await client.post(
            f"/api/v1/agent/sessions/{sid}/messages",
            json={"text": "first"},
        )
        assert r1.status_code == 200

        # Second message's pre-call gate fires: 0.0036 + 0.0072 = 0.0108 > 0.010.
        # The runtime transitions the session to CAPPED and the endpoint
        # sees a non-ACTIVE session on the immediate re-query, but we have
        # to attempt the POST to actually trigger the transition.
        r2 = await client.post(
            f"/api/v1/agent/sessions/{sid}/messages",
            json={"text": "second"},
        )
        # After the second POST the session is CAPPED, so the THIRD attempt
        # gets the clean 409. The second POST itself returns 200 because
        # the user message was persisted before the cap fired.
        assert r2.status_code == 200

        r3 = await client.post(
            f"/api/v1/agent/sessions/{sid}/messages",
            json={"text": "third"},
        )
        assert r3.status_code == 409
        assert "capped" in r3.json()["detail"]

    async with factory() as db:
        session_row = await db.get(AgentSession, sid)
        assert session_row is not None
        assert session_row.status == AgentSessionStatus.CAPPED
