"""MarketProjectionRun — served projections + realized outcomes (design §17.4 + FR-013).

One row per inference attempt (multiple attempts kept; the API serves the
latest SUCCESS per target_date). Full three-class probabilities are stored for
research and outcome grading, but the API layer NEVER emits directional fields
(owner decision 2026-07-10 / §4 Q1). Research surface — no order-path reader
(NFR-001, CI-enforced).
"""

from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import JSON, Boolean, Date, DateTime, Float, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class MarketProjectionRun(Base):
    __tablename__ = "market_projection_runs"
    __table_args__ = (
        UniqueConstraint(
            "projection_type", "market_proxy", "target_date", "attempt_number",
            name="uq_mktproj_run_attempt",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    projection_type: Mapped[str] = mapped_column(String(32), nullable=False)
    market_proxy: Mapped[str] = mapped_column(String(16), nullable=False)
    as_of: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    target_date: Mapped[date] = mapped_column(Date, nullable=False)
    attempt_number: Mapped[int] = mapped_column(nullable=False, default=1)
    model_version: Mapped[str | None] = mapped_column(String(128), nullable=True)
    feature_version: Mapped[str | None] = mapped_column(String(32), nullable=True)
    label_version: Mapped[str | None] = mapped_column(String(32), nullable=True)
    prob_up: Mapped[float | None] = mapped_column(Float, nullable=True)
    prob_down: Mapped[float | None] = mapped_column(Float, nullable=True)
    prob_neutral: Mapped[float | None] = mapped_column(Float, nullable=True)
    prob_material: Mapped[float | None] = mapped_column(Float, nullable=True)
    elevated: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    display_phrase: Mapped[str | None] = mapped_column(String(128), nullable=True)
    confidence: Mapped[str | None] = mapped_column(String(8), nullable=True)
    material_threshold_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    drivers_json: Mapped[list | None] = mapped_column(JSON, nullable=True)
    features_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    source_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    run_status: Mapped[str] = mapped_column(String(16), nullable=False)  # SUCCESS/UNAVAILABLE/FAILED/SKIPPED
    unavailable_reason: Mapped[str | None] = mapped_column(String(128), nullable=True)
    # FR-013 realized-outcome fields (graded by outcomes.py when the label matures)
    outcome_status: Mapped[str] = mapped_column(String(16), nullable=False, default="pending")
    realized_return: Mapped[float | None] = mapped_column(Float, nullable=True)
    realized_label: Mapped[str | None] = mapped_column(String(8), nullable=True)
    correct_magnitude: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    prob_assigned_to_realized_class: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
