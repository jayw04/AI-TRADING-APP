#!/usr/bin/env bash
# Hermetic test of the ADR-0043 DB backup/restore recovery boundary on a SYNTHETIC WAL-mode SQLite
# database (never the box). Covers the recovery scenario end-to-end plus the two hardening fixes:
# backup-location enforcement (canonical paths, traversal, symlink) and stage-then-atomic restore
# that never destroys the live DB, validated against recorded metadata.
set -uo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
TOOL="$HERE/../adr0043_db_backup_restore.sh"
PY="${PYTHON:-python3}"
PASS=0; FAIL=0
ok(){ echo "  PASS: $1"; PASS=$((PASS+1)); }
bad(){ echo "  FAIL: $1"; FAIL=$((FAIL+1)); }
check(){ if eval "$2"; then ok "$1"; else bad "$1 [cond: $2]"; fi; }
sha_of(){ "$PY" - "$1" <<'PY'
import hashlib,sys;print(hashlib.sha256(open(sys.argv[1],'rb').read()).hexdigest())
PY
}
rev_of(){ "$PY" - "$1" <<'PY'
import sqlite3,sys;con=sqlite3.connect(f"file:{sys.argv[1]}?mode=ro",uri=True);print(con.execute("SELECT version_num FROM alembic_version").fetchone()[0])
PY
}
mk_premigration(){ "$PY" - "$1" <<'PY'
import sqlite3, sys
con = sqlite3.connect(sys.argv[1]); con.execute("PRAGMA journal_mode=WAL")
con.execute("CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL)")
con.execute("INSERT INTO alembic_version VALUES ('e7b3f2a9c4d1')")
con.execute("CREATE TABLE risk_reservations (id INTEGER PRIMARY KEY, symbol TEXT, qty NUMERIC)")
con.execute("INSERT INTO risk_reservations (symbol, qty) VALUES ('MSFT', 19)"); con.commit()
con.execute("INSERT INTO risk_reservations (symbol, qty) VALUES ('F', 5)"); con.commit()  # left in WAL
con.close()
PY
}
apply_migration(){ "$PY" - "$1" <<'PY'
import sqlite3, sys
con = sqlite3.connect(sys.argv[1])
con.execute("ALTER TABLE risk_reservations ADD COLUMN position_qty_at_reservation NUMERIC(20,8)")
con.execute("UPDATE alembic_version SET version_num='a4c7e1b93d20'")
con.execute("INSERT INTO risk_reservations (symbol, qty, position_qty_at_reservation) VALUES ('AAPL',3,100)")
con.commit(); con.close()
PY
}

echo "== ADR-0043 DB backup/restore recovery test =="

# ============================================================ (1) backup-location enforcement
WORK=$(mktemp -d); APP="$WORK/opt/workbench/app"; DBDIR="$WORK/opt/workbench/data"
mkdir -p "$APP" "$DBDIR"; DB="$DBDIR/workbench.sqlite"; mk_premigration "$DB"
export WORKBENCH_APP_TREE="$APP"
run_backup(){ bash "$TOOL" backup "$DB" "$1" >"$2" 2>&1; }
L=$(mktemp); run_backup "$APP/backups" "$L"; check "backup UNDER app tree refused"        "[ $? -ne 0 ] && grep -q 'application tree' '$L'"
L=$(mktemp); run_backup "$DBDIR" "$L";        check "backup INTO the db directory refused"  "[ $? -ne 0 ] && grep -q 'live database directory' '$L'"
L=$(mktemp); run_backup "$DBDIR/sub" "$L";     check "backup nested under db dir refused"     "[ $? -ne 0 ] && grep -q 'live database directory' '$L'"
L=$(mktemp); run_backup "$DBDIR/../app/b" "$L";check ".. traversal into app tree refused"     "[ $? -ne 0 ] && grep -q 'application tree' '$L'"
ln -s "$APP" "$WORK/applink"
L=$(mktemp); run_backup "$WORK/applink/b" "$L";check "symlink into app tree refused"          "[ $? -ne 0 ] && grep -q 'application tree' '$L'"
# a legitimate OUTSIDE dir is accepted
BK="$WORK/backups-outside"; L=$(mktemp); run_backup "$BK" "$L"; rc=$?
check "backup OUTSIDE app+db dirs succeeds"    "[ $rc -eq 0 ] && grep -q BACKUP_OK '$L'"
BAK=$(ls "$BK"/workbench.sqlite.*.bak | head -1); META="$BAK.meta.json"
check "  ... backup + metadata written"        "[ -f '$BAK' ] && [ -f '$META' ]"
check "  ... recovery package has NO -wal/-shm sidecars" "[ -z \"\$(ls $BK/*.bak-wal $BK/*.bak-shm 2>/dev/null)\" ]"
PRE_SHA=$(sha_of "$BAK")

# ============================================================ (2) happy-path stage->atomic restore
apply_migration "$DB"
check "migration simulated (rev a4c7e1b93d20)" "[ \"$(rev_of "$DB")\" = a4c7e1b93d20 ]"
L=$(mktemp); bash "$TOOL" restore "$BAK" "$DB" >"$L" 2>&1; rc=$?
check "restore succeeds (RESTORE_OK)"          "[ $rc -eq 0 ] && grep -q RESTORE_OK '$L'"
check "  ... revision reverted to e7b3f2a9c4d1" "[ \"$(rev_of "$DB")\" = e7b3f2a9c4d1 ]"
check "  ... final DB byte-identical to backup (approved SHA)" "[ \"$(sha_of "$DB")\" = '$PRE_SHA' ]"
COL_GONE=$("$PY" - "$DB" <<'PY'
import sqlite3,sys;con=sqlite3.connect(sys.argv[1]);print(not any(r[1]=='position_qty_at_reservation' for r in con.execute("PRAGMA table_info(risk_reservations)")))
PY
)
check "  ... migration column gone"            "[ '$COL_GONE' = True ]"
check "  ... no live -wal/-shm after restore"  "[ ! -f '${DB}-wal' ] && [ ! -f '${DB}-shm' ]"

# ============================================================ (3) metadata validation refusals
# Each doctored backup carries a CORRECT backup_basename (so the legitimate name check passes) and a
# single wrong field; each must refuse and leave the live DB byte-identical.
REAL_BYTES=$(wc -c < "$BAK")
mkmeta(){ # <basename> <sha> <bytes> <ic> <rev> > stdout
  printf '{ "backup_basename":"%s","sha256":"%s","bytes":%s,"integrity_check":"%s","alembic_revision_at_backup":"%s" }\n' "$1" "$2" "$3" "$4" "$5"
}
LIVE0=$(sha_of "$DB")   # live DB state before the refusal cases
# missing metadata
cp "$BAK" "$WORK/nometa.bak"
L=$(mktemp); bash "$TOOL" restore "$WORK/nometa.bak" "$DB" >"$L" 2>&1; check "missing metadata refused" "[ $? -ne 0 ] && grep -q 'metadata not found' '$L'"
# metadata SHA mismatch
cp "$BAK" "$WORK/badsha.bak"; mkmeta "badsha.bak" "$(printf '0%.0s' {1..64})" "$REAL_BYTES" ok e7b3f2a9c4d1 > "$WORK/badsha.bak.meta.json"
L=$(mktemp); bash "$TOOL" restore "$WORK/badsha.bak" "$DB" >"$L" 2>&1; check "metadata SHA mismatch refused" "[ $? -ne 0 ] && grep -qi 'sha256' '$L'"
# metadata byte-size mismatch (correct sha, wrong bytes)
cp "$BAK" "$WORK/badbytes.bak"; mkmeta "badbytes.bak" "$PRE_SHA" 999999 ok e7b3f2a9c4d1 > "$WORK/badbytes.bak.meta.json"
L=$(mktemp); bash "$TOOL" restore "$WORK/badbytes.bak" "$DB" >"$L" 2>&1; check "metadata byte-size mismatch refused" "[ $? -ne 0 ] && grep -qi 'byte size' '$L'"
# wrong alembic revision
cp "$BAK" "$WORK/badrev.bak"; mkmeta "badrev.bak" "$PRE_SHA" "$REAL_BYTES" ok deadbeef1234 > "$WORK/badrev.bak.meta.json"
L=$(mktemp); bash "$TOOL" restore "$WORK/badrev.bak" "$DB" >"$L" 2>&1; check "wrong alembic revision refused" "[ $? -ne 0 ] && grep -qi 'pre-migration' '$L'"
check "  ... live DB byte-identical through all metadata refusals" "[ \"$(sha_of "$DB")\" = '$LIVE0' ]"

# ============================================================ (4) a corrupt backup never destroys live DB
# A corrupt file whose metadata truthfully records its (corrupt) sha/bytes + integrity_check=ok + rev.
# It passes name/sha/bytes but fails its own integrity_check — caught BEFORE any staging or replace,
# so the live DB is left byte-identical (all restore verification precedes the atomic swap).
CORRUPT="$WORK/corrupt.bak"; printf 'not a sqlite database at all' > "$CORRUPT"
cs=$(sha_of "$CORRUPT"); cb=$(wc -c < "$CORRUPT")
mkmeta "corrupt.bak" "$cs" "$cb" ok e7b3f2a9c4d1 > "$CORRUPT.meta.json"
bash "$TOOL" restore "$BAK" "$DB" >/dev/null 2>&1   # known-good live DB first
LIVE_SHA_BEFORE=$(sha_of "$DB")
L=$(mktemp); bash "$TOOL" restore "$CORRUPT" "$DB" >"$L" 2>&1; rc=$?
check "corrupt backup refused before replace"   "[ $rc -ne 0 ] && grep -qi 'integrity_check' '$L'"
check "  ... live DB byte-identical (untouched)" "[ \"$(sha_of "$DB")\" = '$LIVE_SHA_BEFORE' ]"
check "  ... no leftover .restore.*.tmp"         "! ls ${DB}.restore.*.tmp >/dev/null 2>&1"

# ============================================================ (5) fsync fail-closed
# staged-file fsync failure (injected) must refuse BEFORE rename and leave the live DB byte-identical
bash "$TOOL" restore "$BAK" "$DB" >/dev/null 2>&1; SHA_B=$(sha_of "$DB")
L=$(mktemp); ADR0043_TEST_FAIL_FSYNC=1 bash "$TOOL" restore "$BAK" "$DB" >"$L" 2>&1; rc=$?
check "staged fsync failure refuses (fail-closed)"  "[ $rc -ne 0 ] && grep -q 'fsync of staged database failed' '$L'"
check "  ... live DB byte-identical after fsync fail" "[ \"$(sha_of "$DB")\" = '$SHA_B' ]"
check "  ... no leftover .restore.*.tmp"             "! ls ${DB}.restore.*.tmp >/dev/null 2>&1"
# directory fsync failure (injected) is AFTER the atomic rename: content replaced, DISTINCT status
bash "$TOOL" restore "$BAK" "$DB" >/dev/null 2>&1; apply_migration "$DB"   # DB now at a4c7e1b93d20
L=$(mktemp); ADR0043_TEST_FAIL_FSYNC_DIR=1 bash "$TOOL" restore "$BAK" "$DB" >"$L" 2>&1; rc=$?
check "dir fsync failure -> distinct status (exit 6)" "[ $rc -eq 6 ] && grep -q RESTORE_INCOMPLETE_DIRSYNC '$L'"
check "  ... not reported as RESTORE_OK"             "! grep -q 'RESTORE_OK' '$L'"
check "  ... DB content was replaced (rev reverted)"  "[ \"$(rev_of "$DB")\" = e7b3f2a9c4d1 ]"

# ============================================================ (6) WAL/SHM discipline
# backup refuses if a nonempty WAL survives the TRUNCATE checkpoint (a reader pins the snapshot)
DBW="$DBDIR/dbw.sqlite"; mk_premigration "$DBW"
READY="$WORK/rdy"; DONE="$WORK/done"; rm -f "$READY" "$DONE"
"$PY" - "$DBW" "$READY" "$DONE" <<'PY' &
import sqlite3, sys, os, time
db, ready, done = sys.argv[1:4]
con = sqlite3.connect(db)
con.execute("BEGIN"); con.execute("SELECT count(*) FROM risk_reservations").fetchall()  # pin snapshot
open(ready, "w").close()
while not os.path.exists(done): time.sleep(0.02)
con.rollback(); con.close()
PY
RPID=$!
for _ in $(seq 1 200); do [ -f "$READY" ] && break; sleep 0.02; done
"$PY" - "$DBW" <<'PY'
import sqlite3, sys
c = sqlite3.connect(sys.argv[1])
for i in range(200): c.execute("INSERT INTO risk_reservations(symbol,qty) VALUES (?,?)", (f"X{i}", i))
c.commit(); c.close()
PY
L=$(mktemp); bash "$TOOL" backup "$DBW" "$WORK/bkw" >"$L" 2>&1; rc=$?
touch "$DONE"; wait "$RPID" 2>/dev/null
check "nonempty WAL after checkpoint refuses backup" "[ $rc -ne 0 ] && grep -q 'nonempty WAL' '$L'"

# restore removes stale live -wal/-shm and installs none
DBS="$DBDIR/dbs.sqlite"; mk_premigration "$DBS"
bash "$TOOL" backup "$DBS" "$WORK/bks" >/dev/null 2>&1
BAKS=$(ls "$WORK/bks"/dbs.sqlite.*.bak | head -1)
printf 'stale-wal' > "${DBS}-wal"; printf 'stale-shm' > "${DBS}-shm"
L=$(mktemp); bash "$TOOL" restore "$BAKS" "$DBS" >"$L" 2>&1; rc=$?
check "restore succeeds clearing stale sidecars"     "[ $rc -eq 0 ] && grep -q RESTORE_OK '$L'"
# the STALE sidecar bytes must be gone (restore rm's them + installs none). SQLite may recreate fresh
# empty coordination files when it opens the restored WAL-mode DB during verification — that is normal
# and is NOT the planted stale content.
check "  ... stale sidecar CONTENT cleared (no archived sidecars installed)" \
  "! grep -qa stale-wal '${DBS}-wal' 2>/dev/null && ! grep -qa stale-shm '${DBS}-shm' 2>/dev/null"

# ============================================================ (7) backup revision gate
DBX="$DBDIR/dbx.sqlite"; mk_premigration "$DBX"; apply_migration "$DBX"   # now at a4c7e1b93d20
L=$(mktemp); bash "$TOOL" backup "$DBX" "$WORK/bkx" >"$L" 2>&1; rc=$?
check "backup refuses non-pre-migration revision"   "[ $rc -ne 0 ] && grep -q 'not the approved pre-migration revision' '$L'"

# ============================================================ (8) active-writer refusals
"$PY" - "$DB" "$TOOL" "$BK" <<'PY'
import sqlite3, subprocess, sys
db, tool, bk = sys.argv[1], sys.argv[2], sys.argv[3]
con = sqlite3.connect(db); con.execute("BEGIN IMMEDIATE")
r = subprocess.run(["bash", tool, "backup", db, bk], capture_output=True, text=True)
con.rollback(); con.close()
sys.exit(0 if (r.returncode != 0 and "active writer" in (r.stdout + r.stderr)) else 1)
PY
check "backup refuses while a writer holds the DB" "[ $? -eq 0 ]"

echo "== DB recovery test: $PASS passed, $FAIL failed =="
[ "$FAIL" -eq 0 ]
