"""System prompt building (P3 Session 3)."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest

from app.db.enums import AgentSessionMode
from app.db.models.account import Account, AccountMode
from app.db.models.account_state import AccountState
from app.db.models.user import User
from app.llm.system_prompt import (
    UserContextSummary,
    build_system_prompt,
    gather_user_context,
)
from app.services.day_change_basis import BROKER_LAST_EQUITY


def _now() -> datetime:
    return datetime.now(UTC)


async def test_gather_user_context_with_no_account(session_factory):
    async with session_factory() as db:
        db.add(User(id=1, email="jay@test", display_name="Jay"))
        await db.commit()
        ctx = await gather_user_context(db, user_id=1)
    assert ctx.mode == "unknown"
    assert ctx.equity == "unknown"
    assert ctx.positions_open == 0
    assert ctx.strategies_total == 0
    assert ctx.strategies_active == 0


async def test_gather_user_context_with_paper_account(session_factory):
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
                day_change_basis=BROKER_LAST_EQUITY,
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
        ctx = await gather_user_context(db, user_id=1)
    assert ctx.mode == "paper"
    assert "100000" in ctx.equity
    assert ctx.equity.startswith("$")


def test_build_b2_prompt_includes_suggestion_format():
    ctx = UserContextSummary(
        mode="paper", strategies_active=1,
        strategies_total=2, positions_open=3, equity="$100000",
    )
    prompt = build_system_prompt(AgentSessionMode.B2_INTERACTIVE, ctx)
    assert "Suggestion:" in prompt
    assert "Confidence:" in prompt
    assert "paper" in prompt
    assert "Open positions: 3" in prompt
    assert "of which 1 actively running" in prompt


def test_build_b1_prompt_excludes_suggestions():
    ctx = UserContextSummary(
        mode="paper", strategies_active=0,
        strategies_total=0, positions_open=0, equity="$100000",
    )
    prompt = build_system_prompt(AgentSessionMode.B1_READONLY, ctx)
    assert "Suggestion:" not in prompt
    assert "Do not suggest" in prompt


def test_build_b3_prompt_rejected_with_adr_pointer():
    """B3 is paused per ADR 0006 — the rejection should name the ADR."""
    ctx = UserContextSummary(
        mode="paper", strategies_active=0,
        strategies_total=0, positions_open=0, equity="$100000",
    )
    with pytest.raises(ValueError) as excinfo:
        build_system_prompt(AgentSessionMode.B3_AUTONOMOUS, ctx)
    assert "ADR 0006" in str(excinfo.value)
