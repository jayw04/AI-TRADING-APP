"""P11 §4: replay_runs — replay-pass history (re-verify decisions from audit fingerprints).

The second persisted operational-data-model table (ADR 0021), mirroring reconciliation_runs.
One row per replay pass; operational telemetry, not the audit log (not hash-chained — the
mismatch event is recorded separately in audit_log as REPLAY_MISMATCH). Purely additive.

Revision ID: c4e9a2b7d1f3
Revises: b3d8f1a2c7e9
Create Date: 2026-06-20
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "c4e9a2b7d1f3"
down_revision = "b3d8f1a2c7e9"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "replay_runs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("ran_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("window_start", sa.DateTime(timezone=True), nullable=True),
        sa.Column("window_end", sa.DateTime(timezone=True), nullable=True),
        sa.Column("n_checked", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("n_matched", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("n_mismatched", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("n_skipped", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("n_error", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("algorithm_version", sa.String(length=8), nullable=False),
        sa.Column("registry_version", sa.String(length=8), nullable=False),
        sa.Column("detail_json", sa.Text(), nullable=True),
    )
    op.create_index("ix_replay_runs_ran", "replay_runs", ["ran_at"])


def downgrade() -> None:
    op.drop_index("ix_replay_runs_ran", table_name="replay_runs")
    op.drop_table("replay_runs")
