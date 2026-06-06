"""P7 §2 — the strategy-generation service + the create_message tools passthrough."""
from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import select

from app.db.models.audit_log import AuditLog
from app.db.models.user import User
from app.security import CredentialKind, CredentialStore
from app.services.strategy_authoring import service
from app.services.strategy_authoring.service import (
    BudgetExceededError,
    GenerationError,
    NoApiKeyError,
    generate_strategy,
)

UID = 1


def _fake_call(*, code="class S:\n    pass\n", has_tool=True, in_tok=4000, out_tok=2000):
    if has_tool:
        blocks = [{
            "type": "tool_use", "name": "emit_strategy",
            "input": {"code": code, "assumptions": ["RSI period 14"], "explanation": "does X"},
        }]
    else:
        blocks = [{"type": "text", "text": "I cannot."}]
    return SimpleNamespace(content_blocks=blocks, input_tokens=in_tok, output_tokens=out_tok)


async def _seed(session_factory, *, with_key=True) -> None:
    async with session_factory() as s:
        s.add(User(id=UID, email="jay@test"))
        await s.commit()
        if with_key:
            await CredentialStore(s).set(UID, CredentialKind.ANTHROPIC_API_KEY, "sk-test")
            await s.commit()


def _patch_call(monkeypatch, call):
    async def _fake(**kwargs):  # noqa: ANN003
        return call

    monkeypatch.setattr(service, "create_message", _fake)


# ---- create_message tools passthrough (the §2.1 extension) ----


async def test_create_message_passes_tools_only_when_provided(monkeypatch):
    from app.llm import anthropic_client

    recorded: dict = {}

    class _Msgs:
        async def create(self, **kwargs):  # noqa: ANN003
            recorded.update(kwargs)
            return SimpleNamespace(content=[], usage=SimpleNamespace(input_tokens=1, output_tokens=1), stop_reason="end_turn")

    monkeypatch.setattr(anthropic_client, "get_anthropic_client", lambda key: SimpleNamespace(messages=_Msgs()))
    await anthropic_client.create_message(
        api_key="k", model="m", system="s", messages=[],
        tools=[{"name": "emit_strategy"}], tool_choice={"type": "tool", "name": "emit_strategy"},
    )
    assert recorded["tools"] == [{"name": "emit_strategy"}]
    assert recorded["tool_choice"]["name"] == "emit_strategy"
    recorded.clear()
    await anthropic_client.create_message(api_key="k", model="m", system="s", messages=[])
    assert "tools" not in recorded and "tool_choice" not in recorded


# ---- generate_strategy ----


async def test_generate_success_parses_and_audits(session_factory, monkeypatch):
    await _seed(session_factory)
    _patch_call(monkeypatch, _fake_call())
    async with session_factory() as s:
        result = await generate_strategy(s, user_id=UID, description="RSI mean reversion on AAPL")
    assert "class S" in result.code
    assert result.assumptions == ["RSI period 14"]
    assert result.cost_usd > 0
    assert result.model == "claude-sonnet-4-6"
    async with session_factory() as s:
        rows = (await s.execute(
            select(AuditLog).where(AuditLog.action == "STRATEGY_GENERATED")
        )).scalars().all()
    assert len(rows) == 1
    payload = json.loads(rows[0].payload_json)
    assert payload["code"] == result.code
    assert payload["prompt_version"] == "v1"
    assert payload["cost_usd"] > 0


async def test_generate_no_tool_block_raises(session_factory, monkeypatch):
    await _seed(session_factory)
    _patch_call(monkeypatch, _fake_call(has_tool=False))
    async with session_factory() as s:
        with pytest.raises(GenerationError):
            await generate_strategy(s, user_id=UID, description="x")


async def test_generate_no_key_raises(session_factory, monkeypatch):
    await _seed(session_factory, with_key=False)
    _patch_call(monkeypatch, _fake_call())
    async with session_factory() as s:
        with pytest.raises(NoApiKeyError):
            await generate_strategy(s, user_id=UID, description="x")


async def test_generate_budget_exceeded_does_not_call_llm(session_factory, monkeypatch):
    await _seed(session_factory)
    # Seed today's authoring spend at the $2 cap so the next call would exceed it.
    from datetime import UTC, datetime
    async with session_factory() as s:
        s.add(AuditLog(
            user_id=UID, ts=datetime.now(UTC), actor_type="user", actor_id="1",
            action="STRATEGY_GENERATED", target_type="strategy_authoring", target_id=None,
            payload_json=json.dumps({"cost_usd": 2.0}),
        ))
        await s.commit()
    mock_call = AsyncMock()
    monkeypatch.setattr(service, "create_message", mock_call)
    async with session_factory() as s:
        with pytest.raises(BudgetExceededError):
            await generate_strategy(s, user_id=UID, description="x")
    mock_call.assert_not_called()  # refused before the Anthropic call
