"""Recovery service (P11 §5, ADR 0021 property 3) — restart-resume, instrumented.

Extracts the resume-on-boot logic from ``lifespan`` into a testable, instrumented helper so the
restart-recovery contract can be *proven* (a test), not just asserted, and so the recovery KPIs
(``recovery_*`` metrics) are fed. It is **prove-don't-rebuild**: the recovery mechanism already
exists (the engine's idempotent ``register()`` + durable strategy state); this module only makes
it callable in isolation and observable.

> **Restart-safety rests on idempotency, not a durable "resumed" flag.**
> ``strategy_engine.register()`` is idempotent — a second call returns the existing
> ``RunningStrategy`` and opens no second run — so re-registering every
> ``ENGINE_RUNNABLE_STATUSES`` strategy on boot can never double-register or double-dispatch.
> Best-effort: one strategy that fails to register logs + counts a failure and does **not**
> abort the others or boot. Read-only beyond the engine's own registration; never the order path.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Protocol

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.enums import ENGINE_RUNNABLE_STATUSES
from app.db.models.strategy import Strategy as StrategyRow
from app.strategies.hold_service import StrategyOnHold
from app.observability.metrics import (
    recovery_attempts_total,
    recovery_duration_seconds,
    recovery_failures_total,
    recovery_success_total,
)

logger = structlog.get_logger(__name__)

RESUME = "resume_on_boot"  # the recovery_type label


class _Registrar(Protocol):
    async def register(self, strategy_id: int) -> object: ...


@dataclass(frozen=True)
class ResumeSummary:
    """Outcome of one resume-on-boot pass. ``attempted == resumed + len(failed_ids)``."""

    attempted: int = 0
    resumed: int = 0
    failed_ids: list[int] = field(default_factory=list)
    duration_ms: int = 0

    @property
    def failed(self) -> int:
        return len(self.failed_ids)


async def resume_strategies_on_boot(
    session_factory: async_sessionmaker[AsyncSession],
    strategy_engine: _Registrar,
) -> ResumeSummary:
    """Re-register every ``ENGINE_RUNNABLE_STATUSES`` strategy after a restart.

    Per-strategy counters (``recovery_attempts_total`` / ``recovery_success_total`` /
    ``recovery_failures_total`` labelled ``resume_on_boot``) so ``success/(success+failures)`` is
    the clean-resume ratio; one ``recovery_duration_seconds`` observation per pass. Idempotent and
    best-effort — never raises into boot for a per-strategy failure.
    """
    started = time.monotonic()
    async with session_factory() as session:
        rows = (
            await session.execute(
                select(StrategyRow.id).where(
                    StrategyRow.status.in_(list(ENGINE_RUNNABLE_STATUSES))
                )
            )
        ).scalars().all()

    resumed = 0
    failed_ids: list[int] = []
    for sid in rows:
        recovery_attempts_total.labels(recovery_type=RESUME).inc()
        try:
            await strategy_engine.register(sid)
            recovery_success_total.labels(recovery_type=RESUME).inc()
            resumed += 1
        except StrategyOnHold as exc:
            # ADR 0044 inv 5-7: an operational hold is an intentional skip on boot,
            # NOT a recovery failure — don't count it against the failure metric or
            # the failed_ids alert list. register() already recorded the deduped
            # STRATEGY_ACTIVATION_BLOCKED_BY_HOLD; surface it as its own signal.
            logger.warning(
                "strategy_resume_skipped_on_hold", strategy_id=sid,
                reason_code=exc.reason_code, hold_rev=exc.rev,
            )
        except Exception:
            recovery_failures_total.labels(recovery_type=RESUME).inc()
            failed_ids.append(sid)
            logger.exception("strategy_resume_failed_on_boot", strategy_id=sid)

    duration_ms = int((time.monotonic() - started) * 1000)
    recovery_duration_seconds.labels(recovery_type=RESUME).observe(time.monotonic() - started)
    summary = ResumeSummary(
        attempted=len(rows), resumed=resumed, failed_ids=failed_ids, duration_ms=duration_ms
    )
    logger.info(
        "resume_on_boot_complete",
        attempted=summary.attempted,
        resumed=summary.resumed,
        failed=summary.failed,
    )
    return summary
