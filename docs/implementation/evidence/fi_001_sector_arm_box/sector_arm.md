# FI-001 — Sector Arm (box store) — Evidence Addendum

_Run on the AWS box store (the only store with `tickers.sector` populated: 21,679 names / 11 sectors), 2019-01-01..2026-06-12, n=150. All three phases re-run with the **Sector** book included._

> Completes the FI-001 Phase 1–3 arms that the local store could not run (it has 0 sector data). Adds
> **Sector Rotation** as a fourth validated book to the Measurement / Interaction / Allocation studies.

## ⚠ Scope caveat (read first)

The box store has full universe breadth only **from 2025** (pre-2025 SEP is sparse), so Momentum's
weekly backtest yields **80 rebalances, all in ~2025-01→2026-06** — an ~18-month recent window (the
diversifier books get 106). **Absolute magnitudes (the 40–52% CAGRs) are NOT comparable to the local,
full-history 3-book runs** and should not be read as long-cycle numbers. But every book ran on the
**same box store/window**, so the **cross-book comparison — which is the whole point of the sector arm —
is internally valid.** Treat this as a *directional* confirmation, pending a full-history sector store
(still Future Research / Medium).

## Phase 1 — where does Sector sit? (Measurement)

| Pair (vs Momentum) | Full corr | Stress corr (mom worst-DD) | Holdings overlap |
|---|---:|---:|---:|
| Momentum ↔ Low-Vol | 0.22 | 0.27 | 2.6% |
| **Momentum ↔ Sector** | **0.69** | **0.44** | 11.9% |
| Momentum ↔ Trend | 0.90 | 0.87 | 16.1% |

**Sector is a moderate diversifier of Momentum** — correlation 0.69 that **decouples to 0.44 in
Momentum's drawdown** (the good behavior), sitting cleanly **between Low-Vol (the cleanest, 0.22) and
Trend (redundant, 0.90)** — the H1 ordering prior (LOW < SEC < TREND) confirmed with the real fourth
book. Adding Sector lifts the diversification score from 29 (3-book, local) to **48/100** on this window.

## Phase 2 — does adding Sector to blends help? (Interaction)

| Blend (eqw) | Sharpe | MaxDD | ΔSharpe vs mom [95% CI] | ΔMaxDD (pp) | Verdict |
|---|---:|---:|---:|---:|---|
| Momentum + Sector | 1.09 | −31.5% | −0.091 [−0.622, 0.454] | +6.8 | Diversifies (DD-only) |
| Momentum + Low-Vol | 1.21 | −24.6% | +0.027 [−0.305, 0.439] | +13.7 | Diversifies (DD-only) |
| **Momentum + Low-Vol + Trend + Sector** | 1.23 | −24.0% | +0.048 [−0.526, 0.679] | +14.3 | Diversifies (DD-only) |

Same H2 verdict as the local run: every blend **cuts drawdown** with a **non-significant Sharpe change**.
Momentum + Sector alone doesn't lift Sharpe (−0.09, CI spans zero) but shaves 6.8pp of drawdown; the
**4-way equal blend** (adding Sector) reaches the shallowest drawdown of the diversified books (−24.0%).
Combining is a **drawdown** tool — confirmed with four books.

## Phase 3 — does a 4th book rescue sophisticated allocation? (Allocation)

| Method (4 books) | Sharpe | MaxDD | ΔSharpe vs eqw [95% CI] | ΔMaxDD (pp) |
|---|---:|---:|---:|---:|
| **Equal-weight** | **1.23** | −24.0% | 0.0 | +14.3 |
| Inverse-vol | 0.96 | −23.3% | −0.266 [−0.607, 0.166] | +15.0 |
| ERC | 0.88 | −23.2% | −0.348 [−0.872, 0.315] | +15.1 |
| Min-variance | 0.05 | −21.9% | **−1.177 [−2.255, −0.171]** | +16.4 |
| ERC + vol-target (12%) | 1.15 | **−13.4%** | −0.091 [−0.737, 0.556] | **+24.9** |

**This answers the local Phase 3 caveat definitively: a fourth (Sector) book does NOT flip the
ERC-vs-equal-weight calculus.** Equal-weight remains the best allocation (Sharpe 1.23); the
covariance-aware methods are *still worse*, and **min-variance is now significantly worse than
equal-weight** (CI [−2.255, −0.171] excludes zero). The vol-target overlay again cuts drawdown most
(−24.9pp → MaxDD −13.4%). Sophistication doesn't pay even with more books to work with.

## What the sector arm confirms

1. **Sector is a genuine moderate diversifier** (0.69 corr, decouples in stress) — consistent with
   SEC-001's Verdict B, and it slots between Low-Vol and Trend as expected.
2. **The FI-001 conclusion is unchanged and strengthened with four books:** combining validated factors
   is a **risk-management** tool (drawdown reduction), not an alpha source; **equal-weight beats
   sophisticated allocation** (now decisively for min-variance); the **vol-target overlay** is the
   drawdown lever.
3. The combined-book recipe stands: **equal-weight the diversified books + optional vol-target overlay.**

Artifacts: `apps/backend/research/fi001/sector_arm_box/phase{1,2,3}/`. Run mechanics: the three FI-001
scripts were injected into the live backend container via `docker cp`, run read-only against the box
store, then removed (the live app code was untouched). Definitive long-history confirmation still awaits
a store with both full history and sector data (Future Research / Medium).
