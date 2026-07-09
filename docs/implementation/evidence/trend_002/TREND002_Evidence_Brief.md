# TREND-002 — Evidence Brief · Long-History Core Trend

**Program:** TREND-002 · **Date:** 2026-07-08 · **Pre-registration:** v1.0 (frozen) ·
**Data:** Yahoo adjusted-close (research) · **Cash proxy:** SHY (2002+) · **Cadence:** monthly, first
trading day · **Window:** 2002-07 → 2026-07 (**289 monthly rebalances, 24.0 yrs**) ·
**Reproduce:** `trend_002_backtest.py` (seed 20260708) → `trend_002_result.json`.

## Status: **Completed · Power-Limited · Inconclusive** — secondary: **Diversifier Candidate**

TREND-002 was built to attack TREND-001's weakness (statistical power) with a longer, cleaner
equity+bond core. **It did not resolve it** — and it surfaced a second, useful finding: on the core-6
alone the trend edge is *thinner* than on the wider universe. **No paper promotion.**

## The numbers (core-6 primary vs the pre-registered benchmark)

| Metric | **TREND-002** | Equal-weight core-6 | SPY (ref) |
|---|---|---|---|
| CAGR | 7.1% | 8.6% | 10.5% |
| Volatility | **8.8%** | 11.9% | 16.2% |
| Sharpe | **0.61** | 0.59 | 0.58 |
| **Max drawdown** | **−17.2%** | −34.7% | −52.9% |
| Calmar | **0.42** | 0.25 | 0.20 |

Still meaningful **drawdown control** (−17.2% vs −34.7%, a **50.4% relative reduction**), but the
Sharpe improvement is now marginal.

## Why it does not clear the bar

| Path | Test | Result |
|---|---|---|
| **Approved** | ΔSharpe CI excludes 0 | ΔSharpe **+0.02**, CI **[−0.40, +0.46]** → spans 0 ❌ |
| **Power** | observed ΔSharpe ≥ MDE₉₅ | **0.02 < 0.43** → **under-powered** ❌ |
| **Diversifier** | MaxDD-reduction ≥25% **AND** ΔCalmar CI excludes 0 | 50.4% ✓ **but** ΔCalmar +0.17, CI [−0.33, +0.60] spans 0 ❌ |

## The key finding: the trend benefit is stronger in the *wider* universe

TREND-002's core-6 ΔSharpe (**+0.02**) is far below TREND-001's 10-ETF ΔSharpe (**+0.18**). Longer
history did not add power — and narrowing to equity+bond actually **shrank the edge**. The
pre-registered universe-expansion sensitivities are directionally consistent:

| Universe (add-back) | ΔSharpe vs its benchmark |
|---|---|
| core-6 (primary) | +0.02 |
| + EEM | +0.06 |
| + GLD | +0.05 |
| + DBC | +0.10 |
| **+ EEM + GLD + DBC (all 3)** | **+0.16** |

Adding the diversifier sleeves (EM, gold, commodities) back recovers most of TREND-001's edge → **the
observed trend benefit is stronger in the wider universe, especially when the commodity/gold/EM sleeves
are included**. The direction is clear, but it remains **not statistically promotable** — so this is a
directional read, not a claim that the edge "lives" only there.

> **Staggered-inception caveat.** EEM (2003) / GLD (2004) / DBC (2006) start *after* the 2002 core-6
> window, so each add-back is an **available-as-of** sensitivity (the add-back asset simply isn't held
> until it exists; its benchmark starts at the common date too). The direction is robust across the
> add-backs, but the windows differ slightly — this is a sensitivity signal, not a like-for-like
> re-run. A clean common-start re-run would be part of any future TREND-003, not this brief.

## Cash-leg attribution (owner-required transparency)

The verdict is **not** an artifact of the SHY cash proxy:

| Field | Value |
|---|---|
| Avg cash weight | 12.5% |
| Cash-proxy CAGR contribution (SHY vs zero) | +0.13 pp |
| Worst SHY month | −1.8% (the documented short-Treasury duration risk — the 2022 rate shock) |
| **Verdict under SHY / BIL / zero** | **Inconclusive / Inconclusive / Inconclusive** → **does not depend on the proxy** |
| BIL-overlap (2007-07→2026-07) | SHY Sharpe 0.57 / MaxDD −17.2% vs BIL 0.64 / −13.9% |

The SHY caveat is visible (BIL, a purer T-bill proxy, is modestly better over the post-2007 overlap
because SHY took a 2022 duration hit) — but it is **immaterial to the verdict**, which is Inconclusive
under all three cash regimes.

## Cross-program conclusion (TREND-001 + TREND-002)

Two pre-registered tests, two honest **Power-Limited · Inconclusive** verdicts, one consistent picture:

- **Multi-asset time-series trend is a drawdown-control / defensive tool**, not a Sharpe-maximizer. It
  cuts drawdowns 50–63% at the cost of ~1–1.5 pp of CAGR.
- Its Sharpe edge is **directionally favorable but statistically unresolvable** even over 24 years — the
  payoff is crisis-concentrated, so the CIs stay wide.
- The edge is **concentrated in the wider universe** (commodities/gold/EM/FX), so the **TREND-001 (10-ETF)
  form is the better expression** than the core-6.

## Disposition

- **Hold both TREND-001 and TREND-002 as Power-Limited Diversifier Candidates** — no paper promotion
  (the frozen gates did not clear).
- If a defensive trend sleeve is ever pursued, use the **wide-universe (TREND-001) form**, positioned as
  defensive/all-weather with managed expectations, and revisit as forward/live data accrues.
- **Stopping rule:** do not spawn further universe/parameter variants chasing significance — the two
  pre-registered tests have characterized the effect. Any genuinely new hypothesis would be TREND-003
  with a fresh pre-registration.
