"""DailyBudgetResolver against a real DB (P3 Session 1)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from app.agent.pricing import DailyBudgetResolver
from app.db.enums import AgentSessionMode, AgentSessionStatus
from app.db.models.agent_session import AgentSession
from app.db.models.user import User


def _now() -> datetime:
    return datetime.now(UTC)


@pytest.fixture
async def seeded(session_factory):
    async with session_factory() as session:
        session.add(User(id=1, email="jay@test", display_name="Jay"))
        await session.commit()


async def test_spent_today_zero_when_no_sessions(seeded, session_factory):
    resolver = DailyBudgetResolver(daily_budget_usd=Decimal("2.0"))
    async with session_factory() as session:
        spent = await resolver.spent_today(session, user_id=1)
    assert spent == Decimal("0")


async def test_spent_today_sums_active_and_terminal_sessions(seeded, session_factory):
    """Capped and ended sessions still count against today's budget."""
    async with session_factory() as session:
        session.add(
            AgentSession(
                user_id=1,
                mode=AgentSessionMode.B2_INTERACTIVE,
                status=AgentSessionStatus.ACTIVE,
                model="claude-haiku-4-5-20251001",
                total_input_tokens=0,
                total_output_tokens=0,
                total_cost_usd=Decimal("0.50"),
                daily_budget_usd=Decimal("2.0"),
                started_at=_now(),
            )
        )
        session.add(
            AgentSession(
                user_id=1,
                mode=AgentSessionMode.B2_INTERACTIVE,
                status=AgentSessionStatus.CAPPED,
                model="claude-haiku-4-5-20251001",
                total_input_tokens=0,
                total_output_tokens=0,
                total_cost_usd=Decimal("1.20"),
                daily_budget_usd=Decimal("2.0"),
                started_at=_now() - timedelta(hours=2),
                ended_at=_now() - timedelta(hours=1),
            )
        )
        session.add(
            AgentSession(
                user_id=1,
                mode=AgentSessionMode.B1_READONLY,
                status=AgentSessionStatus.ENDED,
                model="claude-haiku-4-5-20251001",
                total_input_tokens=0,
                total_output_tokens=0,
                total_cost_usd=Decimal("0.05"),
                daily_budget_usd=Decimal("2.0"),
                started_at=_now() - timedelta(hours=4),
                ended_at=_now() - timedelta(hours=3),
            )
        )
        await session.commit()

    resolver = DailyBudgetResolver(daily_budget_usd=Decimal("2.0"))
    async with session_factory() as session:
        spent = await resolver.spent_today(session, user_id=1)
    # 0.50 + 1.20 + 0.05 = 1.75
    assert spent == Decimal("1.7500")


async def test_spent_today_ignores_yesterday(seeded, session_factory):
    """A session started before today's midnight does NOT count."""
    yesterday = _now() - timedelta(days=1)
    async with session_factory() as session:
        session.add(
            AgentSession(
                user_id=1,
                mode=AgentSessionMode.B2_INTERACTIVE,
                status=AgentSessionStatus.ENDED,
                model="claude-haiku-4-5-20251001",
                total_input_tokens=0,
                total_output_tokens=0,
                total_cost_usd=Decimal("1.99"),
                daily_budget_usd=Decimal("2.0"),
                started_at=yesterday,
                ended_at=yesterday + timedelta(hours=2),
            )
        )
        await session.commit()

    resolver = DailyBudgetResolver(daily_budget_usd=Decimal("2.0"))
    async with session_factory() as session:
        spent = await resolver.spent_today(session, user_id=1)
    assert spent == Decimal("0")


async def test_spent_today_only_for_specified_user(seeded, session_factory):
    """User 2's session must not count against user 1's budget."""
    async with session_factory() as session:
        session.add(User(id=2, email="other@test", display_name="Other"))
        session.add(
            AgentSession(
                user_id=2,
                mode=AgentSessionMode.B2_INTERACTIVE,
                status=AgentSessionStatus.ACTIVE,
                model="claude-haiku-4-5-20251001",
                total_input_tokens=0,
                total_output_tokens=0,
                total_cost_usd=Decimal("1.50"),
                daily_budget_usd=Decimal("2.0"),
                started_at=_now(),
            )
        )
        await session.commit()

    resolver = DailyBudgetResolver(daily_budget_usd=Decimal("2.0"))
    async with session_factory() as session:
        spent = await resolver.spent_today(session, user_id=1)
    assert spent == Decimal("0")


async def test_remaining_calculates_correctly(seeded, session_factory):
    async with session_factory() as session:
        session.add(
            AgentSession(
                user_id=1,
                mode=AgentSessionMode.B2_INTERACTIVE,
                status=AgentSessionStatus.ACTIVE,
                model="claude-haiku-4-5-20251001",
                total_input_tokens=0,
                total_output_tokens=0,
                total_cost_usd=Decimal("0.75"),
                daily_budget_usd=Decimal("2.0"),
                started_at=_now(),
            )
        )
        await session.commit()

    resolver = DailyBudgetResolver(daily_budget_usd=Decimal("2.0"))
    async with session_factory() as session:
        remaining = await resolver.remaining(session, user_id=1)
    assert remaining == Decimal("1.2500")


async def test_would_exceed_true_when_estimate_pushes_over(seeded, session_factory):
    async with session_factory() as session:
        session.add(
            AgentSession(
                user_id=1,
                mode=AgentSessionMode.B2_INTERACTIVE,
                status=AgentSessionStatus.ACTIVE,
                model="claude-haiku-4-5-20251001",
                total_input_tokens=0,
                total_output_tokens=0,
                total_cost_usd=Decimal("1.95"),
                daily_budget_usd=Decimal("2.0"),
                started_at=_now(),
            )
        )
        await session.commit()

    resolver = DailyBudgetResolver(daily_budget_usd=Decimal("2.0"))
    async with session_factory() as session:
        # 1.95 + 0.10 = 2.05 > 2.0
        exceeds = await resolver.would_exceed(
            session, user_id=1, estimated_cost=Decimal("0.10")
        )
    assert exceeds is True


async def test_would_exceed_false_when_within_budget(seeded, session_factory):
    async with session_factory() as session:
        session.add(
            AgentSession(
                user_id=1,
                mode=AgentSessionMode.B2_INTERACTIVE,
                status=AgentSessionStatus.ACTIVE,
                model="claude-haiku-4-5-20251001",
                total_input_tokens=0,
                total_output_tokens=0,
                total_cost_usd=Decimal("1.00"),
                daily_budget_usd=Decimal("2.0"),
                started_at=_now(),
            )
        )
        await session.commit()

    resolver = DailyBudgetResolver(daily_budget_usd=Decimal("2.0"))
    async with session_factory() as session:
        exceeds = await resolver.would_exceed(
            session, user_id=1, estimated_cost=Decimal("0.10")
        )
    assert exceeds is False
