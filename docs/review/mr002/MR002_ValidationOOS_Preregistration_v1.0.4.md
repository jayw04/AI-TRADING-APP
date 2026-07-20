# MR-002 Validation / OOS Preregistration v1.0.4 (bootstrap-corrected; supersedes v1.0.3)

**Status:** IMMUTABLE. **Governing preregistration.** A **narrow bootstrap-transcription correction**
of v1.0.3, authorized by the owner ruling of 2026-07-20 (`docs/review/comments.md`, Ruling 1). It
supersedes v1.0.3 **only** for the bootstrap defect. **No gate threshold, window, seam date, fold,
cost, D-decision, DSR trial count (N = 5), or access restriction changes** — proven by a machine diff
(only `bootstrap` / `version` / `date` / `supersedes` / `record_status` differ, and
`corrections_from_v1.0.3` is added; every economic invariant is byte-equal).

Machine-readable: `MR002_ValidationOOS_Preregistration_v1.0.4.json`
(`b2a042d4cf8e4d36a70d7e087c3d0e8efc1076e3ee96db7d6c2dc7583129af9c`).
Correction record: `MR002_ValidationOOS_CorrectionRecord_v1.0.4.json` (`33fbb78c…`).

## The defect (the only change)

The Validation/OOS chain substituted **moving-block / L21 / 2000 / seed42** for the frozen **v0.3
stationary / 10,000 / seed 20260711 / expected-L5** rule and **omitted the registered expected-L10
sensitivity**. No signed decision authorized that substitution. The bootstrap-source census
(`MR002_Bootstrap_Source_Census_v1.0`, committed `ed06d01`) established that the stationary rule was
set in v0.2, retained in v0.3, and inherited by the owner-signed v1.0 freeze (`70108c11`); the
moving-block variant entered only through the later Validation/OOS proposal chain and was never
reconciled to v0.3.

## Governing bootstrap (frozen v0.3 stationary rule)

- **Method:** stationary (Politis–Romano, **circular**) bootstrap of eligible daily net portfolio
  returns.
- **Primary expected block length:** **5 sessions**. **Sensitivity expected block length:** **10
  sessions**.
- **Replications:** **10,000** for each block-length run.
- **RNG:** numpy **PCG64**. **Seed:** **20260711**.
- **Statistic:** one-sided **95%** percentile lower confidence bound of mean daily net return.
- **Confirmatory gate:** primary **expected-L=5** lower bound **> 0**.
- **Sensitivity:** expected-L=10 result reported as **robustness evidence** — **not** a separate PASS
  gate (the frozen v0.3 text does not make it one).
- **Mechanics (Politis–Romano):** `p = 1/expected_L`; first source index uniform in `[0, n−1]`; for
  every next observation, with probability `p` start a new block at a uniformly selected source index,
  else advance the prior source index by one; wrap `n−1 → 0` (circular by construction); continue
  until exactly `n` observations. Fixed-length moving blocks are **not** substituted.

The confirmatory OOS gate itself is unchanged: `gates_frozen.oos_pass_requires_BOTH` still requires
`net_oos_sharpe ≥ 0.70` **and** `one_sided_95pct_bootstrap_lower_bound_of_daily_mean_net_return > 0`.
Only the bootstrap that *produces* that lower bound is corrected.

## Everything else — unchanged and governing (from v1.0.3)

Corrected gate battery (`gates_frozen`: Sharpe ≥ 0.70 + bootstrap mean-return lower bound > 0; Calmar
≥ 0.75; MaxDD ≤ 15% validation+OOS; ≥ 3/5 folds; A/C stability; **DSR ≥ 95% at N = 5**; net
annualized return ≥ 3%; cost stress 20/300 bps; breadth incl. ≥ 100 distinct entry dates; trade
concentration; annual profile; regime gates; capacity; PBO / regime-concentration / severe-cost =
diagnostics), the AAPL-authoritative windows and seam dates (validation 2020-01-13→2023-02-08, 775;
OOS 2023-05-30→2026-07-01, 775), five 155-session folds, six-session horizon, D-decisions (S_min
0.70, zero benchmark), the Sharpe estimator, the DSR block (`status` READY, `trials_N` 5, ledger
`deda5cec…` bound), sequencing, sealed-access protocol, and the governing-source census — all as
frozen. The v1.0-final / v1.0.1 / v1.0.2 / v1.0.3 files are preserved unchanged as the superseded
chain.

## DSR dispersion (companion resolution, not a prereg change)

The DSR trial-statistics/dispersion blocker is resolved separately by
`MR002_DSR_DispersionResolution_v1.0.json` (`7a601f5b…`) per Ruling 2: N = 5 unchanged from the
countersigned ledger; σ_trials = stddev(ddof=1) of the validation-period annualized net Sharpes of
MR002-A/B/C only (RNG-001/RNG-EntryLogic retained in N but excluded from dispersion); computed only
during the later authorized validation run and sealed before OOS. That record does **not** alter this
preregistration's economic rules.

## Boundary

Validation/OOS SEALED AND UNREAD; `sequencing.validation_authorization = false`; performance
interpretation + production promotion NOT AUTHORIZED. This correction changes the bootstrap rule and
nothing else; validation access remains a separate, later, explicit authorization after the evaluator
is qualified.
