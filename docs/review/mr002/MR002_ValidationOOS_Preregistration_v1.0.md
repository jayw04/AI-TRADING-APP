# MR-002 Validation / OOS Preregistration v1.0

**Status:** IMMUTABLE (owner-ratified final). All D-* decisions are frozen (`MR002_ValidationOOS_DecisionRecord_v1.0.json`,
sha `9a3a058c…`); all literal seam dates and fold boundaries are pinned from the registered snapshot
session index; all machine-readable pins are in
`MR002_ValidationOOS_Preregistration_v1.0.json` (sha `e9ee38e5…`). **No validation or OOS data
was read** — only the session-date column of the pinned snapshot (owner-authorized metadata
extraction). The realization-endpoint convention (§seam) is **owner-ratified final = 6**; no items
remain pending. It authorizes nothing (validation/OOS stay sealed; Workstream B is separate).

## Frozen decisions (D-*)

- **D-NI — REJECTED.** No non-inferiority overlay. The confirmatory structure is the frozen one:
  validation supplies the positive-fold (≥3/5) and A/C parameter-stability gates; the **OOS verdict
  is absolute** on untouched config B. `Δ_NI` appears nowhere in the gates (historical note only).
  Reason: **fidelity to the frozen design** — not a claim that absolute testing is universally
  stricter than non-inferiority (they test different claims).
- **D-PURGE — scoring exclusions.** The frozen 1,700/850/850 boundaries are NOT shifted;
  eligibility masks apply inside them (§seam).
- **D-BENCH — zero benchmark.** Primary return = daily net portfolio return on $10M NAV; benchmark
  = 0; excess = the net return. All cash interest, short financing, borrow, execution costs are
  already in net P&L. It is **not** a risk-free accrual series (the cash-zero/risk-free conflation
  is removed).
- **D-COST — executable artifact binding mandatory** before any validation access (§16); no
  placeholder in v1.0-final.
- **S_min = 0.70** is the confirmatory PASS threshold (§gates). 0.40 is a reported tag only.

## Authoritative calendar + literal windows (corrections 1, 2)

Source (owner ruling): the registered snapshot `mr002_research.duckdb` (sha `24e5153c…`) session
index — `SELECT DISTINCT date FROM prices ORDER BY date`. Extraction:
`MR002_SessionIndex_Extraction_Output.json` (sha `a0218e87…`), script sha `908de368…`, snapshot
**unchanged** pre/post. Governed sessions **3,400** (list sha `b873421516ba5c4bbeb4ff3859e574f64f7251a956a2ba6ddea0e753981dad3f`);
`prices` and `etf_prices` session sets are **identical within the governed window**. An external
XNYS library was NOT used and would be a NON-GOVERNING DIAGNOSTIC only.

| Window | Inclusive | Sessions | Scoring-eligible (governing) | Eligible sessions |
|---|---|---|---|---|
| Development | 2013-01-02 → 2019-10-02 | 1,700 | — (in use, no performance) | — |
| Validation | 2019-10-03 → 2023-02-16 | 850 | **2020-01-13 → 2023-02-08** | **775** |
| Sealed OOS | 2023-02-17 → 2026-07-10 | 850 (config B) | **2023-05-30 → 2026-07-01** | **775** |

All three observed counts equal the frozen 1,700/850/850.

**Five validation folds (governing, 155 sessions each; correction 6):** contiguous, non-overlapping,
nearly-equal partitions of the 775 eligible validation sessions (775/5 = 155 exactly).
F1 2020-01-13→2020-08-21 · F2 2020-08-24→2021-04-06 · F3 2021-04-07→2021-11-12 ·
F4 2021-11-15→2022-06-28 · F5 2022-06-29→2023-02-08.

## Seam rule (correction 2; endpoint convention OWNER-RATIFIED FINAL = 6)

Basis: **registered session ordinals**, not calendar-day arithmetic. A decision session `t` is
scored only when **all required formation sessions AND the complete execution/holding/return-
realization horizon lie within the SAME governed window**.
- Formation exclusion at window start: **69 sessions** (owner-ruled).
- Realization horizon: next-open (`t+1`) + registered **5-session max hold**. The frozen design
  applies **next-open execution to the exit ladder**, so the exit fill is the open AFTER the 5th
  held session ⇒ horizon spans `t+1..t+6`. **Governing = 6** (last-eligible = N−1−6). A **close-exit
  alternative = 5** (`t+1..t+5`) is computed and reported: it moves each last-eligible date by one
  session (validation → 2023-02-09, OOS → 2026-07-02; 776 eligible each).

> **OWNER-RATIFIED FINAL:** the endpoint convention is **6** (next-open exit; entry open t+1, five
> held sessions t+1..t+5, exit fill open t+6). The 5-session close-exit alternative is **REJECTED**
> and retained below only as historical rationale — it is NOT executable configuration.

## Gates (corrections 4, 5, 8, 13) — frozen literals

**OOS PASS requires BOTH** (correction 5 — the CI gate and the Sharpe threshold are separate):
1. net OOS Sharpe **point estimate ≥ 0.70**, AND
2. the **one-sided 95% moving-block bootstrap lower bound of the daily mean net return > 0**.
(The bootstrap does not itself prove Sharpe > 0.70; it is a separate mean-return significance gate.)

Plus all frozen gates: Calmar ≥ 0.75 · MaxDD ≤ 15% · **DSR ≥ 95%** · **PBO < 20%** · cost-stress at
2× · configs A and C net-profitable · profit-concentration ≤ 35%/yr · regime-concentration ≤ 60% ·
capacity-positive under the 2% ADV cap · trades ≥ 500 / ≥100 long / ≥100 short. Economic
materiality (correction 13) is carried by Sharpe/Calmar/MaxDD/cost-stress/capacity — no
statistically-positive-but-trivial result can pass. `α = 0.05`.

**Diversifier tag (correction — single confirmatory family):** 0.40 ≤ Sharpe < 0.70 with |corr| ≤
0.30 vs MOM-001 ⇒ **FAIL (confirmatory)** with reported tag `DIVERSIFIER_TIER_MET`. Sharpe < 0.40 ⇒
FAIL. The 0.40 tier is never a PASS route.

## Return series + estimator (corrections 5, 6) 

Daily simple net returns on $10M NAV, realized from next-open execution, net of the frozen cost
model (§16); no forward-fill; excess = net return (D-BENCH zero benchmark). Sharpe = arithmetic
mean ÷ sample std (ddof=1) × √252, float64, reported to 4 dp, reproducible bit-for-bit from the
return vector; zero-volatility (peak-to-peak == 0) ⇒ `INTEGRITY_STOP`.

## Bootstrap (correction 4) — exact algorithm

**Moving-block (non-circular) bootstrap.** Draw blocks of fixed length **L = 21** sessions from
random start indices in `[0, n−1]`, truncate blocks at the series end (no wraparound), concatenate
drawn blocks in draw order, truncate the concatenation to exactly `n`. **2,000** resamples, RNG
**NumPy PCG64 seed 42**, **one-sided 95%** lower bound by the **percentile** method. Mean-return and
Sharpe CIs use the **same** resamples; the **same** method governs validation folds and OOS.
Reference primitive: `evaluator_prototype/mr002_valoos_metrics_prototype.py` (synthetic-qualified;
the qualified evaluator binds the frozen implementation).

## PBO / DSR (correction 8)

- **PBO** — CSCV over the config-B per-fold performance matrix (the 5 validation folds), symmetric
  IS/OOS partitions; threshold < 0.20. A and C are **not** PBO trials (they are the
  parameter-stability gate). Exact split count `S`, ranking metric, and partition enumeration are
  bound in the evaluator qualification with synthetic fixtures (prerequisite, not placeholder).
- **DSR** — Deflated Sharpe with **N = 3 trials** (configs A, B, C tried; B is the verdict),
  benchmark Sharpe 0, sample skew/kurtosis of the config-B net series, √252 annualization,
  significance ≥ 95%. Exact estimator + tolerances bound in qualification. A/B/C are the trial
  family for DSR and the stability gate; they are **not** also an unspecified separate family.

## Exposure/risk limits (correction 11) — frozen, hard refusals

sector-gross ≤ 0.2000 · sector-net ≤ 0.0500 · **beta limit 0.10** (the registered LP bound; the
0.0052 in v0.2 was a demonstrated value, corrected) · net-drift band 5% · dollar-neutral (long
gross = short gross) · single-name ≤ registered start weight (`w_i ≤ 0.015` new-entry). **Any
hard-limit breach in replay ⇒ `REFUSED_EXPOSURE_LIMIT`** (hard refusal, not a diagnostic).

## Hard stops + coverage denominators (corrections 7, 10)

Closed code set (§companion `coverage_gates.codes`). Coverage: registered data-availability ≥ 95%,
PIT-SIC ≥ 98%, per-year ≥ 90%/95%, no forward-fill. Per gate, numerator = observed complete
records; denominator = eligible sessions × registered universe cardinality × required fields. The
registered full-population denominator is **40,750 ticker-days** (sealed manifest); the
**window-specific** ticker-day denominators are computed by the evaluator from the FROZEN universe
table at qualification (a prerequisite, not a placeholder — the development-universe count is not
reused as the sealed-window denominator). A data gap is **never** a discretionary reason to move a
boundary — it is `REFUSED_DATA_COVERAGE` on the fixed window.

## Secondary family (correction 12) — CLOSED

All non-gate metrics are **descriptive only** and cannot change any verdict; there is no inferential
secondary family and no post-hoc multiplicity correction. Adding one later requires a *further*
frozen revision before unsealing.

## Sequencing + sealed access (corrections 9, 14, 15)

Sequential: owner authorizes validation → **one** validation execution → evidence + publication →
adjudication → validation chain closed → **separate** OOS authorization only after an accepted
validation PASS → OOS opened **B only, exactly once**. OOS is **physically inaccessible during
validation**.

Access proof (correction 9 — S3 has no general object last-access): **CloudTrail S3 data events**
enabled before access; a dedicated IAM principal; an explicit **DENY** on the OOS partition during
validation; a validation-only access policy; committed CloudTrail event export; policy-state
snapshots before/after each run. First-access = earliest CloudTrail GetObject on the validation
partition; OOS-unread-during-validation = access-policy isolation + **audited absence** of OOS
GetObject events (not a last-access attribute).

## Evaluator (correction 16) + test-status (correction 1)

**Metric-primitives prototype: EXECUTED — 11/11 synthetic tests passed** (reads no data). **Full
validation/OOS evaluator: NOT YET BUILT OR QUALIFIED** (Workstream B). These are stated once, with
no contradiction. Before any unsealing, the evaluator qualification (separate workstream,
`MR002_ValidationOOS_EvaluatorQualificationPlan_v1.0.md`) binds code commit/tree, container digest,
dependency lock, data-manifest identity, benchmark + cost-model implementations (D-COST), the gate
battery, PBO/DSR, report schema, expected output paths, and refusal tests — all qualified on
synthetic + development-free fixtures producing zero real performance.

## Conclusion language (correction 18)

- **Validation PASS:** merit in the preregistered validation period only (folds + stability); not
  OOS or production merit.
- **OOS PASS:** the registered effect cleared the preregistered **absolute** gates in the final
  untouched OOS period. Even an OOS PASS does **not** establish production capacity, scalability, or
  live-trading robustness.

## Finalization

This is v1.0-final: the realization-endpoint convention is owner-ratified (**6**), no deferred
literal dates remain, and every window, date, fold, threshold, estimator, and D-decision is frozen
unchanged from RC1. Workstream B (evaluator build + synthetic qualification) proceeds as a separate
program; validation/OOS stay sealed until the owner authorizes the validation opening.
