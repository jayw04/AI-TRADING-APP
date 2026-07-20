# MR-002 Workstream B — Increment 1 v1.2 submission (bootstrap + DSR-dispersion rulings applied)

**Status: submitted for review; STOP for adjudication.** Implements the owner rulings of 2026-07-20
(`docs/review/comments.md`, Rulings 1–3). The two narrow governance records were committed **first**
(commit `4385ec7`), as the ruling required; this submission covers the Increment 1 **v1.2 code** that
binds to them. **No sealed data read; no performance computed. Increment 2 / validation execution /
OOS execution / real-data access / performance interpretation NOT authorized.**

## Governance records (committed `4385ec7`, before any code)

| Record | sha256 |
|---|---|
| `MR002_ValidationOOS_Preregistration_v1.0.4.json` (governing) | `b2a042d4cf8e4d36a70d7e087c3d0e8efc1076e3ee96db7d6c2dc7583129af9c` |
| `MR002_ValidationOOS_CorrectionRecord_v1.0.4.json` | `33fbb78ce7679aaab2afc514cb0164f09e3331f87b8422b4827a0d2587c91b91` |
| `MR002_DSR_DispersionResolution_v1.0.json` | `7a601f5b7bc0bea5045755723d7f9b946b01f7eba0eee9191e0f2074b6fb5627` |

**v1.0.4 is a machine-diff-proven narrow correction of v1.0.3:** only `bootstrap`, `version`, `date`,
`supersedes`, `record_status` changed and `corrections_from_v1.0.3` was added; every economic
invariant (`gates_frozen`, `windows_literal`, folds, `seam_rule`, `cost_model_frozen_values`, `dsr`,
`exposure_limits_frozen`, `sharpe_estimator`, `sequencing`, `benchmark`, D-decisions, access
protocol) is **byte-equal**. The bootstrap block is now the frozen v0.3 stationary rule: stationary
(Politis–Romano, circular), expected block length **5** (confirmatory) + **10** (reported
robustness), **10,000** replications each, numpy **PCG64**, seed **20260711**, one-sided 95% lower
bound of mean daily net return; confirmatory gate = L=5 lower bound > 0. Moving-block/L21/2000/seed42
is rejected as transcription drift. The DSR trial count **N = 5** and the countersigned ledger
(`deda5cec…`) are **unchanged**; only the dispersion **estimator** is resolved.

## Increment 1 v1.2 code (this submission)

Directory `docs/review/mr002/evaluator/`:

1. **`mr002_valoos_metrics.py`** — moving-block bootstrap **removed**; replaced by the stationary
   Politis–Romano circular construction (`_stationary_indices`,
   `stationary_bootstrap_mean_lower_bound`, `stationary_bootstrap_confirmatory`). Fail-closed:
   expected_block ∈ {5,10}; exactly 10,000 replications; seed 20260711 (`BOOTSTRAP_SEED:*` on any
   other governing-run seed). DSR `trial_sharpe_std` validated finite + non-negative
   (`DSR_TRIAL_DISPERSION_NONFINITE` / `DSR_TRIAL_DISPERSION_NEGATIVE`; σ=0 allowed and flagged
   `trial_sharpe_std_is_zero`, collapsing to the zero-benchmark term). New `production_deflated_sharpe`
   reads N + σ_daily from the validation dispersion artifact and stamps
   `trial_sharpe_std_provenance="VALIDATION_DERIVED"`; synthetic path keeps `"SYNTHETIC"`. PBO
   labelled `NOT_FULLY_QUALIFIED — DIAGNOSTIC ONLY`.
2. **`mr002_valoos_identity.py`** — governing chain retargeted to **v1.0.4** and widened from 3 to **4
   artifacts**: prereg (v1.0.4) + ledger + **CorrectionRecord** (binds v1.0.3→v1.0.4, affirms no
   economic change) + **DispersionResolution** (N=5, source trials A/B/C, estimator, ledger + prereg
   bound). The prereg's stationary-bootstrap spec is cross-checked against the code constants
   (`BOOTSTRAP_NOT_STATIONARY` / `BOOTSTRAP_SEED` / `BOOTSTRAP_REPLICATIONS` / `BOOTSTRAP_L_*`). New
   `load_validation_dispersion_artifact` fail-closes with `REFUSED_CODE_OR_DATA_IDENTITY` when the
   countersigned validation-stage artifact is absent (as it is now) or its identity does not bind.
3. **`mr002_valoos_report.py`** — schema `increment1-v1.2-synthetic`; embeds `dependency_lock_sha256`
   and the v1.0.4 correction + dispersion-resolution identities. Exact-float / signed-zero
   canonicalization unchanged.
4. **`mr002_valoos_registry.py`** — cross-validation text retargeted to v1.0.4 `gates_frozen` (no
   threshold/sample change; the 22 required gates and thresholds are byte-identical).
5. **Evidence + fixtures** — `test_increment1.py` (53 tests), `_gen_evidence.py`,
   `MR002_Increment1_Dependencies.json` (v1.2), regenerated `MR002_Increment1_CanonicalReport.json` +
   `MR002_Increment1_Qualification.json` + `MR002_Increment1_TestLog.txt`. The DSR-dispersion
   governance note is marked RESOLVED (points to the resolution record).

## Qualification result

- **Tests:** 53 passed; **ruff:** clean. Reads no real dataset; synthetic fixtures only.
- **Determinism:** canonical full-battery report byte-identical across runs; `output_hash` =
  `599009ed3da90c40df85be6dc779bd36bc80dde0fca6dec00e89a267a4f368a1`; self-hash verifies; dispositions
  `research_gate_verdict = PASS`, `run_disposition = PASS`; signed-zero (`-0x0.0p+0`) preserved.
- **Independent fixtures:** stationary index sequences frozen (`_stationary_indices(6,2,seed20260711)
  = [5,0,1,2,3,1]`, `(5,5,seed7) = [4,0,1,2,3]`; large-L → one contiguous circular block); DSR
  values hand/scipy-derived (N1 0.9485960168552995, N5 0.8296873320858645); dispersion refusals and
  production-DSR refusals exercised.
- **DSR-N binding:** N=5 sourced from the ledger bytes; no code constant (`TRIALS_N` absent).
- Evidence hashes: dependency lock `17a73ede…`; canonical report file `413aeb71…`; qualification
  `6030d751…`.

## Disclosures (for the reviewer)

- **Identity chain restructured 3 → 4 artifacts.** The prior loaded triple (prereg / ledger /
  `MR002_DSR_Resolution_v1.0`) becomes prereg (v1.0.4) / ledger / CorrectionRecord /
  DispersionResolution. `MR002_DSR_Resolution_v1.0.json` is retained on disk as history (it recorded
  the v1.0.2→v1.0.3 DSR-READY transition); its role is now subsumed by the prereg `dsr` block + the
  ledger + the DispersionResolution, so it is no longer a mandatory load. If you prefer it kept in the
  loaded chain, say so and I will re-add it.
- **Production DSR path is not exercisable end-to-end yet — by design.** The validation-stage artifact
  `MR002_DSR_TrialDispersion_Validation_v1.0.json` is produced only during the later authorized
  validation run. It is absent now, so `load_validation_dispersion_artifact` correctly REFUSES; the
  positive compute path is exercised only against a clearly-labelled **synthetic** in-tmp fixture that
  never claims to be the real validation-derived value. The A/B/C Sharpes are **not** computed.
- **The v0.2-era prototype still contains moving-block.**
  `docs/review/mr002/evaluator_prototype/mr002_valoos_metrics_prototype.py` retains the rejected
  moving-block primitive. It is **no longer referenced** by the governing prereg (v1.0.4
  `reference_implementation` points at the qualified evaluator). Recommend treating it as
  superseded/historical, like the v1.0–v1.0.3 prereg files. Not edited in this submission.
- **Wheel-hash:** still an installed-artifact (dist-info RECORD) lock — sufficient for v1.2 synthetic
  qualification per Ruling 3. A hashed/immutable-container lock from a clean CI/WSL environment is
  owed before the eventual full-evaluator freeze (not blocked on Norton/PyPI).

## Boundary

Validation/OOS **SEALED AND UNREAD**; `sequencing.validation_authorization = false`. This submission
freezes the algorithm and the identity chain only. **NOT authorized:** Increment 2, validation
execution, OOS execution, real-data access, performance interpretation. Awaiting owner adjudication.
