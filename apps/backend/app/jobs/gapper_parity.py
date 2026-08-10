"""GAP-NATIVE-001 daily source-parity accrual job (ADR 0041; GAPPER v2.1.1 §3.1).

Runs ~09:30 ET weekdays — after the 09:05/09:18 native scan and the 09:25 SCAN-001
gate scan, so both source files and that day's gate record exist. Writes one dated
parity artifact per day into ``gapper_parity_dir``.

Deliberately runs on **every** weekday, including days where a source is missing:
the absent-source day is itself parity evidence (see ``parity_record``). Fail-soft —
an advisory measurement job must never break the scheduler.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Any

import structlog

from app.services.gapper_source_parity import parity_record, persist_parity_record
from app.utils.time import EASTERN

logger = structlog.get_logger(__name__)


def _today_et() -> date:
    return datetime.now(UTC).astimezone(EASTERN).date()


async def run_gapper_parity_job(
    *,
    native_dir: str,
    external_dir: str,
    evidence_dir: str,
    directory: str,
    now: datetime | None = None,
) -> dict[str, Any] | None:
    """Build and persist today's native-vs-external parity record."""
    asof = (now.astimezone(EASTERN).date() if now else _today_et())
    try:
        record = parity_record(
            asof,
            native_dir=native_dir,
            external_dir=external_dir,
            evidence_dir=evidence_dir,
        )
        path = persist_parity_record(record, directory)
        comparison = record.get("comparison") or {}
        logger.info(
            "gapper_source_parity_recorded",
            asof=str(asof),
            path=path,
            both_present=record.get("both_present"),
            native_discovery_reason=record.get("native_discovery_reason"),
            overlap_pct_of_external=comparison.get("overlap_pct_of_external"),
            native_count=comparison.get("native_count"),
            external_count=comparison.get("external_count"),
        )
        return record
    except Exception:  # noqa: BLE001 — advisory job must never break the scheduler
        logger.exception("gapper_source_parity_failed", asof=str(asof))
        return None
