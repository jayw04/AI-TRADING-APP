"""Python-native daily SQLite backup — Docker layout + opportunity_occurrence."""

from __future__ import annotations

import os
import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from app.jobs.sqlite_backup import (
    run_sqlite_backup,
    sqlite_file_path_from_url,
)


def _make_db(path: Path, *, n_rows: int = 2) -> None:
    conn = sqlite3.connect(str(path))
    conn.execute(
        """
        CREATE TABLE opportunity_occurrence (
            id INTEGER PRIMARY KEY,
            symbol TEXT NOT NULL,
            candidate_date TEXT NOT NULL,
            family TEXT NOT NULL
        )
        """
    )
    conn.execute("CREATE TABLE unrelated (id INTEGER PRIMARY KEY, note TEXT)")
    conn.execute("INSERT INTO unrelated (note) VALUES ('keep-me')")
    for i in range(n_rows):
        conn.execute(
            "INSERT INTO opportunity_occurrence (symbol, candidate_date, family) VALUES (?,?,?)",
            (f"SYM{i}", "2026-08-14" if i == 0 else "2026-08-21", "MOM-CORE"),
        )
    conn.commit()
    conn.close()


def test_sqlite_url_four_slashes_is_absolute_posix() -> None:
    path = sqlite_file_path_from_url("sqlite+aiosqlite:////app/data/workbench.sqlite")
    assert path.as_posix() == "/app/data/workbench.sqlite"


def test_sqlite_url_relative() -> None:
    path = sqlite_file_path_from_url("sqlite+aiosqlite:///./data/workbench.sqlite")
    assert path.as_posix().endswith("data/workbench.sqlite")


def test_backup_includes_opportunity_occurrence(tmp_path: Path) -> None:
    src = tmp_path / "workbench.sqlite"
    dest = tmp_path / "backups"
    _make_db(src, n_rows=2)
    now = datetime(2026, 8, 26, 6, 0, tzinfo=UTC)
    result = run_sqlite_backup(db_path=src, backup_dir=dest, today_utc=now)
    assert result["skipped"] is False
    target = Path(result["path"])
    assert target.name == "workbench-2026-08-26.sqlite"
    bak = sqlite3.connect(f"file:{target.as_posix()}?mode=ro", uri=True)
    try:
        tables = {r[0] for r in bak.execute("SELECT name FROM sqlite_master").fetchall()}
        assert "opportunity_occurrence" in tables
        count, lo, hi = bak.execute(
            "SELECT COUNT(*), MIN(candidate_date), MAX(candidate_date) FROM opportunity_occurrence"
        ).fetchone()
        assert (count, lo, hi) == (2, "2026-08-14", "2026-08-21")
        assert bak.execute("SELECT note FROM unrelated").fetchone() == ("keep-me",)
        assert bak.execute("PRAGMA integrity_check").fetchone() == ("ok",)
    finally:
        bak.close()


def test_backup_is_idempotent_for_today(tmp_path: Path) -> None:
    src = tmp_path / "workbench.sqlite"
    dest = tmp_path / "backups"
    _make_db(src)
    now = datetime(2026, 8, 26, 6, 0, tzinfo=UTC)
    first = run_sqlite_backup(db_path=src, backup_dir=dest, today_utc=now)
    src_conn = sqlite3.connect(str(src))
    src_conn.execute(
        "INSERT INTO opportunity_occurrence (symbol, candidate_date, family) VALUES ('ZZZ','2026-08-22','GAP')"
    )
    src_conn.commit()
    src_conn.close()
    second = run_sqlite_backup(db_path=src, backup_dir=dest, today_utc=now)
    assert first["skipped"] is False
    assert second["skipped"] is True
    bak = sqlite3.connect(second["path"])
    try:
        assert bak.execute("SELECT COUNT(*) FROM opportunity_occurrence").fetchone() == (2,)
    finally:
        bak.close()


def test_backup_prunes_past_retention(tmp_path: Path) -> None:
    src = tmp_path / "workbench.sqlite"
    dest = tmp_path / "backups"
    dest.mkdir()
    _make_db(src)
    stale = dest / "workbench-2026-07-01.sqlite"
    stale.write_bytes(b"stale")
    old_mtime = (datetime.now(UTC) - timedelta(days=40)).timestamp()
    os.utime(stale, (old_mtime, old_mtime))
    now = datetime(2026, 8, 26, 6, 0, tzinfo=UTC)
    result = run_sqlite_backup(db_path=src, backup_dir=dest, today_utc=now, retention_days=30)
    assert result["pruned"] == 1
    assert not stale.exists()
    assert (dest / "workbench-2026-08-26.sqlite").is_file()


def test_missing_db_raises(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        run_sqlite_backup(db_path=tmp_path / "missing.sqlite", backup_dir=tmp_path / "b")
