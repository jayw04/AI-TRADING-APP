"""SIP-CACHE-001 Implementation B3 — governed consumer registrations and demand leases.

Two tables, deliberately separate from ``sip_cache_records`` (what the plane *has*) — these hold
what the plane is *asked for* and by *whom*:

``sip_consumer_registrations``
    Governance, low churn. A row exists only because the versioned registry artifact
    (``config/sip_consumer_registry.v1.json``) named the consumer and an operator applied it. Never
    populated by discovery. Caps are ``NOT NULL`` because a registration without a cap is invalid
    (owner ruling, B3 Decision 2) — the schema enforces what the validator also enforces.

``sip_demand_leases``
    Operational, high churn. A lease is a bounded, expiring statement of *current execution/decision
    need* — never a selection universe, never "holdings only". ``max_age_s`` is the value **resolved
    from the consumer's governed execution policy** at publish time; the lease carries it and never
    originates it (B3 Decision 3).

⚠ Neither table carries a credential, feed selector, account id, or clock. A consumer cannot express
a trust input through demand any more than through the consumer API (B1 invariant).
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, ForeignKey, Index, Integer, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class SipConsumerRegistration(Base):
    __tablename__ = "sip_consumer_registrations"

    #: e.g. ``strategy:9`` / ``service:risk-reference``. From the artifact, never from a consumer.
    consumer_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    kind: Mapped[str] = mapped_column(String(16), nullable=False)
    strategy_id: Mapped[int | None] = mapped_column(
        ForeignKey("strategies.id"), nullable=True, index=True
    )
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)

    #: JSON list ⊆ ["SIP_EOD", "SIP_LIVE"].
    allowed_profiles: Mapped[str] = mapped_column(Text, nullable=False)
    #: JSON list ⊆ DemandReason values.
    allowed_reasons: Mapped[str] = mapped_column(Text, nullable=False)

    #: Required per consumer (B3 Decision 2). 0 means "profile not allowed" — never "unbounded".
    symbol_cap_eod: Mapped[int] = mapped_column(Integer, nullable=False)
    symbol_cap_live: Mapped[int] = mapped_column(Integer, nullable=False)

    #: Points at the consumer's governed execution policy that supplies the SIP_LIVE bound. The
    #: registration says the consumer MAY request LIVE; it never states the number.
    freshness_policy_ref: Mapped[str | None] = mapped_column(String(128), nullable=True)

    artifact_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    applied_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    applied_by: Mapped[str] = mapped_column(String(128), nullable=False)

    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked_by: Mapped[str | None] = mapped_column(String(128), nullable=True)
    revocation_reason: Mapped[str | None] = mapped_column(String(256), nullable=True)


class SipDemandLease(Base):
    __tablename__ = "sip_demand_leases"
    __table_args__ = (
        # The union scans ACTIVE leases per profile on every refresh.
        Index("ix_sip_demand_leases_profile_status", "profile", "status"),
        Index("ix_sip_demand_leases_consumer_profile", "consumer_id", "profile"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    consumer_id: Mapped[str] = mapped_column(
        ForeignKey("sip_consumer_registrations.consumer_id"), nullable=False
    )
    profile: Mapped[str] = mapped_column(String(16), nullable=False)

    #: JSON sorted list of normalized symbols.
    symbols: Mapped[str] = mapped_column(Text, nullable=False)
    #: JSON {symbol: DemandReason}.
    reasons: Mapped[str] = mapped_column(Text, nullable=False)

    #: LIVE only — policy-resolved. EOD leases carry NULL here and use trading-day tolerance.
    max_age_s: Mapped[Decimal | None] = mapped_column(Numeric(12, 3), nullable=True)
    #: EOD only.
    max_age_trading_days: Mapped[int | None] = mapped_column(Integer, nullable=True)

    effective_from: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    #: ACTIVE | SUPERSEDED | WITHDRAWN | REVOKED | EXPIRED
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    status_reason: Mapped[str | None] = mapped_column(String(256), nullable=True)
    status_changed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    superseded_by: Mapped[int | None] = mapped_column(
        ForeignKey("sip_demand_leases.id"), nullable=True
    )

    #: The audit row that recorded this request (REQUESTED). ADMITTED / SERVED rows reference the
    #: lease id, so REQUESTED ≠ ADMITTED ≠ SERVED is reconstructible from the chain.
    request_audit_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
