"""Daily SQLite backup (P5 §8.5) — WAL-aware, no sqlite3 CLI required.

The backend image ships neither ``bash`` nor the ``sqlite3`` CLI, and
``app/lifespan.py`` lives at ``/app/app/lifespan.py`` so
``Path(__file__).parents[3]`` (repo-root ``scripts/backup_db.sh``) raises
``IndexError``. The scheduled job therefore uses Python's
``sqlite3.Connection.backup`` against ``WORKBENCH_DB_URL`` /
``WORKBENCH_DB_PATH``. Repo-root ``scripts/backup_db.sh`` remains for hosts
that have the CLI.
"""

from __future__ import annotations

import os
import sqlite3
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import structlog
from sqlalchemy.engine.url import make_url

logger = structlog.get_logger(__name__)

DEFAULT_RETENTION_DAYS = 30
DEFAULT_DOCKER_DB = Path("/app/data/workbench.sqlite")


def sqlite_file_path_from_url(db_url: str) -> Path:
    """Map a SQLAlchemy sqlite URL to a filesystem path."""
    url = make_url(db_url)
    if url.get_backend_name() != "sqlite":
        raise ValueError(
            f"daily backup supports sqlite only, got backend={url.get_backend_name()!r}"
        )
    if not url.database:
        raise ValueError("sqlite URL has no database path")
    return Path(url.database)


def resolve_sqlite_db_path(
    *,
    db_path: Path | str | None = None,
    db_url: str | None = None,
) -> Path:
    if db_path is not None:
        return Path(db_path)
    env_path = os.environ.get("WORKBENCH_DB_PATH")
    if env_path:
        return Path(env_path)
    url = db_url or os.environ.get("WORKBENCH_DB_URL")
    if not url:
        try:
            from app.config import get_settings

            url = get_settings().db_url
        except Exception:
            url = None
    if url:
        return sqlite_file_path_from_url(url)
    if DEFAULT_DOCKER_DB.is_file():
        return DEFAULT_DOCKER_DB
    raise FileNotFoundError("no SQLite database path resolved for daily backup")


def resolve_backup_dir(*, backup_dir: Path | str | None = None, db_path: Path) -> Path:
    if backup_dir is not None:
        return Path(backup_dir)
    env_dir = os.environ.get("WORKBENCH_BACKUP_DIR")
    if env_dir:
        return Path(env_dir)
    return db_path.parent / "backups"


def _retention_days(explicit: int | None) -> int:
    if explicit is not None:
        return explicit
    raw = os.environ.get("WORKBENCH_BACKUP_RETENTION_DAYS", str(DEFAULT_RETENTION_DAYS))
    return int(raw)


def _prune_old_backups(backup_dir: Path, retention_days: int, now: datetime) -> int:
    cutoff = now - timedelta(days=retention_days)
    pruned = 0
    for path in backup_dir.glob("workbench-*.sqlite"):
        if not path.is_file():
            continue
        mtime = datetime.fromtimestamp(path.stat().st_mtime, tz=UTC)
        if mtime < cutoff:
            path.unlink(missing_ok=True)
            pruned += 1
    return pruned


def run_sqlite_backup(
    *,
    db_path: Path | str | None = None,
    backup_dir: Path | str | None = None,
    retention_days: int | None = None,
    today_utc: datetime | None = None,
    skip_integrity_check: bool = False,
) -> dict[str, Any]:
    """Take today's WAL-aware snapshot. Idempotent: existing today's file is skipped.

    Failures raise. The scheduler wrapper logs and swallows.
    """
    now = today_utc or datetime.now(UTC)
    src = resolve_sqlite_db_path(db_path=db_path)
    if not src.is_file():
        raise FileNotFoundError(f"SQLite database not found: {src}")
    dest_dir = resolve_backup_dir(backup_dir=backup_dir, db_path=src)
    dest_dir.mkdir(parents=True, exist_ok=True)
    target = dest_dir / f"workbench-{now.date().isoformat()}.sqlite"
    keep = _retention_days(retention_days)

    if target.is_file():
        logger.info("daily_backup_skipped_exists", path=str(target))
        return {
            "path": str(target),
            "bytes": target.stat().st_size,
            "skipped": True,
            "pruned": 0,
        }

    partial = target.with_name(target.name + ".partial")
    partial.unlink(missing_ok=True)
    t0 = time.time()
    src_conn = sqlite3.connect(f"file:{src.as_posix()}?mode=ro", uri=True, timeout=300)
    try:
        dst_conn = sqlite3.connect(str(partial), timeout=300)
        try:
            src_conn.backup(dst_conn)
            if not skip_integrity_check:
                ok = dst_conn.execute("PRAGMA integrity_check").fetchone()
                if ok is None or ok[0] != "ok":
                    raise RuntimeError(f"backup integrity_check failed: {ok!r}")
        finally:
            dst_conn.close()
    finally:
        src_conn.close()

    partial.replace(target)
    pruned = _prune_old_backups(dest_dir, keep, now)
    size = target.stat().st_size
    elapsed_s = round(time.time() - t0, 1)
    logger.info(
        "daily_backup_written",
        path=str(target),
        bytes=size,
        elapsed_s=elapsed_s,
        pruned=pruned,
    )
    return {
        "path": str(target),
        "bytes": size,
        "skipped": False,
        "pruned": pruned,
        "elapsed_s": elapsed_s,
    }
