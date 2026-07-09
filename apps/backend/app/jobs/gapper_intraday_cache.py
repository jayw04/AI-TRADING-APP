"""GAPPER-001 intraday auto-cache job (pre-registration v0.2 §7).

~16:35 ET (after the close and the SCAN back-fill): for today's premarket candidate set, cache the
same-day 1/5-min bars for each candidate + SPY + its sector SPDR, so the eventual CAP-025 replay has
data as evidence accrues. Read-only, fail-soft, no order path — a bad day (no record, no store, an
Alpaca miss) is logged and skipped, never allowed to disturb the scheduler.
"""
from __future__ import annotations

import json
import os
from datetime import date, datetime
from typing import Any
from zoneinfo import ZoneInfo

import structlog

from app.factor_data.gapper_intraday import cache_candidate_event

logger = structlog.get_logger(__name__)
_ET = ZoneInfo("America/New_York")


def _today_et() -> date:
    return datetime.now(_ET).date()


async def run_gapper_intraday_cache_scheduled(
    *, bar_cache: Any, factor_store: Any, directory: str
) -> dict | None:
    """Cache today's candidates' intraday bars (candidate + SPY + sector SPDR). A no-scan day (no
    record persisted this morning) is a clean no-op. Returns a small summary or ``None``."""
    asof = _today_et()
    path = os.path.join(directory, f"premarket_scan_{asof.isoformat()}.json")
    try:
        if not os.path.exists(path):
            logger.info("gapper_intraday_cache_skipped_no_record", asof=str(asof))
            return None
        with open(path, encoding="utf-8") as fh:
            record = json.load(fh)
        candidates = [c.get("symbol") for c in record.get("candidates", []) if c.get("symbol")]
        cached = excluded = 0
        for ticker in candidates:
            res = await cache_candidate_event(bar_cache, factor_store.con, ticker, asof)
            if res.get("cached"):
                cached += 1
            elif res.get("excluded_reason"):
                excluded += 1
        logger.info(
            "gapper_intraday_cache_done",
            asof=str(asof), candidates=len(candidates), cached=cached, excluded=excluded,
        )
        return {"asof": str(asof), "candidates": len(candidates), "cached": cached, "excluded": excluded}
    except Exception:  # noqa: BLE001 — advisory job must never break the scheduler
        logger.exception("gapper_intraday_cache_failed", asof=str(asof))
        return None
