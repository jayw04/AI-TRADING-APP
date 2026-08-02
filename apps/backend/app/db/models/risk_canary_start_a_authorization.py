"""ADR-0043 canary — durable Start A authorization records (Model A).

Capture and consumers load these by ID; callers cannot mint EFFECTIVE by constructing a dataclass.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, ForeignKey, Numeric, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

START_A_STATUS_EFFECTIVE = "EFFECTIVE"
START_A_STATUS_REVOKED = "REVOKED"
START_A_STATUS_DRAFT = "DRAFT"


class RiskCanaryStartAAuthorization(Base):
    """Sealed Start A authorization — sole authority for Model A capture and binding."""

    __tablename__ = "risk_canary_start_a_authorizations"
    __table_args__ = (
        UniqueConstraint("start_a_id", name="uq_risk_canary_start_a_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    start_a_id: Mapped[str] = mapped_column(String(128), nullable=False)
    freeze_id: Mapped[str] = mapped_column(String(128), nullable=False)
    freeze_body_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    broker_account_id: Mapped[str] = mapped_column(String(64), nullable=False)
    workbench_account_id: Mapped[int] = mapped_column(
        ForeignKey("accounts.id", ondelete="CASCADE"), nullable=False
    )
    configuration_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    image_digest: Mapped[str] = mapped_column(String(128), nullable=False)
    commit_sha: Mapped[str] = mapped_column(String(64), nullable=False)
    authorized_session_date: Mapped[str] = mapped_column(String(10), nullable=False)
    design_version: Mapped[str] = mapped_column(String(128), nullable=False)
    applicable_daily_loss_limit: Mapped[Decimal] = mapped_column(Numeric(20, 4), nullable=False)
    authorization_status: Mapped[str] = mapped_column(String(32), nullable=False)
    # SHA-256 of the canonical sealed authorization body (excludes id/row pk).
    authorization_body_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_by: Mapped[str] = mapped_column(String(64), nullable=False, default="SYSTEM")
