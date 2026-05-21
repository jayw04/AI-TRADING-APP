"""Minimal orders REST surface — enough for smoke-testing the router.

The full GET/PATCH/DELETE surface, list pagination, and detail endpoints land
in Session 6 alongside the frontend.
"""

from __future__ import annotations

from decimal import Decimal

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from app.db.enums import OrderSide, OrderSourceType, OrderType, TimeInForce
from app.risk import OrderRequest

router = APIRouter(prefix="/orders", tags=["orders"])


class OrderRequestIn(BaseModel):
    symbol: str
    side: OrderSide
    qty: Decimal = Field(gt=0)
    type: OrderType
    tif: TimeInForce = TimeInForce.DAY
    limit_price: Decimal | None = None
    stop_price: Decimal | None = None
    extended_hours: bool = False
    client_order_id: str | None = None


@router.post("")
async def submit_order(request: Request, payload: OrderRequestIn) -> dict:
    """Submit a new order. P1 single-user: user_id=1, account_id=1."""
    router_instance = getattr(request.app.state, "order_router", None)
    if router_instance is None:
        raise HTTPException(
            status_code=503,
            detail="order router not initialized (alpaca_startup_enabled=False?)",
        )

    req = OrderRequest(
        user_id=1,
        account_id=1,
        symbol_ticker=payload.symbol.upper(),
        side=payload.side,
        qty=payload.qty,
        type=payload.type,
        tif=payload.tif,
        limit_price=payload.limit_price,
        stop_price=payload.stop_price,
        extended_hours=payload.extended_hours,
        source_type=OrderSourceType.MANUAL,
        client_order_id=payload.client_order_id,
    )
    try:
        order = await router_instance.submit(req)
    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail=f"broker transient error: {exc}",
        ) from exc

    return {
        "id": order.id,
        "status": order.status.value,
        "broker_order_id": order.broker_order_id,
        "rejection_reason": order.rejection_reason,
    }
