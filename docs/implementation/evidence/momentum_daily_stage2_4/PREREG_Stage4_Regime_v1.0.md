# Momentum-Daily — Stage 4 Pre-Registration: Regime Filter

| | |
|---|---|
| Stage | **Stage 4 — Regime filter refinement** (proposal v1.1 §7, §9) |
| Status | **FROZEN before any Stage-4 backtest is run** |
| Inherits | Stage-3 winner **N5 / hybrid 50-50 inverse-vol / no sector cap**, on the §5.1 daily-conditional policy (owner-confirmed) |
| Harness | `apps/backend/scripts/backtest_momentum_stage4.py` (this branch) |

Stage 4 holds the entire book fixed (signal 12-1, daily conditional §5.1, 5 names, hybrid sizing, no
sector cap) and compares four **regime-filter** variants. This is the stage that directly targets the
~−74% max drawdown every prior stage carried: the regime overlay de-grosses the book in a market downtrend.

## 1. Frozen controls (from Stages 1-3)

Universe top-200 PIT · 12-1 signal (252/21) · eligibility raw>0 ∧ z≥0 · daily conditional §5.1 policy ·
5 names · **hybrid 50/50 inverse-vol sizing** (per-name ≤20%) · **no sector cap** · 10 bps one-way · $100k ·
window 2005-01-03 → 2026-06-12.

## 2. ⚠ Regime gauge — a disclosed substitution for SPY

The live strategy's regime filter is defined on **SPY**'s 200-day MA. **SPY is not in the research store**
(Sharadar SEP excludes ETFs — SFP not licensed; `index_prices` holds only ^VIX from 2021). Stage 4
therefore computes the regime gauge from a **broad equal-weight market-proxy index** built from the same
survivorship-free SEP spine:

- Basket = the union of `universe_asof(store, d, n=500)` sampled at each month-end over the window (the
  PIT liquid large-cap set).
- Daily index return = the cross-sectional mean daily `closeadj` return across basket names priced on both
  d−1 and d; chained to a level series; **200-trading-day moving average** = the trend gauge.

This is a **proxy for the SPY 200-day MA**, not SPY itself. It is arguably *more* survivorship-honest
(built from the actual investable universe), but it is a substitution and is disclosed as such. **What
Stage 4 decides is the regime *variant* (binary / buffered / graduated / none) and whether a filter helps
at all** — that conclusion transfers to the SPY-based live implementation, which keeps using SPY. The
absolute levels are proxy-dependent; the *ranking of variants* and the *does-a-filter-help* verdict are the
transferable outputs.

## 3. The four variants (§7) — everything else frozen

| Variant | Rule | Gross exposure |
|---|---|---|
| **A — Binary** (current) | proxy close vs its 200-day MA | 1.00 above MA · 0.00 below |
| **B — Buffered binary** | risk-off requires close ≥ **1%** below MA for **2** consecutive days; risk-on requires ≥ 1% above for 2 days; else hold prior state | 1.00 / 0.00, whipsaw-suppressed |
| **C — Graduated** | distance from MA sets gross | 0.98 when >+2% above · 0.60 within ±2% · 0.15 when <−2% below |
| **D — None** (control) | no filter | 1.00 always (= the Stage-3 winner as-is) |

Pre-registered variant parameters (fixed, within the §7 ranges, not tuned after seeing results): buffer
band **±1%** and **2-day** confirmation for B; graduated thresholds **±2%** with gross **0.98 / 0.60 / 0.15**
for C. Un-invested gross is held as cash earning zero. A regime gross change is itself a §5.1 trigger
(`regime_change`), so the book re-grosses immediately on a flip.

## 4. Metric set (§9) + special weight on momentum-crash windows

Net CAGR, Sharpe, Calmar, max drawdown, annualized turnover, average holding period, worst single-name gap
loss, and the three crash-window returns — with **special weight on behavior in momentum-crash windows**
(2008 GFC, 2020 COVID recovery), per §7. The whole point of the regime filter is crash-drawdown control, so
max drawdown and crash-window returns are weighted heavily; a variant that only raises CAGR without
improving drawdown does not win.

## 5. Winner rule + expected outcome

Winner = the variant that most improves **max drawdown and momentum-crash-window behavior** while not
materially sacrificing risk-adjusted return (Sharpe / Calmar). Near-ties resolve toward **less whipsaw /
lower turnover** (buffered over raw binary) per the §7 rationale. Expected: some filter (A/B/C) beats the
no-filter control **D** on drawdown; the buffer (B) or graduation (C) should beat the raw binary (A) by
cutting whipsaw. If **no** filter improves risk-adjusted drawdown over D, that is a reportable finding, and
the fail-open regime *robustness* fix (A5) still ships regardless (it is already in Stage 1 / Workstream A).

The winning variant is the **final promotion-candidate configuration** for momentum-daily.

*Frozen: 2026-07-15. Changes after the first Stage-4 run require a new version + re-run.*
