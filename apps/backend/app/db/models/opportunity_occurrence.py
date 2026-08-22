"""Durable Opportunity History occurrence (watchlist design v0.7 §7.2).

Identity is (screen_id, screen_version, candidate_date, family, symbol).
snapshot_sha256 / snapshot_generated_at are first-write provenance, not keys.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Float, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class OpportunityOccurrence(Base):
    __tablename__ = "opportunity_occurrence"
    __table_args__ = (
        UniqueConstraint(
            "screen_id",
            "screen_version",
            "candidate_date",
            "family",
            "symbol",
            name="uq_opportunity_occurrence_identity",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    symbol: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    candidate_date: Mapped[str] = mapped_column(String(10), nullable=False, index=True)
    family: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    horizon: Mapped[str] = mapped_column(String(32), nullable=False)
    status_at_proposal: Mapped[str] = mapped_column(String(128), nullable=False)
    proposal_price: Mapped[float] = mapped_column(Float, nullable=False)
    proposal_price_source: Mapped[str] = mapped_column(String(64), nullable=False)
    adjustment_basis: Mapped[str] = mapped_column(String(64), nullable=False)
    screen_id: Mapped[str] = mapped_column(String(64), nullable=False)
    screen_version: Mapped[str] = mapped_column(String(32), nullable=False)
    snapshot_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    snapshot_generated_at: Mapped[str] = mapped_column(String(64), nullable=False)
    reason_json: Mapped[str] = mapped_column(Text, nullable=False)
    features_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
