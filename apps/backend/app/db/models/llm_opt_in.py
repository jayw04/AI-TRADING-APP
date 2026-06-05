"""LLMOptIn model (P6b §5, ADR 0006 v2 §5).

A user's opt-in to LLM-driven LIVE trading for ONE strategy at ONE version. The
row IS the ``LLM_OPT_IN_ALLOWED`` runtime bypass the ADR describes: while a row
is ``active`` (and its ``strategy_version`` still matches the live strategy's
version), that strategy's live orders route through the LLM act/skip gate.

Lifecycle: ``pending`` (7-day cooldown running; live still deterministic) →
``active`` (cooldown elapsed; live orders are LLM-gated) → ``opted_out``
(terminal; frictionless exit). Version-pinned: a parameter tweak bumps
``strategies.version``, which silently invalidates the opt-in (ADR §66/§78).
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

# Lifecycle states (small closed set, stored as plain strings).
OPT_IN_PENDING = "pending"
OPT_IN_ACTIVE = "active"
OPT_IN_OPTED_OUT = "opted_out"


class LLMOptIn(Base):
    __tablename__ = "llm_opt_in"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    strategy_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("strategies.id", ondelete="CASCADE"), nullable=False
    )
    # Pin: the opt-in applies only while strategies.version still equals this.
    strategy_version: Mapped[str] = mapped_column(String(32), nullable=False)
    state: Mapped[str] = mapped_column(String(16), nullable=False)
    # The typed risk-acknowledgment phrase, recorded for the audit trail.
    acknowledgment_text: Mapped[str] = mapped_column(Text, nullable=False)
    # Per-user daily LLM cap in cents (default $5/day; user-configurable upward).
    daily_cap_cents: Mapped[int] = mapped_column(Integer, nullable=False, default=500)
    initiated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )  # the 7-day cooldown anchor
    activated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    opted_out_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    opted_out_reason: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )

    __table_args__ = (
        Index("ix_llm_opt_in_strategy_id", "strategy_id"),
        Index("ix_llm_opt_in_user_id", "user_id"),
    )
