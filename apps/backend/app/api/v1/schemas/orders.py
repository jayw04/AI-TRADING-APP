"""Pydantic models for ``/api/v1/orders``."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Literal

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
    limit_price: Decimal | None = Field(default=None, gt=0)
    stop_price: Decimal | None = Field(default=None, gt=0)
    tif: TimeInForce = TimeInForce.DAY
    extended_hours: bool = False
    client_order_id: str | None = None
    # P5 §6: typed-ticker confirmation for manual LIVE orders. Optional at the
    # schema level (paper orders ignore it); the OrderRouter enforces the
    # "required + must match symbol" rule for MANUAL + LIVE. (Today the orders
    # endpoint only targets the paper account, so this is forward-prep for the
    # §7 wizard that opens LIVE order submission.)
    confirmation_text: str | None = Field(default=None, max_length=32)

    @field_validator("symbol")
    @classmethod
    def _upper(cls, v: str) -> str:
        return v.strip().upper()


class FillResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    broker_fill_id: str | None
    qty: Decimal
    price: Decimal
    commission: Decimal
    filled_at: datetime


class RiskCheckSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    decision: str  # "PASS" | "REJECT" (value of RiskDecision enum)
    reason_codes: list[str]
    evaluated_at: datetime


class OrderResponse(BaseModel):
    """Standard order representation. Used by single + list endpoints."""

    model_config = ConfigDict(from_attributes=True)

    id: int | None  # null for ephemeral rejected orders (e.g., unknown symbol)
    broker_order_id: str | None
    client_order_id: str | None
    symbol: str
    side: OrderSide
    qty: Decimal
    type: OrderType
    limit_price: Decimal | None
    stop_price: Decimal | None
    tif: TimeInForce
    extended_hours: bool
    status: OrderStatus
    rejection_reason: str | None
    source_type: OrderSourceType
    source_id: str | None
    created_at: datetime
    submitted_at: datetime | None
    terminal_at: datetime | None
    updated_at: datetime
    fills: list[FillResponse] = []
    risk_check: RiskCheckSummary | None = None


class OrderListResponse(BaseModel):
    items: list[OrderResponse]
    count: int


class OrderModifyRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    new_qty: Decimal | None = Field(default=None, gt=0)
    new_limit_price: Decimal | None = Field(default=None, gt=0)


class OrderActionResponse(BaseModel):
    """Returned by cancel + modify."""

    order_id: int
    requested_action: Literal["cancel", "modify"]
    accepted_by_broker: bool  # True if broker accepted the *request*; final outcome via WS
