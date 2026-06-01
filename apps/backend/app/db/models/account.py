from datetime import datetime
from enum import StrEnum

from sqlalchemy import DateTime, Enum, ForeignKey, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class AccountMode(StrEnum):
    paper = "paper"
    live = "live"


class Account(Base):
    __tablename__ = "accounts"
    __table_args__ = (
        UniqueConstraint("user_id", "broker", "mode", name="uq_accounts_user_broker_mode"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    broker: Mapped[str] = mapped_column(String(50), nullable=False)
    mode: Mapped[AccountMode] = mapped_column(
        Enum(AccountMode, name="account_mode"), nullable=False
    )
    credentials_ref: Mapped[str | None] = mapped_column(String(255), nullable=True)
    label: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # Records when this account was activated to LIVE (P5 §1). Set once by the
    # activation wizard (P5 §7); never read in P5 §1. Storage is declared now so
    # the wizard ships without a migration — same pattern as pending_reload_at.
    broker_mode_locked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    # Circuit breaker state (P5 §5). NULL means "not currently tripped." When
    # tripped, the timestamp records when. Full history is in audit_log
    # (CIRCUIT_BREAKER_TRIPPED / CIRCUIT_BREAKER_RESET actions).
    circuit_breaker_tripped_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
