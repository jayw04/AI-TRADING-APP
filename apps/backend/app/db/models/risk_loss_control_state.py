"""ADR 0043 §D1 — the materialized current loss-control state (one row per account).

This is a **projection** of the append-only ``risk_control_events`` log: a read-optimized row
holding the account's current state so the order path need not fold the whole event log on every
evaluation. It is regenerable from the log and is never the origin of a transition — the log is the
source of truth (§D1.1).

``state_version`` is the compare-and-swap guard: a transition is applied with
``UPDATE ... WHERE state_version = :expected``, so two concurrent writers cannot both advance the
state (the same discipline ``RiskDecisionService._claim_capacity`` uses for capacity, and for the
same reason — a process-local lock is not authority across processes; 2026-07-14 proved it).
``last_sequence_no`` records the highest event sequence folded into this row.

PR 1 lands the table only; the persistence service that advances it arrives in a later increment.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class RiskLossControlState(Base):
    """The current loss-control state for one account — a CAS-guarded projection."""

    __tablename__ = "risk_loss_control_state"
    __table_args__ = (
        UniqueConstraint("account_id", name="uq_risk_loss_control_state_account"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    account_id: Mapped[int] = mapped_column(
        ForeignKey("accounts.id", ondelete="CASCADE"), nullable=False
    )

    # One of the six ADR 0043 §D1 states. Default mirrors
    # ``app.risk.loss_control.constants.STATE_NORMAL`` — kept as a literal here so this
    # foundational model has no dependency on the risk-logic package (layering: models are lower
    # than risk logic; the persistence service asserts the value against the constant).
    state: Mapped[str] = mapped_column(String(32), nullable=False, default="NORMAL")

    # Compare-and-swap guard — bumped on every applied transition.
    state_version: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # Highest risk_control_events.sequence_no folded into this projection.
    last_sequence_no: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    control_version: Mapped[int] = mapped_column(Integer, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
