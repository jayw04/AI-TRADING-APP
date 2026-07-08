# TradingWorkbench — Strategy Production Sprint Plan (v0.1)

**Date:** 2026-07-08 · **Owner:** Jay Wang · **Status:** DRAFT — for review before implementation.
**Source:** owner strategy review (`docs/implementation/comments.md`, 2026-07-08).

> **The shift.** The framework is now mature — governance, risk gates (through ADR-0040), Continuous
> Evidence, the Research Registry, Factor Lab, and a *validated* Discovery capability (SCAN-001). The
> next few weeks move from *"build more infrastructure/governance"* to *"use the mature framework to
> produce a small number of tradeable, user-visible strategy candidates."*
>
> **The one distinction that governs everything below:** the goal is **not** to chase profitable
> strategies by relaxing the evidence standard. It is to find **2–3 evidence-backed candidates** that
> help a user's investment decisions. Every program here runs the *unchanged* discipline:
> pre-registration → evidence package → a verdict whose CI excludes zero → stopping rule → (if it
> passes) a small paper book under Continuous Evidence from day one. **A clean rejection is a success.**

---

## Guardrails (non-negotiable, carried from the current platform)

- **Evidence standard unchanged** — pre-registration, "Validated" = a CI that excludes zero, the
  stopping rule (no looping on parameters), reproducible/survivorship-free/cost-aware.
- **No more broad EAD/Quiver dataset hunting** — the Dataset Triage gate stays in force (four hard
  vetoes: PIT clarity · distinct mechanism · license path · ≥100 benchmarked). *Public
  corporate-disclosure events carry no residual alpha* is now a stopping rule, not a to-do.
- **Insider / Congress / Lobby / GovContract stay reference-only** — displayable as context, never in
  ranking, sizing, or the order path (`rejected_reference_only`).
- **Reuse the platform, don't rebuild it** — each program leans on existing capabilities (Factor Lab
  `run_program`, PORT-001 ERC + vol-target overlay, SCAN-001 Candidate Engine, CAP-025 intraday
  replay, the bootstrap/Evidence-Package engines). New code is the exception, not the default.

---

## Week 0 — Operational readiness (a gate *before* strategy sprinting)

The framework is mature, but strategy work depends on trustworthy **live data + risk gates**. Do not
start strategy studies until these close (owner: "do not skip this").

| # | Item | Definition of done | Status today |
|---|---|---|---|
| 0.1 | **CEE deploy + schedule** | `scripts/reports/` synced into the backend image; systemd timer (like `daily-report`); **SNS alert on INVESTIGATE**; link in the daily report | Report runs on-demand; not automated |
| 0.2 | **Monday fresh-store proof** | Confirm the four factor books RANK (not HOLD) on the 07-06→07-07 fresh store at the Mon 10:00 ET rebalance | Pending Monday |
| 0.3 | **ADR-0040 monitoring** | Emit `market_order_unpriced_count`, `bar_cache_miss_count`, `reference_price_missing_count`; decide real-money fail-closed policy (paper fail-open is fine) | ADR-0040 merged/deploying; metrics not yet added |
| 0.4 | **Total-return pricing** | Enable PORT-001 #3 in **report-only** mode | Built, default-OFF, not started |
| 0.5 | **Registry reconcile (doc-only, non-blocking)** | Capability count 23 → **25** (CAP-024 PIT Security Master, CAP-025 Intraday Replay) + note ADR-0040 | Folded in the v0.18 registry draft (PR #386); confirm merged |

*0.1–0.4 are the load-bearing controls; 0.5 is housekeeping that must not block strategy work.*

---

## Week 1 — TREND-001 · Time-Series Trend Following (the first new strategy)

The most important **missing core strategy class**. The registry already lists TREND-001 as *planned*
and **explicitly distinct** from the rejected TV-001-Supertrend import — that framing is correct and
kept. This is **time-series / absolute momentum**, *not* another cross-sectional momentum variant.
Academic support is stronger here than for any alt-dataset (time-series momentum documented across
equity-index, FX, commodity, and bond futures; 1–12-month persistence, longer-horizon reversal).

**Primary hypothesis (pre-registered):** *assets with positive medium-term own-trend outperform
cash/risk-free (or benchmark) after volatility targeting and costs.*

**Design**
- **Universe:** a liquid ETF set — SPY, QQQ, IWM, DIA, TLT, GLD, DBC, UUP, KMLM (or similar).
- **Signals:** 12-1-month return > 0; price > 200-day MA; optional 3/6/12-month ensemble trend score.
- **Portfolio:** long-only, **vol-targeted**, risk-budgeted across assets, **cash when trend is
  negative**, monthly (or weekly) rebalance.
- **Reuse:** Factor Lab `run_program` + PORT-001 ERC/risk-budget engine + the vol-target overlay +
  circular-block bootstrap (CAP-003) + Evidence Package (CAP-002).

**Approval gates (pre-registered):** Sharpe **and** Calmar improvement vs benchmark · max-drawdown
reduction · bootstrap CI **excludes zero** for the primary excess-return or risk-adjusted metric ·
robust across ETF-only **and** equity-index subsets · survives cost/slippage.

**Deliverable:** TREND-001 pre-registration + backtest Evidence Package → a verdict: **one robust
trend sleeve, or a clean rejection.**

**Data dependency to resolve first:** daily bars for the full ETF universe. SPY/QQQ/IWM/DIA are in the
bar cache; **TLT/GLD/DBC/UUP/KMLM must be confirmed** (Sharadar SFP ETF prices are *not* licensed — use
Alpaca/Yahoo daily). A short data-availability check precedes the pre-registration.

---

## Week 2 — GAPPER-001 · Gap + RVOL Opening Continuation (the second)

Turns our **best internal resource** — the *validated* SCAN-001 Candidate Engine (Gap + RVOL, ATR-
decoupled Discovery Confidence) — into a candidate **trade** strategy, not just a report. Users grasp
"top morning opportunities" far more easily than portfolio factor math, so this is the most
**user-visible** candidate.

> **Not a Range Trader revival.** RNG-001 is archived (OR-fade has no edge). GAPPER-001 is a *new*
> hypothesis: **continuation**, not fade.

**Primary hypothesis (pre-registered):** *high-quality gap/RVOL candidates that hold above VWAP or the
opening-range high after the first 15–30 minutes continue — intraday or over the next 1–5 trading
days.*

**Design**
- **Candidate source:** SCAN-001 / Candidate Engine — Gap %, RVOL, ATR-normalized move, Discovery
  Confidence, liquidity/spread filters.
- **Entry variants:** (A) after the first 15-min high break · (B) after the 30-min opening-range break
  · (C) only if price holds VWAP · (D) only if market/sector is also positive.
- **Exit variants:** same-day close · 1-day · 3-day · 5-day hold · ATR / trailing stop.
- **Critical — use CAP-025 Intraday Replay & Entry-Funnel Diagnostics** so we do **not** repeat the
  daily-OHLC mistake that produced a false positive in RNG-001. Required metrics: post-activation fill
  rate · target-after-entry vs stop-after-entry · day-level P&L (idle capital = 0) · **date-clustered
  bootstrap** over a train/test split · slippage sensitivity · spread/liquidity capacity.

**Deliverable:** GAPPER-001 intraday-replay + opening-continuation Evidence Package → verdict.

**Data dependency to resolve first:** intraday bars for gapper candidates + the **gappers files**
(claude-trading-view) that SCAN-001 consumes — confirm they're present/fresh on the box.

---

## Week 3 — Choose paper candidates

Based on the Week 1–2 verdicts:
- **TREND-001 passes** → add a trend sleeve/book to paper.
- **GAPPER-001 passes** → add a small opportunistic paper book.
- **Both fail** → pivot to **LOW-002** (defensive sleeve) / a portfolio blend from existing diversifier
  evidence.
- Every promoted book runs **Continuous Evidence from day one** (Research Envelope + Evidence Clock).

**Target user-facing lineup (the "complete investment tool"):**
| Slot | Program(s) |
|---|---|
| Core | Momentum (live) / **Trend** |
| Defensive | Low-vol / Sector / Combined |
| Opportunistic | **Gapper** / Discovery candidates |
| Reference-only context | Insider · Congress · Lobby · Gov-contracts |

---

## Deferred / reserved (do NOT start without a trigger)

- **INSIDER-002 — Insider-Confirmed Momentum / Microcap Confirmation.** A *new* hypothesis (insider
  buying is not standalone alpha, but may improve *selection* combined with price momentum + liquidity
  expansion + post-disclosure confirmation). Comes **after** TREND-001 and GAPPER-001; insider stays
  reference-only until this passes a fresh pre-registered test. External evidence supports caution
  (Form-4 abnormal returns weaken/negative once realistic tradable dollar sizes are imposed).
- **No new Quiver datasets.** "We have a dataset" is not a reason to run a study.

---

## Open questions for our review (before I start)

1. **Sequencing:** confirm Week 0 (CEE + Monday proof + ADR-0040 metrics) fully gates Week 1 — or may
   TREND-001 pre-registration/backtest run in parallel with Week 0 ops (they use different subsystems)?
2. **TREND-001 universe:** lock the exact ETF list + rebalance cadence (monthly vs weekly) + benchmark
   (SPY? 60/40?) before pre-registration.
3. **Data:** who confirms TLT/GLD/DBC/UUP/KMLM daily coverage and the gappers-file freshness — should a
   data-availability check be Week-0 item 0.6?
4. **ADR-0040 metrics (0.3):** ship as part of Week 0, or fold into the ADR-0040 PR follow-up?
5. **Scope of "user-visible":** does GAPPER-001 need a UI surface (a "morning opportunities" view) in
   the sprint, or is the Evidence Package enough for now?

## What this sprint is explicitly NOT

- Not relaxing the evidence standard · not chasing 10 ideas · not reviving Range fade logic · not using
  insider as direct alpha · not another governance artifact.

*The next proof is not another document. It is: can the app produce a small set of evidence-backed,
guarded strategies a user can actually use — with realistic expectations?*
