# GAPPER-001 — Pre-Registration v0.1 · Gap + RVOL Opening Continuation

**Date:** 2026-07-08 · **Owner:** Jay Wang · **Program ID:** GAPPER-001 · **Registry:** Planning →
**Running** (on freeze) · **Authority:** Strategy Production Sprint Plan v0.4 (Week 2) + TREND-001/002
disposition (trend characterized; sprint focus now GAPPER).
**Status:** ▶ **ACTIVE — evidence accruing** (owner decision 2026-07-08: build the Candidate Report now,
then accrue). The Data Availability Gate ran → GAPPER-001 is **data-gated** (only 11 gappers-dates « the
≥40 floor; candidate intraday bars uncached) → **verdict = pending forward accrual**. Provenance resolved
to **live-files-only** (PIT reconstruction impractical — no premarket-gapper inputs before 2026-06-22).
The **Morning Opportunities Candidate Report is shipped** (`scripts/reports/morning_opportunities.py`).
Full design-freeze (verdict metric + replay) happens when the ≥40-date sample gate is met (≈ September).

> **Why now.** TREND-001/002 honestly characterized multi-asset trend (defensive Diversifier Candidates,
> power-limited, no paper). The next chance at a **user-visible** strategy is the SCAN/gapper opportunity
> engine — the platform's *validated* SCAN-001 capability turned into a candidate **trade** strategy.
> **Not** a Range Trader revival (RNG-001 archived): this is **continuation**, not fade. Same discipline:
> pre-registration → evidence package → verdict (CI-gated) → stopping rule → paper only if a gate clears.

## 1. Hypothesis (pre-registered)

*High-quality gap/RVOL candidates that hold above VWAP / the opening-range high after the first 30
minutes continue — intraday.*

## 2. Candidate source

The **validated SCAN-001 Candidate Engine** — Gap %, RVOL, ATR-normalized move, Discovery Confidence
(ATR-decoupled), liquidity/spread filters. GAPPER-001 does not invent a new screen; it tests whether the
SCAN candidates carry a tradable **continuation** edge.

## 3. Candidate provenance + minimum-sample gate (BLOCKING — open item)

Historical SCAN candidates may exist only since SCAN went live, which can be far too few for a verdict.
Pick one at freeze:
- **(a) Point-in-time reconstruction** — re-run SCAN-001's selection over historical data. The
  reconstruction is itself pre-registered (inputs, as-of data, any filter differing from live) — this is
  where look-ahead sneaks in, so it is reviewed as *design*, not code detail.
- **(b) Live-files-only** — accept the small window; the gate below decides.

**Minimum-sample gate:** **≥100 eligible gap events across ≥40 distinct dates after the liquidity floor**
(300+/60+ preferred). Below the floor the verdict is **`insufficient_sample`** (not Approved, not
Rejected) and the Week-2 deliverable becomes "evidence accumulation started" — an honest outcome. A tiny
sample must not masquerade as a verdict.

## 4. Primary design (locked — one design; the rest are sensitivity)

SCAN-001 candidate → **enter on the 30-min opening-range high break** → **require price above VWAP** →
**require market & sector positive** → **exit at same-day close**.
- **"Market & sector positive" (exact):** SPY **and** the candidate's sector ETF (GICS-mapped SPDR) both
  **above their prior session close** at the entry bar.
- **Entry price modelling:** fills at the OR-high break **+ half the prevailing spread** (breakout entries
  buy into momentum — adverse selection is the base case, not a sensitivity).
- **Sensitivity (never the primary):** 15-min high break · 1/3/5-day hold · ATR trailing stop ·
  VWAP-only filter. *GAPPER-001 is not a parameter search.*

## 5. Liquidity floor (pre-registered NOW, default-exclude)

Minimum price **$5** · minimum median dollar volume **$20M/day (20-day)** · maximum time-of-entry spread
**25 bps**. Anything below the floor is excluded from the universe *before* any results are computed. A
paper edge in thin names is useless to users if it cannot be executed.

## 6. Execution realism — slippage & method

- **Slippage grid: 5 / 10 / 25 / 50 / 100 bps.** Gap-day small/mid-caps routinely trade 30–100+ bps
  effective spreads at the 30-minute mark; the evidence package reports the **breakeven slippage** (the
  bps level at which the edge dies) as a headline number, alongside the capacity estimate.
- **Method — CAP-025 Intraday Replay & Entry-Funnel Diagnostics** (avoids RNG-001's daily-OHLC false
  positive): post-activation fill rate · target-after-entry vs stop-after-entry · day-level P&L (idle
  capital = 0) · **date-clustered bootstrap** over a train/test split · slippage sensitivity ·
  spread/liquidity capacity.

## 7. Verdict (open item — confirm before freeze)

Three-way, thresholds frozen before the run:
- **Approved:** the **date-clustered bootstrap CI on the net per-trade (or day-level) edge excludes zero**
  after realistic costs, **and** the breakeven slippage comfortably exceeds the assumed cost band
  (proposed: breakeven ≥ 2× the assumed entry cost).
- **Inconclusive / `insufficient_sample`:** the §3 gate isn't met, or the edge CI spans zero under a
  sample too small to resolve (a power limitation, labelled as such — as in TREND).
- **Rejected:** adequate sample, CI spans zero (or breakeven slippage below the assumed cost).
- *Proposed primary metric — net per-trade edge in bps (date-clustered) — owner to confirm vs day-level
  P&L.*

## 8. Deliverable

Intraday-replay + opening-continuation **Evidence Package** (seeded, reproducible; CAP-025 funnel) **+ a
lightweight Morning Opportunities Candidate Report** — a table reusing SCAN-001, **no full UI this
sprint**: `ticker · gap % · RVOL · Discovery Confidence · entry trigger · VWAP status · liquidity/spread
· result label`. **Label discipline:** the report inherits the **ADR-0037 whitelist verbatim** (Watch ·
Research · Backtest Pending · Validated Pattern · Rejected Pattern); no Buy/Sell/target/conviction
vocabulary, and the "entry trigger" column describes the *studied rule*, never an instruction to the
reader. This is the sprint's most user-visible artifact and therefore its compliance surface.

## 9. Data Availability Gate (first execution step — the likely blocker)

Before any replay: confirm **gappers-file freshness** (the claude-trading-view files SCAN-001 consumes),
**SCAN candidate-file freshness**, and **intraday-bar availability** for the candidate window (the 1/5-min
bars the OR-break + VWAP need). As with TREND-001, the gate runs first and records what is/isn't
available; if intraday history is too shallow, the realistic Week-2 outcome is `insufficient_sample`
("evidence accumulation started"), which is honest.

### Data Availability Gate — result (2026-07-08) → data-gated; accrue forward

Ran on the box. **11 gappers-dates** only (2026-06-22 → 07-08, ~10 candidates/day); **6** persisted
premarket-gate evidence records; intraday bars cached for **19 liquid names (5Min) / 5 (1Min)** but
**0 of the current gapper candidates** — the small/mid-cap gappers are uncached. The **≥40-date floor
cannot be met (11 « 40)**, so a replay now would be `insufficient_sample` by construction. → **Verdict =
pending forward accrual** (~1 gappers file/trading day → ≥40 dates ≈ September); mirrors SCAN-001's own
forward-validation gate. **Interim deliverable SHIPPED:** the Morning Opportunities Candidate Report
(`scripts/reports/morning_opportunities.py`) renders the daily SCAN candidates as an **ADR-0037-labelled
watchlist (Backtest Pending)** with an **N/40 accrual counter** — user-visible now, no verdict claimed.

## 10. Lifecycle & guardrails

- No paper promotion unless §7 Approved. Paper requires **CEE from day one**, the **Week-3 paper
  protocol**, and the **ADR-0040 minimal metrics** in place (GAPPER uses intraday/market-order execution).
- Stopping rule: one primary design; a revision is **GAPPER-002** (fresh pre-registration), not an edit.

### Decisions (2026-07-08)

1. **Candidate provenance (§3): live-files-only (b)** — PIT reconstruction impractical (no premarket-gapper
   inputs before 2026-06-22).
2. **Verdict metric (§7):** proposed net per-trade edge in bps (date-clustered) + breakeven ≥ 2× cost —
   **to CONFIRM before the replay** (≈ September); moot until the ≥40-date sample gate is met.
3. **Data gate (§9): RAN** → data-gated; **accruing 6/40**. Interim Candidate Report shipped.

*Next checkpoint: when accrual reaches ≥40 dates, confirm the verdict metric and run the CAP-025 replay.
Until then GAPPER-001 stays ACTIVE-accruing; the Candidate Report is the user-visible surface.*
