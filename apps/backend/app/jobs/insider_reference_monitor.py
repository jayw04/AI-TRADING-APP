"""Insider Reference Monitor — daily EDGAR Form 4 ingest (reference-only surface).

Schedules (ET, registered in lifespan behind ``WORKBENCH_INSIDER_MONITOR_ENABLED``, default OFF):
18:05 weekdays (post-close main pull) + 08:05 weekdays (premarket catch-up for late filings).
Weekly (or when stale/missing) the monitor universe is re-resolved from the PIT factor store and
persisted as an auditable manifest (plan §4.2a). Ingestion reuses the INSIDER-001 §1 stack
(``app.altdata.sec.ingest``) — accession-keyed upserts make re-runs no-ops.

Display-only: writes the PIT Event Store, never touches orders/positions/risk. ``insider_buy``
is ``rejected_reference_only``; account 3 (the owning identity) places no orders here.
Best-effort: any failure logs a one-line summary (the daily report greps it) and returns —
a monitor must never disturb the scheduler (the 7/8 range-outage lesson: leave loud, greppable
evidence in a persistent place, not only container stdout).
"""

from __future__ import annotations

import asyncio
import time
from datetime import UTC, datetime, timedelta

import structlog

from app.altdata.insider_monitor import (
    load_latest_manifest,
    manifest_is_fresh,
    resolve_monitor_universe,
    write_universe_manifest,
)

logger = structlog.get_logger(__name__)

_SINCE_OVERLAP_DAYS = 3  # re-cover weekend/late filings; upserts are idempotent by accession


def _ingest_sync(data_dir: str = "data") -> dict[str, object]:
    """The blocking ingest pass (run via ``asyncio.to_thread``): resolve/refresh the universe
    manifest, then ``ingest_form4`` over it into the PIT Event Store."""
    from app.altdata.events.store import EventStore
    from app.altdata.sec.client import EdgarClient
    from app.altdata.sec.ingest import ingest_form4

    today = datetime.now(UTC).date()

    manifest = load_latest_manifest(data_dir)
    if not manifest_is_fresh(manifest, today=today):
        try:
            from app.factor_data.store import FactorDataStore

            store = FactorDataStore(read_only=True)
            tickers, reason = resolve_monitor_universe(store, as_of=today)
        except Exception:  # noqa: BLE001 — degrade, never break (test #8)
            from app.altdata.insider_monitor import FALLBACK_UNIVERSE

            tickers, reason = list(FALLBACK_UNIVERSE), "fallback-134"
            logger.warning("insider_monitor_universe_fallback", reason="factor store open failed")
        write_universe_manifest(tickers, inclusion_reason=reason, as_of=today, data_dir=data_dir)
    else:
        tickers = [r["ticker"] for r in manifest["rows"]]  # type: ignore[index]

    client = EdgarClient()  # raises if SEC_EDGAR_USER_AGENT unset — caught by the entrypoint
    events_store = EventStore()
    try:
        since = (today - timedelta(days=_SINCE_OVERLAP_DAYS)).isoformat()
        report = ingest_form4(client, events_store, tickers, since=since)
        return {
            "universe": len(tickers),
            "ciks_resolved": report.ciks_resolved,
            "filings_seen": report.form4_filings_seen,
            "new_events": report.events_ingested,
            "fetch_failures": report.fetch_failures,
            "since": since,
        }
    finally:
        events_store.close()


async def run_insider_reference_ingest() -> None:
    """Scheduler entrypoint. Never raises."""
    started = time.monotonic()
    try:
        summary = await asyncio.to_thread(_ingest_sync)
        logger.info(
            "insider_reference_ingest_complete",
            elapsed_s=round(time.monotonic() - started, 1),
            **summary,
        )
    except Exception as exc:  # noqa: BLE001 — a monitor never disturbs the scheduler
        logger.error(
            "insider_reference_ingest_failed",
            error=str(exc),
            elapsed_s=round(time.monotonic() - started, 1),
        )
