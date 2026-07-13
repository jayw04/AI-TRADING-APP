"""REST endpoints for orders.

POST /api/v1/orders                  — Submit a new order via OrderRouter
GET  /api/v1/orders                  — List orders (filterable)
GET  /api/v1/orders/{id}             — Single order with fills + risk_check
DELETE /api/v1/orders/{id}           — Cancel via OrderRouter
PATCH  /api/v1/orders/{id}           — Modify via OrderRouter

Every order-mutating endpoint dispatches to OrderRouter. There is no path
here that talks to the Alpaca adapter directly — ADR 0002 in HTTP form.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.v1.schemas.orders import (
    FillResponse,
    OrderActionResponse,
    OrderCreateRequest,
    OrderListResponse,
    OrderModifyRequest,
    OrderResponse,
    RiskCheckSummary,
)
from app.auth.stub import CurrentUser, get_current_user
from app.brokers.alpaca import PermanentAlpacaError, TransientAlpacaError
from app.db.enums import (
    TERMINAL_ORDER_STATUSES,
    OrderSourceType,
)
from app.db.models.account import Account, AccountMode
from app.db.models.order import Order
from app.db.models.symbol import Symbol
from app.db.session import get_session
from app.orders.router import BrokerModeError, CancelRejectedByRisk
from app.risk import OrderRequest

router = APIRouter(prefix="/orders", tags=["orders"])


def _get_router(request: Request):
    """Pull the OrderRouter instance off app.state (constructed in lifespan)."""
    router_ = getattr(request.app.state, "order_router", None)
    if router_ is None:
        raise HTTPException(status_code=503, detail="Order router not initialized")
    return router_


async def _order_to_response(session: AsyncSession, order: Order) -> OrderResponse:
    """Materialize an Order row into the response shape, with joined ticker
    and embedded fills + risk_check (relationships must already be loaded)."""
    symbol_row = await session.get(Symbol, order.symbol_id) if order.symbol_id else None
    fills = [
        FillResponse(
            id=f.id,
            broker_fill_id=f.broker_fill_id,
            qty=f.qty,
            price=f.price,
            commission=f.commission,
            filled_at=f.filled_at,
        )
        for f in order.fills
    ]
    risk = None
    if order.risk_check is not None:
        risk = RiskCheckSummary(
            id=order.risk_check.id,
            decision=order.risk_check.decision.value,
            reason_codes=order.risk_check.reason_codes,
            evaluated_at=order.risk_check.evaluated_at,
        )
    return OrderResponse(
        id=order.id,
        broker_order_id=order.broker_order_id,
        client_order_id=order.client_order_id,
        symbol=symbol_row.ticker if symbol_row else "?",
        side=order.side,
        qty=order.qty,
        type=order.type,
        limit_price=order.limit_price,
        stop_price=order.stop_price,
        tif=order.tif,
        extended_hours=order.extended_hours,
        status=order.status,
        rejection_reason=order.rejection_reason,
        source_type=order.source_type,
        source_id=order.source_id,
        created_at=order.created_at,
        submitted_at=order.submitted_at,
        terminal_at=order.terminal_at,
        updated_at=order.updated_at,
        fills=fills,
        risk_check=risk,
    )


def _ephemeral_to_response(order: Order) -> OrderResponse:
    """Serialize an ephemeral (non-persisted) rejected Order. Returned when the
    Risk Engine rejected without resolving a symbol — there's no Order row to
    selectinload from, but we still want a consistent response shape."""
    return OrderResponse(
        id=None,
        broker_order_id=None,
        client_order_id=order.client_order_id,
        symbol="?",  # symbol couldn't be resolved
        side=order.side,
        qty=order.qty,
        type=order.type,
        limit_price=order.limit_price,
        stop_price=order.stop_price,
        tif=order.tif,
        extended_hours=order.extended_hours,
        status=order.status,
        rejection_reason=order.rejection_reason,
        source_type=order.source_type,
        source_id=order.source_id,
        created_at=order.created_at,
        submitted_at=None,
        terminal_at=order.terminal_at,
        updated_at=order.updated_at,
        fills=[],
        risk_check=None,
    )


# ---------- POST /orders ----------


@router.post("", response_model=OrderResponse)
async def create_order(
    body: OrderCreateRequest,
    request: Request,
    current_user: CurrentUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> OrderResponse:
    # P5 §7: resolve the target account. An explicit account_id (e.g. the user's
    # LIVE account) must belong to the user; without one, default to the user's
    # paper account (pre-§7 behavior). The router + risk gates enforce the LIVE
    # rules (confirmation, strategy status, risk, cooldown).
    if body.account_id is not None:
        account = await session.get(Account, body.account_id)
        if account is None or account.user_id != current_user.id:
            raise HTTPException(status_code=404, detail="Account not found")
    else:
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

    req = OrderRequest(
        user_id=current_user.id,
        account_id=account.id,
        symbol_ticker=body.symbol,
        side=body.side,
        qty=body.qty,
        type=body.type,
        tif=body.tif,
        limit_price=body.limit_price,
        stop_price=body.stop_price,
        extended_hours=body.extended_hours,
        source_type=body.source,
        source_id=str(body.strategy_id) if body.strategy_id is not None else None,
        client_order_id=body.client_order_id,
        confirmation_text=body.confirmation_text,
    )

    order_router = _get_router(request)
    try:
        order = await order_router.submit(req)
    except BrokerModeError as exc:
        # The request shape is valid; the business semantics are not (yet). A
        # 400 communicates "meaningfully impossible right now" — see P5 §1.
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    # If the engine rejected before resolving a symbol, the router returned
    # an ephemeral Order (no DB row). Serialize it directly — no relationships
    # to load.
    if order.id is None:
        return _ephemeral_to_response(order)

    # Re-fetch with fills + risk_check eagerly loaded.
    loaded = (
        await session.execute(
            select(Order)
            .options(selectinload(Order.fills), selectinload(Order.risk_check))
            .where(Order.id == order.id)
        )
    ).scalars().first()
    if loaded is None:
        # Persisted but somehow can't be re-read — shouldn't happen.
        raise HTTPException(status_code=500, detail="Order persisted but not retrievable")
    return await _order_to_response(session, loaded)


# ---------- GET /orders (list) ----------


@router.get("", response_model=OrderListResponse)
async def list_orders(
    status: str | None = Query(default=None, description="open | history | all"),
    symbol: str | None = Query(default=None),
    source_type: OrderSourceType | None = Query(
        default=None,
        description="Filter by order source type (manual / strategy / agent / pine).",
    ),
    source_id: str | None = Query(
        default=None,
        max_length=64,
        description=(
            "Filter by source id. REQUIRES source_type also be set — strategy "
            "id=42 and agent id=42 share the same numeric namespace, so "
            "source_id alone is ambiguous."
        ),
    ),
    limit: int = Query(default=100, ge=1, le=500),
    current_user: CurrentUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> OrderListResponse:
    if source_id is not None and source_type is None:
        raise HTTPException(
            status_code=400,
            detail="source_id requires source_type to also be specified.",
        )

    stmt = (
        select(Order)
        .options(selectinload(Order.fills), selectinload(Order.risk_check))
        .where(Order.user_id == current_user.id)
        .order_by(Order.created_at.desc())
        .limit(limit)
    )
    if status == "open":
        stmt = stmt.where(Order.status.notin_(list(TERMINAL_ORDER_STATUSES)))
    elif status == "history":
        stmt = stmt.where(Order.status.in_(list(TERMINAL_ORDER_STATUSES)))

    if symbol:
        symbol_row = (
            await session.execute(
                select(Symbol).where(Symbol.ticker == symbol.upper())
            )
        ).scalars().first()
        if symbol_row is None:
            return OrderListResponse(items=[], count=0)
        stmt = stmt.where(Order.symbol_id == symbol_row.id)

    if source_type is not None:
        stmt = stmt.where(Order.source_type == source_type)
    if source_id is not None:
        stmt = stmt.where(Order.source_id == source_id)

    rows = (await session.execute(stmt)).scalars().all()
    items = [await _order_to_response(session, r) for r in rows]
    return OrderListResponse(items=items, count=len(items))


# ---------- GET /orders/{id} ----------


@router.get("/{order_id}", response_model=OrderResponse)
async def get_order(
    order_id: int,
    current_user: CurrentUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> OrderResponse:
    order = (
        await session.execute(
            select(Order)
            .options(selectinload(Order.fills), selectinload(Order.risk_check))
            .where(Order.id == order_id, Order.user_id == current_user.id)
        )
    ).scalars().first()
    if order is None:
        raise HTTPException(status_code=404, detail="Order not found")
    return await _order_to_response(session, order)


# ---------- DELETE /orders/{id} ----------


@router.delete("/{order_id}", response_model=OrderActionResponse)
async def cancel_order(
    order_id: int,
    request: Request,
    current_user: CurrentUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> OrderActionResponse:
    # Ownership check
    order = (
        await session.execute(
            select(Order).where(
                Order.id == order_id, Order.user_id == current_user.id
            )
        )
    ).scalars().first()
    if order is None:
        raise HTTPException(status_code=404, detail="Order not found")

    order_router = _get_router(request)
    try:
        await order_router.cancel(order_id, actor_user_id=current_user.id)
    except CancelRejectedByRisk as exc:
        # ADR 0042 § B. The account is locked and removing this order would NOT reduce risk —
        # most commonly, it is a pending sell-to-close and cancelling it would trap the
        # exposure on the book. A human cannot assert otherwise; there is no override.
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except TransientAlpacaError as exc:
        raise HTTPException(
            status_code=503, detail=f"Broker temporarily unavailable: {exc}"
        ) from exc
    except PermanentAlpacaError as exc:
        raise HTTPException(status_code=409, detail=f"Cancel rejected: {exc}") from exc
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return OrderActionResponse(
        order_id=order_id, requested_action="cancel", accepted_by_broker=True
    )


# ---------- PATCH /orders/{id} ----------


@router.patch("/{order_id}", response_model=OrderActionResponse)
async def modify_order(
    order_id: int,
    body: OrderModifyRequest,
    request: Request,
    current_user: CurrentUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> OrderActionResponse:
    if body.new_qty is None and body.new_limit_price is None:
        raise HTTPException(
            status_code=400, detail="Provide new_qty and/or new_limit_price"
        )

    order = (
        await session.execute(
            select(Order).where(
                Order.id == order_id, Order.user_id == current_user.id
            )
        )
    ).scalars().first()
    if order is None:
        raise HTTPException(status_code=404, detail="Order not found")

    if order.status in TERMINAL_ORDER_STATUSES:
        raise HTTPException(
            status_code=409,
            detail=f"Order is in terminal state: {order.status.value}",
        )

    order_router = _get_router(request)
    try:
        await order_router.replace(
            order_id,
            new_qty=body.new_qty,
            new_limit_price=body.new_limit_price,
            actor_user_id=current_user.id,
        )
    except TransientAlpacaError as exc:
        raise HTTPException(
            status_code=503, detail=f"Broker temporarily unavailable: {exc}"
        ) from exc
    except (PermanentAlpacaError, ValueError) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return OrderActionResponse(
        order_id=order_id, requested_action="modify", accepted_by_broker=True
    )
