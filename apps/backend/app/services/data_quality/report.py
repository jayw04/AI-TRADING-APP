"""EAD Data-Quality Report builder (ADR 0037 §4.0).

Composes the Event Store's EAD counters + latency audit + the Data Source Registry (license) +
(optionally) an ingest run's counters into one internal report: ingestion status · events by
dataset · normalized · unresolved-with-reason · missing-available_time · duplicates · mapping-
failure rate · late revisions · API failures · license status. Read-only, off the order path.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from app.altdata.events.store import EventStore
from app.altdata.source_registry import get_source


@dataclass(frozen=True)
class EADDataQualityReport:
    source_id: str
    source_name: str
    dataset: str
    license_type: str
    license_status: str
    customer_facing_allowed: bool
    events_total: int
    events_eligible: int
    events_ineligible: int
    missing_available_time: int
    revised: int
    raw_hash_coverage: float          # fraction of stored events carrying a raw_payload_hash
    mapping_failure_rate: float       # ineligible / total (proxy: gov-contract ineligible = unresolved)
    unresolved_reasons: dict[str, int]
    pit_violations: int               # available/event BEFORE — impossible (from latency audit)
    # ingest-run counters (present only when a report is passed in)
    ingest_rows_seen: int | None
    ingest_events_built: int | None
    ingest_events_ingested: int | None
    ingest_api_failures: int | None

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def build_govcontract_data_quality(
    store: EventStore, *, ingest_report: Any | None = None,
    source_name: str = "quiver", event_type: str = "gov_contract_award",
    dataset: str = "government_contracts",
) -> EADDataQualityReport:
    """Assemble the government-contract data-quality report from the store (and an optional
    ``GovContractIngestReport``)."""
    src = get_source(source_name)
    stats = store.ead_stats(event_type=event_type, source=source_name)
    lat = store.latency_audit(event_type=event_type)
    total = stats["n_total"]

    if src is not None:
        license_type = src.license_type
        customer_facing = src.customer_facing_allowed
        license_status = (
            f"{src.license_type}: commercial_use={src.commercial_use_allowed}, "
            f"derived_signal={src.derived_signal_allowed}, cache={src.cache_allowed} — "
            f"customer-facing {'ALLOWED' if customer_facing else 'BLOCKED'}"
        )
    else:
        license_type, customer_facing = "unregistered", False
        license_status = "UNREGISTERED SOURCE — populate the Data Source Registry before use"

    return EADDataQualityReport(
        source_id=src.source_id if src else "—",
        source_name=source_name,
        dataset=dataset,
        license_type=license_type,
        license_status=license_status,
        customer_facing_allowed=customer_facing,
        events_total=total,
        events_eligible=stats["n_eligible"],
        events_ineligible=stats["n_ineligible"],
        missing_available_time=stats["n_missing_available_time"],
        revised=stats["n_revised"],
        raw_hash_coverage=(stats["n_with_raw_hash"] / total) if total else 0.0,
        mapping_failure_rate=(stats["n_ineligible"] / total) if total else 0.0,
        unresolved_reasons=stats["unresolved_reasons"],
        pit_violations=int(lat["n_pit_violations"]),
        ingest_rows_seen=getattr(ingest_report, "rows_seen", None),
        ingest_events_built=getattr(ingest_report, "events_built", None),
        ingest_events_ingested=getattr(ingest_report, "events_ingested", None),
        ingest_api_failures=getattr(ingest_report, "fetch_failures", None),
    )


def render_report(r: EADDataQualityReport) -> str:
    """A plain-text internal dashboard rendering (no external exposure)."""
    lines = [
        f"EAD Data Quality — {r.source_id} {r.source_name}/{r.dataset}",
        f"  license        : {r.license_status}",
        f"  events total   : {r.events_total}",
        f"  eligible       : {r.events_eligible}",
        f"  ineligible     : {r.events_ineligible}  (mapping-failure rate {r.mapping_failure_rate:.1%})",
        f"  missing avail. : {r.missing_available_time}",
        f"  revised        : {r.revised}",
        f"  raw-hash cover : {r.raw_hash_coverage:.1%}",
        f"  PIT violations : {r.pit_violations}",
    ]
    if r.unresolved_reasons:
        lines.append("  unresolved by reason:")
        lines += [f"    {k:24s}: {v}" for k, v in sorted(r.unresolved_reasons.items())]
    if r.ingest_rows_seen is not None:
        lines.append(
            f"  last ingest    : rows_seen={r.ingest_rows_seen} built={r.ingest_events_built} "
            f"ingested={r.ingest_events_ingested} api_failures={r.ingest_api_failures}"
        )
    return "\n".join(lines)
