"""Pydantic models for the Discovery scanner endpoints (P8 §2)."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class UniverseSpec(BaseModel):
    kind: str  # discovery_feeds | watchlist | symbols
    symbols: list[str] | None = None  # required for kind="symbols"


class ScannerDefinitionCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    criteria: str = Field(min_length=1)
    universe: UniverseSpec
    timeframe: str = "1Day"


class ScannerDefinitionResponse(BaseModel):
    id: int
    name: str
    criteria: str
    universe_kind: str
    universe_symbols: list[str] | None
    timeframe: str
    created_at: datetime
    updated_at: datetime


class ScannerVocabulary(BaseModel):
    indicators: list[str]  # supported bare indicator names (drift-proof)
    fields: list[str]  # bar fields (open/high/low/close/volume/price)


class ScannerMatchItem(BaseModel):
    symbol: str
    values: dict[str, float]


class ScannerSkipItem(BaseModel):
    symbol: str
    reason: str


class ScannerRunSummary(BaseModel):
    id: int
    scanner_definition_id: int
    run_at: datetime
    status: str
    universe_size: int
    evaluated_count: int
    matched_count: int
    skipped_count: int
    error: str | None


class ScannerRunResponse(ScannerRunSummary):
    criteria_snapshot: str
    universe_kind: str
    timeframe: str
    matched: list[ScannerMatchItem]
    skipped: list[ScannerSkipItem]
