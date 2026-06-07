"""StrategyRevision — the authoring conversation history (P7 §5).

One row per turn of an AI-authoring conversation (generation + each P7b
refinement), preserved read-only as metadata of the SAVED strategy (Direction
Decision 3). Persisted at save time (the client holds the conversation during
authoring; Save sends the full history), so only saved strategies have history —
no orphan rows. Separate from the audit log: this is for the trader's reference,
not forensic reconstruction.
"""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    JSON,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

# Turn kinds.
REVISION_GENERATION = "generation"
REVISION_REFINEMENT = "refinement"


class StrategyRevision(Base):
    __tablename__ = "strategy_revisions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    strategy_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("strategies.id", ondelete="CASCADE"), nullable=False
    )
    seq: Mapped[int] = mapped_column(Integer, nullable=False)  # turn order, 0-based
    kind: Mapped[str] = mapped_column(String(16), nullable=False)
    # The user's input for this turn — the initial description, or a P7b change request.
    user_message: Mapped[str] = mapped_column(Text, nullable=False)
    assumptions_json: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    explanation: Mapped[str] = mapped_column(Text, nullable=False, default="")
    code: Mapped[str] = mapped_column(Text, nullable=False)
    # The backtest outcome dict for this turn's code (or null if none).
    backtest_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    cost_usd: Mapped[Decimal | None] = mapped_column(Numeric(20, 4), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )

    __table_args__ = (
        Index("ix_strategy_revisions_strategy_seq", "strategy_id", "seq"),
    )
