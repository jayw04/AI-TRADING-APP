"""AgentSession — one conversational thread between the trader and the agent.

A session is bounded:
  * started when the user opens a new chat (or programmatically via API);
  * ended when the user clicks End, when a new session supersedes, when
    the daily cost cap fires, or when an unrecoverable error fires.

The cost columns (``total_input_tokens`` / ``total_output_tokens`` /
``total_cost_usd``) are running totals for THIS session, updated after
every Anthropic API call. ``daily_budget_usd`` is stamped at session
start so a mid-day config change doesn't retroactively shrink an
in-flight session.

Multiple sessions per user are allowed historically; only one is
ACTIVE at a time (enforced in the P3 Session 3 runtime, not the schema).
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, ForeignKey, Integer, Numeric, String
from sqlalchemy import Enum as SQLEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.db.enums import AgentSessionMode, AgentSessionStatus


class AgentSession(Base):
    __tablename__ = "agent_sessions"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )

    mode: Mapped[AgentSessionMode] = mapped_column(
        SQLEnum(AgentSessionMode, native_enum=False, length=24),
        nullable=False,
        default=AgentSessionMode.B2_INTERACTIVE,
    )
    status: Mapped[AgentSessionStatus] = mapped_column(
        SQLEnum(AgentSessionStatus, native_enum=False, length=16),
        nullable=False,
        default=AgentSessionStatus.ACTIVE,
    )

    # Default model for this session. Individual messages may report a
    # different model id (e.g. user-requested switch mid-conversation);
    # see ``AgentMessage.model``.
    model: Mapped[str] = mapped_column(String(64), nullable=False)

    # Running totals, updated after every API call.
    total_input_tokens: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0
    )
    total_output_tokens: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0
    )
    # NUMERIC(10,4) — cents to four decimal places. $9999.9999 max.
    total_cost_usd: Mapped[Decimal] = mapped_column(
        Numeric(10, 4), nullable=False, default=Decimal("0")
    )

    # Stamped at start; immune to mid-day config changes.
    daily_budget_usd: Mapped[Decimal] = mapped_column(
        Numeric(10, 4), nullable=False
    )

    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    ended_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Populated when status=ENDED with a reason ("user_end", "superseded");
    # when status=ERROR with the error text. Truncated at 2048 chars.
    end_reason: Mapped[str | None] = mapped_column(String(2048), nullable=True)

    messages = relationship(
        "AgentMessage",
        back_populates="session",
        cascade="all, delete-orphan",
        order_by="AgentMessage.ts",
    )
    tool_invocations = relationship(
        "AgentToolInvocation",
        cascade="all, delete-orphan",
        order_by="AgentToolInvocation.ts",
    )

    def __repr__(self) -> str:  # pragma: no cover
        return (
            f"<AgentSession id={self.id} user_id={self.user_id} "
            f"mode={self.mode.value} status={self.status.value} "
            f"cost=${self.total_cost_usd}>"
        )
