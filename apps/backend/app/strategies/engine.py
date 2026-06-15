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
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import structlog
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from sqlalchemy import select
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
from app.db.models.account import Account, AccountMode
from app.db.models.strategy import Strategy as StrategyRow
from app.db.models.strategy_run import StrategyRun
from app.events.bus import EventBus

from .base import Strategy
from .context import Bar, FillEvent, SignalEvent, StrategyContext
from .loader import StrategyLoader, StrategyLoadError

logger = structlog.get_logger(__name__)


EVENT_SCHEDULE_SENTINEL = "event"

# Standard crontab day-of-week is 0/7=Sunday, 1=Monday … 6=Saturday. APScheduler's
# CronTrigger numbers day_of_week 0=Monday … 6=Sunday and `from_crontab` does NOT
# remap — so a numeric dow like "1" is read as Tuesday, silently shifting every
# weekly strategy by a day. We translate numeric dow tokens to unambiguous day
# NAMES (which APScheduler interprets identically to cron) before scheduling.
_CRON_DOW_NAMES = {0: "sun", 1: "mon", 2: "tue", 3: "wed", 4: "thu", 5: "fri", 6: "sat", 7: "sun"}


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

    # ---- registration ----

    async def register(self, strategy_id: int) -> RunningStrategy:
        """Load, instantiate, and start dispatching to a strategy.

        Idempotent: if the strategy is already registered, returns the
        existing :class:`RunningStrategy`.
        """
        if strategy_id in self._running:
            return self._running[strategy_id]

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
                cron = CronTrigger.from_crontab(_normalize_crontab_dow(schedule))
            except Exception:
                logger.warning(
                    "strategy_schedule_invalid_falling_back",
                    strategy_id=strategy_id,
                    schedule=schedule,
                )
                cron = CronTrigger.from_crontab("*/1 * * * *")
            self._scheduler.add_job(
                self._dispatch_bar_tick,
                cron,
                kwargs={"strategy_id": strategy_id},
                id=job_id,
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

        if running.job_id:
            try:
                self._scheduler.remove_job(running.job_id)
            except Exception:
                logger.exception(
                    "strategy_remove_job_failed", strategy_id=strategy_id
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

    async def _dispatch_bar_tick(self, *, strategy_id: int) -> None:
        """APScheduler-invoked: fetch the latest bar for each of this
        strategy's symbols and call ``on_bar``."""
        running = self._running.get(strategy_id)
        if running is None:
            return

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
            except Exception as exc:
                await self._handle_user_exception(strategy_id, "on_bar", exc)
                return  # stop dispatching to a broken strategy this tick

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
        if running is not None and running.job_id:
            with contextlib.suppress(Exception):
                self._scheduler.remove_job(running.job_id)
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
