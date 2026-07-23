# ADR-0043 validation-box — database migration preflight + recovery plan (v1.0)

**Status:** PLAN for review. Migration execution is NOT authorized. On-box steps are marked
`PENDING BOX-ACCESS AUTHORIZATION` — no box contact has occurred.
**Deploy source:** `b0058bf335628f8dbde09a93915314f3a1f7743b` (artifact SHA-256
`5728813b…`, S3 VersionId `kex9gT31…`).
**Box:** `i-01527ac7b7c7efa35`; currently deployed executable `80a6c043`.

---

## 1. What the migration is

Deploying `b0058bf` and starting the backend runs `alembic upgrade head` (Dockerfile CMD; no compose
override — the definitive Case-B finding). The migration set `b0058bf` adds over the box's deployed
`80a6c043` is **exactly one** migration:

```
a4c7e1b93d20_reservation_position_anchor   (down_revision = e7b3f2a9c4d1)
  upgrade():   ALTER TABLE risk_reservations ADD COLUMN position_qty_at_reservation NUMERIC(20,8) NULL
  downgrade(): DROP COLUMN risk_reservations.position_qty_at_reservation
```

Additive, **nullable**, **no backfill** (ADR 0042 §D amendment). Schema-wise it is low-risk: existing
rows get NULL, and SQLAlchemy addresses columns by name, so an extra nullable column is tolerated by
model reads/writes.

## 2. The rollback hazard (why code-only rollback is insufficient)

`e7b3f2a9c4d1` — the parent revision — **is** present in `80a6c043`. `a4c7e1b93d20` is **not**.

Therefore, once `a4c7e1b93d20` is applied, the DB is stamped at `a4c7e1b93d20`, and a **code-only**
rollback to `80a6c043` **cannot start**: `80a6c043`'s startup `alembic upgrade head` reads the DB
revision `a4c7e1b93d20`, cannot locate it in its own `alembic/versions/` directory, errors
("Can't locate revision identified by 'a4c7e1b93d20'"), and the backend never boots.

**Consequence:** the provisioner's `APPLICATION_ROLLBACK_COMPLETE / DATABASE_ROLLBACK_NOT_IMPLEMENTED`
guarantee is not enough for the migration step. Recovery **requires** restoring the pre-migration
database (stamped at `e7b3f2a9c4d1`), which `80a6c043` boots against cleanly.

## 3. Recovery decision — whole-file SQLite restore

For SQLite, a **verified whole-file restoration** is the clean, revision-safe recovery boundary:

- It reverts both the schema change **and** the `alembic_version` stamp in one step, so `80a6c043`
  boots normally afterwards.
- It avoids `alembic downgrade`, whose SQLite `DROP COLUMN` behaviour is version-dependent (native
  support only on SQLite ≥ 3.35; the migration uses a direct `op.drop_column`, not batch mode).

`downgrade()` exists and is recorded here as a secondary option, but the **primary** recovery is the
whole-file restore. The DB runs in **WAL mode**, so committed data can reside in `workbench.sqlite-wal`.
Recovery must therefore handle `workbench.sqlite`, `workbench.sqlite-wal`, and `workbench.sqlite-shm`
— the tooling checkpoints the WAL into the main file (with the backend stopped) before copying, and
also archives any residual `-wal`/`-shm`.

## 4. Recovery tooling (built + tested against a synthetic DB)

`deploy/aws/adr0043_db_backup_restore.sh`:

```
backup  <db_path> <backup_dir>
  - REFUSE if the backup dir is under the app tree or under the live DB directory. Enforced with
    canonical paths (realpath), so `..` traversal and symlinks cannot smuggle the only backup into a
    directory the deploy swap/cleanup could delete. (WORKBENCH_APP_TREE overrides the app-tree path.)
  - secondary race check (see precondition below)
  - REFUSE unless the live revision is ALREADY the approved pre-migration revision (e7b3f2a9c4d1) —
    do not produce a backup that could never qualify for authorized recovery.
  - PRAGMA wal_checkpoint(TRUNCATE); then REFUSE if a nonempty WAL survives (committed data outside
    the main file, e.g. a reader pinned it). The recovery artifact is the MAIN FILE ONLY — no -wal/
    -shm sidecars are archived (SQLite's own coordination files created during verification are
    removed afterwards).
  - copy the main file to the backup dir; PRAGMA integrity_check; record sha256 + bytes + revision +
    integrity in a .meta.json.
restore <backup_file> <db_path>   # STAGE -> VERIFY -> ATOMIC; the live DB is never destroyed on failure
  - REQUIRE the sidecar .meta.json and validate the RECORDED identity: integrity=ok, alembic
    revision == the approved pre-migration revision (e7b3f2a9c4d1), backup_basename matches.
  - the backup FILE must match the recorded sha256 + bytes, and pass its own integrity_check.
  - stage a copy on the SAME filesystem; verify staged sha256 == recorded; integrity_check; and
    fsync the staged copy FAIL-CLOSED (a persistence failure refuses before rename) — live DB untouched.
  - ATOMICALLY rename the staged copy over the live DB; clear stale -wal/-shm; install NO sidecars;
    verify the FINAL live DB sha256 == recorded and revision == e7b3f2a9c4d1; then fsync the
    containing directory. A directory-fsync failure occurs AFTER the rename, so it is reported as a
    DISTINCT status (RESTORE_INCOMPLETE_DIRSYNC, exit 6), never RESTORE_OK.
  - Any failure BEFORE the rename (missing/mismatched metadata, wrong sha/bytes/revision, corrupt
    backup, staged-verify or staged-fsync failure) refuses with the live DB byte-identical.
```

**Precondition — backend container stop is authoritative.** Backup and restore require the backend
CONTAINER to be stopped and the scheduler/Alpaca startup disabled. The script's `BEGIN IMMEDIATE`
writer probe is only a **secondary race detector** — it proves no writer holds the lock at that
instant, NOT that the backend is stopped (an idle backend connection could pass the probe and then
write). The on-box preflight MUST record the container as stopped (`docker compose … ps` shows the
backend not running) before invoking backup or restore; the probe never substitutes for that.

`deploy/aws/tests/test_db_backup_restore.sh` (**33 cases**, run under pytest via
`test_db_recovery_harness.py`) proves the scenario on a synthetic WAL-mode DB: back up
(rev `e7b3f2a9c4d1`) → simulate `a4c7e1b93d20` → whole-file restore → the restored DB is
**byte-identical** to the backup, the column **gone**, the revision back to `e7b3f2a9c4d1`,
`integrity_check == ok`. Plus the hardening cases: backup refused under the app tree / db dir / via
`..` / via symlink; the recovery package carries no `-wal`/`-shm`; backup refused when a nonempty WAL
survives the checkpoint and when the live revision is not the approved pre-migration revision; restore
refused on missing metadata, sha mismatch, byte mismatch, wrong revision, corrupt backup, and an
injected staged-fsync failure — each leaving the live DB **byte-identical**; a directory-fsync failure
after the atomic rename reported as the distinct `RESTORE_INCOMPLETE_DIRSYNC` (exit 6); stale live
sidecars cleared with none installed; and active-writer refused.

## 5. On-box preflight — `PENDING BOX-ACCESS AUTHORIZATION`

These require SSH to the validation box and are NOT yet authorized. Documented so they can be executed
verbatim once box access is granted, backend stopped throughout:

1. **Stop writes / prove inertness.** `docker compose … stop backend` (or full `down`); confirm the
   scheduler and Alpaca startup are disabled (`WORKBENCH_SCHEDULER_ENABLED=false`,
   `WORKBENCH_ALPACA_STARTUP_ENABLED=false` in the effective env), so nothing writes the DB.
2. **Record identity of the live pre-migration DB.** `sha256sum`, byte size, and
   `SELECT version_num FROM alembic_version` (expected `e7b3f2a9c4d1`) — via the `backup` command,
   which records all three.
3. **Backup OUTSIDE `/opt/workbench/app`.** e.g. `bash deploy/aws/adr0043_db_backup_restore.sh backup
   /opt/workbench/data/workbench.sqlite /opt/workbench/backups`. Keep the `.bak`, `.bak.meta.json`,
   and any `-wal`/`-shm`.
4. **Verify the backup independently.** integrity_check (the tool does this) plus an out-of-band
   `sha256sum` compare of the `.bak`.
5. **Confirm the recovery command** by dry-running `restore` against a **copy** of the live DB on the
   box (never the live file) and checking `RESTORE_OK` + integrity + revision.

## 6. Exact recovery command (if migration is later authorized and must be rolled back)

Backend stopped, then:

```
bash deploy/aws/adr0043_db_backup_restore.sh restore \
  /opt/workbench/backups/workbench.sqlite.<ts>.bak \
  /opt/workbench/data/workbench.sqlite
# expect: RESTORE_OK, integrity ok, alembic_rev e7b3f2a9c4d1
# then start the PRIOR (80a6c043) stack — it now boots against the pre-migration DB.
```

Expected checks after restore: `integrity_check == ok`; `alembic_version == e7b3f2a9c4d1`;
`sha256(workbench.sqlite) == sha256(<backup>)`; prior stack `HEALTHZ_OK`.

## 7. Migration-authorization gate

`ADR0043_MIGRATION_AUTHORIZED=1` must NOT be set until:

- the on-box preflight (§5) has produced a **verified** whole-file backup outside the app tree, and
- the recovery command (§6) has been dry-run-verified on a **copy** of the live DB, and
- migration execution is explicitly authorized with this recovery plan attached.

Only then does deploying `b0058bf` with the migration gate open apply `a4c7e1b93d20`, with a proven
whole-file restore path back to `e7b3f2a9c4d1`.
