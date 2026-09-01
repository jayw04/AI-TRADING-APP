"""SipCacheRecord — the shared SIP operational cache (SIP-CACHE-001 §2, §7).

One row per (symbol, profile, trading_date). ``SIP_EOD`` rows are written once per completed
session; ``SIP_LIVE`` rows are updated in place with the newest observation for the current session,
which keeps the table bounded while remaining durable across restart.

⚠ **This is not the MDQ evidence archive.** The immutable research corpus under
``/opt/workbench/data/mdq_capture`` is sealed, adjudicated and off-limits to live consumers
(ATP v1.0.3 §12). This table is the operational plane: refreshed, retained on a bounded window, and
disposable. A gap here is repaired by a subsequent refresh, never by reading the archive.

⚠ **This is not the IEX bar cache relabelled.** ``/app/bars_cache`` stays IEX and untouched. The
provenance columns below exist so the two planes can never be confused: every row states its feed,
the feed the provider reported serving, both timestamps, and the entitlement identity under which it
was acquired.

The provenance columns are ``NOT NULL`` deliberately — completeness is enforced at the schema layer,
not only in application code.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    Date,
    DateTime,
    Index,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class SipCacheRecord(Base):
    __tablename__ = "sip_cache_records"
    __table_args__ = (
        UniqueConstraint(
            "symbol",
            "profile",
            "trading_date",
            name="uq_sip_cache_records_symbol_profile_date",
        ),
        # Readiness scans "newest observation for this profile" on every evaluation.
        Index("ix_sip_cache_records_profile_source_ts", "profile", "source_timestamp"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)

    symbol: Mapped[str] = mapped_column(String(16), nullable=False)
    profile: Mapped[str] = mapped_column(String(16), nullable=False)
    trading_date: Mapped[date] = mapped_column(Date, nullable=False)
    session: Mapped[str] = mapped_column(String(16), nullable=False)

    # Freshness is measured from source_timestamp and nothing else.
    source_timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    received_at_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    price: Mapped[Decimal | None] = mapped_column(Numeric(18, 6), nullable=True)
    bid: Mapped[Decimal | None] = mapped_column(Numeric(18, 6), nullable=True)
    ask: Mapped[Decimal | None] = mapped_column(Numeric(18, 6), nullable=True)
    bid_size: Mapped[Decimal | None] = mapped_column(Numeric(18, 6), nullable=True)
    ask_size: Mapped[Decimal | None] = mapped_column(Numeric(18, 6), nullable=True)

    # --- provenance: all NOT NULL, all required to reconstruct the observation's origin ---
    feed: Mapped[str] = mapped_column(String(8), nullable=False)
    source_feed_identity: Mapped[str] = mapped_column(String(8), nullable=False)
    provider: Mapped[str] = mapped_column(String(16), nullable=False)
    entitlement_identity: Mapped[str] = mapped_column(String(64), nullable=False)
    credential_identity_fingerprint: Mapped[str] = mapped_column(String(16), nullable=False)
    cache_schema_version: Mapped[int] = mapped_column(Integer, nullable=False)
    quality_classification: Mapped[str | None] = mapped_column(String(32), nullable=True)
