"""SipRecord — one cached SIP observation, individually attributable (SIP-CACHE-001 §7).

Every record carries enough provenance to answer "where did this number come from, when was it
true, and under whose entitlement was it acquired" without consulting anything else.

Two fields exist specifically so a record can never be *silently misattributed*:

``source_feed_identity``
    The feed the provider reports having served, recorded independently of what was requested. A
    record claiming ``feed = sip`` whose ``source_feed_identity`` disagrees is a defect that must
    surface, not a value that is quietly accepted. The AST feed-pinning CI check
    (``check_marketdata_feed_pinning.sh``) proves the *request* named a feed explicitly; it cannot
    see a server-side substitution. This field can.

``entitlement_identity``
    Which entitlement served the observation. It is a per-record provenance field, **not** a set of
    parallel producers — it records what happened, it does not license acquisition from whichever
    identity happens to work (§7.1).

⛔ **No secret material.** The credential is recorded as ``sha256(key)[:12]`` only. The key and
secret never enter this module, the cache, the logs, or any evidence record.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal

from app.market_data.sip.profiles import SipProfile

#: Bumped whenever the persisted shape changes in a way readers must notice.
CACHE_SCHEMA_VERSION = 1

#: The only feed literal this plane ever writes. Never defaulted, never inferred.
SIP_FEED = "sip"

PROVIDER_ALPACA = "alpaca"


@dataclass(frozen=True)
class SipRecord:
    """One SIP observation for one symbol, with full provenance.

    ``source_timestamp`` is the **sole** basis for freshness. ``received_at_utc`` is diagnostic:
    a job that completed recently proves nothing about the age of the data it fetched.
    """

    symbol: str
    profile: SipProfile
    trading_date: date
    session: str

    #: Provider/exchange timestamp — the only clock freshness is measured against.
    source_timestamp: datetime
    #: When we received it. Diagnostic only; never a freshness input.
    received_at_utc: datetime

    price: Decimal | None = None
    bid: Decimal | None = None
    ask: Decimal | None = None
    bid_size: Decimal | None = None
    ask_size: Decimal | None = None

    feed: str = SIP_FEED
    source_feed_identity: str = SIP_FEED
    provider: str = PROVIDER_ALPACA
    entitlement_identity: str = ""
    credential_identity_fingerprint: str = ""
    cache_schema_version: int = CACHE_SCHEMA_VERSION
    quality_classification: str | None = None

    def __post_init__(self) -> None:
        # Provenance completeness is enforced here and again by NOT NULL at the schema layer.
        # A record that cannot say where it came from is not a cheaper record; it is a defect.
        if self.feed != SIP_FEED:
            raise ValueError(
                f"SipRecord.feed must be {SIP_FEED!r}, got {self.feed!r}. This plane never "
                "stores a non-SIP row; an IEX observation is not a SIP observation with a "
                "different label."
            )
        if not self.entitlement_identity:
            raise ValueError("SipRecord.entitlement_identity is required")
        if not self.credential_identity_fingerprint:
            raise ValueError("SipRecord.credential_identity_fingerprint is required")
        if self.source_timestamp.tzinfo is None:
            raise ValueError(
                "SipRecord.source_timestamp must be timezone-aware; a naive timestamp cannot be "
                "compared against a freshness tolerance without inventing a zone."
            )
        if self.received_at_utc.tzinfo is None:
            raise ValueError("SipRecord.received_at_utc must be timezone-aware")

    @property
    def feed_is_authentic(self) -> bool:
        """True when the provider served the feed we asked for.

        A False here is a substitution, not a rounding error — the caller must treat the record as
        unusable rather than downgrade it.
        """
        return self.source_feed_identity == self.feed
