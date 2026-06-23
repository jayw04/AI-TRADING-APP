# SCAN-001 — Candidate Engine: Results v0.2 (de-tautologized)

**Program:** SCAN-001 (Market Opportunity Discovery) · Type: Platform Capability
**Pre-registration:** plan v0.2 §1/§4a (frozen 2026-06-22, owner-approved decisions)
**Evidence:** `docs/implementation/evidence/scan_001_candidate_engine_v0_2/` (JSON + MD), seed 17, reproducible
**Date:** 2026-06-23 · **for owner review**

> **Verdict: SUPPORTED on both cuts.** The prototype's caveat is resolved in the engine's favor — the
> candidate set's higher range is **not** a tautology of selecting on ATR. Candidates expand *beyond* their
> own volatility, the expansion is *tradeable*, and *all three* signals earn their place. The one honest
> qualifier is magnitude, not direction (see §3).

---

## 1. What v0.2 had to prove (and why)

The prototype (v0.1) found candidates realize +3.24% more intraday range than the baseline — but with a
99.9% daily win rate, because we *select* on ATR %, itself a range measure. v0.2 pre-registered three frozen
hypotheses to remove that tautology, evaluated on **both** a headline cut (top-500 universe, trailing 3y)
and a robustness cut (top-200, 5y). The verdict counts only if it holds on both.

---

## 2. The result

### H1′ — do candidates expand *beyond* their own ATR?

`Expansion = realized intraday range ÷ ATR`. Normalizing by ATR is what kills the tautology: >1 means the
name moved *more* than the volatility we screened it for.

| Cut | Candidate | Baseline | Edge (CI) | p | Verdict |
|---|---|---|---|---|---|
| **Headline** (top-500, 3y) | **1.49×** | 0.95× | +0.55 [0.48, 0.61] | 0.000 | **SUPPORTED** |
| **Robustness** (top-200, 5y) | **1.18×** | 0.94× | +0.24 [0.21, 0.27] | 0.000 | **SUPPORTED** |

**This is the headline finding.** The baseline realizes *less* than its ATR (≈0.94×) — average liquid names
mean-revert intraday. The candidates realize *more* (1.18–1.49×) — they over-expand relative to their own
volatility. That difference cannot be an artifact of having selected high-ATR names, because the metric is
already ATR-normalized. **The engine selects genuine expansion, not just volatile names.**

### H2 — is the expansion *tradeable* (not chop)? (moderate 2-of-3 bar)

| Metric | Headline cand / base | Robustness cand / base | Clears (both cuts) |
|---|---|---|---|
| Trend efficiency `\|c−o\|/(h−l)` | 0.478 / 0.450 | 0.476 / 0.455 | ✓ |
| Capturable move % (MFE proxy) | 5.87 / 2.28 | 5.24 / 2.51 | ✓ |
| Net move % (open→close) | 3.76 / 1.42 | 3.34 / 1.57 | ✓ |

**3 of 3 clear on both cuts** (bar was 2 of 3). The capturable move and net move are each **~2.3–2.6× the
baseline** — the range is a real directional excursion an intraday strategy could target, not round-trip
chop. Trend efficiency clears too but by a *thin* margin (≈0.02–0.03): candidates are *slightly* more
directional, but most of the tradeability signal is in the *size* of the move (CM/NM), not its *efficiency*.

### H3 — do Gap and RVOL earn their seat beside ATR?

Both Gap and RVOL are **additive over an ATR-only screen** on both cuts (ΔExpansion and ΔCapturable-move CIs
exclude 0 for ATR+Gap, ATR+RVOL, and the full set). **Recommendation: keep ATR + Gap + RVOL** — no signal is
decoration. (RVOL adds slightly more than Gap on the expansion metric; both clear comfortably.)

---

## 3. The honest qualifiers

1. **Magnitude is regime/universe-dependent.** Expansion is stronger on the recent 3y / top-500 cut (1.49×)
   than on the 5y / top-200 cut (1.18×). Both clear the bar, so the verdict is *Supported*, not *Divergent*
   — but the *edge size* is not constant: a wider, more recent universe shows more expansion. Size the
   expectation to the cut, don't quote 1.49× as universal.
2. **Trend efficiency is the weak leg.** The tradeability case rests on move *size* (CM/NM ~2.5×), not move
   *efficiency* (TE +0.02). The candidates' range is large and directional *enough*, but not dramatically
   "cleaner" than the baseline's — an intraday strategy still needs real entry/exit logic; the engine hands
   it bigger, slightly-more-directional moves, not free money.
3. **Daily-bar approximations unchanged.** Gap uses the official open (~5-min proxy for the 09:25 premarket
   price) and RVOL is a daily proxy. This affects selection *precision*, not the *validity* of the
   ATR-normalized comparison — but it is the reason the next gate is data, not more backtesting.

---

## 4. Decision (against the frozen §4 matrix)

**H1′ ✓ and H2 ✓ on both cuts → "Supported — engine finds genuine, tradeable expansion."** Per the
pre-registered matrix, the next gate is **premarket data + a live-data replication**, *not* further
historical iteration. Specifically:

- **Promote SCAN-001 from Prototype → Validated (capability), with the §3 qualifiers recorded.**
- **Next gate (pre-promotion to any live use):** wire the real premarket feed (PR #221 gappers) and replay
  H1′/H2 on live-data candidates — confirm the daily-proxy result survives true 09:25 inputs.
- **Engine config frozen:** ATR + Gap + RVOL, all three retained (H3).
- **Not in scope / still downstream:** entry/exit mechanics, sizing, risk — the engine selects; strategies
  trade. The §3.2 finding (size > efficiency) is an input to *that* design, not a blocker here.

---

## 5. Reproduce

```bash
PYTHONPATH=apps/backend apps/backend/.venv/Scripts/python.exe \
  apps/backend/scripts/candidate_engine_v0_2.py \
  --store apps/backend/data/factor_data_full.duckdb --end 2026-06-12 --bootstrap 2000 \
  --report-dir docs/implementation/evidence/scan_001_candidate_engine_v0_2
```

Engine tests: `pytest tests/factor_data/test_candidate_engine.py -q` (29 tests, green).
