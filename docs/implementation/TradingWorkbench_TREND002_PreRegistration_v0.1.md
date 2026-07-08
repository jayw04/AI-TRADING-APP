# TREND-002 — Pre-Registration v1.0 · Long-History Core Trend

**Date:** 2026-07-08 · **Owner:** Jay Wang · **Program ID:** TREND-002 · **Registry:** Planning →
**Running** (on freeze) · **Authority:** Strategy Production Sprint Plan v0.4 + TREND-001 disposition.
**Status:** ✅ **FROZEN v1.0 (2026-07-08).** Cash proxy = **SHY** confirmed by the owner (BIL-overlap +
zero-yield as sensitivities). This is a **new program**, not an edit of TREND-001 (the stopping rule has
no back door). No paper promotion unless the pre-registered Approved or Diversifier gates clear.

> **Why TREND-002.** TREND-001 (10-ETF, 2007-03→2026-07, 233 mo) was **Power-Limited · Inconclusive ·
> Diversifier Candidate**: favorable, robust point estimates (62.9% MaxDD reduction, ΔSharpe +0.18) that
> the sample could not resolve (MDE 0.52 > observed 0.18) because the youngest ETFs (UUP 2007, DBC 2006)
> bind the start date. TREND-002 tests the **same frozen design on a longer, higher-power window** by
> using a **core equity + bond universe** that reaches back to ~2002 — more crises (2002 bottom, full
> 2007-08 lead-in), more observations.

## Inherited (frozen, identical to TREND-001 — see `TradingWorkbench_TREND001_PreRegistration_v0.1.md`)

Signal boolean (`TR_12m_skip1 > 0 AND price > MA200`, monthly first-trading-day) · portfolio (long-only,
inverse-vol risk budget, vol-target 10% / 63-day, cap 1.0 = de-risk to cash) · costs 5 bps/side ·
verdict framework (three-way Approved / Diversifier / Rejected, block-bootstrap length 6, Diversifier =
rel-MaxDD ≥25% AND ΔCalmar CI excludes 0) · **power check → MDE run before the verdict** · usability
block · Sprint-Success (an honest verdict ships regardless). Data = Yahoo adjusted-close (research).

## What changes in TREND-002 (the only deltas)

### 1. Universe — Long-History **Core** (equity + bond)

**Primary (6): SPY · QQQ · IWM · EFA · TLT · IEF.** Binding inception = TLT/IEF (2002-07) ⇒ common
window **~2002-08 → present ≈ 288 monthly rebalances** (vs 233 for TREND-001; +2 crisis episodes).

**Pre-declared sensitivity additions (NOT the primary; do NOT re-optimize the universe after seeing
results):** +EEM (from 2003) · +GLD (from 2004) · +DBC (from 2006). Each is a separate sensitivity run;
the **core-6 is the primary** and its verdict is the headline.

### 2. Benchmark

Primary = equal-weight buy-and-hold of the **core-6**, monthly rebalanced (same construction as
TREND-001, new universe). Secondary descriptive = DBMF / KMLM on overlap; tertiary = SPY, 60/40, cash.

### 3. Cash proxy (the one new pre-registered choice — confirm before freeze)

BIL (TREND-001's proxy) only starts 2007-05, so it cannot cover a 2002 window. **Pre-registered choice:
`SHY` (iShares 1–3yr Treasury, inception 2002-07) as the cash-leg total-return proxy for the full
window** (a short-duration Treasury proxy — slightly more duration than pure T-bills, but the only
liquid cash-like series covering 2002+). **BIL (2007+) and zero-yield are sensitivities.**

> **Caveat (documented before freeze):** SHY is used as a long-history cash-like **short-Treasury
> proxy, not a risk-free cash series** — it carries some duration/rate risk (e.g. it can behave worse
> than true T-bills in a year like 2022). The **BIL-overlap and zero-yield sensitivities test whether
> the verdict depends on this proxy.**

### 4. Cash-leg attribution block (evidence-package addition, owner-required)

To keep the SHY choice transparent (so the result can't be attributed to the cash proxy rather than the
trend rule), the TREND-002 evidence package reports: **cash-proxy return contribution** (CAGR delta
SHY-cash vs zero-cash) · **average cash weight** · **worst cash-proxy month** (SHY) · **BIL-overlap
comparison** (SHY vs BIL cash on the post-2007 window) · **zero-yield comparison** · **verdict
dependency on SHY** (does Approved/Diversifier/Inconclusive change under BIL / zero?).

## Data Availability Gate (largely pre-passed from the TREND-001 gate)

All six core ETFs have full Yahoo adjusted-close history (confirmed 2026-07-08): SPY 1993 · QQQ 1999 ·
IWM 2000 · EFA 2001-08 · TLT 2002-07 · IEF 2002-07; sensitivity adds EEM 2003 · GLD 2004 · DBC 2006;
cash proxy SHY 2002-07. Same pre-declared exclusion rule + bond stop-and-review clause as TREND-001. The
gate re-runs (history/gap check + SHY availability) as the first execution step; final universe recorded
in the evidence package.

## Hypothesis & expected read

Same primary hypothesis as TREND-001. **Success test to watch:** does the longer window lower the MDE
below the observed ΔSharpe (i.e., resolve what TREND-001 could not)? If the core-6 clears the ΔSharpe or
Diversifier CI, TREND-002 is a promotable candidate; if it remains power-limited with the same favorable
point estimates, that is itself a strong statement (multi-asset trend's edge is real-in-direction but
genuinely hard to resolve even over 24 years — a defensible "defensive sleeve, manage expectations"
conclusion). Either way the evidence brief ships.

### Confirmed & frozen (owner, 2026-07-08)

1. **Cash proxy = SHY** for the full 2002+ window — **CONFIRMED** (BIL-overlap + zero-yield as
   sensitivities; SHY caveat + cash-leg attribution block added above).

*Frozen v1.0 → Planning → Running. The backtest runs on the seeded, reproducible harness
(`evidence/trend_002/`): core-6 universe + SHY cash + the sensitivity additions (EEM/GLD/DBC) +
BIL-overlap + zero-yield + the cash-leg attribution block. No paper promotion unless a gate clears.*
