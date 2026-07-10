# MKT-PROJ-001 — §2 Baselines-Only Evidence (owner checkpoint before §3 ML)

| Field | Value |
|---|---|
| Date | 2026-07-10 |
| Stage | §2 walk-forward, all six pre-registered baselines, **no ML exists** |
| Pre-registration | v1.2 (FROZEN) |
| Dataset | 5,288 rows persisted (feature_version `mktproj-fv1`; 2016-01-04 → 2026-07-10; ~2,622 valid per horizon; exclusions: 19 ATR warm-up, 2 missing-features, 1 unmatured) |
| Walk-forward | 15 folds; OOS = 1,868/1,869 days (2019-02-01 → 2026-07) |
| Artifacts | `baseline_walkforward_PRE_CLOSE_TOMORROW.json` · `baseline_walkforward_PRE_OPEN_TODAY.json` (this dir) |
| Note | AUC regenerated after the midrank fix (#413) — the first run's tied-score AUCs were artifacts |

## PRE_CLOSE_TOMORROW (primary) — labels: 63.3% NEUTRAL / 21.3% UP / 15.4% DOWN

| Baseline | Brier (MATERIAL)† | ECE | AUC | Elevated coverage | Cond. dir. on material |
|---|---|---|---|---|---|
| always_neutral | 0.4031 | 0.4031 | 0.500 | 0% | 0.578 |
| unconditional | 0.2458 | 0.0605 | 0.477 | 0% | 0.578 |
| prior_day_direction | 0.2458 | 0.0605 | 0.477 | 0% | 0.578 |
| momentum_5d_direction | 0.2458 | 0.0605 | 0.477 | 0% | 0.578 |
| **vol_clustering_move_risk** | **0.2405** | **0.0193** | 0.540 | 0% | 0.578 |

## PRE_OPEN_TODAY (secondary, open-to-close) — 74% NEUTRAL / 13.3% UP / 12.7% DOWN

Best: **vol_clustering_move_risk** — Brier 0.2050 (vs 0.2105 unconditional), ECE 0.027, AUC
0.561. The premarket-gap direction baseline adds nothing over unconditional (AUC 0.500).

† Single primary Move-Risk metric (pre-reg v1.2 §3). Log-loss (clipped) ordered identically.

## What this says (the "how hard is the target" answer)

1. **The bar the §3 model must beat: Brier 0.2405** (primary horizon). Volatility clustering
   is the only baseline with genuine signal — better Brier, much better calibration
   (ECE 0.019), and weak-but-real discrimination (AUC 0.54). The other baselines collapse to
   class rates.
2. **Direction is at base rates, as the design predicted.** Zero argmax directional calls
   from any baseline (§14 floor unmet ⇒ `insufficient_sample` everywhere), and the
   conditional-direction diagnostic equals the UP base rate exactly (0.578 = UP share of
   material days) — i.e. no baseline knows anything about direction beyond drift.
3. **The coverage gate binds hard.** With the frozen call threshold P(MATERIAL) ≥ 0.5 and a
   36.7% material base rate, **no baseline ever makes an elevated call** (coverage 0%). For
   the §3 model to pass Move-Risk validation it must genuinely concentrate probability above
   0.5 on 10–60% of days — hugging the base rate (how vol-clustering earns its calibration)
   cannot pass. This is the frozen design working as intended, and it means the realistic §3
   Move-Risk outcome is also demanding, not just direction.
4. Nothing here was tuned; one run per the freeze.

## Decision requested (plan owner-gate 3)

**Stop or go into §3 ML?** Go = train the frozen calibrated logistic (+ secondaries) against
the 0.2405 Brier bar with the coverage/ECE gates as frozen. Stop = the baseline story already
suggests Move-Risk validation is unlikely to clear coverage, and the program could conclude at
§2 as evidenced-Inconclusive without ML/UI spend. The §3→§4 gate (no UI without a reviewed
model card) remains either way.
