"""GAP-NATIVE-001 scheduled entry point: the box-native premarket gapper scan.

Weekdays 09:05 ET, with an idempotent 09:18 ET retry (both wired in lifespan
behind ``WORKBENCH_NATIVE_GAPPER_SCREENER_ENABLED``): once today's native file
exists the retry is a no-op, so a good 09:05 run makes 09:18 free, and an
Alpaca hiccup at 09:05 still leaves a shot ≥7 minutes before the 09:25 SCAN-001
scan consumes the file. Read-only market data; fail-soft — never raises into
the scheduler. See ADR 0041 and the GAP-NATIVE-001 session doc.
"""

from __future__ import annotations

import os
import time
from datetime import UTC, datetime
from typing import Any

import structlog

from app.config import get_settings
from app.services.native_gapper_screener import scan_native_gappers, write_gappers_file
from app.utils.time import EASTERN

logger = structlog.get_logger(__name__)


async def run_native_gapper_scan(
    factor_store: Any = None,
    *,
    force: bool = False,
    now: datetime | None = None,
) -> dict[str, Any] | None:
    """Scan → write today's ``premarket_gappers_<date>.json`` into the native dir.

    Skips weekends and (unless ``force``) days whose native file already exists.
    A failed scan writes nothing — the reader then falls back to the external
    file or the newest stale one (``premarket_gappers.read_latest_gappers``).
    Returns the scan result dict, or None when skipped/failed."""
    now_utc = now or datetime.now(UTC)
    now_et = now_utc.astimezone(EASTERN)
    if now_et.weekday() >= 5 and not force:
        logger.info("native_gapper_scan_skipped_weekend")
        return None

    directory = get_settings().native_gappers_dir
    date_str = now_et.date().isoformat()
    path = os.path.join(directory, f"premarket_gappers_{date_str}.json")
    if not force and os.path.exists(path):
        logger.info("native_gapper_scan_skipped_exists", path=path)
        return None

    t0 = time.monotonic()
    result = await scan_native_gappers(factor_store=factor_store, now=now_utc)
    if not result.get("ok"):
        # A failed scan writes NOTHING (review §6): the reader falls back to a
        # same-date external file if one exists, else newest-stale. An empty
        # native file is reserved for a scan that genuinely ran and found zero.
        result["status"] = "scan_failed"
        logger.warning(
            "native_gapper_scan_failed",
            reason=result.get("reason"),
            discovery_path=result.get("discovery_path"),
            elapsed_s=round(time.monotonic() - t0, 1),
        )
        return None

    written = write_gappers_file(result["payload"], directory, date_str=date_str)
    result["status"] = (
        "scan_success_non_empty" if result.get("count") else "scan_success_zero_candidates"
    )
    logger.info(
        "native_gapper_scan_complete",
        status=result["status"],
        job_elapsed_s=round(time.monotonic() - t0, 1),
        path=written,
        **(result.get("funnel") or {}),
    )
    return result
