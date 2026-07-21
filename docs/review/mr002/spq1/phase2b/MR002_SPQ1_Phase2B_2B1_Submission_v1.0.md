# MR-002 Workstream C — SPQ-1 Phase 2B — Increment 2B-1

## Dry-Run & Limited-Shard Qualification (resubmitted; third correction round)

### Third-round corrections (final integrity)

- **Resolved-unit uniqueness.** `UnitResult` now exposes `request_key = (session, symbol)` (enumeration)
  and `terminal_key = (session, permanent_security_id)` — identity failures use
  `(session, "UNRESOLVED:symbol")`. `merge` fails closed on a duplicate request unit **and** on a
  duplicate **resolved** `permanent_security_id × session` (the frozen logical unit); `reconcile`
  reports both `duplicate_request_keys = 0` and `duplicate_resolved_permanent_security_session_keys = 0`.
  Canonical ordering is by request key (input-symbol-order-independent). Tested: two symbols → same
  permanent id on one session is rejected; identity failure yields one UNRESOLVED disposition (no silent
  drop); merge is order-invariant.
- **Complete consumed-field price/factor ledger.** Each per-symbol price completed-read now binds, in
  canonical session order, `[session, closeadj, closeunadj, volume, status]` (exact `float.hex()`), so a
  change to raw close, volume, or missingness alters the hash (was `closeadj` only). SPY now binds
  `[session, value]` rows (sector-ETF rows already carry `(ticker, date, value)`). Tested: mutating any
  of closeadj / closeunadj / volume / status changes the hash; unchanged data reproduces it; row order
  is canonicalized.



### Second-round corrections (PIT identity + ledger)

- **Per-session permanent-security resolution.** `run_unit` now resolves
  `permanent_security_id = lineage.resolve_permanent_id(symbol, decision_session)` **at t** (was
  `len(cal)-1`). Enumeration is keyed by `(session, symbol)`; identity is a per-session fact. Ambiguity
  affects only the sessions where it holds. Unit-tested across a boundary.
- **Per-session, PIT CIK resolution.** New `resolve_cik_at(cik_timeline, t)` replaces the unordered
  `LIMIT 1` — it selects the crosswalk CIK whose `[effective_from, effective_through)` interval contains
  t; overlapping intervals with conflicting CIK → `SECURITY_IDENTITY_AMBIGUOUS`. TRV (cik 831001 eff
  1986–1998, 86312 eff 2007–) resolves to **86312** in dev, the predecessor interval correctly excluded
  (unit-tested; row-order-independent via `= ANY`).
- **SIC read matches the amended contract.** `sic_observations` is read as
  `(cik, accepted_utc, sic, accession)`; the **full UTC timestamp** is preserved (not date-truncated);
  a same-acceptance-time pair with conflicting SIC → `SECTOR_EFFECTIVE_DATE_CONFLICT`; exact duplicates
  dedupe; the completed-read hash binds all four fields + the full timestamp.
- **Complete Phase-2B read ledger.** The development snapshot is registered as a guarded object and
  every bulk read (calendar, SPY, sector ETFs, crosswalk, per-symbol prices, earnings) is recorded as a
  completed read with row count / range / query identity / result hash — bounded bulk reads (not
  per-unit), sized for 2B-2. Earnings are bulk-loaded (in-memory checks per unit).

Real-data dispositions now span all four classes: **EMITTED + INELIGIBLE (warm-up,
ELIGIBILITY_EVIDENCE_MISSING) + INTEGRITY_STOP (SECURITY_IDENTITY_AMBIGUOUS)**, plus synthetic
supplementary sentinels (OLS_WINDOW_INCOMPLETE, SIGNAL_INPUT_IDENTITY_MISMATCH, SECTOR_PIT_IDENTITY_
MISSING) with searched-population disclosure.

### First-round corrections applied

1. **PIT-sector source amendment (2B-0).** A controlled 2B-0 amendment now freezes the registered PIT
   sector source as **`research.sic_observations`** (DB `24e5153c…`; columns cik/accepted_utc/sic/
   accession; upper bound `accepted_utc ≤ DEV_END`; pre-window seeds allowed; uniqueness
   `(cik, accepted_utc, accession)`; same-acceptance conflict → `SECTOR_EFFECTIVE_DATE_CONFLICT`;
   coverage 534/535; missing covered cik → `SECTOR_PIT_IDENTITY_MISSING`), guarded + ledgered like every
   input. RunSpecification / DevelopmentRunManifest / InputIdentityManifest regenerated; **run-spec hash
   `10ffaf3a` → `96a3ee48`** (Run ID unchanged, no full run occurred).
2. **Decision cutoff = registered ET close via `zoneinfo`.** Replaces the fabricated fixed `21:00Z`
   with 16:00 America/New_York → UTC (**21:00Z standard / 20:00Z daylight** per historical date),
   closing the DST leakage channel (summer 4–5pm ET evidence). Tests cover winter/summer/DST-transition
   and the 20:30Z-summer boundary.
3. **Structural shard coverage expanded** (frozen before signal inspection): now demonstrates
   **real** `INTEGRITY_STOP:SECURITY_IDENTITY_AMBIGUOUS` (FLT dual-cik lineage), **real**
   `INELIGIBLE:SECTOR_PIT_IDENTITY_MISSING` (EVI, cik absent from sic_observations), ticker-change
   (FLT chain), IPO/warm-up (TWLO), and earnings-cutoff (AAPL), plus **synthetic supplementary**
   sentinels for `OLS_WINDOW_INCOMPLETE` and `SIGNAL_INPUT_IDENTITY_MISMATCH`. Classes with **0 real dev
   instances** (halt/absence, same-timestamp sector conflict) disclose the searched population + rule.
4. **Phase-2B execution-code identity bound.** The amended 2B-0 manifests bind
   `phase2b_orchestration_code_identity` (SHA-256 of `__init__/cutoff/sic_sector/orchestrator`); the run
   verifies its own module hashes and refuses on drift. Closed Phase-1 identities are untouched.

**Status: resubmitted.** The accepted producer runs over a
mechanically-frozen shard set of real development units, proving the terminal-disposition contract,
determinism, shard/restart/merge invariance, PIT sentinels, and isolation. It **stops before the full
~1.3M-unit 2B-2 run**. Uses the ratified run identity (`MR002-SPQ1-P2B-DEV-V1`, run-spec
`10ffaf3a…`) unmodified. No signal value is ranked or interpreted (only dispositions + record
identities are retained).

## New engine (no closed module modified)

All 2B-1 code lives in a new `apps/backend/app/research/mr002/spq1/phase2b/` package (orchestrator +
`sic_sector` resolver), kept **out of** the `spq1/` and `spq1/adapters/` directories the ratified 2B-0
InputIdentityManifest hashes — so every bound module identity is unchanged (2B-0 identity tests still
pass). It binds the **registered owner-countersigned `sic_mapping`** for SIC→sector→ETF (superseding
the Phase-2A placeholder) without editing any closed code.

## PIT sector source finding

The Phase-2A dev snapshot copied `sic_observations` from the **provenance** DB, which covers only **13
ciks** (a curated Phase-2A sample). The registered PIT sector source for the development run is
**`research.sic_observations`** (covers **534/535** dev-universe ciks) — so the orchestrator reads
sector observations from research (guarded, dev-bounded, ledgered). This is recorded in the RunManifest.

## Frozen shard selection (structural; no signal inspection)

6 securities (AAPL/MSFT/INTC/BAC/XOM by liquidity + sector diversity; TWLO for the IPO/warm-up case)
× 4 session-block shards (early-dev warm-up, middle-dev, late-dev, IPO region) → **144 units**.
Universe count is a constant top-250/month (high==low; recorded, not a selector). No natural
halt/absence or same-timestamp-sector-conflict instance in this slice (noted, not fabricated).

## Results

| item | result |
|---|---|
| units | **144** — 84 `SIGNAL_DECISION_RECORD_EMITTED` (all ELIGIBLE), 60 `INELIGIBLE` (warm-up) |
| one terminal disposition / unit | ✔ (reconciles; 0 duplicate, 0 missing, 0 orphan) |
| repeat-run byte-identical | ✔ | single == multi-shard (canonical merge) | ✔ | restart-identical | ✔ |
| completed-shard overwrite blocked | ✔ (atomic, non-overwriting) |
| PIT sentinel (post-cutoff sector obs) | cannot alter close-t sector ✔ |
| unknown refusal codes / deprecated emissions | 0 / 0 |
| validation/OOS objects opened | **0** (opened-object ledger, all COMPLETED, within dev bounds) |
| performance artifacts | none (dispositions + identities only) |
| **acceptance gate** | **all pass** |
| Phase-1 tests / determinism `c9ebd7f9` | 48 unchanged / unchanged |
| evaluator + Increment 1–3 + OQ-1 / hash `42c5cee0` | 152 unchanged / unchanged |
| 2B-0 ratified identity | unchanged (phase2b/ not among the hashed module dirs) |

## Artifacts (13, this directory)

ShardSelection · RunManifest · InputIdentityManifest · OpenedObjectLedger · UnitReconciliation ·
SessionCensus · SecurityCensus · RefusalCensus · PITLeakageAudit · ShardInvarianceReport ·
RestartReport · QualificationReport · PublicationManifest. Canonical merge hash
`39cb493e…` (in ShardInvarianceReport). New code: `phase2b/__init__.py`, `phase2b/sic_sector.py`,
`phase2b/orchestrator.py`; 5 new qualification tests. Generator: `_gen_phase2b_1_run.py` (portable).

## Boundary

Limited-shard only. The full development run (2B-2), ranking, portfolio, execution, performance,
A/B/C, tuning, validation, OOS, order-path, and production all remain **NOT authorized**. Awaiting your
adjudication of the 2B-1 acceptance gate before 2B-2.
