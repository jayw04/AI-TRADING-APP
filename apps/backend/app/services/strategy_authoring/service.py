"""Strategy-generation service (P7 §2).

`generate_strategy` makes the Sonnet tool-use call that turns a plain-English
description into a complete Python strategy, parses the structured output, gates
it on the user's daily LLM budget, audits the full request/response with cost,
and returns the artifact. Generate-and-return only — no persistence (the save
flow is §4). The Anthropic call goes through the allowlisted
`app.llm.create_message`, so this module is NOT in the no-LLM allowlist.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

import structlog
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit import AuditAction, AuditActorType, AuditLogger
from app.config import get_settings
from app.db.models.audit_log import AuditLog
from app.llm.anthropic_client import create_message
from app.llm.pricing import DailyBudgetResolver, estimate_cost
from app.security import CredentialKind, CredentialStore
from app.services.strategy_authoring.prompts import (
    GENERATION_MODEL,
    GENERATION_PROMPT_VERSION,
    GENERATION_SYSTEM,
    STRATEGY_OUTPUT_TOOL,
    build_generation_user_message,
)

logger = structlog.get_logger(__name__)

# Token estimates for the pre-call budget gate (the system prompt is ~2-3k; the
# output is a ≤~150-line strategy + assumptions + explanation).
GEN_EST_INPUT_TOKENS = 4000
GEN_EST_OUTPUT_TOKENS = 2000


class AuthoringError(Exception):
    """Base for strategy-authoring failures."""


class BudgetExceededError(AuthoringError):
    """The user's daily LLM budget would be exceeded by this generation."""


class NoApiKeyError(AuthoringError):
    """The user has no Anthropic API key configured."""


class GenerationError(AuthoringError):
    """The model did not return a usable strategy (no/!malformed tool output)."""


@dataclass(frozen=True)
class GenerationResult:
    code: str
    assumptions: list[str]
    explanation: str
    cost_usd: Decimal
    prompt_version: str
    model: str


async def _authoring_spent_today_usd(
    session: AsyncSession, user_id: int, now: datetime
) -> Decimal:
    """Sum this user's strategy-generation cost since start-of-day (UTC), from the
    STRATEGY_GENERATED audit rows (json_extract on cost_usd)."""
    start_of_day = now.replace(hour=0, minute=0, second=0, microsecond=0)
    total = (
        await session.execute(
            select(
                func.coalesce(
                    func.sum(func.json_extract(AuditLog.payload_json, "$.cost_usd")), 0
                )
            )
            .where(AuditLog.action == AuditAction.STRATEGY_GENERATED.value)
            .where(AuditLog.user_id == user_id)
            .where(AuditLog.ts >= start_of_day)
        )
    ).scalar_one()
    return Decimal(str(total or 0))


def _parse_emit_strategy(call: Any) -> tuple[str, list[str], str]:
    """Pull {code, assumptions, explanation} from the forced tool_use block."""
    for block in call.content_blocks:
        if block.get("type") == "tool_use" and block.get("name") == "emit_strategy":
            data = block.get("input") or {}
            code = data.get("code")
            if not isinstance(code, str) or not code.strip():
                raise GenerationError("tool output had no code")
            assumptions = data.get("assumptions") or []
            if not isinstance(assumptions, list):
                assumptions = [str(assumptions)]
            explanation = str(data.get("explanation", ""))
            return code, [str(a) for a in assumptions], explanation
    raise GenerationError("model did not emit the emit_strategy tool")


async def generate_strategy(
    session: AsyncSession, *, user_id: int, description: str
) -> GenerationResult:
    """Generate a strategy from a description. Raises BudgetExceededError /
    NoApiKeyError / GenerationError on the respective failures."""
    settings = get_settings()
    budget_usd = Decimal(str(settings.agent_daily_budget_usd))
    now = datetime.now(UTC)

    # Budget pre-gate (reuse the agent daily cap): agent spend + prior P7 spend +
    # this call's estimate must stay under the cap.
    agent_spent = await DailyBudgetResolver(budget_usd).spent_today(
        session, user_id=user_id, now=now
    )
    p7_spent = await _authoring_spent_today_usd(session, user_id, now)
    estimated = estimate_cost(GENERATION_MODEL, GEN_EST_INPUT_TOKENS, GEN_EST_OUTPUT_TOKENS)
    if agent_spent + p7_spent + estimated > budget_usd:
        raise BudgetExceededError(
            f"daily LLM budget ${budget_usd} would be exceeded "
            f"(spent ${agent_spent + p7_spent}, est ${estimated})"
        )

    api_key = await CredentialStore(session).get(user_id, CredentialKind.ANTHROPIC_API_KEY)
    if not api_key:
        raise NoApiKeyError("no Anthropic API key configured")

    call = await create_message(
        api_key=api_key,
        model=GENERATION_MODEL,
        system=GENERATION_SYSTEM,
        messages=[{"role": "user", "content": build_generation_user_message(description)}],
        tools=[STRATEGY_OUTPUT_TOOL],
        tool_choice={"type": "tool", "name": "emit_strategy"},
        max_tokens=4096,
    )
    code, assumptions, explanation = _parse_emit_strategy(call)
    cost_usd = estimate_cost(GENERATION_MODEL, call.input_tokens, call.output_tokens)

    AuditLogger.write(
        session,
        actor_type=AuditActorType.USER,
        actor_id=str(user_id),
        action=AuditAction.STRATEGY_GENERATED,
        target_type="strategy_authoring",
        target_id=None,
        payload={
            "description": description,
            "prompt_version": GENERATION_PROMPT_VERSION,
            "model": GENERATION_MODEL,
            "cost_usd": float(cost_usd),
            "assumptions": assumptions,
            "explanation": explanation,
            "code": code,
        },
        user_id=user_id,
    )
    await session.commit()
    logger.info(
        "strategy_generated", user_id=user_id, cost_usd=str(cost_usd),
        code_chars=len(code),
    )
    return GenerationResult(
        code=code, assumptions=assumptions, explanation=explanation,
        cost_usd=cost_usd, prompt_version=GENERATION_PROMPT_VERSION, model=GENERATION_MODEL,
    )
