"""Background worker that dequeues and runs ``backtest_jobs``.

Driven by APScheduler: a single recurring tick (every
``WORKER_TICK_SECONDS``) that dequeues the oldest QUEUED row, runs it
through the :class:`Backtester`, and yields. We don't have a "long-
running task" abstraction — a poll-and-run pattern fits the single-
process model. When multi-worker arrives (P5 alongside multi-user) the
right move is a real job queue (Redis, Postgres ``FOR UPDATE SKIP
LOCKED``, etc.); don't pre-build it here.

Cancellation
------------
Per-job ``asyncio.Event`` held in :attr:`_cancel_flags`. The HTTP cancel
endpoint sets the flag; the worker checks it via the ``cancel_check``
callback the harness honors between bars.

Restart resilience
------------------
On worker boot any rows still marked RUNNING are transitioned to FAILED
with ``error_text='abandoned: worker restarted'``. Queued jobs resume
naturally because the dequeue logic picks them up in FIFO order. Worth
the trade-off: a backtest 99% done at the moment of crash is discarded
instead of left in an ambiguous half-finished state.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

import structlog
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.enums import BacktestJobStatus
from app.db.models.backtest_job import BacktestJob
from app.db.models.strategy import Strategy as StrategyRow
from app.strategies import (
    BacktestConfig,
    Backtester,
    StrategyLoader,
    persist_backtest_result,
)
from app.strategies.backtester import BacktestCancelled

logger = structlog.get_logger(__name__)


# Worker dequeue cadence (seconds). 2s is fast enough that "submitted →
# running" feels instant in the UI without hammering the DB.
WORKER_TICK_SECONDS = 2.0

# Must mirror the path used by the strategies REST endpoint in
# ``app/api/v1/strategies.py``.
STRATEGIES_ROOT = Path("strategies_user")


class BacktestWorker:
    def __init__(
        self,
        *,
        scheduler: AsyncIOScheduler,
        session_factory: async_sessionmaker[AsyncSession],
        bar_cache: Any,
        indicator_computer: Any,
        bus: Any,
    ) -> None:
        self._scheduler = scheduler
        self._session_factory = session_factory
        self._bar_cache = bar_cache
        self._indicator_computer = indicator_computer
        self._bus = bus
        # Per-job cancellation flags. Set by the HTTP cancel handler;
        # checked by the harness's cancel_check callback.
        self._cancel_flags: dict[int, asyncio.Event] = {}
        # The currently-executing job_id. At most one at a time in P4.
        self._current_job_id: int | None = None

    async def start(self) -> None:
        """Reconcile orphaned RUNNING rows, then schedule the tick."""
        await self._reconcile_orphaned_running_jobs()
        self._scheduler.add_job(
            self._tick,
            "interval",
            seconds=WORKER_TICK_SECONDS,
            id="backtest_worker_tick",
            max_instances=1,  # ticks must not overlap
            coalesce=True,
            replace_existing=True,
        )
        logger.info("backtest_worker_started", tick_seconds=WORKER_TICK_SECONDS)

    async def request_cancel(self, job_id: int) -> bool:
        """Mark a job for cancellation.

        Returns True if the job exists and is in a cancellable state.
        QUEUED jobs transition straight to CANCELLED (no worker involvement
        needed). RUNNING jobs get their flag set; the harness raises
        :class:`BacktestCancelled` at the next bar boundary.
        """
        async with self._session_factory() as session:
            row = await session.get(BacktestJob, job_id)
            if row is None:
                return False
            if row.status == BacktestJobStatus.QUEUED:
                row.status = BacktestJobStatus.CANCELLED
                row.completed_at = datetime.now(UTC)
                row.error_text = "cancelled before start"
                strategy_id = row.strategy_id
                await session.commit()
                await self._publish_cancelled(
                    job_id, strategy_id, "cancelled before start"
                )
                return True
            if row.status == BacktestJobStatus.RUNNING:
                self._cancel_flags.setdefault(job_id, asyncio.Event()).set()
                return True
            return False

    # ---------------- internal ----------------

    async def _reconcile_orphaned_running_jobs(self) -> None:
        async with self._session_factory() as session:
            orphans = (
                await session.execute(
                    select(BacktestJob).where(
                        BacktestJob.status == BacktestJobStatus.RUNNING
                    )
                )
            ).scalars().all()
            for row in orphans:
                row.status = BacktestJobStatus.FAILED
                row.error_text = "abandoned: worker restarted"
                row.completed_at = datetime.now(UTC)
                logger.warning(
                    "backtest_worker_orphaned_job",
                    job_id=row.id,
                    strategy_id=row.strategy_id,
                )
            await session.commit()

    async def _tick(self) -> None:
        """Pull the oldest QUEUED job, if any, and run it."""
        if self._current_job_id is not None:
            # Belt-and-suspenders given max_instances=1.
            return
        job_id = await self._dequeue_one()
        if job_id is None:
            return
        try:
            self._current_job_id = job_id
            await self._run_job(job_id)
        finally:
            self._current_job_id = None
            self._cancel_flags.pop(job_id, None)

    async def _dequeue_one(self) -> int | None:
        """Find the oldest QUEUED job, mark it RUNNING, return its id."""
        async with self._session_factory() as session:
            row = (
                await session.execute(
                    select(BacktestJob)
                    .where(BacktestJob.status == BacktestJobStatus.QUEUED)
                    .order_by(BacktestJob.submitted_at)
                    .limit(1)
                )
            ).scalars().first()
            if row is None:
                return None
            row.status = BacktestJobStatus.RUNNING
            row.started_at = datetime.now(UTC)
            strategy_id = row.strategy_id
            job_id = row.id
            await session.commit()
        await self._publish_started(job_id, strategy_id)
        return job_id

    async def _run_job(self, job_id: int) -> None:
        """Execute one job end-to-end."""
        async with self._session_factory() as session:
            job = await session.get(BacktestJob, job_id)
            if job is None:
                return
            strategy_id = job.strategy_id
            label = job.label
            config_dict = dict(job.config_json or {})
            strat = await session.get(StrategyRow, strategy_id)
            code_path = strat.code_path if strat is not None else None
            strat_symbols = list(strat.symbols_json) if strat is not None else []

        if strat is None:
            await self._mark_failed(
                job_id,
                error_text="strategy no longer exists",
                strategy_id=strategy_id,
            )
            return

        try:
            loader = StrategyLoader(STRATEGIES_ROOT)
            strategy_class = loader.load(code_path or "")
        except Exception as exc:
            await self._mark_failed(
                job_id,
                error_text=f"loader failed: {exc}",
                strategy_id=strategy_id,
            )
            return

        try:
            config = _config_from_dict(config_dict)
            symbols = config_dict.get("_symbols") or strat_symbols
        except Exception as exc:
            await self._mark_failed(
                job_id,
                error_text=f"bad config: {exc}",
                strategy_id=strategy_id,
            )
            return

        if not symbols:
            await self._mark_failed(
                job_id,
                error_text="no symbols to backtest",
                strategy_id=strategy_id,
            )
            return

        # Cancellation flag + progress callback wiring.
        cancel_event = self._cancel_flags.setdefault(job_id, asyncio.Event())

        async def progress_cb(idx: int, total: int, current_ts: datetime) -> None:
            pct = (idx / max(total, 1)) * 100.0
            await self._update_progress(
                job_id, percent=pct, current_ts=current_ts.isoformat()
            )
            await self._publish_progress(job_id, strategy_id, pct, current_ts)

        def cancel_check() -> bool:
            return cancel_event.is_set()

        harness = Backtester(
            bar_cache=self._bar_cache,
            indicator_computer=self._indicator_computer,
        )

        try:
            metrics, trades, equity = await harness.run(
                strategy_class,
                symbols,
                config,
                progress_cb=progress_cb,
                cancel_check=cancel_check,
            )
        except BacktestCancelled as exc:
            await self._mark_cancelled(
                job_id, strategy_id=strategy_id, reason=str(exc)
            )
            return
        except Exception as exc:
            logger.exception("backtest_worker_run_failed", job_id=job_id)
            await self._mark_failed(
                job_id, error_text=str(exc)[:2000], strategy_id=strategy_id
            )
            return

        # Persist the result + complete the job in one transaction.
        async with self._session_factory() as session:
            result = await persist_backtest_result(
                session,
                strategy_id=strategy_id,
                config=config,
                metrics=metrics,
                trades=trades,
                equity=equity,
                label=label,
            )
            j = await session.get(BacktestJob, job_id)
            if j is not None:
                j.status = BacktestJobStatus.COMPLETED
                j.result_id = result.id
                j.completed_at = datetime.now(UTC)
                j.percent_complete = 100.0
            await session.commit()
            backtest_id = result.id
            metrics_dict = result.metrics_json

        # Final 100% progress event, then completion.
        await self._publish_progress(
            job_id, strategy_id, 100.0, current_ts=datetime.now(UTC)
        )
        await self._publish_completed(
            job_id, strategy_id, backtest_id, label, metrics_dict
        )
        logger.info(
            "backtest_worker_job_completed",
            job_id=job_id,
            backtest_id=backtest_id,
        )

    async def _update_progress(
        self, job_id: int, *, percent: float, current_ts: str
    ) -> None:
        async with self._session_factory() as session:
            await session.execute(
                update(BacktestJob)
                .where(BacktestJob.id == job_id)
                .values(percent_complete=percent, current_ts=current_ts)
            )
            await session.commit()

    async def _mark_failed(
        self, job_id: int, *, error_text: str, strategy_id: int
    ) -> None:
        async with self._session_factory() as session:
            row = await session.get(BacktestJob, job_id)
            if row is None:
                return
            row.status = BacktestJobStatus.FAILED
            row.error_text = error_text[:2000]
            row.completed_at = datetime.now(UTC)
            await session.commit()
        await self._publish_failed(job_id, strategy_id, error_text)

    async def _mark_cancelled(
        self, job_id: int, *, strategy_id: int, reason: str
    ) -> None:
        async with self._session_factory() as session:
            row = await session.get(BacktestJob, job_id)
            if row is None:
                return
            row.status = BacktestJobStatus.CANCELLED
            row.error_text = reason[:2000]
            row.completed_at = datetime.now(UTC)
            await session.commit()
        await self._publish_cancelled(job_id, strategy_id, reason)

    # ---------- bus publishers ----------

    async def _publish_started(self, job_id: int, strategy_id: int) -> None:
        try:
            await self._bus.publish(
                "backtest.started",
                {"job_id": job_id, "strategy_id": strategy_id},
            )
        except Exception:
            logger.exception("backtest_worker_publish_failed", event="started")

    async def _publish_progress(
        self,
        job_id: int,
        strategy_id: int,
        percent: float,
        current_ts: datetime,
    ) -> None:
        try:
            await self._bus.publish(
                "backtest.progress",
                {
                    "job_id": job_id,
                    "strategy_id": strategy_id,
                    "percent_complete": round(percent, 2),
                    "current_ts": current_ts.isoformat(),
                },
            )
        except Exception:
            logger.exception("backtest_worker_publish_failed", event="progress")

    async def _publish_completed(
        self,
        job_id: int,
        strategy_id: int,
        backtest_id: int,
        label: str,
        metrics: dict[str, Any],
    ) -> None:
        try:
            # Same topic + base payload shape as P2 S4's sync endpoint; we
            # add ``job_id`` so async-aware clients can correlate. Old
            # subscribers that ignore ``job_id`` keep working unchanged.
            await self._bus.publish(
                "backtest.completed",
                {
                    "job_id": job_id,
                    "backtest_id": backtest_id,
                    "strategy_id": strategy_id,
                    "label": label,
                    "metrics": metrics,
                },
            )
        except Exception:
            logger.exception("backtest_worker_publish_failed", event="completed")

    async def _publish_failed(
        self, job_id: int, strategy_id: int, error_text: str
    ) -> None:
        try:
            await self._bus.publish(
                "backtest.failed",
                {
                    "job_id": job_id,
                    "strategy_id": strategy_id,
                    "error_text": error_text[:512],
                },
            )
        except Exception:
            logger.exception("backtest_worker_publish_failed", event="failed")

    async def _publish_cancelled(
        self, job_id: int, strategy_id: int, reason: str
    ) -> None:
        try:
            await self._bus.publish(
                "backtest.cancelled",
                {
                    "job_id": job_id,
                    "strategy_id": strategy_id,
                    "reason": reason[:512],
                },
            )
        except Exception:
            logger.exception("backtest_worker_publish_failed", event="cancelled")


def _config_from_dict(d: dict[str, Any]) -> BacktestConfig:
    """Rehydrate a :class:`BacktestConfig` from a job's ``config_json``."""
    return BacktestConfig(
        start=datetime.fromisoformat(d["start"]),
        end=datetime.fromisoformat(d["end"]),
        initial_equity=Decimal(str(d.get("initial_equity", "100000"))),
        slippage_bps=float(d.get("slippage_bps", 5.0)),
        commission_per_share=float(d.get("commission_per_share", 0.0)),
        timeframe=str(d.get("timeframe", "1Min")),
        params=dict(d.get("params") or {}),
        seed=int(d.get("seed", 42)),
    )
