# RNG-001 — Executive Summary

*One-page stakeholder artifact. Every completed research program emits two outputs: a full technical
report and this one-page summary. Companion to the full report (`Range_BuySell_Formula_Study.md`) and the
whitepaper case study (`RNG-001_Case_Study_for_Whitepaper.md`). Program concluded 2026-06-30.*

---

| Field | Value |
|---|---|
| **Program** | RNG-001 — Range Trader (long-only opening-range fade) |
| **Question** | Does the opening-range fade have a tradable edge? |
| **Answer** | **No** — on the tested universes, regimes, and implementation variants. |
| **Confidence** | **High** — fails across three independent dimensions. |
| **Reason** | Entry mode is second-order (all five variants PF 0.84–0.91, none pass the gate); loses in every market regime (best bucket — range days — PF 0.94); loses on both universe families (momentum names *move but trend*, so the fade fights the trend; mean-reverting names *revert but do not move*, too quiet to clear costs). No sweet spot between them. |
| **Data caveat** | Early results were biased by a bar-cache truncation defect; **disclosed** via an Evidence Correction Report, corrected (data rebuilt), and every experiment re-run — the verdict held and hardened. The defect was escalated to **ADR-0033 (Historical Data Integrity, Foundational)**. |
| **Reusable assets** | **7** — Opportunity Funnel · MAE/MFE trade instrumentation · regime classifier + segmentation harness · entry-comparison harness · universe-screening harness · data-integrity checker + cache-repair tool · the Evidence Correction Report pattern (→ ADR-0033). |
| **Recommendation** | **Archive.** Status: Completed · Rejected. The research program is closed — reopening requires a genuinely new hypothesis (a different mechanic or instrument class), not another parameter sweep. The Range book **remains live on paper as the verdict-distinct rejected-benchmark sleeve**, which also proves the execution/operations layer behaves correctly every session. |

---

**Research Cost Saved.** Framed for a stakeholder, the outcome is not "a strategy was rejected." It is that
the platform **prevented the deployment of an unprofitable strategy before any capital, live-trading risk,
or months of further build-out were spent** — and left behind seven reusable capabilities that accelerate
every future program. One strategy did not survive; seven capabilities did.

**The takeaway.** TradingWorkbench reduces *false positives*. It caught a convincing but unprofitable
strategy on paper, with a transparent and reproducible evidence trail, before a dollar was put at risk.
That the platform detected and disclosed a fault in its own data pipeline along the way — rather than
quietly re-running the numbers — is one of the strongest trust signals it can produce.
