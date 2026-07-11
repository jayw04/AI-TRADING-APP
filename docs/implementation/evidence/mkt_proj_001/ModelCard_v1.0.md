# MKT-PROJ-001 — Model Card v1.0 (§3 evidence; the §3→§4 owner gate)

| Field | Value |
|---|---|
| Date | 2026-07-10 |
| Model | `calibrated_logistic_primary-mktproj-fv1-2016-02-03_2026-07-09` (status **candidate**) |
| Artifact | joblib, sha256 `5ec687017d9b7d4f…`, hash-verified loads |
| Pre-registration | v1.2 (FROZEN) — one run, nothing tuned after this output existed |
| Amendments | 2026-07-11 owner evidence review (approved with documentation/provenance corrections; NO model/threshold/artifact/scope change): direction-gate wording corrected (the model made 102 non-neutral calls, 98 UP/4 DOWN — floor unmet; the original text wrongly said zero); ensemble comparison wording fixed (0.2308 is lower/better); attribution marked last-fold-diagnostic-only; production promotion now requires the full provenance manifest (`promote_model.py`) — git_commit:null is acceptable for draft evidence only |
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

**Direction Gate: `insufficient_sample`.** The model produced 102 non-neutral argmax
directional calls (98 UP, 4 DOWN), but the pre-registered sample floor was not met (DOWN
calls 4 < 50) and no valid directional baseline is available. Therefore no directional skill
claim is allowed. Direction remains closed for v1; no UP/DOWN UI, no directional badge, and
the conditional diagnostic remains evidence-appendix only. *(Corrected 2026-07-11 per the
owner evidence review — the original card wrongly said "no argmax directional calls"; the
baselines made zero calls, the model made 102. Documentation correction only; the gate
outcome is unchanged.)*

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
volatility/regime model rather than a directional one. **Attribution is last-fold diagnostic
only, not a stable global feature-importance claim** (owner evidence review, 2026-07-11).
Per-projection drivers are exact coefficient×value attributions (FR-008); the LLM formatter
does not exist until §4 and is flag-off by design.

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

## OWNER DECISION — 2026-07-10 (gate item 5 adjudicated)

**Accept item 5. Proceed to §4. Do not stop at §3. Do not switch to the ensemble. Do not make
directional claims. Do not claim stress-regime validation.** The 2022 result is a warning, not
disqualifying: the model is not catastrophically worse in stress, the down-trend slice is a
wash, and the primary frozen gate passed with a real, pre-registered threshold that finally
produced usable coverage. The correct response is limited validation, not rejection.

### Approved claim (exact product/evidence framing)

> **Validated Move-Risk Projection — Primary Horizon Only**
>
> The model identifies days with elevated probability of a material market move.
> Direction is uncertain.
> Evidence is strongest in benign/up-trending regimes.
> Stress-regime reliability is not yet established.

Forbidden wording (in addition to NFR-006): *predicts market direction · predicts crashes ·
works in bear markets · trading signal · buy/sell indicator*.

### Regime limitation (owner-required wording)

> **Regime limitation:** The §3 validation pass is concentrated in benign/up-trending regimes.
> The 2022 bear-year slice favored the baseline, and down-trend days were approximately a
> wash. Therefore the model is validated only as a primary-horizon elevated move-risk
> projection, not as a stress-regime or bear-market predictor.

### Dispositions

- **Ensemble**: Brier 0.2308, lower (better) than the primary logistic's 0.2338. *Sensitivity
  only. Candidate for a future pre-registered MKT-PROJ-002, not for MKT-PROJ-001 promotion.*
  Switching now would be tuning.
- **Direction**: closed for v1. Failed the sample floor; no directional badge, no UP/DOWN UI,
  no directional model-card claim. The conditional diagnostic stays in the evidence appendix
  only.
- **Secondary horizon (PRE_OPEN)**: no claim of any kind; not served.

### §4 conditions (owner-frozen scope)

Build only around: *"Elevated move risk; direction uncertain."*
**Allowed:** inference job · API endpoint · Research Preview card · outcome tracking ·
calibration-drift monitoring (CEE) · 30-day train/serve diagnostic · model card ·
primary-horizon elevated move-risk label.
**Not allowed:** order path · ranking · sizing · portfolio construction · directional call ·
secondary-horizon claim · ensemble substitution · threshold tuning · LLM-generated market
explanation (any narrative shown is templated and model-card-approved; LLM prose stays off).

**§4 guardrails (owner-required):** (1) freeze the logistic artifact + threshold; (2) serve
only the primary horizon; (3) show only "Elevated move risk; direction uncertain"; (4) track
realized outcomes for every served prediction; (5) monitor calibration drift through CEE;
(6) report regime slices monthly (uptrend/downtrend/high-vol/low-vol/stress-like);
(7) stress-regime caution in the model card (above); (8) disable or downgrade the card if the
train/serve diagnostic drifts materially.

**Final verdict of record:** *Validated: primary-horizon elevated move-risk probability.
Not validated: direction, secondary horizon, stress-regime prediction, trading use.*
The §4 model-card/API/UI plan returns to the owner before any user-visible card is built.
