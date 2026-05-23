"""APScheduler wiring for the workbench background jobs.

Cadences:
  - Asset sync:    run once at startup, then daily at 04:00 ET (pre-market).
  - Account sync:  every 10s during regular hours; every 60s otherwise.
  - Position sync: every 10s during regular hours; every 60s otherwise.

The "every 10s during regular hours" pattern is implemented as a single
interval job that checks `is_regular_session` and self-throttles. Simpler than
maintaining two competing jobs.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable

import structlog
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from app.services.account_sync import AccountSyncService
from app.services.asset_sync import AssetSyncService
from app.services.market_hours import is_regular_session
from app.services.position_sync import PositionSyncService

logger = structlog.get_logger(__name__)

# Off-hours throttle: poll every 10s, but actually do work only every 6th tick (= 60s).
_OFFHOURS_THROTTLE = 6


class WorkbenchScheduler:
    def __init__(
        self,
        asset_sync: AssetSyncService,
        account_sync: AccountSyncService,
        position_sync: PositionSyncService,
    ) -> None:
        self._asset_sync = asset_sync
        self._account_sync = account_sync
        self._position_sync = position_sync
        self._scheduler = AsyncIOScheduler(timezone="America/New_York")
        self._account_ticks = 0
        self._position_ticks = 0

    def start(self) -> None:
        self._scheduler.add_job(
            self._safe(self._asset_sync.sync_once, "asset_sync"),
            CronTrigger(hour=4, minute=0),
            id="asset_sync_daily",
            replace_existing=True,
            max_instances=1,
        )
        self._scheduler.add_job(
            self._safe(self._account_tick, "account_sync"),
            IntervalTrigger(seconds=10),
            id="account_sync_tick",
            replace_existing=True,
            max_instances=1,
        )
        self._scheduler.add_job(
            self._safe(self._position_tick, "position_sync"),
            IntervalTrigger(seconds=10),
            id="position_sync_tick",
            replace_existing=True,
            max_instances=1,
        )

        self._scheduler.start()
        logger.info("scheduler_started")

    async def shutdown(self) -> None:
        if self._scheduler.running:
            self._scheduler.shutdown(wait=False)
            logger.info("scheduler_stopped")

    @property
    def scheduler(self) -> AsyncIOScheduler:
        """The underlying APScheduler instance.

        Exposed so other components (e.g. ``StrategyEngine``) can register
        cron jobs against the same scheduler instead of standing up their
        own. One scheduler per process keeps job IDs unique and avoids two
        threads racing on the same trigger.
        """
        return self._scheduler

    async def run_startup_sync(self) -> None:
        """Run the at-startup sync passes once, in order.

        Called from the FastAPI lifespan AFTER the scheduler is started so any
        startup errors are visible immediately. Errors are logged but do NOT
        abort startup — the API stays reachable for diagnostics.
        """
        try:
            await self._asset_sync.sync_once()
        except Exception:
            logger.exception("startup_asset_sync_failed")
        try:
            await self._account_sync.sync_once()
        except Exception:
            logger.exception("startup_account_sync_failed")
        try:
            await self._position_sync.sync_once()
        except Exception:
            logger.exception("startup_position_sync_failed")

    # ---- ticks ----

    async def _account_tick(self) -> None:
        self._account_ticks = (self._account_ticks + 1) % _OFFHOURS_THROTTLE
        if not is_regular_session() and self._account_ticks != 0:
            return
        await self._account_sync.sync_once()

    async def _position_tick(self) -> None:
        self._position_ticks = (self._position_ticks + 1) % _OFFHOURS_THROTTLE
        if not is_regular_session() and self._position_ticks != 0:
            return
        await self._position_sync.sync_once()

    # ---- helpers ----

    def _safe(
        self,
        coro_fn: Callable[[], Awaitable[object]],
        name: str,
    ) -> Callable[[], Awaitable[None]]:
        """Wrap a coroutine fn so a single tick failure doesn't kill the schedule."""

        async def _wrapped() -> None:
            try:
                await coro_fn()
            except Exception:
                logger.exception("scheduler_tick_failed", name=name)

        return _wrapped
