# EAD Dataset Triage — required gate before any new alt-data / event program (v0.1)

**Date:** 2026-07-07 · **Owner:** Jay Wang · **Status:** Active governance artifact.
**Why this exists:** after four matched-control rejections of Quiver event datasets, "test every dataset" is no longer a good use of research. This one-page gate makes alt-data exploration **hypothesis-driven, not dataset-by-dataset**. Fold of the owner's LOBBY-001 review (`docs/implementation/comments.md`, Step 2).

---

## The prior these results established (read first)

INSIDER-001, GOVCONTRACT-001, CONGRESS-001, and LOBBY-001 all **cleared the ≥100-benchmarked-event sample gate and were still Rejected** — no positive residual alpha after sector / size / liquidity / momentum matching. These are not four independent findings. They are **one finding**:

> **Public corporate-disclosure events do not carry residual alpha once matched to comparable non-event peers.**

Consequences for triage:
- A new dataset in the **same mechanism class** (a public, scheduled corporate-disclosure event → short-horizon drift) is a **low-prior repeat**, not a new bet. It should fail triage on *mechanism*, before any data is pulled.
- The framework itself is **validated** — it correctly and repeatedly rejects plausible-but-hollow signals. That is the platform's False-Positive-Reduction thesis working, and it is the flagship whitepaper story. The value already delivered is the *evidence that the discipline works*, not a trade.

---

## The gates

Score every candidate dataset against all gates **before** committing to a full study.

| # | Gate | Requirement | Type |
|---|---|---|---|
| 1 | **PIT clarity** | A trustworthy, observable availability date (when the signal was *knowably* public). | **HARD VETO** |
| 2 | **Distinct mechanism** | Not another beta / sector / size / public-disclosure-event proxy. A genuinely different economic channel. | **HARD VETO** |
| 3 | License | Available under the current subscription, or the paid upgrade is clearly justified by a *proven* prior. | Soft |
| 4 | Identity resolution | Maps cleanly to tradable securities (Security-Master resolvable). | Soft |
| 5 | Sample size | Likely **≥100 benchmarked** events/signals *after* PIT + materiality + universe filters. | Soft |
| 6 | Reusable harness | Fits an existing harness (event-study **or** cross-sectional signal), or the new harness is itself justified. | Soft |
| 7 | Commercial path | If it proves out, the license supports future product use (not a dead-end eval). | Soft |

### Decision rule

1. **Any HARD VETO fails → No-Go.** No study. (Rationale: without PIT you cannot separate alpha from lookahead — LOBBY dropped 35% of filings on this gate; without a distinct mechanism the prior already says "no.")
2. Otherwise, **fail two or more soft gates → No full study** (triage note / reference use only).
3. Otherwise → pre-register and run, with an explicit primary hypothesis and the gates recorded.

Gate 2 (distinct mechanism) is the **most weighted** soft-or-hard consideration given the prior above: when in doubt about whether a dataset is "just another disclosure-event proxy," treat it as a veto.

---

## The one-page triage (fill in and commit before any study)

```
Dataset:
Mechanism (economic channel; why it would NOT be another disclosure-event proxy):
PIT anchor (the observable availability date; how it's derived):
License (owned / upgrade-needed / cost):
Expected sample (benchmarked events after filters):
Identity mapping (Security-Master coverage):
Harness type (event-study / cross-sectional signal / new):
Prior (is this the same mechanism class as the 4 rejections? strength of the counter-prior):
Go / No-Go (+ which gates, if any, it fails):
```

Commit the filled sheet alongside the program's pre-registration. No sheet → no study.

---

## Rejected ≠ deleted — the reference-use policy

A Rejected dataset is **not** discarded. It may be used as: reference/context data, event labels in a research dashboard, explanatory metadata, risk/context annotations, whitepaper evidence, negative-evidence memory, or a future *control* variable.

It may **not** be used to size positions, select or rank securities, or trigger trades — unless a *new* pre-registered hypothesis later proves value.

- **Allowed:** "Company had a lobbying-spend spike, but LOBBY-001 found no positive residual alpha."
- **Not allowed:** "Buy because lobbying spend spiked."

**Recommended code guardrail (not just policy):** any rejected event-label that surfaces in the Opportunity Report or a signal feed must carry a `rejected_reference_only` tag, and the sizing / ranking path must refuse to consume tagged labels. Policies erode; the platform's discipline is enforced in code (single router, no-LLM-in-order-path) — extend the same pattern here so "buy because X spiked" cannot creep back in.

---

## Current dataset dispositions (2026-07-07)

| Dataset | Disposition |
|---|---|
| Lobbying (LOBBY-001) | **Done — Rejected.** Reference only. |
| Congress (CONGRESS-001) | **Done — Rejected.** Reference only. |
| Gov contracts (GOVCONTRACT-001) | **Done — Rejected.** Reference only. |
| Insider (INSIDER-001, SEC Form 4) | **Done — Rejected.** Reference only. |
| Flights | Too thin — do not pursue. |
| House / Senate subsets | Not new — covered by Congress. |
| WSB / insiders / 13F (locked) | **Do not upgrade** just to test. |
| Off-exchange / dark-pool | **Interesting, different harness — reserve as OFX-001 (below), not EAD.** |

### Reserved programs (do NOT start yet)

- **LOBBY-002 — New-Issue Lobbying Entry.** Reserved (a firm's *first* lobbying disclosure, a distinct event from a spend spike). Same mechanism class as LOBBY-001 → carries the low prior; start only if a specific counter-hypothesis justifies it.
- **OFX-001 — Off-Exchange / Dark-Pool Signal Study.** Reserved as a **cross-sectional signal program, NOT an event study** — it is a continuous daily panel (rank IC, decile/quantile portfolios, sector-neutral tests, turnover/cost model, walk-forward), so it needs a signal harness the platform does not yet have. **Before reserving Quiver spend for it, check whether FINRA's free off-exchange / short-volume feed suffices** — it may not need paid Quiver at all. Do not force it into the event-study framework.

---

## Upgrade policy

**Do not upgrade the Quiver subscription now.** Reconsider only when one is true: (a) a currently-available dataset produces a robust edge, (b) a locked dataset has a clearly *different* mechanism and a strong prior, (c) commercial rights are needed for a *proven* internal capability, or (d) the dataset supports a risk/context product use beyond trading alpha.

---

*The discipline: the goal is not to keep testing until something works. It is to stop when the evidence says the current data class is not producing value — and to make that a repeatable gate, not a judgment call.*
