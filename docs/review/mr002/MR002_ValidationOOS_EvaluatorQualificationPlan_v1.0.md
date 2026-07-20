# MR-002 Validation/OOS Evaluator Qualification Plan v1.0 (Workstream B)

**Scope:** the SEPARATE engineering workstream to build and qualify the full MR-002 validation/OOS
evaluator. **Not started.** It runs entirely on synthetic and development-free fixtures — producing
NO development, validation, or OOS performance — and must be accepted before the owner authorizes
the validation opening. This plan is the acceptance contract; it reads no sealed data.

> **HARD PRECONDITION (blocking):** Workstream B implementation may NOT begin until BOTH hold:
> (1) the v1.0.2 preregistration is owner-accepted; and (2) the DSR trial ledger is
> **countersigned** with `dsr.status = READY` and an exact `dsr.trials_N` + `trial_ledger_sha256`
> bound (`MR002_DSR_TrialLedger_Candidate_v1.0.json` is a CANDIDATE only). While `dsr.status !=
> READY`: `trials_N` is null, validation authorization is false, the evaluator cannot reach a PASS
> disposition, and no validation input may be opened. The evaluator must implement DSR against the
> countersigned N — never a defaulted 3.

## 0. Relationship to the governance package

The preregistration v1.0-final (`e9ee38e5…`) + decision record (`9a3a058c…`) FREEZE the windows,
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
4. **Metric + gate battery (per the CORRECTED v1.0.1 governing gates — see
   `MR002_ValidationOOS_CorrectionRecord_v1.0.1.json`)** — each a frozen implementation with a
   synthetic fixture of known answer. **PASS gates:** Sharpe ≥ 0.70; bootstrap mean-return lower
   bound > 0; Calmar ≥ 0.75; MaxDD ≤ 15% on **validation+OOS combined**; ≥3/5 positive folds; A/C
   stability; DSR ≥ 95% (**N = blocker**, below); **net annualized return ≥ 3%**; cost stress at
   **20 bps/side + 300 bps/yr borrow**; breadth ≥ 500 trades / **≥100 distinct entry dates** / ≥100
   long / ≥100 short; **trade concentration** (top-10 ≤ 20% of positive trade P&L, single stock ≤
   10%); **annual profile** (≥3 positive years AND largest ≤ 50% of Σ positive annual P&L); **regime
   gates** (≥2 of 3 trend regimes positive, no trend regime > 60% of losses, no vol regime Sharpe <
   −0.50); capacity. **DIAGNOSTICS (implemented but NEVER PASS/FAIL levers):** **PBO** (N=3,
   underpowered), **positive-P&L regime concentration**, **severe cost stress** (30 bps + 1000 bps),
   **annual-P&L Herfindahl**. The evaluator must tag diagnostics as non-gating so they cannot alter
   a verdict.
5. **PBO (CSCV, DIAGNOSTIC)** — exact split count `S`, ranking metric, partition enumeration; output
   reported, never gating. **DSR (GATE)** — deflated-Sharpe estimator, skew/kurtosis, expected-max-
   Sharpe, tolerances; **trial N is BLOCKED** (`MR002_DSR_TrialLedger_Blocker_v1.0.md`) — the DSR
   gate stays unexecutable until the owner binds N from the frozen ledger; do NOT default to 3.
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
