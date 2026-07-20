# MR-002 Workstream C — SPQ-1 Phase 2B — Development-Period Signal-Production Qualification

## Increment 2B-0 — Run Specification (resubmitted after four corrections + SIC clarification)

**Status: 2B-0 run specification resubmitted.** First of the four Phase-2B increments (2B-0 spec →
2B-1 shard qualification → 2B-2 full run → 2B-3 reconciliation/closeout). Freezes the run identity and
binds every source + code identity and every policy **before any signal is produced**. No computation,
no candidate records, no performance.

## Adjudication corrections applied

1. **Complete identity binding.** Every SHA-256 field is now a full 64-char value (the truncated
   `phase2a_dev_snapshot_content_sha256` is now `211eacc0…1621d3ae2`); the generator **validates every
   identity against `^[0-9a-f]{64}$` (and commits against 40-hex) and refuses to write on any
   placeholder** before emitting artifacts.
2. **Guarded, ledgered 2B-0 reads.** The universe + sic_mapping identity reads now go through the
   Phase-2A `PartitionGuard` (authorize → read → `record_completed_read`) and are recorded in a
   dedicated **`MR002_SPQ1_Phase2B_2B0_OpenedObjectLedger_v1.0.json`** (2 completed reads: universe
   20,500 rows `2013-01-01..2019-10-01`, sic_mapping 110 rows; both within dev bounds; 0 validation/OOS
   objects). No direct unledgered source read remains.
3. **Exact universe row-set + frozen PIT membership rule.** The universe identity now hashes the
   **exact authorized governing-month set** (`universe_month between 2013-01-01 and 2019-10-01`, 82
   months), and the manifest freezes: `governing_universe_month(t) = max universe_month ≤ close(t)`;
   membership from that **single** month only; uniqueness key `(universe_month, permanent_security_id)`;
   missing month / duplicate row → `SECURITY_IDENTITY_AMBIGUOUS`; future month excluded; no pre-window
   seed required.
4. **Portable deterministic generator.** `ROOT = Path(__file__).resolve().parents[5]` — no workstation
   path in source discovery, module hashing, identity, or query. A test proves byte-identical artifacts
   from a different working directory.

**SIC-mapping effective-time rule frozen** (clarification): sector = the row whose inclusive
`[sic_start, sic_end]` contains the security's PIT SIC (from `sic_observations.accepted_utc ≤ close t`);
among covering rows, latest `effective_from ≤ close t` governs (NULL = always-effective); same-effective
conflict → `SECTOR_EFFECTIVE_DATE_CONFLICT`; missing SIC range → `SECTOR_PIT_IDENTITY_MISSING`; one ETF
per sector via `sector_etf`.

## Run identity

**Run ID:** `MR002-SPQ1-P2B-DEV-V1` (unchanged — no computation occurred) · **new run-specification
hash `10ffaf3a…`** (was `cf29d8d3`).

Artifacts: `run_spec/…RunSpecification…` (`c0f01b38`) · `manifests/…DevelopmentRunManifest…`
(`1fe35f1a`) · `manifests/…InputIdentityManifest…` (`3216c379`) ·
`evidence/…2B0_OpenedObjectLedger…` (`84a21ff8`).

## Bound source identities

| source | identity | role |
|---|---|---|
| `mr002_research.duckdb` | `24e5153c…` | prices / etf_prices / actions / crosswalk / universe / sic_mapping |
| `mr002_provenance.duckdb` | `f9908dbd…` | sic_observations / earnings_anchors |
| **`sic_mapping`** (registered) | content `c4e8c5e3…` (110 rows) | owner-countersigned SIC-range → sector → ETF |
| **development universe** | content `f638dfe3…` (20,500 rows) | monthly PIT membership, 540 permatickers, 82 months |

Prior chain bound: census `87602e7c` · rulings `d8a9071d` · schema `49c0e550` · Phase-1 valid-path
`c9ebd7f9` · Increment-3 `42c5cee0` · dev-snapshot `211eacc0` · dev-calendar `a7ec4f0f`. Producer and
adapter module SHA-256 are enumerated in the InputIdentityManifest.

## Two consequential bindings (recon-confirmed)

1. **PIT universe = the registered `universe` table** — monthly reconstitution (universe_month,
   permaticker, siccode, liquidity_rank, med_dv_60, in_long/short flags); **top-250 long / top-150
   short** per month (matching frozen §4), survivorship-free, PIT. Membership resolved per session by
   `universe_month ≤ session` — never a present-day list. **540 dev permatickers over 82 months.**
2. **SIC→sector→ETF = the registered, owner-countersigned `sic_mapping`** (reviewer Jay Wang,
   2026-07-11): SIC ranges → 11 research sectors → the 11 SPDR sector ETFs, with confidence and
   effective dates. **This supersedes the Phase-2A `pit_sector_adapter` division placeholder** (a
   one-sample stand-in) for the full-universe run; PIT-ness is carried by each SIC observation's
   `accepted_utc`.

## Frozen mechanics (unaltered)

`numpy.linalg.lstsq` (gelsd/SVD, float64, rcond `1e-10`) · 60-session OLS ending t−1 · R5 (5
consecutive ending t) · 60-obs normalization ending t−1, σ ddof=1 · warm-up 125 return / 126 price ·
ADV median(raw close × raw volume), 60 & 20 sessions ending t−1. No 2B work alters these.

## Frozen policies

- **Unit:** `permanent_security_id × decision_session` → exactly one terminal disposition
  (`SIGNAL_DECISION_RECORD_EMITTED` / `INELIGIBLE` / `INTEGRITY_STOP` / `REFUSED_CODE_OR_DATA_IDENTITY`);
  no silent drops.
- **Ordering:** canonical `(decision_session_ordinal asc, permanent_security_id asc)`.
- **Sharding:** contiguous session-ordinal blocks (units independent → shard-invariant after canonical
  merge); single-process == multi-shard == restart output.
- **Checkpoint/restart:** atomic per-shard completion, non-overwriting, resume from last completed
  shard, identical final manifest.
- **Failure:** any raw exception / unregistered refusal / reconciliation mismatch / post-dev row /
  validation-OOS reference → **STOP, no repair/tune/reinterpret**.
- **Eligibility:** close-t only; any post-close-t fact → `FUTURE_INFORMATION_DETECTED`.
- **Performance quarantine:** signal values are emitted but never ranked or interpreted; only
  implementation diagnostics (finite counts, refusal/coverage distributions) are permitted.

## Boundary

No computation in 2B-0. The partition guard remains mandatory for all downstream increments;
validation/OOS remain sealed and unread; ranking, portfolio, execution, performance, A/B/C, tuning,
order-path, and production remain NOT authorized. Commit / tree / parent SHAs and a clean-tree
confirmation accompany this submission.

**Next (on your ratification of this spec):** 2B-1 — dry-run + mechanically-selected shard
qualification against the shard-acceptance gate, then 2B-2 full run, then 2B-3 closeout.
