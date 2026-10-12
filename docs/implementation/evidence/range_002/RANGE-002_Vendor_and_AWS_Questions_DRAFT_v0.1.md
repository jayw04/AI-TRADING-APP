# RANGE-002 vendor storage and AWS-use questions — DRAFT for the owner to send

| Field | Value |
|---|---|
| Status | **DRAFT. NOT SENT.** The owner sends; no vendor or AWS contact has been made and no data has been fetched. `[MERGE NOT APPROVED]` |
| Default | **DENY.** Any unanswered question below keeps the corresponding fetch/storage action denied (see the record template in the same directory). |
| What each answer unblocks | Step 3 of the preparation chain: fetch authorization. Nothing here authorizes a fetch by itself. |

Evidence already on record (so questions are not asked twice): Alpaca's published pages state history "since 2016", 200/min (Basic) and 10,000/min (Algo Trader Plus) historical calls, `raw` default adjustment and the `asof` symbol-mapping parameter. They are **silent** on storage, caching, derived data, research use, cloud hosting, delisted symbols, and rate-limit scope. The Customer Agreement section "Use of Market Data" forbids reproducing, distributing or commercially exploiting data without written consent. Sharadar's documentation lists the `TICKERS` columns (primary key `table, permaticker, ticker`) and calls the table a snapshot; it does not state how historical ticker intervals, reuse or symbol changes are represented.

## A. Questions for Alpaca (Market Data)

| ID | Question (send verbatim) | Why it matters | Unblocks | If unanswered |
|---|---|---|---|---|
| ALP-1 | May we **store a local copy** of historical 1-minute SIP bars obtained through the Market Data API for **internal research and backtesting**, and for how long may we retain them? | The docs are silent; the Customer Agreement restricts "reproduce". | Any storage of fetched bars | DENY storage |
| ALP-2 | May that copy reside on **our own AWS infrastructure** (we will state the account and region)? | Hosting location is unstated. | Writing fetched bars to AWS | DENY |
| ALP-3 | May **statistics and reports derived** from the data (aggregates that do not reconstruct the bars) be shared with an **independent validator and outside reviewers**? | The validator must be able to see results. | Validator access to outputs | DENY sharing |
| ALP-4 | Are bars for **delisted and renamed symbols** retrievable, under which symbol (historical or current), and how does `asof` behave for a symbol that no longer exists? | Survivorship coverage is not stated. | Delisted-name coverage claim (F2) | Coverage stays UNKNOWN |
| ALP-5 | Is the 10,000 calls/min historical limit applied **per API key, per account or per endpoint** for our entitlement? | Scope is not stated. | Fetch-plan sizing | Plan at the lowest published rate |
| ALP-6 | Is each bar timestamp the **start** of its one-minute interval, in UTC, for the stocks bars endpoint? | The reference page does not state it; the kernel accepts start-stamped bars only. | Timestamp convention verification | Verify empirically before any use |
| ALP-7 | Does our use (an LLC running its own research and paper trading) affect our **subscriber classification** or the entitlement terms for SIP data? | The agreement distinguishes non-professional subscribers. | Entitlement reference | DENY |

## B. Questions for Sharadar / Nasdaq Data Link (identity history)

| ID | Question (send verbatim) | Why it matters | Unblocks | If unanswered |
|---|---|---|---|---|
| SHA-1 | Does a current pull of `SHARADAR/TICKERS` (`table=SEP`) carry **historical ticker intervals** per `permaticker`, or only the current ticker? What do `relatedtickers`, `firstpricedate` and `lastpricedate` denote per row? | Determines whether overwritten issuer history can be reconstructed from a pull. | Retention decision | RETAIN stays undecided |
| SHA-2 | How is a **ticker reused by a different company** after the first delisted represented in `TICKERS`, `SEP` and `ACTIONS`? | Reuse must not be collapsed. | Identity design | SCOPE_AMENDMENT |
| SHA-3 | How is a **symbol change** represented (is history re-keyed to the new ticker), and what are the exact `ACTIONS` action strings for ticker changes, listings and delistings? | `ACTIONS` is ticker-keyed with no `permaticker`. | Interval reconstruction | SCOPE_AMENDMENT |
| SHA-4 | May we **retain the raw `TICKERS` and `ACTIONS` rows** (with intervals) in our research store on AWS under our subscription? | Retention of raw rows is the remedy for the collapsed grain. | Storing raw identity rows | DENY |
| SHA-5 | Is there any **point-in-time / vintage** mechanism beyond `lastupdated`? | A snapshot cannot be backdated. | PIT claim wording | No PIT claim |

## C. AWS-use questions (answered by the owner / operator, not a vendor)

| ID | Question | Answer format |
|---|---|---|
| AWS-1 | Which **AWS account** (id) will hold any fetched or derived data? | 12-digit id |
| AWS-2 | Which **region**? | region code |
| AWS-3 | Which **service** and resource (for example one S3 bucket with Object Versioning, or the existing box)? | service + resource reference |
| AWS-4 | **Data class** of each object: vendor-licensed market data / vendor-licensed identity rows / derived aggregates / evidence. | one class per prefix |
| AWS-5 | **Retention** and deletion (matching ALP-1 / SHA-4)? | duration or "until vendor term ends" |
| AWS-6 | **Access:** which principals may read; is the validator given access to raw data or only derived outputs (ALP-3)? | role list |
| AWS-7 | **Integrity:** checksum and Version-ID pinning per GITHUB-OPS-001; encryption at rest? | yes/no + key reference |
| AWS-8 | **Who creates the resource**, and which dated owner record in Git authorizes it? | person + record path |

Reminder: AWS resource creation or use is withheld until a dated owner record exists in Git. These are questions, not requests to create anything.

## D. How the answers are used
Answers are copied, with the document reference and date received, into `RANGE-002_Fetch_Authorization_Record_TEMPLATE_v0.1.json`. `fetch_authorization_check.py` returns **DENY** unless every field is present and every required permission is an explicit `true`. Even `ALLOW` from the checker is only "the record is complete": it is not an authorization until the owner commits it as a dated record.

---

## E. Resolution status (round 4): what is and is not established

Successful API access is **not** evidence of permitted storage or of complete historical coverage. The earlier return-blind probe (counts only, nothing stored) showed bars were *returned* for sampled dates; it established nothing about the four items below.

| Item | Status | Evidence | Closes with |
|---|---|---|---|
| Permitted historical-data storage and AWS research use | **NOT ESTABLISHED. DENY.** | Alpaca pages are silent on storage, caching, derived data, research use and hosting; the Customer Agreement section "Use of Market Data" forbids reproducing/distributing without written consent. | ALP-1, ALP-2, ALP-3, ALP-7 answered in writing |
| Delisted / renamed-symbol retrieval and identity behaviour | **NOT ESTABLISHED.** | Alpaca documents `asof` (default = current day) for symbol mapping and is silent on delisted symbols. Sharadar documents `TICKERS` PK `(table, permaticker, ticker)` and calls it a snapshot; reuse, symbol-change re-keying and `ACTIONS` action strings are not stated. | ALP-4, SHA-1..SHA-3 answered, then the Stage 0/1 probes below |
| Actual subscription / request limits | **PARTIAL.** | Published: 200/min (Basic), 10,000/min (Algo Trader Plus). **Not established:** which plan the key holds, and whether the limit is per key, account or endpoint. | ALP-5, ALP-7; the plan name from the owner's account page |
| Historical issuer intervals for PIT construction | **NOT ESTABLISHED.** | The live store's `tickers` is `PRIMARY KEY(ticker)` loaded with `INSERT OR REPLACE` (code-derived), so overwritten history is not recoverable from it; a current `TICKERS` pull has not been shown to contain intervals. | SHA-1..SHA-4 and the Stage 0 probe |

**Authorization stays DENY** (see the template record and `fetch_authorization_check.py`) until the answers support permission. The checker returning ALLOW would still not be an authorization.

## F. Approved snapshot handoff (Sharadar store) — for the approved operator route

Creating an export from the production store **is production access**, even when an approved operator performs it. This is a separate request from, and does not retry, the earlier denied read.

1. **Route:** the approved operator only. The agent does not touch production. No stopping or quiescing of trading services unless separately authorized.
2. **Consistency:** every table exported from one read transaction (DuckDB `EXPORT DATABASE (FORMAT PARQUET)` or equivalent) so cross-table consistency is preserved. DuckDB will not open a file a writer holds, so the operator chooses: export from the owning service's own connection, or at a verified moment with no writer. Do not copy an active `.duckdb` or its WAL file.
3. **Tables and columns the PIT logic reads:** `tickers` (all columns including `permaticker`, `ticker`, `category`, `isdelisted`, `firstpricedate`, `lastpricedate`, `lastupdated`); `sep` (`ticker`, `date`, `close`, `closeunadj`, `volume`; `closeadj` optional); `actions` (all columns); `ingest_runs` and `dataset_coverage` for provenance.
4. **Raw identity rows:** if the raw vendor `TICKERS` rows (all `table` values, per-row intervals) were retained at ingest, export them as well. Code review found no retained raw payload. **A current `TICKERS` pull must not be assumed to reconstruct overwritten history**; that is what the Stage 0 probe tests.
5. **Provenance to return (manifest `range002.snapshot_manifest.v1`):** source and path, extraction time (UTC), per-table rows, min/max dates, columns, SHA-256 per file **of the bytes delivered**, S3 object Version ID if S3 is used, and the consistency basis.
6. **Destination and use:** controlled storage, Version-ID pinned (GITHUB-OPS-001); read-only RANGE-002 feasibility analysis. Licence-permitted retention is unresolved (section E).
7. **After receipt:** run `pit_coverage_ro.py` read-only; treat ticker-level aggregates as diagnostics only. PIT construction must resolve issuer identity over effective intervals. A repeated permanent id is a rename *candidate* only after a temporal (non-overlap) check.

## G. Smallest real-data fetch scope — FOR REVIEW. NOT EXECUTED. NOT AUTHORIZED.

Each stage is conditional on the previous stage's evidence and on a dated owner record. Output is **counts, labels and timestamps only; nothing is stored**, matching the earlier return-blind probe. Symbols and months are chosen by the owner/operator, not by the agent.

| Stage | Question it answers | Request | Count | Stored? | Precondition |
|---|---|---|---|---|---|
| 0 Identity metadata probe (Sharadar) | Do `TICKERS` rows for known renamed/reused/delisted tickers carry historical intervals? (feeds `RETAIN_RAW_INTERVALS` vs `SCOPE_AMENDMENT`, pre-registered in #760) | `TICKERS` (`table=SEP`) and `ACTIONS` filtered to ≤ 25 owner-chosen tickers | 2 to 4 calls | No | SHA-1..SHA-3 answered; owner record |
| 1a Intraday pilot (Alpaca) | Timestamp convention, `adjustment=raw`, pagination, field set | 1 owner-chosen symbol, 1 month inside `development_selection` (2016-01-01..2019-12-31), `feed=sip`, `adjustment=raw`, explicit `asof` | ≤ 3 | No (in-memory counts) | ALP-6; entitlement confirmed |
| 1b Delisted behaviour | Is a delisted symbol retrievable, under which symbol? | 1 owner-chosen delisted symbol, 1 month, with and without `asof` | ≤ 6 | No | ALP-4 asked |
| 1c Rename behaviour | Does `asof` link pre/post-rename data? | 1 owner-chosen renamed symbol, 1 month on each side of the rename date | ≤ 6 | No | ALP-4 asked |

Totals: at most about 20 calls, far below any published limit. **Not in scope:** bulk history, the N=100 universe, any storage of bars, holdout dates (2022-2025), the exposed 2026-01..07 window, or any price/return value in the output.

**Exposure note:** Stage 1 touches development-partition dates. It is return-blind, but the D01 exposure ledger / contact audit must record it before it runs.

**Dependencies still preventing real-data use:** vendor storage answer (ALP-1/2), the owner's authorization record in Git, the validator seeing the worksheet before any probe output exists, and the exposure-ledger entry.
