# TREND-001 — Pre-Registration v1.0 (FROZEN) · Multi-Asset Time-Series Trend

**Date:** 2026-07-08 · **Owner:** Jay Wang · **Program ID:** TREND-001 · **Registry:** Planning →
Running → **Rejected — power-limited (2026-07-08)** · **Authority:** accepted Strategy Production Sprint
Plan **v0.4**. · **Verdict + evidence:** `evidence/trend_001/TREND001_Evidence_Brief.md`
(Sharpe 0.83 vs 0.62, MaxDD −10% vs −29% / 65.9% reduction, but ΔSharpe CI [−0.37,+0.77] spans 0 and
the study is under-powered — MDE 0.58 > observed 0.20; robust across all 7 sensitivities. Not
evidence of no effect; owner options incl. TREND-002 longer-history variant).
**Status:** ✅ **FROZEN v1.0 (2026-07-08).** §5 parameters and §10 thresholds confirmed by the owner;
the ETF Data Availability Gate (ingestion + total-return verification) runs in parallel and records the
final universe. Any change to the primary design is TREND-002, not an edit of this file.

> **Discipline (frozen before any result).** One primary design; no looping on parameters. **Approval
> requires a confidence interval that excludes zero**; a rejection may occur because the CI spans zero;
> a *power* failure is labelled as such, **not** a rejection. Any change to the primary design is
> **TREND-002** (a new program ID + fresh pre-registration), never an edit of this file. Sensitivities
> inform interpretation; they never become the primary post-hoc.

---

## 1. Hypothesis

**Primary (pre-registered):** *assets with a positive medium-term own-trend outperform owning the same
assets (and cash) after volatility targeting and costs.*

Time-series / **absolute** momentum (each asset's own trend), **not** cross-sectional momentum and
**not** the rejected TV-001-Supertrend import.

## 2. Universe (subject to the §3 Data Availability Gate)

- **Primary (10):** SPY · QQQ · IWM · EFA · EEM · TLT · IEF · GLD · DBC · UUP.
- **Sensitivity-only sleeve:** KMLM (shorter history).
- **Pre-declared exclusion rule:** an ETF failing *any* §3 criterion is excluded **before any results
  are computed**, and the final universe is recorded in the evidence package.
- **Bond stop-and-review clause (reviewer refinement):** if **TLT or IEF** fail the total-return
  criterion, **HALT and source a total-return series** — do **not** silently drop them. Bonds carry
  trend-following's diversification; dropping them changes what the strategy *is* (unlike dropping
  UUP/DBC, which is a benign universe sensitivity).

## 3. Data & pricing basis — the Data Availability Gate

- **Source (corrected for ETFs):** Alpaca daily bars **+ the total-return construction seam**
  (`app/factor_data/total_return.py` + `app/market_data/alpaca_distributions.py` — cash dividends +
  split multipliers). **Not** the equity factor store (ETFs are not in Sharadar SF1). *Finding
  2026-07-08: the platform's Alpaca bars are RAW/unadjusted (DCAP-003), so total return must be
  constructed via this seam.*
- **Total-return criterion (HARD gate).** Each ETF needs a **verified dividend + split-adjusted
  (total-return) series**. **Raw / close-only ⇒ EXCLUDED** (same as insufficient history): a close-only
  basis systematically understates TLT/IEF returns and can flip the cash-vs-bonds switch and the
  verdict. *Documenting a known-wrong basis does not make a verdict valid.*
- **Per-ETF checklist:** TR series built & validated · history extends to the latest expected trading
  date · no large unexplained gaps · ticker resolves in Alpaca.
- **Ingestion task (first gate action):** the 10 ETFs are **not yet cached** on the box — ingest daily
  bars + distributions before the run.
- **Sprint-wide (for Week 2):** confirm gappers-file / SCAN candidate-file freshness + intraday-bar
  availability (GAPPER-001).

## 4. Signal — exact boolean (frozen)

Hold asset *i* at a rebalance **iff**:

```
TR_12m_skip1(i) > 0   AND   price(i) > MA200(i)
```

evaluated on **total-return (adjusted)** prices at the monthly rebalance date. The **same boolean gates
entry and exit** — no separate exit rule. Failing either condition at a rebalance ⇒ that sleeve is in
**cash** until the next rebalance.

- **`TR_12m_skip1`** = the trailing 12-month total return skipping the most recent month (the platform's
  momentum convention). **12-month-including-last is a sensitivity, not the primary** (recorded as a
  deliberate choice, not a habit).

## 5. Portfolio construction (frozen parameters — confirm before freeze)

- Long-only · **volatility-targeted** · risk-budgeted via the **PORT-001 ERC + vol-target overlay**
  (CAP-018) · **cash when the boolean fails**.
- **Cash leg:** T-bill / BIL total-return proxy (preferred for realism); **zero-yield is a sensitivity**.
- **Pre-registered parameters** *(owner to confirm; these freeze the design):*
  - Portfolio **volatility target = 10% annualized**.
  - **Volatility lookback = 63 trading days** (ex-ante, no look-ahead).
  - Per-asset **inverse-vol risk budget** with the CAP-018 sqrt-damped ERC blend.
  - **Costs = 5 bps per side** (liquid ETFs) + the slippage assumption; report **cost drag at 2× costs**.

## 6. Rebalance cadence (do NOT optimize)

Primary: **monthly, first trading day of the month.** Weekly is a **sensitivity** only.

## 7. Benchmarks

- **Primary:** equal-weight buy-and-hold of the same ETF universe, monthly rebalanced (*does the trend
  rule add value over simply owning the same assets?*).
- **Secondary (descriptive, NOT CI-gated — short overlap):** DBMF and/or KMLM (managed-futures/trend
  ETFs, ~2019–2020+). If the book can't beat buying the trend ETF after costs, the honest recommendation
  is "buy the ETF" — that answer is itself platform value. *Reviewer refinement: the ~5–6-yr overlap is
  low-power, so this is reported directionally, not as a CI verdict.*
- **Tertiary:** SPY · 60/40 SPY/TLT · the T-bill proxy.

## 8. Backtest period

The **longest common total-return history across the primary 10** (expect **~2007+**: DBC 2006 / UUP
2007 constrain the start; EFA 2001 / EEM 2003 / TLT · IEF 2002 are older). The modern full universe
(incl. the KMLM sleeve) is a **sensitivity**.

## 9. Power check — run BEFORE interpreting the verdict

With ~215 monthly observations and trend's crisis-concentrated payoff, a ΔSharpe **block-bootstrap** CI
may be unable to exclude zero *even under the true historical effect*. Before the verdict:

- Simulate the primary design's ΔSharpe CI width under a **range** of plausible **net-of-cost** effect
  sizes (conservative / central / optimistic for this universe & window), and **report the minimum
  detectable effect (MDE)** at the pre-registered block settings.
- If the design **cannot plausibly reject the null even when the effect is real**, record a **power
  limitation** in the evidence package; the **Diversifier path (§10) becomes the realistic bar**. A
  "rejection" that is actually a power failure must be labelled as such.

## 10. Verdict — three-way (all thresholds frozen before the run)

- **Approved:** the **block-bootstrap** CI on **ΔSharpe vs the primary benchmark excludes zero** (block
  length **= 6 monthly observations** — vol-targeting induces autocorrelation an iid bootstrap
  understates).
- **Diversifier:** ΔSharpe CI spans zero **but BOTH** — **relative MaxDD reduction ≥ 25%** **AND
  ΔCalmar > 0 with its CI excluding zero**. → eligible for a **defensive paper sleeve**, not the core
  lineup. *This is not a relaxed bar — it measures TS-trend's actual claim (crisis convexity / drawdown
  control), which headline Sharpe under-captures.*
- **Rejected:** neither path clears.
- **Guardrails (all paths):** CAGR drag **≤ ~30% relative** vs the primary benchmark (pre-set) · robust
  across ETF-only and equity-index subsets · survives cost/slippage.

## 11. Sensitivities (never the primary; recorded for interpretation only)

3/6/12-month ensemble score · MA-only · TR-only · 12m-including-last · weekly cadence · **ex-UUP** ·
**ex-DBC** (tests whether the edge is mostly "avoided the perennial decliners") · zero-yield cash ·
KMLM-included universe.

## 12. Usability / capacity block (in the evidence package)

Suggested account-size range · expected turnover · average number of positions · capacity estimate ·
worst historical drawdown · expected cash usage · user suitability (core / defensive) · **cost drag at
2× assumed costs**.

## 13. Deliverables & lifecycle

- **Evidence Package** (CAP-002): this pre-registration + a **seeded, reproducible** script + JSON +
  Markdown result. Circular-**block** bootstrap (CAP-003) for all CIs.
- **Registry:** TREND-001 Planning → Running → verdict (Approved / Diversifier / Rejected / power-limited).
- **On Approved or Diversifier:** promote to a small paper book **only** with **CEE attached from day
  one** and under the **Week-3 pre-registered paper protocol** (min duration, drift bands, halt rule).
- **Nothing user-visible** before the paper protocol completes; the evidence brief (with its
  Backtest-verdict label) may publish regardless of outcome (§Sprint success).

---

### Confirmed & frozen (owner, 2026-07-08)

1. **§5 parameters CONFIRMED** — vol target 10% · 63-day vol lookback · 5 bps/side costs · block length
   6 monthly obs.
2. **§10 thresholds CONFIRMED** — Diversifier relative-MaxDD ≥ 25% · CAGR-drag guardrail ≤ 30% relative.
3. **§3 data** — the ETF Data Availability Gate (ingest daily bars + build/verify total-return via the
   `total_return.py` seam) is **running now**; the final universe is recorded on completion (append below).

### Data Availability Gate — result (2026-07-08) → ⛔ STOP-AND-REVIEW

Ran on the box (Alpaca paper adapter). Two blockers found **before** any backtest — the gate held the
line:

**(A) Total-return pipeline broken (fixable blocker).** The PORT-001 #3 seam does not currently produce
correct total-return series: (1) `AlpacaDistributionsProvider.prefetch` fails on a datetime with a
time component (Alpaca `CorporateActionsRequest` requires bare dates) → `fallback=True`; (2) even with
bare dates the fetch *succeeds* (181 dividends for SPY/TLT/IEF) but the dividends **do not apply** —
`tr_close == raw close` (`distrib_contribution = 0.0pp` where TLT should show ~20pp over 6y): an
ex-date ↔ bar-timestamp alignment miss in `total_return_bars`. **Per the §3 hard TR gate, TREND-001
cannot run until this is fixed** (a small PORT-001 #3 fix).

**(B) ETF history is only ~2020-07-27 → present (~1,490 daily bars, ~6 years).** All 10 primary ETFs
start **2020-07-27** on the box's Alpaca paper/IEX feed (KMLM 2021-02) — **not the ~2007+ assumed**.
~72 monthly rebalances over one mostly-bull regime + the 2022 drawdown is **power-dead for a ΔSharpe
verdict** and misses every crisis the trend literature relies on.

**RESOLUTION (owner, 2026-07-08): Yahoo adjusted-close as the research data source.** Both blockers
resolved in one move — Yahoo `Adj Close` already incorporates dividends+splits (so it *is* the
total-return basis, decoupling TREND-001 from the broken PORT-001 TR pipeline), and it provides full
per-ETF inception history:

| ETF | Yahoo history start | ETF | history start |
|---|---|---|---|
| SPY | 1993-01 | TLT / IEF | 2002-07 |
| QQQ | 1999-03 | GLD | 2004-11 |
| IWM | 2000-05 | DBC | 2006-02 |
| EFA | 2001-08 | **UUP** | **2007-03** |
| EEM | 2003-04 | KMLM (sens.) | 2020-12 |

**FINAL UNIVERSE (all 10 primary pass): SPY · QQQ · IWM · EFA · EEM · TLT · IEF · GLD · DBC · UUP.**
No exclusions; the §2 bond stop-and-review clause is satisfied (TLT/IEF have adjusted series). **Common
backtest window = 2007-03-01 (UUP inception) → present ≈ 19.3 years / ~232 monthly rebalances**, spanning
2008 / 2011 / 2015-16 / 2018 / 2020 / 2022. KMLM (2020-12+) stays a short-window sensitivity.

**Data provenance note:** Yahoo is a **research-only** source (the backtest, not the order path), so
ADR-0030's no-live-vendor rule does not bind; adjusted-close is dividend/split-adjusted (≈ total
return). The PORT-001 #3 total-return-pipeline bugs (date coercion + ex-date alignment) are a **separate
platform fix**, tracked off TREND-001's critical path.

**Gate status: ✅ PASS.** TREND-001 is unblocked for the Week-1 backtest.
