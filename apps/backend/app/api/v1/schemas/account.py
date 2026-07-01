"""Pydantic models for ``/api/v1/account``."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict


class AccountResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    account_id: int
    mode: str  # "paper" | "live"
    status: str  # "ACTIVE" | ...
    cash: Decimal
    equity: Decimal
    last_equity: Decimal
    buying_power: Decimal
    portfolio_value: Decimal
    day_change: Decimal
    day_change_pct: Decimal
    # Inception-to-date figures (THIS account only, never aggregated across users).
    # starting_equity = earliest recorded equity snapshot (fallback: current equity → 0%).
    starting_equity: Decimal
    total_return: Decimal  # equity - starting_equity
    total_return_pct: Decimal  # fraction, same convention as day_change_pct
    daytrade_count: int
    pattern_day_trader: bool
    trading_blocked: bool
    account_blocked: bool
    updated_at: datetime
