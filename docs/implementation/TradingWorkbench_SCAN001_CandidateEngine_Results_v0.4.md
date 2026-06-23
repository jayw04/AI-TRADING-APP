# SCAN-001 — The Confidence Model: Results (v0.4)

| Field | Value |
|---|---|
| Document version | v0.2 (results — executed against the frozen v1.1 plan; folds the v0.11 review: + methodology diagram) |
| Date | 2026-06-23 |
| Program | SCAN-001 (Market Opportunity Discovery Engine — first profile of the Discovery Lab) |
| Type | Platform Capability · **Capability Maturity:** L3 (Operating Envelope Defined) — *unchanged by this study* |
| Plan | `TradingWorkbench_SCAN001_CandidateEngine_Plan_v0.4.md` (v1.1, FROZEN, owner-approved 2026-06-23) |
| Evidence | `evidence/scan_001_candidate_engine_v0_4/` (JSON + MD), seed 17, circular-block bootstrap n=2000 |
| Verdict | **CONFIDENCE-UNINFORMATIVE (on the pre-registered primary metric)** — the per-candidate confidence does **not** predict ATR-normalized expansion; it is mildly **inverse**. A pre-registered negative — the platform declines again. |

> **Headline in one line:** the engine's per-candidate **confidence number does not predict the expansion
> ratio `E`** — in fact higher-confidence names expand *less* relative to their own ATR. Per the frozen §4
> decision matrix (with `E` as the primary outcome, OQ2), that is **CONFIDENCE-UNINFORMATIVE**. The Confidence
> Model, as the pre-registered `Opportunity × Discovery` product over `E`, **is not shipped as a ranking key.**
> Two honest companion findings sharpen, not soften, the verdict (§3).

### The methodology in one picture

This result is the Evidence-Engineering loop run to a *negative* — and shipped anyway:

```
   Hypothesis ("confidence predicts expansion")
        │
        ▼
   Pre-registration  ──►  Frozen metrics & decision matrix  ──►  Expanding-Window PIT execution
        │                       (E primary, OQ2; §4)                     (anti-circularity)
        ▼
   Negative result  ── H-conf-1 fails: confidence is inverse to E ──►  Feature NOT shipped
        │                                                                (confidence stays explainability,
        ▼                                                                 not a ranking key)
   Forward guidance  ──►  v0.5 named (CM-targeted confidence), NOT a post-hoc rescue of v0.4
```

The same picture, abstracted, is why a customer/investor/patent reviewer can trust the platform: *frozen
criteria in, honest verdict out, the declined feature preserved as a record.*

---

## 1. What was tested (recap of the frozen design)

The Confidence Model decomposes into two levers (plan §0), tested separately:

- **Lever A — per-candidate `opportunity_confidence`** (within-day; the only term that re-ranks candidates inside
  a day). **H-conf-1:** does higher confidence predict larger realized expansion `E = intraday range / own ATR`?
- **Lever B — per-day `discovery_confidence(regime_today)`** (cross-day throttle), computed **point-in-time**
  over an expanding window of prior days only (plan §1b; 3-y warm-up, 60-day per-regime floor). **H-conf-2/3b:**
  do higher-confidence *days* carry larger candidate edge?

Primary outcome `E` (frozen OQ2); `CM = capturable move %` as companion. Two cuts: HEADLINE (top-200,
2010–2026, 3,826 scored days, 180 warm-up) and RECENCY (top-500, 2021–2026, 1,057 days). All CIs are seeded
circular-block bootstrap (n=2000).

---

## 2. Lever A — the per-candidate calibration FAILED (mildly inverse)

**The calibration curve — the readable test.** Realized `E` by confidence band (pooled candidates, terciles):

| Confidence band | HEADLINE `E` | HEADLINE `CM` | RECENCY `E` | RECENCY `CM` |
|---|---|---|---|---|
| **Low** | **1.434** | 4.472 | 1.503 | 4.713 |
| **Medium** | 1.094 | 4.391 | 1.509 | 6.201 |
| **High** | **0.916** | 4.621 | 1.338 | 6.944 |

- **H-conf-1 (E):** monotone Low<Med<High = **False** on both cuts. High−Low edge **−0.4505**, CI
  [−0.486, −0.415], p=1.0 (headline); **−0.0834**, CI [−0.144, −0.019] (recency). Both CIs are **below zero** —
  the relationship is **significantly inverse**, not merely flat. → **NOT SUPPORTED.**
- **H-conf-3a (top-8 of top-15 by confidence):** confidence-ranked selection *underperforms* the flat book on
  `E` — Δ **−0.113**, CI [−0.122, −0.104] (headline, significant); Δ −0.010, CI [−0.025, +0.004] (recency, spans
  0). → **NOT SUPPORTED.** Picking the *highest-confidence* names is, if anything, picking the *lower-expansion*
  names.

**Why — and it is a real mechanism, not a bug (the v0.1 lesson, again).** `E` is **ATR-normalized**
(range ÷ own ATR), while `opportunity_confidence` is partly **ATR-magnitude-driven** (a name clears the ATR
signal by a wide margin precisely when its ATR is large). A high-ATR name has a large denominator, so its
range-to-ATR *ratio* compresses; a name that *barely* qualifies (low ATR, low confidence) can post a range that
is a large multiple of its small ATR. So `E` structurally **rewards low-ATR names** and confidence **rewards
high-ATR names** — they pull in opposite directions. This is the same numerator-vs-denominator insight that
caught the v0.1 prototype's ATR tautology, resurfacing in the confidence layer.

---

## 3. Two honest companion findings (sharpen the verdict; they do NOT rescue it)

These are reported under the methodology's discipline: the primary metric and decision matrix were frozen
(`E`, §4) **before** the run. The observations below are **exploratory** and become *separately pre-registered*
hypotheses for a future iteration — they are **not** used to overturn the frozen verdict.

### 3a. Confidence DOES track *absolute* move size (`CM`), just not vol-normalized expansion

The companion `CM` (capturable move %, **not** ATR-normalized) **rises** with confidence on the recency cut —
**4.71 → 6.20 → 6.94** monotone — and is flat-with-an-uptick on the headline cut (4.47 → 4.39 → 4.62). So the
confidence number is **not** noise: it predicts *how big the move is in percent*, it simply does **not** predict
*expansion relative to the name's own already-elevated volatility*. **Forward hypothesis (to pre-register):** a
confidence calibrated against `CM` (absolute opportunity size) — or an expansion metric normalized differently —
may calibrate where the ATR-ratio one does not. This is the natural v0.5 question.

### 3b. Lever B (regime Discovery Confidence) is weakly but CORRECTLY signed

- **H-conf-2 (forward calibration):** covariance(confidence, daily edge) is **positive and CI-separated on both
  cuts** — 0.0007, CI [0.0002, 0.0011] (headline); 0.0036, CI [0.0005, 0.0070] (recency). Higher-confidence
  *regime days* do carry larger candidate edge. → **SUPPORTED**, but small.
- **H-conf-3b (throttle):** edge-per-exposure barely moves — 0.2074 vs flat 0.2069 (Δ +0.0006); mean exposure
  0.977. Exactly the **pre-registered "expected small"** outcome: v0.3 found the engine REGIME-ROBUST
  (confidence band 0.91–1.00), so there is almost nothing to down-weight.
- **Caveat (honest):** the *readable* median-split is **degenerate on the recency cut** — confidence saturates
  at 1.0, so "strictly above median" captures 0 days (the `high_conf_edge = 0.0` artifact in the JSON). The
  covariance test is the valid Lever-B read; the median split is only interpretable on the headline cut
  (high-conf days edge 0.233 vs low-conf 0.187).

---

## 4. Verdict against the frozen decision matrix (plan §4)

| Frozen outcome | Hit? |
|---|---|
| H-conf-1 holds + H-conf-3a positive → **Confidence-Calibrated** | No |
| H-conf-1 holds, regime-flat → **Calibrated within-day, regime-flat** | No (H-conf-1 itself fails) |
| **H-conf-1 fails (E flat/inverse across terciles) → CONFIDENCE-UNINFORMATIVE** | **Yes** |
| Any lift negative, CI-separated → **Counter-productive** | Partially (3a is significantly negative on the headline cut) |

**→ Frozen verdict: CONFIDENCE-UNINFORMATIVE.** Per the matrix's pre-registered consequence: *rank candidates by
signal **count**, not confidence magnitude; the bounded confidence stays as an **explainability** artifact, not
a sizing/ranking input.* The `Opportunity × Discovery` product is **not** promoted as the candidate rank key.

**What is unchanged.** The v0.2 **Validated** and v0.3 **Operating-Envelope (REGIME-ROBUST, L3)** verdicts
**stand** — v0.4 tested *how to weight* the already-validated candidate set and found the confidence magnitude is
not a good weight for expansion. **Capability Maturity stays L3.** v0.4 does **not** advance SCAN toward L4 (that
path needed a calibrated confidence *plus* the premarket-data gate); it removes one candidate mechanism and
names the better one (§3a).

---

## 5. Lessons & forward direction

1. **The platform declined again — on its own proposed feature.** The Confidence Model was a *named,
   pre-registered* v0.4 deliverable; the evidence said the confidence magnitude doesn't predict `E`, so it is not
   shipped. This is the RNG-001 pattern at the capability layer: *a plausible mechanism, pre-registered, failed
   its bar, and the decline is the asset.*
2. **The v0.1 tautology lesson generalizes.** Any metric that normalizes by ATR will fight a selection/confidence
   signal that rewards ATR. Future expansion metrics must be designed against this coupling explicitly.
3. **The signal is in `CM`, not `E`-magnitude.** Confidence predicts *absolute* opportunity size. The natural
   **v0.5** pre-registration: a `CM`-targeted (or differently-normalized) confidence calibration — a *new*
   hypothesis, not a re-cut of this run.
4. **Lever B is directionally real but has no headroom.** Regime Discovery Confidence forward-calibrates, but
   because the engine is REGIME-ROBUST the throttle is ~0. Keep the v0.3 heatmap as *robustness evidence*, not a
   live throttle.

---

## 6. Honest scope (carried from the harness)

- **PIT confidence is a normal-approx** of v0.3's block bootstrap (an expanding-window bootstrap per day is
  prohibitive); the blend/branch logic is identical to v0.3.
- Lever B throttles on the **market regime** (bull/bear/sideways); the vol axis is left to v0.3's heatmap.
- Within a day the composite rank equals the opportunity-confidence rank (Lever B is constant per day) — by
  design; Lever B only weights across days.
- Lift is **evidence-layer** (expansion edge / edge-per-exposure), never a P&L backtest — the premarket-data
  gate (PR #221) stays the hard prerequisite before any live use.
- Survivorship-biased universe (today's liquid names) — read effects as relative.

*Reproduce:* `PYTHONPATH=apps/backend .venv/Scripts/python.exe apps/backend/scripts/candidate_engine_v0_4.py
--store apps/backend/data/factor_data_full.duckdb --end 2026-06-12 --bootstrap 2000 --report-dir
docs/implementation/evidence/scan_001_candidate_engine_v0_4` (seed 17).
