"""Schemas for GET /api/v1/range-execution — Range Trader buy/sell vs. daily high/low."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from pydantic import BaseModel


class RangeExecutionRecordOut(BaseModel):
    """One (symbol, ET day): our avg BUY/SELL fill (null when not traded) + the day's low/high."""

    et_date: date
    symbol: str
    avg_buy_price: Decimal | None
    avg_sell_price: Decimal | None
    daily_low: Decimal | None
    daily_high: Decimal | None


class RangeExecutionListResponse(BaseModel):
    items: list[RangeExecutionRecordOut]
    count: int
