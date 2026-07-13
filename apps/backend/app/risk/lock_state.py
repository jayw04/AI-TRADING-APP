"""ADR 0042 — is this account in restricted (locked) mode, and why?

One definition, shared. The risk engine's steps 9/13 and the cancellation path must agree on
what "locked" means, or § B is enforceable on orders and quietly not on cancels.

    lock_trigger    — the HISTORICAL condition that activates restricted mode.
                      Backward-looking. No trade can repair it.
    permitted_effect — the FORWARD-LOOKING reduction allowed while locked.

Keeping these apart is load-bearing: conflating them would make the classifier demand that a
reducing order improve an already-realised daily P&L, which no order can do, and every
reduction would be refused for the wrong reason.
"""

from __future__ import annotations

from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.enums import RiskScopeType
from app.db.models.account import Account, AccountMode
from app.db.models.account_state import AccountState
from app.db.models.risk_limits import RiskLimits

LOCK_UNLOCKED = "UNLOCKED"
LOCK_DAILY_LOSS = "DAILY_LOSS"
LOCK_BREAKER = "BREAKER"


async def current_lock_state(
    session: AsyncSession,
    *,
    account_id: int,
    user_id: int,
    broker_mode: AccountMode = AccountMode.paper,
) -> tuple[str, str | None, Decimal | None]:
    """Returns ``(lock_state, lock_reason, daily_pnl)``.

    The breaker is checked FIRST because it is the durable, explicit lock: once tripped it stays
    tripped until a human resets it, whereas the daily-loss condition is recomputed from live
    equity and could flicker across the threshold intraday.
    """
    account = await session.get(Account, account_id)
    if account is None:
        return LOCK_UNLOCKED, None, None

    state = (
        await session.execute(
            select(AccountState).where(AccountState.account_id == account_id)
        )
    ).scalars().first()
    daily_pnl = state.day_change if state is not None else None

    if account.circuit_breaker_tripped_at is not None:
        return LOCK_BREAKER, "circuit_breaker_tripped", daily_pnl

    limits = (
        await session.execute(
            select(RiskLimits).where(
                RiskLimits.user_id == user_id,
                RiskLimits.broker_mode == broker_mode,
                RiskLimits.scope_type == RiskScopeType.GLOBAL,
            )
        )
    ).scalars().first()

    if (
        limits is not None
        and limits.max_daily_loss is not None
        and daily_pnl is not None
        and daily_pnl <= -limits.max_daily_loss
    ):
        return LOCK_DAILY_LOSS, "daily_loss_exceeded", daily_pnl

    return LOCK_UNLOCKED, None, daily_pnl
