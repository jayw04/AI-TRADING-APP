# SCAN-001 — The Confidence Model: Research Plan & Pre-Registration (v0.4)

| Field | Value |
|---|---|
| Document version | v1.1 (FROZEN for execution — owner approved 2026-06-23; folds 3 review refinements: explicit success-if-Lever-B-weak, Capability-Maturity note, Low/Med/High customer artifact) |
| Date | 2026-06-23 |
| Program | SCAN-001 (Market Opportunity Discovery Engine — first profile of the Discovery Lab) |
| Type | Platform Capability · **Capability Maturity:** L3 (Operating Envelope Defined) → step toward **L4** |
| Predecessor | v0.3 results (`..._CandidateEngine_Results_v0.3.md`, tag implied by #234/#235) — REGIME-ROBUST; Discovery-Confidence heatmap produced |
| Successor | premarket-data gate (PR #221 replication) + v1.0 production — both still owner-gated, out of scope here |
| Repository | github.com/jayw04/AI-TRADING-APP |
| Scope | Turn the v0.3 Discovery-Confidence heatmap into a **calibrated, composable confidence number** and test whether confidence actually predicts realized outcome — the bridge from "the engine works here" to "weight candidates by how much we trust today's signal." |
| Estimated wall time | Plan: this doc. Build+run: 5–8 h (engine helpers + harness + a ~16-y expanding-window replay + bootstrap). |
| Tag on completion | `scan-001-v0.4-complete` (after results + registry update) |
| Out of scope | Premarket-data integration, live use, intraday entry/exit, sizing/risk wiring, any change to the frozen selection engine (ATR+Gap+RVOL, top-15). |

> **The question v0.4 answers: *does the confidence number mean anything?*** v0.1–v0.3 always tested
> **candidate vs. baseline** — "the selected set out-expands the field." They never tested whether, *within*
> the selected set, a candidate's **confidence** predicts *which* candidates expand more, nor whether the
> per-day **Discovery Confidence** predicts *which days* the edge is larger. v0.4 is a **calibration** study:
> it asks whether confidence is informative (a usable ranking/sizing input) or merely decorative. Only if it
> calibrates does the pre-registered formula `Opportunity × Discovery-Confidence` earn its place.

---

## 0. Why v0.4 (and the load-bearing subtlety)

The v0.3 results doc named the direction precisely:

> `Candidate Opportunity Score × Discovery Confidence(regime_today) = regime-aware Candidate Rank` — "down-weight candidates automatically when today's regime is weak."

**The subtlety that shapes this whole study:** `Discovery-Confidence(regime_today)` is a *single value per day* —
the same multiplier for every candidate on that day. Multiplying every candidate's score by one constant **does
not reorder candidates within a day**. So the formula decomposes into two genuinely separate levers, and v0.4
must test them separately or the attribution is meaningless (the same H3-attribution discipline that
de-tautologized v0.2):

- **Lever A — within-day (per-candidate):** the engine's existing `opportunity_confidence` (strength over the
  ATR/Gap/RVOL thresholds, already in `candidate_engine.py`). This is the *only* term that re-ranks candidates
  *within* a day. **Never tested for calibration.**
- **Lever B — cross-day (per-regime):** `Discovery-Confidence(regime_today)` from the v0.3 heatmap. This term
  cannot reorder within a day; it can only **down-weight whole days** (an exposure/participation throttle).

**Honest headroom caveat, pre-registered:** v0.3 found the engine **REGIME-ROBUST** — confidence sits in a narrow
`0.91–1.00` band with *no* no-go regime. So Lever B's modulation is small by construction (≈10%); the regime
throttle has little to bite on. We expect, before running, that **Lever A carries most of any usable signal**,
and we say so now so a weak Lever B result reads as *"the engine is robust, as v0.3 found,"* not as a failure.

> **Success definition when Lever B is weak (pre-registered, owner-confirmed):** v0.4 is a **success** if
> **H-conf-1 calibrates (Lever A)** even when H-conf-2/3b are flat. A weak regime throttle is read as
> *"broadly robust — no day needs heavy down-weighting,"* a restatement of the v0.3 REGIME-ROBUST verdict, **not**
> a failure of the Confidence Model. The model fails *only* if the per-candidate confidence (Lever A) is itself
> uninformative (§4, "Confidence-Uninformative").

**Capability Maturity (pre-registered):** if v0.4 lands **Confidence-Calibrated**, SCAN-001 advances from **L3
(Operating Envelope Defined)** *toward* **L4 (Production-Ready)** — but **L4 is not reached here**: it stays
gated on the **premarket-data replication** (PR #221) + a live-data run. v0.4 completes the *research* side of
the path to L4; it does not itself promote the capability.

- **It is:** a calibration + composability study on the *already-validated, already-mapped* edge.
- **It is not:** a re-validation (v0.2 settled that), an Operating-Envelope re-map (v0.3 settled that), a
  parameter search, or a live signal. The selection engine is **frozen**.
- **Honest fork it allows:** if confidence does **not** calibrate (outcome flat across confidence bins), v0.4's
  citable finding is *"the confidence number is not predictive — use the candidate set unweighted"* — a real,
  publishable boundary on the capability, not a failure to hide.

---

## 1. The Confidence Model (frozen definitions, set BEFORE any outcome is seen)

### 1a. Per-candidate opportunity confidence — already frozen (v0.2)

`opportunity_confidence ∈ [0,1]` is the engine's existing `confidence()` — the mean, over the cleared signals,
of how far each clears its threshold (1× → 0.0, ≥2× → 1.0). **Unchanged.** v0.4 only *tests* it.

### 1b. Per-day Discovery Confidence — PIT, expanding-window (the anti-circularity rule)

The v0.3 heatmap confidence was computed **in-sample** over 2010–2026 (the formula
`0.5·(1−p) + 0.5·normalized_edge_magnitude`). Using that number to then "predict" the same period's edge would
be **circular**. v0.4 fixes this with a strict point-in-time rule:

> On scan day *t*, `Discovery-Confidence(regime_today)` is computed **only from days strictly before *t***,
> bucketed by the same frozen regime classifier, using the same frozen v0.3 confidence formula. The test day's
> own outcome never enters its own confidence.

- **Warm-up:** the first **3 years** of the window are *training only* — no test rows emitted until each regime
  has ≥ the v0.3 minimum (60 days) of prior history. Days whose regime is still under-sampled emit
  `Discovery-Confidence = neutral (1.0)` (no down-weight) and are flagged.
- This makes Lever B a genuine **forward** test: does a regime-confidence fit on the past predict the future?

### 1c. The composite (frozen formula)

```
final_confidence(candidate, day) = opportunity_confidence(candidate)        # Lever A, [0,1], within-day
                                  × discovery_confidence(regime_today, t)    # Lever B, [0,1], PIT, per-day
```

Product of two `[0,1]` terms → `[0,1]`. Frozen here; no tuning. (A pre-registered robustness variant —
geometric vs. weighted-arithmetic blend — is **descriptive only**, §6, never elevated to the verdict.)

---

## 2. Frozen hypotheses

Outcome metrics are the v0.2 post-open **expansion ratio** `E` (primary) and **capturable move** `CM`
(tradeability companion) — both realized, never fed back into selection. All bootstraps reuse the seeded (17),
circular-block `evidence.py` machinery.

### H-conf-1 — Per-candidate confidence calibration *(Lever A; the core new test)*

> Among selected candidates, higher `opportunity_confidence` predicts larger realized expansion `E`.

- **Test:** bin candidates into confidence **terciles** (low/mid/high) pooled across all scan days; the realized
  `E` is **monotonically increasing** across terciles, and the **high−low** difference has a 95% bootstrap CI
  excluding 0.
- **Holds** if monotone + high−low CI-separated. **Fails** if `E` is flat across terciles (CI spans 0) →
  confidence is decorative for ranking.

### H-conf-2 — Per-day Discovery-Confidence forward calibration *(Lever B)*

> Across scan days, the PIT `Discovery-Confidence(regime_today)` (§1b) is positively associated with that day's
> realized candidate edge `E_candidate − E_baseline`.

- **Test:** split days into high vs. low PIT Discovery-Confidence (median split); the candidate edge is larger in
  the high-confidence half, **high−low** CI excludes 0. Reported with the honest-headroom caveat (§0): the band
  is narrow because the engine is regime-robust, so a small or non-separated effect is the *expected* read, not a
  refutation of the engine.

### H-conf-3 — Composite lift *(the deliverable; attribution kept separate)*

> A confidence-weighted candidate book beats the flat top-N book on **edge per unit exposure**, and the lift is
> **attributable** to the two levers separately.

- **3a (within-day selection):** rank by `opportunity_confidence`, take the **top-K of the top-N** (K<N) →
  higher mean `E` and `CM` than the flat top-N. (Isolates Lever A.)
- **3b (cross-day throttle):** exposure-weight each day by `discovery_confidence(regime_today)` → improves
  **edge-per-exposure** (and/or cuts participation in the weakest regime) vs. flat daily weight. (Isolates Lever
  B; expected small per §0.)
- **3c (composite):** the full `final_confidence` book vs. flat — reported as the product, with 3a/3b showing
  *which lever earned it*. No claim that the composite beats its best single lever unless the CI says so.

---

## 3. Frozen run configuration (locked before the run)

| Parameter | Value | Rationale |
|---|---|---|
| **Primary window** | 2010-06-13 → 2026-06-12 (~16y), top-200 | Same as v0.3 headline → directly comparable; long history needed for the 3-y PIT warm-up + per-regime priors. |
| **Recency cross-check** | 2021-06 → 2026-06, top-500 | Ties to v0.2/v0.3 headline universe; confirms calibration on the wider recent book. |
| **PIT warm-up** | first 3 y training-only; per-regime ≥60 prior days before a day emits a non-neutral Discovery-Confidence | Anti-circularity (§1b); mirrors v0.3's 60-day cell-sample floor. |
| **Confidence bins** | terciles (H-conf-1), median split (H-conf-2) | Pre-set; no post-hoc bin search. |
| **Selection fraction** | K = top-8 of top-15 (H-conf-3a) | Frozen ratio (≈ half); not optimized. |
| **Engine** | ATR + Gap + RVOL, top-15/day (frozen, v0.2 H3) | v0.4 changes the *weighting/ranking lens*, not the selection set. |
| **Bootstrap** | seeded (17), circular-block, n=2000, 95% CI | Cross-comparable with v0.2 / v0.3 / MOM / LOW. |

**Multiple-comparisons discipline:** the **confirmatory** tests are H-conf-1, H-conf-2, and H-conf-3a/3b/3c.
The blend-variant (§6) and any per-regime calibration breakdown are **exploratory / descriptive**, labeled as
such, never elevated to a pass/fail post hoc.

---

## 4. Pre-registered decision matrix (frozen BEFORE results)

| Outcome | Classification | Consequence for the capability |
|---|---|---|
| H-conf-1 holds (monotone, CI-separated) **and** H-conf-3a positive | **Confidence-Calibrated** | The per-candidate confidence is a real ranking input; ship `final_confidence` as the recommended downstream rank/size key. |
| H-conf-1 holds but H-conf-2/3b weak/flat | **Calibrated within-day, regime-flat** | Use Lever A (per-candidate confidence); treat regime confidence as *robustness evidence* (v0.3), not a throttle. The expected outcome given REGIME-ROBUST. |
| H-conf-1 fails (E flat across terciles) | **Confidence-Uninformative** | Documented boundary: rank candidates by signal **count**, not confidence magnitude; the bounded confidence stays as an *explainability* artifact, not a sizing input. A citable negative. |
| Any lift (3a/3b/3c) **negative**, CI-separated | **Counter-productive (in that lever)** | That lever is a documented no-go for weighting; ship the flat book for it. |

The v0.2 **Validated** and v0.3 **Operating-Envelope** verdicts are **unchanged by any of these** — v0.4
annotates *how to weight* the already-validated, already-mapped candidate set; it cannot un-validate or
un-map a prior result.

### 4a. Deliverable artifacts (customer-facing)

1. **Calibration curve — the headline customer artifact** (owner): a three-row table/chart
   **Low confidence → Medium confidence → High confidence ⇒ realized expansion `E`** (the confidence terciles),
   with CIs. This is the single easiest way to explain the Confidence Model's value: if the bars step up
   left-to-right, the number predicts; if they're flat, it doesn't. `CM` shown alongside as the companion row.
2. **Confidence Model spec** — the frozen `final_confidence` formula + the PIT rule, as the documented input
   contract every downstream Discovery-Lab strategy consumes.
3. **Lift table** — flat vs. Lever-A vs. Lever-B vs. composite, edge + edge-per-exposure, with the attribution.

---

## 5. Method & reuse (≈90% reuse)

- **Engine:** add **pure, unit-tested** helpers to `app/factor_data/candidate_engine.py`:
  - `discovery_confidence(regime_label, prior_edges_by_regime) -> float` — the PIT v0.3-formula lookup over a
    regime's prior-only edge series (neutral 1.0 under warm-up).
  - `composite_confidence(opportunity_confidence, discovery_confidence) -> float` — the frozen product.
  - (Optional) `confidence_weighted_rank(candidates, discovery_conf) -> list[Candidate]` — assigns
    `final_confidence` + re-rank key, leaving the frozen selection set intact.
- **Harness:** `scripts/candidate_engine_v0_4.py` — reuses v0.2 panel plumbing + v0.3 PIT regime classification +
  proxy series verbatim; adds the expanding-window Discovery-Confidence, the tercile/median binning, the three
  lift books, and the bootstrap. Emits `evidence/scan_001_candidate_engine_v0_4/` (JSON + MD), reproducible
  (seed, git, command).
- Read-only research; **no order path**; no LLM; nothing imported into the live engine.

---

## 6. Exploratory (descriptive only, NOT hypotheses)

- **Blend variant:** geometric mean vs. the frozen product, reported side-by-side (sensitivity, no verdict).
- **Per-regime calibration:** H-conf-1 broken down within each market/vol regime (thin cells — descriptive).
- If a striking, mechanism-plausible pattern appears, it becomes a *separately pre-registered* question later,
  never mined from this run.

---

## 7. Research risk register

| Risk | Mitigation |
|---|---|
| **Circularity** (confidence fit on the same days it "predicts") | §1b expanding-window PIT rule + 3-y warm-up; the test day's outcome never enters its own confidence. |
| **Lever B looks like a failure** when it is really REGIME-ROBUST headroom | §0 caveat pre-registered; H-conf-2/3b framed as expected-small; the verdict path "Calibrated within-day, regime-flat" is a *pass*, not a fail. |
| **Confidence ≈ signal-count proxy** (no extra info beyond "how many signals fired") | H-conf-1 controls by also reporting calibration *within* a fixed signal-count stratum (descriptive) — is magnitude informative *given* count? |
| **Bin-boundary fishing** | terciles + median split frozen here; K=8/15 frozen; no post-hoc bin search. |
| **Survivorship-biased universe** | same caveat as v0.2/v0.3 — read effects as relative; an unbiased-universe re-run is a follow-on before any live claim. |
| **Look-ahead in regime / confidence** | all proxy + confidence stats use only bars ≤ day *t*; unit-tested as in v0.3. |

---

## 8. Out of scope (v0.4)

Premarket-data integration (the separate hard gate before any *live* use, PR #221), intraday entry/exit, sizing
and risk wiring, any change to the frozen selection engine, and live deployment. v0.4 is purely the
calibration + composability study on the validated, mapped candidate set.

---

## 9. Deliverables

1. Pure `discovery_confidence` / `composite_confidence` (+ optional `confidence_weighted_rank`) in
   `candidate_engine.py`, with tests at the v0.2 bar (ruff/mypy clean).
2. `scripts/candidate_engine_v0_4.py` + evidence package (`evidence/scan_001_candidate_engine_v0_4/`, JSON+MD),
   reproducible, with the **calibration curve** + **lift table**.
3. **The Confidence Model spec** (§4a) — the frozen `final_confidence` contract for downstream consumers.
4. **Results doc** `..._CandidateEngine_Results_v0.4.md` — per-hypothesis verdicts against §4, the calibration
   classification (Calibrated / within-day-only / Uninformative), the curve + lift table + attribution.
5. Registry update (v0.11) — record the **Confidence Model** outcome; note SCAN-001's step toward **L4**
   (Production-Ready remains gated on the premarket-data replication).

Read-only research throughout. **Walk-away ≥ 1 h** before merge (consistent with prior SCAN doc/research PRs).

---

## 10. Open questions — RESOLVED (owner, 2026-06-23; pre-registration now frozen + APPROVED)

1. **Anti-circularity mechanism** → **Expanding-window PIT + 3-y warm-up** (§1b). The forward-test route: on day
   *t*, Discovery-Confidence uses only days < *t*. A regime emits a non-neutral confidence only after ≥60 prior
   days; under warm-up it is neutral 1.0. Lever B becomes a genuine forward-calibration claim.
2. **Primary calibration outcome** → **expansion ratio `E`** (v0.2/v0.3 primary), `CM` as companion.
3. **Selection fraction K (H-conf-3a)** → **top-8 of top-15** (≈ half), frozen before the run.
4. **Scope of the lift claim** → **evidence layer only** — expansion-edge / edge-per-exposure; **no P&L
   simulation**. Stays true to "the candidate set is evidence, not a signal" and implies no tradeable backtest
   before the premarket-data gate exists.

**Approved for implementation** with these four values. Build proceeds against §1–§5.
