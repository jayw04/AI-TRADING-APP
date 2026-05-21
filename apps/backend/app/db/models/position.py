"""Position — the open position cache per (account, symbol).

Updated by PositionSyncService on each poll. The Position Recomputer
(Session 5) also writes here on every fill so the UI sees changes
immediately rather than waiting for the next poll.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, ForeignKey, Numeric, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Position(Base):
    __tablename__ = "positions"
    __table_args__ = (
        UniqueConstraint("account_id", "symbol_id", name="uq_positions_account_symbol"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    account_id: Mapped[int] = mapped_column(
        ForeignKey("accounts.id", ondelete="CASCADE"), nullable=False
    )
    symbol_id: Mapped[int] = mapped_column(
        ForeignKey("symbols.id", ondelete="RESTRICT"), nullable=False
    )

    qty: Mapped[Decimal] = mapped_column(Numeric(20, 8), nullable=False, default=Decimal(0))
    avg_entry_price: Mapped[Decimal] = mapped_column(
        Numeric(20, 4), nullable=False, default=Decimal(0)
    )
    side: Mapped[str | None] = mapped_column(String(8), nullable=True)  # 'long' | 'short'

    # Computed market values; updated from Alpaca's position snapshot.
    market_value: Mapped[Decimal] = mapped_column(
        Numeric(20, 4), nullable=False, default=Decimal(0)
    )
    cost_basis: Mapped[Decimal] = mapped_column(
        Numeric(20, 4), nullable=False, default=Decimal(0)
    )
    unrealized_pl: Mapped[Decimal] = mapped_column(
        Numeric(20, 4), nullable=False, default=Decimal(0)
    )
    unrealized_plpc: Mapped[Decimal] = mapped_column(
        Numeric(10, 6), nullable=False, default=Decimal(0)
    )

    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
