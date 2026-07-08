# EAD Dataset Triage — required gate before any new alt-data / event program (v0.2)

**Date:** 2026-07-07 · **Owner:** Jay Wang · **Status:** Active governance artifact.
**v0.2 (owner fold):** four **hard** gates now (PIT clarity · distinct mechanism · license path · ≥100 sample), not two — any one fails → no full study. The reference-use rule is a **codified EAD invariant** (enforced in code), not a recommendation.
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
| 3 | **License path** | *Can we legally run the study for the intended internal/research use?* A license path exists for that use — available now, or a clearly-justified upgrade. A study you cannot legally run is a dead-end eval. | **HARD VETO** |
| 4 | **Sample size** | Can plausibly reach **≥100 benchmarked** events/signals *after* PIT + materiality + universe filters. Below this the gate cannot hold the line. | **HARD — no full study** |
| 5 | Identity resolution | Maps cleanly to tradable securities (Security-Master resolvable). | Soft |
| 6 | Reusable harness | Fits an existing harness (event-study **or** cross-sectional signal), or the new harness is itself justified. | Soft |
| 7 | Commercial path | *If it works, can this become product/customer-facing later?* The license supports future product use, not only the internal study. Distinct from Gate 3: License path asks "may we **run the study**?"; Commercial path asks "may we **ship the result**?" | Soft |

### Decision rule

1. **Four hard gates — any one fails → do not run a full study:**
   - **PIT clarity** — no trustworthy observable availability date → No-Go (you cannot separate alpha from lookahead; LOBBY dropped 35% of filings on this gate).
   - **Distinct mechanism** — another beta / sector / size / public-disclosure-event proxy → No-Go *on prior* (the four rejections are one finding; a fifth of the same class fails before any data is pulled).
   - **License path** — no license path for the intended use → No-Go (a study you can't act on is a dead-end eval).
   - **Sample size** — cannot plausibly reach ≥100 benchmarked observations after filters → No full study (below it the gate cannot hold the line).
2. All four hard gates pass, but **two or more soft gates** (identity resolution, reusable harness, commercial path) fail → triage note / reference use only, no full study.
3. All gates pass → pre-register and run, with an explicit primary hypothesis and the gates recorded.

Of the four, **distinct mechanism** is the sharpest given the prior: when in doubt whether a dataset is "just another disclosure-event proxy," treat it as a veto.

### Triage outcomes (record one on every sheet)

Every triage resolves to exactly one of five statuses — a fixed vocabulary so future reviews are fast and comparable:

| Outcome | Meaning | Next action |
|---|---|---|
| **Go** | All gates pass. | Pre-register and run the full study. |
| **No-Go** | A hard gate fails (or the mechanism prior vetoes it). | Do not study. Record the failing gate. |
| **Reference-only** | Passes the hard gates but ≥2 soft gates fail, *or* it is a rejected dataset. | Ingest/display as context only — never ranking, sizing, or the order path (`rejected_reference_only`). |
| **Reserved** | A plausible idea with no current counter-hypothesis or capability. | Record the idea and its trigger; take no action until the trigger fires. |
| **Needs new harness** | Passes on mechanism/prior but requires a research capability the platform does not yet have (e.g. a cross-sectional signal harness). | Defer until the harness exists; do not force it into an existing framework. |

Reserved and Needs-new-harness are *not* No-Go — they are parked, not rejected. OFX-001 is the canonical Needs-new-harness case; LOBBY-002 is Reserved.

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
Outcome (Go / No-Go / Reference-only / Reserved / Needs-new-harness) (+ which gates, if any, it fails):
```

Commit the filled sheet alongside the program's pre-registration. No sheet → no study.

---

## Rejected ≠ deleted — the reference-use policy

A Rejected dataset is **not** discarded. It may be used as: reference/context data, event labels in a research dashboard, explanatory metadata, risk/context annotations, whitepaper evidence, negative-evidence memory, or a future *control* variable.

It may **not** be used to size positions, select or rank securities, or trigger trades — unless a *new* pre-registered hypothesis later proves value.

- **Allowed:** "Company had a lobbying-spend spike, but LOBBY-001 found no positive residual alpha."
- **Not allowed:** "Buy because lobbying spend spiked."

**This is a codified EAD invariant, not just policy (owner, 2026-07-07):**

> **A rejected EAD pattern may be displayed as reference/context, but it may not enter ranking, sizing, or order-path logic.**

Enforced in code via a `rejected_reference_only` tag: any rejected event-label that surfaces in the Opportunity Report or a signal feed carries it, and the ranking / sizing / order path must refuse to consume tagged labels. This joins the platform's other enforced-in-code invariants (single OrderRouter, no-LLM-in-order-path) — policies erode; enforcement doesn't, so "buy because X spiked" cannot creep back in. (Guardrail implementation tracked as the EAD-invariant work item.)

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
