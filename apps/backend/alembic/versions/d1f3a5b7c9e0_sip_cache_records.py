"""sip_cache_records — the shared SIP operational cache (SIP-CACHE-001 §2, §7).

Additive: creates one new table. Separate from the immutable MDQ evidence archive and from the
IEX bar cache. The provenance columns are NOT NULL by design — completeness is enforced at the
schema layer, not only in application code.

Revision ID: d1f3a5b7c9e0
Revises: c8e2a4b1d7f0
Create Date: 2026-09-01
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "d1f3a5b7c9e0"
down_revision = "c8e2a4b1d7f0"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "sip_cache_records",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("symbol", sa.String(length=16), nullable=False),
        sa.Column("profile", sa.String(length=16), nullable=False),
        sa.Column("trading_date", sa.Date(), nullable=False),
        sa.Column("session", sa.String(length=16), nullable=False),
        sa.Column("source_timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("received_at_utc", sa.DateTime(timezone=True), nullable=False),
        sa.Column("price", sa.Numeric(precision=18, scale=6), nullable=True),
        sa.Column("bid", sa.Numeric(precision=18, scale=6), nullable=True),
        sa.Column("ask", sa.Numeric(precision=18, scale=6), nullable=True),
        sa.Column("bid_size", sa.Numeric(precision=18, scale=6), nullable=True),
        sa.Column("ask_size", sa.Numeric(precision=18, scale=6), nullable=True),
        sa.Column("feed", sa.String(length=8), nullable=False),
        sa.Column("source_feed_identity", sa.String(length=8), nullable=False),
        sa.Column("provider", sa.String(length=16), nullable=False),
        sa.Column("entitlement_identity", sa.String(length=64), nullable=False),
        sa.Column("credential_identity_fingerprint", sa.String(length=16), nullable=False),
        sa.Column("cache_schema_version", sa.Integer(), nullable=False),
        sa.Column("quality_classification", sa.String(length=32), nullable=True),
        sa.UniqueConstraint(
            "symbol",
            "profile",
            "trading_date",
            name="uq_sip_cache_records_symbol_profile_date",
        ),
    )
    op.create_index(
        "ix_sip_cache_records_profile_source_ts",
        "sip_cache_records",
        ["profile", "source_timestamp"],
    )


def downgrade() -> None:
    op.drop_index("ix_sip_cache_records_profile_source_ts", table_name="sip_cache_records")
    op.drop_table("sip_cache_records")
