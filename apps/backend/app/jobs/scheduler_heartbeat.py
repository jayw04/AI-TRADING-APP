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
from datetime import UTC, datetime
from pathlib import Path

import structlog
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.models.scheduler_heartbeat import SchedulerHeartbeat

logger = structlog.get_logger(__name__)


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
    session_factory: async_sessionmaker[AsyncSession], host_id: str, *, armed: bool
) -> None:
    code_version = resolve_code_version()
    async with session_factory() as session:
        row = await session.get(SchedulerHeartbeat, host_id)
        now = datetime.now(UTC)
        if row is None:
            session.add(
                SchedulerHeartbeat(
                    host_id=host_id, armed=armed, last_beat_at=now, code_version=code_version
                )
            )
        else:
            row.armed = armed
            row.last_beat_at = now
            row.code_version = code_version
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
    session_factory: async_sessionmaker[AsyncSession], host_id: str
) -> None:
    """Scheduler entrypoint (ACTIVE hosts only): refresh this host's heartbeat."""
    try:
        await _upsert(session_factory, host_id, armed=True)
    except Exception:  # noqa: BLE001 — telemetry is best-effort, never break the schedule
        logger.exception("scheduler_heartbeat_failed", host_id=host_id)
