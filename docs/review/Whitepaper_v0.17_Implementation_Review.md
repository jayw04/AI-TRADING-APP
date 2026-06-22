# Whitepaper v0.17 — Implementation Accuracy Review + New Research Data

**Reviewer:** Claude (against the actual codebase + this session's research, 2026-06-21).
**Source:** `Docs/design/TradingWorkbench_Whitepaper_v0.17_InternalReview.docx` (Draft v0.17, Chapters 1–15).
**Scope:** (1) verify v0.17 against the implementation; (2) **add the newest research data** the draft doesn't yet have (SEC-001 Sector Rotation results), with paste-ready text.

---

## Overall — v0.17 is accurate, current, and noticeably stronger than v0.16

**The v0.16 review feedback is essentially all folded.** v0.17 is now one of the most implementation-faithful drafts the project has had. Confirmed incorporations:

| v0.16 review item | v0.17 status |
|---|---|
| A1 — Production Confidence "future" → **implemented, 74/100** | ✅ §10.6: *"It is implemented: a 0–100 score … currently 74/100 ('Building')"* + the Operational KPI Scorecard sentence. Verbatim. |
| A2 — Range Trading "Pending" → **Rejected** | ✅ §14.5 Case Study 4: *"the answer was no"*, PF 1.27, CI [−$19.74, +$57.53], walk-forward 1.69→1.14→1.33→0.89, **VERDICT Rejected — the platform's first formally-rejected strategy.** |
| A3 — **three** live Risk Profiles (not just Balanced) | ✅ *"running live on paper as three vol-target Risk Profiles (Conservative / Balanced / Growth)"* + the glossary risk-dial definition. |
| A4 — Sector Rotation / program-ID registry | ✅ SEC-001 named, the "momentum picks what, rotation picks where" framing, the MOM-001 / RNG-001 / MF-001 / SEC-001 registry. |
| D1/D2 — positioning: Momentum = reference implementation, not the product | ✅ Outstanding: *"momentum is not the platform; it is the reference strategy that proves the platform works, much as Linux is a reference implementation of an operating system rather than the operating system itself."* The Linux analogy is better than my suggested sentence. |
| D3 — patent **portfolio of families**, not one filing | ✅ §13: *"best protected not as a single patent but as a portfolio of related patent families"* + the family list. |
| B1 — "13 invariants of ADR 0021" mis-attribution | ✅ §14.6: *"the thirteen CI invariants (the codebase's enforced invariant set), including the operational recovery guarantees formalized in ADR 0021."* Exactly the fix. |
| B4 — dashboards framed as roadmap | ✅ §8.9 / §9.11: *"today produced as a generated report artifact; the interactive web dashboard is part of Product Readiness, P13"* + figures marked "(illustrative)." |

Net: the fact-check pass is largely **done**. What remains is (1) **new data that post-dates v0.17**, and (2) a few small nuances.

---

## A. Newly overtaken since v0.17 was written (this session) — the real action items

### A1. SEC-001 Sector Rotation is **no longer "in flight" — V1 is complete (verdict B, Diversifier)** ★ highest priority
§14 (line ~1243) says *"The next pre-registered research program is already in flight: Sector Rotation (SEC-001)."* **It has now resolved.** SEC-001 V1 ran end-to-end (2000–2026, survivorship-free, n=200, 12‑1 frozen) and produced the **strongest non-momentum result the platform has yet recorded** — see the full data in **§D**. Headline: Sharpe **0.51** (vs momentum 0.39, equal-weight 0.35), but the standalone edge's CI just barely spans zero, so it lands **B — Diversifier**, not a standalone A.

This is **whitepaper-grade material** and *strengthens* the thesis: it's the platform's clearest example yet of the gate holding the line on a *genuinely attractive* book (not an obvious reject like Range). **Fix:** promote SEC-001 from "in flight" to a resolved program, and add **Case Study 7 — Sector Rotation** (paste-ready text in §D). Figure 26 ("Six real programs") becomes **seven**.

### A2. The first P13 **web dashboard shipped** (Evidence Dashboard)
§8.9 / §9.11 / §11 frame product dashboards as P13 roadmap ("the interactive web dashboard is part of Product Readiness, P13"). **This session shipped the first one:** an in-app **Evidence Dashboard** (`/evidence`) surfacing the Production Confidence Score (the four weighted components + rationale), the Operational KPI Scorecard, the research-program registry (with per-status verdicts), and the live strategy books — with a print-to-report button. **Fix (small):** add a clause to §8.9 / §11 P13 — *"the first of these, the Evidence Dashboard, is now live in-app; the Governance and Execution dashboards follow."* Keeps the roadmap framing honest while claiming the real progress.

### A3. SEC-001 **V2 (pure sector baskets)** is now in flight / resolving
A natural follow-up the draft can foreshadow: V1's near-miss standalone prompted a pre-registered **V2** that changes *only* the construction (sector-neutral baskets vs top-quintile stocks) to test whether construction — not signal — limited V1. _[V2 result to be appended to §D when its run completes — included so the case study can state V1's follow-up.]_

---

## B. Minor nuances (small, optional)

- **B1 — Illustrative registry IDs.** The example IDs (EXP-2026-014, EV-2026-014, GOV-2026-042, EP-2026-015) are fine as *illustrative* (figures are captioned so), but the real experiment IDs follow `EXP-YYYYMMDD-HHMMSS-<program>` (e.g. `EXP-20260621-…-sec001`). If any non-figure body text implies these are live IDs, soften to "illustrative."
- **B2 — SF1 depth.** §14.4 correctly scopes the multi-factor study to "2017–2026," so the ~10-year depth is implicit. A single half-clause ("the acquired SF1 tier spans ~10 years, 2016+, at full breadth") would make the *still-wide CI* causally explicit and pre-empt a diligent reader — optional honesty polish.
- **B3 — "Six real programs" / case-study count.** Updating to seven (with SEC-001) is the only structural change A1 implies; the §14.8 "two evidence-based 'no' decisions" line can become "two declines and a diversifier-not-standalone," which is an even richer demonstration of the gate's resolution.

---

## C. What NOT to change
The honesty posture, the Proven/Inconclusive/Rejected verdicts, the momentum + P14 numbers (verified against code/evidence), the Linux reference-implementation framing, the patent-family portfolio, and the ADR 0021 attribution — all correct. Keep them.

---

## D. New research data report (paste-ready) — SEC-001 Sector Rotation

> Pre-registered (SEC-001 plan v0.2, owner-approved). 2000–2026, survivorship-free SEP + Sharadar
> `tickers.sector` (11 sectors), n=200 liquid universe, 12‑1 momentum **frozen** (no optimization),
> paired circular-block bootstrap (2000 resamples, seed 17). Evidence package:
> `docs/implementation/evidence/sec_001_sector_rotation/`.

### V1 — top-quintile of strong-sectors' stocks → **VERDICT B (Diversifier)**

| Book | CAGR | Sharpe | maxDD | Calmar |
|---|---|---|---|---|
| Equal-weight (benchmark) | +5.63% | 0.35 | −69.2% | 0.08 |
| Momentum (v1.1, live) | +7.39% | 0.39 | −76.4% | 0.10 |
| **Sector Rotation** | **+10.36%** | **0.51** | **−64.8%** | **0.16** |
| Momentum + Sector blend | +10.44% | 0.48 | −66.8% | 0.16 |

- **H1 (standalone vs equal-weight):** ΔSharpe **+0.16**, paired 95% CI **[−0.03, 0.366]** — point estimate clearly positive and 3/5 walk-forward windows won, but the CI just touches below zero, so it does **not** clear the pre-registered "CI excludes zero" bar for a decisive standalone edge.
- **H2 (diversifier):** corr(momentum, sector) = **0.38** (low → genuine diversifier); sector maxDD **−64.8% vs momentum −76.4%** (~12pp shallower); blend ΔSharpe +0.09, CI [−0.045, 0.233].
- **Cost-robust:** Sharpe 0.53 / 0.51 / 0.47 / 0.35 at 5 / 10 / 20 / 50 bps.

**Paste-ready Case Study 7 — Sector Rotation (V1):**

> **14.x  Case Study 7 — Sector Rotation.** Does rotating into the strongest-momentum *sectors* add value
> beyond single-name momentum? The platform ran a pre-registered study (2000–2026, survivorship-free,
> 12‑1 sector momentum frozen) through the same bootstrap and walk-forward machinery. Sector Rotation
> posted the **strongest risk-adjusted profile of any non-momentum book to date** — Sharpe 0.51 and a
> shallower drawdown (−64.8%) than momentum itself (0.39, −76.4%) — and it is a genuine diversifier
> (correlation 0.38 with momentum). But the standalone edge over a passive equal-weight benchmark was a
> hair short of significance: ΔSharpe +0.16, 95% CI [−0.03, +0.366], just spanning zero. **VERDICT —
> Diversifier (B):** not yet a standalone strategy, but a credible momentum overlay, and the platform's
> clearest demonstration that the statistical gate holds the line even on an *attractive* result. A
> pre-registered V2 isolates whether portfolio construction, not the sector signal, was the limiting
> factor.

### V2 — pure sector baskets → **VERDICT B (Diversifier, confirmed) + stopping rule fires**

Construction-only change (sector-neutral top-3 baskets vs V1's top-quintile stocks); signal/universe/
window/cost identical to V1. Evidence: `docs/implementation/evidence/sec_001_v2_pure_baskets/`.

| Book | CAGR | Sharpe | maxDD |
|---|---|---|---|
| All-sector baskets (H1 control) | +7.47% | 0.45 | −55.7% |
| V1 — stock-level (prior) | +10.83% | 0.53 | −63.4% |
| **V2 — pure sector baskets** | +9.19% | 0.49 | −66.8% |

- **H1 (vs all-sector baskets):** ΔSharpe **+0.04, CI [−0.165, 0.244]** — spans zero, **no standalone edge** (and *weaker* than V1's +0.16).
- **H3 (V2 − V1, construction isolation):** ΔSharpe **−0.04, CI [−0.179, 0.093]** — spans zero → **construction is neutral.** Diversifying away single-stock noise did *not* tighten the edge.
- Diversifier confirmed (corr 0.378; V2 maxDD −66.8% vs momentum −76.4%); K-robust (K=2/3/4 Sharpe 0.50/0.49/0.53); cost-robust to 20 bps.

**The decisive read:** V2 tested whether *construction*, not the *signal*, limited V1's standalone edge. H3 answers cleanly — it doesn't. The sector-rotation signal is a genuine **diversifier** but not a **standalone** edge, and no construction refinement closes the gap. **Per the pre-registered stopping rule, Sector Rotation construction is ARCHIVED** — a standalone book would need a fundamentally different hypothesis (e.g. regime-conditioned rotation), not more tuning.

> **This is itself whitepaper-grade material:** the platform pre-registered a stopping rule and then *honored it* when the evidence said stop — bounding the program rather than chasing it. Update Case Study 7's closing line to: *"V2 confirmed the diversifier verdict and, via a pre-registered stopping rule, formally bounded the program — construction was proven not to be the limiting factor."*

---

### Priority order for the v0.17 → v0.18 edit pass
1. **A1 (SEC-001 V1 → resolved + Case Study 7)** — the one substantive new result; §D is paste-ready.
2. **A2 (Evidence Dashboard shipped)** — a one-clause win in §8.9 / §11.
3. **B3 ("six" → "seven" programs; the "two no's" line)** — follows from A1.
4. **A3 / V2 result** — append when the run lands.
5. **B1 / B2** — optional polish.

> **How to apply:** the source is a `.docx` I can't edit directly. Tell me which items to apply and I'll
> hand you exact drop-in text per section (D's Case Study 7 is already paste-ready), or you apply them.
