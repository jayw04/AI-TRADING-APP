"""AgentRuntime tests against a mocked Anthropic API (P3 Session 3)."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy import select

from app.agent.anthropic_client import AnthropicCall, AnthropicClientNotConfigured
from app.agent.runtime import AgentRuntime, AgentRuntimeError
from app.db.enums import (
    AgentMessageRole,
    AgentSessionMode,
    AgentSessionStatus,
)
from app.db.models.account import Account, AccountMode
from app.db.models.account_state import AccountState
from app.db.models.agent_message import AgentMessage
from app.db.models.agent_session import AgentSession
from app.db.models.agent_tool_invocation import AgentToolInvocation
from app.db.models.user import User
from app.events.bus import EventBus


def _now() -> datetime:
    return datetime.now(UTC)


def _settings(api_key: str = "sk-test", budget: float = 2.0) -> MagicMock:
    s = MagicMock()
    s.anthropic_api_key = api_key
    s.agent_default_model = "claude-haiku-4-5-20251001"
    s.agent_daily_budget_usd = budget
    return s


def _mock_call(
    text: str = "Hello",
    tool_use_blocks: list[dict] | None = None,
    in_tok: int = 2000,
    out_tok: int = 500,
) -> AnthropicCall:
    blocks: list[dict] = []
    if tool_use_blocks:
        blocks.extend(tool_use_blocks)
    if text:
        blocks.append({"type": "text", "text": text})

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


@pytest.fixture
async def seeded(session_factory):
    async with session_factory() as db:
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


# ---------- lifecycle ----------


async def test_start_session_creates_active_row(seeded, session_factory):
    runtime = AgentRuntime(
        _settings(), session_factory, EventBus(), mcp_server_url=None
    )
    sid = await runtime.start_session(user_id=1, mode=AgentSessionMode.B2_INTERACTIVE)
    async with session_factory() as db:
        row = await db.get(AgentSession, sid)
    assert row is not None
    assert row.status == AgentSessionStatus.ACTIVE
    assert row.daily_budget_usd == Decimal("2.0000")
    assert row.mode == AgentSessionMode.B2_INTERACTIVE


async def test_start_session_ends_prior_active(seeded, session_factory):
    """One ACTIVE session per user — a second start_session supersedes the first."""
    runtime = AgentRuntime(
        _settings(), session_factory, EventBus(), mcp_server_url=None
    )
    s1 = await runtime.start_session(user_id=1, mode=AgentSessionMode.B2_INTERACTIVE)
    s2 = await runtime.start_session(user_id=1, mode=AgentSessionMode.B2_INTERACTIVE)
    async with session_factory() as db:
        r1 = await db.get(AgentSession, s1)
        r2 = await db.get(AgentSession, s2)
    assert r1.status == AgentSessionStatus.ENDED
    assert r1.end_reason == "superseded"
    assert r2.status == AgentSessionStatus.ACTIVE


async def test_start_session_without_api_key_raises(seeded, session_factory):
    runtime = AgentRuntime(
        _settings(api_key=""), session_factory, EventBus(), mcp_server_url=None
    )
    with pytest.raises(AnthropicClientNotConfigured):
        await runtime.start_session(user_id=1, mode=AgentSessionMode.B2_INTERACTIVE)


async def test_b3_mode_rejected_with_adr_pointer(seeded, session_factory):
    """B3 is paused per ADR 0006 — the runtime rejects with the ADR named."""
    runtime = AgentRuntime(
        _settings(), session_factory, EventBus(), mcp_server_url=None
    )
    with pytest.raises(AgentRuntimeError) as excinfo:
        await runtime.start_session(user_id=1, mode=AgentSessionMode.B3_AUTONOMOUS)
    assert "ADR 0006" in str(excinfo.value)


async def test_end_session_marks_ended(seeded, session_factory):
    runtime = AgentRuntime(
        _settings(), session_factory, EventBus(), mcp_server_url=None
    )
    sid = await runtime.start_session(user_id=1, mode=AgentSessionMode.B2_INTERACTIVE)
    await runtime.end_session(session_id=sid, reason="user_end")
    async with session_factory() as db:
        row = await db.get(AgentSession, sid)
    assert row.status == AgentSessionStatus.ENDED
    assert row.end_reason == "user_end"


# ---------- the user-message turn ----------


async def test_append_message_text_only_response(seeded, session_factory):
    runtime = AgentRuntime(
        _settings(), session_factory, EventBus(), mcp_server_url=None
    )
    sid = await runtime.start_session(user_id=1, mode=AgentSessionMode.B2_INTERACTIVE)

    with patch(
        "app.agent.runtime.create_message",
        new=AsyncMock(return_value=_mock_call("Your cash is $50k.")),
    ):
        await runtime.append_user_message(session_id=sid, text="what's my cash?")

    async with session_factory() as db:
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
    assert "50k" in rows[1].content_json[0]["text"]


async def test_append_message_tool_use_records_invocation(seeded, session_factory):
    runtime = AgentRuntime(
        _settings(), session_factory, EventBus(), mcp_server_url=None
    )
    sid = await runtime.start_session(user_id=1, mode=AgentSessionMode.B2_INTERACTIVE)

    call_with_tool = _mock_call(
        text="You have 2 positions.",
        tool_use_blocks=[
            {
                "type": "tool_use",
                "id": "tu_1",
                "name": "list_positions",
                "input": {},
            }
        ],
    )
    with patch(
        "app.agent.runtime.create_message",
        new=AsyncMock(return_value=call_with_tool),
    ):
        await runtime.append_user_message(
            session_id=sid, text="what are my positions?"
        )

    async with session_factory() as db:
        invs = (
            await db.execute(
                select(AgentToolInvocation).where(
                    AgentToolInvocation.session_id == sid
                )
            )
        ).scalars().all()
    assert len(invs) == 1
    assert invs[0].tool_name == "list_positions"
    # Tool dispatch is server-side at Anthropic — output_json is not
    # surfaced back to us via the MCP connector.
    assert invs[0].output_json is None


async def test_pre_call_cap_transitions_to_capped(seeded, session_factory):
    """First call passes the pre-call gate; second call's gate refuses.

    The pre-call estimate is 4000 input + 1000 output Haiku tokens ≈
    $0.0072. With budget $0.010:
      - call 1 pre-gate: 0 + 0.0072 < 0.010 ✓ → call proceeds
      - call 1 actual cost: ~$0.0036, session total $0.0036
      - call 2 pre-gate: 0.0036 + 0.0072 = 0.0108 > 0.010 → refused → CAPPED
    """
    runtime = AgentRuntime(
        _settings(budget=0.010), session_factory, EventBus(), mcp_server_url=None
    )
    sid = await runtime.start_session(user_id=1, mode=AgentSessionMode.B2_INTERACTIVE)

    with patch(
        "app.agent.runtime.create_message",
        new=AsyncMock(return_value=_mock_call("first response")),
    ):
        await runtime.append_user_message(session_id=sid, text="first")

    # Verify the first call landed cleanly and the session is still ACTIVE.
    async with session_factory() as db:
        row = await db.get(AgentSession, sid)
    assert row.status == AgentSessionStatus.ACTIVE
    assert row.total_cost_usd == Decimal("0.0036")

    second_mock = AsyncMock(return_value=_mock_call("second"))
    with patch("app.agent.runtime.create_message", new=second_mock):
        await runtime.append_user_message(session_id=sid, text="second")
    assert second_mock.call_count == 0

    async with session_factory() as db:
        row = await db.get(AgentSession, sid)
    assert row.status == AgentSessionStatus.CAPPED
    assert row.end_reason == "pre_call_estimate_over_budget"


async def test_anthropic_exception_transitions_to_error(seeded, session_factory):
    runtime = AgentRuntime(
        _settings(), session_factory, EventBus(), mcp_server_url=None
    )
    sid = await runtime.start_session(user_id=1, mode=AgentSessionMode.B2_INTERACTIVE)

    with patch(
        "app.agent.runtime.create_message",
        new=AsyncMock(side_effect=Exception("API down")),
    ):
        await runtime.append_user_message(session_id=sid, text="hi")

    async with session_factory() as db:
        row = await db.get(AgentSession, sid)
    assert row.status == AgentSessionStatus.ERROR
    assert "API down" in (row.end_reason or "")


async def test_session_totals_updated_after_call(seeded, session_factory):
    runtime = AgentRuntime(
        _settings(), session_factory, EventBus(), mcp_server_url=None
    )
    sid = await runtime.start_session(user_id=1, mode=AgentSessionMode.B2_INTERACTIVE)

    with patch(
        "app.agent.runtime.create_message",
        new=AsyncMock(return_value=_mock_call("hi", in_tok=1500, out_tok=300)),
    ):
        await runtime.append_user_message(session_id=sid, text="hello")

    async with session_factory() as db:
        row = await db.get(AgentSession, sid)
    assert row.total_input_tokens == 1500
    assert row.total_output_tokens == 300
    assert row.total_cost_usd > Decimal("0")


async def test_tool_loop_stops_when_text_present(seeded, session_factory):
    """A response with text ends the loop — even if it also has tool_use."""
    runtime = AgentRuntime(
        _settings(), session_factory, EventBus(), mcp_server_url=None
    )
    sid = await runtime.start_session(user_id=1, mode=AgentSessionMode.B2_INTERACTIVE)

    call_with_text_and_tool = _mock_call(
        text="Here's your answer.",
        tool_use_blocks=[
            {
                "type": "tool_use",
                "id": "tu_x",
                "name": "list_positions",
                "input": {},
            }
        ],
    )
    mock_create = AsyncMock(return_value=call_with_text_and_tool)
    with patch("app.agent.runtime.create_message", new=mock_create):
        await runtime.append_user_message(session_id=sid, text="hello")

    # Loop should have exited after the first call (text was present).
    assert mock_create.call_count == 1
