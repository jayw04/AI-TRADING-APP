"""SCAN-001 Production Validation Gate — increment (D): scheduled premarket outcomes backfill.

Daily at ~16:30 ET (after market close, weekdays), load today's premarket scan record
and back-fill its realized intraday outcomes (E/CM per candidate vs. the eligible-field
baseline). The outcomes are fetched from Alpaca daily bars (existing BarCache). Pure
back-fill, read-only, fail-soft, no order path.

(Activation = register this job in lifespan on backend rebuild; deferred per PR #241.)
"""

from __future__ import annotations

from datetime import date
from typing import TYPE_CHECKING

import structlog

if TYPE_CHECKING:
    from app.market_data.bar_cache import BarCache

logger = structlog.get_logger(__name__)


async def run_premarket_backfill_scheduled(
    bar_cache: BarCache,
    *,
    directory: str = "premarket_gate_evidence",
) -> dict | None:
    """Scheduled job entry point: load today's premarket record and back-fill outcomes.

    Fetches realized bars from BarCache (Alpaca), computes outcomes, and updates the
    record. Returns the updated record or None if today has no scan record (a no-scan
    market day). Logs completion; never raises into the scheduler.
    """
    try:
        from app.services.premarket_outcomes import backfill_evidence

        record = await backfill_evidence(
            bar_cache,
            directory=directory,
            asof=date.today()
        )
        if record is None:
            logger.info("premarket_backfill_scheduled_skipped", reason="no_scan_record_today")
            return None

        logger.info(
            "premarket_backfill_scheduled_complete",
            asof=record.get("asof"),
            status=record.get("outcome_status"),
            candidates_covered=record.get("outcomes", {}).get("coverage", {}).get("candidates_covered"),
        )
        return record
    except Exception:
        logger.exception("premarket_backfill_scheduled_failed")
        return None
