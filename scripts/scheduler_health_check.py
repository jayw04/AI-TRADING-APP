#!/usr/bin/env python
"""Scheduler heartbeat health check (ADR 0032).

Reads the `scheduler_heartbeat` table directly (stdlib sqlite3 — no app imports, so it runs
anywhere) and verifies the single-active-scheduler invariant:

  exit 0  — exactly one armed host with a FRESH beat (healthy)
  exit 1  — no fresh armed beat (the scheduler is down / nothing armed)  -> alarm
  exit 2  — MORE THAN ONE armed host with a fresh beat (double-arm!)     -> incident
  exit 3  — table missing / DB unreadable

Backs the CloudWatch missed-scheduler alarm and the cutover verification step.

Usage:
  scheduler_health_check.py [--db PATH] [--max-age-seconds N]
DB path resolution: --db, else WORKBENCH_DB_URL (sqlite path), else data/workbench.sqlite.
"""

from __future__ import annotations

import argparse
import os
import sqlite3
import sys
from datetime import UTC, datetime


def _resolve_db_path(arg: str | None) -> str:
    if arg:
        return arg
    url = os.environ.get("WORKBENCH_DB_URL", "")
    # sqlite+aiosqlite:////app/data/workbench.sqlite  or  sqlite+aiosqlite:///./data/workbench.sqlite
    if "sqlite" in url and ":///" in url:
        path = url.split(":///", 1)[1]
        return path or "data/workbench.sqlite"
    return "data/workbench.sqlite"


def _parse_ts(value: str) -> datetime | None:
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return dt if dt.tzinfo else dt.replace(tzinfo=UTC)
    except (ValueError, AttributeError):
        return None


def main() -> int:
    ap = argparse.ArgumentParser(description="Scheduler heartbeat health check (ADR 0032)")
    ap.add_argument("--db", default=None)
    ap.add_argument("--max-age-seconds", type=int, default=180,
                    help="A beat older than this is stale (default 180; scheduler beats every 30s).")
    args = ap.parse_args()

    db_path = _resolve_db_path(args.db)
    if not os.path.exists(db_path):
        print(f"FAIL(3): db not found at {db_path}", file=sys.stderr)
        return 3

    try:
        conn = sqlite3.connect(db_path)
        rows = conn.execute(
            "SELECT host_id, armed, last_beat_at FROM scheduler_heartbeat"
        ).fetchall()
        conn.close()
    except sqlite3.Error as exc:
        print(f"FAIL(3): {exc}", file=sys.stderr)
        return 3

    now = datetime.now(UTC)
    fresh_armed = []
    for host_id, armed, last_beat_at in rows:
        ts = _parse_ts(str(last_beat_at))
        age = (now - ts).total_seconds() if ts else None
        if armed and age is not None and age <= args.max_age_seconds:
            fresh_armed.append((host_id, age))

    if len(fresh_armed) == 1:
        host_id, age = fresh_armed[0]
        print(f"OK: single armed host '{host_id}' (beat {age:.0f}s ago)")
        return 0
    if len(fresh_armed) == 0:
        print("FAIL(1): no fresh armed scheduler heartbeat — scheduler down or nothing armed",
              file=sys.stderr)
        return 1
    hosts = ", ".join(h for h, _ in fresh_armed)
    print(f"FAIL(2): DOUBLE-ARM — multiple armed hosts beating: {hosts}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
