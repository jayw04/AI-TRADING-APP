"""Quiver corporate-lobbying ingestion (EAD; LOBBY-001; ADR 0037).

Per ticker: fetch the deep lobbying history → aggregate to firm-quarters → detect spend-spikes →
idempotent upsert of ``lobby_spike`` events into the PIT Event Store, while accumulating the Phase-0
data-quality report across the universe. Read-only, off the order path; fail-soft per ticker (a bad
fetch is counted, never fatal), mirroring the gov-contract / congress siblings.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol

from app.altdata.events.store import EventStore
from app.altdata.quiver.lobbying import (
    LobbyDataQuality,
    SecurityResolver,
    build_lobby_events,
)


class _LobbySource(Protocol):
    """The slice of ``QuiverClient`` the ingest needs (so a fake stands in for tests)."""

    def lobbying_history(self, ticker: str) -> list[dict[str, Any]]: ...


@dataclass
class LobbyIngestReport:
    tickers_requested: int = 0
    events_built: int = 0
    eligible: int = 0            # research_eligible (ticker resolved via CAP-024)
    events_ingested: int = 0     # newly inserted (idempotent — re-runs add 0)
    fetch_failures: int = 0
    data_quality: LobbyDataQuality = field(default_factory=LobbyDataQuality)


def ingest_lobbying(
    client: _LobbySource, store: EventStore, tickers: list[str], *,
    security_master: SecurityResolver,
) -> LobbyIngestReport:
    """Ingest lobbying spend-spike events for ``tickers`` (per-ticker history path)."""
    report = LobbyIngestReport(tickers_requested=len(tickers))
    events = []
    for ticker in tickers:
        try:
            rows = client.lobbying_history(ticker)
        except Exception:  # noqa: BLE001 — fail-soft per ticker; counted, never fatal
            report.fetch_failures += 1
            continue
        evs, dq = build_lobby_events(ticker, rows, security_master=security_master)
        events.extend(evs)
        report.data_quality.merge(dq)
    report.events_built = len(events)
    report.eligible = sum(1 for e in events if e.research_eligible)
    report.events_ingested = store.upsert_events(events)
    return report
