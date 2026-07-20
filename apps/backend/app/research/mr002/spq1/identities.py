"""Frozen-input identity registry (Phase-0 SIG-01/18/28/30/31; census areas 3/11).

Every required input and governing artifact is bound by SHA-256 and verified BEFORE any
computation. A mismatch refuses fail-closed — no default identity, no "best available"
fallback. Producer code version, rule-census, owner-rulings, and schema identities are bound
so a stale producer or governing document cannot silently produce a candidate.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass

from . import (
    PHASE0_CENSUS_SHA256,
    PHASE0_OWNER_RULINGS_SHA256,
    PHASE0_SCHEMA_SHA256,
    PRODUCER_CODE_VERSION,
)
from .refusals import refuse

# The twelve required frozen-input identity slots (census §3 "Required identities").
REQUIRED_IDENTITY_KEYS: tuple[str, ...] = (
    "registered_exchange_calendar",
    "spy_total_return_series",
    "sector_etf_source_series",
    "sector_etf_proxy_mapping_table",
    "price_return_adjustment_policy",
    "pit_sector_source",
    "pit_identity_registry",
    "eligibility_evidence_sources",
    "producer_code_version",
    "rule_census_identity",
    "owner_rulings_identity",
    "schema_identity",
)

# Governing identities that are fixed constants of the closed Phase-0 package.
GOVERNING_IDENTITIES: dict[str, str] = {
    "producer_code_version": PRODUCER_CODE_VERSION,
    "rule_census_identity": PHASE0_CENSUS_SHA256,
    "owner_rulings_identity": PHASE0_OWNER_RULINGS_SHA256,
    "schema_identity": PHASE0_SCHEMA_SHA256,
}


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def canonical_sha256(obj: object) -> str:
    """SHA-256 of the canonical JSON encoding (sort_keys, compact) — deterministic."""
    return sha256_hex(json.dumps(obj, sort_keys=True, separators=(",", ":")).encode("utf-8"))


@dataclass(frozen=True)
class InputIdentityRegistry:
    """Expected identities for a production run. ``verify`` fails closed on any mismatch."""

    identities: dict[str, str]

    def __post_init__(self) -> None:
        missing = [k for k in REQUIRED_IDENTITY_KEYS if k not in self.identities]
        if missing:
            raise refuse(
                "REFUSED_CODE_OR_DATA_IDENTITY:SIGNAL_INPUT_IDENTITY_MISMATCH",
                f"missing required identity slots: {missing}",
            )
        for key, expected in GOVERNING_IDENTITIES.items():
            if self.identities[key] != expected:
                raise refuse(
                    "REFUSED_CODE_OR_DATA_IDENTITY:SIGNAL_INPUT_IDENTITY_MISMATCH",
                    f"governing identity {key} mismatch: "
                    f"expected {expected} got {self.identities[key]}",
                )

    def verify(self, key: str, observed: str) -> None:
        """Verify an observed input identity against the registered expectation."""
        if key not in self.identities:
            raise refuse(
                "REFUSED_CODE_OR_DATA_IDENTITY:SIGNAL_INPUT_IDENTITY_MISMATCH",
                f"identity slot not registered: {key}",
            )
        if self.identities[key] != observed:
            raise refuse(
                "REFUSED_CODE_OR_DATA_IDENTITY:SIGNAL_INPUT_IDENTITY_MISMATCH",
                f"input identity {key} mismatch: expected {self.identities[key]} got {observed}",
            )

    def as_dict(self) -> dict[str, str]:
        return dict(self.identities)
