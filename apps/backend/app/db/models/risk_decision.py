"""ADR 0042 § 7 — the append-only risk-decision ledger.

WHY THIS EXISTS. **Rejected orders are not persisted anywhere.** On 2026-07-13 the ``orders``
table showed *zero* rows for account 1 all day, while the momentum book was in fact proposing
and having refused eighteen orders. The investigation reached the wrong conclusion **twice** —
first "it ran and correctly did nothing", then "it was halted and never ran" — before the
``signals`` table gave up the truth by accident.

There was no durable ledger between *signal generated* and *order accepted*. That is where the
system's most consequential decisions are made, and it was a hole.

The durable lifecycle ADR 0042 requires:

    signal → order proposal → RISK DECISION → broker submission → broker ack/reject → fill/cancel

This table is the third stage, and it is written for **ALLOW and REJECT alike**. An order that
never existed because a gate refused it is exactly the event you most need a record of.

APPEND-ONLY. A retry **references** the prior decision (``supersedes_id``); it never overwrites
it. This is operational evidence, not the hash-chained ``audit_log`` — but it is immutable by
convention and by the absence of any update path.
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
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class RiskDecision(Base):
    """One row per risk decision — allowed or refused, strategy or manual, order or cancel."""

    __tablename__ = "risk_decisions"
    __table_args__ = (
        Index("ix_risk_decisions_account_decided", "account_id", "decided_at"),
        Index("ix_risk_decisions_correlation", "correlation_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)

    # ---- who / what ----------------------------------------------------------------
    account_id: Mapped[int] = mapped_column(
        ForeignKey("accounts.id", ondelete="CASCADE"), nullable=False
    )
    strategy_id: Mapped[int | None] = mapped_column(
        ForeignKey("strategies.id", ondelete="SET NULL"), nullable=True
    )
    strategy_version: Mapped[str | None] = mapped_column(String(32), nullable=True)
    slot_claim_id: Mapped[int | None] = mapped_column(
        ForeignKey("strategy_slot_claims.id", ondelete="SET NULL"), nullable=True
    )
    # STRATEGY | MANUAL | AGENT — the exemption is source-NEUTRAL (§ C); the source is recorded
    # so that neutrality is auditable, not so that it can be privileged.
    source_type: Mapped[str] = mapped_column(String(16), nullable=False)

    # ORDER_SUBMIT | ORDER_CANCEL | ORDER_REPLACE
    action_type: Mapped[str] = mapped_column(String(16), nullable=False)
    order_id: Mapped[int | None] = mapped_column(
        ForeignKey("orders.id", ondelete="SET NULL"), nullable=True
    )
    order_group_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    symbol: Mapped[str] = mapped_column(String(20), nullable=False)
    side: Mapped[str | None] = mapped_column(String(8), nullable=True)
    qty: Mapped[Decimal | None] = mapped_column(Numeric(20, 8), nullable=True)

    # ---- the lock this decision was made under -------------------------------------
    # The daily-loss value is a HISTORICAL trigger. A permitted reduction is NOT required to
    # improve it — recording both keeps that distinction legible after the fact.
    lock_state: Mapped[str] = mapped_column(String(24), nullable=False)  # UNLOCKED|DAILY_LOSS|BREAKER
    lock_reason: Mapped[str | None] = mapped_column(String(64), nullable=True)
    daily_pnl: Mapped[Decimal | None] = mapped_column(Numeric(20, 4), nullable=True)

    # ---- the state it was made AGAINST (§ A) ---------------------------------------
    risk_policy_version: Mapped[str] = mapped_column(String(16), nullable=False)
    before_state_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    projected_after_state_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    broker_cursor: Mapped[str | None] = mapped_column(String(64), nullable=True)

    position_qty_before: Mapped[Decimal | None] = mapped_column(Numeric(20, 8), nullable=True)
    position_qty_after: Mapped[Decimal | None] = mapped_column(Numeric(20, 8), nullable=True)
    gross_exposure_before: Mapped[Decimal | None] = mapped_column(Numeric(20, 4), nullable=True)
    gross_exposure_after: Mapped[Decimal | None] = mapped_column(Numeric(20, 4), nullable=True)
    leverage_before: Mapped[Decimal | None] = mapped_column(Numeric(12, 6), nullable=True)
    leverage_after: Mapped[Decimal | None] = mapped_column(Numeric(12, 6), nullable=True)
    available_reducible_qty: Mapped[Decimal | None] = mapped_column(
        Numeric(20, 8), nullable=True
    )

    # ---- the decision ---------------------------------------------------------------
    risk_effect: Mapped[str] = mapped_column(String(20), nullable=False)
    decision: Mapped[str] = mapped_column(String(16), nullable=False)
    reason_codes: Mapped[str] = mapped_column(Text, nullable=False)  # JSON array

    decided_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    correlation_id: Mapped[str] = mapped_column(String(64), nullable=False)

    # A retry REFERENCES the prior decision. It never overwrites it.
    supersedes_id: Mapped[int | None] = mapped_column(
        ForeignKey("risk_decisions.id", ondelete="SET NULL"), nullable=True
    )
    retry_generation: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
