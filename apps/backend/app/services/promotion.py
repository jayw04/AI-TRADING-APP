"""Promotion action service (P6b §3b-promote, ADR 0007).

The mechanical PROMOTING → PROMOTED action (called by the cooldown cron) + the
30-day post-promotion lockout helpers (used by the promote endpoint and the
/validate spawn guard).

Promotion is ALWAYS user-gated (ADR 0007 forbids auto-promotion); there is no
envelope flag here. The user clicks promote → EVIDENCE_READY → PROMOTING (24h
cooldown) → the cron applies the params and flips → PROMOTED.

v1 deviation from ADR 0007's literal "old variant archived as a strategy version"
model: on PROMOTED we merge the proposal's param changes into the parent strategy
(same `_apply_changes` merge as apply_proposal / spawn) and terminate the paper
variant. The audit log + the proposal record preserve the history; full
strategy-version archiving is deferred to a future ADR-faithful session.
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit import AuditAction, AuditActorType, AuditLogger
from app.db.enums import StrategyStatus
from app.db.models.strategy import Strategy
from app.db.models.strategy_proposal import ProposalState, StrategyProposal
from app.services.paper_variant import PaperVariantService
from app.services.proposal_evaluation import _apply_changes

logger = structlog.get_logger(__name__)

# Per ADR 0007: "locked in STABLE for at least 30 days." Not envelope-tunable
# (same posture as the non-configurable positive-return floor).
PROMOTION_LOCKOUT_DAYS = 30


def _aware(dt: datetime) -> datetime:
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=UTC)


def lockout_expires_at(parent: Strategy) -> datetime | None:
    """When the 30-day post-promotion lockout ends, or None if never promoted."""
    if parent.last_promoted_at is None:
        return None
    return _aware(parent.last_promoted_at) + timedelta(days=PROMOTION_LOCKOUT_DAYS)


def in_lockout(parent: Strategy, now: datetime) -> bool:
    """True iff the parent is within its 30-day post-promotion lockout window."""
    expires = lockout_expires_at(parent)
    return expires is not None and expires > now


async def execute_mechanical_promote(
    session: AsyncSession, *, proposal: StrategyProposal, engine: Any = None
) -> bool:
    """PROMOTING → PROMOTED: terminate the variant, merge the proposal's params
    into the parent, set ``last_promoted_at``, and write the audit rows. Returns
    True if promoted, False if skipped (raced out of PROMOTING). Raises on a
    parent that left LIVE during cooldown (the cron logs + isolates).

    Audit discipline (one row per transaction): terminate's PAPER_VARIANT_
    TERMINATED row commits on its own; then PROMOTING→PROMOTED transition +
    params merge commit together (one audit row); then the STRATEGY_PROMOTED
    marker commits on its own.
    """
    # Race re-check (manual cancel may have moved it out of PROMOTING).
    if proposal.state != ProposalState.PROMOTING:
        return False

    parent = await session.get(Strategy, proposal.strategy_id)
    if parent is None:
        raise ValueError(f"parent strategy {proposal.strategy_id} not found")
    if parent.status != StrategyStatus.LIVE:
        # Parent left LIVE during cooldown (manual deactivate). Abort — leave the
        # proposal PROMOTING; the cron isolates and the user can reject manually.
        raise ValueError(
            f"parent strategy {parent.id} no longer LIVE "
            f"(status={parent.status.value}); promotion aborted"
        )

    now = datetime.now(UTC)

    # Terminate the paper variant (cooldown done; it has served its purpose).
    # No-op if already gone. Commits its own PAPER_VARIANT_TERMINATED row.
    await PaperVariantService(session, engine).terminate_for_parent(
        parent_strategy_id=parent.id, reason="promoted", user_id=proposal.user_id
    )

    # Commit 1: apply params + last_promoted_at + PROMOTING→PROMOTED + audit.
    changes = (proposal.proposal_payload_json or {}).get("changes") or []
    parent.params_json = _apply_changes(dict(parent.params_json or {}), changes)
    parent.last_promoted_at = now
    parent.updated_at = now
    proposal.state = ProposalState.PROMOTED
    proposal.transitioned_at = now
    proposal.updated_at = now
    AuditLogger.write(
        session,
        actor_type=AuditActorType.SYSTEM,
        actor_id="promotion_completion",
        action=AuditAction.STRATEGY_PROPOSAL_TRANSITIONED,
        target_type="strategy_proposal",
        target_id=proposal.id,
        payload={
            "proposal_id": proposal.id,
            "from": "PROMOTING",
            "to": "PROMOTED",
            "trigger": "cooldown_elapsed",
            "completed_at": now.isoformat(),
        },
        user_id=proposal.user_id,
    )
    await session.commit()

    # Commit 2: the STRATEGY_PROMOTED marker (separate row per hash-chain).
    AuditLogger.write(
        session,
        actor_type=AuditActorType.SYSTEM,
        actor_id="promotion_completion",
        action=AuditAction.STRATEGY_PROMOTED,
        target_type="strategy",
        target_id=parent.id,
        payload={
            "parent_strategy_id": parent.id,
            "proposal_id": proposal.id,
            "promoted_at": now.isoformat(),
            "applied_changes": changes,
        },
        user_id=proposal.user_id,
    )
    await session.commit()
    logger.info("strategy_promoted", strategy_id=parent.id, proposal_id=proposal.id)
    return True
