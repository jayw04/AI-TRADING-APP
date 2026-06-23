# SCAN-001 — Candidate Engine Prototype: Findings v0.1

**Program:** SCAN-001 (Market Opportunity Discovery — the first profile of the Discovery Lab)
**Type:** Platform Capability
**Status:** Prototype built · read-only research · **for owner review**
**Branch / PR:** `feat/scan-001-candidate-engine-prototype` · PR #229
**Evidence run:** `EXP` window 2018-01-01 → 2026-06-12 (2,123 trading days), git-reproducible, seed 17
**Date:** 2026-06-22

> **Read this first (the honest headline):** the prototype works end-to-end and produces a statistically clean result, **but the headline edge is partly *definitional*, not a discovery.** See §4. The value of this prototype is the *engine and the harness*, plus a sharpened set of real research questions — not the +3.24% number.

---

## 1. What this is (and the boundary that matters)

SCAN-001 is the **Market Opportunity Discovery** engine: given the pre-open state of a liquid universe, it ranks the names most worth a strategy's attention today and emits an **explainable Candidate Report**.

**It selects names. It does not trade.** (SCAN-001 §0a.) Entries, exits, sizing, and risk all belong to the downstream strategy programs. The candidate set is *evidence*, not a signal — nothing in this prototype touches the OrderRouter, and the harness never routes an order.

This is the first concrete profile of the **Discovery Lab**, the discovery-side sibling of the Factor Lab. Future engines (volume, news, options, macro) plug into the same shape.

---

## 2. What was built

| Artifact | Purpose |
| --- | --- |
| `app/factor_data/candidate_engine.py` | The **pure selection core** — no I/O, no store, no routing. |
| `tests/factor_data/test_candidate_engine.py` | 21 unit tests (green, ruff clean). |
| `scripts/candidate_engine.py` | Read-only research **harness** — replays the engine over historical SEP bars and emits the evidence package. |
| `docs/.../evidence/scan_001_candidate_engine/` | Generated `candidate_engine_evidence.{json,md}` — the H1 evidence + a sample Candidate Report. |

### 2.1 The selection model

- **Eligibility gates** (must *all* pass): price > $10, prev-day $-volume > $20M, **not** reporting earnings today. Liquidity + safety — admission only, never a "reason to select."
- **Opportunity signals** (≥1 must clear): **Gap %** > 3, **RVOL** > 2×, **ATR %** > 2. The drivers that make a name interesting; the ones that fire become the candidate's `reason` (e.g. `Gap + RVOL + ATR`).
- **Confidence** — a bounded `[0,1]` *transparent* score: the mean, over the cleared signals, of how far each beats its threshold (1× → 0.0, ≥2× → 1.0). Not an opaque model output; you can read exactly why a candidate scored what it did.
- **Ranking** — signal count first (a 3-signal name outranks a 1-signal name), confidence as tiebreak, then dollar-volume. Top-N (default 15).
- A `require_all_signals` flag gives the **robustness tightening** (all three drivers) for sensitivity work.

### 2.2 The harness

For each trading day it builds the PIT pre-open feature panel from *prior* bars, runs the engine → ranked top-N, then scores the **realized intraday range %** `(HOD − LOD) / open` — the *opportunity metric* — for the candidates vs the full eligible universe that day. The daily `(candidate − baseline)` difference is the edge; a seeded circular-block bootstrap brackets it with a 95% CI and a one-sided p-value (reusing the P12 `evidence.py` machinery). Universe is re-struck **monthly**, PIT and survivorship-free.

---

## 3. The result (H1)

**H1 — does curation select opportunity?** Over 2018-2026 (2,123 days):

| Metric | Value |
| --- | --- |
| Candidate mean intraday range | **6.33 %** |
| Baseline (eligible-universe) mean range | **3.09 %** |
| Edge (candidate − baseline) | **+3.24 %** · 95% CI [3.08, 3.41] · p ≈ 0 |
| Daily win rate (candidate > baseline) | **99.9 %** |

Mechanically, the engine works: it consistently selects the higher-range names out of the liquid universe.

---

## 4. ⚠️ The critical caveat — why the headline overstates the discovery

**The edge is partly *definitional*.** One of the selection signals is **ATR %**, which *is itself a range measure*. Selecting names with high ATR and then measuring that they have high realized intraday range is close to tautological — and the **~100% daily win rate is the tell**: a genuinely discovered edge does not win 999 days out of 1,000. H1-as-literally-stated is "supported," but it is not evidence of a *non-obvious* edge.

This is exactly the trap Evidence Engineering exists to catch, so the prototype names it loudly in the evidence file rather than burying it under a clean number.

### The genuinely open questions (the real research)

1. **Expansion beyond ATR** — do candidates realize range *in excess of* their own ATR-implied range, or do they just track it? (Realized range ÷ ATR-implied range.) This is the test that removes the tautology.
2. **Directionality** — is the range a *tradeable* directional move, or just chop that an intraday strategy can't monetize? Range alone is not edge.
3. **Signal attribution (H3)** — do Gap and RVOL add anything *over an ATR-only screen*? If not, two of the three filters are decoration.

A candidate engine earns its keep only if it answers #1–#3 affirmatively. That is the next iteration.

### Data honesty (v1 limitations)

- **Gap %** uses the official market open as a ~5-minute approximation of the live 09:25 premarket price. A real pre-open scan needs true premarket quotes.
- **RVOL** is a daily-volume proxy; true premarket relative volume is the v1 refinement.
- The opportunity metric is the post-open *outcome*, so it cannot leak into selection — but #1–#3 above all require data we approximate today.

---

## 5. Recommended next steps (for your decision)

1. **Register SCAN-001** in the Research Program Registry as `Prototype` (roadmap step 4) — record this finding, including the caveat, as the program's first evidence entry.
2. **Iteration v0.2 — kill the tautology:** add the *range-expansion-beyond-ATR* metric (§4 #1) and the *ATR-only attribution* baseline (§4 #3). These reuse the existing harness; they change the *question*, not the plumbing.
3. **Directionality study** (§4 #2): measure signed move / MFE-MAE on candidates vs baseline — does the range translate into a capturable move?
4. **Premarket data** as a separate enabling task before any promotion past prototype (the gappers feed in PR #221 is the natural source).

**What I would *not* do:** treat the +3.24% as a validated edge, or promote anything to paper on this run. The number is real but the framing is not yet honest enough to act on — which is itself a useful, on-methodology outcome.

---

## 6. How to reproduce

```bash
PYTHONPATH=apps/backend apps/backend/.venv/Scripts/python.exe \
  apps/backend/scripts/candidate_engine.py \
  --store apps/backend/data/factor_data_full.duckdb \
  --start 2018-01-01 --end 2026-06-12 --n 200 --top-n 15 --bootstrap 2000 \
  --report-dir docs/implementation/evidence/scan_001_candidate_engine
```

Pure-core tests: `PYTHONPATH=apps/backend apps/backend/.venv/Scripts/python.exe -m pytest tests/factor_data/test_candidate_engine.py -q`
