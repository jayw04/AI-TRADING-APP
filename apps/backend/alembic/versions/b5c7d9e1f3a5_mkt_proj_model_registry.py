"""MKT-PROJ-001 §3: market_projection_model_registry (design §17.4).

Revision ID: b5c7d9e1f3a5
Revises: a4b6c8d0e2f4
Create Date: 2026-07-10
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "b5c7d9e1f3a5"
down_revision = "a4b6c8d0e2f4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "market_projection_model_registry",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("model_version", sa.String(length=128), nullable=False),
        sa.Column("model_type", sa.String(length=64), nullable=False),
        sa.Column("projection_type", sa.String(length=32), nullable=False),
        sa.Column("artifact_path", sa.String(length=256), nullable=False),
        sa.Column("artifact_hash", sa.String(length=64), nullable=False),
        sa.Column("feature_version", sa.String(length=32), nullable=False),
        sa.Column("label_version", sa.String(length=32), nullable=False),
        sa.Column("training_window", sa.String(length=64), nullable=False),
        sa.Column("validation_window", sa.String(length=64), nullable=False),
        sa.Column("git_commit", sa.String(length=64), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False,
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint("model_version", name="uq_mktproj_model_version"),
    )


def downgrade() -> None:
    op.drop_table("market_projection_model_registry")
