"""Unit tests for agent.llm_call — the budget-gated LLM wrapper.

Anthropic is mocked (no real API calls in §1a). ``call_with_budget`` does
``from anthropic import AsyncAnthropic`` at call time, so patching the attribute
on the ``anthropic`` module intercepts construction.
"""
from __future__ import annotations

import sys
import types

import httpx
import pytest

from agent.budget import BudgetRejected
from agent.llm_call import LLMCallFailed, call_with_budget


def _backend(handler) -> httpx.AsyncClient:
    return httpx.AsyncClient(
        transport=httpx.MockTransport(handler), base_url="http://backend"
    )


def _allowed_handler(request: httpx.Request) -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "current_spend_cents": 0,
            "envelope_cents": 200,
            "headroom_cents": 200,
            "decision": "ALLOWED",
        },
    )


def _rejected_handler(request: httpx.Request) -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "current_spend_cents": 200,
            "envelope_cents": 200,
            "headroom_cents": 0,
            "decision": "REJECTED",
        },
    )


def _install_fake_anthropic(monkeypatch: pytest.MonkeyPatch, create_impl) -> dict:
    """Install a fake ``anthropic`` module whose AsyncAnthropic.messages.create
    runs ``create_impl``. Returns a dict tracking instantiation."""
    state = {"constructed": False}

    class _Messages:
        async def create(self, **kwargs):
            return await create_impl(**kwargs)

    class _FakeAsyncAnthropic:
        def __init__(self, *args, **kwargs):
            state["constructed"] = True
            self.messages = _Messages()

    fake_mod = types.ModuleType("anthropic")
    fake_mod.AsyncAnthropic = _FakeAsyncAnthropic  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "anthropic", fake_mod)
    return state


async def test_wrapper_raises_budget_rejected_before_anthropic_call(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _should_not_run(**kwargs):  # pragma: no cover - asserts non-call
        raise AssertionError("Anthropic must not be called when budget rejects")

    state = _install_fake_anthropic(monkeypatch, _should_not_run)

    async with _backend(_rejected_handler) as c:
        with pytest.raises(BudgetRejected):
            await call_with_budget(
                backend_client=c,
                anthropic_api_key="k",
                model="claude-sonnet-4-6",
                messages=[{"role": "user", "content": "hi"}],
                max_tokens=100,
                estimated_input_tokens=50,
            )
    assert state["constructed"] is False


async def test_wrapper_raises_llm_call_failed_on_timeout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _timeout(**kwargs):
        raise TimeoutError("upstream timed out")

    _install_fake_anthropic(monkeypatch, _timeout)

    async with _backend(_allowed_handler) as c:
        with pytest.raises(LLMCallFailed) as exc:
            await call_with_budget(
                backend_client=c,
                anthropic_api_key="k",
                model="claude-sonnet-4-6",
                messages=[{"role": "user", "content": "hi"}],
                max_tokens=100,
                estimated_input_tokens=50,
            )
    assert exc.value.error_type == "timeout"


async def test_wrapper_raises_llm_call_failed_on_empty_response(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _empty(**kwargs):
        usage = types.SimpleNamespace(input_tokens=10, output_tokens=0)
        return types.SimpleNamespace(content=[], usage=usage)

    _install_fake_anthropic(monkeypatch, _empty)

    async with _backend(_allowed_handler) as c:
        with pytest.raises(LLMCallFailed) as exc:
            await call_with_budget(
                backend_client=c,
                anthropic_api_key="k",
                model="claude-sonnet-4-6",
                messages=[{"role": "user", "content": "hi"}],
                max_tokens=100,
                estimated_input_tokens=50,
            )
    assert exc.value.error_type == "empty_response"


async def test_wrapper_returns_result_with_real_usage_on_success(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _ok(**kwargs):
        block = types.SimpleNamespace(text="a proposal")
        usage = types.SimpleNamespace(input_tokens=1234, output_tokens=567)
        return types.SimpleNamespace(content=[block], usage=usage)

    _install_fake_anthropic(monkeypatch, _ok)

    async with _backend(_allowed_handler) as c:
        result = await call_with_budget(
            backend_client=c,
            anthropic_api_key="k",
            model="claude-sonnet-4-6",
            messages=[{"role": "user", "content": "hi"}],
            max_tokens=100,
            estimated_input_tokens=50,
        )
    assert result.text == "a proposal"
    assert result.input_tokens == 1234
    assert result.output_tokens == 567
    assert result.cost_cents >= 1  # real usage → conservative non-zero cost
    assert result.budget.decision == "ALLOWED"
