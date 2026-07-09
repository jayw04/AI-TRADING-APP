"""Scheduler heartbeat writer (ADR 0032).

The ACTIVE host's armed scheduler upserts a `scheduler_heartbeat` row every tick so the running
host is observable: which `host_id` is armed, when it last beat, and which `code_version` is
dispatching (so a debugger immediately knows *which code* was running). Backs the cutover
single-armed verification and the missed-scheduler alarm.

Best-effort everywhere: a missing table or any DB error is logged and swallowed — the heartbeat
must never disturb scheduling or trading.
"""

from __future__ import annotations

import os
import socket
import uuid
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import structlog
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.models.scheduler_heartbeat import SchedulerHeartbeat

logger = structlog.get_logger(__name__)


def _latest_dispatch_at(engine: Any) -> datetime | None:
    """The engine's most recent successful ``on_bar`` across running strategies, as an
    aware UTC datetime — or ``None`` when nothing has dispatched this process yet."""
    try:
        epochs = [
            r.last_dispatch_at
            for r in engine.running_strategies()
            if r.last_dispatch_at is not None
        ]
        if not epochs:
            return None
        return datetime.fromtimestamp(max(epochs), tz=UTC)
    except Exception:  # noqa: BLE001 — telemetry is best-effort, never break the beat
        return None


def resolve_host_id() -> str:
    """Stable host identity (ADR 0032 R4).

    Prefers the explicit, human-friendly ``WORKBENCH_HOST_ID`` (set in the prod overlay, e.g.
    ``ec2-paper``). Otherwise persists a ``hostname-<uuid8>`` id under ``data/host_id`` so the
    identity survives hostname changes (a bare hostname can change; the persisted id does not).
    """
    explicit = os.environ.get("WORKBENCH_HOST_ID")
    if explicit:
        return explicit
    path = Path(os.environ.get("WORKBENCH_HOST_ID_FILE", "data/host_id"))
    try:
        if path.exists():
            val = path.read_text(encoding="utf-8").strip()
            if val:
                return val
        hid = f"{socket.gethostname()}-{uuid.uuid4().hex[:8]}"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(hid, encoding="utf-8")
        return hid
    except OSError:
        return socket.gethostname()


def resolve_code_version() -> str:
    """Which code is dispatching (ADR 0032 R-heartbeat). The bootstrap sets
    ``WORKBENCH_CODE_VERSION`` to the git short-sha; falls back to the app version."""
    env = os.environ.get("WORKBENCH_CODE_VERSION")
    if env:
        return env
    try:
        from app.config import get_settings

        return get_settings().version
    except Exception:  # noqa: BLE001 — never block on version resolution
        return "unknown"


async def _upsert(
    session_factory: async_sessionmaker[AsyncSession],
    host_id: str,
    *,
    armed: bool,
    last_dispatch_at: datetime | None = None,
) -> None:
    code_version = resolve_code_version()
    async with session_factory() as session:
        row = await session.get(SchedulerHeartbeat, host_id)
        now = datetime.now(UTC)
        if row is None:
            session.add(
                SchedulerHeartbeat(
                    host_id=host_id, armed=armed, last_beat_at=now, code_version=code_version,
                    last_dispatch_at=last_dispatch_at,
                )
            )
        else:
            row.armed = armed
            row.last_beat_at = now
            row.code_version = code_version
            # Only advance the stamp — the in-memory engine value resets on restart, and
            # clobbering the persisted stamp with None would fake a dispatch gap.
            if last_dispatch_at is not None:
                row.last_dispatch_at = last_dispatch_at
        await session.commit()


async def write_startup_heartbeat(
    session_factory: async_sessionmaker[AsyncSession], host_id: str, *, armed: bool
) -> None:
    """Record this host's arm state once at boot (so a STANDBY host is visible too)."""
    try:
        await _upsert(session_factory, host_id, armed=armed)
        logger.info("scheduler_heartbeat_startup", host_id=host_id, armed=armed)
    except Exception:  # noqa: BLE001 — telemetry is best-effort, never break boot
        logger.exception("scheduler_heartbeat_startup_failed", host_id=host_id)


async def run_scheduler_heartbeat(
    session_factory: async_sessionmaker[AsyncSession],
    host_id: str,
    engine_getter: Callable[[], Any] | None = None,
) -> None:
    """Scheduler entrypoint (ACTIVE hosts only): refresh this host's heartbeat.

    ``engine_getter`` lazily resolves the StrategyEngine (it is constructed after this job
    is registered); when available, the row also carries the engine's latest successful
    ``on_bar`` time so the CloudWatch ``MissedDispatch`` metric reads real dispatch
    liveness instead of a never-written NULL (which made the alarm fire every market
    morning by construction).
    """
    try:
        engine = engine_getter() if engine_getter is not None else None
        stamp = _latest_dispatch_at(engine) if engine is not None else None
        await _upsert(session_factory, host_id, armed=True, last_dispatch_at=stamp)
    except Exception:  # noqa: BLE001 — telemetry is best-effort, never break the schedule
        logger.exception("scheduler_heartbeat_failed", host_id=host_id)
