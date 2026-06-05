"""Global live-auto-dispatch master switch + the per-order suppression wrap
(P6b §4.5, ADR 0015).

The switch is a durable ``system_config`` flag (mirroring ``app/risk/halt.py``),
defaulting OFF: until an operator turns it on, a LIVE strategy's *automatic*
orders are suppressed before the broker. Manual live orders (Trade page) never
pass through this wrap and are unaffected.

The wrap is checked PER ORDER (not at register time) so flipping the switch off
halts dispatch on the very next order without re-registering every live strategy.
It is built as a standalone factory so the §5 LLM gate nests cleanly inside it
(master switch outermost → an off switch skips the LLM call entirely).
"""
from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.audit import AuditAction, AuditActorType, AuditLogger
from app.db.models.system_config import SystemConfig
from app.risk import OrderRequest
from app.risk.reason_codes import ReasonCode

logger = structlog.get_logger(__name__)

LIVE_AUTODISPATCH_KEY = "trading.live_autodispatch_enabled"

SubmitFn = Callable[[OrderRequest], Awaitable[Any]]


def _truthy(value: str | None) -> bool:
    return bool(value and str(value).strip().lower() in ("1", "true", "yes", "on"))


async def is_live_autodispatch_enabled(session: AsyncSession) -> bool:
    """The global master switch. Absent row → False (default OFF, ADR 0015)."""
    row = (
        await session.execute(
            select(SystemConfig).where(SystemConfig.key == LIVE_AUTODISPATCH_KEY)
        )
    ).scalars().first()
    return _truthy(row.value if row else None)


async def set_live_autodispatch_enabled(
    session: AsyncSession, enabled: bool, *, actor_user_id: int
) -> None:
    """Flip the master switch (upsert) + audit. Caller commits."""
    row = (
        await session.execute(
            select(SystemConfig).where(SystemConfig.key == LIVE_AUTODISPATCH_KEY)
        )
    ).scalars().first()
    if row is None:
        session.add(SystemConfig(key=LIVE_AUTODISPATCH_KEY, value="1" if enabled else "0"))
    else:
        row.value = "1" if enabled else "0"

    AuditLogger.write(
        session,
        actor_type=AuditActorType.USER,
        actor_id=str(actor_user_id),
        action=AuditAction.LIVE_AUTODISPATCH_ENABLED_CHANGED,
        target_type="system_config",
        target_id=LIVE_AUTODISPATCH_KEY,
        payload={"enabled": enabled, "actor_user_id": actor_user_id},
        user_id=actor_user_id,
    )
    logger.warning("live_autodispatch_state_changed", enabled=enabled, actor_user_id=actor_user_id)


def make_live_autodispatch_submit_fn(
    *,
    strategy_id: int,
    real_submit: SubmitFn,
    session_factory: async_sessionmaker[AsyncSession],
) -> SubmitFn:
    """Wrap a LIVE strategy's submit so that, while the master switch is OFF, its
    automatic orders are suppressed (a non-persisted REJECTED order is returned,
    never sent to the broker)."""

    async def _submit(order_request: OrderRequest) -> Any:
        async with session_factory() as session:
            enabled = await is_live_autodispatch_enabled(session)
        if not enabled:
            logger.warning(
                "live_autodispatch_suppressed",
                strategy_id=strategy_id,
                symbol=order_request.symbol_ticker,
            )
            # Import here to avoid a module-load cycle (router imports the risk
            # engine; this module is imported by the engine).
            from app.orders.router import _ephemeral_rejected_order_with_reason

            return _ephemeral_rejected_order_with_reason(
                order_request, ReasonCode.LIVE_AUTODISPATCH_DISABLED.value
            )
        return await real_submit(order_request)

    return _submit
