"""ADR-0043 canary Model A — authoritative session-open baseline (separate from shadow).

Shadow rows in ``risk_session_baselines`` are never upgraded into Model A authority.
Authoritative rows originate only via the Start A capture path.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, ForeignKey, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

BASELINE_SOURCE_SESSION_OPEN_BROKER_EQUITY = "SESSION_OPEN_BROKER_EQUITY"
CANARY_BASELINE_STATUS_ACTIVE = "ACTIVE"


class RiskCanarySessionBaseline(Base):
    """One immutable Model A baseline per (account, session, design_version, freeze_id)."""

    __tablename__ = "risk_canary_session_baselines"
    __table_args__ = (
        UniqueConstraint(
            "account_id",
            "market_session_date",
            "design_version",
            "freeze_id",
            name="uq_risk_canary_session_baseline_identity",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    account_id: Mapped[int] = mapped_column(
        ForeignKey("accounts.id", ondelete="CASCADE"), nullable=False
    )
    broker_account_id: Mapped[str] = mapped_column(String(64), nullable=False)
    market_session_date: Mapped[str] = mapped_column(String(10), nullable=False)
    session_timezone: Mapped[str] = mapped_column(
        String(32), nullable=False, default="America/New_York"
    )

    # Exact parsed equity used for control P&L; canonical 4dp string is serialization-only.
    baseline_equity: Mapped[Decimal] = mapped_column(Numeric(28, 12), nullable=False)
    baseline_equity_raw: Mapped[str] = mapped_column(String(64), nullable=False)
    baseline_equity_canonical_4dp: Mapped[str] = mapped_column(String(64), nullable=False)
    baseline_source: Mapped[str] = mapped_column(String(64), nullable=False)

    broker_response_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    local_receipt_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    persisted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    raw_response_json: Mapped[str] = mapped_column(Text, nullable=False)
    raw_response_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    projection_json: Mapped[str] = mapped_column(Text, nullable=False)
    projection_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    raw_object_ref: Mapped[str | None] = mapped_column(String(256), nullable=True)

    design_version: Mapped[str] = mapped_column(String(128), nullable=False)
    freeze_id: Mapped[str] = mapped_column(String(128), nullable=False)
    start_a_id: Mapped[str] = mapped_column(String(128), nullable=False)
    freeze_body_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    configuration_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    image_digest: Mapped[str] = mapped_column(String(128), nullable=False)
    commit_sha: Mapped[str] = mapped_column(String(64), nullable=False)
    applicable_daily_loss_limit: Mapped[Decimal] = mapped_column(Numeric(20, 4), nullable=False)
    capture_mechanism_version: Mapped[str] = mapped_column(String(64), nullable=False)

    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default=CANARY_BASELINE_STATUS_ACTIVE
    )
