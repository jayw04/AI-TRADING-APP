#!/bin/bash
# Manual restore from a backup (P5 §8.5).
#
# Usage: ./scripts/restore_db.sh <backup-path>
#
# DESTRUCTIVE — overwrites the live DB. The backend MUST be stopped first; the
# script refuses to run if /healthz is reachable. The current DB is snapshotted
# to <db>.pre-restore-<epoch> before the overwrite.

set -e

BACKUP="$1"
DB_PATH="${WORKBENCH_DB_PATH:-/app/data/workbench.sqlite}"
HEALTHZ_URL="${WORKBENCH_HEALTHZ_URL:-http://127.0.0.1:8000/healthz}"

if [ -z "$BACKUP" ]; then
    echo "Usage: $0 <backup-path>" >&2
    exit 1
fi
if [ ! -f "$BACKUP" ]; then
    echo "ERROR: backup not found at $BACKUP" >&2
    exit 1
fi

# Refuse to proceed while the backend is up (a live writer would race us).
if curl -s --max-time 2 "$HEALTHZ_URL" >/dev/null 2>&1; then
    echo "ERROR: backend is reachable at ${HEALTHZ_URL}." >&2
    echo "Stop it first: docker compose stop backend" >&2
    exit 1
fi

echo "About to restore ${BACKUP} -> ${DB_PATH}"
echo "Current DB will be snapshotted to ${DB_PATH}.pre-restore-<epoch>"
read -r -p "Continue? [y/N] " yn
case "$yn" in
    [Yy]*) ;;
    *) echo "Aborted"; exit 0 ;;
esac

if [ -f "$DB_PATH" ]; then
    cp "$DB_PATH" "${DB_PATH}.pre-restore-$(date -u +%s)"
fi

# .backup works as a consistent copy in either direction.
sqlite3 "$BACKUP" ".backup '${DB_PATH}'"

if ! sqlite3 "$DB_PATH" "PRAGMA integrity_check;" | head -1 | grep -q "^ok$"; then
    echo "ERROR: restored DB failed integrity check" >&2
    exit 1
fi

# Confirm the audit hash chain survived the restore.
echo "audit_log rows: $(sqlite3 "$DB_PATH" "SELECT count(*) FROM audit_log;")"
python scripts/verify_audit_integrity.py "$DB_PATH" || \
  echo "WARNING: audit integrity check reported errors — investigate before trusting." >&2

echo "Restore complete. Start backend with: docker compose up -d backend"
