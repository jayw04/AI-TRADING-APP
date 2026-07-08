# TradingWorkbench — Strategy Production Sprint Plan (v0.2)

**Date:** 2026-07-08 · **Owner:** Jay Wang · **Status:** For final review — decisions locked per the
owner's answers; **no implementation until v0.2 is confirmed.**
**Source:** owner strategy review + answers to the v0.1 open questions (`docs/implementation/comments.md`, 2026-07-08).
**Changes v0.1 → v0.2:** folded the five locked decisions — Week-0 is a *partial* gate (pre-reg runs in
parallel; execution/paper gated); TREND-001 universe/cadence/benchmark locked; a **Data Availability
Gate** added to Week 0; ADR-0040 **minimal** metrics scoped to Week 0; GAPPER-001 gets a lightweight
**Candidate Report**, not a UI; sequencing revised.

> **The shift.** The framework is mature (governance, risk gates through ADR-0040, Continuous Evidence,
> the Research Registry, Factor Lab, a *validated* SCAN-001). The next weeks move from building
> infrastructure to producing **2–3 evidence-backed, user-visible strategy candidates** — **without
> relaxing the evidence bar.** A clean rejection is still a success. Every program runs the unchanged
> discipline: pre-registration → evidence package → a verdict whose CI excludes zero → stopping rule →
> (if it passes) a small paper book under Continuous Evidence from day one.

---

## Guardrails (non-negotiable)

- **Evidence standard unchanged** — pre-registration, "Validated" = a CI excluding zero, the stopping
  rule, reproducible / survivorship-free / cost-aware.
- **No more broad EAD/Quiver dataset hunting** — the Dataset Triage gate stays in force.
- **Insider / Congress / Lobby / GovContract stay reference-only** (`rejected_reference_only`).
- **Reuse the platform** — Factor Lab `run_program`, PORT-001 ERC + vol-target overlay, SCAN-001,
  CAP-025 intraday replay, the bootstrap/Evidence-Package engines. New code is the exception.

---

## How Week 0 gates the sprint (Q1 — locked)

Week 0 is a **partial** gate, not a full stop:

- **TREND-001 pre-registration runs *in parallel* with Week 0** — it is research design/documentation,
  not live operation.
- **TREND-001 result interpretation / paper deployment is gated** on: factor-store freshness verified ·
  ETF daily-data availability verified · the adjusted/total-return pricing assumption documented · the
  CEE report scheduled *or* at least operationally runnable.
- **GAPPER-001 paper trading is gated** on: SCAN/gapper file freshness **and** the ADR-0040 minimal
  metrics being in place (GAPPER uses intraday/market-order-style execution).

So: **pre-reg in parallel → execute after the data checks → go to paper after the Week-0 controls.**

---

## Week 0 — Operational readiness + scope lock

| # | Item | Definition of done |
|---|---|---|
| 0.1 | **Finalize TREND-001 v0.2 scope** | This doc's TREND-001 section confirmed by the owner (universe, cadence, benchmark, gates) |
| 0.2 | **Data Availability Gate** (see below) | Per-ETF daily-data checks pass or the excluded set is recorded; gappers/SCAN/intraday freshness confirmed |
| 0.3 | **Factor-store freshness / Monday proof** | Confirm the four factor books RANK (not HOLD) on the fresh store at Mon 10:00 ET |
| 0.4 | **CEE deploy + schedule** | `scripts/reports/` in the backend image; systemd timer; **SNS alert on INVESTIGATE** |
| 0.5 | **ADR-0040 minimal metrics** | The four counters below emitted (logging/counters only — full monitoring is a PR follow-up) |
| 0.6 | **Total-return pricing (report-only)** | PORT-001 #3 enabled in report-only mode; the TREND-001 total-return assumption documented |
| 0.7 | **Registry reconcile (doc-only, non-blocking)** | Capability count 23 → **25** (CAP-024/025) + ADR-0040 |

### Data Availability Gate (Q3 — locked; a real Week-0 gate)

**Per ETF, before TREND-001 execution:** daily OHLCV exists · adjusted-close / total-return assumption
is known · data extends through the latest expected trading date · no large unexplained gaps · the
ticker resolves through the factor store.
**Also check:** gappers-file freshness · SCAN candidate-file freshness · intraday-bar availability for
GAPPER-001.
**Pre-declared exclusion rule (so one missing ETF can't kill the study):** *if an ETF lacks sufficient
history before the run, it is excluded before any results are computed, and the final universe is
recorded.* For GAPPER-001, freshness matters more (a morning/intraday candidate).

### ADR-0040 minimal metrics (Q4 — locked)

Week-0 lightweight counters (do **not** block TREND-001 pre-reg on these; **required before GAPPER-001
paper**): `market_order_priced_from_bar_cache_count` · `market_order_reference_price_missing_count` ·
`market_order_bar_cache_miss_count` · `market_order_unpriced_count`. Full monitoring + the real-money
fail-closed decision → the ADR-0040 PR follow-up.

---

## Week 1 — TREND-001 · Multi-Asset Time-Series Trend (locked scope, Q2)

A **multi-asset time-series / absolute-momentum** strategy — explicitly **not** another equity
cross-sectional momentum variant, and distinct from the rejected TV-001-Supertrend import.

**Primary hypothesis (pre-registered):** *assets with positive medium-term own-trend outperform
owning the same assets (and cash) after volatility targeting and costs.*

**Universe (primary, subject to the Data Availability Gate):**
`SPY` (US large-cap) · `QQQ` (Nasdaq/growth) · `IWM` (US small-cap) · `EFA` (developed intl) · `EEM`
(EM) · `TLT` (long Treasury) · `IEF` (intermediate Treasury) · `GLD` (gold) · `DBC` (broad
commodities) · `UUP` (US dollar).
**Sensitivity-only:** `KMLM` (managed-futures proxy) — shorter history, so a modern sensitivity sleeve,
**not** in the core long-history test.

**Signals:** 12-1-month return > 0 · price > 200-day MA · optional 3/6/12-month ensemble trend score.
**Portfolio:** long-only · **vol-targeted** · risk-budgeted across assets · **cash when trend is
negative**. Reuse Factor Lab `run_program` + PORT-001 ERC/risk-budget + the vol-target overlay.
**Cadence (do NOT optimize):** primary **monthly, first trading day of the month**; **weekly** as a
sensitivity only.
**Benchmark:** primary = **equal-weight buy-and-hold of the same ETF universe, monthly rebalanced**
(the clean question: *does the trend rule add value over simply owning the same assets?*). Secondary =
SPY · 60/40 SPY/TLT · a cash/T-bill proxy if available.

**Approval gates (pre-registered):** Sharpe **and** Calmar improvement vs the equal-weight benchmark ·
max-drawdown reduction · bootstrap CI **excludes zero** for the primary excess-return or risk-adjusted
metric · robust across ETF-only and equity-index subsets · survives cost/slippage.

**Deliverable:** pre-registration + backtest Evidence Package → verdict: **a robust trend sleeve, or a
clean rejection.** Week-1 decision: paper candidate, reject, or **revise only if pre-registered.**

---

## Week 2 — GAPPER-001 · Gap + RVOL Opening Continuation

Turns the *validated* SCAN-001 Candidate Engine (Gap + RVOL, ATR-decoupled Discovery Confidence) into a
candidate **trade** strategy — the most **user-visible** candidate. **Not** a Range Trader revival
(RNG-001 archived): this is **continuation**, not fade.

**Primary hypothesis (pre-registered):** *high-quality gap/RVOL candidates that hold above VWAP or the
opening-range high after the first 15–30 minutes continue — intraday or over the next 1–5 days.*

**Candidate source:** SCAN-001 — Gap %, RVOL, ATR-normalized move, Discovery Confidence, liquidity/spread filters.
**Entry variants:** (A) first 15-min high break · (B) 30-min opening-range break · (C) only if price holds VWAP · (D) only if market/sector is positive.
**Exit variants:** same-day close · 1/3/5-day hold · ATR / trailing stop.
**Critical — CAP-025 Intraday Replay & Entry-Funnel Diagnostics** (so we don't repeat RNG-001's
daily-OHLC false positive). Metrics: post-activation fill rate · target-after-entry vs stop-after-entry
· day-level P&L (idle capital = 0) · **date-clustered bootstrap** over a train/test split · slippage
sensitivity · spread/liquidity capacity.

**Deliverable:** intraday-replay + opening-continuation Evidence Package **+ a lightweight Morning
Opportunities Candidate Report** (Q5 — **no full UI in this sprint**). The report is a table (reusing
SCAN-001, not a new front-end): `ticker · gap % · RVOL · Discovery Confidence · entry trigger · VWAP
status · liquidity/spread · result label`.

---

## Week 3 — Promote paper candidates

- **TREND-001 passes** → trend sleeve/book to paper. **GAPPER-001 passes** → small opportunistic paper
  book. **Both fail** → LOW-002 defensive sleeve / portfolio blend.
- Every promoted book runs **Continuous Evidence from day one**.
- **No insider / Quiver event data in ranking/sizing** unless a new *approved* pre-registered hypothesis
  exists (EAD triage + `rejected_reference_only` stay active).

**Target user-facing lineup:** Core = Momentum (live) / **Trend** · Defensive = Low-vol / Sector /
Combined · Opportunistic = **Gapper** / Discovery · Reference-only = Insider · Congress · Lobby ·
Gov-contracts.

---

## Deferred / reserved

- **INSIDER-002 — Insider-Confirmed Momentum / Microcap Confirmation** — a *new* hypothesis (insider
  buying isn't standalone alpha, but may improve *selection* combined with price momentum + liquidity
  expansion + post-disclosure confirmation). **After** TREND-001 and GAPPER-001; insider stays
  reference-only until it passes a fresh pre-registered test. (External evidence: Form-4 abnormal
  returns weaken/go negative once realistic tradable dollar sizes are imposed.)
- **No new Quiver datasets.**

---

## Locked sprint sequencing (owner)

**Week 0** — 1) finalize TREND-001 v0.2 scope · 2) run the ETF Data Availability Gate · 3) confirm
factor-store freshness / Monday rebalance · 4) deploy/schedule the CEE report · 5) add ADR-0040 minimal
metrics · 6) check gappers/SCAN file freshness. *(TREND-001 pre-registration may proceed in parallel.)*
**Week 1** — 1) run TREND-001 · 2) produce the registered evidence package · 3) decide: paper, reject,
or revise-only-if-pre-registered.
**Week 2** — 1) pre-register GAPPER-001 · 2) run the CAP-025-style intraday replay/funnel · 3) produce
the evidence package + Candidate Report.
**Week 3** — 1) promote any passing strategy to a small paper book · 2) attach Continuous Evidence day
one · 3) keep insider/Quiver event data out of ranking/sizing absent a new approved hypothesis.

## What this sprint is explicitly NOT

Not relaxing the evidence standard · not chasing 10 ideas · not reviving Range fade logic · not using
insider as direct alpha · not a full GAPPER UI · not another governance artifact.

---

*Next step: your confirmation of this v0.2. On confirmation, the first concrete action is Week-0 item
0.1–0.2 (freeze the TREND-001 pre-registration in parallel with running the Data Availability Gate) —
no strategy result is interpreted until the gate + freshness checks pass.*
