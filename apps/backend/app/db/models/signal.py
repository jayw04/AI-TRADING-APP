"""Signal — a timestamped, symbol-scoped event from a strategy or external source.

For Python strategies in P2, signals are written by
``StrategyContext.log_signal``. The signal payload is whatever JSON the
strategy wants to attach. Signals are denormalized for fast reads (no joins
to fetch the symbol ticker; the ``signals(symbol_id, received_at)`` index
keeps "latest signals for symbol X" cheap).

Distinct from orders: a strategy may emit an entry signal and then submit
an order, or emit an info signal and not order anything. The two are linked
through the ``audit_log``, not at schema level.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, DateTime, ForeignKey, Index
from sqlalchemy import Enum as SQLEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.db.enums import SignalType


class Signal(Base):
    __tablename__ = "signals"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )

    # Nullable strategy_id is intentional: PINE_ALERT signals (P4) arrive
    # before being mapped to a strategy, and AGENT_ACTION signals (P6) may
    # also be detached.
    strategy_id: Mapped[int | None] = mapped_column(
        ForeignKey("strategies.id", ondelete="SET NULL"), nullable=True
    )
    symbol_id: Mapped[int] = mapped_column(
        ForeignKey("symbols.id", ondelete="RESTRICT"), nullable=False
    )

    type: Mapped[SignalType] = mapped_column(
        SQLEnum(SignalType, native_enum=False, length=24),
        nullable=False,
    )

    payload_json: Mapped[dict[str, Any]] = mapped_column(
        JSON, nullable=False, default=dict
    )

    # When the signal was produced. ``processed_at`` is set when an order
    # was submitted (or the engine explicitly decided not to act).
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    processed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    strategy = relationship("Strategy")

    __table_args__ = (
        Index("ix_signals_strategy_received", "strategy_id", "received_at"),
        Index("ix_signals_symbol_received", "symbol_id", "received_at"),
    )

    def __repr__(self) -> str:  # pragma: no cover
        return (
            f"<Signal id={self.id} type={self.type.value} "
            f"symbol_id={self.symbol_id}>"
        )
