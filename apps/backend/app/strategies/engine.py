"""StrategyEngine — register / unregister / dispatch.

Owns:

- A dict ``{strategy_id: RunningStrategy}`` of currently-active strategies.
- A handle to the APScheduler instance for cron-scheduled on_bar dispatch.
- Long-lived asyncio tasks consuming the event bus topics
  ``fill.created`` and ``signal.new`` (the bus is generator-style, so the
  engine bridges into callback dispatch).

On ``register()``:

  1. Load the Strategy class via :class:`StrategyLoader`.
  2. Construct :class:`StrategyContext` bound to this strategy_id.
  3. Construct the Strategy instance, call ``on_init``.
  4. If ``schedule != "event"``, add an APScheduler job for ``on_bar``.
  5. Open a ``StrategyRun`` row (started_at=now, status=PAPER).
  6. Transition ``strategies.status`` to PAPER.

On uncaught exception from user code:

  - Log audit, transition ``strategies.status`` to ERROR, write
    ``error_text``, close the ``StrategyRun``, drop from ``_running``.
  - The engine keeps running for every other strategy.

On ``unregister()``:

  - Cancel the APScheduler job.
  - Call ``on_shutdown`` (best-effort; exceptions are swallowed).
  - Close the ``StrategyRun`` row.
  - Transition ``strategies.status`` to IDLE (unless it was just set to
    ERROR by the exception path).
"""

from __future__ import annotations

import asyncio
import contextlib
import time
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import structlog
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.audit import AuditAction, AuditActorType, AuditLogger
from app.db.enums import (
    ENGINE_RUNNABLE_STATUSES,
    StrategyStatus,
    StrategyType,
)
from app.db.enums import (
    SignalType as SignalTypeEnum,
)
from app.db.models import strategy_slot_claim as slot_claim
from app.db.models.account import Account, AccountMode
from app.db.models.strategy import Strategy as StrategyRow
from app.db.models.strategy_run import StrategyRun
from app.events.bus import EventBus
from app.market.session import MarketSession
from app.ops.dispatch_health import (
    DispatchHealth,
    DispatchSnapshot,
    evaluate_dispatch_health,
    stale_dispatch,
)

from .base import Strategy
from .context import Bar, FillEvent, SignalEvent, StrategyContext
from .hold_service import StrategyOnHold, read_hold, record_activation_blocked
from .loader import StrategyLoader, StrategyLoadError

logger = structlog.get_logger(__name__)


EVENT_SCHEDULE_SENTINEL = "event"

# P11 ops: how often the dispatch-liveness monitor runs (minutes).
DISPATCH_HEALTH_CHECK_MINUTES = 5

# Standard crontab day-of-week is 0/7=Sunday, 1=Monday … 6=Saturday. APScheduler's
# CronTrigger numbers day_of_week 0=Monday … 6=Sunday and `from_crontab` does NOT
# remap — so a numeric dow like "1" is read as Tuesday, silently shifting every
# weekly strategy by a day. We translate numeric dow tokens to unambiguous day
# NAMES (which APScheduler interprets identically to cron) before scheduling.
_CRON_DOW_NAMES = {0: "sun", 1: "mon", 2: "tue", 3: "wed", 4: "thu", 5: "fri", 6: "sat", 7: "sun"}

# Strategy schedules are EASTERN-TIME (market clock). The WorkbenchScheduler is an
# AsyncIOScheduler(timezone="America/New_York") and StrategyEngine shares that instance,
# BUT ``CronTrigger.from_crontab(expr)`` with no timezone= defaults to the process-local
# tz (UTC in the container) — silently overriding the scheduler's ET tz. That made a
# ``0 14 * * mon`` schedule fire at 14:00 UTC = 10:00 ET in summer but 09:00 ET in winter,
# drifting vs the 09:30 market open across DST. Pinning from_crontab to ET keeps every
# strategy schedule on the market clock year-round (and consistent with the scheduler's
# own ET jobs). Schedule STRINGS are therefore ET-hour values (e.g. "0 10" = 10:00 ET).
_STRATEGY_SCHEDULE_TZ = ZoneInfo("America/New_York")


def _normalize_crontab_dow(expr: str) -> str:
    """Rewrite numeric day-of-week tokens in a 5-field crontab to day names so
    ``CronTrigger.from_crontab`` honors standard cron semantics (0/7=Sun, 1=Mon).

    Handles single values, comma lists, and ranges (``1``, ``1,3,5``, ``1-5``).
    Fields other than day-of-week are untouched, and a dow field containing a
    wildcard or step (``*``, ``*/2``) is passed through unchanged (no day-name
    ambiguity to resolve there). A non-5-field expression is returned as-is so
    ``from_crontab`` raises on it exactly as before.
    """
    parts = expr.split()
    if len(parts) != 5:
        return expr
    dow = parts[4]
    if "*" in dow or "/" in dow:
        return expr

    def _token(tok: str) -> str:
        names: list[str] = []
        for n in tok.split("-"):  # single value or range endpoints
            if n.isdigit() and 0 <= int(n) <= 7:
                names.append(_CRON_DOW_NAMES[int(n)])
            else:
                return tok  # not a clean numeric token → leave it for from_crontab
        return "-".join(names)

    parts[4] = ",".join(_token(item) for item in dow.split(","))
    return " ".join(parts)


@dataclass
class RunningStrategy:
    """A live strategy instance the engine is dispatching to."""

    strategy_id: int
    instance: Strategy
    job_id: str | None  # APScheduler job id (None for event-driven)
    run_id: int  # StrategyRun row id
    symbols: list[str]
    timeframe: str  # for periodic on_bar dispatch
    schedule: str  # cron expression or "event" — drives WS vs cron path
    overlay_job_id: str | None = None  # P10 §2: APScheduler id for the daily overlay tick (None = no overlay)
    last_dispatch_at: float | None = None  # epoch secs of the last successful on_bar (P11 dispatch-liveness)


class StrategyEngine:
    """Lifecycle owner. One instance per backend process."""

    def __init__(
        self,
        scheduler: AsyncIOScheduler,
        session_factory: async_sessionmaker[AsyncSession],
        bus: EventBus,
        bar_cache: Any,  # BarCache (P2 Session 1)
        indicator_computer: Any,  # IndicatorComputer (P2 Session 1)
        order_router: Any,  # OrderRouter (P1)
        strategies_root: Path,
        factor_accessor: Any | None = None,  # FactorAccessor (P9 §2); None = disabled
    ) -> None:
        self._scheduler = scheduler
        self._session_factory = session_factory
        self._bus = bus
        self._bar_cache = bar_cache
        self._indicator_computer = indicator_computer
        self._order_router = order_router
        self._loader = StrategyLoader(strategies_root)
        # P9 §2: read-only PIT factor accessor handed to every StrategyContext.
        # None = factor data not provisioned; ctx.factors raises FactorDataUnavailable.
        self._factor_accessor = factor_accessor
        # §9A market-session gate — consulted before every on_bar dispatch so a
        # strategy never acts outside its permitted session (RTH-only unless it
        # sets allow_extended_hours). Shares a per-day schedule cache.
        self._market_session = MarketSession()

        self._running: dict[int, RunningStrategy] = {}
        # Optional handle to BarStreamService (P4 §8). Wired post-construction
        # by lifespan via set_bar_stream_service() so the service can be
        # constructed AFTER the engine.
        self._bar_stream_service: Any | None = None

        # The bus is generator-style; spawn one task per topic that runs the
        # async-for loop and dispatches to our handler. Same pattern as
        # TradeUpdateConsumer.
        self._fill_task: asyncio.Task[None] = asyncio.create_task(
            self._consume_topic("fill.created", self._on_fill_event),
            name="strategy-engine:fill.created",
        )
        self._signal_task: asyncio.Task[None] = asyncio.create_task(
            self._consume_topic("signal.new", self._on_signal_event),
            name="strategy-engine:signal.new",
        )
        self._started_at = time.time()  # P11 dispatch-liveness: engine uptime baseline
        # ADR 0044 inv 5-7: a per-process token identifies THIS engine run so a
        # boot loop's repeated register attempts for a held strategy dedup to one
        # STRATEGY_ACTIVATION_BLOCKED_BY_HOLD event; a restart (new token) re-alerts.
        self._run_token = uuid.uuid4().hex
        # P11 ops: periodically flag an active bar-driven strategy that has stopped being
        # dispatched during RTH (the silent-inertness guard — read-only, never trades).
        with contextlib.suppress(Exception):
            self._scheduler.add_job(
                self._dispatch_health_monitor_tick,
                "interval",
                minutes=DISPATCH_HEALTH_CHECK_MINUTES,
                id="ops:dispatch_health_monitor",
                replace_existing=True,
                max_instances=1,
                coalesce=True,
            )
        logger.info("strategy_engine_started")

    async def shutdown(self) -> None:
        """Unregister everything and stop the bus consumers."""
        for sid in list(self._running.keys()):
            try:
                await self.unregister(sid, reason="engine_shutdown")
            except Exception:
                logger.exception(
                    "strategy_unregister_failed_on_shutdown", strategy_id=sid
                )

        for task in (self._fill_task, self._signal_task):
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await task
        logger.info("strategy_engine_stopped")

    # ---- introspection ----

    def get_params_schema(self, strategy_id: int) -> dict[str, Any] | None:
        """Return the in-memory ``params_schema`` for a currently-registered
        strategy, or ``None`` if the strategy isn't registered or its class
        didn't declare a schema (P4 §7).

        Schema is read fresh off ``type(instance)`` so a future hot-reload
        (P4 §4) sees new schemas without re-binding the engine.
        """
        running = self._running.get(strategy_id)
        if running is None:
            return None
        schema = getattr(type(running.instance), "params_schema", None)
        if not isinstance(schema, dict):
            return None
        return schema

    def running_strategies(self) -> list[RunningStrategy]:
        """Read-only snapshot of the currently-dispatching strategies (P11 §1 ops state).

        Each :class:`RunningStrategy` carries the live merged ``instance.params`` and the
        APScheduler ``job_id``/``overlay_job_id`` — the truth of *what is running on a book
        right now*, which the operational-state resolver reads to derive Enabled/Healthy."""
        return list(self._running.values())

    def dispatch_health(self) -> list[DispatchHealth]:
        """P11 ops — per-strategy dispatch liveness (read-only). Flags an active bar-driven
        strategy that has stopped receiving ``on_bar`` during RTH (silent inertness), the
        failure that left the Range Trader idle for weeks while the engine was down."""
        now = time.time()
        is_regular = self._market_session.classify().is_regular
        snaps = [
            DispatchSnapshot(
                strategy_id=r.strategy_id,
                name=getattr(r.instance, "name", None) or f"strategy:{r.strategy_id}",
                schedule=r.schedule,
                timeframe=r.timeframe,
                last_dispatch_at=r.last_dispatch_at,
            )
            for r in self._running.values()
        ]
        return evaluate_dispatch_health(
            snaps, now=now, is_regular_session=is_regular,
            engine_uptime_s=now - self._started_at,
        )

    def scheduler_has_job(self, job_id: str) -> bool:
        """Whether an APScheduler job is currently registered (P11 §1 — detects infra
        actors like the §6 ``breaker_monitor``, which run on this same scheduler)."""
        try:
            return self._scheduler.get_job(job_id) is not None
        except Exception:
            return False

    # ---- registration ----

    async def _block_if_on_hold(self, strategy_id: int, *, source: str) -> None:
        """Fail-closed operational-hold guard (ADR 0044 inv 5-7). This is the single
        authoritative activation choke — every ``register()`` caller inherits it.

        - ACTIVE hold  -> record a deduped ``STRATEGY_ACTIVATION_BLOCKED_BY_HOLD`` in
          its OWN transaction, then raise :class:`StrategyOnHold`.
        - absent / CLEARED -> allow.
        - malformed / unreadable (``HoldStateInvalid`` / ``HoldStoreUnavailable``) ->
          propagate, so a hold that cannot be trusted ALSO blocks. An unreadable hold
          is never read as "no hold".
        """
        async with self._session_factory() as session:
            rec = await read_hold(session, strategy_id)  # Invalid/Unavailable -> block
        if rec is None or not rec.is_active:
            return
        async with self._session_factory() as session, session.begin():
            await record_activation_blocked(
                session, strategy_id=strategy_id, reason_code=rec.reason_code,
                hold_rev=rec.rev, source=source, run_id=self._run_token,
            )
        raise StrategyOnHold(strategy_id, rec.reason_code, rec.rev)

    async def register(self, strategy_id: int) -> RunningStrategy:
        """Load, instantiate, and start dispatching to a strategy.

        Idempotent: if the strategy is already registered, returns the
        existing :class:`RunningStrategy`.
        """
        if strategy_id in self._running:
            return self._running[strategy_id]

        # ADR 0044 inv 5-7: activation choke. An already-running strategy short-
        # circuits above (a hold blocks ACTIVATION, not a live book); everything past
        # here is a fresh activation and must clear the operational hold, fail-closed.
        await self._block_if_on_hold(strategy_id, source="engine.register")

        instance: Strategy
        symbols: list[str]
        merged_params: dict[str, Any]
        cls: type[Strategy]
        schedule: str

        async with self._session_factory() as session:
            row = await session.get(StrategyRow, strategy_id)
            if row is None:
                raise StrategyLoadError(f"strategy_id={strategy_id} not found")
            if row.type != StrategyType.PYTHON:
                raise StrategyLoadError(
                    f"strategy_id={strategy_id} is type {row.type.value}; "
                    "only PYTHON is dispatched in P2"
                )

            # P6b §4.5 (ADR 0015): resolve the dispatch account by STATUS — a
            # LIVE strategy auto-dispatches to the live account; PAPER and
            # PAPER_VARIANT keep the paper path (byte-identical). A LIVE strategy
            # with no live account cannot dispatch → ERROR (not a silent paper
            # fallback, which would place orders on the wrong account).
            account_mode = (
                AccountMode.live
                if row.status == StrategyStatus.LIVE
                else AccountMode.paper
            )
            account = (
                await session.execute(
                    select(Account).where(
                        Account.user_id == row.user_id,
                        Account.broker == "alpaca",
                        Account.mode == account_mode,
                    )
                )
            ).scalars().first()
            if account is None:
                await self._mark_error(session, row, f"no_{account_mode.value}_account")
                await session.commit()
                raise StrategyLoadError(
                    f"no {account_mode.value} account for user_id={row.user_id}"
                )

            try:
                cls = self._loader.load(row.code_path or "")
            except StrategyLoadError:
                await self._mark_error(session, row, "loader_failed")
                await session.commit()
                raise

            symbols = list(row.symbols_json) or list(cls.symbols)
            merged_params = {**cls.default_params, **(row.params_json or {})}

            # P6b §4 (ADR 0006 v2): a Mode-A eval-harness clone runs the
            # deterministic strategy but its order submission is WRAPPED — each
            # intent also drives an LLM act/skip decision for Mode B. The wrapper
            # still calls OrderRouter.submit (ADR 0002); the Anthropic import
            # lives only in the allowlisted eval_harness module.
            submit_order_fn: Any = self._order_router.submit
            if row.harness_role == "mode_a":
                from app.db.models.eval_harness import (
                    HARNESS_TERMINATED,
                    EvalHarness,
                )
                from app.services.eval_harness.gate import make_harness_submit_fn

                harness = (
                    await session.execute(
                        select(EvalHarness)
                        .where(EvalHarness.mode_a_strategy_id == row.id)
                        .where(EvalHarness.state != HARNESS_TERMINATED)
                    )
                ).scalars().first()
                if harness is not None:
                    submit_order_fn = make_harness_submit_fn(
                        harness_id=harness.id,
                        mode_a_id=row.id,
                        mode_b_id=harness.mode_b_strategy_id,
                        user_id=row.user_id,
                        real_submit=self._order_router.submit,
                        session_factory=self._session_factory,
                    )

            # P6b §4.5/§5: a LIVE strategy's live submit is composed of (innermost
            # first) OrderRouter.submit → [§5 LLM act/skip gate, only if opted in]
            # → [§4.5 master-switch suppressor, OUTERMOST]. Master switch outermost
            # means an off switch returns before the LLM is ever consulted (no call,
            # no cost). ADR 0002 stays intact — both wraps still call OrderRouter.submit.
            if row.status == StrategyStatus.LIVE:
                inner = submit_order_fn
                # P6b §5 (ADR 0006 v2 §5): opted-in LIVE strategy → LLM gate.
                from app.services.llm_live_gate.gate import (
                    find_active_opt_in,
                    make_live_llm_submit_fn,
                )

                opt_in = await find_active_opt_in(session, row.id)
                if opt_in is not None:
                    inner = make_live_llm_submit_fn(
                        strategy_id=row.id,
                        user_id=row.user_id,
                        real_submit=inner,
                        session_factory=self._session_factory,
                    )
                # P6b §4.5 (ADR 0015): master-switch suppressor, outermost.
                from app.services.live_autodispatch import (
                    make_live_autodispatch_submit_fn,
                )

                submit_order_fn = make_live_autodispatch_submit_fn(
                    strategy_id=row.id,
                    real_submit=inner,
                    session_factory=self._session_factory,
                )

            ctx = StrategyContext(
                strategy_id=row.id,
                user_id=row.user_id,
                account_id=account.id,
                symbols=symbols,
                session_factory=self._session_factory,
                bar_cache=self._bar_cache,
                indicator_computer=self._indicator_computer,
                submit_order_fn=submit_order_fn,
                bus=self._bus,
                factor_accessor=self._factor_accessor,
            )
            try:
                instance = cls(ctx=ctx, params=merged_params)
            except Exception as exc:
                await self._mark_error(session, row, f"construct_failed: {exc}")
                await session.commit()
                raise

            try:
                await instance.on_init()
            except Exception as exc:
                await self._mark_error(session, row, f"on_init_failed: {exc}")
                await session.commit()
                raise

            # ADR 0044 boundary recheck: a hold placed while this strategy was loading
            # (load + on_init are not instantaneous) must still block. Re-check right
            # before the run becomes authoritative — closes the register-time TOCTOU.
            await self._block_if_on_hold(strategy_id, source="engine.register")

            now = datetime.now(UTC)
            # P6b §4.5 (ADR 0015): a LIVE strategy stays LIVE through registration
            # so it dispatches against the live account (pre-§4.5 this forced
            # PAPER, which is why live auto-dispatch never worked).
            # P6b §2a: a clone (parent_strategy_id set) runs as PAPER_VARIANT so
            # it's engine-runnable but excluded from user-facing "active" surfaces.
            if row.status == StrategyStatus.LIVE:
                run_status = StrategyStatus.LIVE
            elif row.parent_strategy_id is not None:
                run_status = StrategyStatus.PAPER_VARIANT
            else:
                run_status = StrategyStatus.PAPER
            run = StrategyRun(
                strategy_id=row.id,
                started_at=now,
                status=run_status,
            )
            session.add(run)
            await session.commit()
            await session.refresh(run)
            run_id = run.id

            row.status = run_status
            row.error_text = None
            row.updated_at = now
            await self._audit(
                session,
                user_id=row.user_id,
                action=AuditAction.STRATEGY_REGISTERED,
                target_id=row.id,
                payload={"run_id": run_id, "name": cls.name, "symbols": symbols},
            )
            await session.commit()
            schedule = row.schedule

        # Schedule periodic bar dispatch (event-driven strategies skip this).
        job_id: str | None = None
        if schedule != "event":
            job_id = f"strategy:{strategy_id}:on_bar"
            try:
                cron = CronTrigger.from_crontab(
                    _normalize_crontab_dow(schedule), timezone=_STRATEGY_SCHEDULE_TZ
                )
            except Exception:
                logger.warning(
                    "strategy_schedule_invalid_falling_back",
                    strategy_id=strategy_id,
                    schedule=schedule,
                )
                cron = CronTrigger.from_crontab("*/1 * * * *", timezone=_STRATEGY_SCHEDULE_TZ)
            self._scheduler.add_job(
                self._dispatch_bar_tick,
                cron,
                kwargs={"strategy_id": strategy_id},
                id=job_id,
                replace_existing=True,
                max_instances=1,
                coalesce=True,
            )

        # P10 §2 (ADR 0020): optional SECOND cadence for a daily gross-exposure overlay,
        # independent of the on_bar schedule. Opt-in / default-off: the overlay job is
        # registered only when ``use_daily_overlay`` is truthy AND a cadence is set
        # (param ``daily_overlay_schedule`` overrides the class default). single-flight
        # (max_instances=1 + coalesce) so a slow/duplicate fire can't stack — the
        # idempotency half of ADR 0021's recurring-action contract.
        overlay_job_id: str | None = None
        overlay_schedule = (
            merged_params.get("daily_overlay_schedule")
            or getattr(cls, "daily_overlay_schedule", None)
        )
        if merged_params.get("use_daily_overlay") and overlay_schedule:
            overlay_job_id = f"strategy:{strategy_id}:overlay"
            try:
                overlay_cron = CronTrigger.from_crontab(
                    _normalize_crontab_dow(str(overlay_schedule)), timezone=_STRATEGY_SCHEDULE_TZ
                )
            except Exception:
                logger.warning(
                    "strategy_overlay_schedule_invalid_skipping",
                    strategy_id=strategy_id,
                    daily_overlay_schedule=overlay_schedule,
                )
                overlay_job_id = None
            if overlay_job_id is not None:
                self._scheduler.add_job(
                    self._dispatch_overlay_tick,
                    overlay_cron,
                    kwargs={"strategy_id": strategy_id},
                    id=overlay_job_id,
                    replace_existing=True,
                    max_instances=1,
                    coalesce=True,
                )

        running = RunningStrategy(
            strategy_id=strategy_id,
            instance=instance,
            job_id=job_id,
            run_id=run_id,
            symbols=symbols,
            timeframe=merged_params.get("timeframe", "1Min"),
            schedule=schedule,
            overlay_job_id=overlay_job_id,
        )
        self._running[strategy_id] = running
        logger.info(
            "strategy_registered",
            strategy_id=strategy_id,
            name=cls.name,
            symbols=symbols,
            schedule=schedule,
        )

        await self._bus.publish(
            "strategy.status_changed",
            {"strategy_id": strategy_id, "status": run_status.value},
        )
        await self._bus.publish(
            "strategy.run_started",
            {
                "strategy_id": strategy_id,
                "run_id": run_id,
                "started_at": now.isoformat(),
                "symbols": symbols,
            },
        )
        await self._notify_bar_stream_changed()
        return running

    async def unregister(
        self,
        strategy_id: int,
        *,
        reason: str = "user_stop",
    ) -> None:
        """Cancel the scheduled job, call ``on_shutdown``, close the run,
        transition to IDLE.

        Idempotent: unregistering an unknown strategy is a no-op.
        """
        running = self._running.pop(strategy_id, None)
        if running is None:
            return

        for jid in (running.job_id, running.overlay_job_id):
            if not jid:
                continue
            try:
                self._scheduler.remove_job(jid)
            except Exception:
                logger.exception(
                    "strategy_remove_job_failed", strategy_id=strategy_id, job_id=jid
                )

        try:
            await running.instance.on_shutdown()
        except Exception:
            logger.exception(
                "strategy_on_shutdown_failed", strategy_id=strategy_id
            )

        closed_run_id: int | None = None
        closed_started_at: datetime | None = None
        closed_ended_at: datetime | None = None
        async with self._session_factory() as session:
            now = datetime.now(UTC)
            run = await session.get(StrategyRun, running.run_id)
            if run is not None and run.ended_at is None:
                run.ended_at = now
                run.status = StrategyStatus.IDLE
                closed_run_id = run.id
                closed_started_at = run.started_at
                closed_ended_at = run.ended_at
            row = await session.get(StrategyRow, strategy_id)
            # P6b §2a: also reset PAPER_VARIANT → IDLE so a terminated variant
            # isn't re-run on boot (ENGINE_RUNNABLE_STATUSES ⊃ ACTIVE).
            if row is not None and row.status in ENGINE_RUNNABLE_STATUSES:
                row.status = StrategyStatus.IDLE
                row.updated_at = now
            await self._audit(
                session,
                user_id=(row.user_id if row is not None else None),
                action=AuditAction.STRATEGY_UNREGISTERED,
                target_id=strategy_id,
                payload={"reason": reason},
            )
            await session.commit()

        if closed_run_id is not None and closed_ended_at is not None:
            # SQLite drops tz on round-trip even with DateTime(timezone=True);
            # coerce both sides to aware UTC before subtracting.
            ended_aware = (
                closed_ended_at
                if closed_ended_at.tzinfo is not None
                else closed_ended_at.replace(tzinfo=UTC)
            )
            duration_seconds: int | None = None
            if closed_started_at is not None:
                started_aware = (
                    closed_started_at
                    if closed_started_at.tzinfo is not None
                    else closed_started_at.replace(tzinfo=UTC)
                )
                duration_seconds = int(
                    (ended_aware - started_aware).total_seconds()
                )
            await self._bus.publish(
                "strategy.run_ended",
                {
                    "strategy_id": strategy_id,
                    "run_id": closed_run_id,
                    "ended_at": ended_aware.isoformat(),
                    "duration_seconds": duration_seconds,
                    "reason": reason,
                },
            )

        await self._bus.publish(
            "strategy.status_changed",
            {
                "strategy_id": strategy_id,
                "status": StrategyStatus.IDLE.value,
                "reason": reason,
            },
        )
        logger.info(
            "strategy_unregistered", strategy_id=strategy_id, reason=reason
        )
        await self._notify_bar_stream_changed()

    # ---- bar stream integration (P4 §8) ----

    def set_bar_stream_service(self, service: Any | None) -> None:
        """Wire the BarStreamService post-construction.

        Lifespan calls this after the service is built so notifications
        flow on subsequent register/unregister calls.
        """
        self._bar_stream_service = service

    async def dispatch_event_bar(self, *, symbol: str, bar: Any) -> None:
        """Called by :class:`BarStreamService` on each bar arrival.

        Fires ``on_bar`` for every running strategy whose ``schedule``
        is ``"event"`` and whose symbols include ``symbol``. Reuses the
        same error-containment as the cron path.
        """
        symbol = symbol.upper()
        for sid, running in list(self._running.items()):
            if running.schedule != EVENT_SCHEDULE_SENTINEL:
                continue
            if symbol not in {s.upper() for s in running.symbols}:
                continue
            # P0: HALTED stops DISPATCH on every path, not just the cron one. An event-driven
            # strategy would otherwise keep firing proposals on each streamed bar — the
            # "spinning at maximum rate" ADR 0004 names, at websocket cadence.
            if not await self._is_dispatchable_now(sid):
                continue
            if not self._dispatch_allowed(running):
                continue
            try:
                event_bar = self._coerce_to_bar(symbol, running.timeframe, bar)
                if event_bar is None:
                    continue
            except Exception:
                logger.exception(
                    "strategy_event_bar_coerce_failed",
                    strategy_id=sid,
                    symbol=symbol,
                )
                continue
            try:
                await running.instance.on_bar(event_bar)
                running.last_dispatch_at = time.time()
            except Exception as exc:
                await self._handle_user_exception(sid, "on_bar", exc)

    async def start_event_fallback(
        self, *, interval_seconds: int = 60
    ) -> str:
        """Activate a recurring fallback that fires ``on_bar`` for every
        event-scheduled strategy at ``interval_seconds``. Used while the
        WS bar stream is disconnected. Returns the APScheduler job id."""
        job_id = f"event_fallback_{int(time.time() * 1000)}"
        self._scheduler.add_job(
            self._fire_all_event_strategies,
            "interval",
            seconds=interval_seconds,
            id=job_id,
            max_instances=1,
            coalesce=True,
        )
        logger.info("strategy_engine_event_fallback_started", job_id=job_id)
        return job_id

    async def stop_event_fallback(self, job_id: str) -> None:
        with contextlib.suppress(Exception):
            self._scheduler.remove_job(job_id)
        logger.info("strategy_engine_event_fallback_stopped", job_id=job_id)

    async def _fire_all_event_strategies(self) -> None:
        """Fallback tick: dispatch every active event-scheduled strategy
        as if a bar just arrived, using the most recent cached bar."""
        for sid, running in list(self._running.items()):
            if running.schedule != EVENT_SCHEDULE_SENTINEL:
                continue
            for symbol in running.symbols:
                try:
                    latest = await self._bar_cache.get_latest_bar(symbol)
                    if latest is None:
                        continue
                    event_bar = self._coerce_to_bar(
                        symbol, running.timeframe, latest
                    )
                    if event_bar is None:
                        continue
                except Exception:
                    logger.exception(
                        "event_fallback_get_bar_failed",
                        strategy_id=sid,
                        symbol=symbol,
                    )
                    continue
                try:
                    await running.instance.on_bar(event_bar)
                    running.last_dispatch_at = time.time()
                except Exception as exc:
                    await self._handle_user_exception(sid, "on_bar", exc)
                    break

    def _coerce_to_bar(
        self,
        symbol: str,
        timeframe: str,
        source: Any,
    ) -> Bar | None:
        """Build a :class:`Bar` from a StreamedBar, dict, or already-Bar.

        Returns ``None`` if ``source`` doesn't carry usable OHLCV fields.
        """
        if isinstance(source, Bar):
            return source
        symbol = symbol.upper()
        # StreamedBar shape (P4 §8): .ts, .open, .high, .low, .close, .volume
        if hasattr(source, "ts") and hasattr(source, "open"):
            try:
                return Bar(
                    symbol=symbol,
                    timeframe=timeframe,
                    t=source.ts,
                    o=float(source.open),
                    h=float(source.high),
                    l=float(source.low),
                    c=float(source.close),
                    v=int(source.volume),
                )
            except Exception:
                return None
        # dict shape (BarCache.get_latest_bar): {t, o, h, l, c, v}
        if isinstance(source, dict):
            try:
                return Bar(
                    symbol=symbol,
                    timeframe=timeframe,
                    t=source["t"],
                    o=float(source["o"]),
                    h=float(source["h"]),
                    l=float(source["l"]),
                    c=float(source["c"]),
                    v=int(source["v"]),
                )
            except Exception:
                return None
        return None

    async def _notify_bar_stream_changed(self) -> None:
        """Ask the bar stream service to recompute its subscription set.

        No-op if no service has been wired (e.g. tests, alpaca-disabled).
        """
        svc = self._bar_stream_service
        if svc is None:
            return
        try:
            await svc.on_strategies_changed()
        except Exception:
            logger.exception("bar_stream_notify_failed")

    # ---- dispatch ----

    def _dispatch_allowed(self, running: RunningStrategy) -> bool:
        """§9A market-session gate: may this strategy act in the current
        session? REGULAR always; pre/after only when its params opt in via
        ``allow_extended_hours``; CLOSED never. Out-of-session ticks are
        skipped (logged, not an error) so open/close guards are enforceable."""
        allow_extended = bool(
            running.instance.params.get("allow_extended_hours", False)
        )
        info = self._market_session.classify()
        if info.dispatchable(allow_extended=allow_extended):
            return True
        logger.info(
            "strategy_dispatch_skipped_out_of_session",
            strategy_id=running.strategy_id,
            session=info.session.value,
            allow_extended=allow_extended,
        )
        return False

    async def _dispatch_bar_tick(self, *, strategy_id: int) -> None:
        """APScheduler-invoked: fetch the latest bar for each of this
        strategy's symbols and call ``on_bar``."""
        running = self._running.get(strategy_id)
        if running is None:
            return

        # ---- P0 (incident 2026-07-13): HALTED must prevent DISPATCH, not merely reject the
        # orders that follow. ADR 0004 says so explicitly ("a strategy that submits an order,
        # gets a CIRCUIT_BREAKER rejection, and tries again on the next bar tick is not
        # actually stopped — it's spinning at maximum rate") — but nothing implemented it. The
        # breaker flipped strategies.status to HALTED and NOTHING removed the strategy from
        # ``_running``, so momentum-portfolio was halted at 09:30 ET, dispatched anyway at
        # 10:00, and fired 18 order proposals into the risk engine. Every one was rejected.
        #
        # The persisted status is the safety boundary. Read it immediately before dispatch —
        # NOT ``_running`` — because the status can change between the job being queued and
        # the job starting (exactly what happened: the breaker tripped 30 minutes after the
        # scheduler had already armed the 10:00 slot). Fail CLOSED: a status we cannot read is
        # not a licence to trade.
        if not await self._is_dispatchable_now(strategy_id):
            return

        if not self._dispatch_allowed(running):
            return

        # ---- P0: one run per scheduled slot, enforced in DURABLE storage.
        # ``ctx.dispatch_seq`` (below) closes the intra-dispatch hole, but process memory is
        # not a safety boundary — it does not survive a restart or a second scheduler. The
        # UNIQUE (account, strategy, slot, version) constraint is what actually stops the
        # second run. A slot is claimed by being ATTEMPTED, not by succeeding: a run whose
        # every proposal was risk-rejected is COMPLETE, not "nothing happened, try again".
        claim = await self._claim_slot(strategy_id, running)
        if claim is None:
            return

        # Stamp a fresh dispatch identity BEFORE the per-symbol fan-out below. on_bar is about
        # to be called once per symbol (209 times for the combined book), and a portfolio
        # strategy must be able to tell "these are all the same cron slot" from "this is next
        # week's slot". It cannot infer that from the bars — each call carries that symbol's
        # own latest bar, and symbols disagree on how recent that is. See
        # StrategyContext.dispatch_seq. Guarded: telemetry must never break a dispatch.
        with contextlib.suppress(Exception):
            ctx = running.instance.ctx
            ctx.dispatch_seq = (ctx.dispatch_seq or 0) + 1

        for symbol in running.symbols:
            try:
                df = await running.instance.ctx.get_recent_bars(
                    symbol, running.timeframe, n=1
                )
                if df.empty:
                    continue
                last = df.iloc[-1]
                bar = Bar(
                    symbol=symbol.upper(),
                    timeframe=running.timeframe,
                    t=last["t"],
                    o=float(last["o"]),
                    h=float(last["h"]),
                    l=float(last["l"]),
                    c=float(last["c"]),
                    v=int(last["v"]),
                )
            except Exception:
                logger.exception(
                    "strategy_dispatch_get_bar_failed",
                    strategy_id=strategy_id,
                    symbol=symbol,
                )
                continue

            try:
                await running.instance.on_bar(bar)
                running.last_dispatch_at = time.time()
            except Exception as exc:
                await self._close_slot(claim, slot_claim.SLOT_ERROR, f"{type(exc).__name__}: {exc}")
                await self._handle_user_exception(strategy_id, "on_bar", exc)
                return  # stop dispatching to a broken strategy this tick

        # The slot is COMPLETE. Note this is reached even when every order the strategy
        # proposed was rejected by a risk gate — an all-rejected run HAPPENED, it was simply
        # refused, and treating it as "nothing happened" is what let 2026-07-13 re-run 6x.
        await self._close_slot(claim, slot_claim.SLOT_COMPLETED, None)

    async def _is_dispatchable_now(self, strategy_id: int) -> bool:
        """Is this strategy's PERSISTED status still runnable, right now?

        The authoritative check, read immediately before dispatch. ``_running`` is an
        in-memory cache that a circuit-breaker trip does not invalidate — the breaker writes
        ``strategies.status = HALTED`` and nothing evicts the strategy from the engine's map.
        Consulting only ``_running`` is therefore how a HALTED strategy kept being dispatched.

        FAILS CLOSED: if the status cannot be read, we do not dispatch. A database we cannot
        query is not permission to trade.
        """
        try:
            async with self._session_factory() as session:
                status = (
                    await session.execute(
                        select(StrategyRow.status).where(StrategyRow.id == strategy_id)
                    )
                ).scalar_one_or_none()
        except Exception:
            logger.exception("strategy_dispatch_status_check_failed", strategy_id=strategy_id)
            return False  # fail closed

        if status in ENGINE_RUNNABLE_STATUSES:
            return True

        logger.warning(
            "strategy_dispatch_skipped_not_runnable",
            strategy_id=strategy_id,
            status=str(status),
            detail=(
                "persisted status is not runnable (ADR 0004: HALTED must stop DISPATCH, not "
                "merely reject the resulting orders)"
            ),
        )
        return False

    async def _claim_slot(
        self, strategy_id: int, running: RunningStrategy
    ) -> int | None:
        """Claim this scheduled slot in DURABLE storage. Returns the claim id, or None if the
        slot is already claimed (in which case the caller must not run).

        The UNIQUE (account, strategy, slot, version, retry_generation) constraint is the
        control; this is not advisory. FAILS CLOSED: if the claim cannot be written we do not
        dispatch, because we cannot then prove the slot is unclaimed.
        """
        try:
            slot = self._slot_key(running.schedule)
            async with self._session_factory() as session:
                row = (
                    await session.execute(
                        select(StrategyRow).where(StrategyRow.id == strategy_id)
                    )
                ).scalar_one_or_none()
                if row is None:
                    return None
                account_id = (
                    await session.execute(
                        select(Account.id)
                        .where(Account.user_id == row.user_id)
                        .order_by(Account.id)
                        .limit(1)
                    )
                ).scalar_one_or_none()

                claim = slot_claim.StrategySlotClaim(
                    account_id=account_id,
                    strategy_id=strategy_id,
                    scheduled_slot=slot,
                    strategy_version=str(row.version or "0"),
                    retry_generation=0,
                    claimed_at=datetime.now(UTC),
                    outcome=slot_claim.SLOT_RUNNING,
                )
                session.add(claim)
                try:
                    await session.commit()
                except IntegrityError:
                    await session.rollback()
                    logger.warning(
                        "strategy_slot_already_claimed",
                        strategy_id=strategy_id,
                        scheduled_slot=slot,
                        detail=(
                            "this scheduled slot has already been run. A run whose orders were "
                            "all risk-rejected is still a COMPLETED run — retry requires an "
                            "explicit retry_generation, not a re-dispatch."
                        ),
                    )
                    return None
                return claim.id
        except Exception:
            logger.exception("strategy_slot_claim_failed", strategy_id=strategy_id)
            return None  # fail closed

    def _slot_key(self, schedule: str) -> str:  # noqa: ARG002 — schedule kept for future granularity
        """The scheduled slot this dispatch belongs to, as an ET wall-clock key.

        Truncated to the MINUTE: the six 2026-07-13 runs all landed inside 14:00:03-14:00:52,
        so a second-resolution key would have let every one of them claim a distinct slot and
        proved nothing. Strategy schedules are ET (see _STRATEGY_SCHEDULE_TZ), and cron slots
        are minute-granular, so the minute IS the slot.
        """
        return f"{datetime.now(_STRATEGY_SCHEDULE_TZ):%Y-%m-%dT%H:%M}"

    async def _close_slot(self, claim_id: int | None, outcome: str, error: str | None) -> None:
        """Mark the claimed slot finished. Guarded — bookkeeping must never break a dispatch."""
        if claim_id is None:
            return
        try:
            async with self._session_factory() as session:
                row = await session.get(slot_claim.StrategySlotClaim, claim_id)
                if row is None:
                    return
                row.outcome = outcome
                row.finished_at = datetime.now(UTC)
                row.error_text = (error or None) and error[:2000]
                await session.commit()
        except Exception:
            logger.warning("strategy_slot_close_failed", claim_id=claim_id, exc_info=True)

    async def _dispatch_health_monitor_tick(self) -> None:
        """Recurring P11 ops check: WARN-log any active bar-driven strategy that has gone
        stale on dispatch during RTH — the alert that would have caught the Range Trader
        sitting idle for weeks. Fully defensive: never raises into the scheduler."""
        try:
            for r in stale_dispatch(self.dispatch_health()):
                logger.warning(
                    "strategy_dispatch_stale",
                    strategy_id=r.strategy_id,
                    name=r.name,
                    schedule=r.schedule,
                    last_dispatch_age_s=r.last_dispatch_age_s,
                    reason=r.reason,
                )
        except Exception:
            logger.exception("dispatch_health_monitor_failed")

    async def _dispatch_overlay_tick(self, *, strategy_id: int) -> None:
        """APScheduler-invoked at the daily overlay cadence (P10 §2, ADR 0020): call
        the strategy's ``on_overlay_tick`` so it re-sizes gross exposure of its held
        book. Same market-session gate and error containment as ``_dispatch_bar_tick``
        — a broken overlay tick marks the strategy ERROR rather than crashing the
        scheduler."""
        running = self._running.get(strategy_id)
        if running is None:
            return
        # Same P0 gate as _dispatch_bar_tick: a HALTED strategy must not be dispatched at all.
        # momentum-portfolio runs this overlay daily at 15:00 ET — so on 2026-07-13 it would
        # have fired a SECOND wave of order proposals into the risk engine, hours after the
        # breaker had already halted it.
        if not await self._is_dispatchable_now(strategy_id):
            return
        if not self._dispatch_allowed(running):
            return
        try:
            await running.instance.on_overlay_tick()
        except Exception as exc:
            await self._handle_user_exception(strategy_id, "on_overlay_tick", exc)

    async def _consume_topic(
        self,
        topic: str,
        handler: Any,  # async callable taking dict[str, Any]
    ) -> None:
        """Drive an async-generator bus subscription forever, dispatching
        each event to ``handler``. Cancelled at engine shutdown."""
        try:
            async for event in self._bus.subscribe(topic):
                try:
                    await handler(event)
                except Exception:
                    logger.exception(
                        "strategy_engine_handler_error", topic=topic
                    )
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception(
                "strategy_engine_consumer_crashed", topic=topic
            )

    async def _on_fill_event(self, payload: dict[str, Any]) -> None:
        """Route fill events to the originating strategy.

        Fills published with ``source_type='strategy'`` and a numeric
        ``source_id`` are routed to the matching running strategy. Other
        fills are ignored. (P2 Session 4 will extend the trade-update
        consumer to publish these source fields; until then, only the
        engine's tests exercise this path.)
        """
        source_type = payload.get("source_type") or payload.get("order_source_type")
        source_id = payload.get("source_id") or payload.get("order_source_id")
        if source_type != "strategy" or source_id is None:
            return
        try:
            strategy_id = int(source_id)
        except (TypeError, ValueError):
            return
        running = self._running.get(strategy_id)
        if running is None:
            return

        from decimal import Decimal

        try:
            qty = Decimal(str(payload.get("qty", "0")))
            price = Decimal(str(payload.get("price", "0")))
        except Exception:
            qty = price = Decimal(0)

        fill_event = FillEvent(
            fill_id=int(payload.get("fill_id") or 0),
            order_id=int(payload.get("order_id") or 0),
            symbol=str(payload.get("symbol") or "").upper(),
            side=str(payload.get("side") or ""),
            qty=qty,
            price=price,
            filled_at=payload.get("filled_at") or datetime.now(UTC),
        )
        try:
            await running.instance.on_fill(fill_event)
        except Exception as exc:
            await self._handle_user_exception(strategy_id, "on_fill", exc)

    async def _on_signal_event(self, payload: dict[str, Any]) -> None:
        """Route signal events to the originating strategy."""
        strategy_id = payload.get("strategy_id")
        if strategy_id is None:
            return
        try:
            sid = int(strategy_id)
        except (TypeError, ValueError):
            return
        running = self._running.get(sid)
        if running is None:
            return

        try:
            signal_id = int(payload.get("signal_id") or 0)
            type_value = payload.get("type")
            sig_type = (
                SignalTypeEnum(type_value) if type_value else SignalTypeEnum.INFO
            )
        except Exception:
            return

        event = SignalEvent(
            signal_id=signal_id,
            strategy_id=running.strategy_id,
            symbol=str(payload.get("symbol") or "").upper(),
            type=sig_type,
            payload=payload.get("payload") or {},
            received_at=payload.get("received_at") or datetime.now(UTC),
        )
        try:
            await running.instance.on_signal(event)
        except Exception as exc:
            await self._handle_user_exception(sid, "on_signal", exc)

    # ---- error containment ----

    async def _handle_user_exception(
        self,
        strategy_id: int,
        hook: str,
        exc: BaseException,
    ) -> None:
        """User code raised. Mark strategy ERROR, audit, drop from _running."""
        logger.error(
            "strategy_user_exception",
            strategy_id=strategy_id,
            hook=hook,
            error=str(exc),
            exc_info=True,
        )
        async with self._session_factory() as session:
            row = await session.get(StrategyRow, strategy_id)
            if row is not None:
                await self._mark_error(session, row, f"{hook}: {exc}")
                await self._audit(
                    session,
                    user_id=row.user_id,
                    action=AuditAction.STRATEGY_ERROR,
                    target_id=strategy_id,
                    payload={"hook": hook, "error": str(exc)[:512]},
                )
                # Close any open run for this strategy
                open_run = (
                    await session.execute(
                        select(StrategyRun)
                        .where(
                            StrategyRun.strategy_id == strategy_id,
                            StrategyRun.ended_at.is_(None),
                        )
                        .order_by(StrategyRun.id.desc())
                        .limit(1)
                    )
                ).scalars().first()
                if open_run is not None:
                    open_run.ended_at = datetime.now(UTC)
                    open_run.status = StrategyStatus.ERROR
                    open_run.error_text = f"{hook}: {exc}"[:2048]
                await session.commit()
        # Drop without invoking on_shutdown (the strategy is unhealthy).
        running = self._running.pop(strategy_id, None)
        if running is not None:
            for jid in (running.job_id, running.overlay_job_id):
                if jid:
                    with contextlib.suppress(Exception):
                        self._scheduler.remove_job(jid)
        await self._bus.publish(
            "strategy.error",
            {"strategy_id": strategy_id, "hook": hook, "error": str(exc)},
        )
        await self._notify_bar_stream_changed()

    async def _mark_error(
        self,
        session: AsyncSession,
        row: StrategyRow,
        text: str,
    ) -> None:
        row.status = StrategyStatus.ERROR
        row.error_text = text[:2048]
        row.updated_at = datetime.now(UTC)

    async def _audit(
        self,
        session: AsyncSession,
        *,
        user_id: int | None,
        action: AuditAction | str,
        target_id: int,
        payload: dict[str, Any],
    ) -> None:
        """Write a strategy-targeted audit row.

        Thin wrapper around :class:`AuditLogger`; the caller commits.
        """
        AuditLogger.write(
            session,
            actor_type=(
                AuditActorType.USER if user_id is not None else AuditActorType.SYSTEM
            ),
            actor_id=str(user_id) if user_id is not None else None,
            action=action,
            target_type="strategy",
            target_id=target_id,
            payload=payload,
            user_id=user_id,
        )
