"""ops pipeline health: strategy_dispatch_runs, data_health_snapshots, ops_check_runs

Revision ID: c1d4e8f2a6b9
Revises: b5c7d9e1f3a5
Create Date: 2026-07-13

Operational telemetry for the daily/weekly pipeline checklist.

WHY (2026-07-13). On a rebalance Monday the momentum book produced ZERO orders and the
database could not distinguish "fired and correctly traded nothing" from "never fired" —
those are identical in ``orders``, because a no-op leaves no orders to derive a window
from. ``strategy_dispatch_runs`` records the DISPATCH itself, so a no-op writes a row and
a missed fire leaves a hole. The hole is the alarm.

These tables are telemetry, NOT the audit log: not hash-chained, no consequential action
recorded. They follow the ``reconciliation_runs`` precedent.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "c1d4e8f2a6b9"
down_revision = "b5c7d9e1f3a5"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "strategy_dispatch_runs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("strategy_id", sa.Integer(), nullable=False),
        sa.Column("account_id", sa.Integer(), nullable=True),
        sa.Column("scheduled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("schedule", sa.String(length=64), nullable=True),
        sa.Column("market_session", sa.String(length=16), nullable=True),
        sa.Column("outcome", sa.String(length=32), nullable=False),
        sa.Column("symbols_total", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("symbols_with_bars", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("orders_submitted", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("error_text", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["strategy_id"], ["strategies.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["account_id"], ["accounts.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_strategy_dispatch_runs_strategy_started",
        "strategy_dispatch_runs",
        ["strategy_id", "started_at"],
    )
    op.create_index(
        "ix_strategy_dispatch_runs_started", "strategy_dispatch_runs", ["started_at"]
    )

    op.create_table(
        "data_health_snapshots",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("captured_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("source", sa.String(length=32), nullable=False),
        sa.Column("as_of_date", sa.String(length=10), nullable=True),
        sa.Column("last_refresh_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("staleness_sessions", sa.Integer(), nullable=True),
        sa.Column("rows", sa.Integer(), nullable=True),
        sa.Column("symbols_covered", sa.Integer(), nullable=True),
        sa.Column("symbols_expected", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(length=8), nullable=False),
        sa.Column("detail_json", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_data_health_snapshots_source_captured",
        "data_health_snapshots",
        ["source", "captured_at"],
    )

    op.create_table(
        "ops_check_runs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("kind", sa.String(length=8), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(length=8), nullable=False),
        sa.Column("checks_total", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("checks_ok", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("checks_warn", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("checks_fail", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("report_md", sa.Text(), nullable=True),
        sa.Column("detail_json", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_ops_check_runs_kind_started", "ops_check_runs", ["kind", "started_at"])


def downgrade() -> None:
    op.drop_index("ix_ops_check_runs_kind_started", table_name="ops_check_runs")
    op.drop_table("ops_check_runs")
    op.drop_index(
        "ix_data_health_snapshots_source_captured", table_name="data_health_snapshots"
    )
    op.drop_table("data_health_snapshots")
    op.drop_index("ix_strategy_dispatch_runs_started", table_name="strategy_dispatch_runs")
    op.drop_index(
        "ix_strategy_dispatch_runs_strategy_started", table_name="strategy_dispatch_runs"
    )
    op.drop_table("strategy_dispatch_runs")
