"""ADR 0043 — the append-only loss-control event log (the source of truth for state).

WHY THIS TABLE EXISTS
---------------------
The loss controls today live in scattered, mutable state: ``accounts.circuit_breaker_tripped_at``
is a single nullable timestamp, and "why did it trip / was it a real loss or an artifact" is not
recorded anywhere reconstructable. The 2026-07-13 incident could not tell, after the fact, whether
a trip was a genuine loss or a stale-baseline artifact.

ADR 0043 makes the **event log authoritative**: every state transition is appended here with the
full causal context (the D4 trip taxonomy, the values that tripped it, the snapshots it was judged
against). The materialized current-state row (``risk_loss_control_state``) and the legacy
``circuit_breaker_tripped_at`` column are both *projections* — regenerable from this log, never the
origin of a transition.

APPEND-ONLY + ORDERED
---------------------
Rows are never updated or deleted. ``sequence_no`` is monotonic per account (unique with
``account_id``), giving deterministic ordering of near-simultaneous events (§D1.2) — a later event
always observes the state produced by all lower-sequence events.

Only the loss-control persistence service writes this table (§D1.1) — controls emit transition
*requests*; the service is the sole persister. PR 1 lands the table only; the service arrives in a
later increment.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class RiskControlEvent(Base):
    """One appended row per loss-control state transition — the authoritative history."""

    __tablename__ = "risk_control_events"
    __table_args__ = (
        # Monotonic per account: no two events share a sequence number, which is what makes the
        # ordering (and the compare-and-swap that assigns it) deterministic under concurrency.
        UniqueConstraint(
            "account_id", "sequence_no", name="uq_risk_control_event_account_seq"
        ),
        Index("ix_risk_control_events_account_created", "account_id", "created_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    account_id: Mapped[int] = mapped_column(
        ForeignKey("accounts.id", ondelete="CASCADE"), nullable=False
    )
    # ET session date at event time ("YYYY-MM-DD"); nullable for events outside a trading session.
    session_date: Mapped[str | None] = mapped_column(String(10), nullable=True)
    sequence_no: Mapped[int] = mapped_column(Integer, nullable=False)

    # DAILY_LOSS | CIRCUIT_BREAKER | INTEGRITY | RECOVERY | MANUAL — which control emitted this.
    control_type: Mapped[str] = mapped_column(String(24), nullable=False)

    # ---- the transition -------------------------------------------------------------------
    from_state: Mapped[str | None] = mapped_column(String(32), nullable=True)
    to_state: Mapped[str] = mapped_column(String(32), nullable=False)
    requested_transition: Mapped[str | None] = mapped_column(String(48), nullable=True)

    # ---- D4 three-field trip taxonomy (null for non-trip transitions, e.g. recovery steps) -
    trip_type: Mapped[str | None] = mapped_column(String(24), nullable=True)
    trip_cause: Mapped[str | None] = mapped_column(String(48), nullable=True)
    trip_evidence_status: Mapped[str | None] = mapped_column(String(24), nullable=True)

    # ---- what tripped it, and the state it was judged against ------------------------------
    trigger_value: Mapped[Decimal | None] = mapped_column(Numeric(20, 4), nullable=True)
    threshold_value: Mapped[Decimal | None] = mapped_column(Numeric(20, 4), nullable=True)
    baseline_id: Mapped[int | None] = mapped_column(
        ForeignKey("risk_session_baselines.id", ondelete="SET NULL"), nullable=True
    )
    equity_snapshot_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    positions_snapshot_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    orders_snapshot_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    # The ADR 0042 decision-ledger row this transition corresponds to, when the trigger was an
    # order-evaluation (binds the loss-control history to the risk-decision history).
    decision_ledger_id: Mapped[int | None] = mapped_column(
        ForeignKey("risk_decisions.id", ondelete="SET NULL"), nullable=True
    )

    # ---- who / provenance ------------------------------------------------------------------
    # SYSTEM | USER | STRATEGY | AGENT.
    initiator_type: Mapped[str] = mapped_column(String(16), nullable=False)
    initiator_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    control_version: Mapped[int] = mapped_column(Integer, nullable=False)
    engine_commit: Mapped[str | None] = mapped_column(String(64), nullable=True)
    config_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
