# MKT-PROJ-001 — Model Card v1.0 (§3 evidence; the §3→§4 owner gate)

| Field | Value |
|---|---|
| Date | 2026-07-10 |
| Model | `calibrated_logistic_primary-mktproj-fv1-2016-02-03_2026-07-09` (status **candidate**) |
| Artifact | joblib, sha256 `5ec687017d9b7d4f…`, hash-verified loads |
| Pre-registration | v1.2 (FROZEN) — one run, nothing tuned after this output existed |
| Pipeline | manifest `mktproj-fv1` → §6a missingness indicators (5 enumerated fields) → train-window median impute → train-fit standardize → LogisticRegression(C=1.0, L2, max_iter=1000) → Platt on the final contiguous 20% of each training window |
| Secondaries (sensitivity only) | HistGBT+isotonic · average ensemble — **never the gate model** |
| Validation | 15 anchored walk-forward folds; OOS 1,868/1,869 days (2019-02 → 2026-07); block-bootstrap CIs (10-day blocks, 2,000 resamples, seed 42) |
| Evidence | `ml_walkforward_PRE_CLOSE_TOMORROW.json` · `ml_walkforward_PRE_OPEN_TODAY.json` (this dir) |

## Gate results — PRIMARY horizon (PRE_CLOSE_TOMORROW)

**Move-Risk Gate: items 1–4 PASS; item 5 (regime review) is yours to adjudicate.**

| Gate item | Frozen requirement | Result |
|---|---|---|
| 1. Brier improvement | beats best baseline (vol-clustering 0.2405) | **0.2338**, delta −0.0067 ✅ |
| 2. CI excludes zero | block-bootstrap 95% | **[−0.0130, −0.0002]** ✅ (marginal — upper bound −0.0002) |
| 3. ECE guardrail | ≤ baseline ECE + 0.02 (≤ 0.0393) | **0.0312** ✅ |
| 4. Coverage | elevated calls (P≥0.5) on 10–60% of OOS days | **14%** ✅ — the wall the baselines couldn't touch |
| 5. No major regime failure | §7 slices reviewed | ⚠ **see below — owner judgment** |

**Direction Gate: `insufficient_sample`** — the model makes no argmax directional calls
(floor 0/100 required non-neutral). Per v1.2, no directional skill claim is allowed, and the
conditional diagnostic cannot rescue this. Directional verdict: **Inconclusive (insufficient
sample)**, exactly the design's prior.

## Gate item 5 — the regime slices (the honest caveat)

Model-vs-baseline Brier deltas (negative = model better):

```text
trend_up   −0.0082 (n=1500)   vol_low  −0.0094 (n=934)    2019 −0.0077   2021 −0.0208
trend_down −0.0004 (n=368)    vol_high −0.0039 (n=934)    2020 −0.0098   2024 −0.0028
                                                          2025 −0.0202
WORSE:  2022 +0.0074 (n=251)   2023 +0.0011 (flat)   2026-partial +0.0047 (n=129)
```

Reading: the edge is real but **concentrated in up-trend / calm-to-normal regimes**. In the one
full bear year in the OOS window (2022) the model was worse than the baseline by +0.0074 Brier,
and in down-trend slices it is baseline-equivalent, not better. This is not a catastrophic
failure (never wildly worse; the down-trend slice is flat), but it is a genuine asymmetry: the
model earns its pass in benign regimes and gives some back in stressed ones. Whether that
constitutes a "major regime failure" is the §5 judgment the pre-registration reserves for you.

## Secondary horizon (PRE_OPEN_TODAY): Move-Risk **FAILS**

Brier 0.1999 vs baseline 0.2050 — delta −0.0050 but CI **[−0.0122, +0.0018] spans zero**
(coverage 10%, ECE ok). Verdict: **Inconclusive** — stays Research Preview with no validated
claim of any kind.

## Drivers (attribution)

Batch permutation importance (last fold, primary): `spy_dist_ma50` (+0.0071),
`fade_recovery` (+0.0059), `spy_intraday_vol` (+0.0031), `spy_dist_ma200` (+0.0027),
`spy_hl_range_pct` (+0.0022) — trend-distance and intraday-stress features, consistent with a
volatility/regime model rather than a directional one. Per-projection drivers are exact
coefficient×value attributions (FR-008); the LLM formatter does not exist until §4 and is
flag-off by design.

## Sensitivity notes (reported, never the gate)

The average **ensemble scores better than the primary** (Brier 0.2308 vs 0.2338; boosted
0.2352). Per the freeze, the calibrated logistic remains the only gate model — switching to the
ensemble after seeing results would be tuning; it is recorded here as pre-registered
sensitivity, nothing more.

## Limitations

1. The pass is **marginal** (CI upper bound −0.0002) and regime-concentrated (above).
2. Direction is unvalidated and likely stays so — the product may never say more than
   "Elevated move risk; direction uncertain."
3. Train/serve provenance differs (SIP-historical vs IEX-live) — the 30-day drift diagnostic
   runs with §4 if built.
4. ~10 years of history; one bear year in OOS. 2022 is the only stress test we have.

## Recommendation (the §4 decision this card gates)

If you accept the regime pattern as "no major failure": the **primary horizon qualifies as a
Validated Move-Risk Projection** — badge and wording capped at *"Elevated move risk; direction
uncertain"* — and §4 (jobs/API/Research-Preview card, LLM off) is worth building around that
single validated claim, with the CEE rolling-calibration watch and the 30-day drift diagnostic
as the guard rails. If you judge 2022 disqualifying: the honest close is **Inconclusive
(regime-limited)** at §3, zero UI spend, with the §4 decision revisitable after more forward
OOS accrues. Either answer is a clean Evidence Engineering outcome.
