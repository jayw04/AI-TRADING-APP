"""REST endpoints for positions."""

from __future__ import annotations

from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.v1.orders import _order_to_response
from app.api.v1.schemas.orders import OrderResponse
from app.api.v1.schemas.positions import (
    ClosePositionRequest,
    PositionListResponse,
    PositionResponse,
)
from app.auth.stub import CurrentUser, get_current_user
from app.db.enums import OrderSide, OrderSourceType, OrderType, TimeInForce
from app.db.models.account import Account, AccountMode
from app.db.models.order import Order
from app.db.models.position import Position
from app.db.models.symbol import Symbol
from app.db.session import get_session
from app.risk import OrderRequest

router = APIRouter(prefix="/positions", tags=["positions"])


def _get_router(request: Request):
    r = getattr(request.app.state, "order_router", None)
    if r is None:
        raise HTTPException(status_code=503, detail="Order router not initialized")
    return r


@router.get("", response_model=PositionListResponse)
async def list_positions(
    current_user: CurrentUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> PositionListResponse:
    positions = (
        await session.execute(
            select(Position).where(Position.user_id == current_user.id)
        )
    ).scalars().all()

    symbol_by_id: dict[int, str] = {}
    if positions:
        symbol_rows = (
            await session.execute(
                select(Symbol).where(Symbol.id.in_([p.symbol_id for p in positions]))
            )
        ).scalars().all()
        symbol_by_id = {s.id: s.ticker for s in symbol_rows}

    items = [
        PositionResponse(
            id=p.id,
            symbol=symbol_by_id.get(p.symbol_id, "?"),
            qty=p.qty,
            avg_entry_price=p.avg_entry_price,
            side=p.side,
            market_value=p.market_value,
            cost_basis=p.cost_basis,
            unrealized_pl=p.unrealized_pl,
            unrealized_plpc=p.unrealized_plpc,
            updated_at=p.updated_at,
        )
        for p in positions
    ]

    gross = sum(
        (abs(p.market_value or Decimal(0)) for p in positions), start=Decimal(0)
    )
    net = sum((p.market_value or Decimal(0) for p in positions), start=Decimal(0))
    total_pl = sum(
        (p.unrealized_pl or Decimal(0) for p in positions), start=Decimal(0)
    )

    return PositionListResponse(
        items=items,
        count=len(items),
        gross_exposure=gross,
        net_exposure=net,
        total_unrealized_pl=total_pl,
    )


@router.post("/{symbol}/close", response_model=OrderResponse)
async def close_position(
    symbol: str,
    body: ClosePositionRequest,  # noqa: ARG001 - reserved for future close options
    request: Request,
    current_user: CurrentUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> OrderResponse:
    """Close a position by submitting an opposite-side market order through
    the SAME OrderRouter — no broker bypass."""
    symbol = symbol.upper()
    symbol_row = (
        await session.execute(select(Symbol).where(Symbol.ticker == symbol))
    ).scalars().first()
    if symbol_row is None:
        raise HTTPException(status_code=404, detail=f"Unknown symbol: {symbol}")

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
        raise HTTPException(status_code=503, detail="No paper account configured")

    position = (
        await session.execute(
            select(Position).where(
                Position.account_id == account.id,
                Position.symbol_id == symbol_row.id,
            )
        )
    ).scalars().first()
    if position is None or position.qty == 0:
        raise HTTPException(status_code=404, detail=f"No open position in {symbol}")

    # Long position → SELL to close; short position → BUY to close.
    is_long = position.qty > 0
    side = OrderSide.SELL if is_long else OrderSide.BUY
    qty = abs(position.qty)

    # When closing a long, we need allow_short=True or an existing position
    # >= qty. The position itself covers this — engine reads it from the DB.
    req = OrderRequest(
        user_id=current_user.id,
        account_id=account.id,
        symbol_ticker=symbol,
        side=side,
        qty=qty,
        type=OrderType.MARKET,
        tif=TimeInForce.DAY,
        source_type=OrderSourceType.MANUAL,
        source_id=f"close-position-{position.id}",
    )
    order = await _get_router(request).submit(req)

    if order.id is None:
        # Engine rejected before resolving symbol (very unlikely here, since
        # we just looked it up above). Surface as a 409 — the close didn't go.
        raise HTTPException(
            status_code=409,
            detail=f"Close rejected: {order.rejection_reason}",
        )

    loaded = (
        await session.execute(
            select(Order)
            .options(selectinload(Order.fills), selectinload(Order.risk_check))
            .where(Order.id == order.id)
        )
    ).scalars().first()
    if loaded is None:
        raise HTTPException(status_code=500, detail="Order persisted but not retrievable")
    return await _order_to_response(session, loaded)
