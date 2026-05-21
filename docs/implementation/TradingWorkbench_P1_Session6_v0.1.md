# P1 Session 6 — REST API Surface, WS Topic Publishing, Frontend Trading UI

| Field | Value |
|---|---|
| Document version | v0.1 |
| Date | 2026-05-20 |
| Phase | **P1**, **§5 (REST + WS) + §7 (Ticket) + §8 (Pages) + §9 (Live-Mode Gates)** |
| Predecessor | *TradingWorkbench_P1_Session5_v0.1.md* (tag `p1-session5-complete`) |
| Repository | `github.com/jayw04/AI-TRADING-APP` |
| Scope | Make the workbench *usable*. Three PRs: (6A) full REST endpoints + WS topic publishing for orders/fills/positions; (6B) Order Ticket component + Orders + Positions pages wired live; (6C) Charts page (TradingView embed), real Dashboard, live-mode UX gates. |
| Estimated wall time | 6–8 hours (across **3 PRs**) |
| Stopping point | `git tag p1-session6-complete` |
| Explicitly deferred to **P1 Session 7** | Tests + manual smoke matrix (P1.F) + runbook docs + final P1 exit gate |

---

## Why Three PRs Again

Same reason as Session 5: a single monolithic PR for "frontend trading UI" would be ~4000 lines of diff. Splitting along natural seams:

| PR | Components | Approx. lines | Why this seam |
|---|---|---|---|
| **6A** | REST endpoints + Pydantic schemas + WS topic publishing | ~1200 | Pure backend; once merged, the frontend has a stable contract to code against. |
| **6B** | Order Ticket component + Orders page + Positions page | ~1500 | The core trading UX, single domain (orders/positions). Depends on 6A. |
| **6C** | Charts page (TradingView embed) + Dashboard + Live-mode UX gates | ~1100 | Polish + safety; separable from the core trading flow. |

Within each PR, the structure is the same as previous sessions: literal commands, file contents, explicit acceptance.

---

## Session Goal

After all three PRs merge:

- Every P1 REST endpoint from Checklist §5.1 returns real data: `GET /api/v1/account`, `POST/GET/DELETE/PATCH /api/v1/orders`, `GET /api/v1/positions`, `GET /api/v1/quotes/{symbol}`, `GET /api/v1/bars/{symbol}`.
- Every P1 WS topic from Checklist §5.3 is published: `orders`, `fills`, `positions`, `quote.{symbol}`, `system`.
- The OrderTicket component submits paper orders through the full Session 5 pipeline.
- The Orders page lists working + history, supports cancel + modify inline, shows risk-rejection reasons in plain English.
- The Positions page shows live P&L per symbol, with a "Close (market)" action that submits a market order through the same `/api/v1/orders` endpoint (no bypass).
- The Charts page embeds TradingView's free Advanced Charts widget for any seed symbol.
- The Dashboard shows real account data (cash, equity, buying power, day P&L) and real counts of open orders/positions.
- The mode banner is amber for paper, with a confirmation modal scaffolded for live (P5 will actually toggle it).

What does NOT happen this session:

- No tests beyond a handful of smoke checks per PR. The full test matrix is **Session 7**.
- No hotkeys. Deferred to P4 polish.
- No `Strategies` / `Agent` / `Journal` pages. Still placeholders for P2+/P3+.
- No "kill switch" UI page. Deferred to P4 (the endpoint exists; UI lands later).

---

## Prerequisites Check

```bash
cd ~/code/AI-TRADING-APP
git status                                   # clean
git pull origin main
git describe --tags --abbrev=0               # expect: p1-session5-complete

# Smoke that Sessions 2–5 are alive
./scripts/dev.sh &
sleep 30
docker compose logs backend | grep -E "trade_updates_stream_started|scheduler_started|asset_sync_completed" | head

# Verify OrderRouter is reachable from a Python REPL (Session 5 left a minimal
# REST endpoint at /api/v1/_internal/orders; if you took the alternative path
# of REPL-only access, skip this step)
curl -s -X POST http://127.0.0.1:8000/api/v1/_internal/orders \
  -H "Content-Type: application/json" \
  -d '{"symbol":"F","side":"buy","qty":"1","type":"market","tif":"day","last_price":"12"}' \
  | jq '{status, rejection_reason}' 2>/dev/null || echo "skip if Session 5 didn't add the minimal endpoint"

docker compose down
```

- [ ] On `main`, clean tree, at `p1-session5-complete` or later.
- [ ] Backend boots cleanly with all Session 2–5 services healthy.

---

## PR 6A — REST Endpoints + WS Topic Publishing

Cut the branch:

```bash
git checkout -b feat/p1-rest-api-and-ws-topics
```

This PR is pure backend. After it merges, the frontend has a stable, documented HTTP/WS contract.

### 6A.1 — Pydantic schemas

Create `apps/backend/app/api/v1/schemas/__init__.py` (empty), then the schema files.

`apps/backend/app/api/v1/schemas/account.py`:

```python
"""Pydantic models for /api/v1/account."""
from __future__ import annotations

from decimal import Decimal
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class AccountResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    account_id: int
    mode: str                         # "paper" | "live"
    status: str                       # "ACTIVE" | ...
    cash: Decimal
    equity: Decimal
    last_equity: Decimal
    buying_power: Decimal
    portfolio_value: Decimal
    day_change: Decimal
    day_change_pct: Decimal
    daytrade_count: int
    pattern_day_trader: bool
    trading_blocked: bool
    account_blocked: bool
    updated_at: datetime
```

`apps/backend/app/api/v1/schemas/orders.py`:

```python
"""Pydantic models for /api/v1/orders."""
from __future__ import annotations

from decimal import Decimal
from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.db.enums import OrderSide, OrderSourceType, OrderStatus, OrderType, TimeInForce


class OrderCreateRequest(BaseModel):
    """Body for POST /api/v1/orders.

    Strict: unknown fields are rejected so a typo can't silently bypass the
    risk engine via a misnamed override.
    """
    model_config = ConfigDict(extra="forbid")

    symbol: str = Field(min_length=1, max_length=16)
    side: OrderSide
    qty: Decimal = Field(gt=0)
    type: OrderType = OrderType.MARKET
    limit_price: Optional[Decimal] = Field(default=None, gt=0)
    stop_price: Optional[Decimal] = Field(default=None, gt=0)
    tif: TimeInForce = TimeInForce.DAY
    extended_hours: bool = False

    @field_validator("symbol")
    @classmethod
    def _upper(cls, v: str) -> str:
        return v.strip().upper()


class FillResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    broker_fill_id: Optional[str]
    qty: Decimal
    price: Decimal
    commission: Decimal
    filled_at: datetime


class RiskCheckSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    decision: str                    # "pass" | "reject"
    reason_codes: list[str]
    evaluated_at: datetime


class OrderResponse(BaseModel):
    """Standard order representation. Used by both single-order and list endpoints."""
    model_config = ConfigDict(from_attributes=True)

    id: int
    broker_order_id: Optional[str]
    client_order_id: Optional[str]
    symbol: str                      # ticker, joined from symbols table
    side: OrderSide
    qty: Decimal
    type: OrderType
    limit_price: Optional[Decimal]
    stop_price: Optional[Decimal]
    tif: TimeInForce
    extended_hours: bool
    status: OrderStatus
    rejection_reason: Optional[str]
    source_type: OrderSourceType
    source_id: Optional[str]
    created_at: datetime
    submitted_at: Optional[datetime]
    terminal_at: Optional[datetime]
    updated_at: datetime
    fills: list[FillResponse] = []
    risk_check: Optional[RiskCheckSummary] = None


class OrderListResponse(BaseModel):
    items: list[OrderResponse]
    count: int


class OrderModifyRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    new_qty: Optional[Decimal] = Field(default=None, gt=0)
    new_limit_price: Optional[Decimal] = Field(default=None, gt=0)


class OrderActionResponse(BaseModel):
    """Returned by cancel + modify."""
    order_id: int
    requested_action: Literal["cancel", "modify"]
    accepted_by_broker: bool         # True if the broker accepted the request (not the eventual outcome)
```

`apps/backend/app/api/v1/schemas/positions.py`:

```python
from __future__ import annotations

from decimal import Decimal
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict


class PositionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    symbol: str
    qty: Decimal
    avg_entry_price: Decimal
    side: Optional[str]              # "long" | "short" | None
    market_value: Decimal
    cost_basis: Decimal
    unrealized_pl: Decimal
    unrealized_plpc: Decimal
    updated_at: datetime


class PositionListResponse(BaseModel):
    items: list[PositionResponse]
    count: int
    gross_exposure: Decimal
    net_exposure: Decimal
    total_unrealized_pl: Decimal


class ClosePositionRequest(BaseModel):
    """Body for POST /api/v1/positions/{symbol}/close. Empty for now; future
    options (close as limit, partial close) can be added without breaking
    callers."""
    model_config = ConfigDict(extra="forbid")
```

`apps/backend/app/api/v1/schemas/market_data.py`:

```python
from __future__ import annotations

from decimal import Decimal
from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class QuoteResponse(BaseModel):
    symbol: str
    bid: Optional[Decimal]
    ask: Optional[Decimal]
    last: Optional[Decimal]
    bid_size: Optional[int]
    ask_size: Optional[int]
    ts: Optional[datetime]
    source: str = "alpaca-iex"       # documenting the data source


class BarResponse(BaseModel):
    t: datetime
    o: Decimal
    h: Decimal
    l: Decimal
    c: Decimal
    v: int


class BarsResponse(BaseModel):
    symbol: str
    timeframe: str
    bars: list[BarResponse]
```

- [ ] All four schema files created.

### 6A.2 — Account endpoint (real, not stub)

Replace the P0 stub at `apps/backend/app/api/v1/account.py`:

```python
"""GET /api/v1/account — returns the current AccountState row."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.schemas.account import AccountResponse
from app.auth.stub import get_current_user
from app.db.models.account import Account
from app.db.models.account_state import AccountState
from app.db.session import get_session

router = APIRouter(prefix="/account", tags=["account"])


@router.get("", response_model=AccountResponse)
async def get_account(
    current_user=Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    # Resolve the user's active paper account (multi-account is P5+).
    account = (await session.execute(
        select(Account).where(
            Account.user_id == current_user.id,
            Account.broker == "alpaca",
            Account.mode == "paper",
        )
    )).scalars().first()
    if account is None:
        raise HTTPException(status_code=404, detail="No paper account configured")

    state = (await session.execute(
        select(AccountState).where(AccountState.account_id == account.id)
    )).scalars().first()
    if state is None:
        raise HTTPException(
            status_code=503,
            detail="Account state not yet synced; try again in a few seconds",
        )

    return AccountResponse(
        account_id=account.id,
        mode=account.mode,
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
```

### 6A.3 — Orders endpoints

Create `apps/backend/app/api/v1/orders.py`:

```python
"""REST endpoints for orders.

POST /api/v1/orders                  — Submit a new order via OrderRouter
GET  /api/v1/orders                  — List orders (filterable)
GET  /api/v1/orders/{id}             — Single order with fills + risk check
DELETE /api/v1/orders/{id}           — Cancel via OrderRouter
PATCH  /api/v1/orders/{id}           — Modify via OrderRouter

Every order-mutating endpoint dispatches to OrderRouter. There is no path
here that talks to the Alpaca adapter directly — ADR 0002 in HTTP form.
"""
from __future__ import annotations

from decimal import Decimal
from typing import Optional

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
from app.auth.stub import get_current_user
from app.brokers.alpaca import (
    PermanentAlpacaError,
    TransientAlpacaError,
)
from app.db.enums import (
    OrderSourceType,
    OrderStatus,
    TERMINAL_ORDER_STATUSES,
)
from app.db.models.order import Order
from app.db.models.symbol import Symbol
from app.db.session import get_session
from app.risk import OrderRequest

router = APIRouter(prefix="/orders", tags=["orders"])


def _get_router(request: Request):
    """Pull the OrderRouter instance off app.state (constructed in lifespan)."""
    router_ = getattr(request.app.state, "order_router", None)
    if router_ is None:
        raise HTTPException(status_code=503, detail="Order router not initialized")
    return router_


async def _order_to_response(session: AsyncSession, order: Order) -> OrderResponse:
    """Materialize an Order row into the response shape, including joined symbol
    ticker and embedded fills + risk_check."""
    symbol_row = await session.get(Symbol, order.symbol_id)
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


# ---------- POST /orders ----------


@router.post("", response_model=OrderResponse)
async def create_order(
    body: OrderCreateRequest,
    request: Request,
    current_user=Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    # Resolve symbol_id (and reject unknown tickers early).
    symbol_row = (await session.execute(
        select(Symbol).where(Symbol.ticker == body.symbol, Symbol.active.is_(True))
    )).scalars().first()
    if symbol_row is None:
        raise HTTPException(status_code=404, detail=f"Unknown or inactive symbol: {body.symbol}")

    # Resolve account (paper, single account for MVP).
    from app.db.models.account import Account
    account = (await session.execute(
        select(Account).where(
            Account.user_id == current_user.id,
            Account.broker == "alpaca",
            Account.mode == "paper",
        )
    )).scalars().first()
    if account is None:
        raise HTTPException(status_code=503, detail="No paper account configured")

    # Best-effort last price for notional cap evaluation.
    quote = None
    quotes_svc = getattr(request.app.state, "alpaca_adapter", None)
    last_price: Optional[Decimal] = None
    if quotes_svc is not None:
        try:
            # quick last-trade fallback via Alpaca (cached at the data layer
            # in 6A.6); accept None if it fails.
            from app.market_data.quotes import get_last_quote
            quote = await get_last_quote(body.symbol)
            if quote and quote.get("last") is not None:
                last_price = Decimal(str(quote["last"]))
        except Exception:
            last_price = None

    req = OrderRequest(
        user_id=current_user.id,
        account_id=account.id,
        symbol_id=symbol_row.id,
        symbol=body.symbol,
        side=body.side,
        qty=body.qty,
        type=body.type,
        limit_price=body.limit_price,
        stop_price=body.stop_price,
        tif=body.tif,
        extended_hours=body.extended_hours,
        source_type=OrderSourceType.MANUAL,
        last_price=last_price,
    )

    order_router = _get_router(request)
    order = await order_router.submit(req)

    # Re-fetch with fills + risk_check loaded
    order = (await session.execute(
        select(Order)
        .options(selectinload(Order.fills), selectinload(Order.risk_check))
        .where(Order.id == order.id)
    )).scalars().first()
    return await _order_to_response(session, order)


# ---------- GET /orders ----------


@router.get("", response_model=OrderListResponse)
async def list_orders(
    status: Optional[str] = Query(default=None, description="open | history | all"),
    symbol: Optional[str] = Query(default=None),
    since: Optional[str] = None,
    limit: int = Query(default=100, ge=1, le=500),
    current_user=Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
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
    # else: include all
    if symbol:
        symbol_row = (await session.execute(
            select(Symbol).where(Symbol.ticker == symbol.upper())
        )).scalars().first()
        if symbol_row:
            stmt = stmt.where(Order.symbol_id == symbol_row.id)
        else:
            return OrderListResponse(items=[], count=0)

    rows = (await session.execute(stmt)).scalars().all()
    items = [await _order_to_response(session, r) for r in rows]
    return OrderListResponse(items=items, count=len(items))


# ---------- GET /orders/{id} ----------


@router.get("/{order_id}", response_model=OrderResponse)
async def get_order(
    order_id: int,
    current_user=Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    order = (await session.execute(
        select(Order)
        .options(selectinload(Order.fills), selectinload(Order.risk_check))
        .where(Order.id == order_id, Order.user_id == current_user.id)
    )).scalars().first()
    if order is None:
        raise HTTPException(status_code=404, detail="Order not found")
    return await _order_to_response(session, order)


# ---------- DELETE /orders/{id} ----------


@router.delete("/{order_id}", response_model=OrderActionResponse)
async def cancel_order(
    order_id: int,
    request: Request,
    current_user=Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    # Ownership check
    order = (await session.execute(
        select(Order).where(Order.id == order_id, Order.user_id == current_user.id)
    )).scalars().first()
    if order is None:
        raise HTTPException(status_code=404, detail="Order not found")

    order_router = _get_router(request)
    try:
        await order_router.cancel(order_id, actor_user_id=current_user.id)
    except TransientAlpacaError as exc:
        raise HTTPException(status_code=503, detail=f"Broker temporarily unavailable: {exc}")
    except PermanentAlpacaError as exc:
        raise HTTPException(status_code=409, detail=f"Cancel rejected: {exc}")
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    return OrderActionResponse(order_id=order_id, requested_action="cancel", accepted_by_broker=True)


# ---------- PATCH /orders/{id} ----------


@router.patch("/{order_id}", response_model=OrderActionResponse)
async def modify_order(
    order_id: int,
    body: OrderModifyRequest,
    request: Request,
    current_user=Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    if body.new_qty is None and body.new_limit_price is None:
        raise HTTPException(status_code=400, detail="Provide new_qty and/or new_limit_price")

    order = (await session.execute(
        select(Order).where(Order.id == order_id, Order.user_id == current_user.id)
    )).scalars().first()
    if order is None:
        raise HTTPException(status_code=404, detail="Order not found")

    if order.status in TERMINAL_ORDER_STATUSES:
        raise HTTPException(status_code=409, detail=f"Order is in terminal state: {order.status.value}")

    order_router = _get_router(request)
    try:
        await order_router.replace(
            order_id,
            new_qty=body.new_qty,
            new_limit_price=body.new_limit_price,
            actor_user_id=current_user.id,
        )
    except TransientAlpacaError as exc:
        raise HTTPException(status_code=503, detail=f"Broker temporarily unavailable: {exc}")
    except (PermanentAlpacaError, ValueError) as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    return OrderActionResponse(order_id=order_id, requested_action="modify", accepted_by_broker=True)
```

### 6A.4 — Positions endpoints

Create `apps/backend/app/api/v1/positions.py`:

```python
"""REST endpoints for positions."""
from __future__ import annotations

from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.schemas.orders import OrderResponse
from app.api.v1.schemas.positions import (
    ClosePositionRequest,
    PositionListResponse,
    PositionResponse,
)
from app.auth.stub import get_current_user
from app.db.enums import OrderSide, OrderSourceType, OrderType, TimeInForce
from app.db.models.account import Account
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
    current_user=Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    positions = (await session.execute(
        select(Position).where(Position.user_id == current_user.id)
    )).scalars().all()

    symbols = (await session.execute(
        select(Symbol).where(Symbol.id.in_([p.symbol_id for p in positions])) if positions else select(Symbol).where(False)
    )).scalars().all()
    symbol_by_id = {s.id: s.ticker for s in symbols}

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

    gross = sum((abs(p.market_value or Decimal(0)) for p in positions), start=Decimal(0))
    net = sum((p.market_value or Decimal(0) for p in positions), start=Decimal(0))
    total_pl = sum((p.unrealized_pl or Decimal(0) for p in positions), start=Decimal(0))

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
    body: ClosePositionRequest,
    request: Request,
    current_user=Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Close a position by submitting a market order for the opposite side
    through the SAME OrderRouter path — no broker bypass."""
    symbol = symbol.upper()
    symbol_row = (await session.execute(
        select(Symbol).where(Symbol.ticker == symbol)
    )).scalars().first()
    if symbol_row is None:
        raise HTTPException(status_code=404, detail=f"Unknown symbol: {symbol}")

    account = (await session.execute(
        select(Account).where(
            Account.user_id == current_user.id,
            Account.broker == "alpaca",
            Account.mode == "paper",
        )
    )).scalars().first()
    if account is None:
        raise HTTPException(status_code=503, detail="No paper account configured")

    position = (await session.execute(
        select(Position).where(
            Position.account_id == account.id,
            Position.symbol_id == symbol_row.id,
        )
    )).scalars().first()
    if position is None or position.qty == 0:
        raise HTTPException(status_code=404, detail=f"No open position in {symbol}")

    # Long position -> SELL to close; short position -> BUY to close.
    is_long = position.qty > 0
    side = OrderSide.SELL if is_long else OrderSide.BUY
    qty = abs(position.qty)

    req = OrderRequest(
        user_id=current_user.id,
        account_id=account.id,
        symbol_id=symbol_row.id,
        symbol=symbol,
        side=side,
        qty=qty,
        type=OrderType.MARKET,
        tif=TimeInForce.DAY,
        source_type=OrderSourceType.MANUAL,
        source_id=f"close-position-{position.id}",
        last_price=position.avg_entry_price,   # rough; OK for caps
    )
    order = await _get_router(request).submit(req)

    # Re-fetch with fills + risk_check
    from sqlalchemy.orm import selectinload
    from app.db.models.order import Order as OrderModel
    order = (await session.execute(
        select(OrderModel)
        .options(selectinload(OrderModel.fills), selectinload(OrderModel.risk_check))
        .where(OrderModel.id == order.id)
    )).scalars().first()
    # Reuse the orders router's serializer:
    from app.api.v1.orders import _order_to_response
    return await _order_to_response(session, order)
```

### 6A.5 — Market-data endpoints

Create `apps/backend/app/market_data/quotes.py`:

```python
"""Quote and bar fetch helpers, with a tiny in-process cache to avoid
hammering Alpaca's free-tier rate limit."""
from __future__ import annotations

import asyncio
import time
from typing import Any, Optional

from app.brokers.alpaca import AlpacaAdapter

# (symbol -> (cached_at_epoch, payload))
_QUOTE_CACHE: dict[str, tuple[float, dict]] = {}
_QUOTE_TTL_SECONDS = 1.0
_lock = asyncio.Lock()


async def get_last_quote(symbol: str) -> Optional[dict[str, Any]]:
    """Return the most recent quote for a symbol, cached for 1s.

    Returns a dict with bid/ask/last/ts or None if Alpaca refuses or has no
    quote available on the free IEX feed.
    """
    symbol = symbol.upper()
    now = time.time()
    cached = _QUOTE_CACHE.get(symbol)
    if cached and now - cached[0] < _QUOTE_TTL_SECONDS:
        return cached[1]

    async with _lock:
        cached = _QUOTE_CACHE.get(symbol)
        if cached and now - cached[0] < _QUOTE_TTL_SECONDS:
            return cached[1]

        loop = asyncio.get_running_loop()
        try:
            from alpaca.data.historical import StockHistoricalDataClient
            from alpaca.data.requests import StockLatestQuoteRequest
            from app.brokers.alpaca.credentials import load_credentials
            creds = load_credentials()
            client = StockHistoricalDataClient(api_key=creds.api_key, secret_key=creds.api_secret)
            req = StockLatestQuoteRequest(symbol_or_symbols=symbol, feed="iex")
            result = await loop.run_in_executor(None, lambda: client.get_stock_latest_quote(req))
            q = result[symbol] if isinstance(result, dict) else result
            payload = {
                "symbol": symbol,
                "bid": str(getattr(q, "bid_price", None) or ""),
                "ask": str(getattr(q, "ask_price", None) or ""),
                "last": str(getattr(q, "ask_price", None) or getattr(q, "bid_price", None) or ""),
                "bid_size": getattr(q, "bid_size", None),
                "ask_size": getattr(q, "ask_size", None),
                "ts": getattr(q, "timestamp", None).isoformat() if getattr(q, "timestamp", None) else None,
            }
            _QUOTE_CACHE[symbol] = (now, payload)
            return payload
        except Exception:
            return None
```

Create `apps/backend/app/api/v1/market_data.py`:

```python
"""REST endpoints for quotes + historical bars."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Optional

from fastapi import APIRouter, HTTPException, Query

from app.api.v1.schemas.market_data import BarResponse, BarsResponse, QuoteResponse
from app.market_data.quotes import get_last_quote

router = APIRouter(tags=["market-data"])


@router.get("/quotes/{symbol}", response_model=QuoteResponse)
async def get_quote(symbol: str):
    q = await get_last_quote(symbol)
    if q is None:
        raise HTTPException(status_code=503, detail="Quote unavailable (IEX free tier)")
    return QuoteResponse(
        symbol=q["symbol"],
        bid=Decimal(q["bid"]) if q["bid"] else None,
        ask=Decimal(q["ask"]) if q["ask"] else None,
        last=Decimal(q["last"]) if q["last"] else None,
        bid_size=q.get("bid_size"),
        ask_size=q.get("ask_size"),
        ts=datetime.fromisoformat(q["ts"]) if q.get("ts") else None,
    )


@router.get("/bars/{symbol}", response_model=BarsResponse)
async def get_bars(
    symbol: str,
    timeframe: str = Query(default="1Min", description="1Min | 5Min | 15Min | 1Hour | 1Day"),
    start: Optional[str] = None,
    end: Optional[str] = None,
    limit: int = Query(default=100, ge=1, le=10_000),
):
    """Return historical OHLCV bars for one symbol. Uses Alpaca's free
    historical data (IEX feed). Caches handled at adapter layer (Session 2)."""
    from alpaca.data.historical import StockHistoricalDataClient
    from alpaca.data.requests import StockBarsRequest
    from alpaca.data.timeframe import TimeFrame, TimeFrameUnit
    from app.brokers.alpaca.credentials import load_credentials

    creds = load_credentials()
    client = StockHistoricalDataClient(api_key=creds.api_key, secret_key=creds.api_secret)

    tf_map = {
        "1Min": TimeFrame(1, TimeFrameUnit.Minute),
        "5Min": TimeFrame(5, TimeFrameUnit.Minute),
        "15Min": TimeFrame(15, TimeFrameUnit.Minute),
        "1Hour": TimeFrame(1, TimeFrameUnit.Hour),
        "1Day": TimeFrame(1, TimeFrameUnit.Day),
    }
    if timeframe not in tf_map:
        raise HTTPException(status_code=400, detail=f"Unsupported timeframe: {timeframe}")

    end_dt = datetime.fromisoformat(end) if end else datetime.now(timezone.utc)
    start_dt = datetime.fromisoformat(start) if start else (end_dt - timedelta(days=5))

    req = StockBarsRequest(
        symbol_or_symbols=symbol.upper(),
        timeframe=tf_map[timeframe],
        start=start_dt,
        end=end_dt,
        feed="iex",
        limit=limit,
    )
    try:
        result = client.get_stock_bars(req)
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Bars unavailable: {exc}")

    bars = result.data.get(symbol.upper(), []) if hasattr(result, "data") else []
    return BarsResponse(
        symbol=symbol.upper(),
        timeframe=timeframe,
        bars=[
            BarResponse(
                t=b.timestamp,
                o=Decimal(str(b.open)),
                h=Decimal(str(b.high)),
                l=Decimal(str(b.low)),
                c=Decimal(str(b.close)),
                v=int(b.volume),
            )
            for b in bars
        ],
    )
```

### 6A.6 — Register routers in the app factory

Edit `apps/backend/app/main.py` (or wherever `create_app` lives). Add:

```python
from app.api.v1 import account as account_router
from app.api.v1 import orders as orders_router
from app.api.v1 import positions as positions_router
from app.api.v1 import market_data as market_data_router

# Inside create_app():
app.include_router(account_router.router, prefix="/api/v1")
app.include_router(orders_router.router, prefix="/api/v1")
app.include_router(positions_router.router, prefix="/api/v1")
app.include_router(market_data_router.router, prefix="/api/v1")
```

### 6A.7 — WS topic publishing

The event bus is already publishing `order.submitted`, `order.rejected`, `order.transition`, `alpaca.trade_update`, `positions.snapshot`, `account.snapshot` (Sessions 2–5). Now wire them through the existing WS gateway so connected clients receive them.

Edit `apps/backend/app/ws/gateway.py`. Find the WebSocket endpoint and add topic-subscription support if not already there:

```python
"""WebSocket gateway with topic subscriptions and per-topic replay buffers.

Client message shape (JSON):
    {"action": "subscribe", "topics": ["orders", "positions", "quote.AAPL"]}
    {"action": "unsubscribe", "topics": [...]}

Server pushes JSON lines:
    {"topic": "orders", "type": "order.submitted", "payload": {...}, "ts": "..."}
"""
from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from typing import Any

import structlog
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.events.bus import get_event_bus
from app.ws.replay import REPLAY_WINDOWS_SECONDS, ReplayBuffer

logger = structlog.get_logger(__name__)
router = APIRouter()

_replay_buffer = ReplayBuffer(window_overrides=REPLAY_WINDOWS_SECONDS)

# Topics this session publishes on
PUBLISHED_TOPICS = {
    "orders", "fills", "positions", "system", "alerts", "strategies", "agent",
}
# quote.{symbol} is dynamic — handled below


def _wrap(topic: str, type_: str, payload: dict[str, Any]) -> str:
    return json.dumps({
        "topic": topic,
        "type": type_,
        "payload": payload,
        "ts": datetime.now(timezone.utc).isoformat(),
    })


@router.websocket("/ws")
async def ws_endpoint(websocket: WebSocket):
    await websocket.accept()
    bus = get_event_bus()
    subscriptions: set[str] = {"system"}    # heartbeat always on
    unsubscribers: list = []

    async def _forward(topic_name: str):
        async def _handler(payload: dict[str, Any]):
            if topic_name not in subscriptions:
                return
            try:
                await websocket.send_text(_wrap(topic_name, payload.get("__event__") or topic_name, payload))
            except Exception:
                pass
        return bus.subscribe(topic_name, _handler)

    # Translate Session 2-5 bus events onto stable WS topics:
    bus_to_ws_map = {
        # bus topic -> ws topic
        "order.submitted": "orders",
        "order.rejected": "orders",
        "order.transition": "orders",
        "positions.snapshot": "positions",
        "account.snapshot": "system",        # account state surfaced under system
        "alpaca.trade_update": "fills",      # fills topic gets all execution detail
        "alpaca.stream_status": "system",
        "system.symbols_synced": "system",
        "system.reconciliation_drift": "system",
        "system.heartbeat": "system",
    }
    for bus_topic, ws_topic in bus_to_ws_map.items():
        async def _make_handler(ws_topic_=ws_topic, bus_topic_=bus_topic):
            async def _h(payload: dict[str, Any]):
                wrapped = {**payload, "__event__": bus_topic_}
                _replay_buffer.append(ws_topic_, wrapped)
                if ws_topic_ in subscriptions:
                    try:
                        await websocket.send_text(_wrap(ws_topic_, bus_topic_, payload))
                    except Exception:
                        pass
            return _h
        handler = await _make_handler()
        unsub = bus.subscribe(bus_topic, handler)
        unsubscribers.append(unsub)

    # Send initial system.connected
    await websocket.send_text(_wrap("system", "system.connected", {"server_version": "0.1.0"}))

    try:
        while True:
            msg = await websocket.receive_text()
            try:
                data = json.loads(msg)
            except json.JSONDecodeError:
                continue
            action = data.get("action")
            topics = data.get("topics") or []
            if action == "subscribe":
                for t in topics:
                    subscriptions.add(t)
                # Replay any buffered events for newly-subscribed topics
                for t in topics:
                    for evt in _replay_buffer.get_recent(t):
                        try:
                            await websocket.send_text(_wrap(t, evt.get("__event__") or t, evt))
                        except Exception:
                            pass
            elif action == "unsubscribe":
                for t in topics:
                    subscriptions.discard(t)
            elif action == "ping":
                await websocket.send_text(_wrap("system", "system.pong", {}))
    except WebSocketDisconnect:
        pass
    finally:
        for u in unsubscribers:
            try:
                u()
            except Exception:
                pass
```

> **Replay buffer note.** The `ReplayBuffer` from P0 is the placeholder; this session adds `append` and `get_recent` methods if they're not there. Implementation Plan v0.2 §8 documented the per-topic windows: `orders/fills/signals/agent/alerts/strategies: 60min`, `positions: 10min`, `system/quote: 0`. Keep them in `apps/backend/app/ws/replay.py` as a constant dict; the in-memory deque per topic with millisecond-precision dropping is fine for MVP.

### 6A.8 — Quick smoke

```bash
./scripts/dev.sh &
sleep 30

# REST: account
curl -s http://127.0.0.1:8000/api/v1/account | jq .

# REST: orders list (empty)
curl -s http://127.0.0.1:8000/api/v1/orders | jq .

# REST: place a tiny paper order
curl -s -X POST http://127.0.0.1:8000/api/v1/orders \
  -H "Content-Type: application/json" \
  -d '{"symbol":"F","side":"buy","qty":"1","type":"market","tif":"day"}' \
  | jq '{id,status,broker_order_id,rejection_reason}'

# REST: positions
sleep 5  # give the fill a moment
curl -s http://127.0.0.1:8000/api/v1/positions | jq .

# WS: subscribe to orders + system, observe events streaming
# (run in another terminal)
echo '{"action":"subscribe","topics":["orders","fills","positions","system"]}' \
  | websocat -n1 ws://127.0.0.1:8000/ws

# Cleanup
curl -X DELETE https://paper-api.alpaca.markets/v2/positions \
  -H "APCA-API-KEY-ID: $ALPACA_PAPER_API_KEY" \
  -H "APCA-API-SECRET-KEY: $ALPACA_PAPER_API_SECRET"
docker compose down
```

- [ ] `GET /api/v1/account` returns real numbers.
- [ ] `POST /api/v1/orders` submits a paper order via OrderRouter.
- [ ] `GET /api/v1/orders` shows the order with `risk_check` embedded.
- [ ] `GET /api/v1/positions` shows the filled position.
- [ ] WS connection receives `system.connected`, then live `orders` and `fills` events.

### 6A.9 — Commit and PR (6A)

```bash
git add apps/backend/app/api/v1/schemas/
git add apps/backend/app/api/v1/account.py
git add apps/backend/app/api/v1/orders.py
git add apps/backend/app/api/v1/positions.py
git add apps/backend/app/api/v1/market_data.py
git add apps/backend/app/market_data/quotes.py
git add apps/backend/app/main.py
git add apps/backend/app/ws/gateway.py
git add apps/backend/app/ws/replay.py

git commit -m "feat(api): rest endpoints + ws topic publishing for orders/positions/account

- /api/v1/account: real AccountState (replaces P0 stub)
- /api/v1/orders: POST/GET/GET-by-id/DELETE/PATCH, all routed through OrderRouter
- /api/v1/positions: list + close-position (also through OrderRouter)
- /api/v1/quotes/{symbol} and /api/v1/bars/{symbol}: free-tier IEX
- Pydantic schemas with extra='forbid' (no silent risk-engine bypass)
- WS gateway: topic subscriptions, per-topic replay buffer, translates
  bus events to stable WS topics

Frontend lands in PR 6B/6C."

git push -u origin feat/p1-rest-api-and-ws-topics
gh pr create --title "feat(api): REST endpoints + WS topic publishing" \
  --body "P1 Session 6 PR 1 of 3. Full backend HTTP/WS surface for frontend to code against."
gh pr checks
gh pr merge --merge --delete-branch
git checkout main && git pull
```

- [ ] PR 6A merged.

---

## PR 6B — Order Ticket, Orders Page, Positions Page

Cut the branch:

```bash
git checkout -b feat/p1-trading-ui-core
```

This PR introduces the core trading UX. Everything is React/TypeScript in `apps/frontend/src/`.

### 6B.1 — Typed API client

Create `apps/frontend/src/api/types.ts`:

```typescript
// Matches Pydantic schemas in apps/backend/app/api/v1/schemas/. If you change
// either side, change the other.

export type OrderSide = "buy" | "sell";
export type OrderType = "market" | "limit" | "stop" | "stop_limit";
export type TimeInForce = "day" | "gtc" | "ioc" | "fok";
export type OrderStatus =
  | "pending_risk"
  | "pending_submit"
  | "submitted"
  | "partially_filled"
  | "filled"
  | "canceled"
  | "expired"
  | "rejected"
  | "replaced";

export type OrderSourceType =
  | "manual"
  | "strategy"
  | "agent_strategy"
  | "agent_proposal"
  | "pine";

export interface Fill {
  id: number;
  broker_fill_id: string | null;
  qty: string; // Decimal serialized as string
  price: string;
  commission: string;
  filled_at: string;
}

export interface RiskCheckSummary {
  id: number;
  decision: "pass" | "reject";
  reason_codes: string[];
  evaluated_at: string;
}

export interface Order {
  id: number;
  broker_order_id: string | null;
  client_order_id: string | null;
  symbol: string;
  side: OrderSide;
  qty: string;
  type: OrderType;
  limit_price: string | null;
  stop_price: string | null;
  tif: TimeInForce;
  extended_hours: boolean;
  status: OrderStatus;
  rejection_reason: string | null;
  source_type: OrderSourceType;
  source_id: string | null;
  created_at: string;
  submitted_at: string | null;
  terminal_at: string | null;
  updated_at: string;
  fills: Fill[];
  risk_check: RiskCheckSummary | null;
}

export interface OrderListResponse {
  items: Order[];
  count: number;
}

export interface OrderCreateRequest {
  symbol: string;
  side: OrderSide;
  qty: string;
  type?: OrderType;
  limit_price?: string;
  stop_price?: string;
  tif?: TimeInForce;
  extended_hours?: boolean;
}

export interface Position {
  id: number;
  symbol: string;
  qty: string;
  avg_entry_price: string;
  side: "long" | "short" | null;
  market_value: string;
  cost_basis: string;
  unrealized_pl: string;
  unrealized_plpc: string;
  updated_at: string;
}

export interface PositionListResponse {
  items: Position[];
  count: number;
  gross_exposure: string;
  net_exposure: string;
  total_unrealized_pl: string;
}

export interface Account {
  account_id: number;
  mode: "paper" | "live";
  status: string;
  cash: string;
  equity: string;
  last_equity: string;
  buying_power: string;
  portfolio_value: string;
  day_change: string;
  day_change_pct: string;
  daytrade_count: number;
  pattern_day_trader: boolean;
  trading_blocked: boolean;
  account_blocked: boolean;
  updated_at: string;
}

export interface Quote {
  symbol: string;
  bid: string | null;
  ask: string | null;
  last: string | null;
  bid_size: number | null;
  ask_size: number | null;
  ts: string | null;
}
```

Create `apps/frontend/src/api/orders.ts`:

```typescript
import { apiFetch } from "./client";
import type {
  Order,
  OrderCreateRequest,
  OrderListResponse,
} from "./types";

export const ordersApi = {
  create: (body: OrderCreateRequest) =>
    apiFetch<Order>("/api/v1/orders", { method: "POST", body }),

  list: (params: { status?: string; symbol?: string; limit?: number } = {}) => {
    const q = new URLSearchParams();
    if (params.status) q.set("status", params.status);
    if (params.symbol) q.set("symbol", params.symbol);
    if (params.limit) q.set("limit", String(params.limit));
    const suffix = q.toString() ? `?${q}` : "";
    return apiFetch<OrderListResponse>(`/api/v1/orders${suffix}`);
  },

  get: (id: number) => apiFetch<Order>(`/api/v1/orders/${id}`),

  cancel: (id: number) =>
    apiFetch<{ order_id: number; requested_action: "cancel"; accepted_by_broker: boolean }>(
      `/api/v1/orders/${id}`,
      { method: "DELETE" },
    ),

  modify: (id: number, body: { new_qty?: string; new_limit_price?: string }) =>
    apiFetch<{ order_id: number; requested_action: "modify"; accepted_by_broker: boolean }>(
      `/api/v1/orders/${id}`,
      { method: "PATCH", body },
    ),
};
```

Create `apps/frontend/src/api/positions.ts`:

```typescript
import { apiFetch } from "./client";
import type { Order, Position, PositionListResponse } from "./types";

export const positionsApi = {
  list: () => apiFetch<PositionListResponse>("/api/v1/positions"),
  close: (symbol: string) =>
    apiFetch<Order>(`/api/v1/positions/${symbol}/close`, {
      method: "POST",
      body: {},
    }),
};
```

Create `apps/frontend/src/api/quotes.ts`:

```typescript
import { apiFetch } from "./client";
import type { Quote } from "./types";

export const quotesApi = {
  get: (symbol: string) => apiFetch<Quote>(`/api/v1/quotes/${symbol}`),
};
```

If `apps/frontend/src/api/client.ts` doesn't already implement `apiFetch`, add it:

```typescript
const API_BASE = import.meta.env.VITE_API_BASE || "http://127.0.0.1:8000";

interface FetchOptions {
  method?: "GET" | "POST" | "PUT" | "DELETE" | "PATCH";
  body?: unknown;
}

export class ApiError extends Error {
  constructor(public status: number, public detail: string) {
    super(`API ${status}: ${detail}`);
  }
}

export async function apiFetch<T>(path: string, opts: FetchOptions = {}): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    method: opts.method || "GET",
    headers: { "Content-Type": "application/json" },
    body: opts.body !== undefined ? JSON.stringify(opts.body) : undefined,
  });
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const j = await res.json();
      detail = j.detail || JSON.stringify(j);
    } catch {
      // body wasn't JSON
    }
    throw new ApiError(res.status, detail);
  }
  return (await res.json()) as T;
}
```

### 6B.2 — Reason-code translations

Create `apps/frontend/src/lib/risk-reasons.ts`:

```typescript
// Mirrors apps/backend/app/risk/reason_codes.py DESCRIPTIONS map.

export const RISK_REASON_DESCRIPTIONS: Record<string, string> = {
  OK: "Risk checks passed.",
  MODE_MISMATCH: "Order account does not match current trading mode.",
  SYMBOL_DENIED: "Symbol is not allowed by your current risk policy.",
  SHORT_NOT_ALLOWED: "Short selling is not permitted by your risk policy.",
  EXTENDED_HOURS_NOT_ALLOWED: "Extended-hours trading is not permitted for this order type.",
  POSITION_CAP_QTY: "This order would breach your maximum position quantity cap.",
  POSITION_CAP_NOTIONAL: "This order would breach your maximum position notional ($) cap.",
  GROSS_EXPOSURE: "This order would breach your maximum gross exposure cap.",
  HALT_REACHED: "Trading is halted; the daily loss limit was reached.",
  RATE_LIMIT: "You've placed too many orders in the last minute.",
  INVALID_INPUT: "Order has invalid quantity, price, or time-in-force.",
  NO_QUOTE: "No recent price quote available to evaluate the notional cap.",
};

export function describeReason(code: string): string {
  return RISK_REASON_DESCRIPTIONS[code] || code;
}

export function describeReasons(codes: string[]): string {
  if (codes.length === 0) return "(no reason given)";
  return codes.map(describeReason).join(" ");
}
```

### 6B.3 — Order Ticket component

Create `apps/frontend/src/components/ticket/OrderTicket.tsx`:

```tsx
import { useState, useEffect } from "react";
import { ordersApi } from "@/api/orders";
import { quotesApi } from "@/api/quotes";
import { ApiError } from "@/api/client";
import type { OrderSide, OrderType, TimeInForce, Order } from "@/api/types";
import { describeReasons } from "@/lib/risk-reasons";

interface Props {
  defaultSymbol?: string;
  onSubmitted?: (order: Order) => void;
}

export function OrderTicket({ defaultSymbol = "", onSubmitted }: Props) {
  const [symbol, setSymbol] = useState(defaultSymbol);
  const [side, setSide] = useState<OrderSide>("buy");
  const [qty, setQty] = useState("1");
  const [type, setType] = useState<OrderType>("market");
  const [limitPrice, setLimitPrice] = useState("");
  const [stopPrice, setStopPrice] = useState("");
  const [tif, setTif] = useState<TimeInForce>("day");
  const [extendedHours, setExtendedHours] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [lastSubmittedOrder, setLastSubmittedOrder] = useState<Order | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [quote, setQuote] = useState<{ bid?: string; ask?: string; last?: string } | null>(null);

  // Pull quote when symbol changes (debounced 500ms)
  useEffect(() => {
    if (!symbol || symbol.length < 1) {
      setQuote(null);
      return;
    }
    let cancelled = false;
    const t = setTimeout(async () => {
      try {
        const q = await quotesApi.get(symbol.toUpperCase());
        if (!cancelled) {
          setQuote({
            bid: q.bid || undefined,
            ask: q.ask || undefined,
            last: q.last || undefined,
          });
        }
      } catch {
        if (!cancelled) setQuote(null);
      }
    }, 500);
    return () => {
      cancelled = true;
      clearTimeout(t);
    };
  }, [symbol]);

  async function handleSubmit() {
    if (!symbol) {
      setError("Symbol is required");
      return;
    }
    if (Number(qty) <= 0) {
      setError("Quantity must be positive");
      return;
    }
    if ((type === "limit" || type === "stop_limit") && !limitPrice) {
      setError("Limit price required for limit/stop-limit orders");
      return;
    }
    if ((type === "stop" || type === "stop_limit") && !stopPrice) {
      setError("Stop price required for stop/stop-limit orders");
      return;
    }
    setError(null);
    setSubmitting(true);
    try {
      const order = await ordersApi.create({
        symbol: symbol.toUpperCase(),
        side,
        qty,
        type,
        limit_price: limitPrice || undefined,
        stop_price: stopPrice || undefined,
        tif,
        extended_hours: extendedHours,
      });
      setLastSubmittedOrder(order);
      onSubmitted?.(order);
      // On clean success, keep the symbol but reset qty so a stray Enter
      // doesn't reorder.
      setQty("1");
    } catch (e) {
      if (e instanceof ApiError) {
        setError(`${e.detail} (status ${e.status})`);
      } else {
        setError(String(e));
      }
    } finally {
      setSubmitting(false);
    }
  }

  const lastIsRejected =
    lastSubmittedOrder?.status === "rejected" && lastSubmittedOrder.risk_check?.decision === "reject";
  const lastIsBrokerRejected =
    lastSubmittedOrder?.status === "rejected" &&
    lastSubmittedOrder.rejection_reason?.startsWith("broker_error");

  return (
    <div className="space-y-3 rounded-lg border border-gray-700 bg-gray-900 p-4">
      <div className="flex gap-2">
        <input
          type="text"
          value={symbol}
          onChange={(e) => setSymbol(e.target.value)}
          placeholder="Symbol (e.g., AAPL)"
          className="flex-1 rounded bg-gray-800 px-3 py-2 text-white"
        />
        {quote && (
          <div className="text-sm text-gray-300">
            {quote.bid && <span>bid {quote.bid} </span>}
            {quote.ask && <span>ask {quote.ask} </span>}
            {quote.last && <span className="text-white">last {quote.last}</span>}
          </div>
        )}
      </div>

      <div className="flex gap-2">
        <button
          onClick={() => setSide("buy")}
          className={`flex-1 rounded py-2 font-semibold ${
            side === "buy" ? "bg-green-600 text-white" : "bg-gray-800 text-gray-300"
          }`}
        >
          BUY
        </button>
        <button
          onClick={() => setSide("sell")}
          className={`flex-1 rounded py-2 font-semibold ${
            side === "sell" ? "bg-red-600 text-white" : "bg-gray-800 text-gray-300"
          }`}
        >
          SELL
        </button>
      </div>

      <div className="grid grid-cols-2 gap-2">
        <label className="block">
          <span className="text-xs text-gray-400">Qty</span>
          <input
            type="number"
            step="any"
            value={qty}
            onChange={(e) => setQty(e.target.value)}
            className="mt-1 w-full rounded bg-gray-800 px-2 py-1 text-white"
          />
        </label>
        <label className="block">
          <span className="text-xs text-gray-400">Type</span>
          <select
            value={type}
            onChange={(e) => setType(e.target.value as OrderType)}
            className="mt-1 w-full rounded bg-gray-800 px-2 py-1 text-white"
          >
            <option value="market">Market</option>
            <option value="limit">Limit</option>
            <option value="stop">Stop</option>
            <option value="stop_limit">Stop-Limit</option>
          </select>
        </label>
      </div>

      {(type === "limit" || type === "stop_limit") && (
        <label className="block">
          <span className="text-xs text-gray-400">Limit price</span>
          <input
            type="number"
            step="0.01"
            value={limitPrice}
            onChange={(e) => setLimitPrice(e.target.value)}
            className="mt-1 w-full rounded bg-gray-800 px-2 py-1 text-white"
          />
        </label>
      )}
      {(type === "stop" || type === "stop_limit") && (
        <label className="block">
          <span className="text-xs text-gray-400">Stop price</span>
          <input
            type="number"
            step="0.01"
            value={stopPrice}
            onChange={(e) => setStopPrice(e.target.value)}
            className="mt-1 w-full rounded bg-gray-800 px-2 py-1 text-white"
          />
        </label>
      )}

      <div className="grid grid-cols-2 gap-2">
        <label className="block">
          <span className="text-xs text-gray-400">TIF</span>
          <select
            value={tif}
            onChange={(e) => setTif(e.target.value as TimeInForce)}
            className="mt-1 w-full rounded bg-gray-800 px-2 py-1 text-white"
          >
            <option value="day">DAY</option>
            <option value="gtc">GTC</option>
            <option value="ioc">IOC</option>
            <option value="fok">FOK</option>
          </select>
        </label>
        <label className="mt-5 flex items-center gap-2 text-sm text-gray-300">
          <input
            type="checkbox"
            checked={extendedHours}
            onChange={(e) => setExtendedHours(e.target.checked)}
            disabled={type === "market"}
          />
          Extended hours
        </label>
      </div>

      {error && (
        <div className="rounded border border-red-700 bg-red-900/40 p-2 text-sm text-red-200">
          {error}
        </div>
      )}

      {lastIsRejected && lastSubmittedOrder?.risk_check && (
        <div className="rounded border border-amber-700 bg-amber-900/30 p-2 text-sm text-amber-100">
          Order rejected by risk engine:{" "}
          {describeReasons(lastSubmittedOrder.risk_check.reason_codes)}
        </div>
      )}

      {lastIsBrokerRejected && lastSubmittedOrder && (
        <div className="rounded border border-red-700 bg-red-900/30 p-2 text-sm text-red-200">
          Broker rejected the order: {lastSubmittedOrder.rejection_reason}
        </div>
      )}

      {lastSubmittedOrder && lastSubmittedOrder.status !== "rejected" && (
        <div className="rounded border border-emerald-700 bg-emerald-900/30 p-2 text-sm text-emerald-100">
          Order #{lastSubmittedOrder.id} {lastSubmittedOrder.status}
          {lastSubmittedOrder.broker_order_id && (
            <span className="ml-2 text-emerald-300/70">
              broker {lastSubmittedOrder.broker_order_id.slice(0, 8)}…
            </span>
          )}
        </div>
      )}

      <button
        onClick={handleSubmit}
        disabled={submitting || !symbol || Number(qty) <= 0}
        className={`w-full rounded py-2 font-semibold ${
          side === "buy" ? "bg-green-700 hover:bg-green-600" : "bg-red-700 hover:bg-red-600"
        } disabled:bg-gray-700`}
      >
        {submitting ? "Submitting…" : `Submit ${side.toUpperCase()} (paper)`}
      </button>
    </div>
  );
}
```

### 6B.4 — Orders page

Replace `apps/frontend/src/pages/Orders/index.tsx`:

```tsx
import { useEffect, useState } from "react";
import { ordersApi } from "@/api/orders";
import type { Order } from "@/api/types";
import { describeReasons } from "@/lib/risk-reasons";

type Tab = "open" | "history";

export default function OrdersPage() {
  const [tab, setTab] = useState<Tab>("open");
  const [orders, setOrders] = useState<Order[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [selected, setSelected] = useState<Order | null>(null);

  async function load() {
    setLoading(true);
    setError(null);
    try {
      const resp = await ordersApi.list({ status: tab, limit: 200 });
      setOrders(resp.items);
    } catch (e) {
      setError(String(e));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load();
    const id = setInterval(load, 5000);
    return () => clearInterval(id);
  }, [tab]);

  async function handleCancel(order: Order) {
    if (!confirm(`Cancel order #${order.id} (${order.side} ${order.qty} ${order.symbol})?`)) return;
    try {
      await ordersApi.cancel(order.id);
      await load();
    } catch (e) {
      alert(`Cancel failed: ${e}`);
    }
  }

  async function handleModify(order: Order) {
    const newQty = prompt(`New quantity for #${order.id} (current ${order.qty})`, order.qty);
    if (!newQty) return;
    const newLimit =
      order.type === "limit" || order.type === "stop_limit"
        ? prompt(`New limit price (current ${order.limit_price || "—"})`, order.limit_price || "")
        : null;
    try {
      await ordersApi.modify(order.id, {
        new_qty: newQty,
        new_limit_price: newLimit || undefined,
      });
      await load();
    } catch (e) {
      alert(`Modify failed: ${e}`);
    }
  }

  return (
    <div className="space-y-4 p-4">
      <div className="flex gap-4">
        {(["open", "history"] as Tab[]).map((t) => (
          <button
            key={t}
            onClick={() => setTab(t)}
            className={`rounded px-4 py-2 text-sm font-semibold ${
              tab === t ? "bg-blue-600 text-white" : "bg-gray-800 text-gray-300"
            }`}
          >
            {t === "open" ? "Working" : "History"}
          </button>
        ))}
        <button
          onClick={load}
          className="ml-auto rounded bg-gray-700 px-3 py-1 text-sm text-gray-200"
        >
          Refresh
        </button>
      </div>

      {error && <div className="rounded border border-red-700 bg-red-900/40 p-2 text-red-200">{error}</div>}

      <div className="overflow-x-auto rounded border border-gray-800">
        <table className="w-full text-left text-sm">
          <thead className="bg-gray-800 text-gray-300">
            <tr>
              <th className="px-3 py-2">Time</th>
              <th className="px-3 py-2">Symbol</th>
              <th className="px-3 py-2">Side</th>
              <th className="px-3 py-2">Qty</th>
              <th className="px-3 py-2">Type</th>
              <th className="px-3 py-2">Limit/Stop</th>
              <th className="px-3 py-2">Status</th>
              <th className="px-3 py-2">Fills</th>
              <th className="px-3 py-2"></th>
            </tr>
          </thead>
          <tbody>
            {orders.length === 0 && !loading && (
              <tr><td colSpan={9} className="px-3 py-4 text-center text-gray-500">No orders</td></tr>
            )}
            {orders.map((o) => (
              <tr
                key={o.id}
                onClick={() => setSelected(o)}
                className="cursor-pointer border-t border-gray-800 hover:bg-gray-900"
              >
                <td className="px-3 py-2">{new Date(o.created_at).toLocaleTimeString()}</td>
                <td className="px-3 py-2 font-semibold">{o.symbol}</td>
                <td className={`px-3 py-2 ${o.side === "buy" ? "text-green-400" : "text-red-400"}`}>
                  {o.side.toUpperCase()}
                </td>
                <td className="px-3 py-2">{o.qty}</td>
                <td className="px-3 py-2">{o.type}</td>
                <td className="px-3 py-2">{o.limit_price || o.stop_price || "—"}</td>
                <td className="px-3 py-2">{o.status}</td>
                <td className="px-3 py-2">
                  {o.fills.length > 0
                    ? `${o.fills.reduce((s, f) => s + Number(f.qty), 0)} @ ${(
                        o.fills.reduce((s, f) => s + Number(f.qty) * Number(f.price), 0) /
                        o.fills.reduce((s, f) => s + Number(f.qty), 0)
                      ).toFixed(2)}`
                    : "—"}
                </td>
                <td className="px-3 py-2 text-right">
                  {tab === "open" && (
                    <div className="flex justify-end gap-1">
                      <button
                        onClick={(e) => { e.stopPropagation(); handleCancel(o); }}
                        className="rounded bg-gray-700 px-2 py-1 text-xs"
                      >
                        Cancel
                      </button>
                      <button
                        onClick={(e) => { e.stopPropagation(); handleModify(o); }}
                        className="rounded bg-gray-700 px-2 py-1 text-xs"
                      >
                        Modify
                      </button>
                    </div>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {selected && (
        <div className="fixed inset-y-0 right-0 w-96 overflow-y-auto border-l border-gray-800 bg-gray-950 p-4">
          <div className="mb-3 flex items-center justify-between">
            <h3 className="text-lg font-semibold text-white">Order #{selected.id}</h3>
            <button onClick={() => setSelected(null)} className="text-gray-400">✕</button>
          </div>
          <dl className="space-y-2 text-sm text-gray-300">
            <div><dt className="text-gray-500">Symbol</dt><dd>{selected.symbol}</dd></div>
            <div><dt className="text-gray-500">Side / Qty / Type</dt><dd>{selected.side} {selected.qty} {selected.type}</dd></div>
            <div><dt className="text-gray-500">Status</dt><dd>{selected.status}</dd></div>
            <div><dt className="text-gray-500">Source</dt><dd>{selected.source_type}</dd></div>
            <div><dt className="text-gray-500">Broker ID</dt><dd className="break-all">{selected.broker_order_id || "—"}</dd></div>
            <div><dt className="text-gray-500">Created</dt><dd>{new Date(selected.created_at).toLocaleString()}</dd></div>
            {selected.risk_check && (
              <div>
                <dt className="text-gray-500">Risk check</dt>
                <dd className={selected.risk_check.decision === "pass" ? "text-emerald-400" : "text-amber-300"}>
                  {selected.risk_check.decision}
                  {selected.risk_check.decision === "reject" && (
                    <div className="mt-1 text-amber-200">{describeReasons(selected.risk_check.reason_codes)}</div>
                  )}
                </dd>
              </div>
            )}
            {selected.fills.length > 0 && (
              <div>
                <dt className="text-gray-500">Fills</dt>
                <dd>
                  {selected.fills.map((f) => (
                    <div key={f.id}>{f.qty} @ {f.price} ({new Date(f.filled_at).toLocaleTimeString()})</div>
                  ))}
                </dd>
              </div>
            )}
          </dl>
        </div>
      )}
    </div>
  );
}
```

### 6B.5 — Positions page

Replace `apps/frontend/src/pages/Positions/index.tsx`:

```tsx
import { useEffect, useState } from "react";
import { positionsApi } from "@/api/positions";
import type { Position, PositionListResponse } from "@/api/types";

export default function PositionsPage() {
  const [data, setData] = useState<PositionListResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function load() {
    setLoading(true);
    setError(null);
    try {
      const resp = await positionsApi.list();
      setData(resp);
    } catch (e) {
      setError(String(e));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load();
    const id = setInterval(load, 5000);
    return () => clearInterval(id);
  }, []);

  async function handleClose(p: Position) {
    if (!confirm(`Market-close ${p.qty} ${p.symbol} (paper)?`)) return;
    try {
      const order = await positionsApi.close(p.symbol);
      if (order.status === "rejected") {
        alert(`Close rejected: ${order.rejection_reason || "see risk check"}`);
      } else {
        await load();
      }
    } catch (e) {
      alert(`Close failed: ${e}`);
    }
  }

  return (
    <div className="space-y-4 p-4">
      <div className="flex items-center justify-between">
        <h2 className="text-xl font-semibold text-white">Positions</h2>
        <button onClick={load} className="rounded bg-gray-700 px-3 py-1 text-sm text-gray-200">
          Refresh
        </button>
      </div>

      {error && <div className="rounded border border-red-700 bg-red-900/40 p-2 text-red-200">{error}</div>}

      <div className="rounded border border-gray-800">
        <table className="w-full text-left text-sm">
          <thead className="bg-gray-800 text-gray-300">
            <tr>
              <th className="px-3 py-2">Symbol</th>
              <th className="px-3 py-2">Side</th>
              <th className="px-3 py-2 text-right">Qty</th>
              <th className="px-3 py-2 text-right">Avg Entry</th>
              <th className="px-3 py-2 text-right">Market Value</th>
              <th className="px-3 py-2 text-right">Unrealized P&L</th>
              <th className="px-3 py-2 text-right">%</th>
              <th className="px-3 py-2"></th>
            </tr>
          </thead>
          <tbody>
            {(!data || data.items.length === 0) && (
              <tr><td colSpan={8} className="px-3 py-4 text-center text-gray-500">No open positions</td></tr>
            )}
            {data?.items.map((p) => {
              const pl = Number(p.unrealized_pl);
              return (
                <tr key={p.id} className="border-t border-gray-800">
                  <td className="px-3 py-2 font-semibold">{p.symbol}</td>
                  <td className="px-3 py-2">{p.side || "—"}</td>
                  <td className="px-3 py-2 text-right">{p.qty}</td>
                  <td className="px-3 py-2 text-right">{Number(p.avg_entry_price).toFixed(2)}</td>
                  <td className="px-3 py-2 text-right">{Number(p.market_value).toFixed(2)}</td>
                  <td className={`px-3 py-2 text-right ${pl > 0 ? "text-emerald-400" : pl < 0 ? "text-red-400" : ""}`}>
                    {pl.toFixed(2)}
                  </td>
                  <td className={`px-3 py-2 text-right ${pl > 0 ? "text-emerald-400" : pl < 0 ? "text-red-400" : ""}`}>
                    {(Number(p.unrealized_plpc) * 100).toFixed(2)}%
                  </td>
                  <td className="px-3 py-2 text-right">
                    <button
                      onClick={() => handleClose(p)}
                      className="rounded bg-red-800 px-2 py-1 text-xs text-white hover:bg-red-700"
                    >
                      Close
                    </button>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      {data && data.items.length > 0 && (
        <div className="rounded border border-gray-800 bg-gray-900 p-3 text-sm text-gray-300">
          <div className="grid grid-cols-3 gap-4">
            <div>
              <div className="text-xs text-gray-500">Gross exposure</div>
              <div className="text-lg text-white">${Number(data.gross_exposure).toFixed(2)}</div>
            </div>
            <div>
              <div className="text-xs text-gray-500">Net exposure</div>
              <div className="text-lg text-white">${Number(data.net_exposure).toFixed(2)}</div>
            </div>
            <div>
              <div className="text-xs text-gray-500">Total unrealized P&L</div>
              <div className={`text-lg ${Number(data.total_unrealized_pl) >= 0 ? "text-emerald-400" : "text-red-400"}`}>
                ${Number(data.total_unrealized_pl).toFixed(2)}
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
```

### 6B.6 — Wire the ticket into Opportunities (placeholder page)

P1 doesn't ship the full Opportunities page; it lives in P4. For now, replace the placeholder at `apps/frontend/src/pages/Opportunities/index.tsx` with a "Manual order entry" page that just hosts the ticket:

```tsx
import { OrderTicket } from "@/components/ticket/OrderTicket";

export default function OpportunitiesPage() {
  return (
    <div className="space-y-4 p-4">
      <h2 className="text-xl font-semibold text-white">Manual Order Entry</h2>
      <p className="text-sm text-gray-400">
        Discovery, indicators, and curated lists land in P4. For now this page hosts the order ticket.
      </p>
      <OrderTicket />
    </div>
  );
}
```

### 6B.7 — Quick smoke

```bash
./scripts/dev.sh &
sleep 30
# Open http://localhost:5173/orders, http://localhost:5173/positions,
# http://localhost:5173/opportunities
# Place a 1-share Ford order via the ticket; observe it flow through:
# - Orders page shows it in "Working" tab, then transitions to "History"/Filled
# - Positions page shows the new position
# - Click "Close" on the position; observe new sell order, position goes to zero
```

- [ ] Order ticket submits a paper order end-to-end.
- [ ] Orders page lists it; cancel + modify buttons work.
- [ ] Positions page shows the position; Close button works through `/api/v1/positions/{symbol}/close`.
- [ ] Risk rejection (try BUY 100000 F) shows the amber banner with plain-English reason.

### 6B.8 — Commit and PR (6B)

```bash
git add apps/frontend/src/api/
git add apps/frontend/src/lib/risk-reasons.ts
git add apps/frontend/src/components/ticket/
git add apps/frontend/src/pages/Orders/
git add apps/frontend/src/pages/Positions/
git add apps/frontend/src/pages/Opportunities/

git commit -m "feat(frontend): order ticket + orders + positions pages

- Typed API client (api/orders, positions, quotes) matching backend schemas
- OrderTicket component with all P1 order types, TIF, brackets, and live quote
- Risk-rejection banner with plain-English descriptions from risk-reasons.ts
- Orders page: working/history tabs, inline cancel/modify, detail drawer
- Positions page: live P&L table, Close (market) action via same /orders path
- Opportunities placeholder hosts the ticket (full discovery UI lands P4)"

git push -u origin feat/p1-trading-ui-core
gh pr create --title "feat(frontend): order ticket + orders + positions pages" \
  --body "P1 Session 6 PR 2 of 3. Core trading UX."
gh pr checks
gh pr merge --merge --delete-branch
git checkout main && git pull
```

- [ ] PR 6B merged.

---

## PR 6C — Charts, Dashboard, Live-Mode Gates

Cut the branch:

```bash
git checkout -b feat/p1-charts-dashboard-livemode
```

### 6C.1 — TradingView chart embed

Create `apps/frontend/src/components/chart/TVChart.tsx`:

```tsx
import { useEffect, useRef } from "react";

interface Props {
  symbol: string;
  exchange?: string;
  interval?: "1" | "5" | "15" | "60" | "D";
}

// Tiny client-side ticker -> TV-symbol map. Falls back to symbol if unknown.
const SYMBOL_MAP: Record<string, string> = {
  AAPL: "NASDAQ:AAPL",
  MSFT: "NASDAQ:MSFT",
  NVDA: "NASDAQ:NVDA",
  TSLA: "NASDAQ:TSLA",
  AMD: "NASDAQ:AMD",
  GOOGL: "NASDAQ:GOOGL",
  AMZN: "NASDAQ:AMZN",
  META: "NASDAQ:META",
  SPY: "AMEX:SPY",
  QQQ: "NASDAQ:QQQ",
  F: "NYSE:F",
};

export function TVChart({ symbol, interval = "5" }: Props) {
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!containerRef.current) return;
    const tvSymbol = SYMBOL_MAP[symbol.toUpperCase()] || symbol.toUpperCase();
    containerRef.current.innerHTML = "";

    const script = document.createElement("script");
    script.src = "https://s3.tradingview.com/external-embedding/embed-widget-advanced-chart.js";
    script.async = true;
    script.innerHTML = JSON.stringify({
      autosize: true,
      symbol: tvSymbol,
      interval,
      timezone: "America/New_York",
      theme: "dark",
      style: "1",
      locale: "en",
      hide_side_toolbar: false,
      allow_symbol_change: true,
      withdateranges: true,
      details: true,
      studies: ["MASimple@tv-basicstudies"],
      container_id: "tv-chart",
    });
    const wrapper = document.createElement("div");
    wrapper.className = "tradingview-widget-container";
    wrapper.style.height = "100%";
    wrapper.style.width = "100%";
    wrapper.innerHTML = `<div id="tv-chart" style="height: calc(100% - 32px); width: 100%;"></div>`;
    wrapper.appendChild(script);
    containerRef.current.appendChild(wrapper);
  }, [symbol, interval]);

  return <div ref={containerRef} className="h-full w-full" />;
}
```

Replace `apps/frontend/src/pages/Charts/index.tsx`:

```tsx
import { useState } from "react";
import { TVChart } from "@/components/chart/TVChart";

const SEED_SYMBOLS = ["AAPL", "MSFT", "NVDA", "SPY", "QQQ", "F", "TSLA", "AMD", "GOOGL", "AMZN", "META"];

export default function ChartsPage() {
  const [symbol, setSymbol] = useState("AAPL");
  const [input, setInput] = useState("");

  return (
    <div className="flex h-[calc(100vh-4rem)] flex-col">
      <div className="flex items-center gap-2 border-b border-gray-800 p-3">
        <input
          type="text"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && input) {
              setSymbol(input.toUpperCase());
              setInput("");
            }
          }}
          placeholder="Symbol (Enter to load)"
          className="rounded bg-gray-800 px-3 py-1 text-white"
        />
        <span className="text-sm text-gray-400">Quick:</span>
        {SEED_SYMBOLS.map((s) => (
          <button
            key={s}
            onClick={() => setSymbol(s)}
            className={`rounded px-2 py-1 text-xs ${
              symbol === s ? "bg-blue-600 text-white" : "bg-gray-800 text-gray-300"
            }`}
          >
            {s}
          </button>
        ))}
        <span className="ml-auto text-sm text-gray-300">Showing: <span className="text-white">{symbol}</span></span>
      </div>
      <div className="flex-1">
        <TVChart symbol={symbol} interval="5" />
      </div>
    </div>
  );
}
```

### 6C.2 — Dashboard (real data)

Create `apps/frontend/src/api/account.ts`:

```typescript
import { apiFetch } from "./client";
import type { Account } from "./types";

export const accountApi = {
  get: () => apiFetch<Account>("/api/v1/account"),
};
```

Replace `apps/frontend/src/pages/Dashboard/index.tsx`:

```tsx
import { useEffect, useState } from "react";
import { accountApi } from "@/api/account";
import { ordersApi } from "@/api/orders";
import { positionsApi } from "@/api/positions";
import type { Account, Order, Position } from "@/api/types";

function Card({ title, value, sub }: { title: string; value: string; sub?: string }) {
  return (
    <div className="rounded-lg border border-gray-800 bg-gray-900 p-4">
      <div className="text-xs text-gray-500">{title}</div>
      <div className="mt-1 text-2xl font-semibold text-white">{value}</div>
      {sub && <div className="mt-1 text-xs text-gray-400">{sub}</div>}
    </div>
  );
}

export default function DashboardPage() {
  const [account, setAccount] = useState<Account | null>(null);
  const [openOrders, setOpenOrders] = useState<Order[]>([]);
  const [positions, setPositions] = useState<Position[]>([]);
  const [error, setError] = useState<string | null>(null);

  async function load() {
    try {
      const [acc, ords, pos] = await Promise.all([
        accountApi.get().catch(() => null),
        ordersApi.list({ status: "open" }).catch(() => ({ items: [], count: 0 })),
        positionsApi.list().catch(() => ({ items: [], count: 0, gross_exposure: "0", net_exposure: "0", total_unrealized_pl: "0" })),
      ]);
      setAccount(acc);
      setOpenOrders(ords.items);
      setPositions(pos.items);
      setError(null);
    } catch (e) {
      setError(String(e));
    }
  }

  useEffect(() => {
    load();
    const id = setInterval(load, 5000);
    return () => clearInterval(id);
  }, []);

  const dayPL = account ? Number(account.day_change) : 0;
  const dayPLPct = account ? Number(account.day_change_pct) : 0;

  return (
    <div className="space-y-4 p-4">
      <div className="text-xl font-semibold text-white">Dashboard</div>
      {error && <div className="rounded border border-red-700 bg-red-900/40 p-2 text-red-200">{error}</div>}

      <div className="grid grid-cols-4 gap-3">
        <Card
          title="Equity"
          value={account ? `$${Number(account.equity).toFixed(2)}` : "…"}
          sub={account ? `Cash: $${Number(account.cash).toFixed(2)}` : undefined}
        />
        <Card
          title="Buying power"
          value={account ? `$${Number(account.buying_power).toFixed(2)}` : "…"}
        />
        <Card
          title="Day P&L"
          value={
            account
              ? `${dayPL >= 0 ? "+" : ""}$${dayPL.toFixed(2)} (${(dayPLPct).toFixed(2)}%)`
              : "…"
          }
          sub={account?.status}
        />
        <Card
          title="Open / Positions"
          value={`${openOrders.length} / ${positions.length}`}
        />
      </div>

      <div className="grid grid-cols-2 gap-3">
        <div className="rounded-lg border border-gray-800 bg-gray-900 p-4">
          <div className="mb-2 text-sm font-semibold text-gray-300">Working orders</div>
          {openOrders.length === 0 ? (
            <div className="text-sm text-gray-500">None</div>
          ) : (
            <ul className="space-y-1 text-sm">
              {openOrders.slice(0, 8).map((o) => (
                <li key={o.id} className="flex justify-between">
                  <span className={o.side === "buy" ? "text-green-400" : "text-red-400"}>
                    {o.side.toUpperCase()} {o.qty} {o.symbol}
                  </span>
                  <span className="text-gray-500">{o.status}</span>
                </li>
              ))}
            </ul>
          )}
        </div>
        <div className="rounded-lg border border-gray-800 bg-gray-900 p-4">
          <div className="mb-2 text-sm font-semibold text-gray-300">Positions</div>
          {positions.length === 0 ? (
            <div className="text-sm text-gray-500">None</div>
          ) : (
            <ul className="space-y-1 text-sm">
              {positions.slice(0, 8).map((p) => (
                <li key={p.id} className="flex justify-between">
                  <span>{p.symbol} ({p.qty})</span>
                  <span className={Number(p.unrealized_pl) >= 0 ? "text-emerald-400" : "text-red-400"}>
                    ${Number(p.unrealized_pl).toFixed(2)}
                  </span>
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>
    </div>
  );
}
```

### 6C.3 — Live-mode banner + confirmation modal

Create `apps/frontend/src/components/ui/ModeBanner.tsx`:

```tsx
import { useEffect, useState } from "react";
import { accountApi } from "@/api/account";

export function ModeBanner() {
  const [mode, setMode] = useState<"paper" | "live" | "unknown">("unknown");
  const [halted, setHalted] = useState(false);

  useEffect(() => {
    let cancelled = false;
    async function load() {
      try {
        const a = await accountApi.get();
        if (!cancelled) setMode(a.mode);
      } catch {
        if (!cancelled) setMode("unknown");
      }
    }
    load();
    const id = setInterval(load, 10_000);
    return () => { cancelled = true; clearInterval(id); };
  }, []);

  // Halt state isn't yet exposed as a REST field; P5 adds it. Surface as
  // "off" for now.

  if (mode === "live") {
    return (
      <div className="flex items-center justify-center bg-red-600 py-1 text-sm font-semibold text-white">
        ⚠️ LIVE TRADING — REAL ORDERS WILL BE PLACED
      </div>
    );
  }
  if (mode === "paper") {
    return (
      <div className="flex items-center justify-center bg-amber-500 py-1 text-sm font-semibold text-amber-950">
        📝 PAPER TRADING — practice mode, no real orders
      </div>
    );
  }
  return (
    <div className="flex items-center justify-center bg-gray-700 py-1 text-sm text-gray-200">
      Connecting…
    </div>
  );
}
```

Create `apps/frontend/src/components/ticket/LiveConfirmModal.tsx`:

```tsx
import { useState } from "react";

interface Props {
  symbol: string;
  side: "buy" | "sell";
  qty: string;
  type: string;
  onConfirm: () => void;
  onCancel: () => void;
}

export function LiveConfirmModal({ symbol, side, qty, type, onConfirm, onCancel }: Props) {
  const [check1, setCheck1] = useState(false);
  const [check2, setCheck2] = useState(false);
  const [typed, setTyped] = useState("");
  const ready = check1 && check2 && typed.toUpperCase() === symbol.toUpperCase();

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/80">
      <div className="w-[28rem] rounded-lg border-2 border-red-600 bg-gray-950 p-6">
        <h2 className="mb-2 text-lg font-bold text-red-400">⚠️ Confirm Live Order</h2>
        <p className="mb-4 text-sm text-gray-300">
          You are about to place a <span className="font-bold text-white">REAL</span> order
          against Alpaca's <span className="font-bold text-white">live</span> account.
        </p>
        <div className="mb-4 rounded bg-gray-900 p-3 text-base text-white">
          <span className={side === "buy" ? "text-green-400" : "text-red-400"}>{side.toUpperCase()}</span>{" "}
          <span className="font-mono">{qty}</span> <span className="font-bold">{symbol}</span>{" "}
          <span className="text-gray-400">({type})</span>
        </div>
        <div className="space-y-2 text-sm text-gray-300">
          <label className="flex items-start gap-2">
            <input type="checkbox" checked={check1} onChange={(e) => setCheck1(e.target.checked)} />
            <span>I understand this is a live order.</span>
          </label>
          <label className="flex items-start gap-2">
            <input type="checkbox" checked={check2} onChange={(e) => setCheck2(e.target.checked)} />
            <span>I understand orders cannot be unsent.</span>
          </label>
          <label className="block">
            <span>Type <span className="font-mono text-white">{symbol}</span> to confirm:</span>
            <input
              type="text"
              value={typed}
              onChange={(e) => setTyped(e.target.value)}
              className="mt-1 w-full rounded bg-gray-800 px-2 py-1 font-mono text-white"
            />
          </label>
        </div>
        <div className="mt-4 flex gap-2">
          <button onClick={onCancel} className="flex-1 rounded bg-gray-700 py-2 text-white hover:bg-gray-600">
            Cancel
          </button>
          <button
            onClick={onConfirm}
            disabled={!ready}
            className="flex-1 rounded bg-red-700 py-2 font-semibold text-white hover:bg-red-600 disabled:bg-gray-800 disabled:text-gray-500"
          >
            Submit live order
          </button>
        </div>
      </div>
    </div>
  );
}
```

Wire the modal into the OrderTicket. Edit `OrderTicket.tsx` and add this logic just before the `handleSubmit` call:

```tsx
// (Top of file)
import { accountApi } from "@/api/account";
import { LiveConfirmModal } from "./LiveConfirmModal";

// Inside the component:
const [pendingSubmit, setPendingSubmit] = useState(false);
const [mode, setMode] = useState<"paper" | "live">("paper");

useEffect(() => {
  accountApi.get().then((a) => setMode(a.mode)).catch(() => setMode("paper"));
}, []);

async function attemptSubmit() {
  if (mode === "live") {
    setPendingSubmit(true);
    return;
  }
  await handleSubmit();
}

// Replace the existing onClick={handleSubmit} on the Submit button with:
//   onClick={attemptSubmit}

// At the end of the JSX (just before the closing </div>), render the modal:
{pendingSubmit && (
  <LiveConfirmModal
    symbol={symbol.toUpperCase()}
    side={side}
    qty={qty}
    type={type}
    onConfirm={async () => { setPendingSubmit(false); await handleSubmit(); }}
    onCancel={() => setPendingSubmit(false)}
  />
)}
```

### 6C.4 — Mount the banner in App.tsx

Edit `apps/frontend/src/App.tsx`. Add ModeBanner at the top of the page shell:

```tsx
import { ModeBanner } from "@/components/ui/ModeBanner";

// In the JSX, wrap the existing layout:
return (
  <>
    <ModeBanner />
    {/* existing sidebar + main content */}
  </>
);
```

### 6C.5 — Quick smoke

```bash
./scripts/dev.sh &
sleep 30
# Visit http://localhost:5173/
# - Amber PAPER banner at top
# - Dashboard shows real cash/equity/buying power, day P&L
# - Charts page loads TradingView widget for AAPL by default; quick-buttons work
# - Ticket in /opportunities behaves normally (no modal in paper mode)
# - (Optional) set WORKBENCH_TRADING_MODE=live in .env, restart, observe:
#   * banner turns red
#   * ticket submit pops the confirmation modal
#   * actually submitting still goes to Alpaca live (so don't do it unless intended)
```

- [ ] Charts page renders TradingView widget.
- [ ] Dashboard shows real account/orders/positions numbers.
- [ ] Mode banner is amber in paper mode.
- [ ] Toggling to live mode shows red banner; ticket submit pops modal.

### 6C.6 — Commit and PR (6C)

```bash
git add apps/frontend/src/components/chart/
git add apps/frontend/src/components/ui/ModeBanner.tsx
git add apps/frontend/src/components/ticket/LiveConfirmModal.tsx
git add apps/frontend/src/components/ticket/OrderTicket.tsx
git add apps/frontend/src/pages/Charts/
git add apps/frontend/src/pages/Dashboard/
git add apps/frontend/src/api/account.ts
git add apps/frontend/src/App.tsx

git commit -m "feat(frontend): charts page, real dashboard, live-mode UX gates

- TVChart wrapper around TradingView's free Advanced Charts widget
- Charts page: symbol picker + 11 seed shortcuts + 5min default chart
- Dashboard now consumes /api/v1/account + /orders?status=open + /positions
  (replaces P0 stub-JSON)
- ModeBanner: amber for paper, red for live, gray for connecting
- LiveConfirmModal: two-checkbox + type-the-symbol confirmation for every
  live submit; resets per session by design (no 'remember' affordance)
- Banner mounted globally in App.tsx"

git push -u origin feat/p1-charts-dashboard-livemode
gh pr create --title "feat(frontend): charts + real dashboard + live-mode gates" \
  --body "P1 Session 6 PR 3 of 3. Polish + safety scaffolding for P5."
gh pr checks
gh pr merge --merge --delete-branch
git checkout main && git pull
```

- [ ] PR 6C merged.

---

## Final Verification

```bash
./scripts/dev.sh &
sleep 30

# 1. All endpoints respond
curl -s http://127.0.0.1:8000/api/v1/account | jq '{mode,status,equity}'
curl -s http://127.0.0.1:8000/api/v1/orders | jq '.count'
curl -s http://127.0.0.1:8000/api/v1/positions | jq '.count'
curl -s http://127.0.0.1:8000/api/v1/quotes/AAPL | jq '{symbol,last}'

# 2. End-to-end from the UI
# Open http://localhost:5173/
#   - Dashboard: real numbers
#   - Opportunities: place 1-share F buy via ticket
#   - Orders: see the order, then see it fill
#   - Positions: see F position appear; click Close; watch it disappear
#   - Charts: load AAPL, change to NVDA, type custom symbol

# 3. Risk rejection visible in UI
# In /opportunities, try BUY 100000 F. Expect amber banner:
# "Order rejected by risk engine: This order would breach your maximum
#  position quantity cap."

# Cleanup
curl -X DELETE https://paper-api.alpaca.markets/v2/positions \
  -H "APCA-API-KEY-ID: $ALPACA_PAPER_API_KEY" \
  -H "APCA-API-SECRET-KEY: $ALPACA_PAPER_API_SECRET"
docker compose down
```

- [ ] All four GET endpoints return real data.
- [ ] Full UI flow (ticket → orders → fill → position → close) works.
- [ ] Risk rejection surfaces in the UI with plain-English text.

---

## Sign-off

```bash
git tag -a p1-session6-complete -m "P1 Session 6 complete: REST + WS topics + frontend trading UI"
git push origin p1-session6-complete
```

Update `todo.md`:
- Mark Session 6 complete across three PRs (6A, 6B, 6C).
- Tee up **P1 Session 7 — Tests, manual smoke matrix, runbook docs, P1 exit gate** (P1 Checklist §10, §11, §12).

---

## Notes & Gotchas

1. **Three PRs in strict order.** 6A's `OrderResponse` type is imported by 6B's API client. Don't try to merge in parallel.

2. **`OrderResponse.symbol` joins on the symbols table.** The serializer in `_order_to_response` does an extra `session.get(Symbol, ...)` per order, which is fine for the P1 scale (≤200 orders per page). If listing ever gets slow, switch to a single `selectinload` of the symbol relationship.

3. **Quote endpoint is best-effort, not guaranteed.** Alpaca's free IEX feed can return nothing for some symbols outside core market hours. The ticket's notional check passes `last_price=None` and the Risk Engine returns `NO_QUOTE` — which is a legitimate reason to reject an oversized market order without a quote. If you want to permit market orders without a quote, weaken the notional check (the design philosophy is to reject in ambiguity).

4. **`PATCH /orders/{id}` requires Alpaca's replace support.** Replace works for limit/stop orders that haven't filled yet; it rejects fills-in-flight. If you see `409 conflict`, the order is probably partially filled.

5. **WS topic naming.** I picked `orders`, `fills`, `positions`, `system` because they're stable and the frontend can subscribe once at app start. The bus topics from Session 5 (`order.submitted`, `order.transition`, etc.) are translated through the `bus_to_ws_map` in the gateway. Don't change the WS topics without bumping a version — they're a contract.

6. **Live-mode modal is by design annoying.** Per Implementation Plan §11.2 / P1 Checklist §9.2: two checkboxes + typing the symbol, every single time, no "remember" option. If a future PR adds a "skip for next 5 minutes" affordance — reject it.

7. **TradingView widget is the free embed**, not the Charting Library. No customization beyond what TV exposes in the widget config. P4 polish may consider the licensed Charting Library if customization needs grow.

8. **Symbol map is hard-coded for the seed set.** When the user types in a symbol not in `SYMBOL_MAP`, the widget tries to auto-resolve via TV's own search. Works for most large-cap US equities. Add new entries to `SYMBOL_MAP` as they come up; track gaps in `docs/runbook/symbol-mapping-gaps.md`.

9. **Polling at 5s instead of using WS.** The Orders / Positions / Dashboard pages poll `/api/v1/...` every 5 seconds rather than subscribing to the WS. This is intentional for P1: simpler, easier to reason about, and the WS plumbing is there for P2+ pages that genuinely need sub-second freshness. Don't "optimize" to WS in P1.

10. **`@/...` import aliases.** Vite resolves these from `tsconfig.json`'s `paths`. If you don't already have it from P0, add `"paths": { "@/*": ["src/*"] }` to `compilerOptions` and a matching `resolve.alias` in `vite.config.ts`.

11. **The placeholder Opportunities page** is just the ticket plus a one-line note. Per Implementation Plan v0.2 §17, the rich discovery / indicators / curated-lists Opportunities page is **P4 work**, not P1. Don't quietly build it in P1.

12. **Don't start Session 7 mid-session.** This was six to eight hours; Session 7 (tests + smoke matrix + runbook + exit gate) is a focused two-to-three-hour block of its own. Stop at the tag.

---

*End of P1 Session 6 v0.1.*
