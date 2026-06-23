# SCAN-001 — Operating Envelope (Discovery-Stability): Results v0.3

**Program:** SCAN-001 (Market Opportunity Discovery Engine) · Type: Platform Capability
**Capability Maturity:** L2 (Validated) → **L3 (Operating Envelope Defined)** ✅
**Pre-registration:** plan v0.3 (frozen + owner-approved: 2010–2026 / 3-state market regime / 60-day minimum)
**Evidence:** `docs/implementation/evidence/scan_001_candidate_engine_v0_3/` (JSON + MD), seed 17, reproducible
**Date:** 2026-06-23 · **for owner review**

> **Verdict: REGIME-ROBUST.** The Discovery Engine's expansion edge is **positive and CI-separated in every
> market and volatility regime** — there is **no no-go regime**. The capability is broadly deployable; its
> strength *varies* by regime (bull + low-vol strongest, bear weakest) but never disappears. v0.3 defines the
> operating envelope; v0.2's Validated verdict is unchanged.

---

## 1. The Operating Envelope (headline cut: top-200, 2010–2026, 3,826 scored days)

The customer-facing artifact — *where* the engine works, at a glance:

| Regime | Strength | Discovery Confidence | Expansion edge (95% CI), p |
|---|---|---|---|
| **Bull** | ★★★★★ | 1.00 | +0.219 [0.199, 0.241], p≈0 |
| **Sideways** | ★★★★ | 0.93 | +0.189 [0.158, 0.223], p≈0 |
| **Bear** | ★★★ | 0.91 | +0.181 [0.154, 0.208], p≈0 |
| **High-vol** | ★★★★ | 0.94 | +0.194 [0.176, 0.211], p≈0 |
| **Low-vol** | ★★★★★ | 1.00 | +0.219 [0.194, 0.244], p≈0 |

*(Expansion edge = candidate expansion-ratio − baseline, where expansion-ratio = realized intraday range ÷
ATR. Stars = tercile of edge magnitude among CI-separated regimes; confidence ∈ [0,1].)*

**The sweet spot is Bull + Low-vol; the weak corner is Bear.** Every cell clears the bar — the engine finds
opportunity in all conditions tested, just *more* of it when the tape is rising and calm.

---

## 2. What the decomposition says

### 2.1 Robust, not fragile

All five regimes are positive with CIs that exclude zero (p≈0). Per the frozen §4 matrix this is
**Regime-robust** — the strongest possible outcome: downstream strategies need **no regime gate on
opportunity *availability***. The engine does not break in any environment we can measure.

### 2.2 Bear is the weakest leg — but it does **not** go negative

v0.2 §3.4 flagged that the edge compresses in the 2022 bear. v0.3 quantifies it across **799 bear days over
16 years**: the bear edge is **+0.18** — the lowest of the five, ★★★ — but firmly CI-separated and positive.
The earlier "compresses in a bear" read is confirmed and *bounded*: compression, not collapse.

### 2.3 ⚠️ Counter-prior finding — **low-vol beats high-vol**

The intuitive prior (the owner's included) is that more volatility → more intraday opportunity, so high-vol
should dominate. **It doesn't.** Low-vol edge **+0.219 (★★★★★)** exceeds high-vol **+0.194 (★★★★)**, and the
ordering holds on the recency cut too. Interpretation: in calm markets the *baseline* universe expands far
less than its ATR, so the engine's *selected* names stand out more — the edge is a *relative* selection
advantage, and that advantage is widest when the average name is quiet. This is a real, usable design input:
**the engine is not a "volatility-chaser"**; it earns its keep in calm tape as much as in stormy tape.

### 2.4 Both cuts agree on the shape

The recency cross-check (top-500, 2021–2026, 1,057 days) reproduces the **same ordering** — Bull ≈ Low-vol
strongest, Bear / Sideways weakest — at larger magnitudes (bull +0.59, bear +0.40), exactly the
universe/recency scaling seen in v0.2 (wider, more recent universe → bigger edge). The *envelope shape* is
stable; only the *level* moves with the cut.

---

## 3. Honest qualifiers

1. **Magnitude is cut-dependent, shape is not.** The star *ordering* is stable across both cuts, but absolute
   edges differ ~2.5× (16y/top-200 vs 5y/top-500). The envelope tells you *relative* strength by regime; size
   the absolute expectation to the universe/era you deploy in (consistent with v0.2 §3.1).
2. **Market proxy, not an index.** Regimes are labelled from an equal-weight liquid-universe proxy (SPY is
   absent from the SEP store). It is internally consistent (it *is* the baseline the edge is measured against),
   but an SPY-index-based re-run is a named follow-on if a true index series is sourced.
3. **PIT, strictly.** Each day is classified from the proxy through the **prior** close — the regime is known
   at the pre-open scan, never using the day's own outcome. (Stricter than the plan's "≤ day t" wording.)
4. **Confirmatory vs descriptive.** Only the five marginal regimes are confirmatory (all cleared). The 6-cell
   grid and seasonality were intentionally *not* run as pass/fail (multiple-comparisons discipline, plan §3).

---

## 4. Decision (against the frozen §4 matrix)

**Regime-robust on the headline cut, ordering confirmed on the recency cut → SCAN-001 advances to Capability
Maturity L3 (Operating Envelope Defined).**

- **Envelope (frozen output):** works in all regimes; **best Bull + Low-vol (★★★★★)**, **weakest Bear (★★★,
  still positive)**. No regime is a no-go.
- **For downstream strategies:** no hard regime gate required; the **Discovery Confidence** numbers (1.00 bull
  / 0.91 bear …) are the ready input for *soft* regime weighting.
- **v0.4 (named, pre-registered direction):** the **Confidence Model** — turn this heatmap into the live
  `Opportunity Score × Discovery Confidence(regime_today) = regime-aware Candidate Rank`, so candidates
  down-weight automatically in weak regimes.
- **Unchanged gate:** the **premarket-data step** (PR #221) remains the hard prerequisite before any *live*
  use; v0.3 is research on daily bars.
- **Research line:** SCAN-001 construction is now **mature (L3)**; the line stays open only for v0.4 (confidence
  model) and the premarket-data replication — both owner-gated. Aligns with the "consolidate, don't expand"
  directive: no new program, a planned capability completed.

---

## 5. Reproduce

```bash
PYTHONPATH=apps/backend apps/backend/.venv/Scripts/python.exe \
  apps/backend/scripts/candidate_engine_v0_3.py \
  --store apps/backend/data/factor_data_full.duckdb --end 2026-06-12 --bootstrap 2000 \
  --report-dir docs/implementation/evidence/scan_001_candidate_engine_v0_3
```

Classifier tests: `pytest tests/factor_data/test_candidate_engine.py -q` (34 tests, green).
