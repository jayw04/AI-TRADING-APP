# 📋 Docs awaiting your review

This folder holds **copies** of documents that need Jay's review/decision, so they're easy to find in
one place. The **originals** live in `docs/implementation/` (the source of truth, tracked + in PRs);
these are convenience copies. When a doc is reviewed + merged, it's removed from here.

> Claude drops a copy here whenever a doc needs a decision, and updates this index.

---

## Awaiting review

| Document | What it is | Decision needed |
|---|---|---|
| **`Whitepaper_v0.17_Implementation_Review.md`** | Review of the **new v0.17** draft. Good news: v0.17 **folded essentially all the v0.16 feedback** (Production Confidence implemented, Range rejected, three live profiles, Linux reference-implementation framing, patent-family portfolio, ADR 0021 fix). What's left is **new data v0.17 predates**: **§D has the paste-ready SEC-001 Sector Rotation results + a Case Study 7** (V1 = Diversifier B, the strongest non-momentum book yet), the Evidence Dashboard shipped, and a slot for the V2 result. | Tell me **which items** to apply to the v0.17 `.docx` — §D's Case Study 7 is paste-ready. The v0.16 review (below) is now superseded by this. |
| `Whitepaper_v0.16_Implementation_Review.md` | **Superseded by the v0.17 review above** — v0.17 incorporated its fact-checks + positioning §D. Kept for history. | None — folded. |

## Recently reviewed

| Document | Outcome |
|---|---|
| `Whitepaper Ch2 drop-in v0.2` (architecture) | ✅ **Reviewed 2026-06-27 (9.9/10, `docs/design/review-comments.md`)** — "approaching publication quality." Folded into **`Docs/design/Whitepaper_Ch2_DropIn_Architecture_v0.3.md`**: Principle Zero box + closing summary, Registry = "single source of truth", Platform *contains* Infrastructure *produces* Programs, L4 Production-**Qualified**, Deployment Policy (Envelope→Confidence→Position Size), Figure 2.2 input "Candidate Universe"→"Research Universe", Assignment determinism sentence, broader-Discovery note, terminology-consistency callout. |
| `ADR 0029` — Opportunity Registry & engine separation | ✅ **Reviewed 2026-06-27 (9.8/10, `docs/adr/ADR-Review.md`)** — "approve as proposed." Refinements folded into the ADR: **acceptance gated on Monday's first auto-select run** (promote Proposed→Accepted only after the live workflow proves it), **Opportunity Set ID** `OPP-RANGE-20260629-001`, **Registry↔audit reconciliation invariant**, composite-ranking examples marked illustrative-not-frozen, session-immutability restated, and a recommended implementation order (Monday trial → Accept → Phase 1 read-model → weekly calibration → only then Phase 2 code split). |
| `RangeStrategy_Implementation_Review_v1.1` (pre-Monday overview) | ✅ **Reviewed 2026-06-27 (9.95/10)** — judged "ready for Monday's trial; no further architectural changes before it." Six doc refinements folded into **`RangeStrategy_Implementation_Review_v1.2`** (Research Status table · Opportunity Set ID · structural-vs-research params · composite-ranking example %s removed · dashboard linkage · whitepaper-after-Monday). Registry persistence kept deferred per owner; **Post-Run Report** planned for after week 1. |
| `RangeStrategy_Implementation_Review_v1.0` (pre-Monday overview) | ✅ **Reviewed 2026-06-27 (9.8/10)** — headline rec "separate qualification, ranking, opportunity assignment + add an Opportunity Registry" → **ADR 0029** (Proposed). Refinements folded into **v1.1** (evidence-weighted · Opportunity Set term · unused-budget-stays-cash · runbook outcome table · composite ranking for NVDA staleness · rolling weekly calibration · Selection Precision + Opportunity Conversion metrics). Whitepaper Ch2 drop-in bumped to **v0.2** (Opportunity Registry + three engines). |
| `LOW-001` Low Volatility plan | ✅ **Approved 2026-06-21 (9.7/10) + suggestions → v0.2** (momentum relationship · Low-Vol vs Vol-Target · expected-behavior table · outcome probabilities + learning objective · research cost · phase terminology). Q1–Q3 → recommendations (LOW-001 rename · top-200 first · realized vol). **Built + full 2000–2026 run in progress.** Also: Research Program Registry doc created. |
| `SEC-001` **V2** Pure Sector Baskets | ✅ **Approved → built → run complete → verdict B (Diversifier, confirmed); stopping rule fired → construction ARCHIVED** (H1 +0.04 CI spans zero, H3 V2≈V1 → construction not the limiter). Full evidence + harness merged in **PR #216**. |
| `SEC-001` **V1** Sector Rotation Research plan | ✅ **Approved (9.6/10) + 10 suggestions → v0.2** (PR #214). Run complete → **verdict B (Diversifier)**, PR #215 merged. V2 is the follow-up. |

---

## How to use

- Open the doc here, read it, and reply in chat with your decision (or edit the doc / drop notes in
  `Docs/implementation/comments.md` as you've been doing).
- Recommendations are marked in each doc; "go with your recommendations" is always a valid answer.
- Once you decide and the work merges, the entry leaves this table and the copy is cleared.

_Last updated: 2026-06-27 (Range implementation review folded → v1.1 + ADR 0029 + Whitepaper Ch2 v0.2)._
