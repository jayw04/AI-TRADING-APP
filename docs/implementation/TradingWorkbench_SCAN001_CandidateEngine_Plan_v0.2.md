# SCAN-001 — Candidate Engine: Research Plan & Pre-Registration (v0.2)

**Program:** SCAN-001 (Market Opportunity Discovery — first profile of the Discovery Lab)
**Type:** Platform Capability · **Status:** Prototype → v0.2 pre-registration
**Predecessor:** v0.1 plan + prototype findings v0.1 (PR #229)
**Date:** 2026-06-22 · **for owner review / approval before any run**

> **Why a v0.2 at all.** The prototype's H1 ("candidates realize higher intraday range than the
> baseline") came back **+3.24%, p≈0, 99.9% daily win** — and that near-perfect win rate is the tell
> that the result is *partly definitional*: we select on **ATR %**, which is itself a range measure, so
> "high realized range" is close to tautological. v0.2 exists to **remove the tautology** and ask the
> three questions that actually decide whether this engine has found something tradeable. It changes the
> *questions and metrics*, not the plumbing — the engine and harness from v0.1 are reused wholesale.

---

## 0. The one-line goal

Decide, on pre-registered evidence, whether SCAN-001 selects names that move **more than their own
volatility predicts**, in a **directional (tradeable)** way, and whether **Gap and RVOL earn their place
beside ATR** — or whether the prototype's edge was an artifact and the construction line should simplify or
close.

This is a genuine fork: v0.2 can produce an **honest no** (the edge was tautological), which is a valid,
citable outcome under Evidence Engineering — exactly as RNG-001's rejection was.

---

## 1. Hypotheses (frozen BEFORE the run)

Three independent hypotheses, each with a pre-registered metric and success bar. All are evaluated on the
**realized outcome** of the selected day; none of the new metrics is fed back into selection (no leakage).

### H1′ — Expansion beyond ATR (the de-tautologized H1)

> Candidates expand **more than their own ATR predicts** — and more than the baseline does.

- **Metric — expansion ratio** `E = intraday_range_pct / atr_pct` (same units; how many ATRs of range the
  name actually realized). Normalizing by ATR is what removes the "we picked high-ATR names" tautology.
- **Pre-registered bar (BOTH must hold):**
  1. Candidate mean `E` **> 1.0** (they expand beyond their own vol, not merely match it), **and**
  2. Edge `E_candidate − E_baseline` has a 95% bootstrap CI that **excludes 0**.
- **Interpretation:** if `E_candidate ≈ E_baseline ≈ 1`, the prototype edge was tautological — the screen
  picks volatile names that realize exactly their volatility, no opportunity *discovered*.

### H2 — Directionality (is the range tradeable?)

> The realized range is a **directional move**, not chop a strategy can't monetize.

- **Metrics (two, reported together):**
  - **Trend efficiency** `TE = |close − open| / (high − low)` — what fraction of the day's range was net
    directional travel (0 = pure round-trip chop, 1 = clean one-way trend).
  - **Capturable move** `CM = max(high − open, open − low) / open × 100` — the best single-direction excursion
    from the open (an MFE proxy), the move an intraday strategy could actually target.
- **Pre-registered bar:** candidate **`TE` ≥ baseline `TE`** (CI on the difference not materially negative)
  **and** candidate **`CM` > baseline `CM`** (CI excludes 0). I.e. the extra range is *at least as
  directional* as the baseline's and the capturable excursion is genuinely larger.
- **Interpretation:** wider-but-choppier range (higher range, lower `TE`) is a **caution flag** for any
  downstream strategy — the opportunity is real but hard to harvest; we say so rather than imply tradeability.

### H3 — Signal attribution (do Gap and RVOL earn their seat?)

> Gap and RVOL add opportunity **over an ATR-only screen** — otherwise they are decoration and the engine
> should simplify (less overfitting surface = more honest capability).

- **Method:** build four candidate sets per day from the *same* eligible universe and score H1′/H2 on each:
  `ATR-only`, `ATR+Gap`, `ATR+RVOL`, `ATR+Gap+RVOL` (the full engine).
- **Pre-registered bar:** a multi-signal set must beat `ATR-only` on `E` **and** `CM` by a CI-separated
  margin to be judged additive. If neither Gap nor RVOL clears, **recommend simplifying the engine to the
  signals that do** (Occam; documented, not silently dropped).
- **Interpretation:** this is the attribution the prototype explicitly deferred — it tells us which filters
  are load-bearing.

---

## 2. What is reused vs new (≈85% reuse)

| Component | v0.1 (prototype) | v0.2 |
|---|---|---|
| Pure selection core (`candidate_engine.py`) | built | **reused**; add pure metrics `expansion_ratio`, `trend_efficiency`, `capturable_move` + a `signals=` selector so the harness can build the 4 attribution sets |
| Research harness (`scripts/candidate_engine.py`) | built | **reused**; add the 3 hypotheses + the attribution sweep + a v0.2 evidence section |
| SEP store / monthly PIT universe / block bootstrap | built | **reused unchanged** |
| Data | daily SEP | **daily SEP, unchanged** (see §3 — daily bars suffice for these questions) |

New code is small and additive: three pure functions (each unit-tested at the v0.1 bar), one selector
argument, and harness wiring. No new subsystem, no order-path contact.

---

## 3. Why daily bars are sufficient for v0.2 (and where they are NOT)

v0.2's three questions are about whether the selected names **behave differently in ways not mechanically
implied by the selection** — expansion *relative to* ATR, directionality, and marginal signal value. Those
are answerable on daily OHLC because they compare the *outcome* to the *features*, not to a premarket
snapshot. So v0.2 stays on the survivorship-free daily store and needs no new data.

The daily-bar limitation is honestly bounded and unchanged from v0.1: **gap uses the official open (~5-min
approximation of the 09:25 premarket price) and RVOL is a daily proxy.** That approximation affects the
*precision of selection*, not the *validity of the de-tautologized comparison*. **A real premarket feed
(the PR #221 gappers source) remains a hard prerequisite before any promotion past prototype / any live
claim** — it is explicitly *not* in v0.2 scope, only named as the gate that follows a positive v0.2.

---

## 4. Pre-registered decision matrix (frozen BEFORE results)

| Outcome | Verdict | Action |
|---|---|---|
| **H1′ ✓ and H2 ✓** | **Supported** — engine finds genuine, tradeable expansion | Promote toward a validated capability; next gate = premarket data + a live-data replication. |
| **H1′ ✓, H2 ✗** (expands but chops) | **Partial** — real opportunity, not cleanly tradeable | Keep the capability, flag the tradeability caveat for downstream strategy design; study entry/exit mechanics separately. |
| **H1′ ✗** (`E` ≈ baseline ≈ 1) | **Not supported** — prototype edge was tautological | Honest no on the current signals; either redesign the opportunity signal or **close the construction line** (RNG-style citable rejection). |
| **H3:** Gap/RVOL not additive | (orthogonal) | **Simplify** the engine to the load-bearing signals; record the others as tested-and-dropped. |

Bootstrap: seeded (seed 17), circular-block, n=2000, 95% CI + one-sided p-value — the same `evidence.py`
machinery as MOM/LOW/SEC, so the numbers are comparable across the registry. Headline window **2018-2026**
(full prototype window) **plus** sub-period robustness (pre-COVID / COVID / 2022 / 2023-26) — a result that
only holds in one regime is not supported.

---

## 5. Deliverables

1. `candidate_engine.py` — three pure outcome-metric functions + a `signals=` selector (with tests at the
   ≥ v0.1 bar; ruff/mypy clean).
2. `scripts/candidate_engine.py` — H1′/H2 scoring + the H3 attribution sweep + a v0.2 evidence package
   (`evidence/scan_001_candidate_engine_v0_2/`, JSON + MD), reproducible (seed, git, command).
3. **Results doc** `TradingWorkbench_SCAN001_CandidateEngine_Results_v0.2.md` — the verdict against the §4
   matrix, the attribution finding, and the explicit next-gate (premarket data) if supported.
4. Registry update (v0.8) — Prototype → the v0.2 verdict; capability rows updated.

Read-only research throughout. **Walk-away ≥ 1 h** before merge, per the consequential-PR convention.

---

## 6. Research risk register

| Risk | Mitigation |
|---|---|
| **Another hidden tautology** (e.g. `CM` correlates with ATR too) | Report `CM` *and* the ATR-normalized `CM/atr_pct`; pre-register that the headline is the normalized form. |
| **Sub-period instability** | Headline requires the edge to hold across the four sub-periods, not just the full window. |
| **Daily-bar gap/RVOL noise inflating attribution** | H3 is directional, not a precise effect size; flagged as "additive / not additive on daily proxies," to be re-confirmed on premarket data before any live claim. |
| **Over-iteration (sweep-to-fit)** | Thresholds in §1/§4 are frozen here, before the run; v0.2 is one run + sub-periods, not a parameter search. A null result ships as a null result. |

---

## 7. Out of scope (v0.2)

Premarket data integration (the gappers feed), intraday entry/exit mechanics, sizing/risk (downstream
strategies), multiple candidate *engines*, and Discovery Lab generalization — all remain post-v0.2, exactly
as in the v0.1 plan §7/§12. v0.2 is deliberately the *minimum* honest test that resolves the prototype's
caveat.

---

## 8. Open questions (confirm before build)

1. **Headline window** — confirm 2018-2026 + the four sub-periods above (vs. extending to the full
   survivorship-free 1997-2026, which is slower but more regimes).
2. **H2 bar strictness** — is "`TE` ≥ baseline" the right tradeability bar, or do you want a positive
   margin (candidates *more* directional, not merely *as* directional)?
3. **Universe size** — keep top-200 by $-vol, or widen (more candidates/day, thinner names)?
