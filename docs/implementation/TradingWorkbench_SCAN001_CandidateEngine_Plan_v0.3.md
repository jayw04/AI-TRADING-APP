# SCAN-001 — Discovery-Stability Study: Research Plan & Pre-Registration (v0.3)

**Program:** SCAN-001 (Market Opportunity Discovery Engine — first profile of the Discovery Lab)
**Type:** Platform Capability · **Status:** Validated (v0.2) → v0.3 follow-on pre-registration
**Predecessor:** v0.2 results (engine validated on both cuts; §3.4 showed the expansion edge *compresses in the
2022 bear* — the preliminary signal this study formalizes)
**Date:** 2026-06-23 · **for owner review / approval before any run**

> **The question v0.3 answers: *when* does the Discovery Engine work best?** v0.2 proved the engine selects
> genuine, tradeable expansion *on average* across two cuts. But the by-year read already showed the edge is
> **not flat** — it shrinks in the 2022 bear. v0.3 decomposes the validated edge by **market regime**
> (bull / bear / sideways) and **volatility regime** (high / low), turning "it works" into "it works *here*,
> weaker *there*" — a usable input for every downstream strategy's regime gating. This is a **stability /
> conditional-strength** study, not a re-validation: v0.2's verdict stands; v0.3 maps its boundaries.

---

## 0. Why v0.3 (and what it is *not*)

- **It is:** a conditional decomposition of the *already-validated* H1′ expansion edge (and the H2 tradeability
  edge) across pre-registered regime states, to identify where the capability is strong, weak, or absent.
- **It is not:** a re-test of whether the engine works (v0.2 settled that), nor a parameter search, nor a
  strategy. The engine config is **frozen** (ATR + Gap + RVOL, per v0.2 H3); v0.3 changes only the *lens*.
- **Honest fork it allows:** if the edge goes **negative in any regime**, that regime becomes a documented
  no-go for the engine — a real, citable boundary, not a failure of the capability.

---

## 1. Frozen regime definitions (PIT, computed BEFORE any edge is seen)

Regimes are classified per trading day from a **broad-market proxy**, computed point-in-time from data that
exists on the SEP store (SPY is absent from Sharadar SEP — see [[data_sf1_access_tier]] — so the proxy is
built from the liquid universe itself, which is exactly the "market" the candidate edge is measured against).

**Market proxy** `M_t` = the equal-weight cumulative index of the day's eligible liquid universe (the same
equal-weight baseline the v0.2 harness already computes). All proxy statistics use **only bars up to and
including day t** — no look-ahead.

### 1a. Market regime (3-state) — frozen rule

| Regime | Condition on the proxy `M` at day *t* |
|---|---|
| **Bull** | `M_t > SMA200(M)_t` **and** trailing 60-trading-day return of `M` > 0 |
| **Bear** | `M_t < SMA200(M)_t` **and** trailing 60-trading-day return of `M` < 0 |
| **Sideways** | everything else (mixed trend/level signal) |

200-day SMA + 60-day return sign is a standard, non-optimized trend classifier. The thresholds (200, 60, zero)
are **frozen here, before results** — no tuning to make a regime "look" better.

### 1b. Volatility regime (2-state) — frozen rule

| Regime | Condition |
|---|---|
| **High-vol** | trailing 21-day realized volatility of `M` > its own trailing **252-day median** |
| **Low-vol** | otherwise |

A self-referential median split (each day compared to the recent year) so the classifier adapts to the era and
needs no absolute vol threshold. PIT: the 252-day median uses only prior days.

### 1c. The 3×2 regime grid

The two axes cross into six cells (Bull/Bear/Sideways × High/Low-vol). The headline analysis is the **two
marginal axes** (3 market states, 2 vol states); the **6-cell grid is secondary** (cells get thin — governed
by the minimum-sample rule in §3).

---

## 2. Frozen hypotheses

The metric is the v0.2 **expansion edge** `E_candidate − E_baseline` per day (H1′), with the **capturable-move
edge** as the tradeability companion (H2). Both are bucketed by regime and bootstrapped within each bucket.

### H-stab-1 — Market-regime persistence

> The expansion edge is positive and CI-separated in **each** market regime (bull, bear, sideways).

- **Per-regime verdict:** *holds* if that regime's edge has a 95% bootstrap CI excluding 0 (positive).
- **Pre-registered reading:** the headline question is **which regimes hold and which don't**, and the **rank
  order** of edge magnitude (the "works best in ___" deliverable). We expect (from v0.2 §3.4) bull ≥ sideways
  ≥ bear; the study confirms or refutes that ordering, it does not assume it.

### H-stab-2 — Volatility-regime persistence

> The expansion edge is positive and CI-separated in **both** volatility regimes (high, low).

- A plausible prior (un-tested): more intraday range opportunity in high-vol regimes. The study measures it.

### H-stab-3 — Tradeability stability (companion)

> The H2 capturable-move edge holds (CI-separated) in the same regimes where H1′ holds — i.e. where the engine
> finds expansion, that expansion stays *tradeable*, not just larger.

- Where H1′ holds but H-stab-3 fails, the regime is flagged **"expands but harder to harvest"** (the v0.2 §3.2
  "size > efficiency" caveat, made regime-specific).

---

## 3. Frozen run configuration (locked before the run)

| Parameter | Value | Rationale |
|---|---|---|
| **Primary window** | 2010-06-13 → 2026-06-12 (~16y), top-200 universe | Long history is **required** here: regime cells (esp. bear / high-vol) need enough days to bootstrap. Covers 2011 EU crisis, 2015-16 selloff, 2018-Q4, 2020 COVID crash, 2022 bear, plus multiple bulls. |
| **Recency cross-check** | 2021-06 → 2026-06, top-500 | Ties back to v0.2's headline universe; confirms the regime pattern in the recent, wider book. |
| **Minimum cell sample** | **≥ 60 trading days** | A regime bucket with < 60 days is reported as **"insufficient sample — descriptive only,"** never a pass/fail verdict. Guards against over-reading a thin bear/high-vol slice. |
| **Engine** | ATR + Gap + RVOL, top-15/day (frozen, v0.2 H3) | v0.3 changes the lens, not the engine. |
| **Bootstrap** | seeded (17), circular-block, n=2000, 95% CI | Same `evidence.py` machinery as v0.2 / MOM / LOW — cross-comparable. |

**Multiple-comparisons discipline:** the confirmatory tests are the **5 marginal regimes** (3 market + 2 vol).
The 6-cell grid and §6 seasonality are **exploratory / descriptive** — reported with that label, never elevated
to a pass/fail claim post hoc.

---

## 4. Pre-registered decision matrix (frozen BEFORE results)

| Outcome | Classification | Consequence for the capability |
|---|---|---|
| Edge positive + CI-separated in **all** market & vol regimes | **Regime-robust** | Capability is broadly deployable; downstream strategies need no regime gate on *opportunity availability*. |
| Edge positive in some regimes, **weak / not-separated** in others (e.g. bear) | **Regime-conditional** | The capability carries a documented regime caveat; downstream strategies should **condition exposure on regime** (a usable finding, not a demotion). |
| Edge **negative** in any regime | **Regime-fragile (in regime X)** | Regime X is a **documented no-go** for the engine; the capability ships with that boundary explicit. |
| A regime cell < 60 days | **Insufficient sample** | Reported descriptively; revisited only when more history accrues. |

The v0.2 **Validated (Capability)** verdict is **unchanged by any of these** — v0.3 annotates *where* it applies;
it cannot un-validate a result that already held on the full sample.

---

## 5. Method & reuse (≈90% reuse)

- **Engine:** unchanged (`app/factor_data/candidate_engine.py`).
- **Harness:** extend `scripts/candidate_engine_v0_2.py` (or a thin `..._v0_3.py` wrapper) to (a) compute the
  PIT market-proxy series + the frozen regime labels per day, (b) bucket the existing daily edge series by
  regime, (c) bootstrap within each bucket, (d) emit the regime evidence package + the ranked "works-best"
  table. The per-day edge computation, universe, PIT plumbing, and bootstrap are all reused verbatim.
- **New pure helpers** (unit-tested at the v0.2 bar): `sma`, `trailing_return`, `realized_vol`, and the two
  frozen classifiers `market_regime(...)`, `vol_regime(...)` — added to the engine module so they are testable
  in isolation and reusable by future Discovery-Lab profiles.
- Read-only research; **no order path**.

---

## 6. Seasonality (exploratory — descriptive only, NOT a hypothesis)

The owner raised seasonality. To avoid multiple-comparisons fishing, v0.3 reports month-of-year and
day-of-week expansion-edge *descriptively* (a table, no pass/fail, no bootstrap verdict). If a striking,
mechanism-plausible pattern appears (e.g. earnings-season months), it becomes a *separately pre-registered*
question in a later iteration — never a claim mined from this run.

---

## 7. Research risk register

| Risk | Mitigation |
|---|---|
| **Thin regime cells** (few bear / high-vol days) over-read | The ≥60-day minimum-sample rule; the 16-year primary window chosen specifically for regime coverage. |
| **Regime definition tuned to the answer** | Definitions frozen in §1 before any edge is computed; standard 200-SMA/60-day/median rules, no optimization. |
| **Proxy ≠ the real market** (universe-built, not SPY) | The proxy *is* the baseline the edge is measured against — internally consistent; flagged that it is a universe proxy, not an index, and that an index-based re-run is a follow-on if SPY history is sourced. |
| **Look-ahead in regime labels** | All proxy statistics (SMA200, 60-day return, 21-day vol, 252-day median) use only bars ≤ day *t*; unit-tested. |
| **Over-claiming from exploratory axes** | §3 multiple-comparisons rule: only the 5 marginal regimes are confirmatory; grid + seasonality are labeled descriptive. |

---

## 8. Out of scope (v0.3)

Premarket data integration (still the separate hard gate before any live use), intraday entry/exit mechanics,
sizing/risk, and any change to the engine config. v0.3 is purely the regime/vol decomposition of the validated
edge.

---

## 9. Deliverables

1. Pure helpers + frozen classifiers in `candidate_engine.py` (+ tests at the v0.2 bar; ruff/mypy clean).
2. Regime-decomposition harness + evidence package (`evidence/scan_001_candidate_engine_v0_3/`, JSON + MD),
   reproducible (seed, git, command), with the ranked **"works-best / weakest regime"** table.
3. **Results doc** `..._CandidateEngine_Results_v0.3.md` — the per-regime verdicts against the §4 matrix, the
   regime classification (Robust / Conditional / Fragile), and the §6 seasonality description.
4. Registry update (v0.9) — record the regime profile as the SCAN-001 follow-on outcome; close or keep-open the
   research line accordingly.

Read-only research throughout. **Walk-away ≥ 1 h** before merge.

---

## 10. Open questions (confirm before build)

1. **Primary window** — 16 years (2010-2026) as pre-registered, or longer (2000-2026, more crises but older
   microstructure)?
2. **Market-regime granularity** — 3-state (bull/bear/sideways) as frozen, or add a 4th "recovery/early-bull"
   state?
3. **Minimum cell sample** — 60 days, or stricter (e.g. 120) given 16 years gives ample room?
