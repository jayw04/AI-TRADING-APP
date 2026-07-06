"""SchedulerHeartbeat — one row per host, written by the armed scheduler (ADR 0032).

Makes the *armed* host observable: which `host_id` is running its scheduler and when it last
beat. Backs the cutover single-armed check and the missed-scheduler alarm. Operational telemetry,
not the audit log (not hash-chained); purely additive and best-effort — a write failure never
disturbs scheduling.

`last_dispatch_at` is forward-ready (nullable) for an OrderRouter hook that records the last
automated dispatch; until that hook lands the missed-rebalance alarm uses the existing per-job
scheduler success metrics instead, so this column may be NULL.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class SchedulerHeartbeat(Base):
    __tablename__ = "scheduler_heartbeat"

    host_id: Mapped[str] = mapped_column(String, primary_key=True)
    armed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    last_beat_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_dispatch_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    # Which code was dispatching (ADR 0032 R-heartbeat): git short-sha or app version.
    code_version: Mapped[str | None] = mapped_column(String, nullable=True)
