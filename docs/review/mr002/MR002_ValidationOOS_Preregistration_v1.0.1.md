# MR-002 Validation / OOS Preregistration v1.0.1 (supersedes v1.0)

**Status:** IMMUTABLE. **Supersedes `MR002_ValidationOOS_Preregistration_v1.0`** *before any
validation access* — its gate battery was anchored to the v0.1 gate table instead of the governing
v0.3-frozen-into-v1.0 source. Validation and OOS remained **unread**; no evaluator was built from
the wrong battery; no performance was computed; no strategy verdict was affected. The superseded
v1.0 files are preserved unchanged (`ec557827…` md, `e9ee38e5…` json). Machine-readable pins:
`MR002_ValidationOOS_Preregistration_v1.0.1.json` (`7afbd89e…`); gate-by-gate correction:
`MR002_ValidationOOS_CorrectionRecord_v1.0.1.json` (`fc37b21c…`); source census:
`MR002_GateSource_Census_v1.0.json` (`a0327640…`).

## Governing gate source (established by census, not version number)

The governing gate battery is the **v0.3 gate table, frozen UNCHANGED into v1.0**:
- **v1.0_FROZEN** (owner-signed Research-Design Freeze, 2026-07-11) — sha256
  `70108c11f5817158261d17feccc2f8be0519fdc424745eb97ec0fdfbc8cf25fc` — states "all pass gates are
  unchanged and closed since v0.3" (precedence rule #1). Restored to
  `governing_sources/` byte-exact.
- **v1.0_FREEZE_CANDIDATE** — sha256 `7b5ee09c…` — the artifact hash-bound by
  `MR002_SealedManifest_v1.0.json` (`freeze_candidate_doc`; precedence rule #2). Gate lines are
  **identical** to v1.0_FROZEN (only freeze-status wording differs). Also restored byte-exact.
- v1.1 (refreeze) is **portfolio-construction only** and inherits all pass gates unchanged, so it
  does not alter the battery.

**Finding:** both v1.0 freeze docs were **absent from HEAD** (history only, capital-`Docs/` paths);
they are now restored byte-exact under `docs/review/mr002/governing_sources/`.

## Unchanged from v1.0 (correct as previously frozen)

Windows, the AAPL-authoritative snapshot session index (reconciled identical to all-prices
in-window, governed hash `b873421516ba5c4bbeb4ff3859e574f64f7251a956a2ba6ddea0e753981dad3f`), the
literal seam dates (**validation 2020-01-13 → 2023-02-08, 775; OOS 2023-05-30 → 2026-07-01, 775**),
the five 155-session folds, the **six-session** realization horizon (owner-ratified), the
D-decisions (D-NI rejected/absolute-OOS · D-PURGE scoring-exclusions · D-BENCH zero benchmark ·
D-COST artifact binding mandatory · **S_min = 0.70**), the Sharpe estimator (arithmetic/ddof-1/√252,
peak-to-peak-zero → INTEGRITY_STOP), the moving-block bootstrap (L=21, 2,000, PCG64 seed 42,
one-sided 95% percentile), the sequencing, and the CloudTrail sealed-access protocol are **unchanged
and re-affirmed** from v1.0 (see the v1.0 md `ec557827…` for their full text). One wording fix: the
fold-remainder rule is **"remainder to the FINAL fold"** (frozen v0.3; numerically identical here —
775/5 = 155, zero remainder).

## Corrected gate battery (GOVERNING — from v0.3-frozen-into-v1.0)

**Confirmatory verdict is read on the sealed OOS (config B, once), net of base costs.** OOS **PASS
requires ALL** of the gates below (two of them jointly define significance/return):

| Gate | Rule | Sample | Class |
|---|---|---|---|
| Net Sharpe (headline) | **≥ 0.70** point estimate | sealed OOS | gate |
| Bootstrap mean-return | one-sided 95% lower bound **> 0** | sealed OOS | gate |
| Net Calmar | ≥ 0.75 | sealed OOS | gate |
| Max drawdown (net) | ≤ 15% | **validation + sealed OOS combined** (OOS also separate) | gate |
| Positive walk-forward folds | ≥ 3 of 5 (config B) | validation | gate |
| Parameter stability | configs A and C both net-profitable | validation | gate |
| Deflated Sharpe (significance) | ≥ 95% per the trial ledger | sealed OOS | gate (**N = blocker**) |
| Net annualized return | **≥ 3%** at the registered gross cap | sealed OOS | gate |
| Cost stress | profitable at **20 bps/side + 300 bps/yr borrow** | sealed OOS | gate |
| Breadth | ≥ 500 trades · **≥ 100 distinct entry dates** · ≥ 100 long · ≥ 100 short | sealed OOS | gate |
| Trade concentration | top-10 trades ≤ 20% of positive trade P&L · single stock ≤ 10% | sealed OOS | gate |
| Annual profile | **≥ 3 positive calendar years** AND largest positive year ≤ 50% of Σ positive annual P&L | validation + OOS | gate |
| Regime gates | positive net P&L in ≥ 2 of 3 trend regimes · no trend regime > 60% of **losses** · no vol regime Sharpe < −0.50 (regimes < 60 sessions = n/a) | validation + OOS | gate |
| Capacity | positive net edge at $10M under the 2% ADV cap | sealed OOS | gate |

**DIAGNOSTICS (reported, never PASS/FAIL levers):** PBO (N=3, "underpowered"); positive-P&L regime
concentration; severe cost stress (30 bps/side + 1000 bps/yr borrow); annual-P&L Herfindahl.

**Diversifier tag (not a confirmatory PASS route):** OOS Sharpe 0.40–0.70 with |corr| ≤ 0.30 vs
MOM-001 and all of cost-stress/DSR/breadth/trade-concentration/annual-profile/regime gates passing
⇒ **FAIL (confirmatory)** with reported tag `DIVERSIFIER_TIER_MET`. Sharpe < 0.40 ⇒ FAIL.

**Regime definitions (v0.3 §10a):** volatility axis = SPY trailing 21-session annualized realized
vol (High ≥ 20%, Low < 20%); 3 trend regimes; axes never combined into one denominator.

`α = 0.05`. Economic materiality is carried by Sharpe/Calmar/MaxDD/net-return/cost-stress/capacity.

## DSR trial-ledger — GOVERNANCE BLOCKER (correction; DSR N unbound)

The frozen ledger (v0.3) is "configs A/B/C + the mean-reversion family's prior examined variants
(RNG-001 and documented sub-studies; informal MR variants logged before freeze)." **No trial-ledger
artifact exists** enumerating these exactly, so the DSR **N is not defensibly pinnable**. Per the
owner's DSR ruling, this is submitted as a **separate governance blocker**
(`MR002_DSR_TrialLedger_Blocker_v1.0.md`); the DSR gate remains a PREREQUISITE (N unbound) — it
cannot be executed until N is bound from the frozen record. PBO's N=3 is unaffected (A/B/C, and PBO
is a diagnostic).

## Conclusion language (unchanged)

Validation PASS = merit in the validation period only; OOS PASS = the effect cleared the
preregistered **absolute** gates in the final untouched OOS period; even an OOS PASS does not
establish production capacity, scalability, or live-trading robustness.

## Boundary

Validation/OOS SEALED AND UNREAD; performance interpretation + production promotion NOT AUTHORIZED.
Workstream B (evaluator) remains STOPPED pending owner acceptance of v1.0.1 and resolution of the
DSR-N blocker.
