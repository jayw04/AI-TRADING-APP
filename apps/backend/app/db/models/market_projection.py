"""MarketProjectionTrainingRow — the MKT-PROJ-001 historical feature/label dataset (FR-001).

One row per session per horizon (PRE_OPEN_TODAY / PRE_CLOSE_TOMORROW). Research
data, not the audit log: purely additive, rebuilt idempotently by the §1 dataset
builder, and NEVER read by any order-path/ranking/sizing module (NFR-001).
Sessions that cannot produce a clean row are stored with
``valid_for_training=False`` + ``exclusion_reason`` rather than silently dropped.
"""

from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import JSON, Boolean, Date, DateTime, Float, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class MarketProjectionTrainingRow(Base):
    __tablename__ = "market_projection_training_rows"
    __table_args__ = (
        UniqueConstraint(
            "date", "projection_type", "market_proxy", "feature_version",
            name="uq_mktproj_training_row",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    date: Mapped[date] = mapped_column(Date, nullable=False)
    projection_type: Mapped[str] = mapped_column(String(32), nullable=False)
    market_proxy: Mapped[str] = mapped_column(String(16), nullable=False)
    features_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    # SCAN/GAPPER shadow features — separate namespace, shadow model only (§8.4);
    # populated by a later forward pass, never by the historical builder.
    shadow_features_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    label: Mapped[str | None] = mapped_column(String(8), nullable=True)
    realized_return: Mapped[float | None] = mapped_column(Float, nullable=True)
    threshold: Mapped[float | None] = mapped_column(Float, nullable=True)
    valid_for_training: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    exclusion_reason: Mapped[str | None] = mapped_column(String(64), nullable=True)
    feature_version: Mapped[str] = mapped_column(String(32), nullable=False)
    label_version: Mapped[str] = mapped_column(String(32), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
