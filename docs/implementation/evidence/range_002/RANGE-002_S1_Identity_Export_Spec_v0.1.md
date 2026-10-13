# RANGE-002 S1: bounded Sharadar identity diagnostic export, specification v0.1

Status: preparation only. The tool and its synthetic tests exist; it has NOT been run on any real store. Running it is a separate decision (data fetching/extraction scope) that this document does not make.

Tool: `apps/backend/scripts/research/range002/export_identity_snapshot.py` (stdlib + duckdb; runs under `python -I`).
Tests: `apps/backend/tests/research/range002/tooling/test_export_identity_snapshot.py` (synthetic DuckDB fixtures only).
Registry: `apps/backend/ci/pu1_export_paths.json` (INTERNAL_ONLY).

## 1. Purpose

Establish whether the existing factor store holds usable issuer identities (permanent ticker id), ticker history and corporate-action records, and what ingest provenance it carries. It is an identity diagnostic, not a strategy-performance dataset: no price or volume column is selected anywhere. The optional (default-on) `sep_coverage` table is a per-ticker min date, max date and row count.

## 2. Tables and columns, with schema evidence

Schema evidence is limited to repository definitions: `apps/backend/app/factor_data/store.py` (projection lists and DDL), `apps/backend/app/research/range002/data/manifest.py` (`REQUIRED_COLUMNS`, L29-43), `apps/backend/scripts/research/range002/pit_coverage_ro.py` (L33-40 `PIT_REQUIRED_COLUMNS`, L116/L238 optional `table`).

| Export table | Column | Required | Evidence | Status |
|---|---|---|---|---|
| tickers | permaticker | yes | store.py L46-48 (`_TICKERS_COLS`), DDL L151, ALTER L161; manifest.py L33 | verified |
| tickers | ticker | yes | store.py DDL L150 (PRIMARY KEY); manifest.py L34 | verified |
| tickers | name, exchange, category | yes | store.py DDL L152 | verified (category also manifest.py L35) |
| tickers | isdelisted | yes | store.py DDL L154 (BOOLEAN); manifest.py L36 | verified (pit_coverage_ro tolerates Y/N strings; see section 9) |
| tickers | firstpricedate, lastpricedate | yes | store.py DDL L155; manifest.py L37-38 | verified |
| tickers | lastupdated | yes | store.py DDL L156 | verified |
| tickers | `table` | optional | pit_coverage_ro.py L116, L238 and its test fixture only; NOT in store.py DDL | **UNVERIFIED** (exported only if present, listed in `columns_unverified_in_schema`) |
| actions | date, action, ticker, name, value, contraticker | yes | store.py L63 (`_ACTIONS_COLS`), DDL L164-167; manifest.py L42 (date, action, ticker, contraticker) | verified; `value` and `name` are in the DDL, not read by PIT logic |
| ingest_runs | dataset, started_at, finished_at, rows, status | yes if table present | store.py DDL L170-175 | verified |
| ingest_runs | run_id | optional | store.py DDL L173, but added to existing stores by ALTER (L325) | verified in schema; may be absent in an old store (then recorded absent) |
| dataset_coverage | dataset, ingest_run_id, coverage_start, coverage_end, artifact_sha256, artifact_path, source_identity, rows_loaded, recorded_at, status | yes if table present | store.py DDL L183-194 | verified |
| sep_coverage (derived) | ticker, min_date, max_date, n_rows | derived from sep.ticker, sep.date | store.py DDL L137-147 | verified; no other sep column is referenced |

`tickers` and `actions` are required tables (fail closed if absent). `ingest_runs` and `dataset_coverage` are recorded as "not exported: table absent" when absent. Deliberately NOT exported: `tickers.sector`, `tickers.industry` (classification, not identity), and every `sep` price/volume column (`open, high, low, close, volume, closeadj, closeunadj`); a guard rejects these names in any delivered file.

Every requested column is checked against `information_schema.columns` at run time. A requested column that is missing raises a refusal before anything is published (no guessing, no substitution). An optional column that is missing is listed in the file's `optional_columns_absent`.

UNVERIFIED (cannot be established from repository sources; to be observed, never assumed):
1. `tickers.table` existence (and, if present, that it means the vendor TICKERS `table` field).
2. Actual column data types in the real store (the DDL says `isdelisted BOOLEAN`; the diagnostic script tolerates `'Y'/'N'` strings, so the real store may differ). The export copies the stored type.
3. Whether the real `tickers` holds more than one row per ticker. The DDL declares `ticker` PRIMARY KEY (store.py L150), which would collapse reuse; manifest.py L27-28 states a collapsed table cannot show reuse.
4. The vocabulary of `actions.action` values (rename events etc.) and `actions.value` semantics: no repository definition of the vendor vocabulary was used.
5. Whether `run_id`/`dataset_coverage` rows exist for the datasets of interest.

## 3. Query text

Exact text is recorded in the manifest (`queries`), with `query_text_sha256` over the queries joined with LF in the order tickers, actions, ingest_runs, dataset_coverage, sep_coverage. Each is run as `COPY (<query>) TO '<staging file>' (FORMAT PARQUET)`. With `table` absent:

```
SELECT "permaticker", "ticker", "name", "exchange", "category", "isdelisted", "firstpricedate", "lastpricedate", "lastupdated" FROM "tickers" ORDER BY <each column> ASC NULLS FIRST
SELECT "date", "action", "ticker", "name", "value", "contraticker" FROM "actions" ORDER BY <each column> ASC NULLS FIRST
SELECT "dataset", "started_at", "finished_at", "rows", "status", "run_id" FROM "ingest_runs" ORDER BY <each column> ASC NULLS FIRST
SELECT "dataset", "ingest_run_id", "coverage_start", "coverage_end", "artifact_sha256", "artifact_path", "source_identity", "rows_loaded", "recorded_at", "status" FROM "dataset_coverage" ORDER BY <each column> ASC NULLS FIRST
SELECT "ticker" AS ticker, MIN("date") AS min_date, MAX("date") AS max_date, COUNT(*) AS n_rows FROM "sep" GROUP BY "ticker" ORDER BY "ticker", "min_date", "max_date", "n_rows" (each ASC NULLS FIRST)
```

(`<each column>` is expanded in the real text; the manifest contains the full strings.)

## 4. Consistency basis and limits

The source is opened `read_only=True`. Schema introspection, the ingest-identifier reads and every COPY run inside one `BEGIN TRANSACTION ... COMMIT` on that connection, so all tables reflect one DuckDB snapshot. Limits: (a) consistency is DuckDB's snapshot isolation for that connection only; the script does not quiesce or coordinate with other writers. (b) DuckDB takes a file lock: opening read-only may fail while another process holds the store open for writing (the script then fails with nothing published; it never works around a lock). (c) No hash of the live `.duckdb` file is recorded or required; the evidence of what was read is the query text plus the logical content hashes. (d) Atomicity covers publication of the directory, not the read of the source.

## 5. Manifest (`manifest.json`, schema_version `range002.identity_export_manifest.v1`)

Fields: `export_id`; `source` (system, `path_as_given`, note); `extraction_time_utc` (taken just after BEGIN); `executing_identity` (free text); `purpose`; `duckdb_version`; `python_version`; `script_version`; `script_sha256` (SHA-256 of the script file); `queries`; `copy_template`; `query_text_sha256`; `ingest_identifiers` (`ingest_runs` and `dataset_coverage`: each a non-empty list read inside the transaction, or `{"value":"unavailable","reason":...}`, never omitted); `files[]` (table, file, rows, `date_bounds` per date column, `columns`, `optional_columns_absent`, `byte_sha256`, `logical_sha256`, bytes, license_sidecar); `tables_not_exported`; `license_status`; `license_note`; `permission_basis_claimed` (`ref`, `scope`, `tables_named_in_scope`, `tables_not_named_in_scope`); `permission_verified` (always `false`); `permission_note`; `destination_path`; `columns_unverified_in_schema`; `consistency`; `marker`. Validation (`validate_manifest`) fails on any missing or empty required field, a `permission_verified` other than `false`, an empty ref or scope, a forbidden column name, or a `sep_coverage` with columns other than the four.

## 6. Logical content hash (canonical form)

Independent of Parquet encoding and of source row order. For each exported file the content is read back from the delivered Parquet with `ORDER BY <all exported columns, in the fixed column-list order> ASC NULLS FIRST` and serialized as:

* Line 1: compact JSON `[[column_name, duckdb_type], ...]` in the fixed column order.
* One line per row: compact JSON array of the values in that order, ASCII-escaped, LF-terminated.
* NULL is JSON `null` (distinct from `""`). Booleans `true`/`false`. Integers as JSON integers; floats by Python's shortest round-trip repr, so `1` and `1.0` hash differently (the column type is also in the header); non-finite floats as the tag string `__float__:nan`/`__float__:inf`. DATE and TIMESTAMP as ISO-8601. Strings are byte-exact: no Unicode normalization (so NFC and NFD forms of the same text hash differently, deliberately: the export does not alter vendor text). No locale dependence (DuckDB's default string ordering is binary).
* SHA-256 of the concatenated bytes.

Tests cover: unchanged source gives equal hashes across two exports; reordered source rows give equal hashes; a changed value changes the hash; NULL and empty string differ; int and float differ; NFC/NFD differ; column order matters.

## 7. Staging, publish and overwrite rules

1. Refuse if `<dest-root>/<export-id>` or `<dest-root>/.staging-<export-id>` exists (never overwrite, never merge). `--dest-root` must be an existing directory and has no default. `export-id` must match `[A-Za-z0-9][A-Za-z0-9._-]{0,127}`.
2. All output is written to `<dest-root>/.staging-<export-id>/`, then validated (manifest defects; every file's byte hash, row count and logical hash re-computed from the written file).
3. `EXPORT_COMPLETE.json` is written last inside staging (it records the manifest SHA-256 and file list), then the directory is published with a single `os.rename` to `<dest-root>/<export-id>/`. Staging is a sibling, so the rename is same-filesystem and atomic. A published directory therefore always contains the marker. Consumers must require `EXPORT_COMPLETE.json`, and may re-check with `--verify <dir>`.
4. A failed export is never published: only `.staging-<export-id>/` remains, with `EXPORT_FAILED.json` and no completion marker. It must be inspected or cleaned (section 8) before the same id is reused.

## 8. License status and permission

`--license-status` (UNKNOWN default, or PERSONAL, COMMERCIAL_OK) is recorded in the manifest and nothing more. Every delivered file and `manifest.json` gets a PU-1 sidecar `<file>.license.json` (same JSON shape and bytes as `app.licensing.envelope.write_sidecar`; a test asserts equality) declaring sources `["sharadar"]`, whose registry scope is UNKNOWN, so `export_file_for_external_use` refuses every file even when `--license-status COMMERCIAL_OK` is passed. `README_PU1.txt` states internal diagnostics only. Classification is not permission.

`--permission-ref` and `--permission-scope` are both required, non-empty, and recorded verbatim as `permission_basis_claimed` with `permission_verified: false`. The script cannot verify them and does not try. The manifest lists which exported tables the scope text names and which it does not (informational; it does not block). Authorized internal reads remain possible: the Parquet files are readable with duckdb and `pit_coverage_ro.report`.

## 9. Cleanup

`export_identity_snapshot.py --cleanup <export-id> --dest-root <dir>` is a DRY RUN: it prints exactly the files it would remove and removes nothing. `--apply` deletes. Scope is strictly `<dest-root>/<export-id>` and `<dest-root>/.staging-<export-id>`. It refuses: an id that is not a plain id (no separators or `..`); a target that is a symlink or junction, or any symlink/junction inside it; a target whose resolved parent is not dest-root; a published directory without a manifest, or a manifest whose `export_id` differs from the id; any entry that is not a regular file or is not a known name (listed in the manifest or its sidecar, or one of manifest.json, README_PU1.txt, EXPORT_COMPLETE.json, EXPORT_FAILED.json, or the fixed table file names for a staging directory). It deletes files one by one and then the emptied directories; it never recurses, never touches the source store, sibling exports or unrelated files. Apart from `--cleanup --apply` the script performs no deletion.

## 10. What this export does not establish

* It shows only what is in the store. If the store overwrote or collapsed history (for example a `ticker` primary key, or a retro-mapped rename), the export cannot reconstruct reuse or renames that are not there.
* It does not establish PIT eligibility, vendor licence or retention permission, completeness against the vendor's TICKERS table, or that `actions` is complete.
* Without a `sep` price table the existing `pit_coverage_ro.report` stops at "BLOCKED: tickers/sep table missing" on this export (it still lists the files and byte hashes). The coverage of `sep` is available only through `sep_coverage`.
* Not evidence of a person's review; the permission fields are claims, not verified.

## 11. Operator command line (placeholders)

```
python -I apps/backend/scripts/research/range002/export_identity_snapshot.py \
  --source <path-to-factor_data.duckdb> --dest-root <existing-research-dir> \
  --export-id <s1-YYYYMMDD-N> --purpose "<text>" --executing-identity "<name or role>" \
  --permission-ref "<record of permission basis claimed>" \
  --permission-scope "<scope text naming tickers, actions, ingest_runs, dataset_coverage, sep_coverage>" \
  [--no-sep-coverage] [--license-status UNKNOWN]
python -I .../export_identity_snapshot.py --verify <dest-root>/<export-id>
python -I .../export_identity_snapshot.py --cleanup <export-id> --dest-root <dest-root> [--apply]
```

Proposed destination (repository evidence only; the mount is UNVERIFIED without production access): host `/opt/workbench/data/research/range002_s1/` as `--dest-root`, export under `<export-id>` beneath it. Evidence: `deploy/aws/factor-refresh.sh:25` (`DATADIR=/opt/workbench/data`, "mounted into the container at /app/data") and `:26` (store at `$DATADIR/factor_data.duckdb`), `deploy/aws/factor-freshness.sh:155-158` (host `/opt/workbench/data`, in-container `/app/data`), `docs/runbook/aws-migration.md:110` (factor store seeded to `/opt/workbench/data/`), `deploy/aws/log-watcher.sh:4` (precedent subdirectory `/opt/workbench/data/ops/`). Inside the container the same location is `/app/data/research/range002_s1/`. No `research/` subdirectory is defined in the repository; it must be created by the operator, and the mount mapping (`docker-compose.yml:24` uses `./data:/app/data` relative to the project directory) is UNVERIFIED.
