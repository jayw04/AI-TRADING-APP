"""Pydantic models for ``/api/v1/discovery/feeds`` (P8 §1)."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class DiscoveryActiveStock(BaseModel):
    symbol: str
    volume: float
    trade_count: float


class DiscoveryMover(BaseModel):
    symbol: str
    percent_change: float
    change: float
    price: float


class DiscoveryFeedsResponse(BaseModel):
    most_actives: list[DiscoveryActiveStock]
    gainers: list[DiscoveryMover]
    losers: list[DiscoveryMover]
    last_updated: datetime | None
    stale: bool  # served from cache past TTL because the live fetch failed
    error: str | None
