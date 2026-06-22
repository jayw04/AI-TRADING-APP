# 📋 Docs awaiting your review

This folder holds **copies** of documents that need Jay's review/decision, so they're easy to find in
one place. The **originals** live in `docs/implementation/` (the source of truth, tracked + in PRs);
these are convenience copies. When a doc is reviewed + merged, it's removed from here.

> Claude drops a copy here whenever a doc needs a decision, and updates this index.

---

## Awaiting review

| Document | What it is | Decision needed |
|---|---|---|
| **`Whitepaper_v0.16_Implementation_Review.md`** | My fact-check of the v0.16 whitepaper against the actual implementation. **v2 (in progress):** folding your review feedback — add a **Product Positioning Review** section (momentum app → general-purpose Evidence Engineering platform; Momentum as *reference implementation*, not the product), the **"TradingWorkbench is not a trading strategy…"** opening sentence, and the **6-family patent roadmap**. | Once updated, tell me which edits to apply to the whitepaper `.docx` (I provide exact replacement text per section — I can't edit the binary). |

## Recently reviewed

| Document | Outcome |
|---|---|
| `SEC-001` **V2** Pure Sector Baskets plan | ✅ **Approved 2026-06-21 ("one of the best research plans you've produced") + 4 suggestions → v0.2** (Why-V2, stopping rule, commercial-value table, no-overfit clause). Q1–Q3 → recommendations (K=3 · H3 read · all-sector-baskets primary). **Building `scripts/sector_rotation_v2_research.py` + the run now.** |
| `SEC-001` **V1** Sector Rotation Research plan | ✅ **Approved (9.6/10) + 10 suggestions → v0.2** (PR #214). Run complete → **verdict B (Diversifier)**, PR #215 merged. V2 is the follow-up. |

---

## How to use

- Open the doc here, read it, and reply in chat with your decision (or edit the doc / drop notes in
  `Docs/implementation/comments.md` as you've been doing).
- Recommendations are marked in each doc; "go with your recommendations" is always a valid answer.
- Once you decide and the work merges, the entry leaves this table and the copy is cleared.

_Last updated: 2026-06-21 (SEC-001 V2 plan added)._
