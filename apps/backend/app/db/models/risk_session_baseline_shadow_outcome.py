"""ADR 0043 §D3 — the latest shadow-capture OUTCOME per (account, session date).

WHY THIS TABLE EXISTS
---------------------
The shadow capture (PR3a) records a baseline row only when it actually CAPTURES one. Its other
outcomes — reused, skipped, and the two fail-closed ones (MISSING_AFTER_ACTIVITY,
INDETERMINATE) — were log-only. That left the enforcement reader (PR3b) unable to tell *why* a
baseline is absent: "capture never ran", "activity already occurred", and "unverifiable" would all
collapse to a generic "no baseline".

This table makes the last outcome durable and queryable, one row per (account, ET session date),
upserted on each shadow poll. The enforcement basis selector consults it so a fallback carries a
SPECIFIC reason (NO_BASELINE_CAPTURED vs MISSING_AFTER_ACTIVITY vs CAPTURE_INDETERMINATE …) rather
than being collapsed. It is evidence only — never authoritative, never a baseline.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class RiskSessionBaselineShadowOutcome(Base):
    """The most recent shadow-capture outcome for one (account, session date)."""

    __tablename__ = "risk_session_baseline_shadow_outcomes"
    __table_args__ = (
        UniqueConstraint(
            "account_id",
            "market_session_date",
            name="uq_risk_session_baseline_shadow_outcome_account_date",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    account_id: Mapped[int] = mapped_column(
        ForeignKey("accounts.id", ondelete="CASCADE"), nullable=False
    )
    market_session_date: Mapped[str] = mapped_column(String(10), nullable=False)
    # One of app.risk.loss_control.session_baseline.SHADOW_* values.
    outcome: Mapped[str] = mapped_column(String(32), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
