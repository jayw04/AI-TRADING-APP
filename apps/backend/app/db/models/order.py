"""Order — the canonical record of an order from intent through terminal state.

Every order, regardless of source (manual / strategy / pine / agent_strategy /
agent_proposal), produces exactly one row here. The OrderRouter (Session 5)
is the only writer.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Numeric, String
from sqlalchemy import Enum as SQLEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.db.enums import OrderSide, OrderSourceType, OrderStatus, OrderType, TimeInForce

if TYPE_CHECKING:
    from app.db.models.fill import Fill


class Order(Base):
    __tablename__ = "orders"
    __table_args__ = (
        # Composite indices for common query paths from P1 Checklist §2.3:
        # "orders by user, filtered by status, sorted by time"
        # "orders by symbol, sorted by time"
        Index("ix_orders_user_status_created", "user_id", "status", "created_at"),
        Index("ix_orders_symbol_created", "symbol_id", "created_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)

    # Ownership / scoping
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    account_id: Mapped[int] = mapped_column(
        ForeignKey("accounts.id", ondelete="CASCADE"), nullable=False
    )
    symbol_id: Mapped[int] = mapped_column(
        ForeignKey("symbols.id", ondelete="RESTRICT"), nullable=False
    )

    # Broker linkage. broker_order_id is NULL until Alpaca acks (i.e. while
    # status is PENDING_RISK / PENDING_SUBMIT). client_order_id is our own
    # idempotency token sent to Alpaca.
    broker_order_id: Mapped[str | None] = mapped_column(String(64), nullable=True, unique=True)
    client_order_id: Mapped[str | None] = mapped_column(String(64), nullable=True)

    # Intent
    side: Mapped[OrderSide] = mapped_column(
        SQLEnum(OrderSide, native_enum=False, length=8), nullable=False
    )
    qty: Mapped[Decimal] = mapped_column(Numeric(20, 8), nullable=False)
    type: Mapped[OrderType] = mapped_column(
        SQLEnum(OrderType, native_enum=False, length=16), nullable=False
    )
    limit_price: Mapped[Decimal | None] = mapped_column(Numeric(20, 4), nullable=True)
    stop_price: Mapped[Decimal | None] = mapped_column(Numeric(20, 4), nullable=True)
    tif: Mapped[TimeInForce] = mapped_column(
        SQLEnum(TimeInForce, native_enum=False, length=8),
        nullable=False,
        default=TimeInForce.DAY,
    )
    extended_hours: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    # Lifecycle
    status: Mapped[OrderStatus] = mapped_column(
        SQLEnum(OrderStatus, native_enum=False, length=24),
        nullable=False,
        default=OrderStatus.PENDING_RISK,
    )
    rejection_reason: Mapped[str | None] = mapped_column(String(512), nullable=True)

    # Provenance
    source_type: Mapped[OrderSourceType] = mapped_column(
        SQLEnum(OrderSourceType, native_enum=False, length=24), nullable=False
    )
    source_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    parent_order_id: Mapped[int | None] = mapped_column(
        ForeignKey("orders.id", ondelete="SET NULL"), nullable=True
    )

    # Risk linkage. Nullable on both sides of the circular reference.
    risk_check_id: Mapped[int | None] = mapped_column(
        ForeignKey("risk_checks.id", ondelete="SET NULL"), nullable=True
    )

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    submitted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    terminal_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    # Relationships
    fills: Mapped[list[Fill]] = relationship(
        back_populates="order",
        cascade="all, delete-orphan",
        lazy="selectin",
    )
    risk_check = relationship("RiskCheck", foreign_keys=[risk_check_id])
    parent_order = relationship("Order", remote_side="Order.id", uselist=False)
