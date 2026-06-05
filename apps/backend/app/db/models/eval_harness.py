"""EvalHarness + EvalHarnessDecision models (P6b §4, ADR 0006 v2).

The eval harness runs a strategy in three modes (ADR 0006 v2 §33):
- Mode A (control) — the deterministic strategy on paper. A running clone whose
  ``submit_order_fn`` is wrapped by the harness; it always acts.
- Mode B (LLM-managed) — the same intents, but each gated by an LLM act/skip
  decision. Mode B is NOT a separate running strategy; it is an IDLE "bucket"
  row whose id tags B's orders (so the §1a/§2b round-trip reconstruction can
  rebuild B's equity separately). Mode A's wrapper submits B's orders.
- Mode C (live) — the original live Strategy, untouched.

Per-signal A/B decisions live in ``eval_harness_decisions`` (NOT the audit hash
chain — the per-signal volume would swamp it). ``llm_cost_cents`` powers the
per-harness daily budget cap without writing an audit row per call.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    JSON,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

# Harness lifecycle states (stored as plain strings — small closed set).
HARNESS_ACTIVE = "active"
HARNESS_PAUSED_BUDGET = "paused_budget"
HARNESS_TERMINATED = "terminated"


class EvalHarness(Base):
    __tablename__ = "eval_harness"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    parent_strategy_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("strategies.id", ondelete="CASCADE"), nullable=False
    )
    # Mode A: the running, LLM-wrapped clone. Mode B: the IDLE bucket id.
    mode_a_strategy_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("strategies.id", ondelete="CASCADE"), nullable=False
    )
    mode_b_strategy_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("strategies.id", ondelete="CASCADE"), nullable=False
    )
    state: Mapped[str] = mapped_column(String(20), nullable=False)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    terminated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    terminated_reason: Mapped[str | None] = mapped_column(String(64), nullable=True)

    __table_args__ = (
        Index("ix_eval_harness_parent_strategy_id", "parent_strategy_id"),
        Index("ix_eval_harness_user_id", "user_id"),
    )


class EvalHarnessDecision(Base):
    __tablename__ = "eval_harness_decisions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    harness_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("eval_harness.id", ondelete="CASCADE"), nullable=False
    )
    signal_uuid: Mapped[str] = mapped_column(String(36), nullable=False)
    signal_payload_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    mode_a_decision: Mapped[str] = mapped_column(String(8), nullable=False)  # act|skip
    mode_b_decision: Mapped[str] = mapped_column(String(8), nullable=False)
    mode_b_rationale: Mapped[str | None] = mapped_column(Text, nullable=True)
    mode_a_order_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("orders.id", ondelete="SET NULL"), nullable=True
    )
    mode_b_order_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("orders.id", ondelete="SET NULL"), nullable=True
    )
    # Fractional cents (USD×100) for this decision's LLM call — summed per day
    # for the harness budget cap. NULL when the call was skipped/failed.
    llm_cost_cents: Mapped[Decimal | None] = mapped_column(
        Numeric(20, 4), nullable=True
    )
    recorded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )

    __table_args__ = (
        Index(
            "ix_eval_harness_decisions_harness_recorded",
            "harness_id",
            "recorded_at",
        ),
    )
