"""Background job: complete PENDING_LIVE → LIVE transitions after 24h (P5 §7).

Runs every 60s. Idempotent: if the backend was down when the 24h mark elapsed,
the first run after restart catches it up. Processes all eligible strategies in
one pass; each transition is one row update + one audit row.
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import structlog
from sqlalchemy import select

from app.db.enums import StrategyStatus
from app.db.models.strategy import Strategy
from app.services.activation import ACTIVATION_COOLDOWN_HOURS, ActivationService

logger = structlog.get_logger(__name__)


async def run_activation_completion(session_factory: Any, bus: Any = None) -> int:
    """Find PENDING_LIVE strategies whose 24h has elapsed; transition each.
    Returns the count of transitions performed."""
    cutoff = datetime.now(UTC) - timedelta(hours=ACTIVATION_COOLDOWN_HOURS)
    async with session_factory() as session:
        eligible = (
            await session.execute(
                select(Strategy.id)
                .where(Strategy.status == StrategyStatus.PENDING_LIVE)
                .where(Strategy.live_activation_initiated_at.isnot(None))
                .where(Strategy.live_activation_initiated_at <= cutoff)
            )
        ).scalars().all()

    transitioned = 0
    for strategy_id in eligible:
        async with session_factory() as session:
            svc = ActivationService(session=session, bus=bus)
            try:
                if await svc.complete_pending(strategy_id):
                    transitioned += 1
            except Exception:
                logger.exception("activation_completion_failed", strategy_id=strategy_id)

    if transitioned:
        logger.info("activation_completion_pass", transitioned=transitioned)
    return transitioned
