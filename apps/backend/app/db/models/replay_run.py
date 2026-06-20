"""ReplayRun — one row per replay pass (P11 §4, ADR 0021).

Records every replay pass (the window verified, how many decisions matched / mismatched /
were skipped / errored, the wall-clock, and the version pins that make the run reproducible).
Operational telemetry, NOT the audit log — it is not hash-chained; the consequential
*mismatch event* is separately recorded in `audit_log` (`REPLAY_MISMATCH`). Mirrors
`reconciliation_runs` so the §5 recovery work reuses one operational-data-model, not two.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class ReplayRun(Base):
    __tablename__ = "replay_runs"
    __table_args__ = (Index("ix_replay_runs_ran", "ran_at"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    ran_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    # The replayed audit_log.ts window (NULL = unbounded on that side).
    window_start: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    window_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    n_checked: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    n_matched: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    n_mismatched: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    n_skipped: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    n_error: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    algorithm_version: Mapped[str] = mapped_column(String(8), nullable=False)  # recompute contract
    registry_version: Mapped[str] = mapped_column(String(8), nullable=False)   # verifier-set version
    detail_json: Mapped[str | None] = mapped_column(Text, nullable=True)        # non-MATCH verdicts
