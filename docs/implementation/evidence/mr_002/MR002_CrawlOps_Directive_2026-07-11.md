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
