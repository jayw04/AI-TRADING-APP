"""GET /api/v1/account — returns the current AccountState row."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.schemas.account import AccountResponse
from app.auth.stub import CurrentUser, get_current_user
from app.db.models.account import Account, AccountMode
from app.db.models.account_state import AccountState
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
        daytrade_count=state.daytrade_count,
        pattern_day_trader=state.pattern_day_trader,
        trading_blocked=state.trading_blocked,
        account_blocked=state.account_blocked,
        updated_at=state.updated_at,
    )
