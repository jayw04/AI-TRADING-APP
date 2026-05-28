"""AgentMessage — one message in an agent session.

``content_json`` mirrors Anthropic's API content-block format::

    [
      {"type": "text", "text": "..."},
      {"type": "tool_use", "id": "...", "name": "list_positions", "input": {...}},
      {"type": "tool_result", "tool_use_id": "...", "content": "..."},
    ]

Storing in this exact shape lets the Session 3 runtime read messages
back and feed them straight into the next Anthropic call without
re-shaping.

``parent_message_id`` threads tool_use → tool_result pairs: a
``tool_result`` message's parent is the ``tool_use`` message it answers.
Other messages have NULL parent. The self-FK uses ``SET NULL`` so a
defensive delete of a tool_use leaves the tool_result intact (catches
inconsistencies rather than silently cascading).

``input_tokens`` / ``output_tokens`` / ``model`` are populated for
assistant messages (the model that generated them). Tool messages
leave them NULL.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, Index, Integer, String
from sqlalchemy import Enum as SQLEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.db.enums import AgentMessageRole


class AgentMessage(Base):
    __tablename__ = "agent_messages"

    id: Mapped[int] = mapped_column(primary_key=True)
    session_id: Mapped[int] = mapped_column(
        ForeignKey("agent_sessions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    role: Mapped[AgentMessageRole] = mapped_column(
        SQLEnum(AgentMessageRole, native_enum=False, length=24),
        nullable=False,
    )

    # Always a list of content blocks; never a bare string. Even a USER
    # message with one text chunk is stored as
    # ``[{"type":"text","text":"..."}]``.
    content_json: Mapped[list] = mapped_column(JSON, nullable=False, default=list)

    # Usage stats — populated for assistant messages from the API response.
    input_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    output_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    model: Mapped[str | None] = mapped_column(String(64), nullable=True)

    ts: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
    parent_message_id: Mapped[int | None] = mapped_column(
        ForeignKey("agent_messages.id", ondelete="SET NULL"), nullable=True
    )

    session = relationship("AgentSession", back_populates="messages")

    __table_args__ = (
        Index("ix_agent_messages_session_ts", "session_id", "ts"),
    )

    def __repr__(self) -> str:  # pragma: no cover
        return (
            f"<AgentMessage id={self.id} session_id={self.session_id} "
            f"role={self.role.value}>"
        )
