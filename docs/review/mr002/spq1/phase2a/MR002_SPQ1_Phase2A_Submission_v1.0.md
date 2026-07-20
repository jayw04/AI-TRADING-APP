# MR-002 Workstream C — SPQ-1 Phase 2A — Development-Data Source & Adapter Qualification (v1.0)

**Status: resubmitted after the five adjudication corrections.** LIMITED REAL-DATA INTEGRATION —
development partition only.

## Adjudication corrections applied (five)

1. **Future crosswalk rows excluded + no clamping.** The dev snapshot now PIT-bounds the crosswalk
   (`effective_from <= DEV_END`); the identity adapter maps effective dates with a **frozen on-or-after
   session rule** (never at-or-before clamping), retains pre-window rows explicitly as `PRE_WINDOW`,
   and refuses a post-window effective date → `SECURITY_IDENTITY_AMBIGUOUS`. A post-`DEV_END` ticker
   change / merger can no longer become a last-development-session event.
2. **Governed calendar hash enforced.** `load_calendar` verifies the frozen **dev-calendar SHA-256**
   (`a7ec4f0f…`) — a missing / inserted / reordered session at the same 1700 count is rejected. The
   full governed 3400-session hash (`b873421…`, covering dev+val+OOS) is **not recomputable within the
   dev-only boundary**, so it is bound as a Phase-2B/validation-time reference; the dev-calendar
   sub-hash is the enforced dev-only control.
3. **Opened-object ledger records actual reads.** `PartitionGuard` splits `authorize_read` from
   `record_completed_read`; each entry carries the object SHA-256, declared range, executed query,
   **actual row count, actual min/max date, result-set hash, and COMPLETED status**. A returned row
   beyond the authorized bounds fails closed; a pre-read authorization alone is never recorded.
4. **Unknown relationship type fails closed.** The identity adapter refuses an unrecognized
   `relationship_type` → `SECURITY_IDENTITY_AMBIGUOUS` (no corporate-action fallback).
5. **Benchmark completeness + bound parameters.** The SPY adapter asserts completeness (missing
   sessions → `SIGNAL_INPUT_IDENTITY_MISMATCH`); snapshot queries use bound parameters, not string
   concatenation.

The dev-snapshot content hash is **unchanged** (`211eacc0…`) — the corrections tighten integrity
without altering the sampled content.

## Original scope

Read-only adapters bind the registered MR-002 **development** partition (frozen
`2013-01-02 → 2019-10-02`, 1700 governed sessions; the full `governed_session_list_sha256 b873421…`
covers dev+val+OOS and is a Phase-2B reference) to the qualified Phase-1 typed inputs. No
performance metric is computed, retained, or interpreted; the Phase-1 conversion is a schema-compat
check only, and any incidental z-score is an unexamined implementation artifact.

## Registered sources (immutable, local; no live vendor pull)

| source | sha256 | role |
|---|---|---|
| `apps/backend/data/mr002_research.duckdb` | `24e5153c…` | prices (V3), etf_prices (SPY+11 sectors), crosswalk, SIC, actions, universe |
| `apps/backend/data/mr002_provenance.duckdb` | `f9908dbd…` | PIT `sic_observations.accepted_utc`, `earnings_anchors` (acceptance_utc, BMO/AMC, amendments) |

`mr002_research.duckdb`'s hash `24e5153c` is the registered snapshot session index named in the
governing preregistration.

## Partition isolation (technically prevented — your ratified choice)

The registered DBs physically span 2010→2026 (they contain sealed validation+OOS rows). Adapters
therefore **never** open them. A hash-bound **development-only snapshot** (`content_sha256 211eacc0…`)
is materialized once — through the mandatory `PartitionGuard`, logging every read — containing only
rows within `[2013-01-02, 2019-10-02] ∩` the sample, and adapters read **exclusively** that snapshot.
The guard fails closed `INTEGRITY_STOP:FORBIDDEN_PARTITION_ACCESS` (new registered Phase-2 code) on
any out-of-bound range, unregistered object, or path traversal. The opened-object ledger records 6
reads, **all DEVELOPMENT, all within dev bounds, no validation/OOS object opened**.

## Eight domains qualified (real dev data)

Calendar (1700 sessions, dates + ordinals + registered ET policy — no fabricated intraday
timestamps) · permanent-security identity/lineage (crosswalk; ticker-rename continuity vs
merger/share-class separation) · V3 price series (closeadj/closeunadj/close/open/volume, proven
**not interchangeable**) · SPY benchmark (no fallback) · sector-ETF proxies (frozen sector→ETF map) ·
**PIT sector** (`accepted_utc`; latest-available-by-cutoff governs, future-published excluded,
missing → INELIGIBLE) · **earnings/event eligibility** (acceptance_utc availability; post-cutoff →
`ELIGIBILITY_EVIDENCE_MISSING`) · dollar-volume (raw close × raw volume, delegated to frozen Phase-1
median).

## Preregistered mechanical sample

Frozen by structural coverage **before inspecting any signal**: AAPL (ordinary, 1700/1700), SPY+XLK
(complete history), cik 320193 (PIT sector + earnings), crosswalk relationship types (rename /
share-class / succession). Categories with **no natural dev-slice instance** — earnings amendment
(`is_amendment_origin=0`), same-timestamp sector conflict (`sic_conflicts=0`), missing official
next-open (EOD data / execution-layer concept) — are noted honestly and qualified by the closed
Phase-1 resolver logic, **not fabricated** into the slice.

## Qualification results

| item | result |
|---|---|
| Phase-2A tests | **26 passed** (16 real-data + 10 DB-independent units) |
| branch coverage (adapters) | **92%** |
| ruff / mypy | clean / clean |
| Phase-1 tests | **48 passed** (unchanged) |
| evaluator + Increment 1–3 + OQ-1 | **152 passed** (unchanged) |
| Increment-3 accepted hash `42c5cee0` | unchanged |
| Phase-1 valid-path determinism `c9ebd7f9` | unchanged |
| dev-snapshot content hash | `211eacc0…` (stable across re-materialization) |
| opened-object ledger | 6 reads, all DEVELOPMENT, no validation/OOS object |
| performance artifact generated | none |

## Artifacts (this directory)

`SourceRegistry` · `DevelopmentPartitionManifest` · `AdapterManifest` · `PITAvailabilityReport` ·
`IdentityCoverageReport` · `FieldIdentityReport` · `RefusalCoverage` · `DeterminismReport` ·
`OpenedObjectLedger` · `QualificationReport` · this submission. Generator: `_gen_phase2a_artifacts.py`
(the materialized snapshot is reproducible from the registered sources and is not retained in git).

## Boundary held

Development partition only; no full-period signal run, candidate census, cross-sectional ranking,
portfolio construction, execution replay, performance/Sharpe/DSR, A/B/C comparison, validation, OOS,
order-path, or production. Validation/OOS remain sealed and unread. Commit / tree / parent SHAs,
changed-file list, clean-tree confirmation, source registry / partition manifest / adapter manifest
SHA-256, the opened-object ledger, and the no-validation-OOS + no-performance proofs accompany this
submission.
