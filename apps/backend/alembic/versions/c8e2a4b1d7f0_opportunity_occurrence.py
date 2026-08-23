"""Durable opportunity_occurrence for Opportunity History (Phase 1.1).

Revision ID: c8e2a4b1d7f0
Revises: b2d8f4c6a901
Create Date: 2026-08-20

Identity is (screen_id, screen_version, candidate_date, family, symbol).
snapshot_sha256 / snapshot_generated_at are first-write provenance, not keys.
90-day JSON snapshot prune must not touch this table.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "c8e2a4b1d7f0"
down_revision: str | Sequence[str] | None = "b2d8f4c6a901"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "opportunity_occurrence",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("symbol", sa.String(length=16), nullable=False),
        sa.Column("candidate_date", sa.String(length=10), nullable=False),
        sa.Column("family", sa.String(length=32), nullable=False),
        sa.Column("horizon", sa.String(length=32), nullable=False),
        sa.Column("status_at_proposal", sa.String(length=128), nullable=False),
        sa.Column("proposal_price", sa.Float(), nullable=False),
        sa.Column("proposal_price_source", sa.String(length=64), nullable=False),
        sa.Column("adjustment_basis", sa.String(length=64), nullable=False),
        sa.Column("screen_id", sa.String(length=64), nullable=False),
        sa.Column("screen_version", sa.String(length=32), nullable=False),
        sa.Column("snapshot_sha256", sa.String(length=64), nullable=False),
        sa.Column("snapshot_generated_at", sa.String(length=64), nullable=False),
        sa.Column("reason_json", sa.Text(), nullable=False),
        sa.Column("features_json", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "screen_id",
            "screen_version",
            "candidate_date",
            "family",
            "symbol",
            name="uq_opportunity_occurrence_identity",
        ),
    )
    op.create_index(
        "ix_opportunity_occurrence_symbol",
        "opportunity_occurrence",
        ["symbol"],
    )
    op.create_index(
        "ix_opportunity_occurrence_candidate_date",
        "opportunity_occurrence",
        ["candidate_date"],
    )
    op.create_index(
        "ix_opportunity_occurrence_family",
        "opportunity_occurrence",
        ["family"],
    )


def downgrade() -> None:
    op.drop_index("ix_opportunity_occurrence_family", table_name="opportunity_occurrence")
    op.drop_index("ix_opportunity_occurrence_candidate_date", table_name="opportunity_occurrence")
    op.drop_index("ix_opportunity_occurrence_symbol", table_name="opportunity_occurrence")
    op.drop_table("opportunity_occurrence")
