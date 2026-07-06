"""Schemas for GET /range-levels — live range buy/sell/stop monitoring."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class RangeLevelRow(BaseModel):
    symbol: str
    buy: float | None      # entry / support (strategy's actual level)
    sell: float | None     # exit / resistance
    stop: float | None
    current_price: float | None
    position_qty: float
    # forming | levels_set | in_range | at_buy | at_sell | below_stop | holding
    status: str
    levels_at: datetime | None  # when the strategy last published these levels


class RangeLevelsResponse(BaseModel):
    strategy_id: int | None
    strategy_name: str | None
    as_of: datetime
    rows: list[RangeLevelRow]
