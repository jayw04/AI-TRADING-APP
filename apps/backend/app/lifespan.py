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

            # Broker registry constructed early so AccountSyncService can sync EVERY
            # account via its own per-user adapter (P13.5 multi-account). load_all() +
            # adopt_startup_adapter() below populate + connect the adapters before the
            # scheduler's first sync_all tick.
            broker_registry = BrokerRegistry(session_factory)

            asset_sync = AssetSyncService(adapter, session_factory, bus)
            account_sync = AccountSyncService(
                adapter, session_factory, bus, broker_registry=broker_registry
            )
            position_sync = PositionSyncService(
                adapter, session_factory, bus, broker_registry=broker_registry
            )

            scheduler = WorkbenchScheduler(
                asset_sync, account_sync, position_sync,
                enabled=settings.scheduler_enabled,
            )
            scheduler.start()

            # Single-active-scheduler heartbeat (ADR 0032). Record this host's arm
            # state at boot (so a DISARMED standby is visible too); on an armed host,
            # refresh it every 30s. Best-effort — never blocks boot or scheduling.
            from app.jobs.scheduler_heartbeat import (
                resolve_host_id,
                run_scheduler_heartbeat,
                write_startup_heartbeat,
            )

            _host_id = resolve_host_id()
            await write_startup_heartbeat(
                session_factory, _host_id, armed=settings.scheduler_enabled
            )
            if settings.scheduler_enabled:
                scheduler.scheduler.add_job(
                    run_scheduler_heartbeat,
                    trigger="interval",
                    seconds=30,
                    id="scheduler_heartbeat",
                    max_instances=1,
                    coalesce=True,
                    replace_existing=True,
                    kwargs={"session_factory": session_factory, "host_id": _host_id},
                )
                logger.info("scheduler_heartbeat_scheduled", host_id=_host_id)

            # 5. Trade Updates WebSocket (P1 Session 3)
            trade_stream = TradeUpdatesStream(adapter.credentials, bus)
            await trade_stream.start()

            # 6. Broker Registry + Risk Engine + Order Router
            #    (P1 Session 5 Phase A; registry added P5 §2; risk engine gets
            #    the registry + bus in P5 §5 for the new account-level gates).
            #
            # P5 §2: one adapter per account, selected by AccountMode. load_all()
            # builds a per-user adapter for each account from that user's own
            # encrypted credentials (network-free). adopt_startup_adapter() then
            # reuses the already-connected startup paper adapter ONLY for the
            # account whose creds match it, and connects each OTHER paper
            # account's own per-user adapter (§5a — Range Trader activation).
            # This ensures a second paper account (e.g. ALPACA_PAPER_1 under a
            # different user) trades its OWN Alpaca account, not the startup one.
            # Live accounts (none exist yet) get a paper=False adapter from
            # load_all(), but the OrderRouter's §1 BrokerModeError guard
            # short-circuits before the registry is consulted for them.
            await broker_registry.load_all()
            await broker_registry.adopt_startup_adapter(adapter)

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

            # 8b. Factor accessor (P9 §2). Read-only PIT factor data for
            # strategies. Provisioned only if the DuckDB factor store has been
            # ingested; otherwise disabled (ctx.factors raises
            # FactorDataUnavailable) — degrade, don't crash the engine. A locked
            # store (mid-ingest) also degrades to disabled rather than failing boot.
            from app.factor_data.accessor import FactorAccessor
            from app.factor_data.config import resolve_store_path
            from app.factor_data.store import FactorDataStore

            factor_store_path = resolve_store_path()
            # Keep the store handle in app scope for infrastructure jobs (the
            # premarket activation jobs below). The strategy-facing FactorAccessor
            # deliberately does NOT expose it — that would widen the strategy sandbox
            # (see test_accessor_surface_is_read_only). Infra holds its own reference;
            # strategies only ever see the curated read methods via ctx.factors.
            factor_store: FactorDataStore | None = None
            try:
                if factor_store_path.exists():
                    factor_store = FactorDataStore(read_only=True)
                    factor_accessor: FactorAccessor = FactorAccessor(factor_store)
                    logger.info("factor_accessor_provisioned", path=str(factor_store_path))
                else:
                    factor_accessor = FactorAccessor(None)
                    logger.info("factor_accessor_disabled_no_store", path=str(factor_store_path))
            except Exception as exc:  # noqa: BLE001 — factor data must never block boot
                factor_store = None
                factor_accessor = FactorAccessor(None)
                logger.warning("factor_accessor_unavailable", error=str(exc))

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
                factor_accessor=factor_accessor,
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
                kwargs={
                    "session_factory": session_factory,
                    "bus": bus,
                    "engine": strategy_engine,  # P6b §4.5: register on LIVE
                },
            )
            logger.info("activation_completion_scheduled")

            # P6b §5 (ADR 0006 v2 §5): LLM-opt-in 7-day cooldown completion.
            # 15-min interval; re-registers the strategy so the LLM gate applies.
            from app.jobs.llm_opt_in_completion import run_llm_opt_in_completion

            scheduler.scheduler.add_job(
                run_llm_opt_in_completion,
                trigger="interval",
                minutes=15,
                id="llm_opt_in_completion",
                max_instances=1,
                coalesce=True,
                kwargs={"session_factory": session_factory, "engine": strategy_engine},
            )
            logger.info("llm_opt_in_completion_scheduled")

            # 10c. SCAN-001 Production Validation Gate (gate plan §0; ADR 0024) —
            # forward-evidence accrual. The ~09:25 ET scan persists today's premarket
            # candidate set; the ~16:30 ET back-fill attaches realized outcomes. Both
            # read-only/advisory (no order path) and fail-soft. Scheduler is already
            # America/New_York, so the hours below are ET. Needs the read-only factor
            # store (held in app scope above for exactly this) — no store => skip.
            if factor_store is not None:
                from app.jobs.premarket_gate import (
                    run_premarket_backfill_job,
                    run_premarket_scan_job,
                )

                gate_dir = settings.premarket_gate_evidence_dir
                scheduler.scheduler.add_job(
                    run_premarket_scan_job,
                    trigger="cron",
                    day_of_week="mon-fri",
                    hour=9,
                    minute=25,
                    id="premarket_gate_scan",
                    max_instances=1,
                    coalesce=True,
                    kwargs={"factor_store": factor_store, "directory": gate_dir},
                )
                scheduler.scheduler.add_job(
                    run_premarket_backfill_job,
                    trigger="cron",
                    day_of_week="mon-fri",
                    hour=16,
                    minute=30,
                    id="premarket_gate_backfill",
                    max_instances=1,
                    coalesce=True,
                    kwargs={"bar_cache": bar_cache, "directory": gate_dir},
                )
                logger.info("premarket_gate_scheduled", directory=gate_dir)
            else:
                logger.info("premarket_gate_disabled_no_factor_store")

            # 10c-range. Daily Range-Trader universe auto-select (design §"Top 3–5
            # candidates"). ~09:00 ET weekdays (before the open / the premarket gate),
            # re-point each opted-in range strategy (params_json["auto_select_top_n"] > 0)
            # to today's Top-N candidates: stop → set symbols → start, audit-logged.
            # No-op when no strategy has opted in; fail-soft. Scheduler tz is already ET.
            from app.services.range_auto_select import run_daily_range_universe

            scheduler.scheduler.add_job(
                run_daily_range_universe,
                trigger="cron",
                day_of_week="mon-fri",
                hour=9,
                minute=0,
                id="range_autoselect_daily",
                max_instances=1,
                coalesce=True,
                replace_existing=True,
                kwargs={
                    "session_factory": session_factory,
                    "engine": strategy_engine,
                    "bar_cache": bar_cache,
                },
            )
            logger.info("range_autoselect_scheduled")

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

            # 10c-bis. Continuous circuit-breaker monitor (P10 §6 / review v2 #5).
            # A 60s tick that trips the daily-loss breaker for any account with
            # open positions whose net P&L has breached the limit — catching an
            # overnight/idle drawdown the order-time check() can't see. evaluate()
            # skips already-tripped / no-limit accounts; best-effort (never raises
            # into the scheduler). max_instances=1 + coalesce so a slow pass can't stack.
            from app.jobs.breaker_monitor import run_breaker_monitor

            scheduler.scheduler.add_job(
                run_breaker_monitor,
                trigger="interval",
                seconds=60,
                id="breaker_monitor",
                max_instances=1,
                coalesce=True,
                replace_existing=True,
                kwargs={"session_factory": session_factory, "bus": bus},
            )
            logger.info("breaker_monitor_scheduled")

            # 10c-bis. Broker⇄local reconciliation (P11 §3, ADR 0021). 300s
            # interval. INDEPENDENT fresh broker fetch per account (so it also
            # catches a stalled PositionSync), diffs vs the local positions
            # table, and ALERTS on a discrepancy (audit + metric + a
            # reconciliation_runs row). Read-only + alert-only — never the order
            # path. Resolves each account's own adapter via the registry.
            # max_instances=1 + coalesce so a slow pass can't stack.
            from app.services.reconciliation import run_reconciliation_pass

            scheduler.scheduler.add_job(
                run_reconciliation_pass,
                trigger="interval",
                seconds=300,
                id="reconciliation",
                max_instances=1,
                coalesce=True,
                replace_existing=True,
                kwargs={
                    "session_factory": session_factory,
                    "resolve_broker": broker_registry.get,
                },
            )
            logger.info("reconciliation_scheduled")

            # 10c-ter. Decision replay verifier (P11 §4, ADR 0021). Daily (03:30
            # in the scheduler's timezone). Replays the last 24h of automated
            # decisions from their audit fingerprints, re-verifying each decision
            # against its recorded inputs, and feeds the replay-consistency +
            # coverage KPIs. READ-ONLY verification — never the order path; a
            # mismatch is audit-logged (REPLAY_MISMATCH) + alerted, not corrected.
            # Not per-minute (rescanning the whole log adds no safety). max_instances=1
            # + coalesce so a slow pass can't stack.
            from apscheduler.triggers.cron import CronTrigger as _ReplayCron

            from app.services.replay import run_daily_replay, validate_registry

            # Boot-time consistency check: every SUPPORTED capability has a wired
            # verifier (and vice versa). A drift is a programming error — fail fast
            # here rather than silently miscount coverage at 03:30.
            validate_registry()

            scheduler.scheduler.add_job(
                run_daily_replay,
                _ReplayCron(hour=3, minute=30),
                id="replay",
                max_instances=1,
                coalesce=True,
                replace_existing=True,
                kwargs={"session_factory": session_factory},
            )
            logger.info("replay_scheduled")

            # 10c-quater. Equity-snapshot persistence (P12.5 Production Validation).
            # Appends one equity point per account near market close (16:10 in the
            # scheduler's timezone, America/New_York) so the live book's equity curve
            # accrues for the production-validation report. Read-only beyond its own
            # append; no order path. Best-effort; single-flight + coalesce.
            from app.services.equity_snapshot import run_daily_equity_snapshot

            scheduler.scheduler.add_job(
                run_daily_equity_snapshot,
                _ReplayCron(hour=16, minute=10),
                id="equity_snapshot",
                max_instances=1,
                coalesce=True,
                replace_existing=True,
                kwargs={"session_factory": session_factory},
            )
            logger.info("equity_snapshot_scheduled")

            # 10c-quint. Premarket scan (SCAN-001 increment C; PR #241 activation).
            # Weekdays at 09:25 ET (market opens at 09:30). Records the live premarket
            # gappers candidate set to a dated JSON record for forward evidence accrual.
            # Read-only, fail-soft; requires factor_store to be provisioned.
            # max_instances=1 + coalesce.
            from app.jobs.premarket_scan_scheduled import run_premarket_scan_scheduled

            if factor_store is not None:
                scheduler.scheduler.add_job(
                    run_premarket_scan_scheduled,
                    _ReplayCron(day_of_week="mon-fri", hour=9, minute=25),
                    id="premarket_scan",
                    max_instances=1,
                    coalesce=True,
                    replace_existing=True,
                    kwargs={
                        "bar_cache": bar_cache,
                        "factor_store": factor_store,
                    },
                )
                logger.info("premarket_scan_scheduled")
            else:
                logger.info("premarket_scan_skipped", reason="factor_store_unavailable")

            # 10c-sext. Premarket backfill (SCAN-001 increment D; PR #241 activation).
            # Weekdays at 16:30 ET (after market close). Fetches realized intraday
            # outcomes for today's premarket candidates from BarCache, back-fills the
            # evidence record, and persists. Pure back-fill, read-only, fail-soft.
            # max_instances=1 + coalesce.
            from app.jobs.premarket_backfill_scheduled import run_premarket_backfill_scheduled

            scheduler.scheduler.add_job(
                run_premarket_backfill_scheduled,
                _ReplayCron(day_of_week="mon-fri", hour=16, minute=30),
                id="premarket_backfill",
                max_instances=1,
                coalesce=True,
                replace_existing=True,
                kwargs={"bar_cache": bar_cache},
            )
            logger.info("premarket_backfill_scheduled")

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

            # 10e-bis. Scheduled Discovery scans (P8 §4). A 15-min tick that runs
            # each user's `scheduled` scans once their configured
            # discovery_scan_time (trading_profile, default 7:30 ET) has passed
            # today — idempotent per (user, date). The tick-and-check pattern
            # (not a fixed CronTrigger) honors the per-user configurable time and
            # survives the server being down at the exact minute. Reuses the bar
            # cache + indicator computer built above.
            from app.jobs.scheduled_scans import run_scheduled_scans

            scheduler.scheduler.add_job(
                run_scheduled_scans,
                trigger="interval",
                minutes=15,
                id="scheduled_scans",
                max_instances=1,
                coalesce=True,
                replace_existing=True,
                kwargs={
                    "session_factory": session_factory,
                    "bar_cache": bar_cache,
                    "indicator_computer": indicator_computer,
                },
            )
            logger.info("scheduled_scans_scheduled")

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

            # 10g. Promotion cooldown completion (P6b §3b, ADR 0007). Every 15
            # min, flip PROMOTING → PROMOTED for proposals whose 24h cooldown has
            # elapsed (params merge + last_promoted_at + variant terminate). Needs
            # the engine to unregister the promoted variant.
            from app.jobs.promotion_completion import run_promotion_completion

            scheduler.scheduler.add_job(
                run_promotion_completion,
                trigger="interval",
                minutes=15,
                id="promotion_completion",
                max_instances=1,
                coalesce=True,
                kwargs={
                    "session_factory": session_factory,
                    "engine": strategy_engine,
                },
            )
            logger.info("promotion_completion_scheduled")

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

            # Resume-on-boot (P11 §5, ADR 0021 property 3): re-register strategies
            # that were active before the last shutdown. Extracted into the recovery
            # service so it is testable + instrumented (recovery_* metrics). Idempotent
            # (engine.register is a no-op if already registered) and best-effort — a
            # single broken strategy shouldn't take down boot. P6b §2a:
            # ENGINE_RUNNABLE_STATUSES (⊃ ACTIVE) so PAPER_VARIANT clones resume too.
            from app.services.recovery import resume_strategies_on_boot

            # ADR 0032: a DISARMED standby registers NO strategies, so the engine
            # has nothing to dispatch even if something started the scheduler.
            if settings.scheduler_enabled:
                await resume_strategies_on_boot(session_factory, strategy_engine)
            else:
                logger.warning(
                    "resume_strategies_skipped_disarmed",
                    reason="WORKBENCH_SCHEDULER_ENABLED=false",
                )
        else:
            logger.info("alpaca_startup_disabled")

        # P3 §3: AgentRuntime is always constructed, regardless of
        # alpaca-startup status — it talks to Anthropic, not Alpaca.
        # Empty ANTHROPIC_API_KEY is fine at construction time; the
        # runtime refuses at start_session with a clear message. Stateless
        # across sessions, so no shutdown hook needed (the per-session
        # locks dict is dropped when the process exits).
        _agent_settings = get_settings()
        agent_runtime = AgentRuntime(
            settings=_agent_settings,
            session_factory=get_sessionmaker(),
            bus=get_event_bus(),
            # Empty AGENT_MCP_SERVER_URL disables the server-side MCP connector
            # (pure-chat agent) — required locally without a public tunnel, since
            # Anthropic dispatches the URL from its own servers and 400s if it
            # can't reach 127.0.0.1. See app/config.py:agent_mcp_server_url.
            mcp_server_url=_agent_settings.agent_mcp_server_url or None,
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
