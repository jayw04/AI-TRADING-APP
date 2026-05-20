import enum
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class AccountMode(str, enum.Enum):
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
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
