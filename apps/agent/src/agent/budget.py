"""Agent-side budget check + cost-estimation helper (P6 §1a, Decision 6).

The agent calls :func:`check_budget` before every LLM invocation. If the backend
returns REJECTED, it raises :class:`BudgetRejected` — the caller (1b's invocation
path) catches and drops the proposal.

Cost estimation is duplicated here (not imported from the backend's
``app.agent.pricing``) on purpose: the agent must not import backend code
(CI invariant ``check_agent_no_db_access.sh`` forbids ``app.db``; keeping the
agent free of all ``app.*`` imports keeps the process boundary clean). The
estimate is a conservative *upper bound* — overestimating only tightens the cap,
which is the safe direction; underestimating would let spend leak past it.
"""
from __future__ import annotations

from dataclasses import dataclass

import httpx

# Cents per million tokens, mirroring app/agent/pricing.py's PRICING_TABLE
# (verify against https://www.anthropic.com/pricing when rates change).
_SONNET_IN, _SONNET_OUT = 300, 1500  # $3 / $15 per MTok
_HAIKU_IN, _HAIKU_OUT = 80, 400  # $0.80 / $4 per MTok


@dataclass(frozen=True)
class BudgetCheckResult:
    current_spend_cents: int
    envelope_cents: int
    headroom_cents: int
    decision: str  # "ALLOWED" | "REJECTED"


class BudgetRejected(Exception):
    """Raised when the pre-call budget check returns REJECTED. The caller drops
    the proposal (per Decision 7's failure model)."""


def estimate_cost_cents(
    model: str,
    estimated_input_tokens: int,
    estimated_output_tokens: int,
) -> int:
    """Conservative (rounded-up) cents estimate for one LLM call.

    Unknown models fall back to Sonnet pricing — never zero, so a typo can't
    silently bypass the cap.
    """
    if model.startswith("claude-haiku"):
        in_rate, out_rate = _HAIKU_IN, _HAIKU_OUT
    else:
        # Sonnet (and any unknown model) — conservative default.
        in_rate, out_rate = _SONNET_IN, _SONNET_OUT
    in_cost = (max(0, estimated_input_tokens) * in_rate) / 1_000_000
    out_cost = (max(0, estimated_output_tokens) * out_rate) / 1_000_000
    # Round UP to whole cents to stay conservative.
    return int(-(-(in_cost + out_cost) // 1))


async def check_budget(
    client: httpx.AsyncClient,
    estimated_cost_cents: int,
) -> BudgetCheckResult:
    """Call the backend's ``GET /api/v1/agent/cost-envelope``. Raises
    :class:`BudgetRejected` on a REJECTED decision."""
    r = await client.get(
        "/api/v1/agent/cost-envelope",
        params={"estimated_cost_cents": estimated_cost_cents},
    )
    r.raise_for_status()
    payload = r.json()
    result = BudgetCheckResult(
        current_spend_cents=payload["current_spend_cents"],
        envelope_cents=payload["envelope_cents"],
        headroom_cents=payload["headroom_cents"],
        decision=payload["decision"],
    )
    if result.decision == "REJECTED":
        raise BudgetRejected(
            f"Budget exceeded: {result.current_spend_cents}c spent of "
            f"{result.envelope_cents}c envelope; requested {estimated_cost_cents}c"
        )
    return result
