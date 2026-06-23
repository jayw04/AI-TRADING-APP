# SCAN-001 — The De-Tautologized Confidence (CM-targeted): Research Plan & Pre-Registration (v0.5)

| Field | Value |
|---|---|
| Document version | v1.1 (FROZEN for execution — owner-approved 2026-06-23; folds the plan review: causal diagram, internal/external naming, H-cm-3 → Operational Utility, a Suggestive non-promotion bucket, a correlated-features risk, a Confidence Distribution artifact, the Discovery-Lab three-level structure, and the promote-or-close discipline. Hypotheses/metrics/config unchanged.) |
| Date | 2026-06-23 |
| Program | SCAN-001 (Market Opportunity Discovery Engine — first profile of the Discovery Lab) |
| Type | Platform Capability · **Capability Maturity:** L3 — *unchanged by this study* |
| Predecessor | v0.4 results (`..._CandidateEngine_Results_v0.4.md`, PR #236) — CONFIDENCE-UNINFORMATIVE on `E`; the companion observation that confidence tracks **absolute move `CM`** is the thread this study picks up — *carefully* |
| Successor | premarket-data gate (PR #221) — owner's "v0.5 then #221" sequence; out of scope here |
| Repository | github.com/jayw04/AI-TRADING-APP |
| Scope | Test whether there is a **non-mechanical, ATR-decoupled** confidence signal (Gap + RVOL strength) that predicts a **de-tautologized** tradeable outcome — turning v0.4's tantalizing "confidence tracks CM" into a claim that survives the v0.1 tautology check, or a confirmed double-negative. |
| Estimated wall time | Plan: this doc. Build+run: 4–7 h (one new pure helper + harness extension + the ~16-y replay + bootstrap). |
| Tag on completion | `scan-001-v0.5-complete` |
| Out of scope | Premarket-data integration, live use, intraday entry/exit, sizing/risk wiring, any change to the frozen *selection* engine (ATR+Gap+RVOL, top-15). |

> **The trap v0.5 must avoid (state it first).** v0.4 found the per-candidate confidence is *inverse* to
> ATR-normalized expansion `E`, but *positive* to absolute capturable move `CM`. It is tempting to conclude
> "calibrate confidence to `CM` instead." **That would re-introduce the v0.1 ATR tautology.** `CM` is an
> *absolute* % move; high-ATR names mechanically post larger absolute moves; and confidence is partly ATR-driven.
> So "confidence predicts `CM`" is, to first order, "high-ATR names move more" — the exact definitional artifact
> v0.2 corrected by normalizing to `E = range / ATR`. **v0.5 does not chase `CM` naively.** It asks the only
> version of the question that is *not* mechanical:

> **The real v0.5 question:** is there a **non-ATR component of confidence** — the strength of **Gap + RVOL** —
> that predicts a tradeable outcome **after controlling for ATR**? If yes, v0.4's negative was an artifact of
> ATR *poisoning* the confidence blend, and a de-tautologized confidence earns a ranking role. If no, v0.4's
> negative is **robust and final** — confidence *magnitude* carries no de-tautologized sizing signal, and the
> confidence-model research line closes.

### Causal architecture — each component has exactly one job

```
   Market
     │
     ▼
   ATR ───────────►  Candidate SELECTION        (volatility ADMITS a name — engine frozen, v0.2)
                            │
                            ▼
                       Candidate
                            │
        Gap ─┐              │
             ├──►  Discovery Confidence (confidence_GR)  ──►  Ranking  ──►  Candidate Report
       RVOL ─┘        (the NON-mechanical signal under test)

   The anti-pattern v0.5 refutes — the v0.1 / v0.4 tautology:

       ATR ──►  Confidence ──►  "Move"     ✗   (mechanical: ATR drives the confidence AND the move,
                                                  so the relationship is definitional, not predictive)
```

ATR's one job is **selection** (admit volatile names); Gap+RVOL's one job is **confidence/ranking** (which
admitted names to trust). v0.5 tests whether that second job carries real, de-tautologized information. *(This
diagram also belongs in the whitepaper — it explains in one picture why v0.5 exists.)*

---

## 0. Why v0.5, and what it is *not*

- **It is:** a test of whether the **Gap+RVOL magnitude** (not mere presence — v0.2 H3 settled presence) carries
  predictive information for *how much* a candidate moves, **net of the mechanical ATR coupling**. It extends
  v0.2's *presence*-attribution and v0.4's *calibration* into **ATR-controlled magnitude-attribution**.
- **It is not:** a re-validation (v0.2), an Operating-Envelope re-map (v0.3), a naive "calibrate to CM" (the
  trap above), or any change to the frozen selection set.
- **Honest fork it allows:** the most likely *and* most valuable outcome is a **confirmed double-negative** —
  "even decoupled, confidence magnitude does not predict a de-tautologized outcome." That closes the
  confidence-model line with a strong, citable finding, exactly as RNG-001 closed range trading.

---

## 1. Frozen definitions (set BEFORE any outcome is seen)

### 1a. The ATR-decoupled confidence (Lever A, rebuilt)

The engine's existing `opportunity_confidence` blends Gap, RVOL, **and ATR** strength — and the ATR term is what
couples it to the mechanical outcome. v0.5 isolates the **non-mechanical** part:

```
confidence_GR = the v0.2 confidence() computed over the cleared signals in {Gap, RVOL} ONLY
              = mean over cleared Gap/RVOL signals of clamp(signal/threshold − 1, 0, 1)      ∈ [0,1]
```

ATR is **still** an eligibility/opportunity signal in *selection* (the engine is frozen); it is simply **excluded
from the confidence number being tested**. This is a pure helper (`active_signals=("Gap","RVOL")` already exists
in the engine — see `opportunity_signals`/`confidence`), unit-tested at the v0.2 bar.

**Naming — internal vs. customer-facing (review fold).** Internally the field is `confidence_GR`; the
customer-facing name is **"Discovery Confidence"** (the per-candidate ranking number a customer reads). ⚠
**Reconciliation:** v0.3/v0.4 used "Discovery Confidence" for the *per-regime, per-day* trust value (Lever B).
Going forward, to keep one name → one object: the **per-candidate ranking** number is **Discovery Confidence**
(this study), and the **per-regime/per-day** value is **Regime Confidence** (v0.3/v0.4) — while **"Operating
Envelope"** stays the *methodology/study* name that produces it. This is a going-forward documentation
convention; the already-merged v0.3/v0.4 docs are not rewritten — flagged here for the owner. (Code identifier
stays `confidence_GR`.)

### 1b. The ATR control (the anti-tautology mechanism)

Every calibration test is run **within ATR strata**, so the mechanical "high ATR → high CM" channel cannot
masquerade as a confidence signal:

- Pool candidates, split into **ATR terciles** (low / mid / high `atr_pct`), frozen by index.
- Within each ATR tercile, test whether `confidence_GR` predicts the outcome. A signal that survives *inside* an
  ATR band is not the ATR artifact.

### 1c. Outcomes (both reported; `E` primary)

- **`E` = intraday range / own ATR** (the de-tautologized expansion — primary, continuity with v0.2–v0.4).
- **`CM` = capturable move %** (absolute) — reported **only within ATR strata** (raw pooled `CM` is the trap).

---

## 2. Frozen hypotheses

Metric machinery is the seeded (17) circular-block bootstrap from `evidence.py`, as in v0.2–v0.4. All
calibration is day-level where possible (autocorrelation-aware), pooled-with-CI otherwise.

### H-cm-1 — ATR-decoupled calibration on `E` *(the core test)*

> Higher `confidence_GR` (Gap+RVOL strength) predicts higher de-tautologized expansion `E`.

- **Test:** tercile candidates by `confidence_GR`; pooled mean `E` is **monotonically increasing**, and the
  day-level high−low `E` difference has a 95% bootstrap CI **excluding 0** (the v0.4 H-conf-1 machinery, but on
  the *decoupled* confidence).
- **Reading:** if it holds, the Gap/RVOL magnitude *does* carry expansion-sizing information that v0.4's
  ATR-poisoned blend masked. If it fails (flat/inverse), the decoupling does not rescue calibration.

### H-cm-2 — ATR-stratified calibration on `CM` *(the de-tautologized version of v0.4's CM observation)*

> **Within each ATR tercile**, higher `confidence_GR` predicts higher `CM`.

- **Test:** inside each ATR band, tercile by `confidence_GR`; the high−low `CM` difference is positive and
  CI-separated **in at least 2 of 3 ATR bands** (a regime-robustness-style bar; one band passing could be noise).
- **Reading:** this is the *only* non-tautological way to ask "does confidence predict absolute move." A pass
  means Gap/RVOL strength predicts move size beyond what ATR mechanically delivers.

### H-cm-3 — Operational Utility *(does the confidence improve the platform, not just predict?)*

> A `confidence_GR`-weighted top-K book beats the flat top-N book on `E` (and on ATR-band-relative `CM`).

*Framing (review fold):* this is the **Operational Utility** test — the question is not merely "does confidence
*predict*" (H-cm-1/2) but "does confidence-based ranking *improve the platform's output* over the existing
selection." A capability earns its place by utility, not correlation.

- **3a:** rank by `confidence_GR`, take top-8 of top-15 → higher mean `E` than flat (day-level diff, CI>0).
- **3b:** the same selection improves mean `CM` *within ATR strata* (band-relative, so it isn't the ATR artifact).
- Isolates whether the decoupled confidence is a usable *ranking* key where v0.4's full confidence was not.

---

## 3. Frozen run configuration (locked before the run)

| Parameter | Value | Rationale |
|---|---|---|
| **Primary window** | 2010-06-13 → 2026-06-12 (~16y), top-200 | Same as v0.3/v0.4 headline — directly comparable. |
| **Recency cross-check** | 2021-06 → 2026-06, top-500 | Same as v0.2/v0.3/v0.4 — wider recent book. |
| **Confidence under test** | `confidence_GR` (Gap+RVOL only) | The ATR-decoupling — the whole point (§1a). |
| **ATR control** | candidate ATR **terciles**, frozen by index | Transparent, no model; the anti-tautology mechanism (§1b). |
| **Calibration bins** | terciles (within each ATR band) | Pre-set; no post-hoc bin search. |
| **Selection fraction** | K = top-8 of top-15 | Same frozen ratio as v0.4 (comparability). |
| **Engine (selection)** | ATR + Gap + RVOL, top-15/day (frozen, v0.2 H3) | v0.5 changes the *confidence/ranking lens*, never selection. |
| **Bootstrap** | seeded (17), circular-block, n=2000, 95% CI | Cross-comparable with v0.2–v0.4. |

**Multiple-comparisons discipline:** confirmatory tests = H-cm-1, H-cm-2 (2-of-3 ATR bands), H-cm-3a/3b. Any
per-regime or per-signal (Gap-only vs RVOL-only) breakdown is **exploratory / descriptive**, labeled, never
elevated post hoc.

---

## 4. Pre-registered decision matrix (frozen BEFORE results)

| Outcome | Classification | Consequence |
|---|---|---|
| H-cm-1 holds **and/or** H-cm-2 holds (2-of-3 bands) **and** H-cm-3 positive | **DECOUPLED-CALIBRATED** | The Gap+RVOL magnitude *is* a de-tautologized sizing signal. Ship `confidence_GR` (customer-facing **Discovery Confidence**) as the Candidate Report's confidence/ranking field (live use still gated by the premarket-data step + owner). v0.4's negative was an ATR-poisoning artifact. |
| Signal present but **CI barely clears** (e.g. H-cm-2 passes 1 of 3 bands, or a lift CI's lower bound sits just above 0) | **SUGGESTIVE — not promoted** (review fold) | A real-but-weak read. Recorded honestly; **not** promoted to a shipped ranking key on thin separation. Re-examined only if more evidence accrues — the governance middle ground between Calibrated and Uninformative. |
| H-cm-1/2 hold but H-cm-3 flat | **Calibrated, not yet a ranking lift** | Confidence carries signal but top-K selection doesn't capture it; keep as explainability, name the construction follow-on. |
| **All fail** | **CONFIRMED UNINFORMATIVE (double-negative)** | Confidence *magnitude* carries no de-tautologized sizing signal even decoupled from ATR. **Close the confidence-model research line.** v0.4's negative is robust and final — a strong, citable RNG-001-style close. |
| Any lift negative, CI-separated | **Counter-productive (in that lever)** | Ship flat for it. |

The v0.2 *Validated*, v0.3 *Operating-Envelope (L3)*, and v0.4 *Confidence-Uninformative* verdicts are
**unchanged by any of these** — v0.5 tests one *new, de-tautologized* construction. **Capability Maturity stays
L3** regardless (a calibrated confidence is a *ranking* improvement, not an Operating-Envelope or live-readiness
advance; L4 still needs the premarket gate).

### 4a. Deliverable artifacts

1. **The de-tautologized calibration curve** — realized `E` by `confidence_GR` tercile, **and** `CM` by
   `confidence_GR` tercile *within each ATR band* (the honest customer chart: "does Gap/RVOL strength predict
   move, holding volatility fixed?").
2. **Discovery Confidence distribution** (review fold) — a histogram of the `confidence_GR` values across
   candidates (how the bounded [0,1] number is distributed: where it saturates, how many candidates land low/
   mid/high). A simple, customer-useful artifact for reading the confidence field.
3. **Verdict against §4** with the explicit tautology-control narrative.

---

## 5. Method & reuse (≈90% reuse)

- **Engine:** one thin pure helper — `confidence_GR(feat)` = `confidence(feat, opportunity_signals(feat,
  active_signals=("Gap","RVOL")))` (the building blocks already exist; add a named convenience + tests).
- **Harness:** `scripts/candidate_engine_v0_5.py` — reuses the v0.2 panel plumbing + v0.4 calibration/lift
  machinery verbatim; adds the ATR-tercile stratification and swaps the confidence under test to
  `confidence_GR`. Emits `evidence/scan_001_candidate_engine_v0_5/` (JSON+MD), reproducible (seed, command).
- Read-only research; **no order path**; no LLM; nothing imported into the live engine. Lift at the
  **evidence layer only** (no P&L), consistent with v0.4.

---

## 6. Exploratory (descriptive only, NOT hypotheses)

- **Per-signal decomposition** — Gap-only vs RVOL-only confidence calibration (which driver, if any, carries the
  signal); descriptive.
- **Per-regime** — H-cm-1 within v0.3 market regimes (thin cells); descriptive.

---

## 7. Research risk register

| Risk | Mitigation |
|---|---|
| **The v0.1 tautology, reborn** ("confidence predicts CM") | The entire design: confidence is ATR-decoupled (§1a) **and** every test is ATR-stratified (§1b). Raw pooled `CM` is never a verdict metric. |
| **Confidence_GR ≈ Gap alone** (RVOL adds nothing) | The exploratory per-signal split (§6) reports it; the verdict stands on the combined `confidence_GR` either way. |
| **Thin ATR×confidence cells** | Terciles (not finer); 2-of-3-band bar for H-cm-2 guards against one-cell noise; 16-y window for depth. |
| **Look-ahead** | `confidence_GR`, ATR, and outcomes are all same-bar/pre-open as in v0.2–v0.4; no new temporal surface. |
| **Survivorship-biased universe** | Same caveat; read effects as relative; unbiased-universe re-run is a follow-on before any live claim. |
| **Over-claiming a rescue** | A pass must clear H-cm-1/2 *and* H-cm-3; a single-band or single-metric hit is the **Suggestive — not promoted** bucket (§4), not "calibrated." |
| **Correlated features** (review fold) | Gap and RVOL are **not independent** — a gap often *causes* elevated RVOL. v0.5 evaluates their **combined operational value**, not causal independence; we make no claim that Gap and RVOL contribute orthogonally. The exploratory per-signal split (§6) is descriptive only. |

---

## 8. Out of scope (v0.5)

Premarket-data integration (the next thread, PR #221), intraday entry/exit, sizing/risk wiring, any change to
the frozen selection engine, and live deployment.

---

## 9. Deliverables

1. `confidence_GR` pure helper in `candidate_engine.py` (+ tests at the v0.2 bar; ruff/mypy clean).
2. `scripts/candidate_engine_v0_5.py` + evidence package (`evidence/scan_001_candidate_engine_v0_5/`, JSON+MD),
   reproducible, with the ATR-stratified de-tautologized calibration curve.
3. **Results doc** `..._CandidateEngine_Results_v0.5.md` — verdict vs §4, the tautology-control narrative, the
   curve, and the lift/attribution.
4. Registry update (v0.13) — record the v0.5 outcome (DECOUPLED-CALIBRATED or CONFIRMED UNINFORMATIVE); Maturity
   stays L3; update the SCAN research line (close it on a double-negative, or name the construction follow-on).

Read-only research throughout. **Walk-away ≥ 1 h** before merge.

### 9a. Discovery Lab — the three permanent capability levels (review fold)

v0.5 completes a three-level structure that the owner suggests making **official** — the first-generation
Discovery Lab as three permanent, separable capabilities:

| Level | Capability | Question it answers | Status |
|---|---|---|---|
| **L1 — Selection Engine** | candidate discovery (the Candidate Engine, CAP-001) | *which names are opportunities?* | ✅ Validated (v0.2) |
| **L2 — Operating Envelope** | when the engine should be trusted | *in which regimes does it work?* | ✅ Defined (v0.3, L3 maturity) |
| **L3 — Discovery Confidence** | how candidates should be ranked | *how much do we trust each candidate?* | ⏳ Evaluated (v0.5) |

If v0.5 lands a positive, robust result, **Discovery Lab v1.0 is essentially complete**. If it lands another
negative, that too completes v1.0 — it establishes that the platform can *discover* and *bound* its capability,
and that confidence-based ranking adds no measurable value beyond selection. **Either outcome closes the
first-generation Discovery Lab honestly.**

### 9b. Promote-or-close discipline (review fold — avoid endless optimization)

Evidence Engineering is `Question → Answer → Decision → Move On`, not endless tuning. **v0.5 is intended to be
the final major confidence study** unless its results reveal a *genuinely new* question:

- **If v0.5 succeeds** → promote the Discovery Confidence model, update the Candidate Report, keep the
  premarket-data gate before any production use. Do **not** spawn a v0.6 "optimization."
- **If v0.5 fails** → record the negative, **close the Confidence Model research line**, move to the next
  Discovery Lab capability.

A "Suggestive — not promoted" outcome (§4) closes the line too (not promoted), pending future evidence — it is
not a license to keep iterating.

---

## 10. Open questions — RESOLVED (owner, 2026-06-23; pre-registration now frozen + APPROVED)

1. **Confidence construction under test** → **Gap+RVOL only (`confidence_GR`)** — the clean ATR-decoupling; ATR
   still drives *selection*, never the tested confidence number.
2. **Primary outcome** → **`E`** (de-tautologized, continuity with v0.2–v0.4), with **ATR-stratified `CM`** as
   the companion (raw pooled `CM` is never a verdict metric).
3. **ATR control** → **tercile stratification** (transparent, no model).
4. **If decoupled confidence calibrates** → update the **Candidate Report's confidence field** to `confidence_GR`
   (explainability), but keep any *ranking/sizing* use **gated** (premarket-data step + owner).

**Approved for implementation** with these four values. Build proceeds against §1–§5.
