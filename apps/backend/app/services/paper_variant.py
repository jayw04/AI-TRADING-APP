"""Paper-variant runner (P6b §2a-variant, ADR 0007).

Spawns / terminates a cloned ``strategies`` row that runs a proposal's params
forward on the user's paper account, in parallel with the LIVE parent. §2a is
the foundation only — NO comparison metrics (§2b), NO evidence bundle / gate /
promotion (§3).

Decisions (see the §2a-variant doc): variant = a cloned Strategy row with
``parent_strategy_id`` + ``status=PAPER_VARIANT`` (D1/D2); shared paper account
(D3); ``ACCEPTED → EVALUATING`` on spawn, ``→ REJECTED`` on terminate (D4); one
in-flight variant per parent (D7); two audit actions PAPER_VARIANT_SPAWNED /
PAPER_VARIANT_TERMINATED (D9).

Audit discipline: one row per transaction (the §1a-drift hash-chain contract) —
spawn and terminate each write their two audit rows in SEPARATE commits.
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit import AuditAction, AuditActorType, AuditLogger
from app.db.enums import StrategyStatus
from app.db.models.strategy import Strategy
from app.db.models.strategy_proposal import ProposalState, StrategyProposal
from app.services.proposal_evaluation import _apply_changes

logger = structlog.get_logger(__name__)

# D6 (iv): a variant older than this is force-terminated by the expiry sweep.
VARIANT_MAX_AGE_DAYS = 90


class PaperVariantService:
    def __init__(self, session: AsyncSession, engine: Any = None) -> None:
        self._session = session
        self._engine = engine  # app.state.strategy_engine; None in tests/data-only boots

    async def _in_flight_variant_for(self, parent_strategy_id: int) -> Strategy | None:
        return (
            await self._session.execute(
                select(Strategy)
                .where(Strategy.parent_strategy_id == parent_strategy_id)
                .where(Strategy.status == StrategyStatus.PAPER_VARIANT)
            )
        ).scalars().first()

    async def spawn(self, *, proposal_id: int, user_id: int) -> Strategy:
        """Clone the parent with the proposal's params, run it on paper, and
        move the proposal ACCEPTED → EVALUATING. Raises ValueError on guard
        failures (mapped to 400/409 by the endpoint)."""
        proposal = await self._session.get(StrategyProposal, proposal_id)
        if proposal is None or proposal.user_id != user_id:
            raise ValueError("proposal_not_found")
        if proposal.state != ProposalState.ACCEPTED:
            raise ValueError("proposal_not_accepted")
        parent = await self._session.get(Strategy, proposal.strategy_id)
        if parent is None or parent.user_id != user_id:
            raise ValueError("parent_not_found")
        if parent.status != StrategyStatus.LIVE:  # ADR 0007: live-strategy updates only
            raise ValueError("parent_not_live")
        if await self._in_flight_variant_for(parent.id) is not None:  # D7
            raise ValueError("variant_already_in_flight")

        changes = (proposal.proposal_payload_json or {}).get("changes") or []
        variant_params = _apply_changes(dict(parent.params_json or {}), changes)
        now = datetime.now(UTC)
        variant = Strategy(
            user_id=parent.user_id,
            name=f"{parent.name} (variant p{proposal_id})",
            version=parent.version,
            type=parent.type,
            code_path=parent.code_path,
            symbols_json=list(parent.symbols_json or []),
            params_json=variant_params,
            schedule=parent.schedule,
            status=StrategyStatus.PAPER_VARIANT,
            parent_strategy_id=parent.id,
            created_at=now,
            updated_at=now,
        )
        self._session.add(variant)
        await self._session.flush()  # variant.id

        # Commit 1: variant row + its spawn audit (one audit row this txn).
        AuditLogger.write(
            self._session,
            actor_type=AuditActorType.AGENT,
            actor_id="paper_variant",
            action=AuditAction.PAPER_VARIANT_SPAWNED,
            target_type="strategy",
            target_id=variant.id,
            payload={
                "proposal_id": proposal_id,
                "parent_strategy_id": parent.id,
                "variant_strategy_id": variant.id,
            },
            user_id=user_id,
        )
        await self._session.commit()

        # Commit 2: proposal ACCEPTED → EVALUATING + its transition audit.
        proposal.evaluation_results_json = {
            **(proposal.evaluation_results_json or {}),
            "paper_variant": {
                "variant_strategy_id": variant.id,
                "evaluation_started_at": now.isoformat(),
            },
        }
        proposal.state = ProposalState.EVALUATING
        proposal.transitioned_at = now
        proposal.updated_at = now
        AuditLogger.write(
            self._session,
            actor_type=AuditActorType.USER,
            actor_id=str(user_id),
            action=AuditAction.STRATEGY_PROPOSAL_TRANSITIONED,
            target_type="strategy_proposal",
            target_id=proposal.id,
            payload={"from": "ACCEPTED", "to": "EVALUATING", "variant_strategy_id": variant.id},
            user_id=user_id,
        )
        await self._session.commit()

        # Register AFTER commit (the engine opens its own session to read the row).
        if self._engine is not None:
            await self._engine.register(variant.id)
        return variant

    async def terminate(
        self, *, variant_strategy_id: int, reason: str, user_id: int
    ) -> None:
        """Stop a running variant, terminate its proposal (EVALUATING → REJECTED),
        and audit. Idempotent-ish: a missing/already-stopped variant is a no-op."""
        variant = await self._session.get(Strategy, variant_strategy_id)
        if variant is None or variant.parent_strategy_id is None:
            return

        # Engine unregister (its own session: cancels job, closes run, sets IDLE,
        # writes its own STRATEGY_UNREGISTERED audit — one row per txn).
        if self._engine is not None:
            await self._engine.unregister(variant.id, reason=f"paper_variant_{reason}")
        else:
            variant.status = StrategyStatus.IDLE
            variant.updated_at = datetime.now(UTC)

        # Commit: termination audit (one row this txn).
        AuditLogger.write(
            self._session,
            actor_type=AuditActorType.AGENT,
            actor_id="paper_variant",
            action=AuditAction.PAPER_VARIANT_TERMINATED,
            target_type="strategy",
            target_id=variant.id,
            payload={"reason": reason, "parent_strategy_id": variant.parent_strategy_id},
            user_id=user_id,
        )
        await self._session.commit()

        # Commit: proposal EVALUATING → REJECTED + its transition audit.
        proposal = (
            await self._session.execute(
                select(StrategyProposal)
                .where(StrategyProposal.strategy_id == variant.parent_strategy_id)
                .where(StrategyProposal.state == ProposalState.EVALUATING)
            )
        ).scalars().first()
        if proposal is not None:
            now = datetime.now(UTC)
            proposal.state = ProposalState.REJECTED
            proposal.transitioned_at = now
            proposal.updated_at = now
            AuditLogger.write(
                self._session,
                actor_type=AuditActorType.USER,
                actor_id=str(user_id),
                action=AuditAction.STRATEGY_PROPOSAL_TRANSITIONED,
                target_type="strategy_proposal",
                target_id=proposal.id,
                payload={"from": "EVALUATING", "to": "REJECTED", "reason": reason},
                user_id=user_id,
            )
            await self._session.commit()

    async def terminate_for_parent(
        self, *, parent_strategy_id: int, reason: str, user_id: int
    ) -> None:
        """Terminate the in-flight variant for a parent (D8 — e.g. another
        proposal applied to the parent). No-op if none."""
        v = await self._in_flight_variant_for(parent_strategy_id)
        if v is not None:
            await self.terminate(
                variant_strategy_id=v.id, reason=reason, user_id=user_id
            )


async def run_paper_variant_expiry(*, session_factory, engine=None) -> dict[str, int]:
    """D6 (iv) safety sweep: terminate PAPER_VARIANT clones older than
    VARIANT_MAX_AGE_DAYS. Prevents zombie variants (e.g. a parent that left LIVE
    without an explicit termination)."""
    cutoff = datetime.now(UTC) - timedelta(days=VARIANT_MAX_AGE_DAYS)
    terminated = 0
    async with session_factory() as session:
        variants = (
            await session.execute(
                select(Strategy)
                .where(Strategy.status == StrategyStatus.PAPER_VARIANT)
                .where(Strategy.created_at < cutoff)
            )
        ).scalars().all()
        svc = PaperVariantService(session, engine)
        for v in variants:
            await svc.terminate(
                variant_strategy_id=v.id, reason="expired", user_id=v.user_id
            )
            terminated += 1
    logger.info("paper_variant_expiry_sweep", terminated=terminated)
    return {"terminated": terminated}


def register_paper_variant_expiry_job(scheduler, session_factory, engine) -> None:
    """Register the 6-hourly variant-expiry sweep on the APScheduler instance
    (WorkbenchScheduler.scheduler), inside the alpaca-enabled boot block."""
    from apscheduler.triggers.interval import IntervalTrigger

    scheduler.add_job(
        run_paper_variant_expiry,
        IntervalTrigger(hours=6),
        kwargs={"session_factory": session_factory, "engine": engine},
        id="paper_variant_expiry",
        max_instances=1,
        coalesce=True,
        replace_existing=True,
    )
    logger.info("paper_variant_expiry_job_registered")
