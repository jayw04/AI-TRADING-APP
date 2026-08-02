"""Sync-before-admit: no account may admit risk before its first baseline-bearing sync.

``accounts_state`` is written by ``AccountSyncService`` on each poll, and the poll is
scheduler-driven — so between process start and the first successful ``sync_all()`` there is a
window in which every account has NO state row. ``api/v1/account.py`` already treats that window
as normal and answers 503 "try again in a few seconds".

The daily-loss gate cannot be evaluated in that window either. Refusing there is correct — a
configured limit that cannot be evaluated is not a satisfied limit — but "refuse until a
background tick happens to land" is a *lifecycle* problem being handled as a runtime fault. So
startup waits for the baseline instead of racing it:

    PROCESS_STARTED → ACCOUNT_STATE_SYNC_PENDING → BASELINE_VALIDATED → RISK_ADMISSION_ENABLED

The wait is **bounded**. On expiry startup continues and an alert is emitted — it must never hang
the boot, and the account-scoped gate in ``risk/engine.py`` is what keeps the outcome SAFE
(risk-increasing orders refused, ADR 0042 reductions still permitted, no global halt). This
module makes the window short and observable; it is not itself the control.

It also answers the operational question nobody could answer before: **how long is that window?**
``account_state_ready`` carries the measured elapsed time from the start of the wait.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.models.account import Account
from app.db.models.account_state import AccountState

logger = structlog.get_logger(__name__)

#: How long startup will wait for the first baseline-bearing sync before giving up and alerting.
DEFAULT_READINESS_TIMEOUT_SECONDS = 60.0
#: Gap between re-checks (and re-sync attempts) while waiting.
DEFAULT_POLL_INTERVAL_SECONDS = 2.0


@dataclass(frozen=True)
class ReadinessResult:
    """What the wait observed. ``ready`` False means the bound expired, NOT that boot failed."""

    ready: bool
    elapsed_seconds: float
    attempts: int
    missing_account_ids: tuple[int, ...]


async def accounts_missing_state(session: AsyncSession) -> tuple[int, ...]:
    """Account ids with no ``accounts_state`` row — i.e. never successfully synced."""
    rows = (
        await session.execute(
            select(Account.id)
            .outerjoin(AccountState, AccountState.account_id == Account.id)
            .where(AccountState.account_id.is_(None))
            .order_by(Account.id)
        )
    ).scalars().all()
    return tuple(rows)


async def await_account_state_ready(
    session_factory: async_sessionmaker[AsyncSession],
    sync: Callable[[], Awaitable[object]] | None = None,
    *,
    timeout_seconds: float = DEFAULT_READINESS_TIMEOUT_SECONDS,
    poll_interval_seconds: float = DEFAULT_POLL_INTERVAL_SECONDS,
) -> ReadinessResult:
    """Wait (bounded) until every account has a state row, driving ``sync`` between checks.

    Never raises: a broker that is unreachable at boot must not prevent the process from
    starting, it must only prevent the affected accounts from admitting risk — and that is the
    gate's job, not this function's. ``CancelledError`` still propagates so shutdown works.
    """
    started = time.monotonic()
    attempts = 0
    missing: tuple[int, ...] = ()

    while True:
        async with session_factory() as session:
            missing = await accounts_missing_state(session)
        elapsed = time.monotonic() - started

        if not missing:
            logger.info(
                "account_state_ready",
                elapsed_seconds=round(elapsed, 3),
                attempts=attempts,
                phase="BASELINE_VALIDATED",
            )
            return ReadinessResult(True, elapsed, attempts, ())

        if elapsed >= timeout_seconds:
            # The alert. Startup proceeds; these accounts stay non-admitting until a later sync
            # lands, and the daily-loss gate refuses risk increases for them in the meantime.
            logger.error(
                "account_state_not_ready",
                elapsed_seconds=round(elapsed, 3),
                attempts=attempts,
                missing_account_ids=list(missing),
                consequence="accounts refuse risk-increasing orders until synced",
            )
            return ReadinessResult(False, elapsed, attempts, missing)

        if sync is not None:
            attempts += 1
            try:
                await sync()
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.warning(
                    "account_state_sync_attempt_failed",
                    attempt=attempts,
                    missing_account_ids=list(missing),
                    exc_info=True,
                )
        await asyncio.sleep(poll_interval_seconds)
