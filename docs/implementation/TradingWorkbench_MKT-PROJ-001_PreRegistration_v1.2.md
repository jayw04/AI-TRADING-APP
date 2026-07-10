# MKT-PROJ-001 — Pre-Registration v1.2 (FROZEN)

| Field | Value |
|---|---|
| Program | MKT-PROJ-001 — Market Projection Engine |
| Capability | CAP-027 — Market Projection Engine (display-only decision support) |
| Date | 2026-07-10 |
| Status | **FROZEN 2026-07-10 — owner final review (9.5/10) approved the freeze after its 7 pre-freeze edits. v1.1 amendment (owner-provided, same day, BEFORE any validation run existed): the §6a missing-value rule. §1 complete; §2 authorized.** |
| Governing docs | Design v0.2 (`Docs/design/TradingWorkbench_MarketProjectionEngine_RequirementsDesign_v0.2.md`) · Implementation plan v0.2 · Owner reviews 2026-07-10 (plan 9.2/10, final 9.5/10 — both snapshotted alongside) |
| Registered before | any model training, any validation run (v1.0 preceded the dataset build; v1.1 precedes any §2 run) |
| Amendments | v1.0→v1.1 (2026-07-10): added §6a missing-value rule, owner-frozen verbatim. v1.1→v1.2 (2026-07-10, owner approval message): confirmed the expanded structurally-missing enumeration + unexpected-missingness-is-a-data-quality-failure clarification (§6a); froze the elevated-call definition P(MATERIAL) ≥ 0.5 with a no-later-tuning prohibition (§3); confirmed the §14 floor is unrescuable by the conditional diagnostic (§3). No validation output existed at any amendment time — nothing invalidated (§10.3). |

Everything in this document is frozen **before** the first training row is built. Nothing here
may change after validation results are seen; a change requires a new pre-registration version
and restarts the affected evidence.

---

## 1. Frozen primary configuration

```text
Market proxy:    SPY
Horizon:         PRE_CLOSE_TOMORROW
Target:          SPY close(t+1) vs SPY close(t)
Labels:          UP / DOWN / NEUTRAL (strict enum; display phrases are not labels)
Feature set:     historically validated PIT features only (manifest §5)
Primary model:   calibrated logistic regression (§6)
Validation:      walk-forward only (§7)
Binding baseline: best of the pre-registered baselines (§4), per metric
```

Secondary/sensitivity (reported, never the gate): QQQ proxy · PRE_OPEN_TODAY horizon
(open-to-close target) · fixed ±0.75% threshold · magnitude-only model ·
HistGradientBoosting + simple average ensemble · SCAN/GAPPER shadow model (§9).

## 2. Frozen label rule

```text
threshold_asof_forecast_date = max(0.60%, 0.50 × ATR20_pct)
```

where `ATR20_pct` is computed **through the last fully completed regular session before the
forecast timestamp**:

- PRE_OPEN_TODAY (forecast 09:20 ET): ATR through prior close; target = SPY close(t) vs SPY
  regular-session open(t) — open-to-close, never close-to-close.
- PRE_CLOSE_TOMORROW (forecast close−15m): ATR **through t−1**; today's still-forming bar is
  never an ATR input. Target = close(t+1) vs close(t).

```text
realized_return >= +threshold → UP
realized_return <= −threshold → DOWN
otherwise                     → NEUTRAL
```

Half days use the actual early close (via `MarketSession`). Closed days produce no row.
Data-quality exclusions are recorded (`valid_for_training=false` + reason), never silently
dropped.

## 3. Frozen verdict gates

**Move-Risk Gate — "Validated Move-Risk Projection" requires ALL of:**

1. **Primary metric (single, no multiple-testing loophole): Brier score** for P(MATERIAL)
   improves versus the best pre-registered magnitude baseline. Log-loss, ECE, and the
   reliability curve are secondary/diagnostic only.
2. block-bootstrap CI on the Brier improvement excludes zero;
3. **calibration guardrail (numeric):** ECE must not be worse than the best pre-registered
   magnitude baseline's ECE by more than **0.02**; the reliability curve is reviewed as a
   diagnostic;
4. **coverage (numeric):** elevated-move-risk calls on **10%–60% of OOS days**, otherwise the
   Move-Risk verdict is `Inconclusive / insufficient coverage` (a model that never calls risk,
   or always calls it, cannot pass). **Elevated move-risk call = P(MATERIAL) ≥ 0.5** (v1.2,
   owner-frozen pre-evidence); this threshold **must not be tuned later to satisfy the
   coverage gate**;
5. no major regime failure (§7 slices reviewed).

**Direction Gate — "Validated Direction Projection" requires ALL of:**

1. directional precision on non-neutral calls beats the best pre-registered directional
   baseline;
2. CI on the directional precision uplift excludes zero;
3. sample floor met: ≥100 non-neutral OOS calls with ≥50 UP and ≥50 DOWN — otherwise the
   directional verdict is the literal `insufficient_sample` and no directional CI is computed
   or displayed anywhere. Directional calls are argmax-based and therefore honestly sparse on
   a majority-NEUTRAL target; **if the floor is not met, no directional skill claim is
   allowed — the §7.2 conditional-direction diagnostic is reported for interpretation only
   and cannot rescue a failed floor** (v1.2, owner-confirmed);
4. false-positive rate bounded (reported vs baselines; reviewed);
5. no major regime failure; model stable across time windows.

**Product rule:** Move-Risk Gate alone ⇒ badge "Validated Move-Risk Projection", strongest
wording "Elevated move risk; direction uncertain", and never "Validated UP/DOWN projection".
Only the Direction Gate unlocks "Validated Direction Projection". Until a gate clears, the
badge is **Research Preview**. Realistic prior: Rejected/Inconclusive on direction; that is a
successful Evidence Engineering outcome, not a failure.

## 4. Frozen baselines (all six; the gate compares against the best per metric)

1. **Always-Neutral** — P(NEUTRAL)=1.
2. **Unconditional frequencies** — training-window class rates as constant probabilities.
3. **Prior-day direction** — sign(close(t)−close(t−1)) predicts the same class with the
   training-window hit-rate as its probability; NEUTRAL per unconditional rate.
4. **5-day momentum direction** — sign of the 5-day return, same probability construction.
5. **Volatility-clustering move-risk** — P(MATERIAL) = training-window material-day frequency
   within the current ATR20_pct quintile (direction split per unconditional rates).
6. **Premarket gap direction** (PRE_OPEN_TODAY only) — sign of the 09:20 SPY gap.

## 5. Frozen production feature manifest (feature_version = `mktproj-fv1`)

All features PIT as-of the forecast timestamp; every function passes the truncated-vs-full
equality test. Sources: Alpaca (SIP-historical for training, IEX-live for inference — recorded
per run; first-30-live-days train/serve drift diagnostic per the plan).

**PRE_OPEN_TODAY (as of 09:20 ET):** `spy_gap_pct_qf`, `qqq_gap_pct_qf`, `iwm_gap_pct_qf`
(quality-flagged: source + premarket print count), `spy_ret_1d`, `spy_ret_5d`,
`spy_realized_vol_20d`, `atr20_pct`, `spy_dist_ma20`, `spy_dist_ma50`, `spy_dist_ma200`,
`regime_trend` (above/below 200dma), `regime_vol` (ATR quintile).

**PRE_CLOSE_TOMORROW (as of close−15m; every intraday feature uses ONLY data through
close−15m — no final-session high/low/close may leak):** `spy_intraday_ret`,
`qqq_intraday_ret`, `iwm_intraday_ret` (open→close−15m), `spy_late_day_ret`
(14:30→close−15m), `sector_breadth` (share of the 11 SPDRs positive open→close−15m),
`up_sector_count`, `sector_coverage_count` (XLRE from 2015-10, XLC from 2018-06 — missing
sectors shrink the denominator, never fake zeros), `spy_volume_vs_20d_tod` (**cumulative
volume through close−15m ÷ the 20-prior-session average of cumulative volume through the same
time of day** — the time-of-day-matched definition, not full-day average), `spy_intraday_vol`
(5-min realized, through close−15m), `spy_hl_range_pct` (high/low **through close−15m only**),
`fade_recovery` (price at close−15m positioned within the range **through close−15m only**),
plus the PRE_OPEN daily set (`spy_ret_1d/5d`, `spy_realized_vol_20d`, `atr20_pct`,
`dist_ma*`, regimes).

Sector basket frozen: XLK XLF XLV XLE XLI XLY XLP XLU XLB XLRE XLC.

No other feature may influence displayed production probabilities. Adding a feature = new
`feature_version` + new walk-forward evidence.

## 6. Frozen models & hyperparameters (no tuning after results — one run)

- **Primary:** `LogisticRegression(C=1.0, penalty="l2", max_iter=1000, class_weight=None)` on
  standardized features, Platt-calibrated.
- **Secondary:** `HistGradientBoostingClassifier(max_iter=200, learning_rate=0.1,
  early_stopping=False, random_state=42)`, isotonic-calibrated; simple average ensemble of the
  two calibrated models.
- **Calibration is time-respecting only:** within each training window, the base model fits on
  the earlier 80%, calibration fits on the final contiguous 20%; the test fold is strictly
  future. **Random/non-temporal K-fold calibration is forbidden for the primary evidence run.**
- Seed 42 everywhere; artifacts hashed; git commit recorded (NFR-002).

### 6a. Missing-value rule (v1.1 amendment — owner-frozen 2026-07-10, verbatim)

> For numeric features with missing values, impute using the median fitted on the training
> window only, then apply standardization fitted on the same training window only. The fitted
> imputer and scaler are carried forward to the validation/test window. No validation/test data
> may influence the imputation or scaling parameters.
>
> For structurally missing premarket-quality fields stored as None by design, add a
> pre-registered binary missingness indicator per affected feature before imputation, so the
> model can distinguish "median-like value" from "not observed / zero-quality premarket gap."
> The imputed numeric value remains the train-window median.
>
> No target-aware, full-sample, cross-window, or post-hoc imputation is allowed.

Pre-registered missingness indicators (the enumeration of "per affected feature" for the
structurally-None-by-design fields; derived by the pipeline from observed None-ness at both
train and inference time — not stored in `features_json`, so `feature_version` is unchanged):

```text
spy_gap_missing, qqq_gap_missing, iwm_gap_missing        (zero-quality premarket gap)
spy_late_day_ret_missing                                  (half days: 14:30 > close−15m)
spy_volume_vs_20d_tod_missing                             (20-session baseline warm-up)
```

The first three are the owner-named premarket-quality fields; the last two apply the same
principle to the only other fields that are None *by design* rather than by data error.
This enumeration was owner-confirmed (v1.2) with the clarification: **only these
pre-enumerated structurally-missing fields are imputed this way; unexpected missingness in
any other required feature is a data-quality failure** — the row is excluded
(`valid_for_training=false` historically; "Projection unavailable" live), never silently
imputed.

## 7. Frozen validation design

- History: Alpaca ~2016-07 → present (~10y accepted; power caveat: if OOS folds or floors
  prove inadequate, Direction = Inconclusive / insufficient power — **data is never expanded
  after seeing results**).
- Walk-forward: anchored expanding window; first train window ≥3 years; test fold 6 months;
  roll 6 months; all OOS folds pooled.
- CIs: stationary block bootstrap on OOS days, block length 10 trading days, 2,000 resamples,
  95% two-sided.
- Regime slices (reviewed, not numerically gated): calendar year; realized-vol halves;
  above/below 200dma.
- Metrics exactly as design §13, magnitude and direction always reported separately. The
  Move-Risk gate metric is Brier (single primary); log-loss is secondary and computed with
  probabilities **clipped to [1e-6, 1−1e-6]** so deterministic baselines (Always-Neutral)
  cannot produce infinite log-loss.

## 8. Frozen display policy

Confidence mapping per design §18 (HIGH ≥0.60 & gap ≥0.15; MEDIUM ≥0.50 & gap ≥0.08; else
LOW). UI designed for mostly-LOW; LOW and "Projection unavailable" are normal states.
Vocabulary per NFR-006; the §4 card PR does not merge without the advice-adjacent wording
review. Naming: Market Projection Engine/Card/API — never "Market Intelligence".
LLM prose: built, `WORKBENCH_MKTPROJ_LLM_EXPLAIN=false` by default; formats the computed
attribution payload only.

## 9. Frozen shadow policy (SCAN/GAPPER)

Shadow features (`native gapper files, SCAN candidate counts, Discovery Confidence
distributions, GAPPER shadow-ledger metrics, live-only opportunity-report features`) live in
`shadow_features_json` and a separate shadow model id. They never influence displayed
probabilities; shadow results appear only in internal evidence reports until a separate
forward-evidence gate is met. Expectation: **6–12 months of forward observations** before any
serious shadow evidence claim. Promotion requires its own pre-registered gate.

## 10. Stopping rules & checkpoints

1. **§0 → §1:** owner confirms this freeze.
2. **§2 → §3 (baseline-only checkpoint):** after the baselines-only walk-forward run, the owner
   decides whether ML (§3) proceeds. Baselines showing pure noise / inadequate floors is a
   legitimate early stop.
3. No parameter, feature, threshold, window, or baseline changes after any validation output
   has been seen. Amendments require a new pre-registration version and invalidate affected
   results.

## 11. Evidence artifacts (design FR-012)

`docs/implementation/evidence/mkt_proj_001/`: this pre-registration · data-audit JSON ·
feature/label definitions (code-referenced) · training + validation scripts
(`scripts/research/mkt_proj_001/`) · walk-forward result JSON · result markdown · decision
summary · model card · train/serve drift report (first 30 live days).
