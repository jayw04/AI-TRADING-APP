# MR-002 / SPQ-1 Development Plan After Phase 2B — v1.1.1 (governing-source erratum)

**Program:** MR-002 — Sector-Neutral Residual Reversion · **Workstream:** SPQ-1
**Status:** Phase 2B COMPLETE and CLOSED · **Type:** narrow correction to v1.1 (planning only; opens no data, authorizes no execution)
**Relationship to v1.1:** This erratum **supersedes v1.1 for the enumerated items in §F** (governing preregistration version, its identities, the bootstrap contract, the DSR-dispersion rule, and the short-side metric-role classification). For every other section, `MR002_Development_Plan_Next_Phases_v1.1.md` remains in force and is read alongside this document.

---

## A. Erratum

> **Governing preregistration correction.** The governing Validation/OOS preregistration is `MR002_ValidationOOS_Preregistration_v1.0.4`, commit `4385ec7728a81c0db965e2f44d6017e6116d027c`, content SHA-256 `b2a042d4cf8e4d36a70d7e087c3d0e8efc1076e3ee96db7d6c2dc7583129af9c`. It supersedes v1.0.3 for the bootstrap block. The governing bootstrap is the circular Politis–Romano stationary bootstrap with expected block length 5 as primary, expected block length 10 as robustness sensitivity, 10,000 replications each, NumPy PCG64, and seed 20260711. The earlier moving-block/L21/2,000/seed42 values were rejected transcription drift.

**Why this correction exists.** v1.1 §3.1 (and the v1.1-review "items to bind" list) carried the superseded v1.0.3 bootstrap (`moving-block / L21 / 2,000 / seed 42`). A WP 3A-1 source-verification check found that v1.0.4 — six commits ahead of v1.0.3, with v1.0.3 as merge base — is the later, owner-ruled (2026-07-20 Ruling 1) governing prereg that restores the frozen v0.3 stationary rule. Verified locally: `sha256(MR002_ValidationOOS_Preregistration_v1.0.4.json) = b2a042d4…` reproduces the owner-stated content identity exactly.

---

## B. Governing preregistration identity (bind these; do not abbreviate in binding JSON)

| Item | Value |
|---|---|
| Governing prereg | `MR002_ValidationOOS_Preregistration_v1.0.4` |
| Governing commit | `4385ec7728a81c0db965e2f44d6017e6116d027c` |
| Prereg content SHA-256 | `b2a042d4cf8e4d36a70d7e087c3d0e8efc1076e3ee96db7d6c2dc7583129af9c` |
| Superseded prereg | `MR002_ValidationOOS_Preregistration_v1.0.3`, commit `c7a2e4b7ec5bb5012413bd385c78dee3e80d50cb` (bootstrap block only) |
| Correction record | `MR002_ValidationOOS_CorrectionRecord_v1.0.4.json` (v1.0.3 → v1.0.4) |

**Correction classification.** The v1.0.3 → v1.0.4 change is an **INTEGRITY / GOVERNANCE CORRECTION** — a bootstrap-transcription repair restoring the frozen v0.3 stationary rule. It is **not a new trial**, **not a parameter selection based on performance**, and observed no validation/OOS result. Per v1.0.4's own record, **no gate threshold, window, seam date, fold, cost, D-decision, DSR trial count, or access restriction changed.** Phase 3A's degrees-of-freedom attestation (WP 3A-2) must classify it `GOVERNANCE_ONLY` and confirm it leaves `SIGNAL_OR_TRIAL_AFFECTING` count = 0 and DSR N = 5.

---

## C. Corrected §3.1 — preregistration facts Phase 3A must BIND (not redesign)

Phase 3A binds each value below **by content hash and machine-readable diff** against governing preregistration **v1.0.4** (commit `4385ec7728a81c0db965e2f44d6017e6116d027c`, content SHA-256 `b2a042d4…`). It must not reselect or reinterpret them.

| Preregistered fact | Value |
|---|---|
| Validation window | 2020-01-13 → 2023-02-08 |
| OOS window | 2023-05-30 → 2026-07-01 |
| Walk-forward folds | 5 |
| **Primary Sharpe gate** | **net_oos_sharpe ≥ 0.70** (net return **including** 50 bps/yr borrow financing) |
| Borrow financing (in net) | `financing_costs_included_in_net = true`; `borrow_bps_per_year = 50`, day-count 360 |
| Cost stresses | 20 bps/side and 300 bps/yr borrow (severe **diagnostic**: 30 bps/side + 1000 bps/yr) |
| **Bootstrap (CORRECTED)** | **stationary (Politis–Romano, circular)**; expected block length **5 primary + 10 sensitivity**; **10,000** replications each; RNG **NumPy PCG64**; seed **20260711** |
| Bootstrap confidence | one-sided 95% lower bound |
| Confirmatory bootstrap gate | expected-L=5 lower bound of mean daily net return **> 0** (expected-L=10 = robustness **diagnostic only**, not a separate pass gate) |
| DSR multiplicity | N = 5 |
| DSR trial ledger identity | `deda5cec0bbb72dd845633e99682849e6cf0db949e252dba956a432fcb383e9b` (`MR002_DSR_TrialLedger_v1.0.json`) |
| DSR trial set | A, B, C, RNG-001, RNG-EntryLogic |
| DSR annualization | sqrt(252) · benchmark Sharpe = 0.0 |
| Diagnostics | PBO, regime concentration (not gates) |
| Execution endpoint | −5/−6 endpoint = next-open exit (realization horizon 6) |
| Portfolio | dollar-neutral (long_gross == short_gross); min_short = 100 |
| Current authorization | `validation_authorization = false` |

*(The moving-block bootstrap row from v1.1 §3.1 is deleted and replaced by the stationary row above.)*

---

## D. DSR treatment + DSR-dispersion rule *(new binding)*

DSR multiplicity **N = 5** and trial ledger **`deda5cec…`** are unchanged. v1.0.4 additionally carries a governing **DSR-dispersion resolution** that Phase 3A must bind (but must **not** compute during Phase 3A):

| Item | Value |
|---|---|
| N | 5 |
| Dispersion source | validation-period annualized net Sharpes of Config A, B, and C |
| Dispersion estimator | sample standard deviation, `ddof = 1` |
| Conversion to per-observation units | divide by `sqrt(252)` |
| RNG-001 / RNG-EntryLogic | **remain included in N**; **excluded from dispersion** (comparable frozen Sharpes unavailable) |
| Required pre-OOS artifact | `MR002_DSR_TrialDispersion_Validation_v1.0.json` |

The `MR002_DSR_TrialDispersion_Validation_v1.0.json` artifact is **generated during the authorized validation run** and **frozen before OOS authorization**. It is **not** calculated during Phase 3A. Phase 3A's null-model spec (WP 3A-6) binds this rule and the existing 5-trial ledger; it invents no sixth trial and reruns no RNG program.

---

## E. Short-side metric roles (corrects/clarifies v1.1 §2, §4.2 A2, §4.4a)

The preregistered net model — including 50 bps/yr borrow financing — is the frozen primary research test. The conservative availability model is a newly required economic-realism layer that **may block product promotion but must not replace the frozen primary research test**.

| View | metric_role |
|---|---|
| Preregistered net model **including 50 bps/yr borrow financing** (borrow *cost*, borrow *availability* assumed) | `PRIMARY_GATE` |
| Conservative availability / locate / SSR model (A2) | `SECONDARY_GATE` (a.k.a. `ECONOMIC_OPERABILITY_GATE`) |
| Zero-borrow-cost frictionless short attribution | `DIAGNOSTIC_ONLY` |

Phase 3A must confirm — by binding v1.0.4 — that the primary gate's return series is the net-with-borrow-cost series above, and must **not** move the primary statistical gate onto the conservative-availability view. The precise `metric_role` classification is fixed (by hash, from v1.0.4 + the MetricRoleRegistry) before validation opens.

---

## F. Enumerated replacements against v1.1

| v1.1 location | Was | Now |
|---|---|---|
| §3.1 header (L99) | governing prereg **v1.0.3** (`c7a2e4b`) | governing prereg **v1.0.4** (`4385ec7728a81c0db965e2f44d6017e6116d027c`, content `b2a042d4…`) |
| §3.1 table (L108) | Moving-block bootstrap: L=21, 2,000, seed 42 | Stationary Politis–Romano: expected-L 5 (+10 sensitivity), 10,000 each, PCG64, seed 20260711 (§C) |
| §3.1 table (add) | — | Prereg content SHA-256 `b2a042d4…`; DSR-dispersion rule (§D) |
| §4.2 A1 (L166) | "…after preregistration **v1.0.3**…" | "…after preregistration **v1.0.4**…"; the v1.0.3→v1.0.4 correction is classified `GOVERNANCE_ONLY` (§B) |
| §4.2 item 3 (L134) | Config A/B/C bound by hash from prereg **v1.0.3** | …from prereg **v1.0.4** |
| §4.4a (L289) | metric_role bound by hash from prereg **v1.0.3** | …from prereg **v1.0.4** |
| §10 task 1 (L508) | Locate governing prereg **v1.0.3** (`c7a2e4b`) | Locate governing prereg **v1.0.4** (`4385ec7728a81c0db965e2f44d6017e6116d027c`) |

*(Editorial from the v1.1 review, applied here: full hashes are used in all binding statements; §5.3a is labeled Amendment **A5** so the amendment set reads A1–A6 consecutively; a "null-count summary" is `value-blind` only when produced by the sealing/custodian process — never by a direct query of sealed rows.)*

---

## G. Authorization boundary (this revision)

| Action | Status |
|---|---|
| Correct roadmap to v1.1.1 (this document) | AUTHORIZED |
| Bind and verify v1.0.4 source facts (WP 3A-1 source-verification gate) | AUTHORIZED |
| Draft remaining Phase 3A artifacts (WP 3A-1 registry through 3A-8) | **NOT YET AUTHORIZED** |
| Open validation data · Open OOS data · Compute performance | **NOT AUTHORIZED** |

After this correction is accepted, a separate authorization can open drafting of the complete Phase 3A package. Validation/OOS remain sealed and unread.
