"""StrategyFileWatcher — watches ``strategies_user/`` for .py modifications
and marks affected strategies as needing reload.

Design choices:

- **Watch + mark only.** The watcher does NOT trigger an automatic reload.
  Auto-reloading a running strategy during market hours while it holds
  positions is a class of bug we don't want to invent. The user clicks
  Reload (POST /api/v1/strategies/{id}/reload).
- **Per-file granularity.** A strategy is matched by exact equality of
  ``strategies.code_path`` against the modified file's relative path under
  ``strategies_user/``. Editing a helper file imported by RSI does NOT
  mark RSI as pending — module-graph tracking is out of scope (P4 §4
  Gotcha #4).
- **Debounced.** ``watchfiles.awatch`` already coalesces inside a ``step``
  window; we additionally apply a per-file cooldown to prevent a tight
  save loop from flooding the bus.
- **Best-effort.** A loop crash logs but doesn't take the backend down —
  the watcher is non-critical.
"""
from __future__ import annotations

import asyncio
import contextlib
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from watchfiles import Change, awatch

from app.db.models.strategy import Strategy as StrategyRow

logger = structlog.get_logger(__name__)


# Per-file mark cooldown. A user saving in a tight loop (autosave on every
# keystroke) shouldn't generate one bus event per stroke.
COOLDOWN_SECONDS = 2.0


class StrategyFileWatcher:
    """Long-lived asyncio task that bridges ``watchfiles.awatch`` to the DB.

    One instance per backend process. Started in :mod:`app.lifespan`; cancel
    on shutdown to release the underlying inotify (or equivalent) descriptor.
    """

    def __init__(
        self,
        *,
        root: Path,
        session_factory: async_sessionmaker[AsyncSession],
        bus: Any,
    ) -> None:
        self._root = root.resolve()
        self._session_factory = session_factory
        self._bus = bus
        self._task: asyncio.Task[None] | None = None
        self._stop_event = asyncio.Event()
        self._last_marked_at: dict[str, float] = {}

    async def start(self) -> None:
        if not self._root.exists():
            logger.warning(
                "strategy_file_watcher_root_missing",
                root=str(self._root),
            )
            return
        if self._task is not None:
            return
        self._stop_event.clear()
        self._task = asyncio.create_task(
            self._run(), name="strategy_file_watcher"
        )
        logger.info("strategy_file_watcher_started", root=str(self._root))

    async def stop(self) -> None:
        self._stop_event.set()
        if self._task is None:
            return
        try:
            await asyncio.wait_for(self._task, timeout=5.0)
        except TimeoutError:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await self._task
        self._task = None
        logger.info("strategy_file_watcher_stopped")

    async def _run(self) -> None:
        """Long-lived watch loop. ``awatch`` yields a batch per debounce
        window; we route each batch through ``_handle_changes``."""
        try:
            async for changes in awatch(
                str(self._root),
                stop_event=self._stop_event,
                step=300,  # ms debounce window inside watchfiles
                recursive=True,
            ):
                await self._handle_changes(changes)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("strategy_file_watcher_loop_crashed")
            # Swallow — the watcher is non-critical; we don't want it
            # crashing to take the rest of the backend down.

    async def _handle_changes(self, changes: set[tuple[Change, str]]) -> None:
        """Process one batch of file-system events."""
        relevant_paths: set[str] = set()
        for change, path in changes:
            if change not in (Change.modified, Change.added):
                continue
            p = Path(path)
            if p.suffix != ".py":
                continue
            if "__pycache__" in p.parts:
                continue
            if p.name.startswith("."):  # hidden / editor swap files
                continue
            try:
                rel = p.resolve().relative_to(self._root)
            except ValueError:
                continue
            relevant_paths.add(str(rel).replace("\\", "/"))

        if not relevant_paths:
            return

        now_ts = time.time()
        for rel_path in relevant_paths:
            last = self._last_marked_at.get(rel_path, 0.0)
            if now_ts - last < COOLDOWN_SECONDS:
                logger.debug(
                    "strategy_file_watcher_cooldown_skip", path=rel_path
                )
                continue
            self._last_marked_at[rel_path] = now_ts
            await self._mark_strategies_for_path(rel_path)

    async def _mark_strategies_for_path(self, rel_path: str) -> None:
        """Mark every strategy whose ``code_path == rel_path`` as pending
        reload and publish one ``strategy.pending_reload`` event per
        affected strategy."""
        async with self._session_factory() as session:
            stmt = select(StrategyRow).where(StrategyRow.code_path == rel_path)
            strategies = (await session.execute(stmt)).scalars().all()
            if not strategies:
                logger.debug(
                    "strategy_file_watcher_no_match", path=rel_path
                )
                return
            now = datetime.now(UTC)
            ids: list[int] = []
            for s in strategies:
                s.has_pending_reload = True
                s.pending_reload_at = now
                ids.append(s.id)
            await session.commit()

        if self._bus is not None:
            for sid in ids:
                try:
                    await self._bus.publish(
                        "strategy.pending_reload",
                        {
                            "strategy_id": sid,
                            "code_path": rel_path,
                            "detected_at": now.isoformat(),
                        },
                    )
                except Exception:
                    logger.exception(
                        "strategy_file_watcher_publish_failed",
                        strategy_id=sid,
                    )

        logger.info(
            "strategy_file_watcher_marked",
            path=rel_path,
            strategy_count=len(ids),
            ids=ids,
        )
