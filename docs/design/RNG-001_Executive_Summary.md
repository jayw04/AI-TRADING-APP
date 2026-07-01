# RNG-001 — Executive Summary (one page)

*Companion to the full technical report `Range_BuySell_Formula_Study.md`. Every completed research
program produces both: a Technical Report and this one-page summary for stakeholders.*

| Field | Value |
|---|---|
| **Program** | RNG-001 — Range Trader (long-only opening-range fade) |
| **Question** | Does the opening-range fade have a tradable edge? |
| **Answer** | **No** (on the tested universes, regimes, and implementation variants) |
| **Confidence** | **High** — fails across three independent dimensions |
| **Window** | 2023-07 → 2026-06 (3 years), clean 5-min data, disarmed backtests |
| **Reason** | Entry mode is second-order (PF 0.84–0.91, all fail the gate); loses in every regime (best bucket = range, PF 0.94, still losing); loses on both tested universe families (momentum names *trend*; defensive reverters are *too quiet* to clear costs) |
| **Data caveat** | Initial results were biased by a bar-cache truncation bug; documented in an Evidence Correction Report, corrected, re-run — verdict held and hardened (→ ADR-0033) |
| **Reusable assets** | **7** — Opportunity Funnel, data-integrity/cache-repair tool + ADR-0033, Evidence Correction Report pattern, MAE/MFE instrumentation, Regime Classifier, entry-mode harness, universe-screen harness |
| **Recommendation** | **Archive.** RNG-001 Completed · Rejected · Archived. Stays live on paper as the rejected-benchmark sleeve (default config). Reopening requires a *new hypothesis* (different mechanic/instrument), not another parameter sweep. |

**Value delivered:** the platform **prevented deployment of an unprofitable strategy** — before capital,
live-trading risk, or months of Phase-2/4/5 build-out — and left behind seven reusable capabilities. A
rejected strategy; a successful program.

## Promotion-gate scorecard (best variant, momentum universe)

| Gate | Threshold | Result | Pass? |
|---|---|---|---|
| Trades | > 100 | 1,843–3,302 | ✅ |
| Profit Factor | > 1.2 | 0.84–0.91 | ❌ |
| Win Rate | > 50% | 27–48% | ❌ |
| Expectancy | Positive | Negative | ❌ |
| Max Drawdown | ≤ baseline | n/a (rejected on PF/win/expectancy) | — |

Gate fails on Profit Factor, Win Rate, and Expectancy across all variants → **Rejected**.
