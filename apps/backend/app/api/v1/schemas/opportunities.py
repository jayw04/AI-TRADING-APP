"""Pydantic schemas for ``/api/v1/opportunities``.

The endpoint aggregates six widget feeds. Each feed has a max item count
(documented per-field on the fetchers in ``app.api.v1.opportunities``) — the
UI doesn't need pagination here because the page is a glance-and-act
surface, not a deep list.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict

from app.db.enums import (
    OrderSide,
    OrderStatus,
    OrderType,
    RiskDecision,
    SignalType,
    TimeInForce,
)

# ---------- Per-widget item shapes ----------


class OppSignalItem(BaseModel):
    """One row in the Live Signals or Pine Alerts widget."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    strategy_id: int | None
    strategy_name: str | None
    symbol: str
    type: SignalType
    received_at: datetime
    reason: str | None
    side: str | None


class OppStrategyErrorItem(BaseModel):
    """One row in the Strategies in Error widget."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    version: str
    error_text: str
    error_first_seen: datetime | None


class OppOpenOrderItem(BaseModel):
    """One row in the Open Orders Nearing TIF Expiry widget."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    symbol: str
    side: OrderSide
    type: OrderType
    tif: TimeInForce
    qty: Decimal
    limit_price: Decimal | None
    status: OrderStatus
    created_at: datetime
    expiry_reason: str


class OppRiskRejectItem(BaseModel):
    """One row in the Recent Risk Rejections widget."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    order_id: int | None
    symbol: str | None
    decision: RiskDecision
    reason_codes: list[str]
    evaluated_at: datetime


class OppFillItem(BaseModel):
    """One row in the Recent Fills widget."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    order_id: int
    symbol: str
    side: OrderSide
    qty: Decimal
    price: Decimal
    filled_at: datetime
    strategy_id: int | None
    strategy_name: str | None


# ---------- The composite response ----------


class OppLiveSignalsWidget(BaseModel):
    items: list[OppSignalItem]
    count: int
    as_of: datetime


class OppPineAlertsWidget(BaseModel):
    items: list[OppSignalItem]
    count: int
    as_of: datetime


class OppStrategyErrorsWidget(BaseModel):
    items: list[OppStrategyErrorItem]
    count: int
    as_of: datetime


class OppOpenOrdersExpiringWidget(BaseModel):
    items: list[OppOpenOrderItem]
    count: int
    as_of: datetime


class OppRiskRejectionsWidget(BaseModel):
    items: list[OppRiskRejectItem]
    count: int
    as_of: datetime


class OppRecentFillsWidget(BaseModel):
    items: list[OppFillItem]
    count: int
    as_of: datetime


# P8 §4 — matches from the latest pre-market SCHEDULED scan.
class OppDiscoveryMatchItem(BaseModel):
    symbol: str
    scan_name: str
    definition_id: int
    run_id: int
    values: dict[str, float]
    run_at: datetime


class OppDiscoveryMatchesWidget(BaseModel):
    items: list[OppDiscoveryMatchItem]
    count: int
    as_of: datetime


class OpportunitiesResponse(BaseModel):
    live_signals: OppLiveSignalsWidget
    pine_alerts: OppPineAlertsWidget
    discovery_matches: OppDiscoveryMatchesWidget
    strategy_errors: OppStrategyErrorsWidget
    open_orders_expiring: OppOpenOrdersExpiringWidget
    risk_rejections: OppRiskRejectionsWidget
    recent_fills: OppRecentFillsWidget
    as_of: datetime
