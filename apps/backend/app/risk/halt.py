"""System halt flag — durable across restarts via system_config.

When the daily-loss cap trips, the Risk Engine sets the halt flag and any
subsequent order is rejected with HALT_REACHED until the flag is cleared.
Lives in the existing system_config table (P0) so a freshly-started backend
doesn't blindly accept orders after a halt event.
"""

from __future__ import annotations

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.system_config import SystemConfig

logger = structlog.get_logger(__name__)

HALT_KEY = "trading.halted"
HALT_REASON_KEY = "trading.halt_reason"


def _truthy(value: str | None) -> bool:
    return bool(value and str(value).strip().lower() in ("1", "true", "yes", "on"))


async def is_halted(session: AsyncSession) -> bool:
    row = (
        await session.execute(select(SystemConfig).where(SystemConfig.key == HALT_KEY))
    ).scalars().first()
    return _truthy(row.value if row else None)


async def set_halted(session: AsyncSession, halted: bool, reason: str = "") -> None:
    """Set or clear the halt flag. Caller must commit."""
    row = (
        await session.execute(select(SystemConfig).where(SystemConfig.key == HALT_KEY))
    ).scalars().first()
    if row is None:
        session.add(SystemConfig(key=HALT_KEY, value="1" if halted else "0"))
    else:
        row.value = "1" if halted else "0"

    reason_row = (
        await session.execute(
            select(SystemConfig).where(SystemConfig.key == HALT_REASON_KEY)
        )
    ).scalars().first()
    if reason_row is None:
        session.add(SystemConfig(key=HALT_REASON_KEY, value=reason))
    else:
        reason_row.value = reason

    logger.warning("trading_halt_state_changed", halted=halted, reason=reason)


async def halt_reason(session: AsyncSession) -> str:
    row = (
        await session.execute(
            select(SystemConfig).where(SystemConfig.key == HALT_REASON_KEY)
        )
    ).scalars().first()
    return str(row.value) if row else ""
