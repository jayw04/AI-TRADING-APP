"""Quiver congressional-trading ingestion (EAD; CONGRESS-001; ADR 0037).

Fetch congressional trades → normalize → idempotent upsert into the PIT Event Store (no new
store). Read-only, off the order path. Fail-soft per ticker (a bad fetch is counted, never
fatal), mirroring ``app/altdata/quiver/ingest.py`` (the gov-contract sibling).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol

from app.altdata.events.store import CorporateEvent, EventStore
from app.altdata.quiver.congresstrading import SecurityResolver, congress_to_event


class _CongressSource(Protocol):
    """The slice of ``QuiverClient`` the per-ticker ingest needs (so a fake stands in for tests)."""

    def congresstrading_history(self, ticker: str) -> list[dict[str, Any]]: ...


class _CongressLiveSource(Protocol):
    """The slice of ``QuiverClient`` the bulk ingest needs."""

    def congresstrading_live(self) -> list[dict[str, Any]]: ...


@dataclass
class CongressIngestReport:
    tickers_requested: int = 0
    rows_seen: int = 0
    events_built: int = 0
    unresolved: int = 0          # built but not research_eligible (no security resolution)
    events_ingested: int = 0     # newly inserted (idempotent — re-runs add 0)
    fetch_failures: int = 0
    buys: int = 0                # directional breakdown (Purchase-only is the primary)
    sells: int = 0
    non_directional: int = 0     # Exchange / transfers (direction None)
    unresolved_reasons: dict[str, int] = field(default_factory=dict)


def _tally(report: CongressIngestReport, ev: CorporateEvent) -> None:
    report.events_built += 1
    if not ev.research_eligible:
        report.unresolved += 1
        reason = ev.unresolved_reason or "unknown"
        report.unresolved_reasons[reason] = report.unresolved_reasons.get(reason, 0) + 1
    direction = (ev.payload or {}).get("direction")
    if direction == "buy":
        report.buys += 1
    elif direction == "sell":
        report.sells += 1
    else:
        report.non_directional += 1


def ingest_congress(
    client: _CongressSource, store: EventStore, tickers: list[str], *,
    security_master: SecurityResolver,
) -> CongressIngestReport:
    """Ingest congressional trades for ``tickers`` (per-ticker history path)."""
    report = CongressIngestReport(tickers_requested=len(tickers))
    events: list[CorporateEvent] = []
    for ticker in tickers:
        try:
            rows = client.congresstrading_history(ticker)
        except Exception:  # noqa: BLE001 — fail-soft per ticker; counted, never fatal
            report.fetch_failures += 1
            continue
        report.rows_seen += len(rows)
        for row in rows:
            ev = congress_to_event(row, security_master=security_master)
            if ev is None:
                continue
            _tally(report, ev)
            events.append(ev)
    report.events_ingested = store.upsert_events(events)
    return report


def ingest_congress_bulk(
    client: _CongressLiveSource, store: EventStore, *,
    security_master: SecurityResolver,
) -> CongressIngestReport:
    """Ingest recent congressional trades from the live bulk endpoint in one call — the daily-
    incremental path. Idempotent (same deterministic ids ⇒ no double-count)."""
    report = CongressIngestReport(tickers_requested=0)
    try:
        rows = client.congresstrading_live()
    except Exception:  # noqa: BLE001 — a bulk-fetch failure is counted, never fatal
        report.fetch_failures += 1
        return report
    report.rows_seen = len(rows)
    events: list[CorporateEvent] = []
    for row in rows:
        ev = congress_to_event(row, security_master=security_master)
        if ev is not None:
            _tally(report, ev)
            events.append(ev)
    report.events_ingested = store.upsert_events(events)
    return report
