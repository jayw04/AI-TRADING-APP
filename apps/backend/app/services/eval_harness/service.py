"""Eval-harness lifecycle (P6b §4, ADR 0006 v2).

start: mutual-exclusion guards → spawn Mode A (running PAPER_VARIANT clone) +
Mode B (IDLE source_id bucket) + the harness row → register Mode A with the
engine (its wrapped submit_order_fn drives B). stop / invalidation: unregister
Mode A and mark the harness terminated (the Mode A/B rows + their orders stay as
read-only data for the metrics).
"""
from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit import AuditAction, AuditActorType, AuditLogger
from app.db.enums import StrategyStatus
from app.db.models.eval_harness import (
    HARNESS_ACTIVE,
    HARNESS_TERMINATED,
    EvalHarness,
)
from app.db.models.strategy import Strategy
from app.services.paper_variant import find_in_flight_variant

logger = structlog.get_logger(__name__)


async def find_active_harness(
    session: AsyncSession, parent_strategy_id: int
) -> EvalHarness | None:
    """The non-terminated harness for a parent strategy, or None (at most one)."""
    return (
        await session.execute(
            select(EvalHarness)
            .where(EvalHarness.parent_strategy_id == parent_strategy_id)
            .where(EvalHarness.state != HARNESS_TERMINATED)
        )
    ).scalars().first()


def _clone_for_harness(
    parent: Strategy, *, role: str, status: StrategyStatus, now: datetime
) -> Strategy:
    """Clone the parent for a harness mode. Mode A runs (PAPER_VARIANT); Mode B
    is an IDLE bucket. Identical params; the engine resolves the paper account."""
    return Strategy(
        user_id=parent.user_id,
        name=f"{parent.name} (eval {role})",
        version=parent.version,
        type=parent.type,
        code_path=parent.code_path,
        symbols_json=list(parent.symbols_json or []),
        params_json=dict(parent.params_json or {}),
        schedule=parent.schedule,
        status=status,
        parent_strategy_id=parent.id,
        harness_role=role,
        created_at=now,
        updated_at=now,
    )


async def start_eval_harness(
    session: AsyncSession,
    *,
    parent_strategy_id: int,
    user_id: int,
    engine: Any = None,
) -> EvalHarness:
    """Start an LLM eval (ADR 0006 v2). Raises ValueError on guard failures."""
    parent = await session.get(Strategy, parent_strategy_id)
    if parent is None or parent.user_id != user_id:
        raise ValueError("parent_not_found")
    if parent.status != StrategyStatus.LIVE:
        raise ValueError("parent_not_live")

    # Mutual exclusion (Q2): no §2 paper-variant + no existing harness.
    if await find_in_flight_variant(session, parent_strategy_id) is not None:
        raise ValueError("paper_variant_in_flight")
    if await find_active_harness(session, parent_strategy_id) is not None:
        raise ValueError("eval_harness_already_active")

    now = datetime.now(UTC)
    mode_a = _clone_for_harness(
        parent, role="mode_a", status=StrategyStatus.PAPER_VARIANT, now=now
    )
    mode_b = _clone_for_harness(
        parent, role="mode_b", status=StrategyStatus.IDLE, now=now
    )
    session.add(mode_a)
    session.add(mode_b)
    await session.flush()  # ids for the harness FKs

    harness = EvalHarness(
        user_id=user_id,
        parent_strategy_id=parent_strategy_id,
        mode_a_strategy_id=mode_a.id,
        mode_b_strategy_id=mode_b.id,
        state=HARNESS_ACTIVE,
        started_at=now,
    )
    session.add(harness)
    await session.flush()

    AuditLogger.write(
        session,
        actor_type=AuditActorType.USER,
        actor_id=str(user_id),
        action=AuditAction.EVAL_HARNESS_STARTED,
        target_type="eval_harness",
        target_id=harness.id,
        payload={
            "harness_id": harness.id,
            "parent_strategy_id": parent_strategy_id,
            "mode_a_strategy_id": mode_a.id,
            "mode_b_strategy_id": mode_b.id,
            "started_at": now.isoformat(),
        },
        user_id=user_id,
    )
    await session.commit()

    # Register Mode A AFTER commit (the engine opens its own session and looks up
    # the now-committed harness to inject the wrapped submit_order_fn). Mode B is
    # never registered — it's an IDLE bucket.
    if engine is not None:
        await engine.register(mode_a.id)
    return harness


async def _terminate(
    session: AsyncSession, harness: EvalHarness, *, engine: Any, reason: str
) -> None:
    """Stop Mode A running + mark the harness terminated. Idempotent."""
    if harness.state == HARNESS_TERMINATED:
        return
    if engine is not None:
        await engine.unregister(harness.mode_a_strategy_id, reason=f"eval_harness_{reason}")
    else:
        mode_a = await session.get(Strategy, harness.mode_a_strategy_id)
        if mode_a is not None:
            mode_a.status = StrategyStatus.IDLE
            mode_a.updated_at = datetime.now(UTC)
    harness.state = HARNESS_TERMINATED
    harness.terminated_at = datetime.now(UTC)
    harness.terminated_reason = reason
    await session.commit()
    logger.info("eval_harness_terminated", harness_id=harness.id, reason=reason)


async def stop_eval_harness(
    session: AsyncSession,
    *,
    harness_id: int,
    user_id: int,
    engine: Any = None,
    reason: str = "user_stopped",
) -> None:
    """User-initiated stop. Stop/terminate is a state change on the row (no
    separate audit action, per Q10)."""
    harness = await session.get(EvalHarness, harness_id)
    if harness is None or harness.user_id != user_id:
        raise ValueError("harness_not_found")
    await _terminate(session, harness, engine=engine, reason=reason)


async def terminate_harness_for_parent(
    session: AsyncSession,
    *,
    parent_strategy_id: int,
    engine: Any = None,
    reason: str,
) -> None:
    """Auto-invalidation hook (parent left LIVE / params modified). No-op if no
    active harness."""
    harness = await find_active_harness(session, parent_strategy_id)
    if harness is not None:
        await _terminate(session, harness, engine=engine, reason=reason)
