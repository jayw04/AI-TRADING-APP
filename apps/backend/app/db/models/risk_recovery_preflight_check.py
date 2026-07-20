"""ADR 0043 §D5 — the individual checks of a recovery preflight.

Each of the preflight's checks (broker reachable, positions reconcile exactly, open orders
reconcile, baseline present and immutable, loss recomputed from authoritative data, trip cause
classified, no integrity stop remains, …) is recorded here with its own PASS/FAIL/INCOMPLETE
status and its evidence. Recording each check individually — rather than a single aggregate
verdict — is what lets a reviewer see *which* condition blocked (or cleared) a recovery, and is the
audit trail behind the class-dependent authority decision on the parent ``risk_recovery_preflights``
row.

Append-only, like the rest of the loss-control evidence. PR 1 lands the table only.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class RiskRecoveryPreflightCheck(Base):
    """One named check within a recovery preflight, with its status and evidence."""

    __tablename__ = "risk_recovery_preflight_checks"
    __table_args__ = (
        Index("ix_risk_recovery_preflight_checks_preflight", "preflight_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    preflight_id: Mapped[int] = mapped_column(
        ForeignKey("risk_recovery_preflights.id", ondelete="CASCADE"), nullable=False
    )

    # The check's stable name (e.g. "positions_reconcile", "baseline_present").
    check_name: Mapped[str] = mapped_column(String(64), nullable=False)
    # PASS | FAIL | INCOMPLETE.
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    # JSON blob of what the check observed (the evidence behind its status).
    evidence: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
