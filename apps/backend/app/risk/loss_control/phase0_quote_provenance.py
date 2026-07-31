"""ADR-0043 Phase-0 WP9 — market-data quote provenance (offline).

Implements AMD-19: quote-source semantics are structured evidence (provider, feed,
venue scope, entitlement, condition codes, sequence, raw payload hash,
normalization version). A bare string such as \"IEX displayed spread\" is refused.

Does not submit orders or import the order path.
"""

from __future__ import annotations

import hashlib
import inspect
import json
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from app.risk.loss_control.phase0_contracts import TIER_D_DISPLAYED_SPREAD

QUOTE_PROVENANCE_SCHEMA_VERSION = 1
NORMALIZATION_VERSION = "phase0-quote-norm-v1"

REQUIRED_FIELDS: frozenset[str] = frozenset(
    {
        "provider",
        "feed_type",
        "venue_scope",
        "subscription_entitlement",
        "raw_payload_hash",
        "normalization_version",
    }
)


class VenueScope(StrEnum):
    VENUE = "venue"
    CONSOLIDATED = "consolidated"


class ProvenanceRefuseReason(StrEnum):
    STRING_ONLY_SOURCE = "STRING_ONLY_SOURCE"
    MISSING_REQUIRED_FIELDS = "MISSING_REQUIRED_FIELDS"
    INVALID_VENUE_SCOPE = "INVALID_VENUE_SCOPE"
    HASH_MISMATCH = "HASH_MISMATCH"
    EMPTY_PAYLOAD = "EMPTY_PAYLOAD"


@dataclass(frozen=True)
class QuoteProvenance:
    """First-class quote provenance (AMD-19)."""

    provider: str
    feed_type: str
    venue_scope: str
    subscription_entitlement: str
    raw_payload_hash: str
    normalization_version: str = NORMALIZATION_VERSION
    condition_codes: tuple[str, ...] = ()
    sequence_number: str | None = None
    schema_version: int = QUOTE_PROVENANCE_SCHEMA_VERSION

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "provider": self.provider,
            "feed_type": self.feed_type,
            "venue_scope": self.venue_scope,
            "subscription_entitlement": self.subscription_entitlement,
            "condition_codes": list(self.condition_codes),
            "sequence_number": self.sequence_number,
            "raw_payload_hash": self.raw_payload_hash,
            "normalization_version": self.normalization_version,
        }


@dataclass(frozen=True)
class ProvenancedQuote:
    """Quote prices plus structured provenance — never a free-text source alone."""

    symbol: str
    bid: str | None
    ask: str | None
    age_s: str | None
    provenance: QuoteProvenance
    evidence_tier_hint: str = TIER_D_DISPLAYED_SPREAD

    def as_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "bid": self.bid,
            "ask": self.ask,
            "age_s": self.age_s,
            "evidence_tier_hint": self.evidence_tier_hint,
            "provenance": self.provenance.as_dict(),
        }


@dataclass(frozen=True)
class ProvenanceValidation:
    accepted: bool
    reason: ProvenanceRefuseReason | None = None
    detail: str = ""
    quote: ProvenancedQuote | None = None


def hash_raw_payload(payload: bytes | str | dict[str, Any]) -> str:
    if isinstance(payload, dict):
        blob = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    elif isinstance(payload, str):
        blob = payload.encode("utf-8")
    else:
        blob = payload
    if not blob:
        raise ValueError("empty payload")
    return "sha256:" + hashlib.sha256(blob).hexdigest()


def validate_provenance_dict(data: dict[str, Any]) -> ProvenanceRefuseReason | None:
    if not isinstance(data, dict):
        return ProvenanceRefuseReason.MISSING_REQUIRED_FIELDS
    missing = REQUIRED_FIELDS - data.keys()
    if missing:
        return ProvenanceRefuseReason.MISSING_REQUIRED_FIELDS
    try:
        VenueScope(str(data["venue_scope"]))
    except ValueError:
        return ProvenanceRefuseReason.INVALID_VENUE_SCOPE
    if not str(data.get("raw_payload_hash") or "").startswith("sha256:"):
        return ProvenanceRefuseReason.HASH_MISMATCH
    if not str(data.get("normalization_version") or "").strip():
        return ProvenanceRefuseReason.MISSING_REQUIRED_FIELDS
    return None


def refuse_string_only_source(source: str) -> ProvenanceValidation:
    """AMD-19: free-text sources like 'IEX displayed spread' are not evidence."""
    return ProvenanceValidation(
        accepted=False,
        reason=ProvenanceRefuseReason.STRING_ONLY_SOURCE,
        detail=(
            f"quote source {source!r} is a string label; AMD-19 requires structured "
            "provenance fields (provider, feed_type, venue_scope, …)"
        ),
    )


def build_provenanced_quote(
    *,
    symbol: str,
    bid: str | None,
    ask: str | None,
    age_s: str | None,
    provider: str,
    feed_type: str,
    venue_scope: str,
    subscription_entitlement: str,
    raw_payload: bytes | str | dict[str, Any],
    condition_codes: tuple[str, ...] = (),
    sequence_number: str | None = None,
    normalization_version: str = NORMALIZATION_VERSION,
    evidence_tier_hint: str = TIER_D_DISPLAYED_SPREAD,
) -> ProvenanceValidation:
    try:
        payload_hash = hash_raw_payload(raw_payload)
    except ValueError:
        return ProvenanceValidation(
            False, ProvenanceRefuseReason.EMPTY_PAYLOAD, "raw payload empty"
        )
    prov = QuoteProvenance(
        provider=provider,
        feed_type=feed_type,
        venue_scope=venue_scope,
        subscription_entitlement=subscription_entitlement,
        raw_payload_hash=payload_hash,
        normalization_version=normalization_version,
        condition_codes=condition_codes,
        sequence_number=sequence_number,
    )
    err = validate_provenance_dict(prov.as_dict())
    if err is not None:
        return ProvenanceValidation(False, err, f"provenance invalid: {err}")
    quote = ProvenancedQuote(
        symbol=symbol,
        bid=bid,
        ask=ask,
        age_s=age_s,
        provenance=prov,
        evidence_tier_hint=evidence_tier_hint,
    )
    return ProvenanceValidation(True, quote=quote, detail="accepted")


def verify_payload_hash(
    provenance: QuoteProvenance,
    raw_payload: bytes | str | dict[str, Any],
) -> ProvenanceValidation:
    try:
        expected = hash_raw_payload(raw_payload)
    except ValueError:
        return ProvenanceValidation(
            False, ProvenanceRefuseReason.EMPTY_PAYLOAD, "raw payload empty"
        )
    if expected != provenance.raw_payload_hash:
        return ProvenanceValidation(
            False,
            ProvenanceRefuseReason.HASH_MISMATCH,
            "raw_payload_hash does not match payload",
        )
    return ProvenanceValidation(True, detail="hash verified")


def iex_displayed_spread_example(
    *,
    symbol: str,
    bid: str,
    ask: str,
    age_s: str,
    raw_payload: dict[str, Any],
    sequence_number: str | None = None,
) -> ProvenanceValidation:
    """Canonical construction for Alpaca IEX displayed quotes (Tier D diagnostic)."""
    return build_provenanced_quote(
        symbol=symbol,
        bid=bid,
        ask=ask,
        age_s=age_s,
        provider="alpaca",
        feed_type="iex",
        venue_scope=VenueScope.VENUE.value,
        subscription_entitlement="alpaca_iex_free",
        raw_payload=raw_payload,
        sequence_number=sequence_number,
        evidence_tier_hint=TIER_D_DISPLAYED_SPREAD,
    )


def assert_no_order_path_imports() -> None:
    import app.risk.loss_control.phase0_quote_provenance as mod

    src = inspect.getsource(mod)
    needles = [
        "from app." + "services.order_router",
        "import app." + "services.order_router",
        "from app." + "brokers",
        "import app." + "brokers",
        "from app." + "orders",
        "submit_" + "order(",
    ]
    for needle in needles:
        if needle in src:
            raise AssertionError(f"phase0_quote_provenance must not reference {needle}")


__all__ = [
    "NORMALIZATION_VERSION",
    "QUOTE_PROVENANCE_SCHEMA_VERSION",
    "REQUIRED_FIELDS",
    "ProvenanceRefuseReason",
    "ProvenanceValidation",
    "ProvenancedQuote",
    "QuoteProvenance",
    "VenueScope",
    "assert_no_order_path_imports",
    "build_provenanced_quote",
    "hash_raw_payload",
    "iex_displayed_spread_example",
    "refuse_string_only_source",
    "validate_provenance_dict",
    "verify_payload_hash",
]
