# Research Decision — MOM-001 Risk-Profile Consolidation

| Field | Value |
|---|---|
| Date | 2026-07-04 |
| Program | MOM-001 (Momentum) |
| Type | Research Decision (study concluded) — **positive evidence** |
| Governs | ADR 0036 (Canonical Strategy Representation) |
| Status | Decided (owner-directed 2026-07-04); executed on the paper lineup |

## Finding

The three live momentum books differ **only by volatility scaling**. They are the same strategy at
three risk settings, not three strategies.

| Book | Account | Vol target | Rebalance |
|---|---|---|---|
| `momentum-portfolio` (id 2) | user 1 | **Balanced 15%** | Mon 14:00 UTC |
| `momentum-conservative` (id 4) | user 3 | 10% | Mon 14:08 UTC |
| `momentum-growth` (id 5) | user 4 | 20% | Mon 14:16 UTC |

**Evidence they are one alpha:**
- **Correlation ≈ 1.00** and **holdings overlap ≈ 100%** — measured by the Portfolio Analytics Engine
  (CAP-021, PR #322).
- **Identical ranking engine, universe, rebalance schedule, and alpha source** — the only difference is
  the vol-target gross the overlay applies.
- **MOM-002** independently found that reshaping the *same* momentum factor (breadth, sector cap) does
  not create independent evidence (Top-5 ↔ Top-20 corr 0.90); **FI-001** confirmed diversification
  requires *distinct factors*, not re-scalings of one.

The research question these three books answered — *"does changing the volatility target materially
change the strategy's behavior?"* — is now **answered: no. Volatility targeting changes risk, not
alpha.** Continuing to operate three near-identical books adds negligible incremental evidence.

## This is positive evidence

This is not the correction of a mistake — it is a study reaching its conclusion. Provisioning the three
vol-variants in Phase 1 correctly answered a real question and proved operational reliability across
three books. Concluding the study and collapsing to one canonical book is the *mature* outcome.

Many quantitative shops present **Conservative / Balanced / Growth** as three independent strategies.
The honest statement — **they are one strategy with three risk settings** — increases the credibility of
the Evidence-Engineering methodology. The live deployment should reflect what the research demonstrated.

## Decision

1. **Maintain one canonical production implementation of MOM-001** — `momentum-portfolio` (user 1,
   **Balanced 15%** as the default preset). It remains the platform's single ✅ Approved standalone book.
2. **Risk profiles become configuration presets, not independent research programs.** The vol target is
   a selectable parameter of the canonical strategy (Conservative 10% / **Balanced 15% (default)** /
   Growth 20%) — like a fund's Conservative/Moderate/Aggressive allocations, without pretending they are
   different investment processes.
3. **Deactivate (do not delete) the two redundant books** — `momentum-conservative` (id 4) and
   `momentum-growth` (id 5) → status **IDLE**. Preserve their **equity curves, trade history,
   performance statistics, operational logs, and live metrics** as the completed-research record.
   Registry/record reason: *"Archived after research completion — consolidated into canonical MOM-001."*
4. **No liquidation this pass.** Deactivation stops future rebalances; existing positions are left frozen
   (no live-order burst near a rebalance window). Flattening the archived books to lock the final equity
   curve is an optional, separate follow-up.

## The resulting live lineup (verdict-distinct)

| Account | Program | Verdict / Role |
|---|---|---|
| user 1 | **MOM-001** Momentum | ✅ Approved / Canonical production strategy |
| user 6 | **LOW-001** Low Volatility | 🟡 Diversifier / Defensive sleeve |
| user 5 | **SEC-001** Sector Rotation | 🟡 Diversifier / Overlay sleeve |
| user 7 | **Combined Book** (PORT-001) | Portfolio construction |
| user 2 | **RNG-001** Range | 🔴 Rejected / Negative-control benchmark |
| user 3, user 4 | (archived momentum vol-variants) | Archived after research completion |

## Preserved (deactivate ≠ delete)

Retained for the archived books (users 3 & 4): equity curves, trade/order history, performance
statistics, operational logs, live metrics, and the strategy rows themselves (status IDLE). This is the
audit trail showing the risk-profile study ran, concluded, and was consolidated — not erased.

## References

- ADR 0036 — Canonical Strategy Representation
- `Docs/design/research_portfolio_lineup.md` (the verdict-distinct lineup; Phase 2)
- Portfolio Analytics Engine / CAP-021 (PR #322) — the corr ≈ 1.00 / 100%-overlap measurement
- [[mom002_broad_momentum]], [[fi001_factor_interaction]] — same-factor-≠-independent-evidence
- Research Program Registry — MOM-001 row + the CAP-021 measurement

_v1.0 — 2026-07-04. The MOM-001 risk-profile study is concluded; vol scaling is a deployment
configuration, not a distinct alpha._
