# TradingWorkbench — EAD Phase 0A: Event-Store Schema Reconciliation

| Field | Value |
|---|---|
| Document version | v0.1 (design for sign-off) |
| Date | 2026-07-05 |
| Governs | The `corporate_events` schema change + Form-4 `available_time` backfill that ADR 0037 Decision 8 requires before any EAD ingestion (Phase 1) |
| Authority | ADR 0037 (Accepted 2026-07-05) — "the Form-4 `available_time` backfill is a separately-signed-off migration, not a bundled comment" |
| Status | **Design — awaiting owner sign-off of the backfill (§6).** No code applied; no live/box change. The Event Store is an offline DuckDB research artifact (`get_settings().event_store_path`), not the trading DB. |
| Related | ADR 0027 (the store this extends), ADR 0037 Decisions 8–12, `TradingWorkbench_NewCapabilities_BuildSpec_v0.3.docx` §2.5/§2.6 |

---

## 0. Purpose

ADR 0037 Decision 8 adds first-class PIT/identity/audit/licensing/eligibility columns to the existing `corporate_events` store and makes `available_time` the canonical PIT anchor. The single riskiest step is the backfill of historical **Form-4** rows (the live INSIDER-001 evidence base). This note (a) inventories every reader/writer of the store, (b) proves the migration is **inert for INSIDER-001 by construction**, (c) specifies the exact DDL / code changes, and (d) defines the backfill's acceptance-vs-dissemination characterization, reversibility, and result-invariance verification — the gate the owner signs off before Phase 1.

---

## 1. Usage inventory (what touches `corporate_events`)

| Kind | Site | How it touches the table |
|---|---|---|
| **Writer** | `app/altdata/sec/ingest.py:207` → `store.upsert_events(events)` | Positional `INSERT INTO corporate_events VALUES (?,…×10)` (`store.py:110`) |
| **Writer** | `scripts/ingest_form4_resume.py:99` | Same `upsert_events` path |
| **PIT read (only row-returning one)** | `store.events_asof()` (`store.py:117`) | `SELECT {_COLUMNS} … WHERE CAST(filed_at AS DATE) <= ? …` → `_row_to_event` |
| **INSIDER-001 reproduction** | `scripts/run_insider_reproduction.py:89` → `events_asof(as_of, event_type="insider_buy")` | Consumes the above |
| **Signal construction** | `app/altdata/signal.py` | Pure in-memory over `CorporateEvent` objects — never queries the store |
| **§2 validation gate** | `app/altdata/validate.py` | Uses aggregate methods `coverage()` / `latency_audit()` only (no `SELECT *`) |
| **Aggregates** | `store.count/coverage/latency_audit` | `COUNT`/`MIN`/`MAX`/`MEDIAN` — unaffected by added nullable columns |
| **Tests** | `tests/altdata/test_event_store.py`, `test_ingest.py`, `test_validate.py`, `test_signal.py` | Construct a temp store, `upsert_events`, assert on `events_asof` |

**The one load-bearing fact:** `events_asof` is the *only* code path that returns event rows, it projects a fixed 8-column tuple `_COLUMNS = (cik, ticker, event_type, source, accession, filed_at, event_date, payload)`, and `_row_to_event` builds `CorporateEvent` from exactly those 8. Nothing does `SELECT *`. `signal.py` reads only the in-memory dataclass.

---

## 2. Invariance guarantee (why the backfill cannot move INSIDER-001)

The migration is designed so INSIDER-001's result is invariant at the **code** level, not merely the data level:

1. **New columns are nullable and outside the read projection.** `_COLUMNS`, `_row_to_event`, and the legacy `events_asof` SQL are left byte-for-byte unchanged. Existing Form-4 rows get `NULL` in every new column; the projection never selects them.
2. **INSIDER-001 never reads the new columns.** `run_insider_reproduction.py` filters on `event_type` + `filed_at` only. `available_time`, `research_eligible`, `resolved_security_id`, … are simply not in its query. Backfilling them is therefore *inert* for the reproduction — the strongest form of "no read changes result."
3. **The positional-INSERT footgun is fixed, not stepped on.** The current `INSERT … VALUES (?,…×10)` relies on exact column count/order and would silently misalign the moment a column is added. The migration makes the INSERT **column-explicit** (§3.3) so old and new writers stay correct.

**Verification (not assertion):** §4.3 requires re-running `run_insider_reproduction.py` against a copy of the live event store pre- and post-migration and diffing the output — the sign-off does not rely on this reasoning alone.

---

## 3. Schema migration design

### 3.1 New columns (ADR 0037 Decision 8)

```sql
ALTER TABLE corporate_events ADD COLUMN provider_dataset     VARCHAR;
ALTER TABLE corporate_events ADD COLUMN source_event_id      VARCHAR;
ALTER TABLE corporate_events ADD COLUMN available_time       TIMESTAMP;
ALTER TABLE corporate_events ADD COLUMN revision_time        TIMESTAMP;
ALTER TABLE corporate_events ADD COLUMN resolved_security_id VARCHAR;
ALTER TABLE corporate_events ADD COLUMN issuer_name_raw      VARCHAR;
ALTER TABLE corporate_events ADD COLUMN ticker_raw           VARCHAR;
ALTER TABLE corporate_events ADD COLUMN unresolved_reason    VARCHAR;
ALTER TABLE corporate_events ADD COLUMN raw_payload_hash     VARCHAR;
ALTER TABLE corporate_events ADD COLUMN data_source_id       VARCHAR;
ALTER TABLE corporate_events ADD COLUMN research_eligible    BOOLEAN DEFAULT FALSE;
```

Deliberately **no `confidence`/`score` column** (ADR 0037 Decision 8 / trigger #5): any normalizer score rides in `payload`, structurally unreachable by eligibility or ranking until pre-registered and tested.

### 3.2 Fresh-DB schema (`store.py::_init_schema`)

Update the `CREATE TABLE IF NOT EXISTS` to include the eleven columns (plus the existing `ingested_at`) so a newly-created store matches a migrated one exactly. A fresh DB needs no ALTER; the migration script (§3.6) is a no-op on it beyond the view.

### 3.3 Column-explicit INSERT (mandatory)

Replace the positional insert in `upsert_events`:

```python
# before — breaks the instant a column is added:
self._con.execute("INSERT INTO corporate_events VALUES (?,?,?,?,?,?,?,?,?,?)", [...10...])

# after — names the columns it writes; new columns default NULL/FALSE:
self._con.execute(
    "INSERT INTO corporate_events "
    "(event_id, cik, ticker, event_type, source, accession, filed_at, event_date, payload, ingested_at) "
    "VALUES (?,?,?,?,?,?,?,?,?,?)",
    [...10...],
)
```

The Form-4 writer keeps writing exactly these ten fields; EAD normalizers (Phase 1) will use a separate write path that populates the new columns.

### 3.4 Compatibility view

```sql
CREATE OR REPLACE VIEW corporate_events_pit AS
SELECT *, COALESCE(available_time, filed_at) AS pit_time FROM corporate_events;
```

`ingested_at` is **not** in the COALESCE (ingestion can post-date availability on backfill — a look-ahead risk; ADR 0037 Decision 8). Legacy/ad-hoc readers may use `pit_time`; **EAD programs never do** — they read `available_time` directly via §3.5.

### 3.5 EAD read path — a new method, legacy method untouched

Rather than branch `events_asof` (and risk perturbing the insider path), add a sibling:

```python
def events_asof_eligible(self, as_of, *, event_type=None, ticker=None):
    """EAD PIT read: research-eligible events knowable by as_of, anchored on available_time.
    Enforces ADR 0037 Decision 8 — research_eligible AND available_time NOT NULL, no fallback."""
    conds = ["research_eligible = TRUE", "available_time IS NOT NULL",
             "CAST(available_time AS DATE) <= ?"]
    ...
```

`events_asof` (the insider path) is left exactly as it is. Small SQL duplication is the deliberate price of a zero-blast-radius guarantee.

### 3.6 Where the migration lives

A one-shot idempotent script `scripts/migrate_event_store_ead.py` (guards each `ALTER` with a column-exists check, since DuckDB has no `ADD COLUMN IF NOT EXISTS` across all versions), plus the `_init_schema` update for fresh DBs. Not Alembic — Alembic governs the SQLite trading DB, not this DuckDB research store.

---

## 4. Form-4 `available_time` backfill — the separately-signed-off migration

### 4.1 Acceptance-vs-dissemination characterization (ADR 0037 review point 1a)

`filed_at` is the SEC **acceptanceDateTime** (`ingest.py::_parse_acceptance`, `store.py:40`), stored UTC. For Form 4, acceptance ≈ public dissemination: EDGAR disseminates in real time **06:00–22:00 ET**. So acceptance time is a sound public-availability proxy, with two bounded caveats:

- **EDGAR's 17:30 ET filing-date convention** relabels the official *filing date* to the next business day for post-17:30 acceptances — but dissemination still occurs that evening, so the information *is* public the same calendar day. This is a bookkeeping artifact, not an availability lag; no correction needed.
- **True edge:** acceptance in the 22:00–06:00 ET window disseminates at 06:00 next day → `CAST(filed_at AS DATE)` can be one day early. Rare (filings are near-always accepted in business hours). At DATE granularity this is the only residual look-ahead.

**Decision for historical Form-4 backfill:** set `available_time = filed_at` verbatim. Rationale: (i) it is a sound proxy per the above; (ii) it makes `available_time` equal the value INSIDER-001 already reads, so any future `available_time`-based re-read of Form-4 data reproduces the existing study; (iii) we do **not** retroactively "correct" the rare overnight edge, because doing so would alter the historical evidence base for a sub-1-day, sub-1%-of-rows effect. New EAD datasets (government contracts) compute `available_time` from their true announcement/dissemination time going forward — they do not inherit this proxy.

### 4.2 Backfill statement + `research_eligible` default (review point 1b)

```sql
-- available_time proxy for the existing insider capability
UPDATE corporate_events SET available_time = filed_at
 WHERE event_type = 'insider_buy' AND available_time IS NULL;

-- eligibility is opt-in and requires a known resolution; unknown-mapping rows stay FALSE
UPDATE corporate_events SET research_eligible = TRUE
 WHERE event_type = 'insider_buy'
   AND available_time IS NOT NULL
   AND ticker IS NOT NULL;            -- a known security resolution for the row
-- every other row (incl. any ticker-less Form 4) keeps research_eligible = FALSE (the column default)
```

`research_eligible` **defaults FALSE** and never becomes true implicitly; a Form-4 row with no resolvable security stays FALSE (and, under CAP-024, will carry a typed `unresolved_reason` once the Security Master runs over it — out of scope for 0A).

### 4.3 Reversibility + result-invariance verification (the gate)

The backfill migration must:

1. **Be reversible.** Down-path drops the view, sets the eleven columns back to NULL/default (or, cleaner, restores from the pre-migration file copy taken in step 2). The script refuses to run without first writing a timestamped copy of the store file.
2. **Record pre/post counts.** Emit `research_eligible = TRUE` row count and total row count before and after; the PR captures both.
3. **Prove INSIDER-001 invariance.** Run `scripts/run_insider_reproduction.py` against the **pre-migration copy** and the **post-migration store** with identical args; assert the reproduction outputs (event set, entry dates, study statistics) are **identical**. A single differing value blocks the migration. This is the concrete form of ADR 0037's "no historical INSIDER-001 read changes its result."

---

## 5. Test plan (new/updated `tests/altdata/`)

- **`test_event_store_migration.py` (new):** build a store on the *old* schema (10-col), run the migration script, assert: all eleven columns exist + nullable; `research_eligible` default FALSE; `corporate_events_pit` view exists and `pit_time = filed_at` when `available_time` is NULL; a pre-migration `upsert_events` batch is byte-identical under `events_asof` post-migration (projection unchanged).
- **`test_event_store.py` (extend):** column-explicit INSERT still round-trips; `events_asof` unchanged; **`events_asof_eligible`** returns only `research_eligible=TRUE AND available_time NOT NULL` rows, filters on `available_time` (prove a row with `available_time` after `as_of` but `filed_at` before is *excluded* — the EAD PIT semantics), and excludes eligible-but-forward-dated rows.
- **`test_backfill_invariance.py` (new):** synthesize insider rows, snapshot `events_asof(...,'insider_buy')`, apply backfill, re-snapshot, assert equality — the unit-level mirror of §4.3's script-level proof.
- **Existing suites** (`test_ingest.py`, `test_validate.py`, `test_signal.py`) must pass unchanged — their green state *is* part of the invariance evidence.

Offline, laptop-safe (`pytest apps/backend/tests/altdata/`); no box, no live stack.

---

## 6. Sign-off checklist (ADR 0037 gate — owner)

- [ ] **Backfill rule** (§4.2): `available_time = filed_at` for historical Form-4; `research_eligible` opt-in, default FALSE — approved as the historical proxy.
- [ ] **Acceptance-vs-dissemination** (§4.1): the overnight-edge approximation is accepted (not corrected retroactively).
- [ ] **Reversibility + invariance** (§4.3): mandatory pre-migration file copy + the INSIDER-001 reproduction diff = green before apply.
- [ ] **Scope**: 0A touches only the offline DuckDB event store; no trading-DB / Alembic / box change.

On sign-off, Phase 0A implementation (store.py edits + `migrate_event_store_ead.py` + tests) proceeds as its own PR under walk-away discipline; the backfill runs only after the invariance diff is green.

---

## 7. What this unblocks

With the schema reconciled and eligibility columns live, **Phase 0B** (Security Master CAP-024, which populates `resolved_security_id` / `unresolved_reason`) and **Phase 1** (Quiver government-contract normalizer writing `available_time` + `research_eligible` via the EAD write path) have a target schema to write to — and `events_asof_eligible` is the read the GOVCONTRACT-001 study (Phase 2) consumes.
