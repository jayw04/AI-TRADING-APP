"""AgentToolInvocation — flat queryable record of every tool call.

Deliberately redundant with the ``tool_use`` / ``tool_result`` content
blocks in ``agent_messages.content_json``: the redundancy buys a clean
SQL surface ("how many times did the agent call ``list_positions``
today?") without JSON-walking message blobs.

Updated AFTER the tool runs. ``output_json`` holds the result (or NULL
if the tool errored); ``error_text`` holds the failure message (or
NULL on success). ``latency_ms`` is wall-clock time including any DB
queries the tool made.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, DateTime, ForeignKey, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class AgentToolInvocation(Base):
    __tablename__ = "agent_tool_invocations"

    id: Mapped[int] = mapped_column(primary_key=True)
    session_id: Mapped[int] = mapped_column(
        ForeignKey("agent_sessions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # The TOOL_USE message that originated this invocation.
    message_id: Mapped[int] = mapped_column(
        ForeignKey("agent_messages.id", ondelete="CASCADE"),
        nullable=False,
    )

    tool_name: Mapped[str] = mapped_column(String(128), nullable=False)
    input_json: Mapped[dict[str, Any]] = mapped_column(
        JSON, nullable=False, default=dict
    )
    output_json: Mapped[dict[str, Any] | list[Any] | None] = mapped_column(
        JSON, nullable=True
    )
    error_text: Mapped[str | None] = mapped_column(String(2048), nullable=True)

    latency_ms: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        Index("ix_agent_tool_invocations_session_ts", "session_id", "ts"),
        Index("ix_agent_tool_invocations_tool_ts", "tool_name", "ts"),
    )

    def __repr__(self) -> str:  # pragma: no cover
        return (
            f"<AgentToolInvocation id={self.id} tool={self.tool_name} "
            f"session_id={self.session_id}>"
        )
