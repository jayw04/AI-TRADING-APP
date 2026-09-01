"""Typed results that cross the consumer boundary (SIP-CACHE-001 §7, §9, §10).

Two invariants shape these types:

**Provenance survives the boundary.** A consumer receives feed identity, both timestamps, the
entitlement identity and the credential fingerprint alongside the value — not a bare price. A number
whose origin cannot be reconstructed is not usable evidence downstream.

**A non-``PASS`` result carries no usable price.** ``STALE``, ``INCOMPLETE``, ``ENTITLEMENT_FAIL``
and ``ABSENT`` views are constructed with ``price``/``bid``/``ask`` set to ``None``, so a consumer
that ignores ``state`` gets nothing rather than a stale number it can mistake for current. There is
no code path that returns a real price alongside a non-``PASS`` state.

⛔ Nothing here exposes a secret. ``credential_identity_fingerprint`` is ``sha256(key)[:12]``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal

from app.market_data.sip.profiles import SipProfile
from app.market_data.sip.readiness import SipNotReadyError, SipReadinessState


@dataclass(frozen=True)
class SipDataView:
    """One consumer-visible observation, with its readiness verdict attached.

    Obtain via :mod:`app.market_data.sip.api`. Never constructed by consumers.
    """

    symbol: str
    profile: SipProfile
    state: SipReadinessState
    reason: str

    # Populated only when state is PASS. See the module docstring.
    price: Decimal | None = None
    bid: Decimal | None = None
    ask: Decimal | None = None

    # Provenance — present whenever an observation existed at all, even a stale one, so a consumer
    # can report *what* was stale rather than merely that something was.
    feed: str | None = None
    source_feed_identity: str | None = None
    source_timestamp: datetime | None = None
    received_at_utc: datetime | None = None
    entitlement_identity: str | None = None
    credential_identity_fingerprint: str | None = None
    quality_classification: str | None = None
    age_s: float | None = None

    @property
    def is_pass(self) -> bool:
        return self.state is SipReadinessState.PASS

    @property
    def feed_is_authentic(self) -> bool | None:
        """Whether the provider served the feed that was requested.

        ``None`` when no observation existed. A ``False`` is a substitution and the view will not be
        ``PASS``.
        """
        if self.feed is None or self.source_feed_identity is None:
            return None
        return self.feed == self.source_feed_identity

    def require_price(self) -> Decimal:
        """Return the price, or raise if this view is not ``PASS``.

        For consumers that must fail closed loudly. ⛔ There is deliberately no ``default=`` and no
        ``fallback_feed=`` parameter: a consumer that may legitimately proceed on another feed needs
        that fallback designed, registered and governed for it specifically (§10).
        """
        if not self.is_pass or self.price is None:
            raise SipNotReadyError(
                f"{self.symbol}: SIP {self.profile} is {self.state} ({self.reason}). "
                "No price is available. Failing closed."
            )
        return self.price


@dataclass(frozen=True)
class SipProfileStatus:
    """Operational status for one profile — the surface an activation gate queries."""

    profile: SipProfile
    readiness_state: SipReadinessState
    last_transition_reason: str
    evaluated_at: datetime

    last_successful_acquisition: datetime | None = None
    latest_observation: datetime | None = None
    observed_symbols: int = 0
    expected_symbols: int = 0
    coverage: float = 0.0
    age_s: float | None = None
    entitlement_state: str = "unknown"
    quality_counts: dict[str, int] = field(default_factory=dict)
    acquisition_failures: int = 0
    retry_count: int = 0


@dataclass(frozen=True)
class SipPlaneStatus:
    """Whole-plane status. Per-profile verdicts are never collapsed into one.

    ``producer_fingerprint`` is a non-secret reference to the designated producer so an operator can
    confirm *which* identity is in force without the package exposing a way to change it.
    """

    producer_fingerprint: str
    entitlement_identity: str
    cache_schema_version: int
    profiles: dict[str, SipProfileStatus] = field(default_factory=dict)
