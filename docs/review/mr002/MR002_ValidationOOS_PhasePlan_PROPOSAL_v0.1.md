# MR-002 Validation / OOS Phase Plan — PROPOSAL v0.1 (PREPARED, NOT EXECUTED)

**Status:** a preregistration/authorization PROPOSAL only. No validation or OOS data was read
while preparing it. It authorizes nothing; it is submitted for owner review to govern a future,
separately-authorized phase. Stage-3 execution qualification is complete (Run 5 PASS); this phase
would be the FIRST test of economic/statistical merit, which Stage 3 explicitly did not establish.

## 0. Preconditions (must hold before any unsealing)

- The registered Stage-3 clean-run evidence is the fixed input: checkpoint
  `511d11f52ce2751a…` (S3 versionId `Zz_TSuBsU.sMT7q8lpoaJieWbETfZdtq`), manifest `27fe7624…`,
  corpus `1d231930…`, implementation `ecaa262…`.
- Everything in §§1–8 below is FROZEN and committed BEFORE the first validation byte is read.
  Nothing here may change after unsealing.

## 1. Exact windows

- **Development (already used, not re-opened):** 2013-01-02 → 2019-10-02 (the frozen corpus
  source's DEV range). Performance was never computed on it and must not be back-filled.
- **Validation and OOS (sealed):** the two forward sealed periods as DEFINED IN THE MR-002
  PREREGISTRATION window section. Their exact calendar boundaries are to be transcribed from the
  preregistration DESIGN (metadata, not data) at plan finalization and pinned here as literal
  dates before unsealing. **A purge/embargo gap** between windows (proposed: ≥ the maximum
  signal-formation + holding horizon, e.g. ≥ 1 rebalance period) must be stated explicitly so no
  observation straddles a boundary.
- Proposed order: **validation strictly precedes OOS in calendar time**, and OOS is the most
  recent held-out period.

## 2. Hypotheses (fixed before access)

Primary (confirmatory), stated directionally, e.g.:
- H1: the registered sector-neutral residual-reversion book earns a positive risk-adjusted
  excess return over its registered benchmark on validation.
- H2 (OOS gate): the same holds OOS, with an effect not statistically distinguishable-worse than
  validation (no OOS collapse).

Secondary/exploratory hypotheses are labeled as such and cannot promote the book on their own.

## 3. Metrics (fixed before access)

- Primary metric: registered risk-adjusted return (proposed: annualized Sharpe of the book's
  excess return vs the registered benchmark), net of the registered cost model.
- Supporting (reported, non-decisive): CAGR, max drawdown, hit rate, turnover, exposure
  adherence, tail metrics. The primary metric alone drives pass/fail.

## 4. Pass / fail and stop criteria

- **Validation pass:** primary metric ≥ a preregistered threshold with a preregistered
  confidence interval excluding the null (e.g. block-bootstrap CI lower bound > 0), stated as an
  exact number before unsealing.
- **OOS pass:** primary metric passes the same absolute bar AND a non-inferiority bound vs
  validation (OOS not worse than validation by more than a preregistered margin).
- **Hard stops (either window):** exposure/risk-limit breach in replay, evidence-integrity
  failure, or a data-availability gap invalidating the window → REFUSED, no salvage.
- A validation FAIL does not authorize re-parameterization and re-test; it ends the confirmatory
  program (exploratory learning only).

## 5. Multiplicity controls

- Exactly one primary hypothesis per window drives the decision (family size = 1 for the gate).
- Any secondary tests use a preregistered correction (proposed: Holm–Bonferroni across the named
  secondary family) and cannot change the primary verdict.
- No metric-shopping, no window-shopping, no threshold-tuning after unsealing (see §7).

## 6. Permitted comparisons

- The book vs its single registered benchmark; and validation-vs-OOS for the non-inferiority
  check. No post-hoc introduction of new benchmarks, sub-universes, or regimes as decision
  inputs.

## 7. Prohibited post-unseal tuning

- After any validation/OOS byte is read: no changes to signals, thresholds, limits, gates,
  costs, universe, windows, metrics, or hypotheses. The development-window "void figures"
  prohibition (MR-002 erratum) extends here: observed sealed figures may not motivate any
  economic-design change.

## 8. Evidence format + publication rules

- Every window run produces an immutable evidence record (hashes, counts, metric values, CIs,
  seed, exact code/data identities) under the same governance discipline as Stage 3 (frozen
  loaders, byte-exact commits, no normalization).
- Publication states the verdict and the complete evidence; a PASS authorizes only submission for
  adjudication, never automatic promotion.

## 9. Sequential vs simultaneous unsealing (recommendation)

**Recommended: sequential.** Unseal and adjudicate VALIDATION fully first; only on a validation
PASS (and owner authorization) unseal OOS. This preserves OOS as a genuine untouched test and
prevents validation results from informing OOS handling. Simultaneous unsealing is not
recommended.

## 10. What this phase can and cannot conclude

- CAN (if it passes): evidence of a positive, statistically-supported, cost-aware edge that
  survives out of sample on the registered design.
- CANNOT (still out of scope): production promotion, live sizing, or capital allocation — those
  remain separate, later, explicitly-governed decisions.

## Requested owner actions

1. Review this proposal; direct corrections (windows, thresholds, metric, margins, unsealing
   order).
2. On acceptance, a finalized preregistration (v1.0) with literal pinned boundaries/thresholds is
   committed BEFORE any unsealing. Validation/OOS access remains NOT AUTHORIZED until then.
