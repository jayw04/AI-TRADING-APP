# Whitepaper drop-in — The Confidence Model: reject → diagnose → redesign → accept (v0.2)

> **Purpose.** A citable source for the whitepaper covering the **exact mechanics** of SCAN-001's Confidence
> Model and — new in v0.2 — its **full research arc**: the platform designed a confidence model (v0.4),
> **rejected** it on evidence, **diagnosed why** (ATR was poisoning it), **redesigned** it (ATR-decoupled), and
> **accepted** the redesign (v0.5). The whitepaper master is a binary `.docx` this repo can't edit, so this file
> supplies ready-to-paste prose + ASCII figures + the empirical result. Sourced from the frozen
> pre-registrations (`..._Plan_v0.4.md` v1.1, `..._Plan_v0.5.md` v1.1), the engine code
> (`apps/backend/app/factor_data/candidate_engine.py`), and the evidence packages
> (`evidence/scan_001_candidate_engine_v0_4/`, `..._v0_5/`; results docs `..._Results_v0.4.md`,
> `..._Results_v0.5.md`).
>
> **The one sentence for the whitepaper:** *the platform rejected two confidence models before accepting one.*
> That sequence — a designed mechanism, declined on evidence, then diagnosed and repaired into a validated one —
> is a stronger story than any single positive result, and it is exactly what Evidence Engineering is for.

---

## 0. Causal architecture — each component has exactly one job

```
   Market
     │
     ▼
   ATR ───────────►  Candidate SELECTION         (volatility ADMITS a name)
                            │
                            ▼
                       Candidate
                            │
        Gap ─┐              │
             ├──►  Discovery Confidence  ──►  Ranking  ──►  Candidate Report
       RVOL ─┘     (the non-mechanical ranking signal — v0.5, accepted)

   The anti-pattern the platform refuted (the v0.1 / v0.4 tautology):

       ATR ──►  Confidence ──►  "Move"     ✗   (ATR drives the confidence AND the move →
                                                  the relationship is definitional, not predictive)
```

**The load-bearing design rule** (the reusable IP): *ATR belongs in **selection**, not in **confidence**.* A
metric that admits names on volatility must not also *score confidence* on that volatility, or the confidence
inherits the mechanical coupling and becomes either tautological (`CM`) or inverted (`E`). v0.4 violated this
rule by accident (ATR was in the confidence blend); v0.5 enforced it and the signal appeared.

---

## 1. The three-layer confidence formula (the v0.4 model — rejected)

> **Terminology note (v0.5 naming).** This section describes the **v0.4** model, which was *rejected*. In v0.4,
> "Layer B" was called "Discovery Confidence." Under the going-forward naming, that **per-regime/per-day** number
> is **Regime Confidence** ("Operating Envelope" stays the *methodology* name), and **"Discovery Confidence"** now
> denotes the **accepted v0.5 per-candidate** number (§4). Code identifiers are unchanged. The mechanics below are
> preserved as the historical record of the rejected design.

The Confidence Model attaches a transparent, bounded `[0, 1]` number to every candidate, built from two
**independent layers** that combine into one **composite**. Critically, the two layers operate at different
scopes — one *within* a trading day, one *across* days — which is what makes them separable and independently
testable.

```
   LAYER A — OPPORTUNITY CONFIDENCE            LAYER B — DISCOVERY CONFIDENCE
   (per candidate, within-day)                (per day, across-day)
   how strongly THIS name cleared             how much we trust the ENGINE
   its opportunity thresholds                 in TODAY's market regime
            │                                          │
            │  opportunity_confidence ∈ [0,1]          │  discovery_confidence(regime_today) ∈ [0,1]
            │                                          │
            └──────────────────────┬───────────────────┘
                                   ▼
                       COMPOSITE (final) CONFIDENCE
                final_confidence = opportunity_confidence
                                 × discovery_confidence(regime_today)
                                 ∈ [0,1]
```

### Layer A — Opportunity Confidence (per candidate, within-day)

The strength with which a name cleared the engine's opportunity signals (Gap %, Relative Volume, ATR %). For
each **cleared** signal, measure how far it exceeded its threshold, clamp to `[0, 1]` on a 1×→2× scale, and
average over the cleared signals:

```
ratio_s          = signal_s / threshold_s              (for each cleared signal s)
normalized_s     = clamp(ratio_s − 1, 0, 1)            (1× threshold → 0.0 ; ≥2× threshold → 1.0)
opportunity_confidence = mean( normalized_s  over cleared signals s )      ∈ [0,1]
```

This is **transparent by construction** — not an opaque model output. A name that just barely qualifies scores
near 0; a name clearing every signal by ≥2× scores 1.0. (Source: `candidate_engine.confidence()`.)

### Layer B — Discovery Confidence (per day, across-day)

How much the **engine itself** should be trusted in *today's* market regime — the SCAN-001 v0.3 Operating-
Envelope heatmap, expressed as a bounded number. It is a **single value for the whole day** (it depends on the
regime, not on any individual candidate), so it can throttle *whole days* but cannot reorder candidates within a
day. The mapping from a regime's measured edge statistics to `[0, 1]` is the **frozen v0.3 blend**:

```
given a regime's edge statistics (point = mean expansion edge, ci_low = 95% lower bound,
                                  p = one-sided p for edge>0, ref = strongest separated regime's point):

  point ≤ 0                       →  discovery_confidence = 0.0          (a no-go regime)
  point > 0, CI NOT separated     →  discovery_confidence = 0.4·(1 − p)  (weak, separation-discounted)
  point > 0, CI separated         →  discovery_confidence = 0.5·(1 − p) + 0.5·(point / ref)
                                                                          (significance + magnitude)
```

(Source: `candidate_engine.discovery_confidence()`, identical branch logic to the v0.3 `_assign_envelope`.)

### Composite — the frozen product

```
final_confidence = clamp(opportunity_confidence, 0, 1) × clamp(discovery_confidence, 0, 1)   ∈ [0,1]
```

A product of two `[0, 1]` terms stays in `[0, 1]`. Inputs are clamped defensively so a malformed feed can never
push the composite out of range. This is a **weighting/ranking key** — it never changes *which* names the engine
selects (the selection set is frozen at the v0.2-validated Gap+RVOL+ATR engine). (Source:
`candidate_engine.composite_confidence()`.)

**The load-bearing subtlety (state it in the whitepaper).** Because Layer B is constant across all candidates on
a given day, the composite **does not reorder candidates within a day** — within-day ranking is driven entirely
by Layer A. Layer B can only **down-weight whole days** (an exposure/participation throttle). The two layers are
therefore genuinely separate levers and are tested separately.

---

## 2. Expanding-Window Point-in-Time (PIT) — the anti-circularity rule

The danger in any "confidence predicts outcome" claim is **circularity**: if the confidence for a day is fit
using that same day's outcome, "confidence predicts the edge" is true by construction and means nothing. The
Expanding-Window PIT rule removes this.

```
   timeline ───────────────────────────────────────────────────────────────────▶
                                                   ┌── scan day t ──┐
   [ ........ prior days < t (TRAINING ONLY) ......]│  classify regime(t) from data ≤ t−1
                                                    │  discovery_confidence(t) is computed
                                                    │  ONLY from prior days' edges in that regime
                                                    │  → then day t's own outcome is observed
                                                    │  → and only AFTERWARD appended to history
                                                    └────────────────┘
```

Rules (all frozen in the pre-registration, plan §1b):

1. **Prior-only.** On scan day *t*, `discovery_confidence(regime_today)` is computed **exclusively from days
   strictly before *t*** — the test day's own outcome never enters its own confidence.
2. **Warm-up.** The first **3 years** are training-only; a regime emits a non-neutral confidence only after it
   has accumulated **≥ 60 prior days** of history (mirrors the v0.3 minimum-cell-sample floor). Under warm-up the
   confidence is **neutral = 1.0** (no down-weight).
3. **Regime classification is itself PIT** — the market regime for day *t* is read from the broad-market proxy
   through the **prior close** (a 200-day SMA + 60-day return-sign rule), so a day's regime is known at its
   pre-open scan, never using its own close.
4. **Computation note (honest caveat).** The per-day separation statistic uses a **closed-form normal
   approximation** (mean ÷ standard error of the regime's prior daily-edge series) in place of v0.3's per-bucket
   block bootstrap — an expanding-window bootstrap on every one of ~3,800 days is computationally prohibitive.
   The **blend and branch logic are identical to v0.3**; only the separation statistic is the cheap closed form.

This is what converts Layer B from "a heatmap that describes 2010–2026" into "a number that, computed from the
past, is then tested against the future."

---

## 3. The empirical result (what the evidence says — report it honestly)

The v0.4 study ran the model over 2010–2026 (top-200, 3,826 scored days) and a 2021–2026 recency cross-check
(top-500), seeded circular-block bootstrap n=2000. **Verdict: CONFIDENCE-UNINFORMATIVE on the pre-registered
primary metric.**

**Calibration curve — realized expansion `E` (range ÷ own ATR) by confidence band (headline cut):**

```
   realized E
   1.43 ┤■■■■■■■■■■■■■■■■■■■■   Low confidence
   1.09 ┤■■■■■■■■■■■■■■■        Medium confidence
   0.92 ┤■■■■■■■■■■■■■          High confidence
        └──────────────────────────────────────
        Higher confidence → LOWER expansion (mildly inverse, CI-separated)
```

- **Layer A does not calibrate to `E`** — it is mildly **inverse** (high−low edge −0.45, CI [−0.49, −0.42]).
  *Mechanism:* `E` is ATR-normalized while confidence is partly ATR-driven, so they pull opposite ways — the same
  numerator-vs-denominator insight that caught the v0.1 prototype's ATR tautology. Per the frozen decision
  matrix, this is **CONFIDENCE-UNINFORMATIVE**: the bounded confidence stays an **explainability** artifact, not
  a sizing/ranking key.
- **But confidence DOES track absolute move size** — the companion metric `CM` (capturable move %, *not*
  ATR-normalized) **rises** with confidence on the recency cut (4.71 → 6.20 → 6.94). Confidence predicts *how big
  the move is*, not *expansion relative to the name's own volatility*. (Exploratory; the natural v0.5
  pre-registration is a `CM`-targeted confidence.)
- **Layer B is weakly but correctly signed** — higher-confidence *regime days* carry larger edge
  (covariance CI-separated positive on both cuts), but the throttle moves edge-per-exposure by ≈0 because v0.3
  found the engine REGIME-ROBUST (nothing to down-weight).

## 4. The redesign (v0.5) — diagnose, repair, accept

v0.4 also named *why* it failed: `E` is ATR-normalized and the confidence had **ATR in its blend**, so the two
were mechanically coupled. v0.5 acted on that diagnosis — it tested an **ATR-decoupled** confidence built from
**Gap + RVOL strength only** (ATR still drives selection, just not the confidence number), every test controlled
**within ATR strata** so the tautology cannot pose as signal.

**The reversal — the same high−low expansion test, before and after removing ATR from the confidence:**

```
   high − low realized E (CI-separated)
   v0.4  ATR-blended confidence    −0.45   ◄ inverse  ✗
   v0.5  ATR-decoupled (Gap+RVOL)  +0.89   ► positive ✓     ← removing ATR FLIPPED the sign
```

- **H-cm-1 (calibration on `E`):** monotone Low<Med<High on **both** cuts; high−low `E` **+0.89** CI [0.85, 0.93]
  (headline), **+0.51** CI [0.45, 0.59] (recency). The Gap+RVOL magnitude predicts the de-tautologized outcome.
- **H-cm-2 (calibration on `CM`, within ATR strata):** higher confidence → higher capturable move in **3 of 3**
  ATR bands on **both** cuts — confidence predicts move size *even holding volatility fixed*.
- **H-cm-3 (operational utility):** a top-K-by-confidence book lifts `E` (+0.19 / +0.17, CI-separated) **and** the
  top-K's **mean ATR equals the flat book's** (5.48 vs 5.48) — so the lift is the Gap+RVOL signal, **not** an
  ATR-selection artifact.

**Verdict: DECOUPLED-CALIBRATED — accepted.** The platform ships `confidence_gr` (customer-facing **Discovery
Confidence**) as the Candidate Report's ranking field; any live ranking/sizing use stays gated behind the
premarket-data step.

**Whitepaper takeaway.** This is Evidence Engineering's complete loop: a mechanism **proposed** (v0.4),
**rejected** on a frozen metric, **diagnosed** (ATR poisoning), **redesigned** (ATR out of the confidence), and
**accepted** (v0.5) on the same rigorous bar — *the platform rejected two confidence models before accepting
one.* The reusable design rule it produced — **ATR belongs in selection, not in confidence** — is broader and
more defensible IP than any single positive result: a method (hypothesis → validation → artifact detection →
redesign → validation), not a claimed edge.

---

## 5. Scientific Self-Correction (a standalone whitepaper subsection)

> Ready-to-paste subsection. The single most compelling property the SCAN-001 confidence arc demonstrates.

**The platform does not optimize until it wins. It proposes, tests, rejects, redesigns, re-tests — and stops.**

Most research tooling is built to *find* a positive result; under enough freedom it eventually will, and the
result rarely survives contact with new data. TradingWorkbench is built to *trust* a result, which means it must
be equally willing to reject one — including its own. The Confidence Model is the proof:

```
   Propose   →   Reject   →   Diagnose   →   Redesign   →   Re-test   →   Accept   →   STOP
   (v0.4)        (v0.4)       (ATR is in     (ATR out of    (v0.5)        (v0.5)       (no v0.6;
                 frozen        the           the                          frozen        Discovery Lab
                 metric)       confidence)   confidence)                  metric)       v1.0 frozen)
```

Two disciplines make this credible and distinguish it from ordinary backtest iteration:

1. **Frozen evaluation before data.** Each step's primary metric and decision matrix are pre-registered and
   owner-frozen *before* the run, so neither the rejection (v0.4) nor the acceptance (v0.5) is a story told after
   seeing the numbers.
2. **Stop on answer, not on success.** When v0.5 answered the question, the research line **closed** — no v0.6
   "optimization." Endless versioning would *reduce* credibility; the discipline is `Question → Evidence →
   Decision → Archive → next program`.

The artifact a customer, investor, or patent reviewer should remember is not the accepted confidence model — it
is that *the platform corrected itself, on the record, against its own pre-registered bar.*

---

*Sources: pre-registrations `..._Plan_v0.4.md`, `..._Plan_v0.5.md` (both v1.1, frozen); engine
`apps/backend/app/factor_data/candidate_engine.py` (`confidence`, `confidence_gr`, `discovery_confidence`,
`composite_confidence`); results `..._Results_v0.4.md`, `..._Results_v0.5.md`; evidence packages
`evidence/scan_001_candidate_engine_v0_4/` and `..._v0_5/` (seed 17, bootstrap n=2000, reproducible).*
