# SCAN-001 — The De-Tautologized Confidence: Results (v0.5)

| Field | Value |
|---|---|
| Document version | v0.1 (results — executed against the frozen v1.1 plan) |
| Date | 2026-06-23 |
| Program | SCAN-001 (Market Opportunity Discovery Engine — first profile of the Discovery Lab) |
| Type | Platform Capability · **Capability Maturity:** L3 — *unchanged by this study* |
| Plan | `TradingWorkbench_SCAN001_CandidateEngine_Plan_v0.5.md` (v1.1, FROZEN, owner-approved 2026-06-23) |
| Evidence | `evidence/scan_001_candidate_engine_v0_5/` (JSON + MD), seed 17, circular-block bootstrap n=2000 |
| Verdict | **DECOUPLED-CALIBRATED** — the ATR-decoupled confidence (Gap + RVOL) predicts a de-tautologized outcome on **both** cuts, holds **within every ATR band**, and lifts the book. The platform **accepts** this confidence model — having rejected two before it. |

> **Headline in one line:** v0.4 found the confidence number *inverse* to expansion `E` — but the confidence
> blended **ATR** in, and ATR is the mechanical driver. v0.5 stripped ATR out (testing **Gap + RVOL strength
> only**) and the relationship **flipped sign**: high−low `E` went from **−0.45 (v0.4)** to **+0.89 (v0.5)**,
> CI-separated, monotone, on both cuts. The signal was real all along — it was being *poisoned* by the ATR term.
> ATR belongs in **selection**, not in **confidence**. Per the frozen §4 matrix → **DECOUPLED-CALIBRATED**:
> ship `confidence_gr` (customer-facing **Discovery Confidence**) as the Candidate Report's ranking field, with
> live use still gated by the premarket-data step.

### The methodology in one picture — two rejections, one acceptance

```
   v0.4  full confidence (ATR + Gap + RVOL)  ──►  E   :  INVERSE   ✗   rejected (CONFIDENCE-UNINFORMATIVE)
   v0.4  naive "calibrate to raw CM"          ──►  —   :  tautology ✗   refused at design (ATR drives both)
   v0.5  ATR-decoupled (Gap + RVOL only)      ──►  E   :  +0.89 CI-sep ✓  ACCEPTED (DECOUPLED-CALIBRATED)
```

*The platform rejected two confidence models before accepting one.* That sequence — not the accepted model
alone — is the asset.

**The reversal, as one chart** (realized expansion `E` by confidence band, headline):

```
   E
   1.6 ┤                              ● High            v0.5  (ATR-decoupled, Gap+RVOL)
   1.3 ┤                                                ── monotone, high−low +0.89, CI-separated
   1.0 ┤              ● Med
   0.8 ┤  ● Low
       └────────────────────────────────────►
          Low          Med          High

   vs. v0.4 (ATR-blended): High 0.92  <  Med 1.09  <  Low 1.43   — the line sloped DOWN (inverse −0.45)
```

---

## 1. What was tested (recap of the frozen design)

The confidence under test is **`confidence_gr`** — the bounded [0,1] opportunity confidence over the cleared
**Gap and RVOL** signals **only** (ATR excluded from the *confidence*, though ATR still drives *selection*; the
engine is frozen). Every test controls for the mechanical ATR channel. Primary outcome `E` (range ÷ own ATR);
companion `CM` (capturable move %), reported **within ATR terciles**. Two cuts: HEADLINE (top-200, 2010–2026,
4,025 days, 60,375 candidates) and RECENCY (top-500, 2021–2026, 1,256 days, 18,840 candidates). Seeded
circular-block bootstrap (n=2000).

---

## 2. H-cm-1 — ATR-decoupled calibration on `E`: SUPPORTED (both cuts)

**The de-tautologized calibration curve** — realized `E` by Discovery-Confidence band:

| Band | HEADLINE `E` | HEADLINE `CM` | RECENCY `E` | RECENCY `CM` |
|---|---|---|---|---|
| **Low** | 0.804 | 3.27 | 1.128 | 4.86 |
| **Medium** | 1.048 | 4.12 | 1.441 | 6.02 |
| **High** | **1.581** | 5.90 | **1.770** | 7.52 |

- **Monotone Low < Med < High = True** on both cuts. High−Low `E` edge **+0.891**, CI [0.847, 0.935]
  (headline); **+0.514**, CI [0.445, 0.586] (recency). → **SUPPORTED.**
- **The reversal:** the *identical* high−low test on v0.4's ATR-blended confidence was **−0.45** (inverse).
  Removing the ATR term from the confidence flipped the sign to strongly positive. The Gap+RVOL magnitude
  carries genuine expansion information that the ATR term had been *masking* (high-ATR names have low `E` by the
  numerator-vs-denominator coupling, and ATR-in-confidence dragged the whole signal inverse).

---

## 3. H-cm-2 — ATR-stratified calibration on `CM`: SUPPORTED, 3/3 bands (both cuts)

Within **each** ATR tercile — so the mechanical "high-ATR → high-CM" channel is held fixed — higher Discovery
Confidence predicts higher capturable move:

| ATR band | HEADLINE high−low `CM` (CI) | RECENCY high−low `CM` (CI) |
|---|---|---|
| low_atr | +1.284 [1.168, 1.404] ✓ | +1.437 [1.187, 1.684] ✓ |
| mid_atr | +0.306 [0.270, 0.344] ✓ | +2.486 [1.886, 3.134] ✓ |
| high_atr | +4.010 [3.554, 4.480] ✓ | +4.375 [3.245, 5.816] ✓ |

**3 of 3 bands CI-separated on both cuts** (the bar was ≥2 of 3). This is the cleanest possible refutation of
the tautology objection: confidence predicts move size **even holding volatility fixed**. The effect is largest
in the high-ATR band — the most volatile names benefit *most* from the Gap+RVOL discrimination.

---

## 4. H-cm-3 — Operational Utility (does it improve the platform?): SUPPORTED

A top-8-of-15 book ranked by Discovery Confidence beats the flat top-15:

| | HEADLINE | RECENCY |
|---|---|---|
| `E` lift (top-K − flat) | **+0.186**, CI [0.175, 0.197] | **+0.166**, CI [0.145, 0.188] |
| `CM` lift | +0.508, CI [0.462, 0.554] | +0.674, CI [0.580, 0.777] |
| **Decoupling check — mean ATR** | top-K **5.48** vs flat **5.48** | top-K **6.54** vs flat **6.31** |

The decoupling check is the load-bearing detail: ranking by `confidence_gr` **does not raise the book's ATR**
(top-K ≈ flat), so the `CM`/`E` lift is **not** an ATR-selection artifact — it is the Gap+RVOL signal doing real
work. → **SUPPORTED** (Operational Utility, not mere correlation).

---

## 5. Discovery Confidence distribution (the customer artifact)

How the bounded [0,1] number lands across candidates (headline):

```
 [0.0,0.1)  ████████████████████████████  58.5%   ← cleared on ATR alone → Gap+RVOL confidence ≈ 0
 [0.1,0.5)  ██████████                     20.3%
 [0.5,0.9)  ██████                         11.5%
 [0.9,1.0]  █████                           9.7%   ← strong Gap+RVOL names
```

**58.5% of candidates score ~0 on Discovery Confidence** — they were admitted by ATR alone, and (per §2) those
are exactly the low-expansion names. The confidence number's job is to separate the ~10–20% of genuinely
Gap+RVOL-strong candidates from the ATR-only majority. This is *why* the decoupling matters: the field is
informative precisely where the old ATR-blended confidence was not.

---

## 6. Verdict against the frozen decision matrix (plan §4)

| Frozen outcome | Hit? |
|---|---|
| H-cm-1 and/or H-cm-2 (≥2/3 bands) **and** H-cm-3 positive → **DECOUPLED-CALIBRATED** | **Yes** (all three; 3/3 bands) |
| CI barely clears → Suggestive — not promoted | No (CIs clear comfortably, both cuts) |
| All fail → Confirmed uninformative | No |

**→ DECOUPLED-CALIBRATED.** Consequence (frozen): **ship `confidence_gr` as the Candidate Report's confidence
field** (customer-facing **Discovery Confidence**); any *ranking/sizing* use in production stays **gated** by the
premarket-data step (PR #221) + owner sign-off (plan OQ4). v0.4's negative is now explained, not contradicted:
it was an **ATR-poisoning artifact** of blending ATR into the confidence.

**What is unchanged.** v0.2 *Validated*, v0.3 *Operating-Envelope (L3)*, v0.4 *Confidence-Uninformative* all
stand. **Capability Maturity stays L3** — a calibrated ranking confidence is not an Operating-Envelope or
live-readiness advance; L4 still requires the premarket-data gate + live replication.

---

## 7. Lessons & what happens next (promote-or-close, plan §9b)

1. **ATR belongs in selection, not in confidence.** The single most reusable lesson: a metric that admits names
   on volatility must not also score *confidence* on that volatility, or the confidence inherits the mechanical
   coupling. This is the v0.1 tautology lesson, fully generalized — and now *resolved*, not just avoided.
2. **The platform rejected two confidence models before accepting one** (v0.4 full-blend; the naive CM-chase),
   then accepted the ATR-decoupled one on evidence. The *sequence* is the credibility story (whitepaper line).
3. **Promote, then stop** (the §9b discipline): this is the final confidence study. Recommended actions —
   - **Promote** the Discovery Confidence model: set the Candidate Report's confidence field to `confidence_gr`
     (explainability; pre-registered & owner-approved, OQ4). *Recommended as a separate, focused product PR* so
     the research PR stays read-only — the change touches a live product surface.
   - **Keep the premarket-data gate** before any production ranking/sizing use.
   - **Do not** spawn a v0.6 confidence optimization. Discovery Lab v1.0 (Selection v0.2 · Operating Envelope
     v0.3 · Discovery Confidence v0.5) is now **complete**.

---

## 8. Honest scope

- Confidence under test is **Gap+RVOL only** (`confidence_gr`); ATR drives *selection*, never the tested
  confidence — the anti-tautology decoupling.
- Every `CM` test is **within ATR terciles** so the mechanical high-ATR→high-CM channel can't pose as a signal.
- Gap and RVOL are **not independent** (a gap can cause RVOL); v0.5 evaluates their **combined** operational
  value, not causal independence (plan §7).
- Lift is **evidence-layer** (E / CM diffs), never a P&L backtest — the premarket-data gate (PR #221) stays the
  hard prerequisite before any live use.
- Survivorship-biased universe (today's liquid names) — read effects as relative.

*Reproduce:* `PYTHONPATH=apps/backend .venv/Scripts/python.exe apps/backend/scripts/candidate_engine_v0_5.py
--store apps/backend/data/factor_data_full.duckdb --end 2026-06-12 --bootstrap 2000 --report-dir
docs/implementation/evidence/scan_001_candidate_engine_v0_5` (seed 17).
