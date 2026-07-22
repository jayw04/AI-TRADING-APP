"""ADR 0042 § D — exposure reservations.

Two concurrent sells of 300 against a long of 500 each pass the zero-crossing check in
isolation (``500 - 300 >= 0``) and **together create a 100-share short**. No single-order check
can see that. Only *reducible capacity* can — and capacity is only real if an approval
CONSUMES it.

So an approved reduction **reserves** the quantity it was approved for, and
``available_reducible_quantity`` nets reservations out.

This table is deliberately SEPARATE from ``risk_decisions``. The ledger is append-only — a
decision is a historical fact and is never mutated. A reservation has a *lifecycle* (held →
consumed, or held → released), and mixing a mutable lifecycle into an immutable ledger would
quietly destroy the ledger's central property.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, ForeignKey, Index, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

RESERVATION_HELD = "HELD"          # approved, not yet submitted/filled — consumes capacity
RESERVATION_CONSUMED = "CONSUMED"  # the order reached a terminal filled state
RESERVATION_RELEASED = "RELEASED"  # rolled back (version conflict, reject, cancel)


class RiskReservation(Base):
    """A quantity of reducible exposure promised to one approved decision."""

    __tablename__ = "risk_reservations"
    __table_args__ = (
        Index("ix_risk_reservations_open", "account_id", "symbol", "state"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    account_id: Mapped[int] = mapped_column(
        ForeignKey("accounts.id", ondelete="CASCADE"), nullable=False
    )
    symbol: Mapped[str] = mapped_column(String(20), nullable=False)
    qty: Mapped[Decimal] = mapped_column(Numeric(20, 8), nullable=False)

    decision_id: Mapped[int | None] = mapped_column(
        ForeignKey("risk_decisions.id", ondelete="SET NULL"), nullable=True
    )
    order_id: Mapped[int | None] = mapped_column(
        ForeignKey("orders.id", ondelete="SET NULL"), nullable=True
    )

    # The broker long for this symbol AT THE MOMENT this reservation was created — the anchor
    # that lets a later decision PROVE the position has absorbed a fill, rather than assume it.
    # Broker positions, broker orders and local fills are three non-atomic reads: a locally
    # observed fill may not yet appear in the positions endpoint. Crediting such a fill back
    # would manufacture reducible capacity and could admit a sell that crosses zero. NULL on
    # rows written before this column existed — absorption is then unprovable and credited ZERO.
    position_qty_at_reservation: Mapped[Decimal | None] = mapped_column(
        Numeric(20, 8), nullable=True
    )

    state: Mapped[str] = mapped_column(String(12), nullable=False, default=RESERVATION_HELD)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    released_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    release_reason: Mapped[str | None] = mapped_column(String(64), nullable=True)
