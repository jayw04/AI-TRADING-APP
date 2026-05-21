"""FastAPI lifespan wiring for background services.

Startup:
  1. Spawn the WS heartbeat task (carried over from P0 §4).
  2. Instantiate AlpacaAdapter and connect (fail-loud if creds are wrong).
  3. Build the three sync services.
  4. Start the WorkbenchScheduler and run an initial sync pass.

Shutdown (reverse order):
  1. Stop the scheduler.
  2. Disconnect the adapter.
  3. Cancel the heartbeat task.

Startup errors in any *sync* call are logged but do not abort the lifespan,
so the API stays reachable for diagnostics. A failure to connect to Alpaca,
however, *does* propagate — credentials issues should be loud.
"""

from __future__ import annotations

import asyncio
import contextlib
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI

from app.brokers.alpaca import AlpacaAdapter
from app.config import get_settings
from app.db.session import get_sessionmaker
from app.events import get_event_bus
from app.services.account_sync import AccountSyncService
from app.services.asset_sync import AssetSyncService
from app.services.position_sync import PositionSyncService
from app.services.scheduler import WorkbenchScheduler
from app.ws.gateway import heartbeat_loop

logger = structlog.get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    logger.info("lifespan_startup_begin")

    heartbeat_task: asyncio.Task[None] | None = None
    adapter: AlpacaAdapter | None = None
    scheduler: WorkbenchScheduler | None = None

    try:
        # 1. WS heartbeat (P0 §4)
        heartbeat_task = asyncio.create_task(heartbeat_loop(), name="ws-heartbeat")

        # 2. Alpaca adapter + scheduler — gated by settings.alpaca_startup_enabled
        # so tests can run without real creds and without hitting the broker.
        settings = get_settings()
        if settings.alpaca_startup_enabled:
            adapter = AlpacaAdapter()
            await asyncio.to_thread(adapter.connect)
            logger.info("alpaca_connected_at_startup", paper=adapter.is_paper)

            session_factory = get_sessionmaker()
            bus = get_event_bus()

            asset_sync = AssetSyncService(adapter, session_factory, bus)
            account_sync = AccountSyncService(adapter, session_factory, bus)
            position_sync = PositionSyncService(adapter, bus)

            scheduler = WorkbenchScheduler(asset_sync, account_sync, position_sync)
            scheduler.start()

            # Stash for request handlers / tests
            app.state.alpaca_adapter = adapter
            app.state.asset_sync = asset_sync
            app.state.account_sync = account_sync
            app.state.position_sync = position_sync
            app.state.scheduler = scheduler

            # Initial sync pass (each call wraps its own try/except internally)
            await scheduler.run_startup_sync()
        else:
            logger.info("alpaca_startup_disabled")

        logger.info("lifespan_startup_complete")
        yield
    finally:
        logger.info("lifespan_shutdown_begin")
        if scheduler is not None:
            try:
                await scheduler.shutdown()
            except Exception:
                logger.exception("scheduler_shutdown_failed")
        if adapter is not None:
            try:
                adapter.disconnect()
            except Exception:
                logger.exception("adapter_disconnect_failed")
        if heartbeat_task is not None:
            heartbeat_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await heartbeat_task
        logger.info("lifespan_shutdown_complete")
