"""P5.5 s2: morning_briefs table

Additive only — no backfill. Briefs are generated forward (scheduled mon-fri
09:00 ET, or on-demand); there is nothing to seed for existing users.

Revision ID: b3f8c2d1e9a7
Revises: 9d2e7b3a1f5c
Create Date: 2026-06-02

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision: str = "b3f8c2d1e9a7"
down_revision: str | Sequence[str] | None = "9d2e7b3a1f5c"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "morning_briefs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("brief_date", sa.Date(), nullable=False),
        sa.Column("symbols_json", sa.JSON(), nullable=False),
        sa.Column("overall_note", sa.Text(), nullable=False),
        sa.Column("agent_used", sa.Boolean(), nullable=False),
        sa.Column("trigger", sa.String(length=32), nullable=False),
        sa.Column("generated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name="fk_morning_briefs_user_id_users",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_morning_briefs"),
        sa.UniqueConstraint(
            "user_id", "brief_date", name="uq_morning_briefs_user_id_brief_date"
        ),
    )
    op.create_index("ix_morning_briefs_user_id", "morning_briefs", ["user_id"])


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index("ix_morning_briefs_user_id", table_name="morning_briefs")
    op.drop_table("morning_briefs")
