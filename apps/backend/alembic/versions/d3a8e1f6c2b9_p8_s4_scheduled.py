"""P8 s4: scheduled scanning

P8 §4 — `scanner_definitions.scheduled` (a saved scan opts into the pre-market
cron) + `scanner_runs.trigger` (manual | scheduled; only scheduled runs feed
the Opportunities view).

Revision ID: d3a8e1f6c2b9
Revises: c2f5a8d31e7b
Create Date: 2026-06-07

"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "d3a8e1f6c2b9"
down_revision: str | Sequence[str] | None = "c2f5a8d31e7b"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("scanner_definitions") as batch:
        batch.add_column(
            sa.Column(
                "scheduled",
                sa.Boolean(),
                nullable=False,
                server_default=sa.false(),
            )
        )
    with op.batch_alter_table("scanner_runs") as batch:
        batch.add_column(
            sa.Column(
                "trigger",
                sa.String(12),
                nullable=False,
                server_default="manual",
            )
        )


def downgrade() -> None:
    with op.batch_alter_table("scanner_runs") as batch:
        batch.drop_column("trigger")
    with op.batch_alter_table("scanner_definitions") as batch:
        batch.drop_column("scheduled")
