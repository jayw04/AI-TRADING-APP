"""MorningBrief — the scheduled per-user session brief (P5.5 §2).

One row per (user_id, brief_date); re-runs UPSERT the row (latest-only view).
The full generation history is in the audit log (MORNING_BRIEF_GENERATED).

Stores the structured per-symbol observations (bias labels, key levels) plus
an optional 1-2 sentence agent narration. The brief is informational — it
submits no orders and takes no action.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class MorningBrief(Base):
    __tablename__ = "morning_briefs"
    __table_args__ = (
        # One brief per user per trading day; re-runs UPSERT this row. Composite
        # → must be a table-level constraint (not column-level).
        UniqueConstraint(
            "user_id", "brief_date", name="uq_morning_briefs_user_id_brief_date"
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # The trading day this brief covers (US/Eastern). One brief per (user, date).
    brief_date: Mapped[date] = mapped_column(Date, nullable=False)

    # Per-symbol observations:
    # [{ "symbol","bias","key_level","watch_for","indicators":{...} }, ...]
    symbols_json: Mapped[list[Any]] = mapped_column(JSON, nullable=False, default=list)

    # Optional agent narration (empty if no Anthropic key / call failed).
    overall_note: Mapped[str] = mapped_column(Text, nullable=False, default="")

    # Did the agent contribute, or is this structured-data-only?
    agent_used: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    # How the brief was triggered: 'scheduled' | 'manual'.
    trigger: Mapped[str] = mapped_column(String(32), nullable=False)

    generated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
