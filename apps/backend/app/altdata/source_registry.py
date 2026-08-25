"""Data Source Registry (EAD; ADR 0037 §6.4, DCAP-007).

A first-class entitlement/metadata record per external data source, populated **before** the
source is ingested. The ``commercial_use_allowed`` / ``derived_signal_allowed`` /
``cache_allowed`` flags are load-bearing: they gate what the Daily Opportunity Report may expose
externally (ADR 0037 §2.4 / §4.3). Read-only, off the order path.

v0 is an in-code registry (a DB table can replace it later without changing consumers).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

# Our ingestion contract for a source — distinct from the provider's publishing cadence.
#   LIVE                 — a scheduled job ingests on the stated cadence; staleness is a FAULT.
#   PAUSED_BY_GOVERNANCE — ingestion intentionally not scheduled pending a governed decision;
#                          staleness is EXPECTED and must not be reported as an outage.
#   UNEXPECTEDLY_STALE   — ingestion is meant to be running but has stopped; investigate.
INGESTION_STATUS = Literal["LIVE", "PAUSED_BY_GOVERNANCE", "UNEXPECTEDLY_STALE"]
INGESTION_STATUSES: frozenset[str] = frozenset(
    ("LIVE", "PAUSED_BY_GOVERNANCE", "UNEXPECTEDLY_STALE")
)


@dataclass(frozen=True)
class DataSource:
    source_id: str                     # DCAP id, e.g. "DCAP-007"
    source_name: str                   # the CorporateEvent.source value, e.g. "quiver"
    provider: str
    datasets_enabled: tuple[str, ...]
    license_type: str                  # "hobbyist" | "trader" | "commercial" | "public" | ...
    commercial_use_allowed: bool
    redistribution_allowed: bool
    cache_allowed: bool                # may we persist/cache the raw data (internal research)?
    derived_signal_allowed: bool       # may we expose derived scores/alerts/rankings?
    refresh_frequency: str
    known_latency: str
    point_in_time_supported: bool
    contact_owner: str
    renewal_date: str | None           # ISO date, or None for month-to-month
    # ``refresh_frequency`` above is the *provider's* publishing cadence. This is *our* ingestion
    # state, and the two diverge: a source can publish daily while we deliberately hold a frozen
    # corpus. Declaring it explicitly is the difference between a paused feed and a broken one.
    # **Deliberately has no default.** Defaulting to LIVE would let a new source inherit an
    # implicit "we ingest this daily" contract nobody wrote — exactly the provider-cadence-read-as-
    # ingestion-contract ambiguity this field exists to remove. Every source must say what it is.
    ingestion_status: INGESTION_STATUS
    # Required for any non-LIVE status (enforced below): a paused feed has to say who paused it
    # and what unpauses it, or the next reader cannot tell it from a broken one.
    ingestion_status_note: str = ""

    def __post_init__(self) -> None:
        if self.ingestion_status not in INGESTION_STATUSES:
            raise ValueError(
                f"{self.source_name}: ingestion_status {self.ingestion_status!r} is not one of "
                f"{sorted(INGESTION_STATUSES)}"
            )
        if self.ingestion_status != "LIVE" and not self.ingestion_status_note.strip():
            raise ValueError(
                f"{self.source_name}: ingestion_status {self.ingestion_status!r} requires an "
                "ingestion_status_note explaining why, and what would change it"
            )

    @property
    def customer_facing_allowed(self) -> bool:
        """A card built on this source may be shown externally ONLY if commercial + derived-signal
        rights are held (redistribution/cache are separately required for raw redistribution).
        Internal R&D use does not require these."""
        return self.commercial_use_allowed and self.derived_signal_allowed


# Quiver Quant — Hobbyist plan (verified 2026-07-05): No Commercial Use Rights on Hobbyist OR
# Trader; Commercial is contact-priced. Internal R&D only until a written Commercial license.
QUIVER_GOVCONTRACTS = DataSource(
    source_id="DCAP-007",
    source_name="quiver",
    provider="Quiver Quant",
    datasets_enabled=("government_contracts",),
    license_type="hobbyist",
    commercial_use_allowed=False,      # ADR 0037 §2.4 — blocks any external card
    redistribution_allowed=False,
    cache_allowed=True,                # internal research caching (the Event Store) is fine
    derived_signal_allowed=False,      # no external derived scores/rankings pre-Commercial
    refresh_frequency="daily",
    known_latency="disclosure lag ~days (uncalibrated — pending USAspending cross-check)",
    point_in_time_supported=True,
    contact_owner="Jay Wang (GlobalComplyAI, LLC)",
    renewal_date=None,                 # month-to-month
    ingestion_status="PAUSED_BY_GOVERNANCE",
    ingestion_status_note=(
        "Frozen research corpus, not a running feed. All 890,689 gov_contract_award rows landed "
        "in a single backfill on 2026-07-06 (max event_date 2026-07-03); no scheduled job, cron, "
        "or systemd timer ingests this source on the box, and none is expected to. GOVCONTRACT-001 "
        "closed INTERIM 'Insufficient Evidence' (coverage-limited), and the agreed path is to "
        "broaden small-cap coverage rather than relax gates — so ingestion stays paused until that "
        "data decision is made. gov_contract_award is additionally a rejected reference-only event "
        "label (ADR 0037 / check_reference_only_invariant.sh): it may be displayed as context but "
        "never enters ranking, sizing, or the order path. A growing gap between event_date and "
        "today is therefore EXPECTED for this source and is not an operational fault."
    ),
)

_REGISTRY: dict[str, DataSource] = {ds.source_name: ds for ds in (QUIVER_GOVCONTRACTS,)}


def get_source(source_name: str) -> DataSource | None:
    """Look up a registered source by its ``CorporateEvent.source`` value (e.g. ``"quiver"``)."""
    return _REGISTRY.get(source_name)


def all_sources() -> tuple[DataSource, ...]:
    return tuple(_REGISTRY.values())
