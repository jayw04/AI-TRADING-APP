"""``GET /api/v1/signals`` — cross-strategy signal view.

Per-strategy listings live under
``/api/v1/strategies/{id}/signals``; this endpoint is the dashboard view
that aggregates across the user's strategies (and across detached
signals from external sources like Pine alerts).
"""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.schemas.strategies import SignalListResponse, SignalResponse
from app.auth.stub import CurrentUser, get_current_user
from app.db.enums import SignalType
from app.db.models.signal import Signal
from app.db.models.symbol import Symbol
from app.db.session import get_session

router = APIRouter(prefix="/signals", tags=["signals"])


@router.get("", response_model=SignalListResponse)
async def list_signals(
    strategy_id: int | None = Query(default=None),
    symbol: str | None = Query(default=None),
    type_: SignalType | None = Query(default=None, alias="type"),
    since: datetime | None = Query(default=None),
    limit: int = Query(default=200, ge=1, le=1000),
    current_user: CurrentUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> SignalListResponse:
    stmt = select(Signal).where(Signal.user_id == current_user.id)
    if strategy_id is not None:
        stmt = stmt.where(Signal.strategy_id == strategy_id)
    if symbol:
        sym = (
            await session.execute(
                select(Symbol).where(Symbol.ticker == symbol.upper())
            )
        ).scalars().first()
        if sym is None:
            return SignalListResponse(items=[], count=0)
        stmt = stmt.where(Signal.symbol_id == sym.id)
    if type_ is not None:
        stmt = stmt.where(Signal.type == type_)
    if since is not None:
        stmt = stmt.where(Signal.received_at >= since)
    stmt = stmt.order_by(Signal.received_at.desc()).limit(limit)

    signals = (await session.execute(stmt)).scalars().all()

    # Single batch join: resolve ticker once per symbol_id instead of per row.
    symbol_ids = list({s.symbol_id for s in signals})
    symbols_by_id: dict[int, str] = {}
    if symbol_ids:
        sym_rows = (
            await session.execute(
                select(Symbol).where(Symbol.id.in_(symbol_ids))
            )
        ).scalars().all()
        symbols_by_id = {s.id: s.ticker for s in sym_rows}

    items = [
        SignalResponse(
            id=s.id,
            strategy_id=s.strategy_id,
            symbol=symbols_by_id.get(s.symbol_id, "?"),
            payload=s.payload_json,
            type=s.type,
            received_at=s.received_at,
            processed_at=s.processed_at,
        )
        for s in signals
    ]
    return SignalListResponse(items=items, count=len(items))
