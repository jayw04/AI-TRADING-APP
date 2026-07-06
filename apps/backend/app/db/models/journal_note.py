"""JournalNote — a free-text trade-journal note attached to one order.

The Journal page shows the user's trades (derived from filled orders) and lets
them annotate each with rationale / reflection — the discipline the platform is
built around. One note per order (``order_id`` unique), owned by the order's
user. A note is a personal annotation, not a consequential trading action, so it
is deliberately NOT audit-logged.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class JournalNote(Base):
    __tablename__ = "journal_notes"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # One note per order. ON DELETE CASCADE so a purged order takes its note with it.
    order_id: Mapped[int] = mapped_column(
        ForeignKey("orders.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    note: Mapped[str] = mapped_column(Text, nullable=False, default="")

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
