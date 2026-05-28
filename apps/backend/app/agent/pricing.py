"""Pricing table + cost-estimation helpers.

Pricing is hardcoded, not fetched dynamically. Page-scraping on every
request is wasteful and creates a hidden dependency. The cost of this
design is that pricing changes require a code change — which is correct,
because pricing changes ARE a deliberate config change worth committing.

When Anthropic publishes new rates, update :data:`PRICING_TABLE` and
verify against https://www.anthropic.com/pricing (the prices live under
each model card on the API tab).

Unknown model ids return :data:`UNKNOWN_MODEL_PRICING` (high estimate)
so a typo doesn't silently bypass the cap. The Session 3 runtime should
refuse to use a model that's not in the table.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import ROUND_HALF_UP, Decimal

import structlog
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

logger = structlog.get_logger(__name__)


@dataclass(frozen=True)
class ModelPricing:
    """Per-million-token pricing for one model.

    Verify against https://www.anthropic.com/pricing before each release.
    Last verified: 2026-01 (Claude 4.7 model family launch).
    """

    input_per_million_usd: Decimal
    output_per_million_usd: Decimal


# Pricing keyed by API model id, NOT by family name. The API id is what
# AgentSession.model stores.
PRICING_TABLE: dict[str, ModelPricing] = {
    # Verify before launch — placeholder Jan 2026 values.
    "claude-haiku-4-5-20251001": ModelPricing(
        input_per_million_usd=Decimal("0.80"),
        output_per_million_usd=Decimal("4.00"),
    ),
    "claude-sonnet-4-6": ModelPricing(
        input_per_million_usd=Decimal("3.00"),
        output_per_million_usd=Decimal("15.00"),
    ),
    "claude-opus-4-7": ModelPricing(
        input_per_million_usd=Decimal("15.00"),
        output_per_million_usd=Decimal("75.00"),
    ),
}


# Used when a session lands on a model id we don't recognize. We
# overcharge rather than undercharge so the cap fires earlier rather
# than later — better a session capped too soon than a runaway bill.
UNKNOWN_MODEL_PRICING = ModelPricing(
    input_per_million_usd=Decimal("15.00"),
    output_per_million_usd=Decimal("75.00"),
)


def get_pricing(model: str) -> ModelPricing:
    """Return pricing for ``model``, or :data:`UNKNOWN_MODEL_PRICING`.

    Logs a warning when the model isn't in the table so it surfaces in
    operations.
    """
    pricing = PRICING_TABLE.get(model)
    if pricing is None:
        logger.warning("agent_pricing_unknown_model", model=model)
        return UNKNOWN_MODEL_PRICING
    return pricing


def estimate_cost(
    model: str,
    input_tokens: int,
    output_tokens: int,
) -> Decimal:
    """USD cost for one API call, rounded to $0.0001 precision.

    Zero or negative token counts return ``Decimal("0")``; they typically
    indicate a streaming response where usage wasn't reported.
    """
    if input_tokens <= 0 and output_tokens <= 0:
        return Decimal("0")
    pricing = get_pricing(model)
    input_cost = (
        Decimal(max(0, input_tokens)) * pricing.input_per_million_usd
    ) / Decimal("1000000")
    output_cost = (
        Decimal(max(0, output_tokens)) * pricing.output_per_million_usd
    ) / Decimal("1000000")
    total = input_cost + output_cost
    return total.quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)


class DailyBudgetResolver:
    """Computes a user's remaining daily budget across all agent sessions.

    Constructed with the user's configured budget (read from settings at
    session start, stamped onto the ``AgentSession`` row). Each call to
    :meth:`remaining` queries today's cumulative spend across ALL the
    user's sessions started today — both ACTIVE and terminal ones, since
    capped/ended sessions still count against today's budget.
    """

    def __init__(self, daily_budget_usd: Decimal) -> None:
        self.daily_budget_usd = daily_budget_usd

    async def spent_today(
        self,
        session: AsyncSession,
        *,
        user_id: int,
        now: datetime | None = None,
    ) -> Decimal:
        """Total cost of all sessions for ``user_id`` started today (UTC)."""
        from app.db.models.agent_session import AgentSession as AgentSessionRow

        if now is None:
            now = datetime.now(UTC)
        start_of_day = now.replace(hour=0, minute=0, second=0, microsecond=0)

        result = await session.execute(
            select(
                func.coalesce(func.sum(AgentSessionRow.total_cost_usd), 0)
            ).where(
                AgentSessionRow.user_id == user_id,
                AgentSessionRow.started_at >= start_of_day,
            )
        )
        spent = result.scalar() or Decimal("0")
        # Coerce to Decimal (SQLite may return float for SUM()).
        return Decimal(str(spent)).quantize(Decimal("0.0001"))

    async def remaining(
        self,
        session: AsyncSession,
        *,
        user_id: int,
        now: datetime | None = None,
    ) -> Decimal:
        """Remaining budget. Can be negative if ``spent_today`` exceeded the
        budget between checks (race window with post-call cap enforcement)."""
        spent = await self.spent_today(session, user_id=user_id, now=now)
        return (self.daily_budget_usd - spent).quantize(Decimal("0.0001"))

    async def would_exceed(
        self,
        session: AsyncSession,
        *,
        user_id: int,
        estimated_cost: Decimal,
        now: datetime | None = None,
    ) -> bool:
        """``True`` if the next call's estimated cost would push the user
        over the daily cap.

        Caller uses this to refuse a request before sending it to
        Anthropic. After the response arrives, the runtime updates
        ``session.total_cost_usd`` from real usage — that's the
        post-call accounting; this is the pre-call gate.
        """
        spent = await self.spent_today(session, user_id=user_id, now=now)
        return (spent + estimated_cost) > self.daily_budget_usd
