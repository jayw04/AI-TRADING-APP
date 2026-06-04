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
import os
import sys
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

import structlog
from fastapi import FastAPI

from app.brokers.alpaca import AlpacaAdapter, TradeUpdatesStream
from app.brokers.registry import BrokerRegistry
from app.config import get_settings
from app.db.session import get_sessionmaker
from app.events import get_event_bus
from app.indicators import IndicatorComputer
from app.llm.runtime import AgentRuntime
from app.market_data.bar_cache import BarCache
from app.orders import OrderRouter
from app.orders.lifecycle import TradeUpdateConsumer
from app.orders.positions import PositionRecomputer
from app.risk import RiskEngine
from app.security import MasterKeyMissingError, verify_master_key
from app.services.account_sync import AccountSyncService
from app.services.asset_sync import AssetSyncService
from app.services.backtest_worker import BacktestWorker
from app.services.bar_stream import BarStreamService
from app.services.position_sync import PositionSyncService
from app.services.scheduler import WorkbenchScheduler
from app.services.strategy_file_watcher import StrategyFileWatcher
from app.strategies import StrategyEngine
from app.ws.gateway import heartbeat_loop, start_replay_populator, stop_replay_populator

logger = structlog.get_logger(__name__)


async def run_daily_backup() -> None:
    """Run scripts/backup_db.sh (P5 §8.5) — daily SQLite backup.

    The script path defaults to ``<repo-root>/scripts/backup_db.sh`` (resolved
    relative to this file) and is overridable via ``WORKBENCH_BACKUP_SCRIPT``
    for non-standard deployments. Failures are logged, never raised — a missed
    backup must not take down the scheduler."""
    import os

    default_script = Path(__file__).resolve().parents[3] / "scripts" / "backup_db.sh"
    script = os.environ.get("WORKBENCH_BACKUP_SCRIPT", str(default_script))
    try:
        proc = await asyncio.create_subprocess_exec(
            "bash",
            script,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()
        if proc.returncode != 0:
            logger.error(
                "daily_backup_failed",
                returncode=proc.returncode,
                stderr=stderr.decode(errors="replace").strip(),
            )
        else:
            logger.info(
                "daily_backup_complete", detail=stdout.decode(errors="replace").strip()
            )
    except Exception:
        logger.exception("daily_backup_exception")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    logger.info("lifespan_startup_begin")

    # P6 §1b: the URL of the agent control-plane service. The proposals
    # endpoint synchronously invokes POST {agent_url}/generate-proposal. Set
    # unconditionally (outside the alpaca block) so it's present in every boot;
    # in docker-compose the backend service sets AGENT_URL=http://agent:8767.
    app.state.agent_url = os.environ.get("AGENT_URL", "http://127.0.0.1:8767")

    heartbeat_task: asyncio.Task[None] | None = None
    adapter: AlpacaAdapter | None = None
    broker_registry: BrokerRegistry | None = None
    scheduler: WorkbenchScheduler | None = None
    trade_stream: TradeUpdatesStream | None = None
    trade_update_consumer: TradeUpdateConsumer | None = None
    strategy_engine: StrategyEngine | None = None
    strategy_file_watcher: StrategyFileWatcher | None = None
    bar_stream_service: BarStreamService | None = None

    try:
        # 0. Master key verification (P5 §4). Must run BEFORE the broker
        # registry loads adapters — the async credentials_for_mode() reads the
        # encrypted credential store, which needs the master key. Fail loud,
        # fail fast: no "degraded mode" that silently falls back to env vars.
        try:
            verify_master_key()
        except MasterKeyMissingError as exc:
            logger.error("master_key_missing_or_invalid", error=str(exc))
            sys.exit(1)

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

            # 6. Broker Registry + Risk Engine + Order Router
            #    (P1 Session 5 Phase A; registry added P5 §2; risk engine gets
            #    the registry + bus in P5 §5 for the new account-level gates).
            #
            # P5 §2: one adapter per account, selected by AccountMode. Construct
            # is network-free; we then reuse the already-connected startup paper
            # adapter for the user's paper account(s) so we don't open a second
            # TradingClient. Live accounts (none exist yet) would get a paper=False
            # adapter, but the OrderRouter's §1 BrokerModeError guard short-circuits
            # before the registry is ever consulted for them.
            broker_registry = BrokerRegistry(session_factory)
            await broker_registry.load_all()
            from sqlalchemy import select as _select

            from app.db.models.account import Account as _Account
            from app.db.models.account import AccountMode as _AccountMode

            async with session_factory() as _acc_session:
                _paper_ids = [
                    a.id
                    for a in (
                        await _acc_session.execute(
                            _select(_Account).where(
                                _Account.mode == _AccountMode.paper
                            )
                        )
                    ).scalars().all()
                ]
            for _aid in _paper_ids:
                broker_registry.register(_aid, adapter)

            # P5 §5: the engine now also runs the circuit breaker (publishes on
            # the bus when it trips) and the LIVE-only buying-power gate (uses
            # the registry; dormant until §7). bar_cache is wired in §7 when
            # live MARKET orders need a price estimate.
            risk_engine = RiskEngine(
                session_factory, broker_registry=broker_registry, bus=bus
            )

            order_router = OrderRouter(
                adapter, risk_engine, session_factory, bus,
                broker_registry=broker_registry,
            )

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

            # 10. BacktestWorker (P4 §2). Shares the same scheduler so the
            # 2s tick lives alongside the existing sync jobs.
            backtest_worker = BacktestWorker(
                scheduler=scheduler.scheduler,
                session_factory=session_factory,
                bar_cache=bar_cache,
                indicator_computer=indicator_computer,
                bus=bus,
            )
            await backtest_worker.start()

            # 10b. Activation completion job (P5 §7). Every 60s, flip
            # PENDING_LIVE → LIVE for strategies whose 24h cooldown (ADR 0005)
            # has elapsed. Idempotent across restarts. max_instances=1 +
            # coalesce so a slow pass doesn't pile up.
            from app.jobs.activation_completion import run_activation_completion

            scheduler.scheduler.add_job(
                run_activation_completion,
                trigger="interval",
                seconds=60,
                id="activation_completion",
                max_instances=1,
                coalesce=True,
                kwargs={"session_factory": session_factory, "bus": bus},
            )
            logger.info("activation_completion_scheduled")

            # 10c. Metrics snapshot job (P5 §8.3). Every 30s, sample the
            # DB-derived gauges (active strategies by status, cooldown / breaker
            # / pending-live counts, audit-log row count, credential staleness).
            from app.jobs.metrics_snapshot import run_metrics_snapshot

            scheduler.scheduler.add_job(
                run_metrics_snapshot,
                trigger="interval",
                seconds=30,
                id="metrics_snapshot",
                max_instances=1,
                coalesce=True,
                kwargs={"session_factory": session_factory},
            )
            logger.info("metrics_snapshot_scheduled")

            # 10d. Daily SQLite backup (P5 §8.5). 02:00 in the scheduler's
            # timezone (America/New_York). 30-day retention is enforced inside
            # the script. max_instances=1 + coalesce so a slow/long backup can't
            # stack up behind itself.
            from apscheduler.triggers.cron import CronTrigger

            scheduler.scheduler.add_job(
                run_daily_backup,
                CronTrigger(hour=2, minute=0),
                id="daily_backup",
                max_instances=1,
                coalesce=True,
                replace_existing=True,
            )
            logger.info("daily_backup_scheduled")

            # 10e. Morning brief (P5.5 §2). Mon-fri 09:00 in the scheduler's
            # timezone (America/New_York) — 30 min before the equity open, so the
            # user has reading time. Needs the bar cache + indicator computer
            # built above; broker-independent otherwise. Idempotent per (user,
            # date). max_instances=1 + coalesce so a slow pass can't stack.
            from app.jobs.morning_brief_generation import run_morning_brief_generation

            scheduler.scheduler.add_job(
                run_morning_brief_generation,
                CronTrigger(day_of_week="mon-fri", hour=9, minute=0),
                id="morning_brief_generation",
                max_instances=1,
                coalesce=True,
                replace_existing=True,
                kwargs={
                    "session_factory": session_factory,
                    "bar_cache": bar_cache,
                    "indicator_computer": indicator_computer,
                },
            )
            logger.info("morning_brief_scheduled")

            # 10f. Proposal cadence (P6 §2a). Opt-in per user via
            # agent_envelope_json.proposal_cadence; registers one cron job per
            # user with cadence != off. Same scheduler instance as the morning
            # brief; jobs re-register on each startup.
            from app.services.proposal_cadence import register_all_cadence_jobs

            await register_all_cadence_jobs(scheduler.scheduler, session_factory)
            logger.info("proposal_cadence_jobs_registered")

            # 10g. Proposal backtest-eval reconcile (P6 §2b-backtest). Singleton
            # cron (every minute) that detects completed baseline/variant
            # backtests (via BacktestJob.result_id) and writes the verdict into
            # the proposal's evaluation_results_json.
            from app.services.proposal_evaluation import (
                register_proposal_evaluation_reconcile_job,
            )

            register_proposal_evaluation_reconcile_job(
                scheduler.scheduler, session_factory
            )
            logger.info("proposal_evaluation_reconcile_registered")

            # 10h. Proposal human-review sampling (P6 §2b-review). Singleton
            # weekly cron (Mon 09:00 ET) that samples 10% of the past week's
            # terminal-state proposals for qualitative human review (Decision 8
            # supplement). Same scheduler instance; de-dups against already
            # sampled, merge-writes the human_review sub-key.
            from app.services.proposal_review_sampling import (
                register_proposal_review_sampling_job,
            )

            register_proposal_review_sampling_job(
                scheduler.scheduler, session_factory
            )
            logger.info("proposal_review_sampling_registered")

            # 10i. Paper-variant expiry (P6b §2a). 6-hourly sweep that
            # force-terminates PAPER_VARIANT clones older than 90 days (D6 safety
            # net for orphaned variants). Needs the engine to unregister them.
            from app.services.paper_variant import register_paper_variant_expiry_job

            register_paper_variant_expiry_job(
                scheduler.scheduler, session_factory, strategy_engine
            )
            logger.info("paper_variant_expiry_registered")

            # 11. BarStreamService (P4 §8). Built AFTER the engine so we can
            # wire it back via set_bar_stream_service before any strategy
            # registers — register() fires on_strategies_changed() which the
            # service needs to be reachable for.
            bar_stream_service = BarStreamService(
                session_factory=session_factory,
                engine=strategy_engine,
                bar_cache=bar_cache,
                bus=bus,
            )
            strategy_engine.set_bar_stream_service(bar_stream_service)
            await bar_stream_service.start()

            # Stash for request handlers / tests
            app.state.alpaca_adapter = adapter
            app.state.asset_sync = asset_sync
            app.state.account_sync = account_sync
            app.state.position_sync = position_sync
            app.state.scheduler = scheduler
            app.state.trade_stream = trade_stream
            app.state.risk_engine = risk_engine
            app.state.broker_registry = broker_registry
            app.state.order_router = order_router
            app.state.position_recomputer = position_recomputer
            app.state.trade_update_consumer = trade_update_consumer
            app.state.bar_cache = bar_cache
            app.state.indicator_computer = indicator_computer
            app.state.strategy_engine = strategy_engine
            app.state.backtest_worker = backtest_worker
            app.state.bar_stream_service = bar_stream_service

            # P4 §4: hot-reload watcher. Independent of the engine — it only
            # marks DB rows + publishes bus events when a .py file under
            # strategies_user/ changes. Started here so it parallels the
            # engine in production paths; tests with alpaca disabled get
            # neither, and construct the watcher directly when needed.
            strategy_file_watcher = StrategyFileWatcher(
                root=Path("strategies_user"),
                session_factory=session_factory,
                bus=bus,
            )
            await strategy_file_watcher.start()
            app.state.strategy_file_watcher = strategy_file_watcher

            # Initial sync pass (each call wraps its own try/except internally)
            await scheduler.run_startup_sync()

            # Resume-on-boot: re-register strategies that were active before
            # the last shutdown. Best-effort — a single broken strategy
            # shouldn't take down boot.
            from sqlalchemy import select

            from app.db.enums import ENGINE_RUNNABLE_STATUSES
            from app.db.models.strategy import Strategy as StrategyRow

            async with session_factory() as resume_session:
                # P6b §2a: ENGINE_RUNNABLE_STATUSES (⊃ ACTIVE) so PAPER_VARIANT
                # clones resume after a restart, like any running strategy.
                rows_to_resume = (
                    await resume_session.execute(
                        select(StrategyRow).where(
                            StrategyRow.status.in_(list(ENGINE_RUNNABLE_STATUSES))
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

        # P3 §3: AgentRuntime is always constructed, regardless of
        # alpaca-startup status — it talks to Anthropic, not Alpaca.
        # Empty ANTHROPIC_API_KEY is fine at construction time; the
        # runtime refuses at start_session with a clear message. Stateless
        # across sessions, so no shutdown hook needed (the per-session
        # locks dict is dropped when the process exits).
        agent_runtime = AgentRuntime(
            settings=get_settings(),
            session_factory=get_sessionmaker(),
            bus=get_event_bus(),
        )
        app.state.agent_runtime = agent_runtime

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
        # Stop the file watcher first — it owns an inotify (or equivalent)
        # descriptor and shouldn't be racing the engine teardown to mark
        # rows as pending_reload.
        if strategy_file_watcher is not None:
            try:
                await strategy_file_watcher.stop()
            except Exception:
                logger.exception("strategy_file_watcher_stop_failed")
        # Stop the bar stream before the engine so an in-flight bar
        # dispatch doesn't race with the engine going away.
        if bar_stream_service is not None:
            try:
                await bar_stream_service.stop()
            except Exception:
                logger.exception("bar_stream_service_stop_failed")
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
        # P5 §2: disconnect per-account adapters BEFORE the explicit adapter
        # disconnect below. The startup paper adapter is shared (registered in
        # the registry AND held as `adapter`); close_all() disconnects it, and
        # the adapter.disconnect() that follows is an idempotent no-op.
        if broker_registry is not None:
            try:
                broker_registry.close_all()
            except Exception:
                logger.exception("broker_registry_close_failed")
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
