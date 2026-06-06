"""P7 s4: strategies.authoring_method

P7 §4 — how a strategy was authored: "manual" (hand-written / registered by
code_path), "nl_generation" (single-shot AI), "nl_refinement" (P7b), "template"
(P8). Default "manual"; the authored-save endpoint sets "nl_generation".
server_default backfills existing rows.

Revision ID: a4c7e9b2f1d6
Revises: f1b8d3e6a2c7
Create Date: 2026-06-06

"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "a4c7e9b2f1d6"
down_revision: str | Sequence[str] | None = "f1b8d3e6a2c7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("strategies", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                "authoring_method",
                sa.String(16),
                nullable=False,
                server_default="manual",
            )
        )


def downgrade() -> None:
    with op.batch_alter_table("strategies", schema=None) as batch_op:
        batch_op.drop_column("authoring_method")
