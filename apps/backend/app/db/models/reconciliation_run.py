"""ReconciliationRun — one row per reconciliation pass (P11 §3, ADR 0021).

The first persisted operational-data-model table. Records every reconciliation pass
(clean or not) so KPIs (latency, discrepancy rate) and run history are queryable. This is
operational telemetry, NOT the audit log — it is not hash-chained; the *discrepancy event*
is separately recorded in `audit_log` (`RECONCILIATION_DISCREPANCY`). Append-only in
spirit (run history); reconciliation never mutates portfolio state.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class ReconciliationRun(Base):
    __tablename__ = "reconciliation_runs"
    __table_args__ = (
        Index("ix_reconciliation_runs_account_ran", "account_id", "ran_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    account_id: Mapped[int] = mapped_column(
        ForeignKey("accounts.id", ondelete="CASCADE"), nullable=False
    )
    ran_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    domain: Mapped[str] = mapped_column(String(16), nullable=False)   # 'position' | 'intent'
    result: Mapped[str] = mapped_column(String(16), nullable=False)   # pass|warning|fail|error|unavailable
    n_checked: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    n_discrepancies: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    algorithm_version: Mapped[str] = mapped_column(String(8), nullable=False)
    detail_json: Mapped[str | None] = mapped_column(Text, nullable=True)
