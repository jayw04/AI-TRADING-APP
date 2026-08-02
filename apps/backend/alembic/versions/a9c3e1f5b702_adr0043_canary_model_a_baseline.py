"""ADR-0043 canary Model A — risk_canary_session_baselines (Start A authoritative).

Does not modify risk_session_baselines shadow rows.

Revision ID: a9c3e1f5b702
Revises: c1f4a7d2e8b3
Create Date: 2026-07-31
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "a9c3e1f5b702"
down_revision: str | Sequence[str] | None = "c1f4a7d2e8b3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "risk_canary_session_baselines",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("account_id", sa.Integer(), nullable=False),
        sa.Column("broker_account_id", sa.String(length=64), nullable=False),
        sa.Column("market_session_date", sa.String(length=10), nullable=False),
        sa.Column("session_timezone", sa.String(length=32), nullable=False),
        sa.Column("baseline_equity", sa.Numeric(precision=28, scale=12), nullable=False),
        sa.Column("baseline_equity_raw", sa.String(length=64), nullable=False),
        sa.Column("baseline_equity_canonical_4dp", sa.String(length=64), nullable=False),
        sa.Column("baseline_source", sa.String(length=64), nullable=False),
        sa.Column("broker_response_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("local_receipt_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("persisted_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("raw_response_json", sa.Text(), nullable=False),
        sa.Column("raw_response_sha256", sa.String(length=64), nullable=False),
        sa.Column("projection_json", sa.Text(), nullable=False),
        sa.Column("projection_sha256", sa.String(length=64), nullable=False),
        sa.Column("raw_object_ref", sa.String(length=256), nullable=True),
        sa.Column("design_version", sa.String(length=128), nullable=False),
        sa.Column("freeze_id", sa.String(length=128), nullable=False),
        sa.Column("start_a_id", sa.String(length=128), nullable=False),
        sa.Column("freeze_body_sha256", sa.String(length=64), nullable=False),
        sa.Column("configuration_digest", sa.String(length=64), nullable=False),
        sa.Column("image_digest", sa.String(length=128), nullable=False),
        sa.Column("commit_sha", sa.String(length=64), nullable=False),
        sa.Column("applicable_daily_loss_limit", sa.Numeric(precision=20, scale=4), nullable=False),
        sa.Column("capture_mechanism_version", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.ForeignKeyConstraint(["account_id"], ["accounts.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "account_id",
            "market_session_date",
            "design_version",
            "freeze_id",
            name="uq_risk_canary_session_baseline_identity",
        ),
    )


def downgrade() -> None:
    op.drop_table("risk_canary_session_baselines")
