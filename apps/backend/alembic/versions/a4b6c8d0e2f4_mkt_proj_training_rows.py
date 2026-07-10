"""MKT-PROJ-001 §1: market_projection_training_rows (FR-001).

Revision ID: a4b6c8d0e2f4
Revises: c3d5e7f9a1b2
Create Date: 2026-07-10
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "a4b6c8d0e2f4"
down_revision = "c3d5e7f9a1b2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "market_projection_training_rows",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("projection_type", sa.String(length=32), nullable=False),
        sa.Column("market_proxy", sa.String(length=16), nullable=False),
        sa.Column("features_json", sa.JSON(), nullable=True),
        sa.Column("shadow_features_json", sa.JSON(), nullable=True),
        sa.Column("label", sa.String(length=8), nullable=True),
        sa.Column("realized_return", sa.Float(), nullable=True),
        sa.Column("threshold", sa.Float(), nullable=True),
        sa.Column("valid_for_training", sa.Boolean(), nullable=False),
        sa.Column("exclusion_reason", sa.String(length=64), nullable=True),
        sa.Column("feature_version", sa.String(length=32), nullable=False),
        sa.Column("label_version", sa.String(length=32), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False,
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint(
            "date", "projection_type", "market_proxy", "feature_version",
            name="uq_mktproj_training_row",
        ),
    )


def downgrade() -> None:
    op.drop_table("market_projection_training_rows")
