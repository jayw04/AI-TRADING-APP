"""GET /api/v1/account — returns the current AccountState row."""

from __future__ import annotations

from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.schemas.account import AccountResponse
from app.auth.stub import CurrentUser, get_current_user
from app.db.models.account import Account, AccountMode
from app.db.models.account_state import AccountState
from app.db.models.equity_snapshot import EquitySnapshot
from app.db.session import get_session

router = APIRouter(prefix="/account", tags=["account"])


@router.get("", response_model=AccountResponse)
async def get_account(
    current_user: CurrentUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> AccountResponse:
    # Resolve the user's active paper account (multi-account is P5+).
    account = (
        await session.execute(
            select(Account).where(
                Account.user_id == current_user.id,
                Account.broker == "alpaca",
                Account.mode == AccountMode.paper,
            )
        )
    ).scalars().first()
    if account is None:
        raise HTTPException(status_code=404, detail="No paper account configured")

    state = (
        await session.execute(
            select(AccountState).where(AccountState.account_id == account.id)
        )
    ).scalars().first()
    if state is None:
        # AccountSyncService hasn't completed its first poll yet (or the
        # adapter startup is disabled in tests).
        raise HTTPException(
            status_code=503,
            detail="Account state not yet synced; try again in a few seconds",
        )

    # Inception-to-date: earliest equity snapshot for THIS account (per-user, never
    # aggregated), on/after the account's performance-inception marker when one is set
    # (so a book that started live after its account row measures from then, not from
    # the earliest snapshot). Fallback to current equity when no history exists in the
    # window → 0% return, which is exactly right for a just-started book.
    eq_stmt = select(EquitySnapshot.equity).where(EquitySnapshot.account_id == account.id)
    if account.performance_inception_at is not None:
        eq_stmt = eq_stmt.where(EquitySnapshot.ts >= account.performance_inception_at)
    starting_equity = (
        await session.execute(eq_stmt.order_by(EquitySnapshot.ts.asc()).limit(1))
    ).scalars().first()
    if starting_equity is None or starting_equity <= 0:
        starting_equity = state.equity
    total_return = state.equity - starting_equity
    total_return_pct = (
        (state.equity / starting_equity - Decimal(1))
        if starting_equity and starting_equity > 0
        else Decimal(0)
    )

    return AccountResponse(
        account_id=account.id,
        mode=account.mode.value,
        status=state.status,
        cash=state.cash,
        equity=state.equity,
        last_equity=state.last_equity,
        buying_power=state.buying_power,
        portfolio_value=state.portfolio_value,
        day_change=state.day_change,
        day_change_pct=state.day_change_pct,
        starting_equity=starting_equity,
        total_return=total_return,
        total_return_pct=total_return_pct,
        daytrade_count=state.daytrade_count,
        pattern_day_trader=state.pattern_day_trader,
        trading_blocked=state.trading_blocked,
        account_blocked=state.account_blocked,
        updated_at=state.updated_at,
    )
