"""Run a scanner definition and record the result (P8 §2/§4).

Shared by the on-demand run endpoint (trigger="manual") and the pre-market cron
(trigger="scheduled"). Builds + adds the ScannerRun row and writes the
SCANNER_RUN audit entry; the caller commits.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.logger import AuditAction, AuditActorType, AuditLogger
from app.db.models.scanner_definition import ScannerDefinition
from app.db.models.scanner_run import RUN_OK, TRIGGER_MANUAL, ScannerRun
from app.services.scanner.engine import DiscoveryFeedsFn, run_scan


async def run_and_record(
    session: AsyncSession,
    *,
    definition: ScannerDefinition,
    bar_cache: Any,
    indicator_computer: Any,
    discovery_feeds_fn: DiscoveryFeedsFn,
    now: datetime,
    trigger: str = TRIGGER_MANUAL,
) -> ScannerRun:
    """Evaluate the definition's criterion over its universe, persist a
    ScannerRun (added to the session, not committed), and audit it."""
    result = await run_scan(
        session,
        criteria=definition.criteria,
        universe_kind=definition.universe_kind,
        universe_symbols=definition.universe_symbols_json,
        timeframe=definition.timeframe,
        user_id=definition.user_id,
        bar_cache=bar_cache,
        indicator_computer=indicator_computer,
        discovery_feeds_fn=discovery_feeds_fn,
        now=now,
    )

    run = ScannerRun(
        scanner_definition_id=definition.id,
        user_id=definition.user_id,
        run_at=now,
        status=RUN_OK,
        trigger=trigger,
        criteria_snapshot=definition.criteria,
        universe_kind=definition.universe_kind,
        timeframe=definition.timeframe,
        universe_size=result.universe_size,
        evaluated_count=result.evaluated,
        matched_count=len(result.matched),
        skipped_count=len(result.skipped),
        matched_json=[
            {"symbol": m.symbol, "values": m.values} for m in result.matched
        ],
        skipped_json=[
            {"symbol": s.symbol, "reason": s.reason} for s in result.skipped
        ],
        error=None,
    )
    session.add(run)

    AuditLogger.write(
        session,
        actor_type=AuditActorType.USER,
        actor_id=str(definition.user_id),
        action=AuditAction.SCANNER_RUN,
        target_type="scanner_definition",
        target_id=definition.id,
        user_id=definition.user_id,
        payload={
            "criteria": definition.criteria,
            "universe_kind": definition.universe_kind,
            "timeframe": definition.timeframe,
            "trigger": trigger,
            "universe_size": result.universe_size,
            "matched_count": len(result.matched),
            "skipped_count": len(result.skipped),
            "matched_symbols": [m.symbol for m in result.matched],
        },
    )
    return run
