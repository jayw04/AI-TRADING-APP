"""Snapshot DB-derived gauge values for Prometheus (P5 §8.3.2).

Runs every 30s via the lifespan scheduler. Counters/histograms are incremented
inline at the event sites; gauges reflect current state and must be sampled —
that's this job. Each pass zeroes the per-status gauge before repopulating so a
status that drops to zero strategies doesn't leave a stale value (Prometheus
gauges retain their last set value).
"""

from __future__ import annotations

from datetime import UTC, datetime

import structlog
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.enums import StrategyStatus
from app.db.models.account import Account
from app.db.models.audit_log import AuditLog
from app.db.models.strategy import Strategy
from app.db.models.user_credential import UserCredential
from app.observability import metrics as obs
from app.utils.time import ensure_aware

logger = structlog.get_logger(__name__)


async def run_metrics_snapshot(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Sample gauge values from the DB. Best-effort: never raises into the
    scheduler (the lifespan wrapper also guards, but be defensive)."""
    try:
        now = datetime.now(UTC)
        async with session_factory() as session:
            # strategies_active by status — zero all known statuses first.
            for s in StrategyStatus:
                obs.strategies_active.labels(status=s.value).set(0)
            rows = (
                await session.execute(
                    select(Strategy.status, func.count(Strategy.id)).group_by(
                        Strategy.status
                    )
                )
            ).all()
            for status, count in rows:
                label = status.value if hasattr(status, "value") else str(status)
                obs.strategies_active.labels(status=label).set(count)

            cooldown = (
                await session.execute(
                    select(func.count(Strategy.id))
                    .where(Strategy.cooldown_until.isnot(None))
                    .where(Strategy.cooldown_until > now)
                )
            ).scalar() or 0
            obs.strategies_in_cooldown.set(cooldown)

            tripped = (
                await session.execute(
                    select(func.count(Account.id)).where(
                        Account.circuit_breaker_tripped_at.isnot(None)
                    )
                )
            ).scalar() or 0
            obs.circuit_breakers_tripped.set(tripped)

            pending = (
                await session.execute(
                    select(func.count(Strategy.id)).where(
                        Strategy.status == StrategyStatus.PENDING_LIVE
                    )
                )
            ).scalar() or 0
            obs.pending_live_strategies.set(pending)

            audit_rows = (
                await session.execute(select(func.count(AuditLog.id)))
            ).scalar() or 0
            obs.audit_log_rows_total.set(audit_rows)

            creds = (
                await session.execute(
                    select(UserCredential.kind, func.max(UserCredential.updated_at))
                    .where(UserCredential.revoked_at.is_(None))
                    .group_by(UserCredential.kind)
                )
            ).all()
            for kind, last_updated in creds:
                aware = ensure_aware(last_updated)
                if aware is None:
                    continue
                obs.credential_stale_seconds.labels(kind=kind).set(
                    (now - aware).total_seconds()
                )
    except Exception:
        logger.exception("metrics_snapshot_failed")
