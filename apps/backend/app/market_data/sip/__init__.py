"""SIP-CACHE-001 — the shared SIP operational data plane.

One designated paid SIP producer identity → shared Workbench operational cache → governed
consumers. Deliberately separate from the immutable MDQ evidence archive (which is research
evidence, not a live store) and from the IEX bar cache (which stays IEX).

Implementation A ships the producer/cache foundation only. Consumer APIs and the ADR-0055
reference-price integration are Implementation B, gated on their own review.
"""

from app.market_data.sip.identity import PRODUCER, ProducerIdentityError
from app.market_data.sip.profiles import SipProfile
from app.market_data.sip.readiness import (
    SipNotReadyError,
    SipReadiness,
    SipReadinessState,
)
from app.market_data.sip.schema import CACHE_SCHEMA_VERSION, SipRecord

__all__ = [
    "CACHE_SCHEMA_VERSION",
    "PRODUCER",
    "ProducerIdentityError",
    "SipNotReadyError",
    "SipProfile",
    "SipReadiness",
    "SipReadinessState",
    "SipRecord",
]
