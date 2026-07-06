"""Schemas for the Trade Journal (GET /journal, PUT /journal/{order_id}/note)."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field


class JournalEntry(BaseModel):
    """One executed trade, with its editable note. Derived from a filled order."""

    order_id: int
    symbol: str
    side: str
    qty: Decimal
    avg_fill_price: Decimal | None
    value: Decimal | None  # abs notional = Σ(fill qty × price)
    source_type: str
    source_id: str | None
    source_label: str  # human label: strategy name, "Manual", "Agent", …
    filled_at: datetime | None
    note: str


class JournalListResponse(BaseModel):
    items: list[JournalEntry]
    count: int


class NoteUpdateRequest(BaseModel):
    note: str = Field(default="", max_length=4000)


class NoteResponse(BaseModel):
    order_id: int
    note: str
