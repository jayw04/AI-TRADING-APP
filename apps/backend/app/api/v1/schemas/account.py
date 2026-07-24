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
    # `null` when no day baseline could be established (`day_change_basis == "UNAVAILABLE"`).
    # A missing measurement is reported as missing; it is never rendered as a measured 0.00.
    day_change: Decimal | None
    day_change_pct: Decimal | None
    # "BROKER_LAST_EQUITY" | "PRIOR_SESSION_CLOSE_PROXY" | "UNAVAILABLE"
    # — see app/services/day_change_basis.py. The proxy is a prior-close stand-in, NOT a
    # current-session opening baseline and not equivalent to `risk_session_baselines`.
    day_change_basis: str
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
