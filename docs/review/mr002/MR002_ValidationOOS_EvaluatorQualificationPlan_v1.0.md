# MR-002 Validation/OOS Evaluator Qualification Plan v1.0 (Workstream B)

**Scope:** the SEPARATE engineering workstream to build and qualify the full MR-002 validation/OOS
evaluator. **Not started in the governance turn.** It runs entirely on synthetic and
development-free fixtures — producing NO development, validation, or OOS performance — and must be
accepted before the owner authorizes the validation opening. This plan is the acceptance contract;
it reads no sealed data.

## 0. Relationship to the governance package

The preregistration v1.0-RC1 (`399e3b53…`) + decision record (`9a3a058c…`) FREEZE the windows,
gates, estimator, bootstrap, thresholds, seam rule, and dispositions. This workstream produces the
**executable** that implements exactly those frozen rules and proves it on synthetic fixtures. No
rule may be changed here; a needed rule change returns to governance.

## 1. What already exists (identity-tested, committed)

- `evaluator_prototype/mr002_valoos_metrics_prototype.py` (`62d10e50…`) — §7 Sharpe + §8 moving-block
  bootstrap + §9 diff primitives; imports numpy only; reads no data. **11/11 synthetic tests pass**
  (`test_…prototype.py` `082f7089…`, log `c7b352d1…`).
- `evaluator_prototype/mr002_session_index_extraction.py` (`908de368…`) — the narrow session-date
  extraction (metadata only); output `a0218e87…`.

These are metric/calendar primitives — **not** the evaluator.

## 2. Components to build (each with synthetic-fixture correctness)

1. **Portfolio replay** — the registered residual-reversion cascade producing per-session config-B
   target positions (dollar/sector/beta-neutral; entry |z|≥z_entry & extreme decile; 5-session max
   hold + exit ladder; next-open execution; 1.5%-NAV new-entry cap; 2% ADV clip). Bound to the
   registered numerical code identity (commit/tree/container/lock; pandas-ta transplant provenance
   carried).
2. **Cost model (D-COST)** — 10 bps/side, 50 bps/yr borrow ÷360, $10M NAV, 2% ADV clip-never-delay,
   1.5% new-entry cap, next-open execution, no forward-fill — as a committed file bound by
   version + sha256.
3. **Benchmark (D-BENCH)** — zero; excess = net return; all financing/costs in net P&L.
4. **Metric + gate battery** — Sharpe (frozen estimator), Calmar, MaxDD, positive-folds, cost-stress
   2×, A/C stability, profit/regime concentration, capacity, trades — each a frozen implementation
   with a synthetic fixture of known answer.
5. **PBO (CSCV)** and **DSR** — exact split count `S`, ranking metric, partition enumeration (PBO);
   deflated-Sharpe estimator, N=3 trials, skew/kurtosis, tolerances (DSR).
6. **Report schema** — immutable per-window record: record_type, window, disposition ∈ {PASS, FAIL,
   REFUSED, INTEGRITY_STOP}, every gate value + CI, seed, code/data/image identities, hashes.
   Output paths `.../valoos/<window>/MR002_ValOOS_<window>_Report.json` + a no-overwrite publication
   wrapper (Run-5 pattern: exclusive create, exit↔disposition validation, locked hashes).
7. **Identity + refusal layer** — refuse on any commit/tree/image/data-manifest mismatch
   (`REFUSED_CODE_OR_DATA_IDENTITY`) BEFORE any window read; enforce the §10 hard-stop codes.

## 3. Synthetic-fixture qualification (no real data)

- Every metric/gate has a synthetic input with a closed-form or hand-verified answer (as the
  metric prototype already demonstrates for Sharpe/bootstrap).
- A synthetic end-to-end run (fabricated positions + fabricated prices) produces a full report with
  a deterministic disposition — reading no real returns.
- Identity tests prove refusal on wrong commit/tree/image/data-manifest.
- Determinism: same fixtures + seed 42 ⇒ bit-identical report.
- Coverage-denominator logic tested on a synthetic universe of known cardinality.

## 4. Binding required before ANY validation access (D-COST + correction 16)

commit + tree · container digest · dependency lock · data-manifest identity (validation/OOS
partitions of `24e5153c…`) · benchmark impl · cost-model impl (file+blob+sha256+version) · metric
impl · bootstrap impl · PBO/DSR impl · report schema · expected output paths. `PENDING_EVALUATOR_BIND`
is resolved here; it may not survive into the authorized run.

## 5. Acceptance submission (what Workstream B returns)

evaluator code identities (commit/tree/blobs) · container + dependency identity · report schema ·
full synthetic end-to-end evidence + hashes · every gate's synthetic fixture result · refusal-test
evidence · determinism proof · confirmation that zero development/validation/OOS performance was
computed. Owner review of that package precedes any validation-opening authorization.

## 6. Boundary

No sealed data, no development performance, no strategy performance. Validation access is a
separate later authorization; OOS access is a further separate authorization after an accepted
validation PASS.
