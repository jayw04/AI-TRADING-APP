# Custody record — Strategy Lifecycle & Research Operating Model v1.0

This record lives **outside** the governed source file (its §23 item 2). It carries the acceptance
and custody facts for `Strategy_Lifecycle_and_Research_Operating_Model_v1_0.md` in this directory.
Documentation custody grants no operational authority (model §0.3, §20, §22).

| Field | Value |
|---|---|
| Governed file | `docs/design/Lifecycle/Strategy_Lifecycle_and_Research_Operating_Model_v1_0.md` (canonical path, model §0.3 / §23 item 1) |
| Owner acceptance | 2026-09-02 — "OWNER ACCEPTED / CONTENT APPROVED"; LD-1 … LD-8 accepted at the §19 values |
| Accepted source identity | owner-supplied `…_v1_0_OFFICIAL.md`, 61,990 bytes, LF, SHA-256 `f6b2f1219679a0081fa381d266bb6f28e8a444941ba157d9578dfadd6689d998` (**obsolete** after the repair below; recorded for lineage only) |
| **Custodied identity** | **61,993 bytes, LF, SHA-256 `4ee9b83d46d6ebc035657ac87d2a51c65584b31281f4e659cb6edcf230533391`** |
| Editorial repair ruling | 2026-09-02 — "ONE EDITORIAL REPAIR REQUIRED BEFORE MERGE": Appendix A was deliberately deleted at acceptance; the dangling references were to be cleaned; nothing else changes |
| Status after merge | GOVERNING / OWNER ACCEPTED / CANONICAL CUSTODY COMPLETE — the merge SHA is the squash commit of the custody PR on `main`; the file SHA-256 above is verifiable with `git show main:<path> \| sha256sum` |
| Authority position | below frozen registrations / sealed evidence / accepted ADRs / explicit owner rulings, and below ATP for current execution (model §0.1) |

## Editorial repair applied (the complete diff versus the accepted source)

Exact search for `Appendix A` after repair: **0 occurrences** (required by the ruling).

| # | Location | Accepted text | Custodied text | Why |
|---|---|---|---|---|
| 1 | §0.1, consequences, first bullet | "(v0.1 §17 contained several; they are relocated to Appendix A and marked accordingly)" | "(v0.1 §17 contained several; they were removed from the durable v1.0)" | dangling reference; disposition matches the R10 repair. Not named among the ruling's three items but required by its zero-reference rule |
| 2 | §0.2 | "… and in custody records. The one exception is Appendix A, which is explicitly a dated, non-governing snapshot that the owner may delete at acceptance without loss." | "… and in custody records." | ruling item 1 — the durable document simply contains no observation-dated facts |
| 3 | §21 row R4, "Change" column | "Identity register (§6.3); undefined terms flagged in Appendix A." | "Identity register (§6.3); any future use of Strategy 9, Mechanism-C, or similar deployed / program identifiers must cite the governing artifact that defines them." | ruling item 2 — referential rule; the model does not define those identifiers itself |
| 4 | §21 row R10, "Change" column | "… (§0.2); §17 moved to Appendix A as a dated non-governing snapshot with authority references and conflict flags." | "… (§0.2); the observation-dated §17 content was removed from the durable v1.0, with current-state facts remaining in ATP / custody." | ruling item 3 — actual final disposition of §17 |

Unchanged by this custody (verified by the diff being exactly the four hunks above): every LD value,
lifecycle state, verdict / disposition vocabulary, gate definition, authority rule, retirement
contract (§10.1), thesis-health rule, research invariant (§7), and the §20 non-authorisation list.
Word-conversion formatting artifacts (escaped punctuation, grid-style tables) are deliberately left
as accepted; cleanup, if ever, is a later patch version.

## What this custody does not do

§23 items 3–10 (ATP successor reference, lifecycle registry before dashboards, retirement control as a
REQUIRED ENABLER, census / trial-ledger support, observation protocols, conformance identity) remain
future ATP / enabler work admitted through ATP §1. Frozen research specifications are not modified
retroactively. No priority, lane, batch, account binding, activation, or order authority is created.
