# MR-002 — Crawl-Ops Directive (owner, 2026-07-11) · Implementation Status

**Context:** the stage-2 EDGAR crawl filled its 40GB EC2 volume — the response cache reached 38GB over
~10k responses because plain urllib sent no `Accept-Encoding` and large submissions JSONs cached
uncompressed. Recovery: online EBS grow to 200GB + relaunch (pinned manifest + content-hash cache made
the resume cheap). The owner directed: **finish the current run unchanged; fix the design for every
future crawl; do not normalize the 200GB volume as the solution.**

## Before-next-crawl items — IMPLEMENTED (commit with this doc)

| Directive | Implementation (`mr002_stage2_edgar_crawl.py`) |
|---|---|
| `Accept-Encoding: gzip, deflate` + declared UA | added to every request; gzip transfer decoded via stdlib (no new deps) |
| Compress cached payloads at rest | cache entries written as `.gz` (level 6); reader accepts both `.gz` and legacy plain entries so existing caches stay usable; compressed/uncompressed byte counters recorded per response and in totals |
| Largest-cache-object report | `largest_objects_report(100)` — top-100 by on-disk size with URL (via the new `cache_index.jsonl`) and uncompressed size; embedded in the run report |
| Disk circuit breakers | in-worker `DiskGuard`: checked every 50 fetches; **< 20% free ⇒ stop accepting new downloads with a checkpointed, resumable halt** (single-threaded worker, so the first threshold is the effective breaker; the 10-minute external monitor observes only) |
| Error-body retention tier | failed requests log status + body **hash** + **first 4KB** only — auditability without multi-MB error pages |
| Idempotent, batch-friendly DB writes | `INSERT OR REPLACE` keyed by (cik, accession) retained; per-issuer transactional batches |

## Next engineering increment — REGISTERED (task, not yet built)

S3 content-addressed raw cache (`sha256/ab/cd/<hash>.json.gz` + manifest records with compressed/
uncompressed sizes; small local LRU only) · request-level durable checkpoint table
(PENDING/RUNNING/SUCCEEDED/FAILED + `db_committed_at`; resume queries unfinished rows only, no
issuer-level rescans) · staged bounded pipeline (fetcher → raw writer → parser → batch DB writer, one
global SEC rate limiter, backpressure) · retention tiers with lifecycle expiry.

## Final optimization — REGISTERED

**SEC nightly bulk ZIP as the historical baseline** (download once → checksum → archive → normalize →
bulk-load), with the per-company submissions API / daily index reserved for incremental additions.
This converts future full crawls into a one-time bulk import + small daily upserts.

## Cache-size verification note

38GB / ~10k responses ≈ 3.8MB average — consistent with uncompressed submissions + shard JSONs
(1–15MB each for large filers); ranged header fallbacks are 4KB. The top-100 report from the current
run will confirm empirically; the checklist of accidental-storage patterns from the directive
(duplicates, debug dumps, double-stored content, per-retry keys) is part of that review.

**Current run:** proceeding on the old fetcher per the owner's explicit instruction; its provenance
manifest fully records the disk-full window. The upgraded fetcher reads the existing cache, so any
future resume benefits immediately.

## Acceptance refinements (owner, 2026-07-11) — APPLIED

Commit 7355995 accepted for current-crawler hardening, **validation pending from the completed run
report**. Refinements implemented in the follow-up commit:

- **Hash identity split:** `content_sha256` = canonical uncompressed bytes (drives identity + the
  dual-hash rule — gzip metadata can never trip it); `storage_sha256` = compressed object bytes
  (storage integrity / ETag analogue). Both recorded per response and in the cache index.
- **Controlled-halt evidence:** the disk-guard trip record is `DISK_HEADROOM_GUARD` with free bytes +
  percentage, last completed URL, and a counter snapshot; the run report carries an explicit
  `termination_reason` (COMPLETED vs guard/stop) so a controlled halt is distinguishable from a crash.
- **Burst calibration:** the run report computes the worst observed 50-consecutive-response compressed
  burst; the check cadence must satisfy free > burst + decompression allowance + DB/WAL allowance +
  safety reserve (re-evaluated against the top-100 report; per-download checks if a few large objects
  dominate).
- **Append-safe cache writes:** tmp object → fsync → atomic rename → index append → index fsync — a
  crash cannot leave a valid cache object without an index entry (nor a torn object).
- **Task #9 re-sequenced per the owner:** checkpoints → S3 cache → bulk-ZIP baseline → staged pipeline
  (fetch workers share ONE global SEC limiter) → local LRU. Checkpointing precedes concurrency. The
  future manifest is SQLite/PG for lookups with JSONL exported as the audit artifact.

**Completion-evidence checklist for the run report (owner):** no further disk-headroom breaches ·
compressed-vs-uncompressed byte ratio · top cache objects + endpoint distribution · successful
legacy-cache replay · failure bodies capped at 4KB · final issuer/accession counts · zero duplicate
database rows · every disk-full-window failure recovered or explicitly unresolved.

## Validation-scope correction (owner, 2026-07-11) + post-completion sequence

**Correction accepted:** the in-flight run executes the PRE-hardening fetcher, so it cannot validate
the 4KB error-body cap or DISK_HEADROOM_GUARD behavior — historical failure artifacts are inspectable
but are NOT presented as validation of the new controls. **Those two items belong to the first
hardened-run acceptance test.**

**Post-completion sequence (owner-ordered):** 1) reconcile every failure in the disk-full window ·
2) verify final database counts + uniqueness (zero duplicate rows) · 3) generate the reconstructed
top-100 report (URL keys recomputed from the response manifest) · 4) terminate the expanded instance
only after artifacts are durably copied · 5) run the **hardened smoke crawl**
(`mr002_hardened_smoke.py`) before the next full production crawl.

**Smoke coverage (deliberate tests, per the owner):** gzip cache creation · legacy cache reading ·
content-vs-storage hash separation · capped (≤4KB) error retention · controlled disk-guard
termination (forced via the MR002_DISKGUARD_FORCE_FREE_PCT hook → exit 3 + partial run report with
termination_reason=DISK_HEADROOM_GUARD — plumbing added so a controlled halt is distinguishable from
a crash IN THE ARTIFACTS) · resumption from cache, with exact request-level resumption recorded as
PENDING_TASK9 until the checkpoint table lands (checkpoints precede concurrency). The smoke run
shares the single SEC limiter budget — never run concurrently with a production crawl.
