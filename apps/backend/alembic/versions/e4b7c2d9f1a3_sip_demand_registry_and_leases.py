"""sip_consumer_registrations + sip_demand_leases — SIP-CACHE-001 Implementation B3.

Additive: two new tables, no data migration, no change to existing tables. The registry is populated
only by the governed apply script from the versioned artifact; this migration creates it empty.

Revision ID: e4b7c2d9f1a3
Revises: d1f3a5b7c9e0
Create Date: 2026-09-02
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "e4b7c2d9f1a3"
down_revision = "d1f3a5b7c9e0"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "sip_consumer_registrations",
        sa.Column("consumer_id", sa.String(length=64), primary_key=True),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("strategy_id", sa.Integer(), sa.ForeignKey("strategies.id"), nullable=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("allowed_profiles", sa.Text(), nullable=False),
        sa.Column("allowed_reasons", sa.Text(), nullable=False),
        sa.Column("symbol_cap_eod", sa.Integer(), nullable=False),
        sa.Column("symbol_cap_live", sa.Integer(), nullable=False),
        sa.Column("freshness_policy_ref", sa.String(length=128), nullable=True),
        sa.Column("artifact_sha256", sa.String(length=64), nullable=False),
        sa.Column("applied_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("applied_by", sa.String(length=128), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_by", sa.String(length=128), nullable=True),
        sa.Column("revocation_reason", sa.String(length=256), nullable=True),
    )
    op.create_index(
        "ix_sip_consumer_registrations_strategy_id",
        "sip_consumer_registrations",
        ["strategy_id"],
    )
    op.create_index(
        "ix_sip_consumer_registrations_user_id",
        "sip_consumer_registrations",
        ["user_id"],
    )

    op.create_table(
        "sip_demand_leases",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "consumer_id",
            sa.String(length=64),
            sa.ForeignKey("sip_consumer_registrations.consumer_id"),
            nullable=False,
        ),
        sa.Column("profile", sa.String(length=16), nullable=False),
        sa.Column("symbols", sa.Text(), nullable=False),
        sa.Column("reasons", sa.Text(), nullable=False),
        sa.Column("max_age_s", sa.Numeric(precision=12, scale=3), nullable=True),
        sa.Column("max_age_trading_days", sa.Integer(), nullable=True),
        sa.Column("effective_from", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("status_reason", sa.String(length=256), nullable=True),
        sa.Column("status_changed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "superseded_by", sa.Integer(), sa.ForeignKey("sip_demand_leases.id"), nullable=True
        ),
        sa.Column("request_audit_id", sa.Integer(), nullable=True),
    )
    op.create_index(
        "ix_sip_demand_leases_profile_status", "sip_demand_leases", ["profile", "status"]
    )
    op.create_index(
        "ix_sip_demand_leases_consumer_profile", "sip_demand_leases", ["consumer_id", "profile"]
    )


def downgrade() -> None:
    op.drop_index("ix_sip_demand_leases_consumer_profile", table_name="sip_demand_leases")
    op.drop_index("ix_sip_demand_leases_profile_status", table_name="sip_demand_leases")
    op.drop_table("sip_demand_leases")
    op.drop_index("ix_sip_consumer_registrations_user_id", table_name="sip_consumer_registrations")
    op.drop_index(
        "ix_sip_consumer_registrations_strategy_id", table_name="sip_consumer_registrations"
    )
    op.drop_table("sip_consumer_registrations")
