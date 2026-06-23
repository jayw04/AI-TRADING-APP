"""SCAN-001 Production Validation Gate — increment (C): scheduled premarket scan.

Daily at ~09:25 ET (weekdays), run the live premarket gappers scan and persist the
Candidate Report as a dated evidence record. The record is immutable until back-fill
(increment D, ~16:30). Read-only, fail-soft, no order path.

(Activation = register this job in lifespan on backend rebuild; deferred per PR #241.)
"""

from __future__ import annotations

from datetime import date
from typing import TYPE_CHECKING

import structlog

if TYPE_CHECKING:
    from app.factor_data.store import FactorDataStore
    from app.market_data.bar_cache import BarCache

logger = structlog.get_logger(__name__)


async def run_premarket_scan_scheduled(
    bar_cache: BarCache,
    factor_store: FactorDataStore | None,
    *,
    directory: str = "premarket_gate_evidence",
) -> dict | None:
    """Scheduled job entry point: run the premarket scan for today and persist the record.

    Returns the persisted record or None if scanning is unavailable (store not provisioned,
    gappers file missing/stale, etc.). Logs completion; never raises into the scheduler.
    """
    if factor_store is None:
        logger.warning(
            "premarket_scan_scheduled_skipped",
            reason="factor_store_unavailable"
        )
        return None

    try:
        from app.services.premarket_evidence import record_premarket_scan

        record = record_premarket_scan(
            factor_store.con,
            asof=date.today(),
            directory=directory,
            top_n=15
        )
        logger.info(
            "premarket_scan_scheduled_complete",
            asof=record.get("asof"),
            candidates=record.get("funnel", {}).get("candidate_count"),
            path=record.get("_path")
        )
        return record
    except Exception:
        logger.exception("premarket_scan_scheduled_failed")
        return None
