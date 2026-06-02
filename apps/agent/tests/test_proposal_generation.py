"""Unit tests for agent.proposal_generation — full flow with injected fakes.

The MCP + backend clients are fakes (the MCP wire protocol is only exercised in
the live smoke). Anthropic is mocked by installing a fake ``anthropic`` module.
The budget check hits a MockTransport httpx client (the fake backend's ``.http``).
"""
from __future__ import annotations

import json
import sys
import types

import httpx
import pytest

from agent.config import AgentConfig
from agent.llm_call import LLMCallFailed
from agent.proposal_generation import generate_proposal

CONFIG = AgentConfig(
    backend_api_base="http://backend",
    workbench_mcp_base="http://mcp",
    agent_api_key="agt-key",
    anthropic_api_key="sk-test",
)


class FakeMcp:
    async def get_trading_profile(self):
        return {"bias_criteria": {}, "bias_thresholds": {}, "agent_envelope": {}}

    async def get_strategy_history(self, strategy_id, limit=30):
        return {"snapshot": {"id": strategy_id, "params": {"rsi_min": 50}}, "performance": {}}

    async def get_recent_proposals(self, strategy_id, limit=5):
        return []

    async def get_strategy_recent_orders(self, strategy_id, limit=20):
        return []


class FakeBackend:
    def __init__(self, proposal_state="DRAFT", budget="ALLOWED"):
        self._proposal_state = proposal_state
        self.patched = None

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                json={
                    "current_spend_cents": 0,
                    "envelope_cents": 200,
                    "headroom_cents": 200,
                    "decision": budget,
                },
            )

        self.http = httpx.AsyncClient(
            transport=httpx.MockTransport(handler), base_url="http://backend"
        )

    async def get_proposal(self, proposal_id):
        return {"id": proposal_id, "strategy_id": 1, "state": self._proposal_state}

    async def update_proposal_to_reviewing(self, proposal_id, *, proposal_payload, evidence_bundle, llm_usage):
        self.patched = {
            "proposal_id": proposal_id,
            "proposal_payload": proposal_payload,
            "evidence_bundle": evidence_bundle,
            "llm_usage": llm_usage,
        }
        return {"state": "REVIEWING"}


def _install_fake_anthropic(monkeypatch, create_impl):
    class _Messages:
        async def create(self, **kwargs):
            return await create_impl(**kwargs)

    class _FakeAnthropic:
        def __init__(self, *a, **k):
            self.messages = _Messages()

    mod = types.ModuleType("anthropic")
    mod.AsyncAnthropic = _FakeAnthropic  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "anthropic", mod)


def _ok_payload() -> str:
    return json.dumps(
        {
            "proposal_type": "parameter_adjustment",
            "changes": [{"param": "rsi_min", "from": 50, "to": 55, "reason": "r"}],
            "confidence": "MEDIUM",
            "summary": "Tune RSI",
            "rationale": "Recent data supports a higher RSI floor.",
        }
    )


def _anthropic_returning(text: str):
    async def create(**kwargs):
        block = types.SimpleNamespace(text=text)
        usage = types.SimpleNamespace(input_tokens=1200, output_tokens=300)
        return types.SimpleNamespace(content=[block], usage=usage)

    return create


async def test_full_flow_success(monkeypatch):
    _install_fake_anthropic(monkeypatch, _anthropic_returning(_ok_payload()))
    backend = FakeBackend()
    result = await generate_proposal(CONFIG, 7, mcp=FakeMcp(), backend=backend)
    assert result.state == "REVIEWING"
    assert result.confidence == "MEDIUM"
    # The PATCH to REVIEWING carried the payload + llm_usage cost telemetry.
    assert backend.patched["proposal_id"] == 7
    assert backend.patched["llm_usage"]["model"] == "claude-sonnet-4-6"
    assert "cost_cents" in backend.patched["llm_usage"]


async def test_parse_error_drops_proposal(monkeypatch):
    _install_fake_anthropic(monkeypatch, _anthropic_returning("not json at all"))
    backend = FakeBackend()
    with pytest.raises(ValueError):
        await generate_proposal(CONFIG, 7, mcp=FakeMcp(), backend=backend)
    assert backend.patched is None  # never wrote back


async def test_missing_fields_raises_keyerror(monkeypatch):
    _install_fake_anthropic(monkeypatch, _anthropic_returning(json.dumps({"summary": "x"})))
    backend = FakeBackend()
    with pytest.raises(KeyError):
        await generate_proposal(CONFIG, 7, mcp=FakeMcp(), backend=backend)


async def test_invalid_confidence_raises_valueerror(monkeypatch):
    bad = json.dumps(
        {
            "proposal_type": "parameter_adjustment",
            "changes": [],
            "confidence": "VERY_HIGH",
            "summary": "x",
            "rationale": "y",
        }
    )
    _install_fake_anthropic(monkeypatch, _anthropic_returning(bad))
    backend = FakeBackend()
    with pytest.raises(ValueError):
        await generate_proposal(CONFIG, 7, mcp=FakeMcp(), backend=backend)


async def test_budget_rejected_propagates(monkeypatch):
    from agent.budget import BudgetRejected

    _install_fake_anthropic(monkeypatch, _anthropic_returning(_ok_payload()))
    backend = FakeBackend(budget="REJECTED")
    with pytest.raises(BudgetRejected):
        await generate_proposal(CONFIG, 7, mcp=FakeMcp(), backend=backend)
    assert backend.patched is None


async def test_anthropic_timeout_raises_llm_call_failed(monkeypatch):
    async def boom(**kwargs):
        raise TimeoutError("slow")

    _install_fake_anthropic(monkeypatch, boom)
    backend = FakeBackend()
    with pytest.raises(LLMCallFailed):
        await generate_proposal(CONFIG, 7, mcp=FakeMcp(), backend=backend)


async def test_non_draft_proposal_raises(monkeypatch):
    _install_fake_anthropic(monkeypatch, _anthropic_returning(_ok_payload()))
    backend = FakeBackend(proposal_state="REVIEWING")
    with pytest.raises(ValueError):
        await generate_proposal(CONFIG, 7, mcp=FakeMcp(), backend=backend)
