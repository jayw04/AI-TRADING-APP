"""BacktestJob — one attempt to run a backtest.

A successful job produces exactly one :class:`BacktestResult` row (linked
via ``result_id``); cancelled or failed jobs have ``result_id=NULL``.

``config_json`` carries the full :class:`BacktestConfig` so the worker
can rehydrate a job after a process restart. ``percent_complete`` and
``current_ts`` are advisory — the real-time channel is the
``backtest.progress`` WS event; the columns are for polling fallback and
forensic inspection.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import (
    JSON,
    DateTime,
    Float,
    ForeignKey,
    Index,
    String,
)
from sqlalchemy import Enum as SQLEnum
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.enums import BacktestJobStatus


class BacktestJob(Base):
    __tablename__ = "backtest_jobs"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    strategy_id: Mapped[int] = mapped_column(
        ForeignKey("strategies.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # Populated when the job transitions to COMPLETED. NULL otherwise.
    result_id: Mapped[int | None] = mapped_column(
        ForeignKey("backtest_results.id", ondelete="SET NULL"), nullable=True
    )

    status: Mapped[BacktestJobStatus] = mapped_column(
        SQLEnum(BacktestJobStatus, native_enum=False, length=16),
        nullable=False,
        default=BacktestJobStatus.QUEUED,
        index=True,
    )

    # Persisted at submission so the worker can rehydrate the config
    # without going back through the API. Underscore-prefixed keys
    # (e.g. ``_symbols``) are worker-internal — see Note 6 in the doc.
    config_json: Mapped[dict[str, Any]] = mapped_column(
        JSON, nullable=False, default=dict
    )

    # Progress columns (advisory; real-time is the WS event).
    percent_complete: Mapped[float] = mapped_column(
        Float, nullable=False, default=0.0
    )
    # ISO timestamp of the bar currently being processed. Kept as string to
    # avoid timezone-conversion noise — purely a display value.
    current_ts: Mapped[str | None] = mapped_column(String(64), nullable=True)

    submitted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # On failure: the exception message (truncated). On cancellation:
    # who/why. NULL for successful completions.
    error_text: Mapped[str | None] = mapped_column(String(2048), nullable=True)

    # User-facing label carried here so the UI can show "running:
    # tighter-rsi-25" without joining to the eventual BacktestResult.
    label: Mapped[str] = mapped_column(
        String(128), nullable=False, default="default"
    )

    __table_args__ = (
        Index("ix_backtest_jobs_strategy_status", "strategy_id", "status"),
        Index("ix_backtest_jobs_submitted_at", "submitted_at"),
    )

    def __repr__(self) -> str:  # pragma: no cover
        return (
            f"<BacktestJob id={self.id} strategy={self.strategy_id} "
            f"status={self.status.value}>"
        )
