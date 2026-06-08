"""ScannerRun — one recorded execution of a ScannerDefinition (P8 §2).

Stores the criterion snapshot + the matched / skipped symbols so the run is
reconstructible from the criterion alone (P8 Decision 1). The audit log carries
a parallel SCANNER_RUN entry; this table is the queryable result history the
Discovery view (§3) renders.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import (
    JSON,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

RUN_OK = "ok"
RUN_ERROR = "error"

# How the run was triggered. Only scheduled runs feed the Opportunities view.
TRIGGER_MANUAL = "manual"
TRIGGER_SCHEDULED = "scheduled"


class ScannerRun(Base):
    __tablename__ = "scanner_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    scanner_definition_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("scanner_definitions.id", ondelete="CASCADE"),
        nullable=False,
    )
    user_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    run_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    trigger: Mapped[str] = mapped_column(
        String(12), nullable=False, default=TRIGGER_MANUAL
    )
    criteria_snapshot: Mapped[str] = mapped_column(Text, nullable=False)
    universe_kind: Mapped[str] = mapped_column(String(16), nullable=False)
    timeframe: Mapped[str] = mapped_column(String(8), nullable=False)
    universe_size: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0
    )
    evaluated_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0
    )
    matched_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0
    )
    skipped_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0
    )
    matched_json: Mapped[list[dict[str, Any]]] = mapped_column(
        JSON, nullable=False, default=list
    )
    skipped_json: Mapped[list[dict[str, Any]]] = mapped_column(
        JSON, nullable=False, default=list
    )
    error: Mapped[str | None] = mapped_column(Text, nullable=True)

    __table_args__ = (
        Index(
            "ix_scanner_runs_definition_run", "scanner_definition_id", "run_at"
        ),
        Index("ix_scanner_runs_user", "user_id"),
    )
