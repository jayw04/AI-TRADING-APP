"""GET /api/v1/benchmarks — reference index-fund returns since inception (dashboard comparison).

Each fund's return is computed over the SAME window the current user's account uses for its
``total_return`` (``starting_equity`` = earliest equity snapshot on/after the account's
``performance_inception_at`` marker). So an account that started live today is compared to the
index from today, not from the global earliest snapshot — the two returns cover the same window.
Read-only, off the order path.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.stub import CurrentUser, get_current_user
from app.db.models.account import Account, AccountMode
from app.db.models.equity_snapshot import EquitySnapshot
from app.db.session import get_session
from app.services.benchmark_snapshot import benchmark_returns

router = APIRouter(prefix="/benchmarks", tags=["benchmarks"])


@router.get("")
async def get_benchmarks(
    current_user: CurrentUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict[str, list[dict[str, Any]]]:
    """Per reference index fund: inception date + inception/current price + return-since-inception %,
    windowed to the current user's account inception (marker, else earliest equity snapshot)."""
    account = (
        await session.execute(
            select(Account).where(
                Account.user_id == current_user.id,
                Account.broker == "alpaca",
                Account.mode == AccountMode.paper,
            )
        )
    ).scalars().first()

    since = None
    if account is not None:
        since = account.performance_inception_at
        if since is None:
            # No explicit marker → align to the account's earliest equity snapshot, the same
            # bound `starting_equity` uses, so the windows match (this reproduces the prior
            # global-aligned behaviour when every account/benchmark shares one inception date).
            since = (
                await session.execute(
                    select(EquitySnapshot.ts)
                    .where(EquitySnapshot.account_id == account.id)
                    .order_by(EquitySnapshot.ts.asc())
                    .limit(1)
                )
            ).scalars().first()

    return {"items": await benchmark_returns(session, since=since)}
