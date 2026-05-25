# P4 Item 2 — Async Backtest with Progress Events

| Field | Value |
|---|---|
| Document version | v0.1 |
| Date | 2026-05-23 |
| Phase | **P4 — Polish & Extend**, Item §2 |
| Predecessor | *TradingWorkbench_P4_Item1_TVWebhooks_v0.1.md* (tag `p4-tv-webhooks-complete`) |
| Repository | `github.com/jayw04/AI-TRADING-APP` |
| Scope | Replace the synchronous `POST /api/v1/strategies/{id}/backtest` with a fire-and-forget pattern. New `backtest_jobs` table tracks state. Background worker (APScheduler-driven) runs the backtester, emits progress events every ~1 second on the `backtests` WS topic, persists the completed result. UI shows a progress bar in `BacktestRunModal` and updates `BacktestResultsView` on completion. Lift the 1-year range cap. **Two sessions** — backend in this PR, frontend in the follow-up. This doc covers both, but each is independently mergeable. |
| Estimated wall time | 4–5 hours backend + 2–3 hours frontend |
| Stopping point | `git tag p4-async-backtest-complete` after BOTH PRs merge |
| Out of scope | Concurrent backtests across different strategies (allowed; not orchestrated). Distributed worker pool (single-process APScheduler is sufficient at this scale). Real-time intermediate metrics ("current Sharpe so far") — progress carries only `percent_complete` + `current_ts`. Cancellation by another user — backtests are per-user-owned and cancellation is the originating user's right only. |

---

## Session Goal

After both PRs land:
- `POST /api/v1/strategies/{id}/backtest` returns **202** immediately with `{job_id, status: "queued"}`.
- A background worker picks up queued jobs in FIFO order, runs the existing `Backtester` (unchanged from P2 Session 3), and persists a `BacktestResult` row at the end.
- During execution the worker emits `backtest.progress` events every ~1 second carrying `{job_id, backtest_id, percent_complete, current_ts}`. Granularity: any progress in `(0, 100)`; we send a final `100%` event right before `backtest.completed`.
- On completion: `backtest.completed` (already exists from P2 Session 4) carries the full `BacktestResult` summary; the job row transitions to `completed`.
- On failure: `backtest.failed` carries `{job_id, error_text}`; job transitions to `failed`.
- A new `GET /api/v1/backtest-jobs/{job_id}` returns the current state for polling fallback (the UI prefers WS but degrades to polling if WS drops mid-backtest).
- A new `POST /api/v1/backtest-jobs/{job_id}/cancel` requests cancellation. Worker checks a cancellation flag between bars; transitions the job to `cancelled`.
- **The 1-year range cap is removed.** A 5-year 1-minute backtest now works (60–120s wall time), the UI doesn't time out.
- Frontend (Session 2 of this item): `BacktestRunModal` listens to `backtest.progress` for its job_id, renders a progress bar, opens `BacktestResultsView` on `backtest.completed`. Closing the modal mid-run keeps the job running; the result appears in the Backtests tab when done.

What does NOT happen:
- No concurrent backtests for the **same strategy** at the same time. The job queue enforces single-flight per strategy (a second request while one is running returns 409). Concurrent backtests across **different** strategies are fine.
- No "save partial progress" — a cancelled or failed backtest produces no `BacktestResult` row. Job rows live forever in the `backtest_jobs` table for forensics, but trades/equity/metrics are only persisted on full completion.
- No retry of failed jobs from the UI. If a backtest fails, the trader inspects the `error_text`, fixes the cause, and submits a fresh job.

---

## Prerequisites Check

```bash
cd ~/code/AI-TRADING-APP
git status                                       # clean
git pull origin main
git describe --tags --abbrev=0                   # expect: p4-tv-webhooks-complete

./scripts/dev.sh &
sleep 30

# Synchronous backtest endpoint still works (we'll preserve a shim)
curl -fs "http://127.0.0.1:8000/api/v1/strategies" | jq '.count'

# APScheduler is initialized (P1 Session 2)
docker compose logs backend | grep -E "scheduler_started" | head -1

# Reference RSI strategy is registered (from prior smoke), or be ready to register one
curl -fs "http://127.0.0.1:8000/api/v1/strategies?status=idle" | jq '.items[0].id'

docker compose down
```

- [ ] On `main`, clean tree, at `p4-tv-webhooks-complete`.
- [ ] APScheduler boots; reference strategy exists or can be created.

```bash
git checkout -b feat/p4-async-backtest-backend
```

---

# Part A — Backend (Session 1 of 2)

## §2A.1 — `backtest_jobs` Schema

A new table tracks each backtest *job* (an attempt to compute a BacktestResult). The existing `backtest_results` table stores only successful completions. The new `backtest_jobs` table is the audit trail for "what was attempted, and what happened to it."

### 2A.1.1 — Enum

Edit `apps/backend/app/db/enums.py`. Append:

```python
class BacktestJobStatus(str, Enum):
    """Lifecycle of a backtest job.

    Transitions:
        QUEUED    -> RUNNING        (worker picks up)
        RUNNING   -> COMPLETED      (full result persisted)
        RUNNING   -> FAILED         (uncaught exception)
        RUNNING   -> CANCELLED      (user cancellation honored mid-bar)
        QUEUED    -> CANCELLED      (cancelled before worker started)
    """
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


# Convenience: jobs in these states are still in-flight or waiting.
PENDING_BACKTEST_JOB_STATUSES = frozenset({
    BacktestJobStatus.QUEUED,
    BacktestJobStatus.RUNNING,
})
```

### 2A.1.2 — Model

Create `apps/backend/app/db/models/backtest_job.py`:

```python
"""BacktestJob — one attempt to run a backtest.

A successful job produces exactly one BacktestResult row (linked via
result_id). Cancelled and failed jobs have result_id=NULL.

Storage of config_json: we persist the BacktestConfig as JSON on the job
row so the worker can pick it up after a process restart (queued jobs
survive restart; running jobs are marked failed on restart — the worker
won't reattach to a half-done backtest).

current_ts and percent_complete are updated by the worker as it iterates.
They're advisory — the WS `backtest.progress` event is the real-time
channel; the columns are for polling fallback and post-hoc inspection.
"""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    JSON,
    DateTime,
    Enum as SQLEnum,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.db.enums import BacktestJobStatus


class BacktestJob(Base):
    __tablename__ = "backtest_jobs"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    strategy_id: Mapped[int] = mapped_column(
        ForeignKey("strategies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # Set when the job transitions to COMPLETED. NULL otherwise.
    result_id: Mapped[int | None] = mapped_column(
        ForeignKey("backtest_results.id", ondelete="SET NULL"), nullable=True
    )

    status: Mapped[BacktestJobStatus] = mapped_column(
        SQLEnum(BacktestJobStatus, native_enum=False, length=16),
        nullable=False,
        default=BacktestJobStatus.QUEUED,
        index=True,
    )

    # Persisted at submission. Worker reads this to resume after restart
    # (or just to know what to run on first dequeue).
    config_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)

    # Progress fields (advisory)
    percent_complete: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    # ISO timestamp string of the bar currently being processed. Kept as
    # string to avoid timezone-conversion noise — it's a display value.
    current_ts: Mapped[str | None] = mapped_column(String(64), nullable=True)

    submitted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # On failure: the exception message, truncated. On cancellation: who/why.
    error_text: Mapped[str | None] = mapped_column(String(2048), nullable=True)

    # The user-facing label for the resulting BacktestResult. Carried here so
    # the UI can show "running: tighter-rsi-25" without joining to the result.
    label: Mapped[str] = mapped_column(String(128), nullable=False, default="default")

    __table_args__ = (
        Index("ix_backtest_jobs_strategy_status", "strategy_id", "status"),
        Index("ix_backtest_jobs_submitted_at", "submitted_at"),
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<BacktestJob id={self.id} strategy={self.strategy_id} status={self.status.value}>"
```

### 2A.1.3 — Register import

Edit `apps/backend/app/db/models/__init__.py`. Append:

```python
from .backtest_job import BacktestJob  # noqa: F401
```

### 2A.1.4 — Migration

```bash
cd apps/backend
uv run alembic revision --autogenerate -m "P4: backtest_jobs table"
```

Open the generated file. Verify:

- [ ] `op.create_table('backtest_jobs', ...)` with FKs to `users`, `strategies`, `backtest_results`.
- [ ] Index `ix_backtest_jobs_strategy_status` on `(strategy_id, status)`.
- [ ] Index `ix_backtest_jobs_submitted_at` on `submitted_at`.
- [ ] `downgrade()` drops the table.

```bash
uv run alembic upgrade head
uv run sqlite3 data/workbench.sqlite ".schema backtest_jobs"
uv run alembic downgrade -1
uv run alembic upgrade head
cd ../..
```

- [ ] Migration round-trips clean.

---

## §2A.2 — Progress Reporter

The `Backtester` from P2 Session 3 takes a bar loop and emits no callbacks during execution. Rather than rewriting the harness, give it an optional progress callback parameter.

Edit `apps/backend/app/strategies/backtester.py`. Extend the signature of `Backtester.run`:

```python
from typing import Callable, Awaitable

# Type alias — async callback (bar_idx, total_bars, current_bar_ts) -> None
ProgressCallback = Callable[[int, int, datetime], Awaitable[None]]


class Backtester:
    async def run(
        self,
        strategy_class: Type[Strategy],
        symbols: list[str],
        config: BacktestConfig,
        *,
        progress_cb: Optional[ProgressCallback] = None,
        cancel_check: Optional[Callable[[], bool]] = None,
    ) -> tuple[BacktestMetrics, list[BacktestTrade], list[EquityPoint]]:
        """Run a backtest.

        progress_cb: optional async callable invoked periodically with the
            current bar index, total bars, and bar timestamp. The harness
            calls it at most every N bars to avoid hammering the bus.
        cancel_check: optional sync callable returning True if the worker
            should bail. Checked between bars. Raises BacktestCancelled
            when triggered.
        """
        # ... existing setup unchanged ...

        # Determine the master timeline (existing code unchanged)
        master_symbol = list(bars_by_symbol.keys())[0]
        master_len = len(bars_by_symbol[master_symbol])

        # NEW: progress reporting cadence. Aim for ~1 callback per second of
        # wall time; ~50 bars per callback is a reasonable default for typical
        # backtester speeds (a few thousand bars/sec). Tune if observed
        # wall-time differs.
        progress_every_n_bars = max(1, master_len // 200)  # at most ~200 callbacks

        # Main loop (mostly unchanged; new bits annotated NEW)
        for idx in range(master_len):
            # NEW: cancel check at each bar
            if cancel_check is not None and cancel_check():
                raise BacktestCancelled(f"Cancelled at bar {idx}/{master_len}")

            ctx._advance_cursor(idx)
            now = ctx._current_bar_ts() or config.start

            # ... existing per-bar work unchanged ...

            # NEW: progress callback at the configured cadence
            if progress_cb is not None and (idx % progress_every_n_bars == 0 or idx == master_len - 1):
                try:
                    await progress_cb(idx, master_len, now)
                except Exception:
                    logger.exception("backtest_progress_cb_failed", bar=idx)
                    # Don't let a progress-cb error kill the backtest

        # ... existing post-loop work unchanged ...
```

Define the exception (in the same file or `backtest_models.py`):

```python
class BacktestCancelled(Exception):
    """Raised by the harness when the cancel_check callback returns True."""
```

- [ ] `Backtester.run` accepts `progress_cb` and `cancel_check`.
- [ ] `BacktestCancelled` defined.

> The reproducibility test from P2 Session 3 stays green: it doesn't pass either callback, and the harness's behavior with `progress_cb=None` and `cancel_check=None` is byte-identical to before.

---

## §2A.3 — The Background Worker

Create `apps/backend/app/services/backtest_worker.py`:

```python
"""Backtest worker — picks up queued backtest_jobs and executes them.

Driven by APScheduler: a single recurring job (every 2 seconds) that
dequeues the oldest QUEUED job, runs it, then yields. We don't have a
"long-running task" — we have a poll-and-run pattern that fits the single-
process model. Multi-worker arrives with P5/multi-user.

Cancellation:
  The worker maintains a per-job-id Event in `_cancel_flags`. The HTTP
  cancellation endpoint sets the flag; the worker checks it via the
  cancel_check callback the harness honors between bars.

Restart resilience:
  On worker boot, any rows in RUNNING status are transitioned to FAILED
  with error_text='abandoned: worker restarted'. Queued jobs naturally
  resume because the dequeue logic picks them up in FIFO order.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any, Optional

import structlog
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.enums import BacktestJobStatus
from app.db.models.backtest_job import BacktestJob
from app.db.models.strategy import Strategy as StrategyRow
from app.strategies import (
    Backtester,
    BacktestConfig,
    StrategyLoader,
    persist_backtest_result,
)
from app.strategies.backtester import BacktestCancelled

logger = structlog.get_logger(__name__)


# Worker dequeue cadence (seconds).
WORKER_TICK_SECONDS = 2.0

# Strategies root — must match the API handlers in app/api/v1/strategies.py
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
        # In-memory cancellation flags keyed by job_id. Set by HTTP handler;
        # checked by the harness's cancel_check callback.
        self._cancel_flags: dict[int, asyncio.Event] = {}
        # Tracks the currently-executing job_id (at most one at a time in P4).
        self._current_job_id: Optional[int] = None

    async def start(self) -> None:
        """Reconcile any orphaned RUNNING rows, then schedule the tick."""
        await self._reconcile_orphaned_running_jobs()
        self._scheduler.add_job(
            self._tick,
            "interval",
            seconds=WORKER_TICK_SECONDS,
            id="backtest_worker_tick",
            max_instances=1,                # do NOT overlap ticks
            coalesce=True,
        )
        logger.info("backtest_worker_started", tick_seconds=WORKER_TICK_SECONDS)

    async def request_cancel(self, job_id: int) -> bool:
        """Mark a job for cancellation.

        Returns True if the job exists and is in a cancellable state.
        For QUEUED jobs we transition straight to CANCELLED (no worker
        involvement needed). For RUNNING jobs we set the flag and let the
        harness raise BacktestCancelled at the next bar boundary.
        """
        async with self._session_factory() as session:
            row = await session.get(BacktestJob, job_id)
            if row is None:
                return False
            if row.status == BacktestJobStatus.QUEUED:
                row.status = BacktestJobStatus.CANCELLED
                row.completed_at = datetime.now(timezone.utc)
                row.error_text = "cancelled before start"
                await session.commit()
                await self._publish_cancelled(job_id, row.strategy_id, "cancelled before start")
                return True
            if row.status == BacktestJobStatus.RUNNING:
                self._cancel_flags.setdefault(job_id, asyncio.Event()).set()
                return True
            return False

    # ---------------- internal ----------------

    async def _reconcile_orphaned_running_jobs(self) -> None:
        """On boot, fail any rows still marked RUNNING."""
        async with self._session_factory() as session:
            result = await session.execute(
                select(BacktestJob).where(BacktestJob.status == BacktestJobStatus.RUNNING)
            )
            orphans = result.scalars().all()
            for row in orphans:
                row.status = BacktestJobStatus.FAILED
                row.error_text = "abandoned: worker restarted"
                row.completed_at = datetime.now(timezone.utc)
                logger.warning("backtest_worker_orphaned_job",
                               job_id=row.id, strategy_id=row.strategy_id)
            await session.commit()

    async def _tick(self) -> None:
        """Pull the oldest QUEUED job, if any, and run it."""
        if self._current_job_id is not None:
            # Should never happen because max_instances=1, but be defensive
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

    async def _dequeue_one(self) -> Optional[int]:
        """Find the oldest QUEUED job, mark it RUNNING, return its id."""
        async with self._session_factory() as session:
            result = await session.execute(
                select(BacktestJob)
                .where(BacktestJob.status == BacktestJobStatus.QUEUED)
                .order_by(BacktestJob.submitted_at)
                .limit(1)
            )
            row = result.scalars().first()
            if row is None:
                return None
            row.status = BacktestJobStatus.RUNNING
            row.started_at = datetime.now(timezone.utc)
            await session.commit()
            await self._publish_started(row.id, row.strategy_id)
            return row.id

    async def _run_job(self, job_id: int) -> None:
        """Execute one job end-to-end."""
        # Load the job + the strategy row
        async with self._session_factory() as session:
            job = await session.get(BacktestJob, job_id)
            strat = await session.get(StrategyRow, job.strategy_id)
            if strat is None:
                await self._mark_failed(
                    job_id, error_text="strategy no longer exists",
                    strategy_id=job.strategy_id,
                )
                return

        try:
            loader = StrategyLoader(STRATEGIES_ROOT)
            strategy_class = loader.load(strat.code_path or "")
        except Exception as exc:
            await self._mark_failed(
                job_id, error_text=f"loader failed: {exc}",
                strategy_id=job.strategy_id,
            )
            return

        # Reconstruct BacktestConfig from job.config_json
        try:
            cfg_dict = dict(job.config_json or {})
            config = _config_from_dict(cfg_dict)
            symbols = cfg_dict.get("_symbols") or list(strat.symbols_json or [])
        except Exception as exc:
            await self._mark_failed(
                job_id, error_text=f"bad config: {exc}",
                strategy_id=job.strategy_id,
            )
            return

        if not symbols:
            await self._mark_failed(
                job_id, error_text="no symbols to backtest",
                strategy_id=job.strategy_id,
            )
            return

        # Progress + cancellation wiring
        cancel_event = self._cancel_flags.setdefault(job_id, asyncio.Event())
        async def progress_cb(idx: int, total: int, current_ts: datetime) -> None:
            pct = (idx / max(total, 1)) * 100.0
            await self._update_progress(job_id, percent=pct, current_ts=current_ts.isoformat())
            await self._publish_progress(job_id, job.strategy_id, pct, current_ts)

        def cancel_check() -> bool:
            return cancel_event.is_set()

        harness = Backtester(
            bar_cache=self._bar_cache, indicator_computer=self._indicator_computer,
        )

        try:
            metrics, trades, equity = await harness.run(
                strategy_class, symbols, config,
                progress_cb=progress_cb,
                cancel_check=cancel_check,
            )
        except BacktestCancelled as exc:
            await self._mark_cancelled(
                job_id, strategy_id=job.strategy_id, reason=str(exc),
            )
            return
        except Exception as exc:
            logger.exception("backtest_worker_run_failed", job_id=job_id)
            await self._mark_failed(
                job_id, error_text=str(exc)[:2000], strategy_id=job.strategy_id,
            )
            return

        # Persist the result + complete the job
        async with self._session_factory() as session:
            result = await persist_backtest_result(
                session,
                strategy_id=job.strategy_id,
                config=config,
                metrics=metrics,
                trades=trades,
                equity=equity,
                label=job.label,
            )
            j = await session.get(BacktestJob, job_id)
            j.status = BacktestJobStatus.COMPLETED
            j.result_id = result.id
            j.completed_at = datetime.now(timezone.utc)
            j.percent_complete = 100.0
            await session.commit()
            backtest_id = result.id
            metrics_dict = result.metrics_json

        # Publish final progress (100%) and completion
        await self._publish_progress(job_id, job.strategy_id, 100.0, current_ts=datetime.now(timezone.utc))
        await self._publish_completed(job_id, job.strategy_id, backtest_id, job.label, metrics_dict)
        logger.info("backtest_worker_job_completed",
                    job_id=job_id, backtest_id=backtest_id)

    async def _update_progress(self, job_id: int, *, percent: float, current_ts: str) -> None:
        async with self._session_factory() as session:
            await session.execute(
                update(BacktestJob)
                .where(BacktestJob.id == job_id)
                .values(percent_complete=percent, current_ts=current_ts)
            )
            await session.commit()

    async def _mark_failed(self, job_id: int, *, error_text: str, strategy_id: int) -> None:
        async with self._session_factory() as session:
            row = await session.get(BacktestJob, job_id)
            if row is None:
                return
            row.status = BacktestJobStatus.FAILED
            row.error_text = error_text[:2000]
            row.completed_at = datetime.now(timezone.utc)
            await session.commit()
        await self._publish_failed(job_id, strategy_id, error_text)

    async def _mark_cancelled(self, job_id: int, *, strategy_id: int, reason: str) -> None:
        async with self._session_factory() as session:
            row = await session.get(BacktestJob, job_id)
            if row is None:
                return
            row.status = BacktestJobStatus.CANCELLED
            row.error_text = reason[:2000]
            row.completed_at = datetime.now(timezone.utc)
            await session.commit()
        await self._publish_cancelled(job_id, strategy_id, reason)

    # ---------- bus publishers ----------

    async def _publish_started(self, job_id: int, strategy_id: int) -> None:
        try:
            await self._bus.publish("backtest.started", {
                "job_id": job_id,
                "strategy_id": strategy_id,
            })
        except Exception:
            logger.exception("backtest_worker_publish_failed", event="started")

    async def _publish_progress(self, job_id: int, strategy_id: int,
                                percent: float, current_ts: datetime) -> None:
        try:
            await self._bus.publish("backtest.progress", {
                "job_id": job_id,
                "strategy_id": strategy_id,
                "percent_complete": round(percent, 2),
                "current_ts": current_ts.isoformat() if isinstance(current_ts, datetime) else str(current_ts),
            })
        except Exception:
            logger.exception("backtest_worker_publish_failed", event="progress")

    async def _publish_completed(self, job_id: int, strategy_id: int,
                                 backtest_id: int, label: str, metrics: dict) -> None:
        try:
            # 'backtest.completed' is already used by P2 Session 4; preserve
            # that shape for back-compat (frontend currently listens on it).
            await self._bus.publish("backtest.completed", {
                "job_id": job_id,
                "backtest_id": backtest_id,
                "strategy_id": strategy_id,
                "label": label,
                "metrics": metrics,
            })
        except Exception:
            logger.exception("backtest_worker_publish_failed", event="completed")

    async def _publish_failed(self, job_id: int, strategy_id: int, error_text: str) -> None:
        try:
            await self._bus.publish("backtest.failed", {
                "job_id": job_id,
                "strategy_id": strategy_id,
                "error_text": error_text[:512],
            })
        except Exception:
            logger.exception("backtest_worker_publish_failed", event="failed")

    async def _publish_cancelled(self, job_id: int, strategy_id: int, reason: str) -> None:
        try:
            await self._bus.publish("backtest.cancelled", {
                "job_id": job_id,
                "strategy_id": strategy_id,
                "reason": reason[:512],
            })
        except Exception:
            logger.exception("backtest_worker_publish_failed", event="cancelled")


def _config_from_dict(d: dict) -> BacktestConfig:
    """Reconstruct a BacktestConfig from a dict that came out of config_json."""
    from datetime import datetime as dt
    return BacktestConfig(
        start=dt.fromisoformat(d["start"]),
        end=dt.fromisoformat(d["end"]),
        initial_equity=Decimal(str(d.get("initial_equity", "100000"))),
        slippage_bps=float(d.get("slippage_bps", 5.0)),
        commission_per_share=float(d.get("commission_per_share", 0.0)),
        timeframe=str(d.get("timeframe", "1Min")),
        params=dict(d.get("params") or {}),
        seed=int(d.get("seed", 42)),
    )
```

- [ ] Worker created.

Wire it in the lifespan. Edit `apps/backend/app/lifespan.py` after the strategy engine is created:

```python
from app.services.backtest_worker import BacktestWorker

# Construct after scheduler + bar_cache + indicator_computer + event_bus exist
app.state.backtest_worker = BacktestWorker(
    scheduler=app.state.scheduler,
    session_factory=app.state.session_factory,
    bar_cache=app.state.bar_cache,
    indicator_computer=app.state.indicator_computer,
    bus=app.state.event_bus,
)
await app.state.backtest_worker.start()
```

- [ ] Worker started in lifespan.

---

## §2A.4 — REST: Submit Job, Get Job, Cancel Job, List Jobs

### 2A.4.1 — Pydantic schemas

Edit `apps/backend/app/api/v1/schemas/strategies.py`. Append:

```python
from app.db.enums import BacktestJobStatus


class BacktestJobResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    strategy_id: int
    result_id: Optional[int]
    status: BacktestJobStatus
    label: str
    percent_complete: float
    current_ts: Optional[str]
    submitted_at: datetime
    started_at: Optional[datetime]
    completed_at: Optional[datetime]
    error_text: Optional[str]


class BacktestJobListResponse(BaseModel):
    items: list[BacktestJobResponse]
    count: int


class BacktestJobSubmittedResponse(BaseModel):
    """Returned by POST /strategies/{id}/backtest in async mode (202)."""
    job_id: int
    strategy_id: int
    status: BacktestJobStatus
    submitted_at: datetime
```

### 2A.4.2 — Change `POST /strategies/{id}/backtest` to fire-and-forget

Edit `apps/backend/app/api/v1/strategies.py`. Replace the existing `run_backtest` handler:

```python
@router.post(
    "/{strategy_id}/backtest",
    response_model=BacktestJobSubmittedResponse,
    status_code=202,
)
async def submit_backtest(
    strategy_id: int,
    body: BacktestRequest,
    request: Request,
    current_user=Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Submit a backtest for asynchronous execution.

    Returns 202 with a job_id immediately. Subscribe to the 'backtests' WS
    topic and filter on this job_id to follow progress. The completed
    BacktestResult is fetchable via GET /strategies/{id}/backtests/{result_id}
    once the job's status is 'completed'.
    """
    row = await session.get(StrategyRow, strategy_id)
    if row is None or row.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Strategy not found")
    if row.type != StrategyType.PYTHON:
        raise HTTPException(status_code=400, detail="Only python strategies are backtestable")
    if body.end <= body.start:
        raise HTTPException(status_code=400, detail="end must be after start")
    # NOTE: the 1-year range cap is removed. Async means no HTTP timeout pressure.

    # Single-flight per strategy: refuse a new job if there's already a
    # QUEUED or RUNNING job for this strategy.
    existing = (await session.execute(
        select(BacktestJob)
        .where(
            BacktestJob.strategy_id == strategy_id,
            BacktestJob.status.in_(list(PENDING_BACKTEST_JOB_STATUSES)),
        )
    )).scalars().first()
    if existing is not None:
        raise HTTPException(
            status_code=409,
            detail=f"Backtest job {existing.id} for this strategy is still {existing.status.value}. "
                   "Wait or cancel it first.",
        )

    # Resolve symbols (UI may have overridden; otherwise fall back to strategy)
    symbols = body.symbols or list(row.symbols_json or [])
    merged_params = {**(row.params_json or {}), **body.params}

    # Persist the job
    config_dict = {
        "start": body.start.isoformat(),
        "end": body.end.isoformat(),
        "initial_equity": str(body.initial_equity),
        "slippage_bps": body.slippage_bps,
        "commission_per_share": body.commission_per_share,
        "timeframe": body.timeframe,
        "params": merged_params,
        "_symbols": symbols,        # underscore prefix → worker-internal
    }

    job = BacktestJob(
        user_id=current_user.id,
        strategy_id=strategy_id,
        status=BacktestJobStatus.QUEUED,
        config_json=config_dict,
        label=body.label,
        percent_complete=0.0,
        submitted_at=datetime.now(timezone.utc),
    )
    session.add(job)
    await session.flush()

    await AuditLogger.write(
        session,
        actor_type=AuditActorType.USER,
        actor_id=str(current_user.id),
        action=AuditAction.STRATEGY_BACKTESTED,
        target_type="backtest_job",
        target_id=job.id,
        payload={
            "strategy_id": strategy_id,
            "range_start": body.start.isoformat(),
            "range_end": body.end.isoformat(),
            "label": body.label,
        },
        user_id=current_user.id,
    )
    await session.commit()
    await session.refresh(job)

    bus = _get_bus(request)
    if bus is not None:
        try:
            await bus.publish("backtest.queued", {
                "job_id": job.id,
                "strategy_id": strategy_id,
                "label": body.label,
            })
        except Exception:
            pass

    return BacktestJobSubmittedResponse(
        job_id=job.id,
        strategy_id=strategy_id,
        status=job.status,
        submitted_at=job.submitted_at,
    )
```

Required new imports at the top of the file:

```python
from app.db.enums import (
    ACTIVE_STRATEGY_STATUSES,
    BacktestJobStatus,
    PENDING_BACKTEST_JOB_STATUSES,
    StrategyStatus,
    StrategyType,
)
from app.db.models.backtest_job import BacktestJob
from app.api.v1.schemas.strategies import (
    # ... existing imports ...
    BacktestJobListResponse,
    BacktestJobResponse,
    BacktestJobSubmittedResponse,
)
```

### 2A.4.3 — New job-management endpoints

Append to `apps/backend/app/api/v1/strategies.py`:

```python
@router.get("/{strategy_id}/backtest-jobs", response_model=BacktestJobListResponse)
async def list_backtest_jobs(
    strategy_id: int,
    status: Optional[BacktestJobStatus] = Query(default=None),
    limit: int = Query(default=50, ge=1, le=500),
    current_user=Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    row = await session.get(StrategyRow, strategy_id)
    if row is None or row.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Strategy not found")
    stmt = select(BacktestJob).where(BacktestJob.strategy_id == strategy_id)
    if status is not None:
        stmt = stmt.where(BacktestJob.status == status)
    stmt = stmt.order_by(BacktestJob.submitted_at.desc()).limit(limit)
    rows = (await session.execute(stmt)).scalars().all()
    return BacktestJobListResponse(
        items=[BacktestJobResponse.model_validate(r, from_attributes=True) for r in rows],
        count=len(rows),
    )
```

Now a top-level `backtest-jobs` router for the per-job endpoints (no `strategy_id` in the path — the job already knows its strategy):

Create `apps/backend/app/api/v1/backtest_jobs.py`:

```python
"""Per-job endpoints for backtest jobs.

POST /api/v1/backtest-jobs/{job_id}/cancel — request cancellation
GET  /api/v1/backtest-jobs/{job_id}        — current state
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.schemas.strategies import BacktestJobResponse
from app.auth.stub import get_current_user
from app.db.models.backtest_job import BacktestJob
from app.db.session import get_session

router = APIRouter(prefix="/backtest-jobs", tags=["backtest-jobs"])


def _get_worker(request: Request):
    w = getattr(request.app.state, "backtest_worker", None)
    if w is None:
        raise HTTPException(status_code=503, detail="Backtest worker not initialized")
    return w


@router.get("/{job_id}", response_model=BacktestJobResponse)
async def get_job(
    job_id: int,
    current_user=Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    row = await session.get(BacktestJob, job_id)
    if row is None or row.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Backtest job not found")
    return BacktestJobResponse.model_validate(row, from_attributes=True)


@router.post("/{job_id}/cancel", response_model=BacktestJobResponse)
async def cancel_job(
    job_id: int,
    request: Request,
    current_user=Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    row = await session.get(BacktestJob, job_id)
    if row is None or row.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Backtest job not found")

    worker = _get_worker(request)
    accepted = await worker.request_cancel(job_id)
    if not accepted:
        raise HTTPException(
            status_code=409,
            detail=f"Job is in status {row.status.value}; cancellation not applicable.",
        )

    # Re-fetch for the response (cancel may have updated the row already
    # for QUEUED jobs; for RUNNING jobs the worker will update on its next
    # bar boundary).
    await session.refresh(row)
    return BacktestJobResponse.model_validate(row, from_attributes=True)
```

Mount in `apps/backend/app/main.py`:

```python
from app.api.v1 import backtest_jobs as backtest_jobs_router
app.include_router(backtest_jobs_router.router, prefix="/api/v1")
```

- [ ] All four endpoints in place: submit (202), list jobs, get job, cancel job.

---

## §2A.5 — WS Topic Wiring

Edit `apps/backend/app/ws/gateway.py`. Extend `bus_to_ws_map`:

```python
bus_to_ws_map = {
    # ... existing entries ...

    # NEW for P4 Item 2:
    "backtest.queued":    "backtests",
    "backtest.started":   "backtests",
    "backtest.progress":  "backtests",
    # 'backtest.completed' already maps to 'backtests' from P2 Session 4
    "backtest.failed":    "backtests",
    "backtest.cancelled": "backtests",
}
```

The `backtests` WS topic already exists from P2 Session 4 with a 60-min replay window. We add four new event types under the same topic — no replay-window change needed.

- [ ] All five new event types map to `backtests`.

---

## §2A.6 — Backend Tests

Create `apps/backend/tests/api/test_backtest_jobs_endpoint.py`:

```python
"""Tests for the async backtest job lifecycle via REST."""
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pandas as pd
import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.db.enums import (
    BacktestJobStatus, RiskScopeType, StrategyStatus, StrategyType,
)
from app.db.models.account import Account
from app.db.models.backtest_job import BacktestJob
from app.db.models.risk_limits import RiskLimits
from app.db.models.strategy import Strategy as StrategyRow
from app.db.models.symbol import Symbol
from app.db.models.user import User


def _now():
    return datetime.now(timezone.utc)


@pytest.fixture
async def seeded(session_factory):
    async with session_factory() as session:
        session.add(User(id=1, email="jay@test", display_name="Jay"))
        session.add(Account(id=1, user_id=1, broker="alpaca", mode="paper", label="Paper"))
        session.add(Symbol(id=1, ticker="AAPL", exchange="NASDAQ",
                           asset_class="us_equity", name="Apple", active=True))
        session.add(RiskLimits(
            user_id=1, scope_type=RiskScopeType.GLOBAL, scope_id=None,
            max_position_qty=Decimal("100"),
            max_position_notional=Decimal("25000"),
            max_gross_exposure=Decimal("100000"),
            max_daily_loss=Decimal("2000"),
            max_orders_per_minute=10, allow_short=False,
            created_at=_now(), updated_at=_now(),
        ))
        row = StrategyRow(
            id=1, user_id=1, name="rsi", version="0.1.0",
            type=StrategyType.PYTHON, status=StrategyStatus.IDLE,
            code_path="examples/rsi_meanreversion.py",
            params_json={}, symbols_json=["AAPL"], schedule="*/1 * * * *",
            risk_limits_id=None, created_at=_now(), updated_at=_now(),
        )
        session.add(row)
        await session.commit()


@pytest.fixture
async def client(seeded, session_factory):
    from app.main import create_app
    app = create_app()
    app.state.event_bus = MagicMock()
    app.state.event_bus.publish = AsyncMock()
    app.state.bar_cache = MagicMock()
    app.state.bar_cache.get_bars = AsyncMock(return_value=pd.DataFrame())
    app.state.indicator_computer = MagicMock()
    # Worker is required by the cancel endpoint
    app.state.backtest_worker = MagicMock()
    app.state.backtest_worker.request_cancel = AsyncMock(return_value=True)
    async with AsyncClient(app=app, base_url="http://test") as ac:
        yield ac


@pytest.mark.asyncio
async def test_submit_returns_202_with_job_id(client, session_factory):
    resp = await client.post("/api/v1/strategies/1/backtest", json={
        "start": "2025-11-03T00:00:00+00:00",
        "end": "2025-11-10T00:00:00+00:00",
        "label": "test",
        "slippage_bps": 5,
    })
    assert resp.status_code == 202
    body = resp.json()
    assert body["status"] == "queued"
    assert body["job_id"] > 0

    async with session_factory() as session:
        job = await session.get(BacktestJob, body["job_id"])
    assert job is not None
    assert job.label == "test"
    assert job.percent_complete == 0


@pytest.mark.asyncio
async def test_long_range_no_longer_rejected(client):
    """The 1-year cap is gone. A 5-year range should accept."""
    resp = await client.post("/api/v1/strategies/1/backtest", json={
        "start": "2020-01-01T00:00:00+00:00",
        "end": "2025-01-01T00:00:00+00:00",
        "label": "long",
    })
    assert resp.status_code == 202


@pytest.mark.asyncio
async def test_inverted_range_still_rejected(client):
    resp = await client.post("/api/v1/strategies/1/backtest", json={
        "start": "2025-11-10T00:00:00+00:00",
        "end": "2025-11-03T00:00:00+00:00",
        "label": "backwards",
    })
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_single_flight_per_strategy(client):
    """A second submit while the first is QUEUED returns 409."""
    r1 = await client.post("/api/v1/strategies/1/backtest", json={
        "start": "2025-11-03T00:00:00+00:00",
        "end": "2025-11-10T00:00:00+00:00",
        "label": "first",
    })
    assert r1.status_code == 202

    r2 = await client.post("/api/v1/strategies/1/backtest", json={
        "start": "2025-11-03T00:00:00+00:00",
        "end": "2025-11-10T00:00:00+00:00",
        "label": "second",
    })
    assert r2.status_code == 409


@pytest.mark.asyncio
async def test_get_job_returns_state(client, session_factory):
    resp = await client.post("/api/v1/strategies/1/backtest", json={
        "start": "2025-11-03T00:00:00+00:00",
        "end": "2025-11-04T00:00:00+00:00",
        "label": "tiny",
    })
    job_id = resp.json()["job_id"]

    r = await client.get(f"/api/v1/backtest-jobs/{job_id}")
    assert r.status_code == 200
    body = r.json()
    assert body["id"] == job_id
    assert body["status"] == "queued"
    assert body["label"] == "tiny"


@pytest.mark.asyncio
async def test_get_job_returns_404_for_other_user(client, session_factory):
    async with session_factory() as session:
        session.add(User(id=2, email="other@test", display_name="Other"))
        await session.commit()
        job = BacktestJob(
            user_id=2, strategy_id=1, status=BacktestJobStatus.QUEUED,
            config_json={}, label="x", percent_complete=0,
            submitted_at=_now(),
        )
        session.add(job)
        await session.commit()
        await session.refresh(job)
        other_jid = job.id

    r = await client.get(f"/api/v1/backtest-jobs/{other_jid}")
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_cancel_calls_worker_and_succeeds(client):
    resp = await client.post("/api/v1/strategies/1/backtest", json={
        "start": "2025-11-03T00:00:00+00:00",
        "end": "2025-11-04T00:00:00+00:00",
    })
    job_id = resp.json()["job_id"]
    r = await client.post(f"/api/v1/backtest-jobs/{job_id}/cancel")
    assert r.status_code == 200
    client._transport.app.state.backtest_worker.request_cancel.assert_called_with(job_id)


@pytest.mark.asyncio
async def test_cancel_returns_409_when_worker_refuses(client):
    """If the job is already completed/failed/cancelled, worker returns False."""
    resp = await client.post("/api/v1/strategies/1/backtest", json={
        "start": "2025-11-03T00:00:00+00:00",
        "end": "2025-11-04T00:00:00+00:00",
    })
    job_id = resp.json()["job_id"]
    client._transport.app.state.backtest_worker.request_cancel = AsyncMock(return_value=False)
    r = await client.post(f"/api/v1/backtest-jobs/{job_id}/cancel")
    assert r.status_code == 409


@pytest.mark.asyncio
async def test_list_jobs_filters_by_status(client, session_factory):
    """Three jobs in different statuses; filter returns only the matching one."""
    for status in [BacktestJobStatus.QUEUED, BacktestJobStatus.COMPLETED, BacktestJobStatus.FAILED]:
        async with session_factory() as session:
            session.add(BacktestJob(
                user_id=1, strategy_id=1, status=status,
                config_json={}, label=status.value, percent_complete=0,
                submitted_at=_now(),
            ))
            await session.commit()

    r = await client.get("/api/v1/strategies/1/backtest-jobs?status=failed")
    assert r.status_code == 200
    body = r.json()
    assert body["count"] >= 1
    assert all(item["status"] == "failed" for item in body["items"])


@pytest.mark.asyncio
async def test_submit_publishes_queued_event(client):
    bus = client._transport.app.state.event_bus
    await client.post("/api/v1/strategies/1/backtest", json={
        "start": "2025-11-03T00:00:00+00:00",
        "end": "2025-11-04T00:00:00+00:00",
    })
    topics = [c.args[0] for c in bus.publish.call_args_list]
    assert "backtest.queued" in topics
```

### 2A.6.2 — Worker integration test

Create `apps/backend/tests/services/test_backtest_worker.py`:

```python
"""Backtest worker integration test using the real Backtester + committed fixture bars."""
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import asyncio
import pandas as pd
import pytest
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from app.db.enums import (
    BacktestJobStatus, StrategyStatus, StrategyType,
)
from app.db.models.account import Account
from app.db.models.backtest_job import BacktestJob
from app.db.models.backtest_result import BacktestResult
from app.db.models.strategy import Strategy as StrategyRow
from app.db.models.symbol import Symbol
from app.db.models.user import User
from app.events.bus import EventBus
from app.indicators import IndicatorComputer
from app.services.backtest_worker import BacktestWorker


FIXTURE_DIR = Path(__file__).resolve().parents[1] / "fixtures" / "bars"


def _now():
    return datetime.now(timezone.utc)


def _load_fixture_bars() -> pd.DataFrame:
    days = ["2025-11-03", "2025-11-04", "2025-11-05"]
    frames = []
    for d in days:
        p = FIXTURE_DIR / f"AAPL_{d}_1Min.parquet"
        if not p.exists():
            pytest.skip(f"Missing fixture {p}")
        frames.append(pd.read_parquet(p))
    df = pd.concat(frames).reset_index(drop=True)
    df["t"] = pd.to_datetime(df["t"], utc=True)
    return df.sort_values("t").reset_index(drop=True)


@pytest.fixture
async def seeded(session_factory):
    async with session_factory() as session:
        session.add(User(id=1, email="jay@test", display_name="Jay"))
        session.add(Account(id=1, user_id=1, broker="alpaca", mode="paper", label="Paper"))
        session.add(Symbol(id=1, ticker="AAPL", exchange="NASDAQ",
                           asset_class="us_equity", name="Apple", active=True))
        session.add(StrategyRow(
            id=1, user_id=1, name="rsi", version="0.1.0",
            type=StrategyType.PYTHON, status=StrategyStatus.IDLE,
            code_path="examples/rsi_meanreversion.py",
            params_json={}, symbols_json=["AAPL"], schedule="*/1 * * * *",
            risk_limits_id=None, created_at=_now(), updated_at=_now(),
        ))
        await session.commit()


@pytest.fixture
async def worker(session_factory, seeded):
    scheduler = AsyncIOScheduler()
    scheduler.start()
    bus = EventBus()
    bar_cache = MagicMock()
    bar_cache.get_bars = AsyncMock(return_value=_load_fixture_bars())
    indicator_computer = IndicatorComputer()
    w = BacktestWorker(
        scheduler=scheduler, session_factory=session_factory,
        bar_cache=bar_cache, indicator_computer=indicator_computer, bus=bus,
    )
    yield w, scheduler, bus
    scheduler.shutdown(wait=False)


@pytest.mark.asyncio
async def test_worker_completes_a_queued_job(worker, session_factory):
    w, scheduler, bus = worker
    # Subscribe to bus events
    received: list[tuple[str, dict]] = []
    async def collector(topic, payload):
        received.append((topic, payload))
    # EventBus.subscribe API may differ — adjust as needed
    if hasattr(bus, "subscribe"):
        bus.subscribe("backtest.started", collector)
        bus.subscribe("backtest.progress", collector)
        bus.subscribe("backtest.completed", collector)

    # Queue a job
    async with session_factory() as session:
        job = BacktestJob(
            user_id=1, strategy_id=1, status=BacktestJobStatus.QUEUED,
            label="test",
            config_json={
                "start": "2025-11-03T00:00:00+00:00",
                "end": "2025-11-06T00:00:00+00:00",
                "initial_equity": "100000",
                "slippage_bps": 5.0,
                "commission_per_share": 0.0,
                "timeframe": "1Min",
                "params": {},
                "_symbols": ["AAPL"],
            },
            percent_complete=0.0,
            submitted_at=_now(),
        )
        session.add(job)
        await session.commit()
        await session.refresh(job)
        jid = job.id

    # Start the worker — its tick will pick the job up
    await w.start()
    # Wait for completion (with a generous timeout)
    for _ in range(60):
        await asyncio.sleep(0.5)
        async with session_factory() as session:
            row = await session.get(BacktestJob, jid)
            if row.status in (BacktestJobStatus.COMPLETED,
                              BacktestJobStatus.FAILED,
                              BacktestJobStatus.CANCELLED):
                break

    async with session_factory() as session:
        final = await session.get(BacktestJob, jid)
    assert final.status == BacktestJobStatus.COMPLETED
    assert final.result_id is not None
    assert final.percent_complete == 100.0

    # BacktestResult was persisted
    async with session_factory() as session:
        result = await session.get(BacktestResult, final.result_id)
    assert result is not None
    assert result.strategy_id == 1


@pytest.mark.asyncio
async def test_worker_reconciles_orphaned_running_on_start(worker, session_factory):
    w, _, _ = worker
    async with session_factory() as session:
        session.add(BacktestJob(
            user_id=1, strategy_id=1, status=BacktestJobStatus.RUNNING,
            label="orphan", config_json={}, percent_complete=42.0,
            submitted_at=_now(), started_at=_now(),
        ))
        await session.commit()

    await w.start()

    async with session_factory() as session:
        orphans = (await session.execute(
            "SELECT id, status, error_text FROM backtest_jobs WHERE label='orphan'"
        )).all()
    assert orphans[0][1] == BacktestJobStatus.FAILED.value
    assert "abandoned" in (orphans[0][2] or "")


@pytest.mark.asyncio
async def test_worker_cancels_queued_job_synchronously(worker, session_factory):
    w, _, _ = worker
    async with session_factory() as session:
        job = BacktestJob(
            user_id=1, strategy_id=1, status=BacktestJobStatus.QUEUED,
            label="to-cancel", config_json={}, percent_complete=0,
            submitted_at=_now(),
        )
        session.add(job)
        await session.commit()
        await session.refresh(job)
        jid = job.id

    accepted = await w.request_cancel(jid)
    assert accepted is True

    async with session_factory() as session:
        row = await session.get(BacktestJob, jid)
    assert row.status == BacktestJobStatus.CANCELLED
```

Run:

```bash
cd apps/backend
uv run pytest tests/api/test_backtest_jobs_endpoint.py tests/services/test_backtest_worker.py -v
uv run pytest -q          # full suite still green (including the P2 reproducibility test, since the harness's
                          # behavior is byte-identical when progress_cb / cancel_check are None)
cd ../..
```

- [ ] Endpoint tests pass (10 cases).
- [ ] Worker integration test passes.
- [ ] **P2 reproducibility test still passes.** This is the load-bearing invariant.

---

## §2A.7 — Backend Smoke

```bash
./scripts/dev.sh &
sleep 30

# Get a strategy id
SID=$(curl -s "http://127.0.0.1:8000/api/v1/strategies?limit=1" | jq '.items[0].id')
echo "Strategy: $SID"

# Submit a backtest
JOB=$(curl -s -X POST "http://127.0.0.1:8000/api/v1/strategies/${SID}/backtest" \
  -H "Content-Type: application/json" \
  -d '{
    "start": "2025-11-03T00:00:00+00:00",
    "end": "2025-11-06T00:00:00+00:00",
    "label": "smoke-async"
  }')
echo $JOB | jq
JOB_ID=$(echo $JOB | jq -r '.job_id')

# Subscribe to backtests WS in another terminal:
#   echo '{"action":"subscribe","topics":["backtests"]}' | websocat -n5 ws://127.0.0.1:8000/ws
# You should see: backtest.queued → backtest.started → backtest.progress (multiple) → backtest.completed

# Poll the job status
for i in 1 2 3 4 5 6 7 8 9 10; do
  sleep 2
  curl -s "http://127.0.0.1:8000/api/v1/backtest-jobs/${JOB_ID}" \
    | jq '{status, percent_complete, current_ts, result_id, error_text}'
done

# Verify the BacktestResult landed
curl -s "http://127.0.0.1:8000/api/v1/strategies/${SID}/backtests?limit=1" \
  | jq '.items[0] | {id, label, metrics: {trade_count, total_return}}'

# Negative: submit another while idle
curl -s -X POST "http://127.0.0.1:8000/api/v1/strategies/${SID}/backtest" \
  -H "Content-Type: application/json" \
  -d '{"start":"2025-11-03T00:00:00+00:00","end":"2025-11-06T00:00:00+00:00"}'
# (After the first one completes, this should also 202; if the first is still running, expect 409)

docker compose down
```

- [ ] Submit returns 202 with a job_id.
- [ ] Polling shows status QUEUED → RUNNING → COMPLETED.
- [ ] `percent_complete` advances from 0 toward 100.
- [ ] `BacktestResult` row appears at the end.
- [ ] WS subscriber observes the progress stream (if you ran the websocat).

---

## §2A.8 — Backend Commit and PR

```bash
git add apps/backend/app/db/enums.py
git add apps/backend/app/db/models/backtest_job.py
git add apps/backend/app/db/models/__init__.py
git add apps/backend/alembic/versions/
git add apps/backend/app/strategies/backtester.py
git add apps/backend/app/strategies/backtest_models.py
git add apps/backend/app/services/backtest_worker.py
git add apps/backend/app/lifespan.py
git add apps/backend/app/api/v1/schemas/strategies.py
git add apps/backend/app/api/v1/strategies.py
git add apps/backend/app/api/v1/backtest_jobs.py
git add apps/backend/app/main.py
git add apps/backend/app/ws/gateway.py
git add apps/backend/tests/api/test_backtest_jobs_endpoint.py
git add apps/backend/tests/services/test_backtest_worker.py

git commit -m "feat(backtest): async job queue with progress + cancellation (P4 §2 backend)

- New backtest_jobs table (QUEUED/RUNNING/COMPLETED/FAILED/CANCELLED)
- POST /strategies/{id}/backtest returns 202 with job_id immediately
- 1-year range cap removed (async means no HTTP timeout)
- Single-flight per strategy: 409 if a job already in-flight
- BacktestWorker tick (2s interval) dequeues QUEUED jobs and runs them
  via the existing Backtester (unchanged: P2 reproducibility test still
  green because progress_cb/cancel_check default to None)
- Bus events: backtest.queued / started / progress / completed / failed
  / cancelled. All route to existing 'backtests' WS topic.
- New endpoints: GET/POST /api/v1/backtest-jobs/{id}, cancel via POST.
- Worker reconciles orphaned RUNNING rows on boot (failed: abandoned)
- 10 endpoint tests + 3 worker integration tests"

git push -u origin feat/p4-async-backtest-backend

gh pr create \
  --title "feat(backtest): async job queue with progress (P4 §2 backend)" \
  --body "Backend half of P4 §2. Frontend half (progress UI) is a separate PR."

gh pr checks
gh pr merge --merge --delete-branch
git checkout main && git pull
git tag -a p4-async-backtest-backend-complete -m "P4 §2 backend complete"
git push origin p4-async-backtest-backend-complete
```

- [ ] Backend PR merged.
- [ ] Backend half tagged.

---

# Part B — Frontend (Session 2 of 2)

```bash
git checkout -b feat/p4-async-backtest-frontend
```

## §2B.1 — Type Definitions

Extend `apps/frontend/src/api/types.ts`:

```typescript
export type BacktestJobStatusT =
  | "queued"
  | "running"
  | "completed"
  | "failed"
  | "cancelled";

export interface BacktestJob {
  id: number;
  user_id: number;
  strategy_id: number;
  result_id: number | null;
  status: BacktestJobStatusT;
  label: string;
  percent_complete: number;
  current_ts: string | null;
  submitted_at: string;
  started_at: string | null;
  completed_at: string | null;
  error_text: string | null;
}

export interface BacktestJobListResponse {
  items: BacktestJob[];
  count: number;
}

export interface BacktestJobSubmittedResponse {
  job_id: number;
  strategy_id: number;
  status: BacktestJobStatusT;
  submitted_at: string;
}
```

## §2B.2 — API Client

Extend `apps/frontend/src/api/strategies.ts`. Replace the synchronous `runBacktest` and add new methods:

```typescript
// Replace existing:
submitBacktest: (id: number, body: BacktestRequest) =>
  apiFetch<BacktestJobSubmittedResponse>(`/api/v1/strategies/${id}/backtest`, {
    method: "POST",
    body,
  }),

listBacktestJobs: (id: number, status?: BacktestJobStatusT, limit = 50) => {
  const q = new URLSearchParams();
  if (status) q.set("status", status);
  q.set("limit", String(limit));
  return apiFetch<BacktestJobListResponse>(`/api/v1/strategies/${id}/backtest-jobs?${q}`);
},
```

Create `apps/frontend/src/api/backtest_jobs.ts`:

```typescript
import { apiFetch } from "./client";
import type { BacktestJob } from "./types";

export const backtestJobsApi = {
  get: (id: number) => apiFetch<BacktestJob>(`/api/v1/backtest-jobs/${id}`),
  cancel: (id: number) =>
    apiFetch<BacktestJob>(`/api/v1/backtest-jobs/${id}/cancel`, {
      method: "POST",
      body: {},
    }),
};
```

> Keep the old `runBacktest` name as a deprecated alias for one release if you want a soft migration; for a clean MVP, just rename to `submitBacktest` everywhere.

## §2B.3 — `BacktestRunModal` Rewrite

The old modal blocked on a synchronous response. The new modal:
1. Calls `submitBacktest` → gets a `job_id`.
2. Subscribes to `backtests` WS topic, filters to this `job_id`.
3. Shows progress bar; updates on `backtest.progress`.
4. On `backtest.completed` → fetches the full `BacktestResult` and notifies parent (opens `BacktestResultsView`).
5. On `backtest.failed` → shows error in the modal; keeps modal open for the user to dismiss.
6. On modal close mid-run: the job keeps running; modal disappears. The Backtests tab will show the row update.

Edit `apps/frontend/src/pages/Strategies/BacktestRunModal.tsx`. Replace the run handler and add progress state:

```tsx
import { useEffect, useRef, useState } from "react";
import { strategiesApi } from "@/api/strategies";
import { backtestJobsApi } from "@/api/backtest_jobs";
import { ApiError } from "@/api/client";
import type { Strategy, BacktestResult, BacktestJob } from "@/api/types";
import { useWorkbenchSocket } from "@/hooks/useWorkbenchSocket";

interface Props {
  strategy: Strategy;
  onClose: () => void;
  onCompleted: (result: BacktestResult) => void;
}

export function BacktestRunModal({ strategy, onClose, onCompleted }: Props) {
  const now = new Date();
  const tenDaysAgo = new Date(now.getTime() - 10 * 86400_000);

  const [label, setLabel] = useState("default");
  const [start, setStart] = useState(tenDaysAgo.toISOString().slice(0, 10));
  const [end, setEnd] = useState(now.toISOString().slice(0, 10));
  const [initialEquity, setInitialEquity] = useState("100000");
  const [slippageBps, setSlippageBps] = useState("5");
  const [timeframe, setTimeframe] = useState("1Min");
  const [paramsText, setParamsText] = useState(JSON.stringify(strategy.params, null, 2));

  const [jobId, setJobId] = useState<number | null>(null);
  const [jobStatus, setJobStatus] = useState<string>("queued");
  const [percent, setPercent] = useState(0);
  const [currentTs, setCurrentTs] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  // Listen for backtest events for our specific job_id
  useWorkbenchSocket(["backtests"], async (msg) => {
    const payload = msg.payload as Record<string, unknown>;
    if (jobId === null || payload.job_id !== jobId) return;

    if (msg.type === "backtest.started") {
      setJobStatus("running");
    } else if (msg.type === "backtest.progress") {
      setPercent(Number(payload.percent_complete) || 0);
      setCurrentTs((payload.current_ts as string | null) ?? null);
    } else if (msg.type === "backtest.completed") {
      // Fetch the full BacktestResult
      const backtestId = payload.backtest_id as number;
      try {
        const result = await strategiesApi.getBacktest(strategy.id, backtestId);
        onCompleted(result);
      } catch (e) {
        setError(`Could not load result: ${e}`);
      }
    } else if (msg.type === "backtest.failed") {
      setJobStatus("failed");
      setError(String(payload.error_text || "Backtest failed"));
    } else if (msg.type === "backtest.cancelled") {
      setJobStatus("cancelled");
      setError("Backtest cancelled");
    }
  });

  // Polling fallback (in case WS drops): poll the job every 3s while in-flight
  useEffect(() => {
    if (jobId === null) return;
    if (jobStatus === "completed" || jobStatus === "failed" || jobStatus === "cancelled") return;
    const id = setInterval(async () => {
      try {
        const job = await backtestJobsApi.get(jobId);
        setJobStatus(job.status);
        setPercent(job.percent_complete);
        setCurrentTs(job.current_ts);
        if (job.status === "completed" && job.result_id) {
          const result = await strategiesApi.getBacktest(strategy.id, job.result_id);
          onCompleted(result);
        } else if (job.status === "failed") {
          setError(job.error_text || "Backtest failed");
        }
      } catch {
        // ignore polling errors
      }
    }, 3000);
    return () => clearInterval(id);
  }, [jobId, jobStatus, strategy.id, onCompleted]);

  async function handleSubmit() {
    setError(null);
    let paramsParsed: Record<string, unknown>;
    try {
      paramsParsed = paramsText.trim() ? JSON.parse(paramsText) : {};
    } catch (e) {
      setError(`Params not valid JSON: ${e}`);
      return;
    }
    try {
      const submitted = await strategiesApi.submitBacktest(strategy.id, {
        start: new Date(start).toISOString(),
        end: new Date(end).toISOString(),
        label: label.trim() || "default",
        initial_equity: initialEquity,
        slippage_bps: Number(slippageBps),
        timeframe,
        params: paramsParsed,
      });
      setJobId(submitted.job_id);
      setJobStatus(submitted.status);
    } catch (e) {
      if (e instanceof ApiError) {
        setError(`${e.detail} (status ${e.status})`);
      } else {
        setError(String(e));
      }
    }
  }

  async function handleCancel() {
    if (jobId === null) return;
    try {
      await backtestJobsApi.cancel(jobId);
    } catch (e) {
      setError(`Cancel failed: ${e}`);
    }
  }

  const inFlight = jobId !== null && (jobStatus === "queued" || jobStatus === "running");

  return (
    <div className="fixed inset-0 z-40 flex items-center justify-center bg-black/70">
      <div className="w-[32rem] max-h-[90vh] overflow-y-auto rounded-lg border border-gray-700 bg-gray-950 p-5">
        <div className="mb-3 flex items-center justify-between">
          <h2 className="text-lg font-semibold text-white">
            {inFlight ? "Running backtest…" : "Run backtest"}
          </h2>
          <button onClick={onClose} className="text-gray-400 hover:text-white">✕</button>
        </div>

        {jobId === null ? (
          /* ---- form ---- */
          <FormView
            label={label} setLabel={setLabel}
            start={start} setStart={setStart}
            end={end} setEnd={setEnd}
            initialEquity={initialEquity} setInitialEquity={setInitialEquity}
            slippageBps={slippageBps} setSlippageBps={setSlippageBps}
            timeframe={timeframe} setTimeframe={setTimeframe}
            paramsText={paramsText} setParamsText={setParamsText}
            error={error}
          />
        ) : (
          /* ---- progress ---- */
          <ProgressView
            status={jobStatus}
            percent={percent}
            currentTs={currentTs}
            error={error}
          />
        )}

        <div className="mt-4 flex justify-end gap-2">
          {jobId === null ? (
            <>
              <button onClick={onClose} className="rounded bg-gray-700 px-3 py-1.5 text-sm text-gray-200">
                Cancel
              </button>
              <button onClick={handleSubmit}
                className="rounded bg-blue-700 px-3 py-1.5 text-sm font-semibold text-white hover:bg-blue-600">
                Run
              </button>
            </>
          ) : inFlight ? (
            <>
              <button onClick={handleCancel}
                className="rounded bg-amber-800 px-3 py-1.5 text-sm font-semibold text-white hover:bg-amber-700">
                Cancel job
              </button>
              <button onClick={onClose}
                className="rounded bg-gray-700 px-3 py-1.5 text-sm text-gray-200">
                Close (job keeps running)
              </button>
            </>
          ) : (
            <button onClick={onClose}
              className="rounded bg-gray-700 px-3 py-1.5 text-sm text-gray-200">
              Close
            </button>
          )}
        </div>
      </div>
    </div>
  );
}

function FormView(props: any) {
  // Extract the form into its own component for readability — same fields as
  // the old modal. Body identical to the prior implementation.
  return (
    <div className="space-y-3 text-sm text-gray-300">
      {/* Label / start / end / initialEquity / slippage / timeframe / params — same as before */}
      {/* (copy verbatim from the prior implementation) */}
      {props.error && (
        <div className="rounded border border-red-700 bg-red-900/40 p-2 text-sm text-red-200">
          {props.error}
        </div>
      )}
    </div>
  );
}

function ProgressView({
  status, percent, currentTs, error,
}: { status: string; percent: number; currentTs: string | null; error: string | null }) {
  return (
    <div className="space-y-4">
      <div>
        <div className="mb-1 flex justify-between text-xs text-gray-400">
          <span>Status: <span className="text-white">{status}</span></span>
          <span>{percent.toFixed(1)}%</span>
        </div>
        <div className="h-3 overflow-hidden rounded bg-gray-800">
          <div
            className={`h-full transition-all ${
              status === "failed" || status === "cancelled" ? "bg-rose-600" : "bg-blue-600"
            }`}
            style={{ width: `${Math.min(100, percent)}%` }}
          />
        </div>
      </div>
      {currentTs && (
        <div className="text-xs text-gray-500">
          Current bar: {new Date(currentTs).toLocaleString()}
        </div>
      )}
      {error && (
        <div className="rounded border border-red-700 bg-red-900/40 p-2 text-sm text-red-200">
          {error}
        </div>
      )}
      {status === "queued" && (
        <div className="text-xs text-gray-500">
          Waiting for worker… (typically &lt;3s)
        </div>
      )}
    </div>
  );
}
```

- [ ] Modal split into form/progress views; switches on `jobId !== null`.
- [ ] WS-driven progress with polling fallback.
- [ ] Cancel button when in-flight.
- [ ] Close button explicitly says "(job keeps running)" when in-flight.

## §2B.4 — `BacktestsTab` Updates

The tab list view from P2 Session 5 already shows `BacktestSummary` rows from completed backtests. Add a small in-flight indicator that lists current QUEUED/RUNNING jobs above the completed rows.

Edit `apps/frontend/src/pages/Strategies/tabs/BacktestsTab.tsx`. Add an `useEffect` that polls jobs every 5s and lists in-flight ones:

```tsx
const [jobs, setJobs] = useState<BacktestJob[]>([]);

const loadJobs = useCallback(async () => {
  try {
    // Pull both QUEUED and RUNNING in two calls
    const [queued, running] = await Promise.all([
      strategiesApi.listBacktestJobs(strategy.id, "queued"),
      strategiesApi.listBacktestJobs(strategy.id, "running"),
    ]);
    setJobs([...queued.items, ...running.items]);
  } catch {
    setJobs([]);
  }
}, [strategy.id]);

useEffect(() => {
  loadJobs();
  const id = setInterval(loadJobs, 5000);
  return () => clearInterval(id);
}, [loadJobs]);

// Also re-fetch on WS events for this strategy
useWorkbenchSocket(["backtests"], (msg) => {
  const sid = (msg.payload as any).strategy_id;
  if (sid === strategy.id) {
    loadJobs();
    load();    // existing: loads completed summaries
  }
});
```

Render an "In flight" section above the existing completed-results table:

```tsx
{jobs.length > 0 && (
  <div className="rounded border border-blue-800 bg-blue-950/30 p-3">
    <div className="mb-2 text-sm font-semibold text-blue-200">
      In flight ({jobs.length})
    </div>
    {jobs.map((j) => (
      <div key={j.id} className="flex items-center justify-between border-t border-blue-900 py-2 text-sm">
        <div>
          <span className="font-semibold text-white">{j.label}</span>
          <span className="ml-2 text-xs text-gray-400">
            {j.status} · {j.percent_complete.toFixed(0)}%
          </span>
        </div>
        <button
          onClick={() => backtestJobsApi.cancel(j.id).then(loadJobs)}
          className="rounded bg-amber-800 px-2 py-1 text-xs text-white hover:bg-amber-700"
        >
          Cancel
        </button>
      </div>
    ))}
  </div>
)}
```

- [ ] In-flight section renders above the completed-results table.
- [ ] Cancel button on each in-flight job works.

## §2B.5 — Frontend Tests

Create `apps/frontend/src/pages/Strategies/__tests__/BacktestRunModal.test.tsx`:

```tsx
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { BacktestRunModal } from "../BacktestRunModal";
import { strategiesApi } from "@/api/strategies";
import { backtestJobsApi } from "@/api/backtest_jobs";

vi.mock("@/api/strategies");
vi.mock("@/api/backtest_jobs");
vi.mock("@/hooks/useWorkbenchSocket", () => ({
  useWorkbenchSocket: () => {},
}));

const mockedStrategies = vi.mocked(strategiesApi);
const mockedJobs = vi.mocked(backtestJobsApi);

const baseStrategy = {
  id: 1, name: "rsi", version: "0.1.0", type: "python" as const,
  status: "idle" as const, code_path: "examples/rsi.py",
  params: {}, symbols: ["AAPL"], schedule: "*/1 * * * *",
  risk_limits_id: null, error_text: null,
  created_at: new Date().toISOString(), updated_at: new Date().toISOString(),
};

beforeEach(() => { vi.resetAllMocks(); });

describe("BacktestRunModal (async)", () => {
  it("submits and transitions to progress view", async () => {
    mockedStrategies.submitBacktest.mockResolvedValue({
      job_id: 42, strategy_id: 1, status: "queued",
      submitted_at: new Date().toISOString(),
    } as any);
    render(<BacktestRunModal strategy={baseStrategy as any} onClose={() => {}} onCompleted={() => {}} />);
    fireEvent.click(screen.getByText("Run"));
    await waitFor(() =>
      expect(mockedStrategies.submitBacktest).toHaveBeenCalled()
    );
    expect(await screen.findByText(/Running backtest/i)).toBeInTheDocument();
  });

  it("shows cancel button while in flight", async () => {
    mockedStrategies.submitBacktest.mockResolvedValue({
      job_id: 42, strategy_id: 1, status: "queued",
      submitted_at: new Date().toISOString(),
    } as any);
    mockedJobs.cancel.mockResolvedValue({} as any);
    render(<BacktestRunModal strategy={baseStrategy as any} onClose={() => {}} onCompleted={() => {}} />);
    fireEvent.click(screen.getByText("Run"));
    const cancelBtn = await screen.findByText(/Cancel job/i);
    fireEvent.click(cancelBtn);
    await waitFor(() => expect(mockedJobs.cancel).toHaveBeenCalledWith(42));
  });

  it("Close button says 'job keeps running' while in flight", async () => {
    mockedStrategies.submitBacktest.mockResolvedValue({
      job_id: 42, strategy_id: 1, status: "queued",
      submitted_at: new Date().toISOString(),
    } as any);
    render(<BacktestRunModal strategy={baseStrategy as any} onClose={() => {}} onCompleted={() => {}} />);
    fireEvent.click(screen.getByText("Run"));
    expect(await screen.findByText(/job keeps running/i)).toBeInTheDocument();
  });
});
```

Run:

```bash
cd apps/frontend
pnpm test --run
cd ../..
```

- [ ] All Vitest tests pass.

## §2B.6 — Frontend Smoke

```bash
./scripts/dev.sh
```

In a browser:
1. Strategies → click a strategy → Backtests tab → "Run backtest".
2. Modal form → fill defaults → Run.
3. Modal transitions to progress view, shows status "queued" briefly, then "running".
4. Progress bar advances; current bar timestamp ticks.
5. On completion → results modal opens.
6. Submit another backtest, close the modal mid-run. Verify the Backtests tab shows the in-flight indicator.
7. Click Cancel on the in-flight row → row transitions to "cancelled" (after a few seconds).

- [ ] All steps green.

## §2B.7 — Frontend Commit and PR

```bash
git add apps/frontend/src/api/types.ts
git add apps/frontend/src/api/strategies.ts
git add apps/frontend/src/api/backtest_jobs.ts
git add apps/frontend/src/pages/Strategies/BacktestRunModal.tsx
git add apps/frontend/src/pages/Strategies/tabs/BacktestsTab.tsx
git add apps/frontend/src/pages/Strategies/__tests__/BacktestRunModal.test.tsx

git commit -m "feat(frontend): async backtest progress + cancellation (P4 §2 frontend)

- submitBacktest replaces synchronous runBacktest
- New backtestJobsApi: get(), cancel()
- BacktestRunModal now: submit → progress bar → completion (via WS) or
  polling fallback. Cancel button mid-run; Close says 'job keeps running'.
- BacktestsTab: 'In flight' section above completed-results table with
  per-job Cancel buttons. Updates via 5s poll AND backtests WS topic."

git push -u origin feat/p4-async-backtest-frontend

gh pr create \
  --title "feat(frontend): async backtest progress + cancellation (P4 §2 frontend)" \
  --body "Frontend half of P4 §2. Backend was tag p4-async-backtest-backend-complete."

gh pr checks
gh pr merge --merge --delete-branch
git checkout main && git pull
git tag -a p4-async-backtest-complete -m "P4 §2 complete (backend + frontend)"
git push origin p4-async-backtest-complete
```

- [ ] Frontend PR merged.
- [ ] `p4-async-backtest-complete` tag pushed.
- [ ] `todo.md` updated: P4 §2 ✅.

---

## Verification Checklist (both halves)

### Backend (Part A)

- [ ] §2A.1 `backtest_jobs` table + enum + model; migration round-trips.
- [ ] §2A.2 `Backtester.run` accepts optional `progress_cb` + `cancel_check`; P2 reproducibility test still green.
- [ ] §2A.3 `BacktestWorker` dequeues jobs, runs them, publishes events; reconciles orphans on boot.
- [ ] §2A.4 `POST /strategies/{id}/backtest` returns 202; 1-year cap removed; single-flight per strategy.
- [ ] §2A.4 `GET /backtest-jobs/{id}` + `POST /backtest-jobs/{id}/cancel` work.
- [ ] §2A.5 WS gateway routes five new events to `backtests` topic.
- [ ] §2A.6 13 backend tests pass.
- [ ] §2A.7 Curl smoke walks the happy path.
- [ ] §2A.8 Backend PR merged, tagged.

### Frontend (Part B)

- [ ] §2B.1 Types extended.
- [ ] §2B.2 API client updated; `backtest_jobs.ts` created.
- [ ] §2B.3 BacktestRunModal split form/progress; WS-driven with polling fallback.
- [ ] §2B.4 BacktestsTab shows in-flight section.
- [ ] §2B.5 Vitest tests pass.
- [ ] §2B.6 Live smoke walks the full UI flow.
- [ ] §2B.7 Frontend PR merged; final tag pushed.

---

## Notes & Gotchas

1. **The P2 reproducibility test must stay green.** `Backtester.run` with `progress_cb=None` and `cancel_check=None` is byte-identical to the P2 behavior. If you ever see the reproducibility test flake after this PR, the culprit is almost certainly a change in the harness's iteration order, not the new callbacks themselves.

2. **Single-flight per strategy, not per user.** Two different strategies can backtest in parallel. The worker still processes them serially (one tick = one job), but the queue accepts them. If you start hitting "I want concurrent worker slots" pressure, that's a real signal — but it's P5+ scope, not this item.

3. **Progress cadence is bar-index-based, not wall-clock-based.** The harness fires `progress_cb` at most every `master_len // 200` bars (≈200 callbacks per backtest regardless of length). On a 1-minute, 5-year backtest (~500K bars) this is 1 callback per 2500 bars; on a 1-day, 3-month backtest (~60 bars) it's almost every bar. Wall-clock-based throttling would be more uniform but adds time-checking overhead inside a hot loop.

4. **Cancellation is checked between bars, not within them.** A bar that hangs in `strategy.on_bar` (e.g., a slow indicator computation) won't honor cancellation until it returns. In practice strategies are fast; if you ever ship a strategy with multi-second per-bar work, you'd want to thread cancellation deeper — but for P4 this is fine.

5. **Orphan reconciliation on worker start** transitions RUNNING rows to FAILED with `error_text='abandoned: worker restarted'`. The trader sees a clear failure rather than a job stuck in RUNNING forever. The trade-off: a backtest that was 99% done at the moment of crash gets discarded. Acceptable for MVP; if real users find this painful, P4 polish could checkpoint progress mid-run.

6. **`config_json._symbols`** uses an underscore prefix to mark it as worker-internal. The Pydantic `BacktestRequest` doesn't have `_symbols`; the API handler injects it before persistence. This keeps the API contract clean while letting the worker rehydrate the full config independently.

7. **Bus events use `backtest.*` topic-prefix routing.** All five new events route to the existing `backtests` WS topic with no replay-window change. Frontend clients that already subscribe to `backtests` automatically receive the new event types — they just need to handle the new `msg.type` values.

8. **`backtest.completed` event shape is back-compatible.** P2 Session 4's payload was `{backtest_id, strategy_id, label, metrics}`; the new worker adds `job_id`. Frontend code that doesn't read `job_id` continues to work unchanged.

9. **The synchronous endpoint is GONE, not deprecated.** `POST /strategies/{id}/backtest` returns 202 now — clients that expected a 200 with the full result will need to update. The breaking change is acceptable for an MVP product with one user; for a public API it would warrant a `/v2` route. Note in the runbook.

10. **Single-process APScheduler.** `max_instances=1` on the tick job. If you ever scale to multiple backend workers, you'll need a real job queue (Redis, Postgres `FOR UPDATE SKIP LOCKED`, etc.) and a distributed worker pool. Don't pre-build it; the day you need it, the architecture should change.

11. **No retry-on-failure.** A failed backtest stays failed. The error text is the user's diagnostic; they submit a fresh job. If the failure was transient (Alpaca rate limit, etc.), it'll work on retry. Don't auto-retry — silently retrying a strategy bug masks the bug.

12. **Reproducibility test runs on the synchronous code path.** P2 Session 3's `test_reference_strategy_backtest_is_reproducible` calls `harness.run(...)` directly without `progress_cb`/`cancel_check`. After this PR, that path is preserved — the worker is a layer on top, not a replacement. The test stays green for free.

13. **The worker survives bar_cache misses.** If a backtest's date range has no cached bars, the harness returns empty metrics (P2 Session 3 behavior); the worker writes them as the completed BacktestResult. The trader sees `trade_count=0`. Could improve UX by detecting "no bars" earlier and failing fast, but the current behavior is correct, just less informative.

14. **Don't bundle other P4 items into either PR.** Each P4 item is independently tagged. The backend + frontend PRs for §2 share a tag but neither overlaps with §3 (Opportunities page) or other items.

---

*End of P4 Item 2 v0.1.*
