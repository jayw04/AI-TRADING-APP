#!/bin/bash
# Daily SQLite backup (P5 §8.5).
#
# Uses SQLite's `.backup` command — atomic and WAL-aware, so it produces a
# consistent snapshot regardless of in-flight transactions (a plain `cp` of a
# WAL database can capture a torn state).
#
# Output:    data/backups/workbench-YYYY-MM-DD.sqlite
# Retention: WORKBENCH_BACKUP_RETENTION_DAYS (default 30); older files pruned.
#
# Run on a schedule (the lifespan registers a 02:00 cron job) or by hand.

set -e

DB_PATH="${WORKBENCH_DB_PATH:-/app/data/workbench.sqlite}"
BACKUP_DIR="${WORKBENCH_BACKUP_DIR:-/app/data/backups}"
RETENTION_DAYS="${WORKBENCH_BACKUP_RETENTION_DAYS:-30}"

mkdir -p "$BACKUP_DIR"

TODAY=$(date -u +%Y-%m-%d)
TARGET="${BACKUP_DIR}/workbench-${TODAY}.sqlite"

if [ -f "$TARGET" ]; then
    echo "Backup for ${TODAY} already exists at ${TARGET} — skipping"
    exit 0
fi

# Atomic snapshot via .backup (works whether or not WAL is enabled).
sqlite3 "$DB_PATH" ".backup '${TARGET}'"

# Verify the snapshot is a readable, intact database before trusting it.
if ! sqlite3 "$TARGET" "PRAGMA integrity_check;" | head -1 | grep -q "^ok$"; then
    echo "ERROR: backup integrity check failed for ${TARGET}" >&2
    rm -f "$TARGET"
    exit 1
fi

# Prune snapshots older than the retention window (best-effort; mtime-based).
find "$BACKUP_DIR" -name "workbench-*.sqlite" -type f -mtime "+${RETENTION_DAYS}" -delete 2>/dev/null || true

SIZE=$(stat -c%s "$TARGET" 2>/dev/null || stat -f%z "$TARGET" 2>/dev/null || echo "?")
echo "Backup complete: ${TARGET} (${SIZE} bytes)"
exit 0
