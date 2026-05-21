"""RiskCheck — one row per Risk Engine evaluation.

Every order placement causes exactly one RiskCheck row to be written BEFORE
the order is dispatched to the broker (pass) or rejected (reject). This is
the audit trail for "why did/didn't this order go through".
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, Integer
from sqlalchemy import Enum as SQLEnum
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.enums import RiskDecision


class RiskCheck(Base):
    __tablename__ = "risk_checks"

    id: Mapped[int] = mapped_column(primary_key=True)

    # Linkage. For P1 only order_id is populated. strategy_id and
    # agent_session_id are reserved for P2/P3; bare INTEGERs (no FK) since
    # those tables don't exist yet. A later migration adds the FKs.
    order_id: Mapped[int | None] = mapped_column(
        ForeignKey("orders.id", ondelete="SET NULL"), nullable=True, index=True
    )
    strategy_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    agent_session_id: Mapped[int | None] = mapped_column(Integer, nullable=True)

    decision: Mapped[RiskDecision] = mapped_column(
        SQLEnum(RiskDecision, native_enum=False, length=16), nullable=False
    )
    reason_codes: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    evaluated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
