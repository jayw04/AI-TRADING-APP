"""P5.5 s1: trading_profiles table + per-user empty-profile backfill

Adds:
  - trading_profiles (one row per user; five JSON sections + timestamps).
  - A UNIQUE index on user_id. The model declares user_id with
    ``unique=True, index=True``, which SQLAlchemy emits as a SINGLE unique
    index (ix_trading_profiles_user_id) — NOT a separate UNIQUE constraint.
    This migration mirrors that exactly so create_all (tests) and the migration
    (prod) produce the same schema.

Data migration:
  - Insert an empty profile ({} for every JSON section) for each existing user.
    Users created AFTER this migration get their profile auto-created lazily by
    TradingProfileService.get(); the backfill is best-effort for the
    populated-DB case.

Revision ID: 9d2e7b3a1f5c
Revises: f2a7c1d9e4b6
Create Date: 2026-06-01

"""
from collections.abc import Sequence
from datetime import UTC, datetime

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision: str = "9d2e7b3a1f5c"
down_revision: str | Sequence[str] | None = "f2a7c1d9e4b6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "trading_profiles",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("watchlist_json", sa.JSON(), nullable=False),
        sa.Column("bias_criteria_json", sa.JSON(), nullable=False),
        sa.Column("bias_thresholds_json", sa.JSON(), nullable=False),
        sa.Column("session_preferences_json", sa.JSON(), nullable=False),
        sa.Column("risk_preferences_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name="fk_trading_profiles_user_id_users",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_trading_profiles"),
    )
    # Single UNIQUE index — matches the model's unique=True + index=True.
    op.create_index(
        "ix_trading_profiles_user_id",
        "trading_profiles",
        ["user_id"],
        unique=True,
    )

    # Backfill empty profiles for every existing user.
    conn = op.get_bind()
    now_iso = datetime.now(UTC).isoformat()
    users = conn.execute(sa.text("SELECT id FROM users")).fetchall()
    for u in users:
        conn.execute(
            sa.text(
                "INSERT INTO trading_profiles ("
                "user_id, watchlist_json, bias_criteria_json, "
                "bias_thresholds_json, session_preferences_json, "
                "risk_preferences_json, created_at, updated_at"
                ") VALUES ("
                ":uid, '{}', '{}', '{}', '{}', '{}', :ts, :ts"
                ")"
            ),
            {"uid": u.id, "ts": now_iso},
        )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index("ix_trading_profiles_user_id", table_name="trading_profiles")
    op.drop_table("trading_profiles")
