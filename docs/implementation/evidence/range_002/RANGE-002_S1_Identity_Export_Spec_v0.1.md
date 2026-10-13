# RANGE-002 S1: identity + screening handoff export, specification v0.2

(File name keeps the v0.1 path; the content is v0.2, "screening handoff".)

Status: preparation only. The tool and its synthetic tests exist; it has NOT been run on any real store. Running it is a separate decision (data extraction scope) that this document does not make.

Tool: `apps/backend/scripts/research/range002/export_identity_snapshot.py` (stdlib + duckdb; runs under `python -I`; script version 1.1.0).
Tests: `apps/backend/tests/research/range002/tooling/test_export_identity_snapshot.py` (synthetic DuckDB fixtures only).
Registry: `apps/backend/ci/pu1_export_paths.json` (INTERNAL_ONLY).

## 0. Revised scope for authorization

What would be authorized, exactly (a decision for the weekly meeting minutes or Jay's explicit instruction; this document records no decision):

| Item | Content |
|---|---|
| Tables, identity | `tickers` (permaticker, ticker, name, exchange, category, isdelisted, firstpricedate, lastpricedate, lastupdated; plus `table` only if the store has it), `actions` (date, action, ticker, name, value, contraticker), `ingest_runs` (dataset, started_at, finished_at, rows, status, run_id if present), `dataset_coverage` (10 provenance columns) |
| Table, coverage | `sep_coverage`: ticker, min_date, max_date, n_rows over the FULL sep table (default on; `--no-sep-coverage` omits it) |
| Table, screening | `sep_daily` (only with `--include-sep-daily`): ticker, date, open, high, low, close, closeunadj, closeadj, volume, lastupdated; required: ticker, date, close, closeunadj, volume; any other column missing from the store is listed in `columns_missing`, never guessed |
| Window | `date BETWEEN --sep-date-from AND --sep-date-to` inclusive, all tickers present in it (bounded by date, not by a symbol list). Screening quarter 2016-Q1 = 2016-01-01..2016-03-31 plus lookback. Recommended: `--sep-date-from 2015-11-02`, `--sep-date-to 2016-03-31`, `--screen-start 2016-01-01` (about 40 trading sessions before the first 2016 month: a margin over N for the prior-close/price-floor check and for a decision day that is the last session before the month) |
| Lookback requirement | `--required-lookback-trading-days 20` , `--lookback-calendar-days 45` and `--max-decision-gap-days 7` (owner-confirmed maximum D-to-month-start gap). Current SCHEMA-PINNED values: `universe.adv_window_days = 20` (`apps/backend/app/research/range002/spec/schema.py:293`, `_eq(20)`) and `universe.min_price = 10.0` (`schema.py:292`, `_eq(10.0)`; recorded for context, not used by the export); runner `--lookback-calendar-days 45` (slice `[D - 45 days, D]`, `run_descriptive_screen.py`). They are inputs to the tool, never defaults; they are re-read from the frozen spec at freeze |
| Consistency | one DuckDB read transaction on a `read_only=True` connection (section 4) |
| Expected size (order of magnitude, not measured) | identity tables: 10^4 to 10^5 rows each; sep_coverage: 10^4 rows; sep_daily: roughly 10^6 rows (~10^3 to 10^4 tickers x ~105 sessions), tens of MB of Parquet. Not verified against the real store; the manifest reports actual rows and bytes |
| Manifest | section 5 |
| Does NOT do | no repair of overwritten issuer history; no SIP/intraday/minute bars (refused by name); no unbounded history (an explicit window is mandatory); no fundamentals or other tables; no universe change (affected issuers are only reported; the universe builder excludes them visibly as INSUFFICIENT_HISTORY); no write to the store or to production; no copy of the .duckdb file; no network; no deletion except `--cleanup --apply` of one export id |
| License | status recorded, default UNKNOWN; PU-1 sidecars declare source `sharadar`, registry scope UNKNOWN, so the external-use seam refuses every file; a label does not grant permission (section 8) |
| Permission | `--permission-ref` and `--permission-scope` recorded as a claim; `permission_verified` is always false |
| Destination | placeholder `<dest-root>`; proposed `/opt/workbench/data/research/range002_s1/` (UNVERIFIED, section 11) |
| Command line | section 11 |

## 1. Purpose

(a) Establish whether the existing store holds usable issuer identities (permanent ticker id), ticker history and corporate-action records, with ingest provenance. (b) With `--include-sep-daily`, hand the RANGE-002 screening run the daily SEP rows it needs for one bounded window, with proof that the lookback is adequate. Default mode (no `--include-sep-daily`) exports no price or volume column at all.

## 2. Tables and columns, with schema evidence

Schema evidence is limited to repository definitions: `apps/backend/app/factor_data/store.py` (projection lists and DDL), `apps/backend/app/research/range002/data/manifest.py` (`REQUIRED_COLUMNS`, L29-43), `apps/backend/scripts/research/range002/pit_coverage_ro.py` (L33-40 `PIT_REQUIRED_COLUMNS`, L116/L238 optional `table`).

| Export table | Column | Required | Evidence | Status |
|---|---|---|---|---|
| tickers | permaticker | yes | store.py L46-48 (`_TICKERS_COLS`), DDL L151, ALTER L161; manifest.py L33 | verified |
| tickers | ticker | yes | store.py DDL L150 (PRIMARY KEY); manifest.py L34 | verified |
| tickers | name, exchange, category | yes | store.py DDL L152 | verified (category also manifest.py L35) |
| tickers | isdelisted | yes | store.py DDL L154 (BOOLEAN); manifest.py L36 | verified (pit_coverage_ro tolerates Y/N strings; section 10) |
| tickers | firstpricedate, lastpricedate | yes | store.py DDL L155; manifest.py L37-38 | verified |
| tickers | lastupdated | yes | store.py DDL L156 | verified |
| tickers | `table` | optional | pit_coverage_ro.py L116, L238 and its test fixture only; NOT in store.py DDL | **UNVERIFIED** (exported only if present, listed in `columns_unverified_in_schema`) |
| actions | date, action, ticker, name, value, contraticker | yes | store.py L63, DDL L164-167; manifest.py L42 | verified |
| ingest_runs | dataset, started_at, finished_at, rows, status | yes if table present | store.py DDL L170-175 | verified |
| ingest_runs | run_id | optional | store.py DDL L173; added to old stores by ALTER (L325) | verified in schema; may be absent in an old store |
| dataset_coverage | dataset, ingest_run_id, coverage_start, coverage_end, artifact_sha256, artifact_path, source_identity, rows_loaded, recorded_at, status | yes if table present | store.py DDL L183-194 | verified |
| sep_coverage (derived) | ticker, min_date, max_date, n_rows | from sep.ticker, sep.date | store.py DDL L137-147 | verified |
| sep_daily | ticker, date, close, closeunadj, volume | required | store.py `_SEP_COLS` L34-44, DDL L137-147; manifest.py L41 | verified |
| sep_daily | open, high, low, closeadj, lastupdated | optional (recorded in `columns_missing` if absent) | store.py `_SEP_COLS` L34-44, DDL L137-147 | verified in schema; may be absent in the real store |

`tickers` and `actions` are required tables (fail closed if absent). `ingest_runs` and `dataset_coverage` are recorded as "not exported: table absent" when absent. `sep` is required only when `sep_coverage` or `sep_daily` is requested. Deliberately NOT exported: `tickers.sector`, `tickers.industry`.

Column guard (allowlist). Price/volume names (`open, high, low, close, volume, closeadj, closeunadj, adj_close, price`, plus any column containing `close`, `volume` or `adj`) are allowed ONLY in `sep_daily` and ONLY from the explicit list above. In any other table they are refused at planning time and by manifest validation; any `sep_daily` column outside the explicit list is refused. Intraday/minute/SIP/bar tables (names matching intraday, minute, bars, sip, quote, trade, ...) requested through `--table` are refused by name with an "out of scope" message; any other unlisted table name is refused too.

Every requested column is checked against `information_schema.columns` at run time. A required column that is missing raises a refusal before anything is published.

UNVERIFIED (cannot be established from repository sources; to be observed, never assumed):
1. `tickers.table` existence (and, if present, that it means the vendor TICKERS `table` field).
2. Actual column data types in the real store (the DDL says `isdelisted BOOLEAN`; the diagnostic script tolerates `'Y'/'N'`). The export copies the stored type.
3. Whether the real `tickers` holds more than one row per ticker. The DDL declares `ticker` PRIMARY KEY (store.py L150), which would collapse reuse; manifest.py L27-28 says a collapsed table cannot show reuse.
4. The vocabulary of `actions.action` values and `actions.value` semantics.
5. Whether `run_id`/`dataset_coverage` rows exist for the datasets of interest.
6. The price basis of `close`, `closeadj`, `closeunadj`, `volume`: recorded as vendor-documentation claims (`price_basis_declared`), never verified by the script.

## 3. Query text

Exact text is recorded in the manifest (`queries`), with `query_text_sha256` over the queries joined with LF in the order tickers, actions, ingest_runs, dataset_coverage, sep_coverage, sep_daily. Each runs as `COPY (<query>) TO '<staging file>' (FORMAT PARQUET)`. Every query ends in an explicit `ORDER BY <each exported column> ASC NULLS FIRST` (expanded in the manifest). With `table` absent and all sep columns present:

```
SELECT "permaticker", "ticker", "name", "exchange", "category", "isdelisted", "firstpricedate", "lastpricedate", "lastupdated" FROM "tickers" ORDER BY ...
SELECT "date", "action", "ticker", "name", "value", "contraticker" FROM "actions" ORDER BY ...
SELECT "dataset", "started_at", "finished_at", "rows", "status", "run_id" FROM "ingest_runs" ORDER BY ...
SELECT "dataset", "ingest_run_id", "coverage_start", "coverage_end", "artifact_sha256", "artifact_path", "source_identity", "rows_loaded", "recorded_at", "status" FROM "dataset_coverage" ORDER BY ...
SELECT "ticker" AS ticker, MIN("date") AS min_date, MAX("date") AS max_date, COUNT(*) AS n_rows FROM "sep" GROUP BY "ticker" ORDER BY ...
SELECT "ticker", "date", "open", "high", "low", "close", "closeunadj", "closeadj", "volume", "lastupdated" FROM "sep" WHERE "date" BETWEEN DATE '<from>' AND DATE '<to>' ORDER BY ...
```

## 4. Consistency basis and lookback check

The source is opened `read_only=True`. Schema introspection, the lookback check, the ingest-identifier reads and every COPY run inside one `BEGIN TRANSACTION ... COMMIT` on that connection, so all tables reflect one DuckDB snapshot. Limits: (a) consistency is DuckDB snapshot isolation for that connection only; the script does not quiesce or coordinate with other writers. (b) DuckDB takes a file lock: opening read-only may fail while another process holds the store open for writing (nothing is published; the script never works around a lock). (c) No hash of the live `.duckdb` file is recorded or required; the evidence of what was read is the query text plus the logical hashes. (d) Atomicity covers publication of the directory, not the read of the source.

Lookback adequacy (only with `--include-sep-daily`). Required inputs, no defaults: `--sep-date-from`, `--sep-date-to`, `--screen-start`, `--required-lookback-trading-days N`, `--lookback-calendar-days L`, `--max-decision-gap-days G`. Dates are strict `YYYY-MM-DD`; `sep-date-from < screen-start <= sep-date-to`; N, L and G are integers >= 1. Giving any of the six without `--include-sep-daily` is refused.

1. Decision days. For each month start M with `screen-start <= M <= sep-date-to` (2016-01-01, 2016-02-01, 2016-03-01), D is the last date present in `sep_daily` strictly before M, derived from the data (expected 2015-12-31, 2016-01-29, 2016-02-29; never hard-coded). No such date: refused, message names M.
2. Structural check (fails closed; run inside the transaction before any file is written, then re-run on the delivered file and required to be identical). The runner slice is the calendar range `[D - L, D]` inclusive. It must contain at least N distinct dates present in `sep_daily` by itself; history outside the slice never satisfies the check. D itself is present by construction. Failure message: `lookback inadequate: decision day <D> (month start <M>): the runner slice [<start>, <D>] holds <n> distinct trading dates < required <N> ...`; nothing is exported and nothing is published. (A "trading date" is a date present in SEP, not an exchange calendar.)
3. Per-issuer report (informational, never fails the export). Among tickers with a row on D, those with fewer than N USABLE observations inside the slice (usable = close, closeunadj and volume non-null and > 0 on that date). Summary counts per reason and a capped sample (20) are in the manifest; the full list per decision day, with reasons, is the export file `lookback_affected_issuers.json`. Reasons: `ROWS_IN_SLICE_LT_<N>` (fewer than N dated rows), `NULL_FIELD`, `ZERO_VOLUME`, `NONPOSITIVE_PRICE` (added: close or closeunadj <= 0, since "usable" requires > 0). These issuers will be excluded visibly by the universe builder as INSUFFICIENT_HISTORY; the export changes no universe and removes no row.
4. Availability record, per D: `d_precedes_month_start` (D < M), `max_date_in_slice` (must equal D), `rows_in_slice_with_date_after_decision_day` (0 by construction), `exported_rows_after_decision_day_not_in_slice` (informational), and `lastupdated_vs_decision_day`: count of slice rows whose `lastupdated` is later than D, with min and max. Vendor `lastupdated` is not an as-of timestamp, so this only shows possible later revisions in the delivered rows (report-only: nothing is filtered or changed). If `lastupdated` is absent the entry is `{"value":"unavailable","reason":...}`.
5. Decision-day gap (enforced). `(M - D)` in calendar days must be <= G (owner-confirmed value 7). Otherwise refused, nothing exported or published: `decision-day gap too large: decision day <D> (month start <M>): gap <n> calendar days > maximum <G> (data hole or short window; nothing exported)`. This is checked before the slice count, so a data hole is refused even when the lookback slice would pass. `decision_day_gap_calendar_days`, `max_decision_gap_days` and `gap_within_limit: true` are recorded per decision day, and G in `planning_inputs.max_decision_gap_days`; the whole check is re-run on the delivered file and must be identical.

## 5. Manifest (`manifest.json`, schema_version `range002.identity_export_manifest.v1`)

Fields: `export_id`; `source` (system, `path_as_given`, note); `extraction_time_utc`; `executing_identity` (free text); `purpose`; `duckdb_version`; `python_version`; `script_version`; `script_sha256`; `queries`; `copy_template`; `query_text_sha256`; `ingest_identifiers` (`ingest_runs` and `dataset_coverage`: a non-empty list read inside the transaction, or `{"value":"unavailable","reason":...}`, never omitted); `files[]` (table, file, rows, `date_bounds` per date column, `columns`, `optional_columns_absent`, `columns_missing`, `byte_sha256`, `logical_sha256`, bytes, license_sidecar); `tables_not_exported`; `license_status`; `license_note`; `permission_basis_claimed` (`ref`, `scope`, `tables_named_in_scope`, `tables_not_named_in_scope`); `permission_verified` (always `false`); `permission_note`; `destination_path`; `columns_unverified_in_schema`; `consistency`; `marker`. With `sep_daily` also: `planning_inputs` (`universe.adv_window_days` as supplied, `adv_window_matches_schema_pin`, `universe.min_price` 10.0 context only, `lookback_calendar_days`, `max_decision_gap_days`, `export_window`, `screen_start`, `evidence` citing schema.py:292-293 and the runner, `status`: current schema-pinned values, re-read from the frozen spec at freeze) and `report_files[]` (`lookback_affected_issuers.json`: file, byte_sha256, bytes, license_sidecar; it carries a PU-1 sidecar like every delivered file and is listed in `EXPORT_COMPLETE.json`).

`sep_daily` section (present exactly when the file is): `requested_window` (from, to, inclusive), `screen_start`, `min_date_present`, `max_date_present`, `rows`, `distinct_tickers`, `distinct_trading_dates`, `rows_per_year`, `columns_requested`, `columns_present`, `columns_missing`, `price_basis_declared` (exactly: close "vendor-documented split-adjusted (UNVERIFIED against data)"; closeadj "vendor-documented split- and dividend-adjusted (UNVERIFIED)"; closeunadj "vendor-documented unadjusted (UNVERIFIED)"; volume "vendor-documented split-adjusted (UNVERIFIED)"), `price_basis_note`, `provenance_fields_present` (lastupdated if present; ingest run ids and dataset_coverage rows are in `ingest_identifiers`), `lookback` (rule, required_trading_days, lookback_calendar_days, found_trading_days_min, `decision_days[]` with the section 4 fields plus tickers_on_decision_day, affected_issuers_count, affected_by_reason, affected_sample, rows_in_slice; affected_issuers_file; result), `limitations`:
* does not repair overwritten issuer history: tickers is keyed by ticker in the store DDL, so ticker reuse is collapsed; this file adds no identity beyond tickers;
* contains no SIP/intraday minute bars; SEP is daily only;
* tickers.category is as-of-latest in the store unless proven otherwise;
* price_basis_declared entries are claims, never verified by the script;
* lookback adequacy counts distinct dates present, not an exchange calendar;
* bounded by date window, not by a symbol list; store survivorship is not established here.

Validation (`validate_manifest`) fails on any missing or empty required field, `permission_verified` other than `false`, an empty ref or scope, a price/volume column outside `sep_daily` or a `sep_daily` column outside the explicit list, a `sep_coverage` with other than the four columns, a `sep_daily` file without its section (or the reverse), `price_basis_declared` differing from the claims above, a lookback result other than PASS or without decision days, or missing `planning_inputs`/`report_files` with `sep_daily`.

## 6. Logical content hash (canonical form)

Independent of Parquet encoding and of source row order. Each file is read back from the delivered Parquet (streamed in chunks) with `ORDER BY <all exported columns, in the fixed column-list order> ASC NULLS FIRST` and serialized as:

* Line 1: compact JSON `[[column_name, duckdb_type], ...]`.
* One line per row: compact JSON array of the values in that order, ASCII-escaped, LF-terminated.
* NULL is JSON `null` (distinct from `""`). Booleans `true`/`false`. Integers as JSON integers; floats by Python's shortest round-trip repr, so `1` and `1.0` differ (the column type is also in the header); non-finite floats as the tag `__float__:nan`/`__float__:inf`. DATE and TIMESTAMP as ISO-8601. Strings are byte-exact: no Unicode normalization (NFC and NFD forms hash differently, deliberately). No locale dependence (DuckDB's default string ordering is binary).
* SHA-256 of the concatenated bytes.

## 7. Staging, publish and overwrite rules

1. Refuse if `<dest-root>/<export-id>` or `<dest-root>/.staging-<export-id>` exists (never overwrite, never merge). `--dest-root` must be an existing directory and has no default. `export-id` must match `[A-Za-z0-9][A-Za-z0-9._-]{0,127}`.
2. All output is written to `<dest-root>/.staging-<export-id>/`, then validated (manifest defects; every file's byte hash, row count and logical hash re-computed from the written file).
3. `EXPORT_COMPLETE.json` is written last inside staging (manifest SHA-256 and file list), then the directory is published with a single `os.rename` to `<dest-root>/<export-id>/`. Staging is a sibling, so the rename is same-filesystem and atomic. A published directory always contains the marker. Consumers must require `EXPORT_COMPLETE.json`, and may re-check with `--verify <dir>`.
4. A failed export is never published: only `.staging-<export-id>/` remains, with `EXPORT_FAILED.json` and no completion marker. It must be inspected or cleaned (section 9) before the same id is reused.

## 8. License status and permission

`--license-status` (UNKNOWN default, or PERSONAL, COMMERCIAL_OK) is recorded in the manifest and nothing more. Every delivered file and `manifest.json` gets a PU-1 sidecar `<file>.license.json` (same JSON shape and bytes as `app.licensing.envelope.write_sidecar`; a test asserts equality) declaring sources `["sharadar"]`, whose registry scope is UNKNOWN, so `export_file_for_external_use` refuses every file even with `--license-status COMMERCIAL_OK`. `README_PU1.txt` states internal diagnostics/screening inputs only. Classification is not permission.

`--permission-ref` and `--permission-scope` are both required, non-empty, and recorded verbatim as `permission_basis_claimed` with `permission_verified: false`. The script cannot verify them and does not try. Authorized internal reads remain possible: the Parquet files are readable with duckdb.

## 9. Cleanup

`export_identity_snapshot.py --cleanup <export-id> --dest-root <dir>` is a DRY RUN: it prints exactly the files it would remove and removes nothing. `--apply` deletes. Scope is strictly `<dest-root>/<export-id>` and `<dest-root>/.staging-<export-id>`. It refuses: an id that is not a plain id; a target that is a symlink or junction, or any symlink/junction inside it; a target whose resolved parent is not dest-root; a published directory without a manifest, or a manifest whose `export_id` differs from the id; any entry that is not a regular file or is not a known name (listed in the manifest or its sidecar, or one of manifest.json, README_PU1.txt, EXPORT_COMPLETE.json, EXPORT_FAILED.json, or the fixed table file names). It deletes files one by one and then the emptied directories; it never recurses, never touches the source store, sibling exports or unrelated files. Apart from `--cleanup --apply` the script performs no deletion.

## 10. What this export does not establish, and consumer notes

* It shows only what is in the store. If the store overwrote or collapsed history (a `ticker` primary key, a retro-mapped rename), the export cannot reconstruct reuse or renames that are not there.
* It does not establish PIT eligibility, vendor licence or retention permission, completeness against the vendor's TICKERS table, or that `actions` is complete.
* The price basis of the SEP columns is a claim, not a finding.
* `pit_coverage_ro.py` is unchanged. Given a Parquet directory it builds views from files named `tickers`, `sep`, `actions`, `ingest_runs`, `dataset_coverage` (`<table>.parquet` or `<table>/*.parquet`). The staged price file is named `sep_daily.parquet`, so on an export directory as delivered the PIT diagnostic reports "BLOCKED: tickers/sep table missing". Mapping `sep` to `sep_daily` is the consumer's step. In the consumer's own DuckDB session:

```sql
CREATE VIEW sep AS SELECT * FROM read_parquet('<export dir>/sep_daily.parquet');
```

  `pit_coverage_ro.report` builds its own views from file names, so using it unchanged also requires a consumer-side scratch directory in which the file is named `sep.parquet` (a copy; never rename or edit the export in place). A copy carries no valid license sidecar and is not an export.

## 11. Operator command line, preflight and destination

Preflight (operator steps; the tool enforces only P4 and that `<dest-root>` exists; P1-P3 and P5 are not checked by the script, and the script never creates a probe file):

```
# P1  mount exists and is the intended volume (expected: the data volume behind /opt/workbench/data)
df -h <dest-root>        # confirm Filesystem / Mounted-on is the intended volume, not the root disk by accident
# P2  free space >= max(3 x expected size, 1 GiB)   (expected size order: tens of MB; not measured)
df -B1 --output=avail <dest-root>
# P3  write access: the OPERATOR creates and removes one probe file inside <dest-root> only
touch <dest-root>/.s1-write-probe && rm <dest-root>/.s1-write-probe
# P4  export id not already present (the script also refuses this)
test ! -e <dest-root>/<export-id> && test ! -e <dest-root>/.staging-<export-id> && echo free
# P5  the factor store is not being written (a writer holds the file lock; the read-only open then fails)
```

The single export command:

```
python -I apps/backend/scripts/research/range002/export_identity_snapshot.py \
  --source <path-to-factor_data.duckdb> --dest-root <existing-research-dir> \
  --export-id <s1-YYYYMMDD-N> --purpose "<text>" --executing-identity "<name or role>" \
  --permission-ref "<record of permission basis claimed>" \
  --permission-scope "<scope text naming tickers, actions, ingest_runs, dataset_coverage, sep_coverage, sep_daily>" \
  --include-sep-daily --sep-date-from 2015-11-02 --sep-date-to 2016-03-31 \
  --screen-start 2016-01-01 --required-lookback-trading-days 20 --lookback-calendar-days 45 \
  --max-decision-gap-days 7
```

Optional: `--no-sep-coverage`, `--license-status UNKNOWN|PERSONAL|COMMERCIAL_OK` (default UNKNOWN). Afterwards:

```
python -I .../export_identity_snapshot.py --verify <dest-root>/<export-id>
python -I .../export_identity_snapshot.py --cleanup <export-id> --dest-root <dest-root> [--apply]
```

(N = 20 and L = 45 are the current schema-pinned/runner values, re-read from the frozen spec at freeze; G = 7 is the maximum decision-day gap confirmed by the owner; the dates are recommendations, not decisions.)

Proposed destination (repository evidence only; the mount is UNVERIFIED without production access): host `/opt/workbench/data/research/range002_s1/` as `--dest-root`, export under `<export-id>` beneath it. Evidence: `deploy/aws/factor-refresh.sh:25` (`DATADIR=/opt/workbench/data`, "mounted into the container at /app/data") and `:26` (store at `$DATADIR/factor_data.duckdb`), `deploy/aws/factor-freshness.sh:155-158`, `docs/runbook/aws-migration.md:110`, `deploy/aws/log-watcher.sh:4` (precedent subdirectory `/opt/workbench/data/ops/`). Inside the container the same location is `/app/data/research/range002_s1/`. No `research/` subdirectory is defined in the repository; it must be created by the operator, and the mount mapping (`docker-compose.yml:24` uses `./data:/app/data` relative to the project directory) is UNVERIFIED.
