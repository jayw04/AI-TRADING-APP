"""MarketProjectionModelRegistry — versioned model artifacts for MKT-PROJ-001 (design §17.4).

One row per trained artifact: version, type, artifact path + sha256, the
feature/label versions it was trained against, its training/validation windows,
and the git commit — the NFR-002 reproducibility record. ``status`` lifecycle:
``candidate`` (trained, evidence attached) → ``production`` (§4, the row
inference loads — that transition will be audit-logged when inference exists)
→ ``retired``. Research data; never read by any order-path module (NFR-001).
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class MarketProjectionModelRegistry(Base):
    __tablename__ = "market_projection_model_registry"
    __table_args__ = (UniqueConstraint("model_version", name="uq_mktproj_model_version"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    model_version: Mapped[str] = mapped_column(String(128), nullable=False)
    model_type: Mapped[str] = mapped_column(String(64), nullable=False)
    projection_type: Mapped[str] = mapped_column(String(32), nullable=False)
    artifact_path: Mapped[str] = mapped_column(String(256), nullable=False)
    artifact_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    feature_version: Mapped[str] = mapped_column(String(32), nullable=False)
    label_version: Mapped[str] = mapped_column(String(32), nullable=False)
    training_window: Mapped[str] = mapped_column(String(64), nullable=False)
    validation_window: Mapped[str] = mapped_column(String(64), nullable=False)
    git_commit: Mapped[str | None] = mapped_column(String(64), nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="candidate")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
