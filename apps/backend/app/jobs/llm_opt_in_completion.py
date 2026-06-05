"""Background job: complete LLM-opt-in PENDING → ACTIVE after the 7-day cooldown
(P6b §5, ADR 0006 v2 §5).

Mirrors ``activation_completion`` (15-min interval; idempotent across restarts).
Each completion re-registers the strategy so the LLM gate applies. If the
strategy left LIVE or its version drifted during the window, the opt-in is
invalidated (opted_out) instead.
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import structlog
from sqlalchemy import select

from app.db.models.llm_opt_in import OPT_IN_PENDING, LLMOptIn
from app.services.llm_live_gate.gate import LLM_OPT_IN_COOLDOWN_DAYS
from app.services.llm_live_gate.service import complete_pending_opt_in

logger = structlog.get_logger(__name__)


async def run_llm_opt_in_completion(session_factory: Any, engine: Any = None) -> int:
    """Find pending opt-ins whose 7-day cooldown has elapsed; complete each.
    Returns the count of activations performed."""
    cutoff = datetime.now(UTC) - timedelta(days=LLM_OPT_IN_COOLDOWN_DAYS)
    async with session_factory() as session:
        eligible = (
            await session.execute(
                select(LLMOptIn.id)
                .where(LLMOptIn.state == OPT_IN_PENDING)
                .where(LLMOptIn.initiated_at <= cutoff)
            )
        ).scalars().all()

    activated = 0
    for opt_in_id in eligible:
        async with session_factory() as session:
            try:
                if await complete_pending_opt_in(
                    session, opt_in_id=opt_in_id, engine=engine
                ):
                    activated += 1
            except Exception:
                logger.exception("llm_opt_in_completion_failed", opt_in_id=opt_in_id)

    if activated:
        logger.info("llm_opt_in_completion_pass", activated=activated)
    return activated
