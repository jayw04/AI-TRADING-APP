"""Durable one-run-per-scheduled-slot claim.

WHY (incident 2026-07-13). ``momentum-portfolio`` executed its 10:00 ET slot SIX times in
52 seconds, re-proposing the same SNDK/LITE trims on every pass. The in-process guard
(``ctx.dispatch_seq``) closes the intra-dispatch hole, but process memory is not a safety
boundary: it does not survive a restart, it does not survive a second scheduler, and it is
not evidence after the fact.

So the claim is PERSISTED, and the uniqueness lives in the database:

    UNIQUE (account_id, strategy_id, scheduled_slot, strategy_version)

The claim is written BEFORE the strategy runs. A second attempt on the same slot hits the
constraint and is refused.

**A run that reached signal generation and risk evaluation is COMPLETE — even if every
proposal was rejected.** That is the load-bearing semantic. On 2026-07-13 all 18 order
proposals were rejected by the daily-loss gate, and the strategy treated "nothing happened"
as licence to try again. It had happened; it had simply been refused. A slot is claimed by
being *attempted*, not by succeeding.

Retry is therefore an explicit, recorded act (``retry_generation`` + ``retry_reason``), never
a side effect of failure. Nothing deletes a claim to re-run a slot.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

# ---- outcome of the claimed run ----------------------------------------------------
SLOT_RUNNING = "RUNNING"
SLOT_COMPLETED = "COMPLETED"  # reached risk evaluation — INCLUDING all-rejected
SLOT_ERROR = "ERROR"


class StrategySlotClaim(Base):
    """One row per (account, strategy, scheduled slot, strategy version).

    Written before execution; the UNIQUE constraint is what actually prevents the second run.
    """

    __tablename__ = "strategy_slot_claims"
    __table_args__ = (
        # THE control. Not an index for speed — the uniqueness IS the mechanism.
        UniqueConstraint(
            "account_id",
            "strategy_id",
            "scheduled_slot",
            "strategy_version",
            "retry_generation",
            name="uq_strategy_slot_claim",
        ),
        Index("ix_strategy_slot_claims_strategy_slot", "strategy_id", "scheduled_slot"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)

    account_id: Mapped[int | None] = mapped_column(
        ForeignKey("accounts.id", ondelete="SET NULL"), nullable=True
    )
    strategy_id: Mapped[int] = mapped_column(
        ForeignKey("strategies.id", ondelete="CASCADE"), nullable=False
    )

    # The slot this run belongs to, as an ET wall-clock instant truncated to the schedule's
    # granularity (e.g. 2026-07-13T10:00 ET). NOT "now" — two dispatches of the same cron slot
    # have different `now` but the same slot.
    scheduled_slot: Mapped[str] = mapped_column(String(32), nullable=False)

    # Part of the key: a code change is a legitimately different run of the same slot.
    strategy_version: Mapped[str] = mapped_column(String(32), nullable=False)

    # Retry is EXPLICIT. Bump this (with a reason) to legitimately re-run a slot; never delete
    # the original claim.
    retry_generation: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    retry_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    claimed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    outcome: Mapped[str] = mapped_column(String(16), nullable=False, default=SLOT_RUNNING)
    error_text: Mapped[str | None] = mapped_column(Text, nullable=True)
