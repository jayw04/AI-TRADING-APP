"""Phase 0A — migrate the ``corporate_events`` store to the EAD schema (ADR 0037 Decision 8).

Idempotent + reversible. Adds the eleven EAD governance/identity/audit columns, (re)creates the
``corporate_events_pit`` compatibility view, and backfills the historical **Form-4** rows
(``available_time = filed_at``; ``research_eligible = TRUE`` where a security is resolved).

**Safety (ADR 0037 — separately-signed-off migration):**
  * A timestamped file copy is taken *before* the connection opens; that copy is the down-path.
  * The backfill only ever *adds* ``available_time``/``research_eligible`` to insider rows; it
    touches no column the legacy ``events_asof`` (INSIDER-001) read path projects, so the
    reproduction is invariant by construction. Verify with a pre/post reproduction diff
    (``scripts/run_insider_reproduction.py``) against the printed backup before trusting a run.

Offline research artifact (DuckDB), never the trading DB. Usage (from apps/backend):
    python scripts/migrate_event_store_ead.py                       # default event_store_path
    python scripts/migrate_event_store_ead.py --events-db data/events.duckdb
    python scripts/migrate_event_store_ead.py --dry-run             # report only, no writes
"""

from __future__ import annotations

import argparse
import shutil
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import duckdb

from app.altdata.events.store import EAD_COLUMN_DDL, EventStore, ensure_ead_schema
from app.config import get_settings


def _existing_columns(con: duckdb.DuckDBPyConnection) -> set[str]:
    rows = con.execute(
        "SELECT column_name FROM information_schema.columns WHERE table_name = 'corporate_events'"
    ).fetchall()
    return {r[0] for r in rows}


def _table_exists(con: duckdb.DuckDBPyConnection) -> bool:
    row = con.execute(
        "SELECT COUNT(*) FROM information_schema.tables WHERE table_name = 'corporate_events'"
    ).fetchone()
    return bool(row and row[0])


def _count(con: duckdb.DuckDBPyConnection, where: str = "") -> int:
    sql = "SELECT COUNT(*) FROM corporate_events" + (f" WHERE {where}" if where else "")
    row = con.execute(sql).fetchone()
    return int(row[0]) if row else 0


def backfill_insider(con: duckdb.DuckDBPyConnection) -> dict[str, int]:
    """Backfill historical Form-4 rows (Phase 0A §4.2). ``available_time = filed_at`` (the
    characterized proxy); ``research_eligible = TRUE`` only where a security is resolved
    (``ticker IS NOT NULL``). Every other row keeps the ``research_eligible = FALSE`` default."""
    eligible_before = _count(con, "research_eligible = TRUE")
    con.execute(
        "UPDATE corporate_events SET available_time = filed_at "
        "WHERE event_type = 'insider_buy' AND available_time IS NULL"
    )
    con.execute(
        "UPDATE corporate_events SET research_eligible = TRUE "
        "WHERE event_type = 'insider_buy' AND available_time IS NOT NULL AND ticker IS NOT NULL"
    )
    return {
        "insider_rows": _count(con, "event_type = 'insider_buy'"),
        "available_time_populated": _count(
            con, "event_type = 'insider_buy' AND available_time IS NOT NULL"),
        "eligible_before": eligible_before,
        "eligible_after": _count(con, "research_eligible = TRUE"),
    }


def migrate_event_store(
    db_path: str | Path, *, backup: bool = True, backfill: bool = True, dry_run: bool = False,
) -> dict[str, Any]:
    """Apply the EAD migration to ``db_path``. Returns a report dict (backup path, columns added,
    row counts). ``dry_run`` reports what *would* change without writing."""
    path = Path(db_path)
    report: dict[str, Any] = {"db_path": str(path), "dry_run": dry_run, "backup_path": None,
                              "fresh_create": False, "columns_added": [], "backfill": None}

    if not path.exists():
        # Fresh DB: EventStore init lays down the full schema + view; nothing to migrate/backfill.
        if not dry_run:
            EventStore(str(path)).close()
        report["fresh_create"] = True
        return report

    if backup and not dry_run:
        ts = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
        bak = path.with_suffix(path.suffix + f".pre-ead-{ts}.bak")
        shutil.copy2(path, bak)
        report["backup_path"] = str(bak)

    con = duckdb.connect(str(path), read_only=dry_run)
    closed = False
    try:
        if not _table_exists(con):
            # File exists but no table yet — treat as fresh once writable.
            con.close()
            closed = True
            if not dry_run:
                EventStore(str(path)).close()
            report["fresh_create"] = True
            return report

        if dry_run:
            present = _existing_columns(con)
            report["columns_added"] = [n for n, _ in EAD_COLUMN_DDL if n not in present]  # would-add
            report["backfill"] = {
                "insider_rows": _count(con, "event_type = 'insider_buy'"),
                "eligible_before": _count(con, "research_eligible = TRUE")
                if "research_eligible" in present else 0,
            }
            return report

        report["columns_added"] = ensure_ead_schema(con)  # adds missing columns + (re)creates view
        if backfill:
            report["backfill"] = backfill_insider(con)
    finally:
        if not closed:
            con.close()
    return report


def _main() -> None:
    ap = argparse.ArgumentParser(description="Migrate the corporate_events store to the EAD schema.")
    ap.add_argument("--events-db", default=None,
                    help="path to the event store (default: settings.event_store_path)")
    ap.add_argument("--no-backup", action="store_true", help="skip the pre-migration file copy")
    ap.add_argument("--no-backfill", action="store_true", help="add columns/view but skip the backfill")
    ap.add_argument("--dry-run", action="store_true", help="report only; make no changes")
    args = ap.parse_args()

    db_path = args.events_db or get_settings().event_store_path
    report = migrate_event_store(
        db_path, backup=not args.no_backup, backfill=not args.no_backfill, dry_run=args.dry_run,
    )

    print(f"event store : {report['db_path']}")
    print(f"dry-run     : {report['dry_run']}")
    if report["fresh_create"]:
        print("fresh-create: schema + view laid down (no migration/backfill needed)")
        return
    print(f"backup      : {report['backup_path'] or '(skipped)'}")
    print(f"cols {'to add' if report['dry_run'] else 'added'} : {report['columns_added'] or '(none)'}")
    if report["backfill"] is not None:
        bf = report["backfill"]
        print("backfill    :")
        for k, v in bf.items():
            print(f"  {k:24s}: {v}")
    if not report["dry_run"]:
        print("\nNEXT: verify INSIDER-001 invariance - run scripts/run_insider_reproduction.py "
              "against the backup and the migrated store; the outputs must be identical.")


if __name__ == "__main__":
    _main()
