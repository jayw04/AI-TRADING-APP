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
| `LOW-001` Low Volatility plan | ✅ **Approved 2026-06-21 (9.7/10) + suggestions → v0.2** (momentum relationship · Low-Vol vs Vol-Target · expected-behavior table · outcome probabilities + learning objective · research cost · phase terminology). Q1–Q3 → recommendations (LOW-001 rename · top-200 first · realized vol). **Built + full 2000–2026 run in progress.** Also: Research Program Registry doc created. |
| `SEC-001` **V2** Pure Sector Baskets | ✅ **Approved → built → run complete → verdict B (Diversifier, confirmed); stopping rule fired → construction ARCHIVED** (H1 +0.04 CI spans zero, H3 V2≈V1 → construction not the limiter). Full evidence + harness merged in **PR #216**. |
| `SEC-001` **V1** Sector Rotation Research plan | ✅ **Approved (9.6/10) + 10 suggestions → v0.2** (PR #214). Run complete → **verdict B (Diversifier)**, PR #215 merged. V2 is the follow-up. |

---

## How to use

- Open the doc here, read it, and reply in chat with your decision (or edit the doc / drop notes in
  `Docs/implementation/comments.md` as you've been doing).
- Recommendations are marked in each doc; "go with your recommendations" is always a valid answer.
- Once you decide and the work merges, the entry leaves this table and the copy is cleared.

_Last updated: 2026-06-21 (SEC-001 V2 plan added)._
