"""Proposal generation — the main agent flow (P6 §1b).

Per Decision 1 (stateless single-shot): one invocation = one proposal.
Per Decision 7 (failure model): exceptions raise cleanly; the caller (server.py)
catches them and reports a graceful error (the backend then drops the DRAFT).

``generate_proposal`` constructs the real MCP + backend clients from config, or
accepts injected ones (unit tests pass fakes, so the MCP wire protocol is only
exercised in the Norton/Docker-deferred live smoke).
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

import structlog

from agent.backend_client import BackendClient
from agent.config import AgentConfig
from agent.llm_call import call_with_budget
from agent.mcp_client import WorkbenchMcpClient

logger = structlog.get_logger(__name__)

# VERIFY against the installed Anthropic SDK's accepted-models list at paste time.
PROPOSAL_GENERATION_MODEL = "claude-sonnet-4-6"

_REQUIRED_FIELDS = ("proposal_type", "changes", "confidence", "summary", "rationale")
_VALID_CONFIDENCE = ("LOW", "MEDIUM", "HIGH")


@dataclass(frozen=True)
class ProposalGenerationResult:
    state: str  # "REVIEWING"
    confidence: str
    proposal_payload: dict[str, Any]
    evidence_bundle: dict[str, Any]
    llm_usage: dict[str, Any]


SYSTEM_PROMPT_TEMPLATE = """You are a systematic-trading proposal generator. You suggest small, evidence-grounded adjustments to a strategy's configuration based on its recent performance and the user's bias model.

You are NOT recommending trades and NOT predicting prices. You suggest PARAMETER ADJUSTMENTS for the strategy's configuration. The user reviews and decides whether to apply your proposal.

Your output MUST be a single JSON object with this exact shape:

{{
  "proposal_type": "parameter_adjustment" | "rule_modification" | "new_rule",
  "changes": [
    {{"param": "<parameter name>", "from": "<current value>", "to": "<proposed value>", "reason": "<short justification grounded in the evidence>"}}
  ],
  "confidence": "LOW" | "MEDIUM" | "HIGH",
  "summary": "<one sentence headline>",
  "rationale": "<2-4 sentences on why this change matches the evidence and the user's bias model>"
}}

If you cannot identify a meaningful improvement, return proposal_type "new_rule" with an empty changes list and a summary explaining why no change is suggested.

Confidence: LOW = weak/limited evidence; MEDIUM = clear signal consistent with the bias model; HIGH = strong signal across multiple evidence sources.

User's bias criteria:
{bias_criteria}

User's bias thresholds:
{bias_thresholds}

User's behavioral envelope (constraints you MUST respect):
- Prohibitions: {prohibitions}
- Preferences: {preferences}
- Additional context: {prompt_augmentations}

Output ONLY the JSON object. No preamble, no markdown fences, no text outside the JSON."""


def _extract_json(text: str) -> str:
    """Tolerate LLM output that wraps the JSON in markdown fences or prose.

    The prompt asks for a bare JSON object, but models sometimes return
    ```json … ``` or add a preamble. Strip the fences; otherwise fall back to
    the first {...} span. Returns the original (stripped) text when no object is
    found, so the caller's json.loads still raises a clear error."""
    s = (text or "").strip()
    if s.startswith("```"):
        s = s.split("\n", 1)[1] if "\n" in s else s[3:]
        if "```" in s:
            s = s[: s.rfind("```")]
        s = s.strip()
    if s.startswith("{"):
        return s
    i, j = s.find("{"), s.rfind("}")
    return s[i : j + 1] if i != -1 and j > i else s


async def _run(
    *,
    mcp: Any,
    backend: Any,
    anthropic_api_key: str | None,
    proposal_id: int,
    model: str,
) -> ProposalGenerationResult:
    if not anthropic_api_key:
        raise RuntimeError("ANTHROPIC_API_KEY required for proposal generation")

    proposal = await backend.get_proposal(proposal_id)
    if proposal["state"] != "DRAFT":
        raise ValueError(
            f"Proposal {proposal_id} is not in DRAFT state (got {proposal['state']})"
        )
    strategy_id = proposal["strategy_id"]

    # Evidence via MCP (Decision 2 read surface).
    profile = await mcp.get_trading_profile()
    history = await mcp.get_strategy_history(strategy_id, limit=30)
    recent_proposals = await mcp.get_recent_proposals(strategy_id, limit=5)
    recent_orders = await mcp.get_strategy_recent_orders(strategy_id, limit=20)

    evidence_bundle = {
        "strategy_snapshot": history.get("snapshot", {}),
        "recent_performance": history.get("performance", {}),
        "recent_proposals": recent_proposals,
        "recent_orders": recent_orders,
        "user_profile_signals": {
            "bias_criteria": profile.get("bias_criteria", {}),
            "bias_thresholds": profile.get("bias_thresholds", {}),
            "agent_envelope": profile.get("agent_envelope", {}),
        },
    }

    envelope = profile.get("agent_envelope") or {}
    system_prompt = SYSTEM_PROMPT_TEMPLATE.format(
        bias_criteria=json.dumps(profile.get("bias_criteria", {}), indent=2),
        bias_thresholds=json.dumps(profile.get("bias_thresholds", {}), indent=2),
        prohibitions=json.dumps(envelope.get("prohibitions", []), indent=2),
        preferences=json.dumps(envelope.get("preferences", {}), indent=2),
        prompt_augmentations=envelope.get("prompt_augmentations", "(none)"),
    )

    user_prompt = (
        f"Strategy ID: {strategy_id}\n\n"
        f"Strategy snapshot:\n{json.dumps(evidence_bundle['strategy_snapshot'], indent=2)}\n\n"
        f"Recent performance:\n{json.dumps(evidence_bundle['recent_performance'], indent=2)}\n\n"
        f"Last proposals (do not repeat these):\n"
        f"{json.dumps(evidence_bundle['recent_proposals'], indent=2)}\n\n"
        "Propose one adjustment grounded in this evidence."
    )

    estimated_input_tokens = (len(system_prompt) + len(user_prompt)) // 4

    llm_result = await call_with_budget(
        backend_client=backend.http,
        anthropic_api_key=anthropic_api_key,
        model=model,
        messages=[
            {"role": "user", "content": user_prompt},
        ],
        system=system_prompt,
        max_tokens=1500,
        estimated_input_tokens=estimated_input_tokens,
    )

    try:
        payload = json.loads(_extract_json(llm_result.text))
    except json.JSONDecodeError as exc:
        raise ValueError(
            f"LLM output not valid JSON: {exc} | raw[:200]={llm_result.text[:200]!r}"
        ) from exc

    missing = [k for k in _REQUIRED_FIELDS if k not in payload]
    if missing:
        raise KeyError(f"LLM output missing required fields: {missing}")
    if payload["confidence"] not in _VALID_CONFIDENCE:
        raise ValueError(f"Invalid confidence value: {payload['confidence']!r}")

    llm_usage = {
        "model": llm_result.model,
        "input_tokens": llm_result.input_tokens,
        "output_tokens": llm_result.output_tokens,
        "cost_cents": str(llm_result.cost_cents),  # fractional-cents shape (§1a #3)
    }
    await backend.update_proposal_to_reviewing(
        proposal_id,
        proposal_payload=payload,
        evidence_bundle=evidence_bundle,
        llm_usage=llm_usage,
    )

    return ProposalGenerationResult(
        state="REVIEWING",
        confidence=payload["confidence"],
        proposal_payload=payload,
        evidence_bundle=evidence_bundle,
        llm_usage=llm_usage,
    )


async def generate_proposal(
    config: AgentConfig,
    proposal_id: int,
    *,
    mcp: Any | None = None,
    backend: Any | None = None,
    model: str = PROPOSAL_GENERATION_MODEL,
) -> ProposalGenerationResult:
    """Generate a proposal for a DRAFT proposal_id. Constructs real MCP +
    backend clients from config unless injected (tests inject fakes)."""
    if mcp is not None and backend is not None:
        return await _run(
            mcp=mcp,
            backend=backend,
            anthropic_api_key=config.anthropic_api_key,
            proposal_id=proposal_id,
            model=model,
        )
    async with (
        WorkbenchMcpClient(config.workbench_mcp_base) as real_mcp,
        BackendClient(config.backend_api_base, config.agent_api_key) as real_backend,
    ):
        return await _run(
            mcp=real_mcp,
            backend=real_backend,
            anthropic_api_key=config.anthropic_api_key,
            proposal_id=proposal_id,
            model=model,
        )
