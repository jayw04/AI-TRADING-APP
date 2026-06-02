"""LLM-call wrapper with budget check + failure handling (P6 §1a).

Per Decisions 6 + 7:
  1. Compute a conservative cost estimate.
  2. Pre-call budget check (raises BudgetRejected if over the envelope).
  3. Anthropic call (raises LLMCallFailed on any error — timeout, API error,
     refusal/empty output).
  4. Compute actual cost from real usage.
  5. Return LLMCallResult; the CALLER writes the audit row (1b).

Failures are dropped, not retried (Decision 7). §1a ships this wrapper with no
caller; 1b adds the first caller (the proposal-generation path), which catches
BudgetRejected / LLMCallFailed and writes the appropriate audit row.
"""
from __future__ import annotations

from dataclasses import dataclass

import httpx

from agent.budget import (
    BudgetCheckResult,
    BudgetRejected,  # noqa: F401 - re-exported for callers that catch it
    check_budget,
    estimate_cost_cents,
)


@dataclass(frozen=True)
class LLMCallResult:
    text: str
    model: str
    input_tokens: int
    output_tokens: int
    cost_cents: int
    budget: BudgetCheckResult


class LLMCallFailed(Exception):
    """Raised when the LLM call fails (timeout, refusal, malformed/empty output).
    The caller drops the proposal (Decision 7)."""

    def __init__(self, error_type: str, detail: str, model: str):
        self.error_type = error_type
        self.detail = detail
        self.model = model
        super().__init__(f"LLMCallFailed[{error_type}/{model}]: {detail}")


async def call_with_budget(
    *,
    backend_client: httpx.AsyncClient,
    anthropic_api_key: str,
    model: str,
    messages: list[dict],
    max_tokens: int,
    estimated_input_tokens: int,
) -> LLMCallResult:
    """The single point through which the agent makes LLM calls."""
    estimated_cost = estimate_cost_cents(model, estimated_input_tokens, max_tokens)
    budget_result = await check_budget(backend_client, estimated_cost)

    try:
        from anthropic import AsyncAnthropic
    except ImportError as exc:
        raise LLMCallFailed("import_error", str(exc), model) from exc

    client = AsyncAnthropic(api_key=anthropic_api_key)

    try:
        resp = await client.messages.create(
            model=model,
            max_tokens=max_tokens,
            messages=messages,
        )
    except TimeoutError as exc:
        raise LLMCallFailed("timeout", str(exc), model) from exc
    except Exception as exc:
        # Catches anthropic.APIError, anthropic.RateLimitError, etc. Per
        # Decision 7: dropped, not retried.
        raise LLMCallFailed(
            error_type=type(exc).__name__,
            detail=str(exc)[:500],
            model=model,
        ) from exc

    text = "".join(
        block.text for block in resp.content if hasattr(block, "text")
    ).strip()
    if not text:
        raise LLMCallFailed("empty_response", "LLM returned no text content", model)

    in_tok = resp.usage.input_tokens
    out_tok = resp.usage.output_tokens
    actual_cost = estimate_cost_cents(model, in_tok, out_tok)

    return LLMCallResult(
        text=text,
        model=model,
        input_tokens=in_tok,
        output_tokens=out_tok,
        cost_cents=actual_cost,
        budget=budget_result,
    )
