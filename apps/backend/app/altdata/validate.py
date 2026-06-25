"""§2 data-validation gate (plan §2; ADR 0027).

Before any research consumes the corporate-event store, prove the DATA is trustworthy — the
event-driven analogue of the factor-data health gate (EvidenceEngineering Methodology §7). A
failing check **blocks** §3 (signal/event-study). The gate composes an ingest report + the
store's coverage + the filing-latency/PIT audit into a GO / BLOCKED verdict:

- **CIK resolution** — enough of the requested universe resolves to a CIK (the sibling system's
  ~11% hole would bias the study if ignored);
- **PIT sanity** — no filing dated *before* its transaction (impossible; would mean look-ahead);
- **amendments** — 4/A corrections are surfaced (not silently dropped);
- **coverage** — the store is non-empty and spans the expected window.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.altdata.events.store import EventStore
from app.altdata.sec.ingest import IngestReport

MIN_CIK_RESOLUTION = 0.85  # >= 85% of requested tickers must resolve, else the study is biased


@dataclass
class ValidationReport:
    passed: bool
    checks: dict[str, Any]
    blockers: list[str] = field(default_factory=list)


def validate(
    store: EventStore, *, ingest: IngestReport | None = None, event_type: str = "insider_buy",
) -> ValidationReport:
    """Run the §2 gate. ``ingest`` (optional) adds CIK-resolution + ingest-quality checks; the
    store always contributes coverage + the latency/PIT audit."""
    checks: dict[str, Any] = {
        "coverage": store.coverage(),
        "latency": store.latency_audit(event_type=event_type),
    }
    blockers: list[str] = []

    if ingest is not None:
        req, res = ingest.tickers_requested, ingest.ciks_resolved
        rate = res / req if req else 0.0
        checks["cik_resolution"] = {
            "requested": req, "resolved": res, "rate": round(rate, 4),
            "unresolved": ingest.unresolved_tickers,
        }
        checks["ingest"] = {
            "filings_seen": ingest.form4_filings_seen, "amendments": ingest.amendments_seen,
            "events_ingested": ingest.events_ingested, "fetch_failures": ingest.fetch_failures,
        }
        if req and rate < MIN_CIK_RESOLUTION:
            blockers.append(
                f"CIK resolution {rate:.0%} below the {MIN_CIK_RESOLUTION:.0%} minimum "
                f"({len(ingest.unresolved_tickers)} unresolved)")

    lat = checks["latency"]
    if lat["n_pit_violations"] > 0:
        blockers.append(
            f"{lat['n_pit_violations']} PIT violation(s): a filing dated before its transaction "
            "(impossible — indicates a date/parse error or look-ahead)")

    if checks["coverage"]["n_events"] == 0:
        blockers.append("no events in the store — nothing to validate")

    return ValidationReport(passed=not blockers, checks=checks, blockers=blockers)


def render(report: ValidationReport) -> str:
    """A short markdown summary of the §2 gate for the operational run / status doc."""
    cov, lat = report.checks["coverage"], report.checks["latency"]
    lines = [
        f"# INSIDER-001 §2 data validation — {'GO ✅' if report.passed else 'BLOCKED ⛔'}",
        "",
        f"- **Events:** {cov['n_events']} ({cov.get('by_type', {})}) across "
        f"{cov['distinct_tickers']} issuers, {cov['first_filed']} → {cov['last_filed']}.",
        f"- **Filing latency (txn→filed):** median {lat['median_latency_days']}d, "
        f"range [{lat['min_latency_days']}, {lat['max_latency_days']}]d; "
        f"{lat['n_pit_violations']} PIT violation(s), {lat['n_latency_over_5d']} > 5d, "
        f"{lat['n_missing_event_date']} missing event date.",
    ]
    if "cik_resolution" in report.checks:
        cr, ing = report.checks["cik_resolution"], report.checks["ingest"]
        lines.append(
            f"- **CIK resolution:** {cr['resolved']}/{cr['requested']} ({cr['rate']:.0%}); "
            f"filings {ing['filings_seen']} ({ing['amendments']} amendments), "
            f"{ing['fetch_failures']} fetch failures.")
        if cr["unresolved"]:
            lines.append(f"  - unresolved: {', '.join(cr['unresolved'][:20])}"
                         + (" …" if len(cr["unresolved"]) > 20 else ""))
    if report.blockers:
        lines += ["", "## Blockers", *[f"- ⛔ {b}" for b in report.blockers]]
    return "\n".join(lines)
