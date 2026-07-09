"""GAPPER-001 shadow-ledger job (pre-registration v0.2 §8).

~16:40 ET (after the close, the SCAN back-fill, and the intraday auto-cache): compute + persist today's
shadow-ledger record — per-candidate primary-design outcomes + the daily book. Forward observation only
(Backtest Pending). Read-only, fail-soft; a no-scan day is a clean no-op.
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Any
from zoneinfo import ZoneInfo

import structlog

from app.services.gapper_shadow_ledger import compute_day_ledger

logger = structlog.get_logger(__name__)
_ET = ZoneInfo("America/New_York")


def _today_et() -> date:
    return datetime.now(_ET).date()


async def run_gapper_shadow_ledger_scheduled(
    *, bar_cache: Any, factor_store: Any, evidence_dir: str, ledger_dir: str
) -> dict | None:
    asof = _today_et()
    try:
        record = await compute_day_ledger(
            bar_cache, factor_store.con,
            evidence_dir=evidence_dir, ledger_dir=ledger_dir, asof=asof,
        )
        if record is None:
            logger.info("gapper_shadow_ledger_skipped_no_record", asof=str(asof))
        return record
    except Exception:  # noqa: BLE001 — advisory job must never break the scheduler
        logger.exception("gapper_shadow_ledger_failed", asof=str(asof))
        return None
