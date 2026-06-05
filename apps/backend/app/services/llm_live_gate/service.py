"""LLM-opt-in lifecycle (P6b §5, ADR 0006 v2 §5).

initiate (typed-ack + TOTP, eligibility-gated) → pending (7-day cooldown) →
[cron] active (LLM gate live) ; opt-out is frictionless from pending|active.
Mirrors ``ActivationService``. The engine wrap is applied/dropped by a strategy
re-register on activate / opt-out (the §4.5 + §5 wraps are rebuilt at register).
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit import AuditAction, AuditActorType, AuditLogger
from app.db.enums import StrategyStatus
from app.db.models.llm_opt_in import (
    OPT_IN_ACTIVE,
    OPT_IN_OPTED_OUT,
    OPT_IN_PENDING,
    LLMOptIn,
)
from app.db.models.strategy import Strategy
from app.security import CredentialKind, CredentialStore
from app.services.eval_harness.eligibility import check_eligibility
from app.services.eval_harness.service import find_active_harness
from app.services.llm_live_gate.gate import (
    DEFAULT_LIVE_DAILY_CAP_CENTS,
    LLM_OPT_IN_COOLDOWN_DAYS,
)
from app.utils.time import ensure_aware

logger = structlog.get_logger(__name__)

# The exact typed risk-acknowledgment phrase (normalized compare, like the
# typed-symbol confirmation). Recorded on the opt-in row.
RISK_ACK_PHRASE = (
    "I understand LLM-driven trading is non-deterministic and I accept the risk"
)


def _normalize(text: str) -> str:
    return " ".join(text.strip().lower().split())


async def find_non_terminal_opt_in(
    session: AsyncSession, strategy_id: int
) -> LLMOptIn | None:
    """The pending|active opt-in for a strategy, or None (at most one)."""
    return (
        await session.execute(
            select(LLMOptIn)
            .where(LLMOptIn.strategy_id == strategy_id)
            .where(LLMOptIn.state != OPT_IN_OPTED_OUT)
        )
    ).scalars().first()


async def initiate_opt_in(
    session: AsyncSession,
    *,
    strategy_id: int,
    user_id: int,
    acknowledgment_text: str,
    totp_code: str,
) -> LLMOptIn:
    """Start an opt-in (state=pending, 7-day cooldown). Raises ValueError on guard
    failures. No engine change — the LLM gate switches on at activation."""
    strategy = await session.get(Strategy, strategy_id)
    if strategy is None or strategy.user_id != user_id:
        raise ValueError("strategy_not_found")
    if strategy.status != StrategyStatus.LIVE:
        raise ValueError("parent_not_live")

    # Eligibility (§4 double-floor) — the opt-in flow refuses to render otherwise.
    harness = await find_active_harness(session, strategy_id)
    if harness is None:
        raise ValueError("no_eligible_harness")
    verdict = await check_eligibility(session, harness)
    if not verdict.eligible:
        raise ValueError("no_eligible_harness")

    if await find_non_terminal_opt_in(session, strategy_id) is not None:
        raise ValueError("opt_in_already_active")

    if _normalize(acknowledgment_text) != _normalize(RISK_ACK_PHRASE):
        raise ValueError("acknowledgment_mismatch")

    from app.auth.totp import verify_code

    secret = await CredentialStore(session).get(user_id, CredentialKind.TOTP_SECRET)
    if secret is None or not verify_code(secret, totp_code):
        raise ValueError("totp_invalid")

    now = datetime.now(UTC)
    opt_in = LLMOptIn(
        user_id=user_id,
        strategy_id=strategy_id,
        strategy_version=strategy.version,
        state=OPT_IN_PENDING,
        acknowledgment_text=acknowledgment_text,
        daily_cap_cents=DEFAULT_LIVE_DAILY_CAP_CENTS,
        initiated_at=now,
        created_at=now,
        updated_at=now,
    )
    session.add(opt_in)
    await session.flush()
    AuditLogger.write(
        session,
        actor_type=AuditActorType.USER,
        actor_id=str(user_id),
        action=AuditAction.LLM_OPT_IN_INITIATED,
        target_type="strategy",
        target_id=strategy_id,
        payload={
            "opt_in_id": opt_in.id,
            "strategy_id": strategy_id,
            "strategy_version": strategy.version,
            "initiated_at": now.isoformat(),
            "activates_at": (now + timedelta(days=LLM_OPT_IN_COOLDOWN_DAYS)).isoformat(),
        },
        user_id=user_id,
    )
    await session.commit()
    logger.info("llm_opt_in_initiated", strategy_id=strategy_id, user_id=user_id)
    return opt_in


async def opt_out(
    session: AsyncSession,
    *,
    strategy_id: int,
    user_id: int,
    engine: Any = None,
    reason: str = "user_opted_out",
) -> None:
    """Frictionless opt-out (no cooldown). pending|active → opted_out. If it was
    active, re-register the strategy so the LLM wrap is dropped (the deterministic
    strategy resumes live duty)."""
    opt_in = await find_non_terminal_opt_in(session, strategy_id)
    if opt_in is None:
        raise ValueError("opt_in_not_found")
    if opt_in.user_id != user_id:
        raise ValueError("opt_in_not_found")
    was_active = opt_in.state == OPT_IN_ACTIVE
    now = datetime.now(UTC)
    opt_in.state = OPT_IN_OPTED_OUT
    opt_in.opted_out_at = now
    opt_in.opted_out_reason = reason
    opt_in.updated_at = now
    AuditLogger.write(
        session,
        actor_type=AuditActorType.USER,
        actor_id=str(user_id),
        action=AuditAction.LLM_OPT_OUT,
        target_type="strategy",
        target_id=strategy_id,
        payload={"opt_in_id": opt_in.id, "reason": reason, "was_active": was_active},
        user_id=user_id,
    )
    await session.commit()
    if was_active and engine is not None:
        await engine.unregister(strategy_id, reason="llm_opt_out")
        await engine.register(strategy_id)
    logger.info("llm_opt_out", strategy_id=strategy_id, reason=reason)


async def complete_pending_opt_in(
    session: AsyncSession, *, opt_in_id: int, engine: Any = None
) -> bool:
    """Cron entry point. pending + 7d elapsed + still version-matched + LIVE →
    active (re-register so the LLM gate applies). If the version drifted or the
    strategy left LIVE during the window → opted_out (invalidated)."""
    opt_in = await session.get(LLMOptIn, opt_in_id)
    if opt_in is None or opt_in.state != OPT_IN_PENDING:
        return False
    now = datetime.now(UTC)
    initiated = ensure_aware(opt_in.initiated_at)
    assert initiated is not None
    if now - initiated < timedelta(days=LLM_OPT_IN_COOLDOWN_DAYS):
        return False

    strategy = await session.get(Strategy, opt_in.strategy_id)
    invalid = (
        strategy is None
        or strategy.status != StrategyStatus.LIVE
        or strategy.version != opt_in.strategy_version
    )
    if invalid:
        opt_in.state = OPT_IN_OPTED_OUT
        opt_in.opted_out_at = now
        opt_in.opted_out_reason = "invalidated"
        opt_in.updated_at = now
        AuditLogger.write(
            session,
            actor_type=AuditActorType.SYSTEM,
            actor_id="llm_opt_in_completion",
            action=AuditAction.LLM_OPT_OUT,
            target_type="strategy",
            target_id=opt_in.strategy_id,
            payload={"opt_in_id": opt_in.id, "reason": "invalidated"},
            user_id=opt_in.user_id,
        )
        await session.commit()
        return False

    opt_in.state = OPT_IN_ACTIVE
    opt_in.activated_at = now
    opt_in.updated_at = now
    AuditLogger.write(
        session,
        actor_type=AuditActorType.SYSTEM,
        actor_id="llm_opt_in_completion",
        action=AuditAction.LLM_OPT_IN_ACTIVATED,
        target_type="strategy",
        target_id=opt_in.strategy_id,
        payload={"opt_in_id": opt_in.id, "activated_at": now.isoformat()},
        user_id=opt_in.user_id,
    )
    await session.commit()
    if engine is not None:
        await engine.unregister(opt_in.strategy_id, reason="llm_opt_in_activated")
        await engine.register(opt_in.strategy_id)
    logger.info("llm_opt_in_activated", strategy_id=opt_in.strategy_id)
    return True
