"""Background job: complete PROMOTING → PROMOTED after the 24h cooldown (P6b §3b).

Mirrors ``app/jobs/activation_completion.py`` (PENDING_LIVE → LIVE): collect the
elapsed ids, then a fresh session per item (no row locking — SQLite serializes
writes; a re-check inside the loop handles the cancel race). The cooldown anchor
is the proposal's ``transitioned_at`` (set when it entered PROMOTING — nothing
else transitions a PROMOTING proposal except this cron or a manual cancel).
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import structlog
from sqlalchemy import select

from app.db.models.strategy_proposal import ProposalState, StrategyProposal
from app.services.activation import ACTIVATION_COOLDOWN_HOURS
from app.services.promotion import execute_mechanical_promote

logger = structlog.get_logger(__name__)


def _aware(dt: datetime) -> datetime:
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=UTC)


async def run_promotion_completion(
    *, session_factory: Any, engine: Any = None
) -> dict[str, int]:
    """Find PROMOTING proposals whose 24h cooldown has elapsed; promote each.
    Returns ``{"promoted": n, "errored": n}``."""
    now = datetime.now(UTC)
    cooldown = timedelta(hours=ACTIVATION_COOLDOWN_HOURS)

    async with session_factory() as session:
        rows = (
            await session.execute(
                select(StrategyProposal.id, StrategyProposal.transitioned_at)
                .where(StrategyProposal.state == ProposalState.PROMOTING)
                .where(StrategyProposal.transitioned_at.isnot(None))
            )
        ).all()
    elapsed_ids = [
        pid for pid, ts in rows if ts is not None and _aware(ts) + cooldown <= now
    ]

    promoted = errored = 0
    for proposal_id in elapsed_ids:
        async with session_factory() as session:
            proposal = await session.get(StrategyProposal, proposal_id)
            # Re-check: a manual cancel may have moved it out of PROMOTING.
            if proposal is None or proposal.state != ProposalState.PROMOTING:
                continue
            try:
                if await execute_mechanical_promote(
                    session, proposal=proposal, engine=engine
                ):
                    promoted += 1
            except Exception:
                logger.exception(
                    "promotion_completion_failed", proposal_id=proposal_id
                )
                await session.rollback()
                errored += 1

    if promoted or errored:
        logger.info(
            "promotion_completion_pass", promoted=promoted, errored=errored
        )
    return {"promoted": promoted, "errored": errored}
