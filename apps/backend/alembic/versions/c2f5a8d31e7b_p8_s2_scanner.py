"""P8 s2: scanner_definitions + scanner_runs

P8 §2 — the Discovery scanner engine: a saved criterion + universe spec
(scanner_definitions) and its recorded executions (scanner_runs).

Revision ID: c2f5a8d31e7b
Revises: b6d1f4a8c3e2
Create Date: 2026-06-07

"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "c2f5a8d31e7b"
down_revision: str | Sequence[str] | None = "b6d1f4a8c3e2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "scanner_definitions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("criteria", sa.Text(), nullable=False),
        sa.Column("universe_kind", sa.String(16), nullable=False),
        sa.Column("universe_symbols_json", sa.JSON(), nullable=True),
        sa.Column(
            "timeframe", sa.String(8), nullable=False, server_default="1Day"
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_scanner_definitions_user", "scanner_definitions", ["user_id"]
    )

    op.create_table(
        "scanner_runs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "scanner_definition_id",
            sa.Integer(),
            sa.ForeignKey("scanner_definitions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("run_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("criteria_snapshot", sa.Text(), nullable=False),
        sa.Column("universe_kind", sa.String(16), nullable=False),
        sa.Column("timeframe", sa.String(8), nullable=False),
        sa.Column("universe_size", sa.Integer(), nullable=False),
        sa.Column("evaluated_count", sa.Integer(), nullable=False),
        sa.Column("matched_count", sa.Integer(), nullable=False),
        sa.Column("skipped_count", sa.Integer(), nullable=False),
        sa.Column("matched_json", sa.JSON(), nullable=False),
        sa.Column("skipped_json", sa.JSON(), nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
    )
    op.create_index(
        "ix_scanner_runs_definition_run",
        "scanner_runs",
        ["scanner_definition_id", "run_at"],
    )
    op.create_index("ix_scanner_runs_user", "scanner_runs", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_scanner_runs_user", table_name="scanner_runs")
    op.drop_index(
        "ix_scanner_runs_definition_run", table_name="scanner_runs"
    )
    op.drop_table("scanner_runs")
    op.drop_index(
        "ix_scanner_definitions_user", table_name="scanner_definitions"
    )
    op.drop_table("scanner_definitions")
