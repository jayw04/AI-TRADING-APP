"""Pydantic models for ``/api/v1/positions``."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict


class PositionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    symbol: str
    qty: Decimal
    avg_entry_price: Decimal
    side: str | None  # "long" | "short" | None
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
    """Body for POST /api/v1/positions/{symbol}/close.

    Empty for now; future options (close as limit, partial close) can be added
    without breaking callers."""

    model_config = ConfigDict(extra="forbid")
