"""P11 §3: reconciliation_runs — operational run history (broker ⇄ local).

The first persisted operational-data-model table (ADR 0021). One row per reconciliation
pass; operational telemetry, not the audit log (not hash-chained — the discrepancy event
is recorded separately in audit_log). Purely additive.

Revision ID: b3d8f1a2c7e9
Revises: d3a8e1f6c2b9
Create Date: 2026-06-19
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "b3d8f1a2c7e9"
down_revision = "d3a8e1f6c2b9"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "reconciliation_runs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("account_id", sa.Integer(), sa.ForeignKey("accounts.id", ondelete="CASCADE"), nullable=False),
        sa.Column("ran_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("domain", sa.String(length=16), nullable=False),
        sa.Column("result", sa.String(length=16), nullable=False),
        sa.Column("n_checked", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("n_discrepancies", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("algorithm_version", sa.String(length=8), nullable=False),
        sa.Column("detail_json", sa.Text(), nullable=True),
    )
    op.create_index(
        "ix_reconciliation_runs_account_ran",
        "reconciliation_runs",
        ["account_id", "ran_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_reconciliation_runs_account_ran", table_name="reconciliation_runs")
    op.drop_table("reconciliation_runs")
