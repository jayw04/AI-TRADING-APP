"""Per-strategy cooldown after failed order submissions (P5 §6).

When a strategy submits an order that doesn't reach the broker (risk rejection,
broker adapter error, validation error — anything that isn't 'accepted by
Alpaca'), the strategy enters a 60-second cooldown.

During cooldown:
  - Subsequent STRATEGY-sourced orders for this strategy_id are rejected with
    STRATEGY_COOLDOWN (in the OrderRouter).
  - EXCEPT a position-reducing exit (a SELL covered by the current long): it is
    exempt and proceeds to the risk engine — a de-risking stop-out must never be
    delayed by the anti-spin cooldown (ADR 0039, extending ADR 0038). The cooldown
    is still SET by a failed exit; only the check is relaxed.
  - Other strategies are unaffected (per-strategy, not per-account).
  - Manual orders are NOT subject to strategy cooldown.

After 60s elapses the strategy can submit again automatically (no manual
intervention). The user may clear it sooner — a normal user action since it
unlocks no new capability, just compresses the wait.

Persisted on strategies.cooldown_until, so it survives backend restarts.

Datetime handling: cooldown_until is DateTime(timezone=True) which SQLite
returns naive on read; comparisons coerce via the shared ensure_aware()
helper (Session 5 §5.0).
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit import AuditAction, AuditActorType, AuditLogger
from app.db.models.strategy import Strategy
from app.utils.time import ensure_aware

logger = structlog.get_logger(__name__)


DEFAULT_COOLDOWN_SECONDS = 60


@dataclass
class CooldownStatus:
    strategy_id: int
    in_cooldown: bool
    cooldown_until: datetime | None
    seconds_remaining: int  # 0 if not in cooldown


class StrategyCooldownService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def status(self, strategy_id: int) -> CooldownStatus:
        strategy = await self._session.get(Strategy, strategy_id)
        if strategy is None:
            raise ValueError(f"Strategy {strategy_id} not found")
        now = datetime.now(UTC)
        cooldown_until = ensure_aware(strategy.cooldown_until)
        if cooldown_until is None or cooldown_until <= now:
            return CooldownStatus(
                strategy_id=strategy_id,
                in_cooldown=False,
                cooldown_until=None,
                seconds_remaining=0,
            )
        seconds = int((cooldown_until - now).total_seconds())
        return CooldownStatus(
            strategy_id=strategy_id,
            in_cooldown=True,
            cooldown_until=cooldown_until,
            seconds_remaining=max(0, seconds),
        )

    async def is_in_cooldown(
        self, strategy_id: int
    ) -> tuple[bool, datetime | None]:
        """Fast check used by the OrderRouter pre-trade. Returns
        (in_cooldown, cooldown_until)."""
        strategy = await self._session.get(Strategy, strategy_id)
        if strategy is None:
            return (False, None)
        now = datetime.now(UTC)
        cooldown_until = ensure_aware(strategy.cooldown_until)
        if cooldown_until is None or cooldown_until <= now:
            return (False, None)
        return (True, cooldown_until)

    async def set_cooldown(
        self,
        strategy_id: int,
        *,
        duration_seconds: int = DEFAULT_COOLDOWN_SECONDS,
        reason: str = "",
    ) -> None:
        """Set or extend the cooldown. Overwrites cooldown_until = now + N
        unconditionally — the 'each failure resets the window' semantics: a
        strategy that keeps failing every 30s never escapes."""
        strategy = await self._session.get(Strategy, strategy_id)
        if strategy is None:
            logger.warning("cooldown_set_missing_strategy", strategy_id=strategy_id)
            return
        now = datetime.now(UTC)
        new_until = now + timedelta(seconds=duration_seconds)
        strategy.cooldown_until = new_until
        await self._session.commit()
        logger.info(
            "strategy_cooldown_set",
            strategy_id=strategy_id,
            cooldown_until=new_until.isoformat(),
            duration_seconds=duration_seconds,
            reason=reason,
        )

    async def clear_cooldown(self, strategy_id: int, *, user_id: int) -> None:
        """Manual user clear. Permission-checked + audit-logged. Idempotent
        (no-op + no audit if not in cooldown)."""
        strategy = await self._session.get(Strategy, strategy_id)
        if strategy is None:
            raise ValueError(f"Strategy {strategy_id} not found")
        if strategy.user_id != user_id:
            raise PermissionError(
                f"Strategy {strategy_id} does not belong to user {user_id}"
            )
        if strategy.cooldown_until is None:
            return
        prior_until = ensure_aware(strategy.cooldown_until)
        strategy.cooldown_until = None
        AuditLogger.write(
            self._session,
            actor_type=AuditActorType.USER,
            actor_id=str(user_id),
            action=AuditAction.STRATEGY_COOLDOWN_CLEARED,
            target_type="strategy",
            target_id=strategy_id,
            payload={
                "prior_cooldown_until": prior_until.isoformat() if prior_until else None,
                "cleared_by_user_id": user_id,
            },
            user_id=user_id,
        )
        await self._session.commit()
        logger.info(
            "strategy_cooldown_cleared", strategy_id=strategy_id, user_id=user_id
        )
