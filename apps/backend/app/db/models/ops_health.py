"""Operational pipeline-health telemetry — three tables.

Motivation (2026-07-13). On a rebalance Monday the momentum book produced ZERO orders and
we could not tell, from the database alone, whether the strategy

    (a) fired and correctly decided to trade nothing (target book == current book), or
    (b) never fired at all.

Those two look IDENTICAL in the ``orders`` table, because a no-op leaves no orders to
derive a run window from. Deriving rebalance windows from orders is therefore structurally
incapable of answering the question. The dispatch itself has to be recorded.

These are OPERATIONAL TELEMETRY, not the audit log — they are NOT hash-chained, and they
record no consequential action. They follow the ``reconciliation_runs`` precedent: a run
row is written whether the outcome was clean or not, so history is queryable and a MISSING
row is itself the signal.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

# ---- strategy_dispatch_runs.outcome ------------------------------------------------
DISPATCH_COMPLETED = "COMPLETED"  # ran to completion (may be 0 orders)
DISPATCH_SKIPPED_OUT_OF_SESSION = "SKIPPED_OUT_OF_SESSION"
DISPATCH_NOT_RUNNING = "NOT_RUNNING"  # strategy not in the engine's map
DISPATCH_ERROR = "ERROR"

# ---- status for data_health_snapshots / ops_check_runs ------------------------------
STATUS_OK = "OK"
STATUS_WARN = "WARN"
STATUS_FAIL = "FAIL"


class StrategyDispatchRun(Base):
    """ONE ROW PER SCHEDULED DISPATCH — the record that distinguishes a legitimate
    zero-order rebalance from a rebalance that never fired.

    A no-op still writes a row (``outcome=COMPLETED, orders_submitted=0``). If the
    scheduler never fires, there is NO ROW — and absence is exactly the alarm.
    """

    __tablename__ = "strategy_dispatch_runs"
    __table_args__ = (
        Index("ix_strategy_dispatch_runs_strategy_started", "strategy_id", "started_at"),
        Index("ix_strategy_dispatch_runs_started", "started_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    strategy_id: Mapped[int] = mapped_column(
        ForeignKey("strategies.id", ondelete="CASCADE"), nullable=False
    )
    account_id: Mapped[int | None] = mapped_column(
        ForeignKey("accounts.id", ondelete="SET NULL"), nullable=True
    )

    # the cron slot this dispatch belongs to (e.g. 2026-07-13 10:00 ET) — lets us assert
    # "the 10:00 slot produced a row" without guessing from wall-clock drift.
    scheduled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)

    schedule: Mapped[str | None] = mapped_column(String(64), nullable=True)
    market_session: Mapped[str | None] = mapped_column(String(16), nullable=True)
    outcome: Mapped[str] = mapped_column(String(32), nullable=False)

    symbols_total: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    symbols_with_bars: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    orders_submitted: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    error_text: Mapped[str | None] = mapped_column(Text, nullable=True)


class DataHealthSnapshot(Base):
    """ONE ROW PER DATA SOURCE PER CHECK — when was it last refreshed, how current is it,
    and how much of the live universe does it actually cover."""

    __tablename__ = "data_health_snapshots"
    __table_args__ = (Index("ix_data_health_snapshots_source_captured", "source", "captured_at"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    captured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    # FACTOR_STORE_SEP | FACTOR_STORE_ACTIONS | BAR_CACHE | UNIVERSE_COVERAGE
    source: Mapped[str] = mapped_column(String(32), nullable=False)

    # newest data date present (e.g. sep max(date)) and when the source file was written
    as_of_date: Mapped[str | None] = mapped_column(String(10), nullable=True)
    last_refresh_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # trading sessions between as_of_date and the last COMPLETED session (0 == current)
    staleness_sessions: Mapped[int | None] = mapped_column(Integer, nullable=True)

    rows: Mapped[int | None] = mapped_column(Integer, nullable=True)
    symbols_covered: Mapped[int | None] = mapped_column(Integer, nullable=True)
    symbols_expected: Mapped[int | None] = mapped_column(Integer, nullable=True)

    status: Mapped[str] = mapped_column(String(8), nullable=False)
    detail_json: Mapped[str | None] = mapped_column(Text, nullable=True)


class OpsCheckRun(Base):
    """ONE ROW PER CHECKLIST RUN (DAILY or WEEKLY) — the traceable header, with the
    rendered report kept alongside so a past run can be read back verbatim."""

    __tablename__ = "ops_check_runs"
    __table_args__ = (Index("ix_ops_check_runs_kind_started", "kind", "started_at"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    kind: Mapped[str] = mapped_column(String(8), nullable=False)  # DAILY | WEEKLY
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    status: Mapped[str] = mapped_column(String(8), nullable=False)  # OK | WARN | FAIL
    checks_total: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    checks_ok: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    checks_warn: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    checks_fail: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    report_md: Mapped[str | None] = mapped_column(Text, nullable=True)
    detail_json: Mapped[str | None] = mapped_column(Text, nullable=True)
