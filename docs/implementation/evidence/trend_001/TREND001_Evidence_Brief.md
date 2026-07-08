# TREND-001 — Evidence Brief · Multi-Asset Time-Series Trend

**Program:** TREND-001 · **Date:** 2026-07-08 · **Pre-registration:** v1.0 (frozen) ·
**Data:** Yahoo adjusted-close (research) · **Cadence:** monthly, **first trading day** (frozen §6) ·
**Window:** 2007-03 → 2026-07 (**233 monthly rebalances, 19.3 yrs**) ·
**Reproduce:** `trend_001_backtest.py` (seed 20260708) → `trend_001_result.json`.

## Status: **Completed · Power-Limited · Inconclusive** — secondary: **Diversifier Candidate**

**Not promoted to paper.** This is **not** a clean rejection (unlike RNG-001, which was a true "no").
The pre-registered gates did not clear, but the failure is one of **statistical power**, not of the
hypothesis — the pre-registration itself (§9) requires a power failure to be labelled as such rather
than counted as an ordinary rejection.

The point estimates are **directionally favorable and economically meaningful, but statistically
unresolved** over the available window.

## The numbers (primary design vs the pre-registered benchmark)

| Metric | **TREND-001** | Equal-weight buy-hold | SPY (ref) |
|---|---|---|---|
| CAGR | 7.6% | 7.5% | 10.8% |
| Volatility | **8.0%** | 10.6% | 17.3% |
| Sharpe | **0.79** | 0.61 | 0.61 |
| **Max drawdown** | **−11.3%** | −30.5% | −52.9% |
| Calmar | **0.67** | 0.25 | 0.21 |

**The story is drawdown control:** −11.3% worst drawdown vs −30.5% (benchmark) / −52.9% (SPY) — a
**62.9% relative MaxDD reduction** at ~¾ the benchmark's volatility.

## Why it does not clear the bar (all thresholds frozen before the run)

| Path | Test | Result |
|---|---|---|
| **Approved** | ΔSharpe CI excludes 0 | ΔSharpe **+0.18**, CI **[−0.34, +0.71]** → spans 0 ❌ |
| **Power** | observed ΔSharpe ≥ MDE₉₅ | **0.18 < 0.52** → **under-powered** ❌ |
| **Diversifier** | MaxDD-reduction ≥25% **AND** ΔCalmar CI excludes 0 | 62.9% ✓ **but** ΔCalmar +0.43, CI [−0.39, +1.09] spans 0 ❌ |

Trend's payoff is concentrated in a few crisis windows (2008, 2020, 2022), which widens the
block-bootstrap ΔSharpe distribution: the minimum detectable ΔSharpe over this sample (**0.52**) is
larger than the observed effect (**0.18**). This is the pre-registered power limitation, realized.

*Cadence note (correction folded in): the frozen §6 rule is first-trading-day monthly; an earlier draft
ran last-trading-day. Rerun on the frozen cadence — the result is directionally identical (Sharpe 0.79
vs 0.83; MaxDD −11.3% vs −10.0%; ΔSharpe +0.18 vs +0.20), so the mismatch did not change the
conclusion.*

## Robustness — the direction is consistent across every pre-registered sensitivity

| Variant | ΔSharpe vs benchmark |
|---|---|
| **Primary** | **+0.18** |
| MA-only | +0.18 |
| TR-only | +0.07 |
| 12m no-skip | +0.18 |
| zero-yield cash | +0.17 |
| **2× costs** | +0.15 |
| ex-UUP | +0.20 |
| ex-DBC | +0.14 |

All seven give a **positive** ΔSharpe. Survives 2× costs (only **−0.25 pp** CAGR). The edge persists
ex-UUP / ex-DBC, so it is not merely a short on the dollar/commodities.

## Same-window comparison vs off-the-shelf trend ETFs (correction #5)

On each trend ETF's **own overlap window** (apples-to-apples):

| Overlap window | TREND-001 Sharpe / MaxDD | ETF Sharpe / MaxDD |
|---|---|---|
| **DBMF** 2019-07 → 2026-07 (85 mo) | **0.94** / **−5.6%** | 0.56 / −17.3% |
| **KMLM** 2021-02 → 2026-07 (66 mo) | **0.73** / **−5.6%** | 0.17 / −24.8% |

TREND-001's own construction **beats both managed-futures/trend ETFs** on their own windows — so "just
buy the trend ETF" is not the better answer here. (Short windows; directional, not CI-gated.)

## Usability / capacity (correction #4 — fully populated)

| Field | Value |
|---|---|
| Avg active ETF positions | **5.5** (median 6 of 10) |
| Avg cash allocation | 2.3% (spikes to ~100% only in broad crises — the source of the drawdown control) |
| Annual turnover | ~468% |
| Worst single month | −9.2% |
| Cost drag at 2× costs | −0.25 pp CAGR |
| Capacity | effectively unbounded for an individual (≤10 mega-cap ETFs, monthly, low churn) |
| **Suggested role** | **defensive / all-weather sleeve — NOT a core return engine** (gives up upside vs SPY: 7.6% vs 10.8% CAGR) |

## Disposition & next steps

1. **Hold TREND-001 as a Power-Limited Diversifier Candidate** — no paper promotion; it nearly clears
   the Diversifier concept economically (huge drawdown reduction, positive ΔCalmar point) but not the CI
   requirement.
2. **Publish this brief** (Sprint Success is met: a complete, reproducible, pre-registered evidence
   package with an honest verdict).
3. **Open TREND-002 — Long-History Core Trend** (new pre-registration, not an edit): core universe
   SPY/QQQ/IWM/EFA/TLT/IEF back to ~2002 for more crises and higher power; EEM/GLD/DBC as
   pre-declared sensitivity additions (do not optimize the universe after seeing results).

**Bottom line:** TREND-001 is not a trade yet, but it is a credible signal that multi-asset trend may be
valuable as a **defensive/all-weather sleeve**. TREND-002 is the right next test.
