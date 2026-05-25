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
    ACTIVE_STRATEGY_STATUSES,
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


@dataclass
class RunningStrategy:
    """A live strategy instance the engine is dispatching to."""

    strategy_id: int
    instance: Strategy
    job_id: str | None  # APScheduler job id (None for event-driven)
    run_id: int  # StrategyRun row id
    symbols: list[str]
    timeframe: str  # for periodic on_bar dispatch


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
    ) -> None:
        self._scheduler = scheduler
        self._session_factory = session_factory
        self._bus = bus
        self._bar_cache = bar_cache
        self._indicator_computer = indicator_computer
        self._order_router = order_router
        self._loader = StrategyLoader(strategies_root)

        self._running: dict[int, RunningStrategy] = {}

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

            account = (
                await session.execute(
                    select(Account).where(
                        Account.user_id == row.user_id,
                        Account.broker == "alpaca",
                        Account.mode == AccountMode.paper,
                    )
                )
            ).scalars().first()
            if account is None:
                raise StrategyLoadError(
                    f"no paper account for user_id={row.user_id}"
                )

            try:
                cls = self._loader.load(row.code_path or "")
            except StrategyLoadError:
                await self._mark_error(session, row, "loader_failed")
                await session.commit()
                raise

            symbols = list(row.symbols_json) or list(cls.symbols)
            merged_params = {**cls.default_params, **(row.params_json or {})}
            ctx = StrategyContext(
                strategy_id=row.id,
                user_id=row.user_id,
                account_id=account.id,
                symbols=symbols,
                session_factory=self._session_factory,
                bar_cache=self._bar_cache,
                indicator_computer=self._indicator_computer,
                submit_order_fn=self._order_router.submit,
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
            run = StrategyRun(
                strategy_id=row.id,
                started_at=now,
                status=StrategyStatus.PAPER,
            )
            session.add(run)
            await session.commit()
            await session.refresh(run)
            run_id = run.id

            row.status = StrategyStatus.PAPER
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
                cron = CronTrigger.from_crontab(schedule)
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
            {"strategy_id": strategy_id, "status": StrategyStatus.PAPER.value},
        )
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

        async with self._session_factory() as session:
            now = datetime.now(UTC)
            run = await session.get(StrategyRun, running.run_id)
            if run is not None and run.ended_at is None:
                run.ended_at = now
                run.status = StrategyStatus.IDLE
            row = await session.get(StrategyRow, strategy_id)
            if row is not None and row.status in ACTIVE_STRATEGY_STATUSES:
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
