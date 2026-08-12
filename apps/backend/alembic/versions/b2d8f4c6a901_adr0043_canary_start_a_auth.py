"""Extend ADR-0043 canary Model A schema: durable Start A authorizations.

Revision ID: b2d8f4c6a901
Revises: a9c3e1f5b702
Create Date: 2026-07-31
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "b2d8f4c6a901"
down_revision: str | Sequence[str] | None = "a9c3e1f5b702"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "risk_canary_start_a_authorizations",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("start_a_id", sa.String(length=128), nullable=False),
        sa.Column("freeze_id", sa.String(length=128), nullable=False),
        sa.Column("freeze_body_sha256", sa.String(length=64), nullable=False),
        sa.Column("broker_account_id", sa.String(length=64), nullable=False),
        sa.Column("workbench_account_id", sa.Integer(), nullable=False),
        sa.Column("configuration_digest", sa.String(length=64), nullable=False),
        sa.Column("image_digest", sa.String(length=128), nullable=False),
        sa.Column("commit_sha", sa.String(length=64), nullable=False),
        sa.Column("authorized_session_date", sa.String(length=10), nullable=False),
        sa.Column("design_version", sa.String(length=128), nullable=False),
        sa.Column("applicable_daily_loss_limit", sa.Numeric(precision=20, scale=4), nullable=False),
        sa.Column("authorization_status", sa.String(length=32), nullable=False),
        sa.Column("authorization_body_sha256", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by", sa.String(length=64), nullable=False),
        sa.ForeignKeyConstraint(["workbench_account_id"], ["accounts.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("start_a_id", name="uq_risk_canary_start_a_id"),
    )


def downgrade() -> None:
    op.drop_table("risk_canary_start_a_authorizations")
