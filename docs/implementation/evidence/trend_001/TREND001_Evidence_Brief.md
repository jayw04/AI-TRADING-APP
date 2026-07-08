# TREND-001 — Evidence Brief · Multi-Asset Time-Series Trend

**Program:** TREND-001 · **Date:** 2026-07-08 · **Pre-registration:** v1.0 (frozen) ·
**Data:** Yahoo adjusted-close (research) · **Window:** 2008-05 → 2026-07 (**219 monthly rebalances,
18.3 yrs**) · **Reproduce:** `trend_001_backtest.py` (seed 20260708) → `trend_001_result.json`.

## Verdict: **Rejected — POWER-LIMITED (inconclusive), not evidence of no effect**

TREND-001's point estimates are **strong and robust** — but the edge is concentrated in crises, so
even 18 years cannot resolve it from zero at the 95% bar. This is **not** an RNG-001-style clean
rejection (where there was no edge); it is *"the edge is real in direction and magnitude but
statistically unresolvable."* Per the frozen §10 thresholds neither the Approved nor the Diversifier
path clears, and per §9 a rejection that is a power failure must be **labelled as such**.

## The numbers (primary design vs the pre-registered benchmark)

| Metric | **TREND-001** | Equal-weight buy-hold | SPY |
|---|---|---|---|
| CAGR | 7.5% | 7.1% | 11.7% |
| Volatility | **7.6%** | 9.8% | 16.1% |
| **Sharpe** | **0.83** | 0.62 | 0.71 |
| **Max drawdown** | **−10.0%** | −29.3% | −46.3% |
| Calmar | **0.75** | 0.24 | 0.48 |

**The headline is drawdown control:** −10% worst drawdown vs −29% (benchmark) / −46% (SPY) — a **65.9%
relative MaxDD reduction**, at ~⅔ the volatility. That is exactly the crisis-convexity claim
time-series trend actually makes.

## Why it doesn't clear the bar (all thresholds frozen before the run)

| Path | Test | Result |
|---|---|---|
| **Approved** | ΔSharpe CI excludes 0 | ΔSharpe **+0.204**, CI **[−0.37, +0.77]** → spans 0 ❌ |
| **Power** | observed ΔSharpe ≥ MDE₉₅ | **0.204 < 0.584** → **under-powered** ❌ |
| **Diversifier** | MaxDD-reduction ≥25% **AND** ΔCalmar CI excludes 0 | 65.9% ✓ **but** ΔCalmar +0.508, CI [−0.47, +1.04] spans 0 ❌ |

The minimum detectable ΔSharpe over this sample (0.58) is **larger than the observed effect** (0.20):
trend's payoff is concentrated in a few crisis windows (2008, 2020, 2022), which makes the block-
bootstrap ΔSharpe distribution wide — more years did *not* shrink it (SE 0.27→0.30 from 151→219 mo).
This is the pre-registered power limitation, realized.

## Robustness — the direction is consistent everywhere

All seven pre-registered sensitivities give a **positive** ΔSharpe and materially lower drawdown than
the benchmark — the result is not an artifact of one knob:

| Variant | Sharpe | ΔSharpe | MaxDD |
|---|---|---|---|
| **Primary** | 0.83 | +0.20 | −10.0% |
| MA-only | 0.86 | +0.24 | −8.0% |
| TR-only | 0.73 | +0.11 | −10.7% |
| 12m no-skip | 0.80 | +0.17 | −12.2% |
| zero-yield cash | 0.82 | +0.19 | −10.0% |
| **2× costs** | 0.79 | +0.17 | −10.1% |
| ex-UUP | 0.80 | +0.22 | −12.9% |
| ex-DBC | 0.89 | +0.20 | −10.0% |

- **Survives costs:** doubling costs to 10 bps/side costs only **−0.27 pp** of CAGR.
- **Not just "avoided the laggards":** dropping UUP and DBC (the perennial decliners) *keeps* the edge
  (ΔSharpe +0.22 / +0.20) — so it isn't merely a short on the dollar/commodities.

## Secondary (descriptive — different, short windows; NOT CI-gated)

Off-the-shelf managed-futures/trend ETFs over their overlap: **DBMF** Sharpe 0.60 (86 mo), **KMLM**
Sharpe 0.20 (67 mo). TREND-001's own construction is competitive-to-better — so "just buy the trend
ETF" is not clearly the superior answer — but the windows differ and the overlap is short, so this is
directional only.

## Usability / capacity

Low-vol (~7.6%), low-drawdown (−10%) profile → **suitability = defensive / all-weather sleeve**, not a
return-maximizer (it gives up upside vs SPY: 7.5% vs 11.7% CAGR). Long-only, ≤10 liquid mega-ETFs →
**capacity is effectively unbounded** for an individual investor; monthly rebalance → low turnover;
meaningful cash allocation in downtrends (the source of the drawdown control). Cost-insensitive.

## Recommendation (owner decision — no auto-promotion)

Under the frozen rule TREND-001 is **not promoted to paper** (we do not promote on unresolved CIs — the
discipline holds). But this is a *power-limited* result with a strong, robust drawdown-control signal,
so the honest options are:

1. **TREND-002 (new pre-registration) — extend the history.** The binding constraint is UUP (2007). An
   equity+bond-core universe (e.g. SPY/QQQ/IWM/TLT/IEF, back to ~2002) or dropping the youngest ETFs
   buys more crises and more power. Per the revision=new-ID rule this is **TREND-002**, not an edit.
2. **Hold as a documented power-limited Diversifier candidate** — revisit when forward/live data
   accumulates (it *nearly* clears the Diversifier path: MaxDD ✓, ΔCalmar point +0.51 but CI spans 0).
3. **Publish the brief as-is** (Sprint Success): "we tested multi-asset trend; it shows strong drawdown
   control but is statistically unresolvable over the available window — here is the evidence."

The sprint's own success metric is met either way: a complete, reproducible, pre-registered evidence
package with an honest verdict.
