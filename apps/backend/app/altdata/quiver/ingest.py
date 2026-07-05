"""Quiver government-contract ingestion (EAD Phase 1; GOVCONTRACT-001; ADR 0037).

Fetch per-ticker award history → normalize → idempotent upsert into the PIT Event Store.
Read-only, off the order path. Fail-soft per ticker (a bad fetch is counted, never fatal),
mirroring ``app/altdata/sec/ingest.py``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol

from app.altdata.events.store import CorporateEvent, EventStore
from app.altdata.quiver.govcontracts import (
    DISCLOSURE_LAG_DAYS,
    SecurityResolver,
    govcontract_to_event,
)


class _GovContractSource(Protocol):
    """The slice of ``QuiverClient`` the ingest needs (so a fake stands in for tests)."""

    def govcontracts_history(self, ticker: str) -> list[dict[str, Any]]: ...


@dataclass
class GovContractIngestReport:
    tickers_requested: int = 0
    rows_seen: int = 0
    events_built: int = 0
    unresolved: int = 0          # built but not research_eligible (no security resolution)
    events_ingested: int = 0     # newly inserted (idempotent — re-runs add 0)
    fetch_failures: int = 0
    unresolved_reasons: dict[str, int] = field(default_factory=dict)


def ingest_govcontracts(
    client: _GovContractSource, store: EventStore, tickers: list[str], *,
    security_master: SecurityResolver, disclosure_lag_days: int = DISCLOSURE_LAG_DAYS,
) -> GovContractIngestReport:
    """Ingest government-contract awards for ``tickers``. Returns a report; the data-quality
    view (§4.0) is built on these counters + the store's ``coverage``/``latency_audit``."""
    report = GovContractIngestReport(tickers_requested=len(tickers))
    events: list[CorporateEvent] = []
    for ticker in tickers:
        try:
            rows = client.govcontracts_history(ticker)
        except Exception:  # noqa: BLE001 — fail-soft per ticker; counted, never fatal
            report.fetch_failures += 1
            continue
        report.rows_seen += len(rows)
        for row in rows:
            ev = govcontract_to_event(row, security_master=security_master,
                                      disclosure_lag_days=disclosure_lag_days)
            if ev is None:
                continue
            report.events_built += 1
            if not ev.research_eligible:
                report.unresolved += 1
                reason = ev.unresolved_reason or "unknown"
                report.unresolved_reasons[reason] = report.unresolved_reasons.get(reason, 0) + 1
            events.append(ev)
    report.events_ingested = store.upsert_events(events)
    return report
