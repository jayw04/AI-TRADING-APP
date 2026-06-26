"""Pydantic models for ``GET /api/v1/range-insight/{symbol}`` (P8 §5)."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class MoveStatsModel(BaseModel):
    mean: float
    median: float
    p80: float


class BandModel(BaseModel):
    low: float
    high: float


class RangeCandidateModel(BaseModel):
    """One ranked range-trading candidate (P8 §5a)."""

    symbol: str
    status: str
    atr20: float | None
    atr20_pct: float | None
    intraday_range: float | None
    classification: str | None
    last_close: float | None
    efficiency_ratio: float | None
    oscillation: float | None
    suitable: bool
    score: float
    rank: int


class RangeCandidatesResponse(BaseModel):
    """Ranked range-trading candidates over a universe (daily 'what to range-trade' feed)."""

    as_of: datetime
    candidates: list[RangeCandidateModel]


class RangeInsightResponse(BaseModel):
    symbol: str
    status: str  # "ok" | "insufficient_data"
    bars_used: int
    low_confidence: bool
    as_of: datetime | None
    anchor: float | None
    anchor_source: str | None
    last_close: float | None
    atr20: float | None
    atr20_pct: float | None
    typical_move_up: MoveStatsModel | None
    typical_move_down: MoveStatsModel | None
    support: float | None
    resistance: float | None
    high_band: BandModel | None
    low_band: BandModel | None
    intraday_range: float | None
    classification: str | None
    efficiency_ratio: float | None
    disclaimer: str
