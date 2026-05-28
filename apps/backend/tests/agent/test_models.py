"""Schema smoke: round-trip rows for the three agent tables (P3 Session 1)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import select

from app.db.enums import (
    AgentMessageRole,
    AgentSessionMode,
    AgentSessionStatus,
)
from app.db.models.agent_message import AgentMessage
from app.db.models.agent_session import AgentSession
from app.db.models.agent_tool_invocation import AgentToolInvocation
from app.db.models.user import User


def _now() -> datetime:
    return datetime.now(UTC)


@pytest.fixture
async def seeded(session_factory):
    async with session_factory() as session:
        session.add(User(id=1, email="jay@test", display_name="Jay"))
        await session.commit()


async def test_can_create_and_read_session(seeded, session_factory):
    async with session_factory() as session:
        s = AgentSession(
            user_id=1,
            mode=AgentSessionMode.B2_INTERACTIVE,
            status=AgentSessionStatus.ACTIVE,
            model="claude-haiku-4-5-20251001",
            total_input_tokens=0,
            total_output_tokens=0,
            total_cost_usd=Decimal("0"),
            daily_budget_usd=Decimal("2.0"),
            started_at=_now(),
        )
        session.add(s)
        await session.commit()
        await session.refresh(s)
        assert s.id is not None
        assert s.status == AgentSessionStatus.ACTIVE
        # Decimal precision survives round-trip.
        assert s.daily_budget_usd == Decimal("2.0000")


async def test_session_cascade_deletes_messages_and_invocations(seeded, session_factory):
    async with session_factory() as session:
        s = AgentSession(
            user_id=1,
            mode=AgentSessionMode.B2_INTERACTIVE,
            status=AgentSessionStatus.ACTIVE,
            model="claude-haiku-4-5-20251001",
            total_input_tokens=0,
            total_output_tokens=0,
            total_cost_usd=Decimal("0"),
            daily_budget_usd=Decimal("2.0"),
            started_at=_now(),
        )
        session.add(s)
        await session.flush()
        sid = s.id

        msg = AgentMessage(
            session_id=sid,
            role=AgentMessageRole.USER,
            content_json=[{"type": "text", "text": "hello"}],
            ts=_now(),
        )
        session.add(msg)
        await session.flush()

        inv = AgentToolInvocation(
            session_id=sid,
            message_id=msg.id,
            tool_name="list_positions",
            input_json={},
            output_json=[],
            latency_ms=42,
            ts=_now(),
        )
        session.add(inv)
        await session.commit()

        await session.delete(s)
        await session.commit()

        remaining_msgs = (
            await session.execute(
                select(AgentMessage).where(AgentMessage.session_id == sid)
            )
        ).scalars().all()
        remaining_invs = (
            await session.execute(
                select(AgentToolInvocation).where(
                    AgentToolInvocation.session_id == sid
                )
            )
        ).scalars().all()
        assert remaining_msgs == []
        assert remaining_invs == []


async def test_tool_use_parent_threading(seeded, session_factory):
    """A TOOL_RESULT message's ``parent_message_id`` points at its TOOL_USE."""
    async with session_factory() as session:
        s = AgentSession(
            user_id=1,
            mode=AgentSessionMode.B2_INTERACTIVE,
            status=AgentSessionStatus.ACTIVE,
            model="claude-haiku-4-5-20251001",
            total_input_tokens=0,
            total_output_tokens=0,
            total_cost_usd=Decimal("0"),
            daily_budget_usd=Decimal("2.0"),
            started_at=_now(),
        )
        session.add(s)
        await session.flush()

        tool_use = AgentMessage(
            session_id=s.id,
            role=AgentMessageRole.TOOL_USE,
            content_json=[
                {
                    "type": "tool_use",
                    "id": "tu_1",
                    "name": "list_positions",
                    "input": {},
                }
            ],
            ts=_now(),
        )
        session.add(tool_use)
        await session.flush()

        tool_result = AgentMessage(
            session_id=s.id,
            role=AgentMessageRole.TOOL_RESULT,
            content_json=[
                {
                    "type": "tool_result",
                    "tool_use_id": "tu_1",
                    "content": "[]",
                }
            ],
            parent_message_id=tool_use.id,
            ts=_now(),
        )
        session.add(tool_result)
        await session.commit()
        await session.refresh(tool_result)

        assert tool_result.parent_message_id == tool_use.id


async def test_session_relationship_iterates_messages_in_ts_order(
    seeded, session_factory
):
    async with session_factory() as session:
        s = AgentSession(
            user_id=1,
            mode=AgentSessionMode.B2_INTERACTIVE,
            status=AgentSessionStatus.ACTIVE,
            model="claude-haiku-4-5-20251001",
            total_input_tokens=0,
            total_output_tokens=0,
            total_cost_usd=Decimal("0"),
            daily_budget_usd=Decimal("2.0"),
            started_at=_now(),
        )
        session.add(s)
        await session.flush()

        base = _now()
        for i, content in enumerate(["first", "second", "third"]):
            session.add(
                AgentMessage(
                    session_id=s.id,
                    role=AgentMessageRole.USER,
                    content_json=[{"type": "text", "text": content}],
                    ts=base + timedelta(seconds=i),
                )
            )
        await session.commit()

        await session.refresh(s, attribute_names=["messages"])
        texts = [m.content_json[0]["text"] for m in s.messages]
        assert texts == ["first", "second", "third"]
