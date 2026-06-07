"""ScannerDefinition — a saved Discovery scanner (P8 §2).

A user-authored boolean criterion (over supported indicator names) plus a
universe spec. Evaluated deterministically by app/services/scanner; runs are
recorded as ScannerRun rows. No LLM (P8 Decision 1).
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    JSON,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

# universe_kind values.
UNIVERSE_DISCOVERY_FEEDS = "discovery_feeds"
UNIVERSE_WATCHLIST = "watchlist"
UNIVERSE_SYMBOLS = "symbols"
UNIVERSE_KINDS = frozenset(
    {UNIVERSE_DISCOVERY_FEEDS, UNIVERSE_WATCHLIST, UNIVERSE_SYMBOLS}
)


class ScannerDefinition(Base):
    __tablename__ = "scanner_definitions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    criteria: Mapped[str] = mapped_column(Text, nullable=False)
    universe_kind: Mapped[str] = mapped_column(String(16), nullable=False)
    universe_symbols_json: Mapped[list[str] | None] = mapped_column(
        JSON, nullable=True
    )
    timeframe: Mapped[str] = mapped_column(
        String(8), nullable=False, default="1Day"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )

    __table_args__ = (Index("ix_scanner_definitions_user", "user_id"),)
