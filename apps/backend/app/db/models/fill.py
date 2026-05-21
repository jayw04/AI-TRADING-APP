"""Fill — one row per (partial) execution received from the broker.

The Session 5 trade-update consumer writes one Fill per Alpaca 'fill' or
'partial_fill' event. Position recomputation aggregates these.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, ForeignKey, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class Fill(Base):
    __tablename__ = "fills"

    id: Mapped[int] = mapped_column(primary_key=True)
    order_id: Mapped[int] = mapped_column(
        ForeignKey("orders.id", ondelete="CASCADE"), nullable=False, index=True
    )

    # Alpaca's execution_id — unique per fill, used for idempotency on replay.
    broker_fill_id: Mapped[str | None] = mapped_column(String(64), nullable=True)

    qty: Mapped[Decimal] = mapped_column(Numeric(20, 8), nullable=False)
    price: Mapped[Decimal] = mapped_column(Numeric(20, 4), nullable=False)
    commission: Mapped[Decimal] = mapped_column(
        Numeric(20, 4), nullable=False, default=Decimal(0)
    )
    filled_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)

    order = relationship("Order", back_populates="fills")
