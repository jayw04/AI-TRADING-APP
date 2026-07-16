# MR-002 — Pre-Registration v0.1 (DRAFT) · Sector-Neutral Residual Reversion

**Date:** 2026-07-11 · **Owner:** Jay Wang · **Program ID:** MR-002 (Q1) · **Registry:** → **Planning**
(entered on owner approval of this draft; **Running** on freeze) · **Authority:** owner strategy proposal
`Docs/Strategies/Proposed Strategies.txt` (2026-07-11) + the RNG-001 disposition.
**Status:** 🟡 **DRAFT v0.1 — NOT FROZEN.** Freeze requires owner answers to **Q1–Q5** (§12). No backtest
code runs, and no data beyond the availability gate is materialized, until this document is frozen — the
design must be locked blind (GAPPER-001 precedent).

> **Governance disposition (from the proposal, restated as binding):** RNG-001 remains **Completed ·
> Rejected (Evidenced) · Archived** and is not modified. MR-002 is a **new hypothesis** — sector-neutral
> residual reversion across a broad liquid universe — **not** a continuation or parameter repair of
> RNG-001's VWAP-deviation fade. The companion candidate RNG-002 (regime-gated ETF range reversion) is
> chartered **separately, later**, and only after MR-002's harness work is underway (proposal order:
> MR-002 primary, RNG-002 secondary).

## 1. Hypothesis

After removing broad-market and sector movements, unusually large company-specific (residual) price moves
frequently represent temporary liquidity pressure rather than information, and **partially reverse over
the following one to five trading sessions**. The economic mechanism is compensation for providing
liquidity (consistent with the maintained daily-reversal factor literature); the edge is therefore
expected to come from **breadth and repeatability across many small independent trades**, not from
magnitude in any single episode.

How this differs from the rejected RNG-001 (pre-registered, so the independence is auditable):
it does not fade distance-from-VWAP; it removes market + sector return before measuring overextension;
it diversifies across many stock-level events instead of a few range episodes; and it excludes likely
information-driven moves (earnings/corporate-event windows, large gaps).

## 2. Universe (point-in-time, reconstituted monthly)

Reconstituted on the **first trading day of each month** using only data available at that date:

- **Top 250 US common stocks by trailing 60-session median dollar volume** (target 200–300; 250 fixed as
  the primary; 200 and 300 are pre-declared sensitivities, not alternatives to optimize over).
- Close price **> $10** on the reconstitution date.
- Trailing 60-session **median dollar volume > $25M**.
- **Common stocks only** — no ETFs, ADRs, preferred shares, SPACs, or units (Sharadar TICKERS
  `category`/type filters).
- **No recent IPOs:** ≥ 252 prior trading sessions of price history required.
- **Short side:** borrow assumed available for this universe at the registered cost (§7); names flagged
  hard-to-borrow are handled per Q4.
- A name that leaves the universe mid-month is not force-exited; existing positions run to their normal
  exit, but no new entries.

Survivorship-freedom is mandatory: membership is computed from point-in-time price/volume history
(Sharadar SEP), never from a current-day constituent list.

## 3. Signal construction (frozen definitions)

For every stock `i`, estimate the rolling **60-session** OLS model on daily total returns:

`r_i,t = α_i + β_m,i · r_SPY,t + β_s,i · r_Sector,t + ε_i,t`

- `r_SPY,t` = SPY total return; `r_Sector,t` = the stock's GICS sector SPDR (XLK/XLF/XLE/XLV/XLI/XLP/
  XLY/XLU/XLB/XLC/XLRE) total return, mapped via the factor-store `tickers.sector` resolver (the
  GAPPER-001 CAP pattern). A stock whose sector cannot be resolved is **excluded**, never defaulted to
  SPY-only (no silent fallback — CAP-024 principle).
- Betas are estimated on sessions `t−60 … t−1` (no same-day look-ahead); the day-`t` residual is
  `ε_i,t = r_i,t − α̂_i − β̂_m,i·r_SPY,t − β̂_s,i·r_Sector,t`.
- **Signal:** `z_i,t` = (cumulative residual over sessions `t−4 … t`) ÷ (rolling 60-session standard
  deviation of the 5-session cumulative residual). Overlapping 5-day windows are used for the volatility
  estimate; this is fixed, not tuned.

## 4. Entry, exit, and timing (frozen)

**Timing (Q3):** signals are computed after the close of session `t`; entries and exits execute at the
**next session's open** (`t+1` open), with costs per §7. Portfolio refresh is daily.

**Long entry — all must hold:** `z ≤ −Z_entry` · stock in the **bottom 10%** of that day's eligible
residual z-scores · no earnings announcement within **[t−2, t+2]** sessions (Sharadar EVENTS) · no
merger/split/delisting/major-corporate-action flag (Sharadar ACTIONS) · one-day opening gap **< 6%** ·
spread/impact inside the registered liquidity envelope (§7).

**Short entry — mirror:** `z ≥ +Z_entry` · top 10% of eligible scores · same event and liquidity
exclusions · borrow assumed per §7 with cost below the registered limit.

**Exit — first occurrence of:** `|z|` returns inside **±0.35** · **5 sessions** elapsed · residual
extends beyond **±3.5** *and* the market or sector confirms the direction (SPY or the sector ETF moves
the same direction ≥ 1σ of its own 60-session daily vol that day) — the hypothesis-failure stop · an
earnings/prohibited event enters the next-session window · portfolio risk limit forces reduction.
**No tight ordinary price stop** (pre-registered: reversion trades routinely worsen before reverting;
the stop detects hypothesis failure, not noise).

## 5. Portfolio construction (frozen)

Market beta ≈ neutral and sector exposure ≈ neutral (both within ±10% of gross) · equal residual-risk
contribution across positions · max position **1.5% of gross** · max sector gross **20%** · initial
gross exposure **100%** (1.0×; never increased inside the backtest) · portfolio volatility target **8%
annualized** (63-day realized, the platform's standard overlay) · no position > **3%** of projected
portfolio risk. Gross exposure increases are a *live-paper governance* decision after validation, never
a backtest parameter.

## 6. Frozen parameter policy (exactly three configurations)

| Config | Entry `Z_entry` | Exit z | Max hold | Role |
|---|---|---|---|---|
| A | 1.75 | 0.35 | 5 sessions | neighborhood sensitivity |
| **B (PRIMARY)** | **2.00** | 0.35 | 5 sessions | **the verdict configuration** |
| C | 2.25 | 0.35 | 5 sessions | neighborhood sensitivity |

The verdict is read on **B only**. A and C exist to test parameter-neighborhood stability (a pass gate),
not to pick a winner. **No other combinations are run.** PBO and Deflated Sharpe computations declare
`N_trials = 3` (plus any sensitivity explicitly listed in this document — nothing else).

## 7. Data plan & cost model

| Input | Source | Note |
|---|---|---|
| Stock daily prices/volume | **Sharadar SEP** (dividend-adjusted returns) | survivorship-free, PIT |
| Universe metadata / sector | Sharadar TICKERS (+ factor-store sector→SPDR resolver) | unresolved sector ⇒ exclude |
| Earnings dates | **Sharadar EVENTS** | drives the [t−2, t+2] exclusion |
| Corporate actions | Sharadar ACTIONS | merger/split/delisting flags |
| SPY + sector ETF returns | **Yahoo adjusted close** (research-grade, the TREND precedent) | Sharadar bundle has no ETF prices (no SFP) |

**Cost model (Q2 — proposed, to be confirmed at freeze):**

- **Base:** 10 bps/side per stock trade (spread + impact, all-in, conservative for top-250 liquidity) ·
  short borrow **50 bps/yr** on short market value, accrued daily.
- **Stress (mandatory pass gate):** **2×** — 20 bps/side and 100 bps/yr borrow.
- **Liquidity envelope:** a trade may not exceed **2% of the stock's 20-session median daily dollar
  volume**; capacity reporting (§10) uses this participation cap.
- Rejection rule (from the proposal, binding): a short-horizon strategy that passes only under zero-cost
  or close-price execution **must be rejected**.

**Data Availability Gate (first execution step, before any signal code):** verify SEP depth and coverage
for the top-250 construction across the full window; verify sector-SPDR history (XLC 2018-06, XLRE
2015-10 — sector mapping before ETF inception is handled by Q5); verify EVENTS/ACTIONS coverage over the
window; record the realized window + any exclusions in the evidence package. If coverage forces a window
materially shorter than ~10 years, **stop and re-review before freeze** (power).

## 8. Testing sequence (frozen order — no step may be skipped or reordered)

1. **Development sample:** first **50%** of the realized data window (harness construction + the three
   configs run here only).
2. **Walk-forward validation:** next **25%**, rolling folds; fold P&L recorded per fold.
3. **Sealed out-of-sample:** final **25%** — **run once, on config B, after §1–§7 are frozen**; results
   are never used to adjust anything. Any post-hoc change creates **MR-002-v2** with a new untouched
   sealed period (Q1).
4. **Date-clustered (block) bootstrap** on daily book returns — dates are the resampling unit (CAP-003 /
   CAP-025 lesson: same-day positions are correlated).
5. **Regime decomposition:** bull / bear / sideways / high-vol / low-vol attribution.
6. **Transaction-cost sensitivity:** 0.5× / 1× / 2× grid + **breakeven cost** headline.
7. **Parameter-neighborhood stability:** configs A and C.
8. **PBO + Deflated Sharpe** with `N_trials` per §6.
9. **Paper-trading verification before any production discussion** (CEE from day one, ADR-0040 metrics).

## 9. Verdict framework & pass gates (LOCKED at freeze)

Platform three-way framework, extended by the proposal's gate table. The verdict is read on **config B,
net of base costs, on the sealed OOS period** unless a gate names another sample.

**✅ Approved (standalone)** — ALL of:

| Gate | Requirement |
|---|---|
| Net OOS Sharpe | ≥ 0.70 |
| Net OOS Calmar | ≥ 0.75 |
| Max drawdown (net, full test) | ≤ 15% |
| Positive walk-forward folds | ≥ 60% |
| Date-clustered bootstrap mean-return CI | lower bound > 0 |
| Cost stress | still profitable at 2× costs |
| Parameter stability | configs A and C both profitable (net) |
| PBO | < 20% |
| Deflated Sharpe significance | ≥ 95% |
| Profit concentration | no single year > 35% of total P&L |
| Regime concentration | no single regime > 60% of total P&L |
| Capacity | positive net edge under the 2% participation cap |

**🟡 Diversifier (B)** — fails Approved, but ALL of: net OOS Sharpe ≥ 0.40 · bootstrap CI lower bound
> 0 · |corr| ≤ 0.30 vs the MOM-001 canonical book on overlapping dates · cost-stress, PBO, DSR, and
both concentration gates still pass. (A market-neutral sleeve earns Diversifier only with real
stand-alone evidence — neutrality alone is not value.)

**🟡 Power-Limited · Inconclusive** — the TREND-001 §9 lesson, pre-registered here: before the verdict,
compute **MDE₉₅** for the sealed-OOS Sharpe under the date-clustered bootstrap. If the observed Sharpe
is positive but the CI spans zero **and** the observed effect < MDE₉₅, the label is a **power failure**,
not a rejection, and is reported as such.

**🔴 Rejected** — adequate power and any mandatory gate fails, or the cost/zero-cost rejection rule
(§7) fires.

The key decision metric is **credible net return after robustness and cost gates — never highest
backtested CAGR** (binding, from the proposal).

## 10. Evidence package (`evidence/mr_002/`, seeded & reproducible)

Pre-reg (this doc, frozen) · harness code + seed · run manifest (data snapshot hashes, window, universe
counts per month) · results: **Performance** (CAGR, Sharpe, Sortino, Calmar, maxDD) · **Trade quality**
(win rate, payoff, expectancy, trade count) · **Robustness** (folds, bootstrap CI, A/C neighbors) ·
**Costs** (gross vs net, 1×/2×, breakeven) · **Stability** (annual + regime attribution) ·
**Concentration** (top trades/dates/sectors/names) · **Capacity** (turnover, participation, borrow) ·
**Validation** (PBO, DSR, MDE) · Evidence Brief + registry/`programs.py` entry.

## 11. Stopping rule & lifecycle

One primary design; one sealed test. **No parameter adjustment after viewing sealed OOS results** — any
revision is a fresh pre-registration (**MR-002-v2** or MR-003 per Q1) with a new untouched test period.
No paper promotion unless the Approved or Diversifier gate clears; paper requires CEE from day one and
the standard promotion protocol. If Rejected: archive with the evidence brief — the rejection is a
citable asset (CAP-011). Registry entry created at freeze (Planning → Running); `programs.py` mirrored.

## 12. Open questions — owner answers required BEFORE freeze

- **Q1 · Program ID & revision convention.** The proposal names it **MR-002**, but no MR-001 exists in
  the registry (RNG-001 is the prior mean-reversion program under a different family). Confirm: keep
  **MR-002** as the permanent ID (implicitly acknowledging RNG-001 as the family's #001), and confirm
  whether a post-sealed revision is **MR-002-v2** (proposal's wording) or a new **MR-003** (GAPPER
  convention: a revision is a fresh program).
- **Q2 · Cost model numbers.** Confirm 10 bps/side base + 50 bps/yr borrow (stress 2×) and the 2%
  participation cap, or set different registered values.
- **Q3 · Execution timing.** Confirm **next-session-open** execution for entries and exits (signal at
  close `t`, trade at open `t+1`). Alternative: close-to-close (`t+1` close) as a sensitivity only.
- **Q4 · Hard-to-borrow handling.** No historical borrow data source exists in our stack. Proposed:
  assume general-collateral borrow for the whole top-250 universe at the §7 registered cost, and report
  short-side P&L share so the verdict's borrow sensitivity is visible. Confirm, or restrict the short
  book (e.g., top-150 only).
- **Q5 · Sector history.** XLC (2018) and XLRE (2015) post-date most of the window. Proposed: map their
  sectors to the pre-inception parent SPDR (Communication→XLK/XLY legacy composition, Real Estate→XLF)
  before inception, disclosed in the manifest. Confirm, or drop those two sectors' stocks pre-inception.

---

*Draft v0.1 → owner review → answers folded → **FROZEN v1.0** → Data Availability Gate → development
sample. RNG-002 gets its own separate pre-registration afterward; it is not covered by this freeze.*
