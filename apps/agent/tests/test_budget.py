"""Unit tests for agent.budget — cost estimation + the budget client."""
from __future__ import annotations

import httpx
import pytest

from agent.budget import (
    BudgetRejected,
    check_budget,
    estimate_cost_cents,
)

# ---------------- estimate_cost_cents ----------------


def test_estimate_cost_sonnet() -> None:
    # 1M input + 1M output at $3/$15 per MTok = 300 + 1500 = 1800 cents.
    assert estimate_cost_cents("claude-sonnet-4-6", 1_000_000, 1_000_000) == 1800


def test_estimate_cost_haiku() -> None:
    # 1M input + 1M output at $0.80/$4 per MTok = 80 + 400 = 480 cents.
    assert estimate_cost_cents("claude-haiku-4-5-20251001", 1_000_000, 1_000_000) == 480


def test_estimate_cost_unknown_model_uses_sonnet_default() -> None:
    # Unknown model must NOT be free — falls back to Sonnet (the higher rate).
    unknown = estimate_cost_cents("gpt-nonsense", 1_000_000, 1_000_000)
    sonnet = estimate_cost_cents("claude-sonnet-4-6", 1_000_000, 1_000_000)
    assert unknown == sonnet == 1800


def test_estimate_cost_rounds_up_conservatively() -> None:
    # A tiny call (1 input token, 0 output) costs a fraction of a cent → rounds
    # UP to 1, never down to 0 (under-estimating would leak spend past the cap).
    assert estimate_cost_cents("claude-sonnet-4-6", 1, 0) == 1


def test_estimate_cost_zero_tokens_is_zero() -> None:
    assert estimate_cost_cents("claude-sonnet-4-6", 0, 0) == 0


# ---------------- check_budget ----------------


def _client(handler) -> httpx.AsyncClient:
    return httpx.AsyncClient(
        transport=httpx.MockTransport(handler), base_url="http://backend"
    )


async def test_check_budget_allowed() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/v1/agent/cost-envelope"
        assert request.url.params["estimated_cost_cents"] == "10"
        return httpx.Response(
            200,
            json={
                "current_spend_cents": 0,
                "envelope_cents": 200,
                "headroom_cents": 200,
                "decision": "ALLOWED",
            },
        )

    async with _client(handler) as c:
        res = await check_budget(c, 10)
    assert res.decision == "ALLOWED"
    assert res.headroom_cents == 200


async def test_check_budget_raises_on_rejected() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "current_spend_cents": 195,
                "envelope_cents": 200,
                "headroom_cents": 5,
                "decision": "REJECTED",
            },
        )

    async with _client(handler) as c:
        with pytest.raises(BudgetRejected):
            await check_budget(c, 999)
