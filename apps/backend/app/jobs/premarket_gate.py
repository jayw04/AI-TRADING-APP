"""SCAN-001 Production Validation Gate — scheduled forward-evidence jobs.

The gate accrues *forward* evidence (gate plan §0; ADR 0024): each trading day the
~09:25 ET premarket scan persists today's candidate set + the eligible field, and the
~16:30 ET back-fill attaches each name's realized intraday outcome. Once ~40 days of
records exist, ``premarket_verdict.run_gate_verdict`` reads them and returns a
TRANSFERS / DOES-NOT-TRANSFER / INSUFFICIENT verdict.

Both jobs are read-only / advisory — no order path, no broker writes — and **fail-soft**:
a bad day (no store, no gappers file, an Alpaca miss) is logged and skipped, never
allowed to disturb the scheduler. The scan persists; the back-fill is best-effort and a
no-scan day is a clean no-op.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any
from zoneinfo import ZoneInfo

import structlog

from app.services.premarket_evidence import record_premarket_scan
from app.services.premarket_outcomes import backfill_evidence

logger = structlog.get_logger(__name__)

# The scan/back-fill "asof" is the current Eastern trading day. The scheduler itself is
# already America/New_York, but compute the date explicitly so the job is correct
# regardless of how it is invoked (tests, a manual run).
_ET = ZoneInfo("America/New_York")


def _today_et() -> date:
    return datetime.now(_ET).date()


async def run_premarket_scan_job(*, factor_store: Any, directory: str) -> None:
    """~09:25 ET: run the live premarket scan for today and persist its evidence
    record (candidate set + eligible field, outcomes still ``pending``)."""
    asof = _today_et()
    try:
        record = record_premarket_scan(factor_store, asof=asof, directory=directory)
        logger.info(
            "premarket_gate_scan_recorded",
            asof=str(asof),
            candidates=len(record.get("candidates", [])),
            eligible=len(record.get("eligible", [])),
            path=record.get("_path"),
        )
    except Exception:  # noqa: BLE001 — advisory job must never break the scheduler
        logger.exception("premarket_gate_scan_failed", asof=str(asof))


async def run_premarket_backfill_job(*, bar_cache: Any, directory: str) -> None:
    """~16:30 ET: attach realized intraday outcomes to today's record. A no-scan day
    (no record persisted this morning) is a clean no-op."""
    asof = _today_et()
    try:
        record = await backfill_evidence(bar_cache, directory=directory, asof=asof)
        if record is None:
            logger.info("premarket_gate_backfill_skipped_no_record", asof=str(asof))
            return
        logger.info(
            "premarket_gate_backfill_done",
            asof=str(asof),
            outcome_status=record.get("outcome_status"),
            coverage=record.get("outcomes", {}).get("coverage"),
            edge_E=record.get("outcomes", {}).get("edge_E"),
        )
    except Exception:  # noqa: BLE001 — advisory job must never break the scheduler
        logger.exception("premarket_gate_backfill_failed", asof=str(asof))
