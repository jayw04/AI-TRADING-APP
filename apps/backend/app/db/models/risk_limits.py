"""RiskLimits — the configurable envelope used by the Risk Engine.

Each row is scoped (GLOBAL, ACCOUNT, STRATEGY, AGENT_SESSION). The Risk Engine
resolves the most specific applicable row at evaluate-time. For P1 we only
need GLOBAL — Session 5's engine starts there and adds the other scopes later.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Integer, Numeric
from sqlalchemy import Enum as SQLEnum
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.enums import RiskScopeType
from app.db.models.account import AccountMode


class RiskLimits(Base):
    __tablename__ = "risk_limits"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )

    scope_type: Mapped[RiskScopeType] = mapped_column(
        SQLEnum(RiskScopeType, native_enum=False, length=32), nullable=False
    )
    # Scopes a limits row to PAPER or LIVE (P5 §1). The engine filters on this
    # so a live trade only matches live-scoped limits, a paper trade only
    # paper-scoped. Existing rows backfill to 'paper' via server_default;
    # live-scoped rows are created when P5 §5/§7 ship.
    broker_mode: Mapped[AccountMode] = mapped_column(
        SQLEnum(AccountMode, native_enum=False, length=16),
        nullable=False,
        default=AccountMode.paper,
        server_default="paper",
        index=True,
    )
    # scope_id is INTEGER (not FK) because the referenced tables may not
    # exist yet (strategies in P2, agent_sessions in P3). NULL when GLOBAL.
    scope_id: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # All caps nullable so a row can leave a particular cap unset; the engine
    # then falls back to a more general scope's value.
    max_position_qty: Mapped[Decimal | None] = mapped_column(Numeric(20, 8), nullable=True)
    max_position_notional: Mapped[Decimal | None] = mapped_column(Numeric(20, 4), nullable=True)
    max_gross_exposure: Mapped[Decimal | None] = mapped_column(Numeric(20, 4), nullable=True)
    max_daily_loss: Mapped[Decimal | None] = mapped_column(Numeric(20, 4), nullable=True)
    max_orders_per_minute: Mapped[int | None] = mapped_column(Integer, nullable=True)

    allow_short: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    allowed_symbols: Mapped[list | None] = mapped_column(JSON, nullable=True)
    denied_symbols: Mapped[list | None] = mapped_column(JSON, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
