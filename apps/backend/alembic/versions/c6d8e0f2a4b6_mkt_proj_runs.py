"""MKT-PROJ-001 §4: market_projection_runs (design §17.4 + FR-013 + review fields).

Revision ID: c6d8e0f2a4b6
Revises: b5c7d9e1f3a5
Create Date: 2026-07-10
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "c6d8e0f2a4b6"
down_revision = "b5c7d9e1f3a5"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "market_projection_runs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("projection_type", sa.String(length=32), nullable=False),
        sa.Column("market_proxy", sa.String(length=16), nullable=False),
        sa.Column("as_of", sa.DateTime(timezone=True), nullable=False),
        sa.Column("target_date", sa.Date(), nullable=False),
        sa.Column("attempt_number", sa.Integer(), nullable=False),
        sa.Column("model_version", sa.String(length=128), nullable=True),
        sa.Column("feature_version", sa.String(length=32), nullable=True),
        sa.Column("label_version", sa.String(length=32), nullable=True),
        sa.Column("prob_up", sa.Float(), nullable=True),
        sa.Column("prob_down", sa.Float(), nullable=True),
        sa.Column("prob_neutral", sa.Float(), nullable=True),
        sa.Column("prob_material", sa.Float(), nullable=True),
        sa.Column("elevated", sa.Boolean(), nullable=True),
        sa.Column("display_phrase", sa.String(length=128), nullable=True),
        sa.Column("confidence", sa.String(length=8), nullable=True),
        sa.Column("material_threshold_pct", sa.Float(), nullable=True),
        sa.Column("drivers_json", sa.JSON(), nullable=True),
        sa.Column("features_json", sa.JSON(), nullable=True),
        sa.Column("source_json", sa.JSON(), nullable=True),
        sa.Column("run_status", sa.String(length=16), nullable=False),
        sa.Column("unavailable_reason", sa.String(length=128), nullable=True),
        sa.Column("outcome_status", sa.String(length=16), nullable=False),
        sa.Column("realized_return", sa.Float(), nullable=True),
        sa.Column("realized_label", sa.String(length=8), nullable=True),
        sa.Column("correct_magnitude", sa.Boolean(), nullable=True),
        sa.Column("prob_assigned_to_realized_class", sa.Float(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False,
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint(
            "projection_type", "market_proxy", "target_date", "attempt_number",
            name="uq_mktproj_run_attempt",
        ),
    )


def downgrade() -> None:
    op.drop_table("market_projection_runs")
