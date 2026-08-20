"""Pydantic schemas for ``/api/v1/opportunities``.

The endpoint aggregates six widget feeds. Each feed has a max item count
(documented per-field on the fetchers in ``app.api.v1.opportunities``) — the
UI doesn't need pagination here because the page is a glance-and-act
surface, not a deep list.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

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


# Pre-market gappers — read-only ingest of the external scanner (advisory only).
class OppPremarketGapperItem(BaseModel):
    rank: int
    symbol: str
    price: float | None = None
    gap_pct: float | None = None
    premarket_volume: int | None = None
    catalyst: str | None = None
    headlines: list[str] = Field(default_factory=list)


class OppPremarketGappersWidget(BaseModel):
    items: list[OppPremarketGapperItem]
    count: int
    as_of: datetime
    # Source-file metadata so the UI can show provenance + a stale badge.
    scanned_at: datetime | None = None
    date: str | None = None
    stale: bool = True


class OppWatchlistChip(BaseModel):
    key: str
    value: str


class OppWatchlistItem(BaseModel):
    symbol: str
    family_ids: list[str]
    horizon: str
    status: str
    name: str | None = None
    sector: str | None = None
    chips: list[OppWatchlistChip] = Field(default_factory=list)
    why: str = ""
    tradability: str = "not measured (Phase 1)"
    price_source: str = ""
    close: float | None = None
    market_cap: float | None = None
    adv20: float | None = None


class OppWatchlistFamily(BaseModel):
    family_id: str
    operator_name: str
    horizon: str
    available: bool
    unavailable_reason: str | None = None
    count: int
    items: list[OppWatchlistItem] = Field(default_factory=list)


class OppCandidateWatchlistWidget(BaseModel):
    """DISC-001 Band B — candidates only, never a signal."""

    as_of: datetime
    as_of_session: str | None = None
    universe_id: str
    screen_id: str
    screen_version: str
    subtitle: str = "Watch, not a signal"
    vix: float | None = None
    families: dict[str, OppWatchlistFamily]
    all_items: list[OppWatchlistItem] = Field(default_factory=list)
    all_count: int = 0
    stale: bool = True


class OpportunitiesResponse(BaseModel):
    live_signals: OppLiveSignalsWidget
    pine_alerts: OppPineAlertsWidget
    discovery_matches: OppDiscoveryMatchesWidget
    strategy_errors: OppStrategyErrorsWidget
    open_orders_expiring: OppOpenOrdersExpiringWidget
    risk_rejections: OppRiskRejectionsWidget
    recent_fills: OppRecentFillsWidget
    premarket_gappers: OppPremarketGappersWidget
    candidate_watchlist: OppCandidateWatchlistWidget
    as_of: datetime


class OppHistoryOccurrence(BaseModel):
    """One durable family-row occurrence. Current price is read-time only."""

    symbol: str
    family: str
    candidate_date: str
    horizon: str
    status_at_proposal: str
    proposal_price: float
    proposal_price_source: str
    adjustment_basis: str
    reason: dict[str, object] = Field(default_factory=dict)
    screen_id: str
    screen_version: str
    snapshot_sha256: str
    snapshot_generated_at: str
    first_seen: str
    last_seen: str
    occurrence_count: int = 1
    current_price: float | None = None
    current_price_as_of: str | None = None
    current_price_source: str | None = None
    change_pct: float | None = None


class OppHistoryResponse(BaseModel):
    view: str
    count: int
    items: list[OppHistoryOccurrence]
    as_of: datetime
