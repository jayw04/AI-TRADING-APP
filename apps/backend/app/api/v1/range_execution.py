"""GET /api/v1/range-execution — Range Trader daily buy/sell vs. the stock's daily high/low.

Read-through: completed days in the requested window that aren't captured yet are materialized + frozen
(from fills + the bar cache) into ``range_execution_records``, then the window's rows are returned. The
range book is a single shared book (user 2), so the endpoint is auth-gated, not per-caller scoped.
"""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.schemas.range_execution import (
    RangeExecutionListResponse,
    RangeExecutionRecordOut,
)
from app.auth.stub import CurrentUser, get_current_user
from app.db.models.range_execution_record import RangeExecutionRecord
from app.db.session import get_session
from app.services.range_execution import capture_window

router = APIRouter(prefix="/range-execution", tags=["range-execution"])


@router.get("", response_model=RangeExecutionListResponse)
async def list_range_execution(
    request: Request,
    from_date: date = Query(..., description="Start ET date (inclusive)."),
    to_date: date = Query(..., description="End ET date (inclusive)."),
    current_user: CurrentUser = Depends(get_current_user),  # noqa: ARG001 — gate-only; shared book
    session: AsyncSession = Depends(get_session),
) -> RangeExecutionListResponse:
    bar_cache = getattr(request.app.state, "bar_cache", None)
    if bar_cache is not None and to_date >= from_date:
        await capture_window(session, bar_cache, from_date, to_date)
    rows = (
        await session.execute(
            select(RangeExecutionRecord)
            .where(
                RangeExecutionRecord.et_date >= from_date,
                RangeExecutionRecord.et_date <= to_date,
            )
            .order_by(RangeExecutionRecord.et_date, RangeExecutionRecord.symbol)
        )
    ).scalars().all()
    items = [
        RangeExecutionRecordOut(
            et_date=r.et_date,
            symbol=r.symbol,
            avg_buy_price=r.avg_buy_price,
            avg_sell_price=r.avg_sell_price,
            daily_low=r.daily_low,
            daily_high=r.daily_high,
        )
        for r in rows
    ]
    return RangeExecutionListResponse(items=items, count=len(items))
