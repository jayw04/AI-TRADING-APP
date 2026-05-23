"""FastAPI lifespan wiring for background services.

Startup:
  1. Spawn the WS heartbeat task (carried over from P0 §4).
  2. Instantiate AlpacaAdapter and connect (fail-loud if creds are wrong).
  3. Build the three sync services.
  4. Start the WorkbenchScheduler and run an initial sync pass.
  5. Start the TradeUpdatesStream as a background task.

Shutdown (reverse order):
  1. Stop the TradeUpdatesStream (before scheduler, so trailing events don't
     race in after services have torn down their session factory).
  2. Stop the scheduler.
  3. Disconnect the adapter.
  4. Cancel the heartbeat task.

Startup errors in any *sync* call are logged but do not abort the lifespan,
so the API stays reachable for diagnostics. A failure to connect to Alpaca,
however, *does* propagate — credentials issues should be loud.
"""

from __future__ import annotations

import asyncio
import contextlib
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

import structlog
from fastapi import FastAPI

from app.brokers.alpaca import AlpacaAdapter, TradeUpdatesStream
from app.config import get_settings
from app.db.session import get_sessionmaker
from app.events import get_event_bus
from app.indicators import IndicatorComputer
from app.market_data.bar_cache import BarCache
from app.orders import OrderRouter
from app.orders.lifecycle import TradeUpdateConsumer
from app.orders.positions import PositionRecomputer
from app.risk import RiskEngine
from app.services.account_sync import AccountSyncService
from app.services.asset_sync import AssetSyncService
from app.services.position_sync import PositionSyncService
from app.services.scheduler import WorkbenchScheduler
from app.strategies import StrategyEngine
from app.ws.gateway import heartbeat_loop, start_replay_populator, stop_replay_populator

logger = structlog.get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    logger.info("lifespan_startup_begin")

    heartbeat_task: asyncio.Task[None] | None = None
    adapter: AlpacaAdapter | None = None
    scheduler: WorkbenchScheduler | None = None
    trade_stream: TradeUpdatesStream | None = None
    trade_update_consumer: TradeUpdateConsumer | None = None
    strategy_engine: StrategyEngine | None = None

    try:
        # 1. WS heartbeat (P0 §4) + WS replay populator (P1 Session 6).
        # The populator owns the global ReplayBuffer; per-connection forwarders
        # in gateway.py do live forwarding without duplicating appends.
        heartbeat_task = asyncio.create_task(heartbeat_loop(), name="ws-heartbeat")
        start_replay_populator()

        # 2. Alpaca adapter + scheduler + trade-updates stream — gated by
        # settings.alpaca_startup_enabled so tests can run without real creds
        # and without hitting the broker.
        settings = get_settings()
        if settings.alpaca_startup_enabled:
            adapter = AlpacaAdapter()
            await asyncio.to_thread(adapter.connect)
            logger.info("alpaca_connected_at_startup", paper=adapter.is_paper)

            session_factory = get_sessionmaker()
            bus = get_event_bus()

            asset_sync = AssetSyncService(adapter, session_factory, bus)
            account_sync = AccountSyncService(adapter, session_factory, bus)
            position_sync = PositionSyncService(adapter, session_factory, bus)

            scheduler = WorkbenchScheduler(asset_sync, account_sync, position_sync)
            scheduler.start()

            # 5. Trade Updates WebSocket (P1 Session 3)
            trade_stream = TradeUpdatesStream(adapter.credentials, bus)
            await trade_stream.start()

            # 6. Risk Engine + Order Router (P1 Session 5 Phase A)
            risk_engine = RiskEngine(session_factory)
            order_router = OrderRouter(adapter, risk_engine, session_factory, bus)

            # 7. PositionRecomputer + TradeUpdateConsumer (P1 Session 5 Phase B)
            # Consumer subscribes to the bus and translates alpaca.trade_update
            # events into Fill rows + Order transitions + position recomputes.
            position_recomputer = PositionRecomputer(session_factory, bus)
            trade_update_consumer = TradeUpdateConsumer(
                session_factory, bus, position_recomputer
            )
            await trade_update_consumer.start()

            # 8. BarCache + IndicatorComputer (P2 Session 1). These do not
            # need the adapter for fetches (they call the historical data
            # client directly via load_credentials), but we only construct
            # them when alpaca_startup_enabled so tests don't write parquet
            # files into the repo root.
            bar_cache = BarCache(
                adapter=adapter,
                root=settings.bars_cache_root,
                max_gb=settings.bars_cache_max_gb,
            )
            indicator_computer = IndicatorComputer()

            # 9. StrategyEngine (P2 Session 2). Shares the same
            # AsyncIOScheduler instance as WorkbenchScheduler — two
            # schedulers contending for the same job IDs would be a
            # sneaky bug.
            strategy_engine = StrategyEngine(
                scheduler=scheduler.scheduler,
                session_factory=session_factory,
                bus=bus,
                bar_cache=bar_cache,
                indicator_computer=indicator_computer,
                order_router=order_router,
                strategies_root=Path("strategies_user"),
            )

            # Stash for request handlers / tests
            app.state.alpaca_adapter = adapter
            app.state.asset_sync = asset_sync
            app.state.account_sync = account_sync
            app.state.position_sync = position_sync
            app.state.scheduler = scheduler
            app.state.trade_stream = trade_stream
            app.state.risk_engine = risk_engine
            app.state.order_router = order_router
            app.state.position_recomputer = position_recomputer
            app.state.trade_update_consumer = trade_update_consumer
            app.state.bar_cache = bar_cache
            app.state.indicator_computer = indicator_computer
            app.state.strategy_engine = strategy_engine

            # Initial sync pass (each call wraps its own try/except internally)
            await scheduler.run_startup_sync()

            # Resume-on-boot: re-register strategies that were active before
            # the last shutdown. Best-effort — a single broken strategy
            # shouldn't take down boot.
            from sqlalchemy import select

            from app.db.enums import ACTIVE_STRATEGY_STATUSES
            from app.db.models.strategy import Strategy as StrategyRow

            async with session_factory() as resume_session:
                rows_to_resume = (
                    await resume_session.execute(
                        select(StrategyRow).where(
                            StrategyRow.status.in_(list(ACTIVE_STRATEGY_STATUSES))
                        )
                    )
                ).scalars().all()
            for row in rows_to_resume:
                try:
                    await strategy_engine.register(row.id)
                except Exception:
                    logger.exception(
                        "strategy_resume_failed_on_boot", strategy_id=row.id
                    )
        else:
            logger.info("alpaca_startup_disabled")

        logger.info("lifespan_startup_complete")
        yield
    finally:
        logger.info("lifespan_shutdown_begin")
        # Stop the WS replay populator before the bus subscribers go quiet —
        # avoids the populator throwing on stopped bus.
        try:
            await stop_replay_populator()
        except Exception:
            logger.exception("replay_populator_stop_failed")
        # Stop the strategy engine before the consumer so any in-flight
        # on_fill dispatches don't race with the consumer being torn down.
        if strategy_engine is not None:
            try:
                await strategy_engine.shutdown()
            except Exception:
                logger.exception("strategy_engine_shutdown_failed")
        # Stop the consumer first so trailing trade-update events don't try to
        # write into a session factory that's about to go away.
        if trade_update_consumer is not None:
            try:
                await trade_update_consumer.stop()
            except Exception:
                logger.exception("trade_update_consumer_stop_failed")
        # Stop the WS stream before the scheduler so no new events arrive
        # while the consumer is being torn down.
        if trade_stream is not None:
            try:
                await trade_stream.stop()
            except Exception:
                logger.exception("trade_stream_stop_failed")
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
