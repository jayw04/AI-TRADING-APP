"""GET /api/v1/benchmarks — reference index-fund returns since inception (dashboard comparison).

Each fund's return is computed over the SAME earliest→latest window the accounts' ``total_return``
uses (``starting_equity`` = earliest equity snapshot), so the dashboard compares like-for-like.
Read-only, off the order path.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.stub import CurrentUser, get_current_user
from app.db.session import get_session
from app.services.benchmark_snapshot import benchmark_returns

router = APIRouter(prefix="/benchmarks", tags=["benchmarks"])


@router.get("")
async def get_benchmarks(
    current_user: CurrentUser = Depends(get_current_user),  # noqa: ARG001 — auth gate only
    session: AsyncSession = Depends(get_session),
) -> dict[str, list[dict[str, Any]]]:
    """Per reference index fund: inception date + inception/current price + return-since-inception %."""
    return {"items": await benchmark_returns(session)}
