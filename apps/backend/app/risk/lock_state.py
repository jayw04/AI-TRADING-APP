"""ADR 0042 — is this account in restricted (locked) mode, and why?

One definition, shared. The risk engine's steps 9/13 and the cancellation path must agree on
what "locked" means, or § B is enforceable on orders and quietly not on cancels.

    lock_trigger    — the HISTORICAL condition that activates restricted mode.
                      Backward-looking. No trade can repair it.
    permitted_effect — the FORWARD-LOOKING reduction allowed while locked.

Keeping these apart is load-bearing: conflating them would make the classifier demand that a
reducing order improve an already-realised daily P&L, which no order can do, and every
reduction would be refused for the wrong reason.

**A daily-loss limit that cannot be evaluated is not a satisfied daily-loss limit.**
``accounts_state.day_change`` carries ``0`` as a PLACEHOLDER when no baseline was found — the
truth is in ``day_change_basis`` (``services/day_change_basis.py``), not in the number. Reading
the number alone turns "unknown" into a measured flat day, and the daily-loss condition can then
never become true: an unavailable basis would silently remove the ADR 0042 restricted-mode
protection. So the unavailable case gets its own lock state rather than falling through to
UNLOCKED, and it is NEVER represented as an artificial threshold breach.
"""

from __future__ import annotations

from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.enums import RiskScopeType
from app.db.models.account import Account, AccountMode
from app.db.models.account_state import AccountState
from app.db.models.risk_limits import RiskLimits
from app.services.day_change_basis import UNAVAILABLE

LOCK_UNLOCKED = "UNLOCKED"
LOCK_DAILY_LOSS = "DAILY_LOSS"
LOCK_BREAKER = "BREAKER"
#: A daily-loss limit is configured but its baseline could not be established, so the gate cannot
#: be evaluated. Restricted like any other lock (reduction-only via the ADR 0042 classifier) —
#: NOT a measured breach. Persisted into ``risk_decisions.lock_state`` (``String(24)``).
LOCK_BASELINE_UNAVAILABLE = "BASELINE_UNAVAILABLE"

#: Why the baseline could not be established. Distinguishes "no sync has run for this account"
#: from "sync ran and found no usable baseline" — different operational fixes.
REASON_NO_ACCOUNT_STATE = "daily_loss_basis_unavailable:no_account_state"
REASON_BASIS_UNAVAILABLE = "daily_loss_basis_unavailable:basis_unavailable"


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

    ``daily_pnl`` is ``None`` whenever no baseline was established — the placeholder ``0`` on
    ``accounts_state`` is never passed off as a measurement.
    """
    account = await session.get(Account, account_id)
    if account is None:
        return LOCK_UNLOCKED, None, None

    state = (
        await session.execute(
            select(AccountState).where(AccountState.account_id == account_id)
        )
    ).scalars().first()
    # The basis LABEL decides whether the number means anything; see the module docstring.
    if state is None:
        daily_pnl, unavailable_reason = None, REASON_NO_ACCOUNT_STATE
    elif state.day_change_basis == UNAVAILABLE or state.day_change is None:
        daily_pnl, unavailable_reason = None, REASON_BASIS_UNAVAILABLE
    else:
        daily_pnl, unavailable_reason = state.day_change, None

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

    if limits is None or limits.max_daily_loss is None:
        # No daily-loss protection is configured, so there is none to lose. An unmeasurable
        # baseline costs nothing here and must not gratuitously restrict the account.
        return LOCK_UNLOCKED, None, daily_pnl

    if unavailable_reason is not None:
        return LOCK_BASELINE_UNAVAILABLE, unavailable_reason, None

    if daily_pnl is not None and daily_pnl <= -limits.max_daily_loss:
        return LOCK_DAILY_LOSS, "daily_loss_exceeded", daily_pnl

    return LOCK_UNLOCKED, None, daily_pnl
