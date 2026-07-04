| Field | Value |
|---|---|
| Document version | v0.2 (final — owner approved for implementation 2026-07-04, 9.7/10; v0.2 folds the pre-execution refinements) |
| Date | 2026-07-04 |
| Phase | FI-001 (Factor Interaction & Portfolio Engineering) — Phase 4 follow-on; owner priority #4 |
| Session | CAP-020 Regime-Overlay Validation |
| Predecessor | FI-001 Phase 4 Adaptive (PR #330) · PORT-001 #3 total-return pricing (PR #348, `f780b3a`) |
| Successor | (on Validated) paper activation → Continuous Evidence Engine observation |
| Repository | github.com/jayw04/AI-TRADING-APP |
| Scope | Validate **CAP-020** — the `regime_gross` rule (equal-weight combined book, de-risk gross to `g` when the market proxy is below its N-day SMA) — against the owner's risk-adjusted / Calmar-central bar, net of costs, with IS/OOS + walk-forward + parameter sweeps + bootstrap CIs, then set its registry label via a deployment decision matrix. |
| Estimated wall time | 6–9 hours (validation harness + cost/IS-OOS/sweeps + evidence package + result doc + PR) |
| Tag on completion | `fi001-cap020-validation-complete` |
| Out of scope | Live/paper activation; a new ADR for the overlay; the ADR-0020/0022 vol-target overlay (a *different* overlay); building a new paper book; re-optimizing the factor books; the sector arm if box sector data is still absent (documented, not blocking). |

---

## 0. Executive summary

- **Objective** — move CAP-020 from *"Promising"* to a defensible verdict by measuring whether the 200d-SMA gross overlay materially improves the equal-weight combined book's **drawdown and Calmar, net of costs, out-of-sample, and robustly** — not just at one lucky parameter point.
- **What CAP-020 is** — the `regime_gross` rule from FI-001 Phase 4 (`scripts/fi001_phase4_adaptive.py`): eqw the validated factor books, scale gross to `g` (default 0.5) when a market proxy < its N-day SMA (default 200), else 1.0. Distinct from the live ADR-0020 vol-target overlay.
- **Why now** — FI-001 concluded that combining factors is *risk management via a regime gross overlay, not alpha*; CAP-020 is that overlay, and it's owner priority #4. Its current evidence is return-level, single-point, with ΔSharpe CIs spanning zero.
- **Verdict mechanism** — a **deployment decision matrix** (owner-specified): Validated / Conditionally Promising / Rejected-Evidenced. Rejection is a first-class outcome (RNG-001 discipline: a verdict requires evidence).
- **Risk to live trading** — **none.** This is an offline research/backtest study; it changes no live book and adds no order-path code.

### §0.1 — Research objectives vs deployment objectives

Kept explicitly separate so the study's *findings* are not conflated with the *decision* they inform:

**Research objectives** (what the study measures)
- Determine whether CAP-020 improves the combined book's **portfolio quality** (drawdown / Calmar), net of realistic costs.
- **Assess robustness** across parameters, sub-periods, and cost levels.
- **Quantify uncertainty** (bootstrap CIs on the drawdown/Calmar improvement).
- **Produce reproducible evidence** (Evidence Package + result doc).

**Deployment objectives** (what the decision does)
- Set the **registry status** via the decision matrix (Validated / Conditionally Promising / Rejected-Evidenced).
- Decide **paper-trading eligibility** (Validated → eligible → then Continuous Evidence Engine observation, ADR-0022 §7).
- **Update the research registry** (doc matrix + `programs.py`).

The research objectives are answered by numbers; the deployment objectives are answered by applying §4 to those numbers.

## Review response (v0.2 — how the final `comments.md` was folded)

| # | Owner suggestion | Where addressed |
|---|---|---|
| 1 | Separate research vs deployment objectives | §0.1 (new) |
| 2 | Statistical-power / sample-limitations discussion | §5.5 + §9 note 7 |
| 3 | More than one regime proxy (concept vs implementation) | §8 (future) + §9 note 8 |
| 4 | Explicit robustness rule (proportion of param combos) | §4 "Validation checks" — ≥ 2/3 of the grid |
| 5 | Economic significance (not just statistical) | §4 "Economic-significance floor" |
| 6 | Reproducibility metadata in the Evidence Package | §5.7 (commit / env / seed / dataset version) |
| 7 | Risk-matrix: regime frequency changes over time | §7 (new row) |
| key | **Hierarchy** of acceptance criteria (one primary rule) | §4 restructured — Calmar = primary decision rule |

## 1. Why this session exists

FI-001's headline finding: combining validated factor books (MOM/LOW/SEC/TREND) is **drawdown reduction, not alpha**, and the best drawdown-managed book was *equal-weight + a market-regime gross overlay* — CAP-020. But Phase 4 only measured it at the **return level**, at a **single parameter point** (SMA=200, risk-off gross=0.5), over one window (2019–2026, n≈150), with **no turnover cost**, **no IS/OOS split**, **no parameter sweep**, and a **ΔSharpe CI that spans zero**. The registry (`TradingWorkbench_Research_Program_Registry_v0.1.md:256`) is explicit: this "earns live validation, not the word [validated]."

This session closes exactly those gaps so the label can move — up to *Validated*, sideways to *Conditionally Promising*, or down to *Rejected (Evidenced)* — on evidence, not vibes. ADR-0022 §7 already sets the platform norm: *"no regime signal governs a real book until it has cleared survivorship-free + IS/OOS + walk-forward validation, then paper observation."* This is that clearance for CAP-020.

## 2. What this session ships

- `scripts/cap020_regime_validation.py` — a reproducible validation harness that builds the eqw combined book (reusing FI-001 Phase 4's book construction), applies the **parameterized** overlay, and runs the full grid (below), emitting per-cell metrics + bootstrap ΔCIs vs the overlay-OFF benchmark.
- **Turnover + transaction-cost modeling** (cost sweep 5/10/20/50 bps, mirroring the factor_lab runner) — the #1 missing piece.
- **IS/OOS split + walk-forward windows** and **parameter sweeps** (SMA window, risk-off gross) — robustness.
- **Bootstrap CIs** on ΔMaxDD and ΔCalmar (paired vs eqw-overlay-OFF), reusing the Phase 4 bootstrap.
- An **Evidence Package** + a result doc `docs/implementation/evidence/cap_020/CAP020_Validation_v1.0.md` applying the decision matrix.
- **Registry label update** in `TradingWorkbench_Research_Program_Registry_v0.1.md` (CAP-020 line) + FI-001 headline in `app/research/programs.py`, per the verdict.
- Unit tests for the new harness pieces (overlay parameterization, turnover/cost, metric calcs) — pure/offline.

## 3. Prerequisites

- Factor price data for the four books available where the study runs (the FI-001 factor store / momentum backtest inputs). Phase 4 ran on the box; this study runs where that data lives (offline research; not the live stack).
- FI-001 Phase 4 code (`scripts/fi001_phase4_adaptive.py`) + tests (`tests/scripts/test_fi001_phase4.py`) — the book-construction + bootstrap source.
- factor_lab primitives: walk-forward `_windows` (`factor_lab/runner.py:68`), the cost-sweep pattern, `verdict.classify`.

## 4. Acceptance criteria (owner-defined — modified Option 2, Calmar-central)

Benchmark throughout = the **equal-weight combined book with the overlay OFF** (the honest null — the overlay must beat *that*, not a strawman). All metrics computed **net of transaction costs**, **out-of-sample**.

The criteria are a **hierarchy**, not a flat list — so if two metrics conflict, the decision is unambiguous (owner review, key methodological point):

1. **PRIMARY decision rule — Calmar improvement.** The overlay is a portfolio risk overlay, so the single metric that decides it is **return per unit of drawdown**. Required: **ΔCalmar > 0 vs the benchmark, OOS, net of costs, with the bootstrap CI excluding zero, and economically meaningful** (§ economic-significance floor).
2. **REQUIRED supporting evidence — Max Drawdown reduction.** ΔMaxDD must be a genuine reduction (CI excludes zero). Calmar can rise via either a smaller drawdown or a higher return; for a *de-risking* overlay the improvement must come with an actual drawdown reduction, not only a return artifact — so MaxDD reduction is a required corroborant of the primary rule.
3. **GUARDRAILS — must not do harm.** ΔSharpe ≥ −0.05 (ideally ≥ 0) and ΔCAGR ≥ −2.0 pp vs the benchmark. A Calmar win bought by wrecking Sharpe or giving up most of the return fails here.
4. **VALIDATION CHECKS — is the result trustworthy?**
   - **Statistical:** the ΔCalmar (primary) and ΔMaxDD (supporting) CIs exclude zero (paired bootstrap vs benchmark).
   - **Robustness (explicit rule):** **≥ 2/3 of the tested parameter combinations** (the SMA × risk-off-gross grid) satisfy the primary rule *and* the guardrails — so no one or two isolated settings can carry the conclusion.
   - **Sub-period consistency:** the benefit holds OOS and does not invert across walk-forward windows / market environments.

**Economic-significance floor (owner review #5).** Beyond statistical significance, the improvement must be *operationally* meaningful net of realistic frictions: a ΔCalmar of, say, +0.01 with a wide CI is statistically curious but not deployable. The §4 "material" thresholds below are the economic floor; a result that clears the CI test but not the material threshold is **Conditionally Promising**, not Validated.

**Proposed "material" thresholds (conservative defaults — owner confirms/edits in review):**
| Metric | Material bar | Note |
|---|---|---|
| ΔMaxDD | ≥ 5 pp reduction, CI excludes 0 | Phase 4 showed ~+6.4pp vs eqw at the single point |
| ΔCalmar | ≥ +0.10 absolute (or ≥ +15% rel.), CI excludes 0 | the primary portfolio-overlay metric |
| ΔSharpe (guardrail) | ≥ −0.05 | ideally ≥ 0; "not materially worse" |
| ΔCAGR (guardrail) | ≥ −2.0 pp | overlay gives up some bull CAGR by design |

**Deployment decision matrix (owner-specified — replaces a binary verdict), driven by the hierarchy:**
| Result | Registry label | Production decision |
|---|---|---|
| **Primary (Calmar)** clears CI + economic floor, **MaxDD** corroborates, **all guardrails** hold, **≥ 2/3 grid** robust, consistent OOS | **Validated (v1.0)** | Eligible for paper activation → then Continuous Evidence Engine observation (ADR-0022 §7) |
| Drawdown/Calmar improve but **a guardrail fails**, or a **CI touches 0**, or **< 2/3 grid**, or below the **economic floor** | **Conditionally Promising** | More research (e.g. tune the risk-off gross, add a second signal/proxy) |
| **No** drawdown/Calmar benefit, benefit **inverts OOS**, or portfolio quality materially degrades | **Rejected (Evidenced)** | Do not deploy; documented like RNG-001 |

Registry mapping: the doc matrix carries the free-text label; `app/research/programs.py`'s enum (`validated`/`rejected`/`inconclusive`/`research`/`planned`) maps *Conditionally Promising → inconclusive*, *Rejected (Evidenced) → rejected*, *Validated → validated*.

## 5. Detailed work

### §5.1 — The book + overlay under test
- **Book:** equal-weight of the validated factor books, reconstructed via FI-001 Phase 4's existing construction (`fi001_phase4_adaptive.py`) — import/extend, don't rebuild.
- **Overlay (parameterized):** `gross_t = g if proxy_{t-1} < SMA_N(proxy)_{t-1} else 1.0`, applied to the eqw book's returns. `.shift(1)` (no look-ahead), warm-up fails open to risk-ON — as in `_regime_riskon` (`fi001_phase4_adaptive.py:89`). Free knobs = `N` (SMA window) and `g` (risk-off gross).

### §5.2 — Turnover + transaction cost (the #1 gap)
- Turnover from the overlay = |Δgross| on each regime flip (plus the book's own rebalance turnover, already modeled in the base backtest). Cost = turnover × bps.
- **Cost sweep 5/10/20/50 bps** (factor_lab convention). Report every metric net of each cost level; the acceptance bar is evaluated at a **stated default (e.g. 10 bps)** with the sweep showing sensitivity. Expectation: 200d-SMA flips are infrequent (~a few/yr) → low overlay turnover → small cost drag, but this must be *shown*, not asserted.

### §5.3 — IS/OOS + walk-forward
- Split the 2019–2026 sample IS/OOS (e.g. 60/40 chronological) and run walk-forward windows (`factor_lab/runner.py:_windows` precedent; `scripts/walk_forward_regime_overlay.py` is the closest regime study to mirror). The overlay must clear the bar **OOS**, not just in-sample.

### §5.4 — Parameter sweep + robustness surface
- Grid `N ∈ {150,200,250} × g ∈ {0.3,0.5,0.7}` × cost `∈ {5,10,20,50}bps`. Produce a robustness surface: the drawdown/Calmar benefit should be a *plateau*, not a single spike at (200, 0.5). A benefit that exists only at one knob setting → fails robustness → Conditionally Promising or Rejected.

### §5.5 — Statistics & statistical power (owner review #2)
- Paired bootstrap (reuse Phase 4's) of ΔMaxDD and ΔCalmar vs the eqw-overlay-OFF benchmark; report point estimate + CI. "Significant" = CI excludes zero.
- **Power / sample-limitation caveat (bounds the conclusions, does not invalidate them):** the sample is **2019-01 → 2026-06 (~n=150 monthly / ~1,850 daily)** — a **relatively short window with few full market cycles and only a couple of major bear episodes** (2020 COVID, 2022). Drawdown/regime statistics are inherently *low-n on the events that matter* (the overlay only "acts" in the handful of below-SMA stretches). The verdict language must reflect this: a *Validated* result is "validated over 2019–2026," and the Continuous Evidence Engine (CAP-021) then accrues out-of-window confidence. This is why *Validated → eligible for paper*, not *straight to live*.

### §5.6 — Metrics reported per cell
CAGR, Sharpe, MaxDD, **Calmar**, worst-month / CVaR(5%) (tail), turnover, cost drag, number of regime flips, and the paired ΔCIs vs benchmark.

### §5.7 — Verdict + registry update + reproducibility metadata (owner review #6)
Apply §4's decision matrix to the OOS, cost-net, robustness-checked results → write the result doc + Evidence Package → update the CAP-020 registry line + FI-001 headline in `programs.py`. The **Evidence Package embeds reproducibility metadata** so a future run can reconstruct these exact numbers: **git commit hash, Python version, key package versions (numpy/pandas/scipy), the random seed used for the bootstrap, and the dataset/factor-store version (path + as-of date + row counts)**. The bootstrap seed is fixed and recorded (determinism, per the factor_lab convention).

## 6. Manual smoke (how to run)
```bash
# where the FI-001 factor data lives (offline research):
python scripts/cap020_regime_validation.py --cost-bps 10 --out research/cap020/
# → prints the robustness surface + OOS verdict; writes the evidence package JSON + result doc.
# unit tests (offline):
uv run pytest tests/scripts/test_cap020_regime_validation.py -q
```
Load-bearing assertion: the OOS, cost-net ΔMaxDD and ΔCalmar (vs eqw-overlay-OFF) with their bootstrap CIs, evaluated against §4 → a single decision-matrix outcome.

## 7. Risk matrix

| Risk | Impact | Mitigation |
|---|---|---|
| Overlay benefit is a single-window artifact | Medium | IS/OOS + walk-forward; OOS is the bar |
| Curve-fit to (200d, 0.5) | Medium | Parameter sweep; require a plateau, not a spike |
| Turnover cost erases the benefit | Medium | Explicit cost sweep; bar evaluated net of cost |
| ΔSharpe/ΔCalmar CI spans zero (as today) | High (→ not Validated) | Honest verdict via the decision matrix; Conditionally Promising/Rejected are valid outcomes |
| Look-ahead in the regime signal | High (invalidates study) | `.shift(1)` on the SMA gate (Phase 4 precedent), unit-tested |
| **Regime frequency changes over time** (overlays behave differently in prolonged bull vs volatile-sideways markets) | Medium | Evaluate across sub-periods **and** distinct market environments (2020 crash, 2022 bear, 2023-24 bull); report per-environment, not just pooled |
| Sector arm data still absent on box | Low | Document as a scoped exclusion (Phase 4 already skipped it) |

## 8. What this session does NOT do
- Does **not** activate CAP-020 on a live/paper book — Validated only makes it *eligible* (then paper observation per ADR-0022 §7).
- Does **not** touch the live ADR-0020/0022 vol-target overlay (a different mechanism).
- Does **not** re-optimize the factor books or change their weights (eqw is the FI-001 recipe).
- Does **not** add an ADR (this is validation of an existing research finding, not a new architectural decision) — unless the verdict is Validated *and* the owner wants to codify the overlay as a governed capability, which would be a follow-on.
- Does **not** build a new paper account or strategy template.
- Does **not** test alternative regime proxies this pass (owner review #3) — the study stays focused on the FI-001 rule (market proxy vs its SMA). But the harness is written **proxy-agnostic** (the proxy series is an input), so a *future* study can distinguish "the overlay **concept**" from "one **implementation**" by swapping in an **equal-weight index**, a **global-equity index**, or a **multi-asset risk index** — noted as the natural follow-on if this pass validates.

## 9. Notes & gotchas
1. **Two overlays, do not conflate.** CAP-020 = the discrete 200d-SMA gross rule (FI-001 Phase 4). The live overlay = ADR-0020 continuous vol-target (+ADR-0022 breadth/VIX). They are different studies with different code and different acceptance history.
2. **Benchmark is eqw-overlay-OFF, not momentum.** Phase 4 compared to both; the *validation* bar is vs the equal-weight book with the overlay off — the overlay must add value over the book it modifies.
3. **Honest-null discipline.** A ΔSharpe CI spanning zero is the current state; the study may well land *Conditionally Promising* (drawdown improves, guardrails/CI don't fully clear). That is a legitimate, valuable outcome — not a failure of the session. RNG-001 is the precedent (evidenced rejection is a deliverable).
4. **Reuse Phase 4, don't rebuild.** Import the book construction + bootstrap from `fi001_phase4_adaptive.py`; the new script adds parameterization, cost, IS/OOS, and the sweep.
5. **Registry vocab mismatch.** The doc matrix uses free-text labels ("Conditionally Promising"); the `programs.py` enum does not have that value — map it to `inconclusive` in code, keep the richer label in the doc matrix.
6. **"Material" thresholds in §4 = the economic-significance floor.** Owner-reviewed; they are the operational bar (a statistically-significant-but-tiny improvement is *Conditionally Promising*, not Validated). Locked for this pass to avoid re-litigating the verdict after the numbers are in.
7. **Statistical power is bounded (2019–2026).** Few full cycles / bear episodes → the overlay's decisive events are low-n. Verdict language says "validated over 2019–2026"; CAP-021 (Continuous Evidence Engine) accrues the rest out-of-window. This is *why* Validated → paper-eligible, not straight-to-live.
8. **Harness is proxy-agnostic by construction.** The regime proxy is an input series, so the alternative-proxy follow-on (eqw index / global equity / multi-asset risk) needs no re-architecture — it separates the overlay *concept* from this one *implementation*.
9. **Acceptance criteria are a hierarchy, not a flat list.** Primary decision rule = **Calmar** (net cost, OOS, CI≠0, economically material); MaxDD reduction is the required corroborant; Sharpe/CAGR are do-no-harm guardrails; robustness (≥2/3 grid) + sub-period consistency are trust checks. If metrics conflict, Calmar decides — subject to the guardrails not being breached.
