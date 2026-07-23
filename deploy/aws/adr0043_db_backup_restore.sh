#!/usr/bin/env bash
# ADR-0043 validation-box DATABASE backup + whole-file restore (the recovery boundary for the
# reviewed-superset migration a4c7e1b93d20).
#
# WHY WHOLE-FILE RESTORE, NOT `alembic downgrade`
# Deploying b0058bf and starting the backend runs `alembic upgrade head`, applying a4c7e1b93d20
# (an additive NULLABLE column on risk_reservations). Once applied, the DB is stamped at that
# revision. The currently-deployed code 80a6c043 does NOT contain that revision in its alembic
# script directory, so a code-only rollback to 80a6c043 fails at startup — its `alembic upgrade head`
# cannot locate revision a4c7e1b93d20 and the backend never boots. Recovery therefore requires
# restoring the PRE-migration database file (stamped at e7b3f2a9c4d1), which 80a6c043 boots against
# cleanly. For SQLite a verified whole-file restoration is the clean, revision-safe boundary.
#
# BACKEND MUST BE STOPPED (authoritative precondition).
# Backup and restore require the backend CONTAINER to be stopped and the scheduler/Alpaca startup
# disabled. Container-stop proof is authoritative; this script cannot verify it. The `BEGIN IMMEDIATE`
# writer probe (_assert_no_writer) is only a SECONDARY race detector — it proves no writer holds the
# lock at that instant, NOT that the backend is stopped (an idle backend connection could pass and
# then write). The on-box runbook records the container as stopped before invoking this script.
#
# WAL/SHM HANDLING
# The DB runs in WAL mode. `backup` checkpoints the WAL into the main file (TRUNCATE) then copies it,
# archiving any residual -wal/-shm, and records sha256 + bytes + integrity_check + alembic revision
# in a sidecar .meta.json. `restore` validates the backup against that recorded metadata, STAGES a
# verified copy on the same filesystem, and only then ATOMICALLY renames it over the live DB — so a
# failed restore never destroys the live database.
set -uo pipefail
PYTHON="${PYTHON:-python3}"
fatal() { echo "FATAL: $*" >&2; exit 1; }
command -v "$PYTHON" >/dev/null || fatal "python3 is required."
command -v realpath >/dev/null || fatal "realpath is required for path-safety checks."
EXPECTED_PREMIGRATION_REV="${ADR0043_EXPECTED_PREMIGRATION_REV:-e7b3f2a9c4d1}"

_integrity_check() {  # $1 = db path ; prints ok / detail ; exit 3 if not ok
  "$PYTHON" - "$1" <<'PY'
import sqlite3, sys
con = sqlite3.connect(f"file:{sys.argv[1]}?mode=ro", uri=True)
try:
    r = con.execute("PRAGMA integrity_check").fetchone()[0]
finally:
    con.close()
print(r); sys.exit(0 if r == "ok" else 3)
PY
}

_current_rev() {  # $1 = db path ; prints alembic_version.version_num or NONE/NO_ALEMBIC_TABLE
  "$PYTHON" - "$1" <<'PY'
import sqlite3, sys
con = sqlite3.connect(f"file:{sys.argv[1]}?mode=ro", uri=True)
try:
    try:
        row = con.execute("SELECT version_num FROM alembic_version").fetchone()
        print(row[0] if row else "NONE")
    except sqlite3.OperationalError:
        print("NO_ALEMBIC_TABLE")
finally:
    con.close()
PY
}

_assert_no_writer() {  # SECONDARY race detector only (NOT proof the backend is stopped)
  "$PYTHON" - "$1" <<'PY'
import sqlite3, sys
con = sqlite3.connect(sys.argv[1], timeout=0.5)
try:
    con.execute("BEGIN IMMEDIATE"); con.rollback()
except sqlite3.OperationalError as e:
    print(f"LOCKED: {e}", file=sys.stderr); sys.exit(5)
finally:
    con.close()
PY
}

_checkpoint_truncate() { "$PYTHON" - "$1" <<'PY'
import sqlite3, sys
con = sqlite3.connect(sys.argv[1])
try: con.execute("PRAGMA wal_checkpoint(TRUNCATE)")
finally: con.close()
PY
}

_sha() { "$PYTHON" - "$1" <<'PY'
import hashlib, sys
h = hashlib.sha256()
with open(sys.argv[1], "rb") as f:
    for b in iter(lambda: f.read(1 << 20), b""): h.update(b)
print(h.hexdigest())
PY
}

_fsync() { "$PYTHON" - "$1" <<'PY'
import os, sys
if os.environ.get("ADR0043_TEST_FAIL_FSYNC"):     # test-only fault injection
    print("forced fsync failure", file=sys.stderr); sys.exit(1)
try:
    fd = os.open(sys.argv[1], os.O_RDONLY)
    try: os.fsync(fd)
    finally: os.close(fd)
except OSError as e:
    print(e, file=sys.stderr); sys.exit(1)
PY
}

_fsync_dir() { "$PYTHON" - "$1" <<'PY'
import os, sys
if os.environ.get("ADR0043_TEST_FAIL_FSYNC_DIR"):  # test-only fault injection
    print("forced dir fsync failure", file=sys.stderr); sys.exit(1)
try:
    fd = os.open(sys.argv[1], os.O_RDONLY)          # a directory fd
    try: os.fsync(fd)
    finally: os.close(fd)
except OSError as e:
    print(e, file=sys.stderr); sys.exit(1)
PY
}

_meta_get() { "$PYTHON" - "$1" "$2" <<'PY'
import json, sys
try:
    print(json.load(open(sys.argv[1])).get(sys.argv[2], ""))
except Exception:
    print("")
PY
}

# --------------------------------------------------------------------- backup
cmd_backup() {  # <db_path> <backup_dir_OUTSIDE_app>
  local db="$1" dir="$2"
  [ -f "$db" ] || fatal "database not found: $db"

  # backup location MUST be outside the app tree AND outside the live DB directory — enforced with
  # canonical paths so `..` traversal and symlinks cannot smuggle the only backup into a directory
  # the deployment swap/cleanup can delete.
  local db_real db_dir_real dir_real app_real
  db_real="$(realpath "$db")"; db_dir_real="$(dirname "$db_real")"
  dir_real="$(realpath -m "$dir")"
  app_real="$(realpath -m "${WORKBENCH_APP_TREE:-/opt/workbench/app}")"
  case "$dir_real/" in
    "$app_real/"*)    fatal "backup directory ($dir_real) is under the application tree ($app_real) — a deploy swap could delete the only backup." ;;
    "$db_dir_real/"*) fatal "backup directory ($dir_real) is under the live database directory ($db_dir_real)." ;;
  esac
  mkdir -p "$dir_real" || fatal "cannot create backup dir: $dir_real"

  echo "--- secondary race check (authoritative precondition is: backend container stopped) ---"
  _assert_no_writer "$db" || fatal "database has an active writer — STOP THE BACKEND CONTAINER before backup (this probe is only a race detector)."
  # The live DB must already be at the approved pre-migration revision — refuse now rather than
  # produce a backup that could never qualify for authorized recovery.
  local rev; rev="$(_current_rev "$db")"; echo "  current_alembic_revision=$rev"
  [ "$rev" = "$EXPECTED_PREMIGRATION_REV" ] || \
    fatal "live DB revision '$rev' is not the approved pre-migration revision '$EXPECTED_PREMIGRATION_REV' — refusing to back up a non-approvable state."

  echo "--- checkpoint WAL -> main file (TRUNCATE) ---"; _checkpoint_truncate "$db"
  # After a TRUNCATE checkpoint (backend stopped) the WAL must be empty, so the main file alone is a
  # self-contained snapshot. A nonempty WAL means committed data lives outside the main file (e.g. a
  # reader pinned it) — refuse, because the backup identity covers the main file ONLY. -shm is
  # transient coordination state and is never part of the recovery artifact.
  [ ! -s "${db}-wal" ] || fatal "nonempty WAL remains after TRUNCATE checkpoint — cannot produce a self-contained main-file backup (is a reader holding a snapshot?)."
  rm -f "${db}-wal" "${db}-shm"

  local base ts out; base="$(basename "$db")"; ts="$(date -u +%Y%m%dT%H%M%SZ)"
  out="$dir_real/${base}.${ts}.bak"
  cp -f "$db" "$out"      # main file only — no -wal/-shm sidecars in the recovery package
  echo "--- verifying backup copy (integrity_check + sha256) ---"
  local ic; ic="$(_integrity_check "$out")" || fatal "backup failed integrity_check: $ic"
  local sha bytes; sha="$(_sha "$out")"; bytes="$(wc -c < "$out")"
  # opening the WAL-mode copy for integrity_check makes SQLite create a -shm (and maybe -wal) beside
  # it. Remove them so the recovery package is the main file + metadata ONLY (no sidecars).
  rm -f "$out-wal" "$out-shm"
  cat > "$out.meta.json" <<META
{ "source_db": "$db_real", "backup": "$out", "backup_basename": "$(basename "$out")",
  "sha256": "$sha", "bytes": $bytes, "alembic_revision_at_backup": "$rev",
  "integrity_check": "$ic", "created_utc": "$ts" }
META
  echo "=== BACKUP_OK ==="
  printf '  %-13s: %s\n' backup "$out" sha256 "$sha" bytes "$bytes" alembic_rev "$rev" \
         integrity "$ic" meta "$out.meta.json"
}

# --------------------------------------------------------------------- restore (stage -> verify -> atomic)
cmd_restore() {  # <backup_file> <db_path>
  local bak="$1" db="$2" meta="$1.meta.json"
  [ -f "$bak" ]  || fatal "backup file not found: $bak"
  [ -f "$meta" ] || fatal "backup metadata not found: $meta — refusing to restore an unrecorded file."

  # 1) validate the RECORDED metadata (approval + self-consistency), not just a post-hoc recompute
  local rec_sha rec_bytes rec_ic rec_rev rec_base
  rec_sha="$(_meta_get "$meta" sha256)"; rec_bytes="$(_meta_get "$meta" bytes)"
  rec_ic="$(_meta_get "$meta" integrity_check)"; rec_rev="$(_meta_get "$meta" alembic_revision_at_backup)"
  rec_base="$(_meta_get "$meta" backup_basename)"
  [ -n "$rec_sha" ] || fatal "metadata missing sha256."
  [ "$rec_ic" = "ok" ] || fatal "recorded integrity_check is '$rec_ic', not ok."
  [ "$rec_rev" = "$EXPECTED_PREMIGRATION_REV" ] || \
    fatal "recorded alembic revision '$rec_rev' != approved pre-migration '$EXPECTED_PREMIGRATION_REV'."
  [ -z "$rec_base" ] || [ "$rec_base" = "$(basename "$bak")" ] || \
    fatal "metadata backup_basename '$rec_base' != actual '$(basename "$bak")'."

  # 2) the backup FILE must match the recorded identity, and pass its own integrity_check
  local act_sha act_bytes ic
  act_sha="$(_sha "$bak")"; act_bytes="$(wc -c < "$bak")"
  [ "$act_sha" = "$rec_sha" ]     || fatal "backup sha256 ($act_sha) != recorded ($rec_sha)."
  [ "$act_bytes" = "$rec_bytes" ] || fatal "backup byte size ($act_bytes) != recorded ($rec_bytes)."
  ic="$(_integrity_check "$bak")" || fatal "backup fails integrity_check ($ic) — refusing."

  if [ -f "$db" ]; then
    echo "--- secondary race check on the live DB (authoritative: backend container stopped) ---"
    _assert_no_writer "$db" || fatal "live database has an active writer — STOP THE BACKEND CONTAINER before restore."
  fi

  # 3) STAGE a verified copy on the SAME filesystem — the live DB is NOT touched until this passes
  local stg="${db}.restore.$$.tmp"
  rm -f "$stg"
  cp -f "$bak" "$stg" || { rm -f "$stg"; fatal "staged copy failed — live DB left untouched."; }
  local stg_sha; stg_sha="$(_sha "$stg")"
  [ "$stg_sha" = "$rec_sha" ] || { rm -f "$stg"; fatal "staged copy sha256 ($stg_sha) != recorded ($rec_sha) — live DB left untouched."; }
  _integrity_check "$stg" >/dev/null || { rm -f "$stg"; fatal "staged copy failed integrity_check — live DB left untouched."; }
  # fsync is FAIL-CLOSED: if the staged bytes are not durably persisted, do not proceed to rename.
  _fsync "$stg" || { rm -f "$stg"; fatal "fsync of staged database failed — live DB left untouched."; }

  # 4) ATOMIC replace (same-fs rename), then clear stale WAL/SHM. NO sidecars are installed — the
  # backup identity is the main file alone; installing a WAL/SHM could change the effective DB while
  # the main-file sha still matched the approved metadata.
  mv -f "$stg" "$db" || { rm -f "$stg"; fatal "atomic rename failed — live DB left untouched."; }
  rm -f "${db}-wal" "${db}-shm"

  # 5) final content verification against the RECORDED identity (the DB is already replaced)
  local fin_sha fin_ic fin_rev
  fin_sha="$(_sha "$db")"; fin_ic="$(_integrity_check "$db")" || fatal "restored DB failed integrity_check: $fin_ic"
  fin_rev="$(_current_rev "$db")"
  [ "$fin_sha" = "$rec_sha" ] || fatal "restored DB sha256 ($fin_sha) != recorded ($rec_sha)."
  [ "$fin_rev" = "$EXPECTED_PREMIGRATION_REV" ] || fatal "restored DB revision ($fin_rev) != approved ($EXPECTED_PREMIGRATION_REV)."

  # 6) durability of the directory entry replacement. This runs AFTER the atomic rename, so a failure
  # here means the content is correct but the rename's persistence is unconfirmed — report a DISTINCT
  # recovery-verification failure (exit 6), never RESTORE_OK.
  if ! _fsync_dir "$(dirname "$db")"; then
    echo "RESTORE_INCOMPLETE_DIRSYNC: DB content restored + verified (sha=$fin_sha rev=$fin_rev), but the directory fsync after the atomic rename failed — confirm the rename is persisted before proceeding." >&2
    exit 6
  fi
  echo "=== RESTORE_OK ==="
  printf '  %-13s: %s\n' restored_db "$db" sha256 "$fin_sha" alembic_rev "$fin_rev" integrity "$fin_ic"
}

usage() { echo "usage: $0 backup <db_path> <backup_dir> | restore <backup_file> <db_path>" >&2; exit 2; }
case "${1:-}" in
  backup)  shift; [ $# -eq 2 ] || usage; cmd_backup "$@" ;;
  restore) shift; [ $# -eq 2 ] || usage; cmd_restore "$@" ;;
  *) usage ;;
esac
