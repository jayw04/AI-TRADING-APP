# TradingWorkbench — Strategy Production Sprint Plan (v0.3)

**Date:** 2026-07-08 · **Owner:** Jay Wang · **Status:** For final review — folds the v0.2 review edits
(owner: approve after these). **No implementation until v0.3 is confirmed.**
**Source:** owner reviews + answers in `docs/implementation/comments.md` (2026-07-08).
**Changes v0.2 → v0.3:** one **primary** signal/design per strategy (no combination/parameter search);
locked **primary verdict metric** (ΔSharpe); TREND-001 **decoupled** from the PORT-001 total-return
rollout; explicit **liquidity/spread + slippage** gates for GAPPER; **capacity/usability** reporting on
both evidence packages; CEE-from-day-one stated on each program; minor wording fixes.

> **The shift.** Move from building infrastructure to producing **2–3 evidence-backed, user-visible
> strategy candidates** — **without relaxing the evidence bar.** A clean rejection is still a success.
> Each program runs the unchanged discipline: pre-registration → evidence package → verdict → stopping
> rule → (if it passes) a small paper book under Continuous Evidence from day one. **Approval requires a
> confidence interval that excludes zero;** a rejection may occur precisely because the CI spans zero.

---

## Guardrails (non-negotiable)

- **Evidence standard unchanged** — pre-registration, **approval requires a CI excluding zero**, the
  stopping rule (no looping on parameters), reproducible / survivorship-free / cost-aware.
- **No more broad EAD/Quiver dataset hunting** — the Dataset Triage gate stays in force.
- **Insider / Congress / Lobby / GovContract stay reference-only** (`rejected_reference_only`).
- **Reuse the platform** — Factor Lab `run_program`, PORT-001 ERC + vol-target overlay, SCAN-001,
  CAP-025 intraday replay, the bootstrap/Evidence-Package engines.
- **One primary rule per program** — a single pre-registered primary design; everything else is a
  *sensitivity test*, never a candidate strategy. No signal-combination or parameter search.

---

## How Week 0 gates the sprint (partial gate)

- **TREND-001 pre-registration runs *in parallel* with Week 0** — it is research design, not live ops.
- **TREND-001 result interpretation** is gated on: factor-store freshness verified · ETF daily-data
  availability verified (Data Availability Gate) · the TREND-001 **pricing basis documented**.
- **GAPPER-001 paper trading** is gated on: SCAN/gapper freshness **and** the ADR-0040 minimal metrics.
- **Any paper deployment** is gated on: CEE report scheduled *or* operationally runnable.

Flow: **pre-reg in parallel → execute after the data checks → go to paper after the Week-0 controls.**

---

## Week 0 — Operational readiness + scope lock

| # | Item | Definition of done |
|---|---|---|
| 0.1 | **Finalize TREND-001 v0.3 scope** | Owner-confirmed (universe, single primary signal, cadence, benchmark, verdict metric) |
| 0.2 | **Data Availability Gate** (below) | Per-ETF daily-data checks pass or the excluded set is recorded; gappers/SCAN/intraday freshness confirmed |
| 0.3 | **Factor-store freshness / Monday proof** | Four factor books RANK (not HOLD) on the fresh store at Mon 10:00 ET |
| 0.4 | **CEE deploy + schedule** | `scripts/reports/` in the backend image; systemd timer; **SNS alert on INVESTIGATE** |
| 0.5 | **ADR-0040 minimal metrics** | The four counters below (logging/counters only — full monitoring is a PR follow-up) |
| 0.6 | **Total-return pricing (report-only) — decoupled from TREND-001** | PORT-001 #3 in report-only mode. **Does NOT block TREND-001 research** unless TREND-001 requires the same data source; TREND-001 instead **documents its own pricing basis** (adjusted-close / total-return / close-only) |
| 0.7 | **Registry reconcile (doc-only, non-blocking)** | Capability count 23 → **25** (CAP-024/025) + ADR-0040 |

**Data Availability Gate.** Per ETF, before TREND-001 execution: daily OHLCV exists · adjusted-close /
total-return assumption known · data extends through the latest expected trading date · no large
unexplained gaps · ticker resolves through the factor store. Also: gappers-file freshness · SCAN
candidate-file freshness · intraday-bar availability for GAPPER-001. **Pre-declared exclusion rule:** an
ETF lacking sufficient history is excluded *before* any results are computed, and the final universe is
recorded.

**ADR-0040 minimal metrics (Week 0; do not block TREND-001 pre-reg; required before GAPPER paper):**
`market_order_priced_from_bar_cache_count` · `market_order_reference_price_missing_count` ·
`market_order_bar_cache_miss_count` · `market_order_unpriced_count`. Full monitoring + the real-money
fail-closed decision → the ADR-0040 PR follow-up.

---

## Week 1 — TREND-001 · Multi-Asset Time-Series Trend

Multi-asset time-series / absolute-momentum — **not** an equity cross-sectional momentum variant, and
distinct from the rejected TV-001-Supertrend.

**Primary hypothesis (pre-registered):** *assets with a positive medium-term own-trend outperform
owning the same assets (and cash) after volatility targeting and costs.*

**Universe (primary, subject to the Data Availability Gate):** SPY · QQQ · IWM · EFA · EEM · TLT · IEF ·
GLD · DBC · UUP. **Sensitivity-only:** KMLM (shorter history — modern sensitivity sleeve, not the core
long-history test).

**Signal (locked — one primary, the rest are sensitivity):**
- **Primary signal:** **12-1-month total return > 0.**
- **Risk filter / confirmation:** price > 200-day MA.
- **Sensitivity (not the primary rule):** 3/6/12-month ensemble trend score. *TREND-001 is not a
  signal-combination search.*

**Portfolio:** long-only · **vol-targeted** · risk-budgeted across assets · **cash when the trend is
negative** (the cash leg earns a **declared risk-free proxy** — pre-register which: a T-bill/BIL proxy,
zero, or broker cash yield; a T-bill proxy is preferred for realism). Reuse Factor Lab `run_program` +
PORT-001 ERC/risk-budget + the vol-target overlay.

**Cadence (do NOT optimize):** primary **monthly, first trading day**; **weekly** as sensitivity only.

**Benchmark:** primary = **equal-weight buy-and-hold of the same ETF universe, monthly rebalanced**
(*does the trend rule add value over simply owning the same assets?*). Secondary = SPY · 60/40 SPY/TLT
· a cash/T-bill proxy.

**Backtest period (after the Data Availability Gate):** the **longest common history across the primary
ETFs**; the modern full universe (incl. KMLM) as a **sensitivity**.

**Verdict (locked):**
- **Primary verdict metric: ΔSharpe vs the equal-weight same-universe benchmark — approval requires the
  bootstrap CI on ΔSharpe to exclude zero.**
- **Guardrails:** ΔCalmar > 0 · MaxDD reduction > 0 · CAGR drag not excessive · robust across ETF-only
  and equity-index subsets · survives cost/slippage.

**Deliverable:** pre-registration + backtest Evidence Package (incl. the **usability/capacity block**
below). Week-1 decision: paper candidate, reject, or **revise only if pre-registered.** **Paper
deployment requires CEE attached from day one.**

---

## Week 2 — GAPPER-001 · Gap + RVOL Opening Continuation

Turns the *validated* SCAN-001 Candidate Engine into a candidate **trade** strategy — the most
user-visible candidate. **Not** a Range Trader revival: **continuation**, not fade.

**Primary hypothesis (pre-registered):** *high-quality gap/RVOL candidates that hold above VWAP / the
opening-range high after the first 30 minutes continue — intraday.*

**Primary design (locked — one design; the rest are sensitivity):**
SCAN-001 candidate → **enter on the 30-min opening-range high break** → **require price above VWAP** →
**require market/sector positive** → **exit at same-day close**.
**Sensitivity:** 15-min high break · 1/3/5-day hold · ATR trailing stop · VWAP-only filter. *GAPPER-001
is not a parameter search.*

**Liquidity / spread gates (execution realism — required in the evidence package):** minimum dollar
volume · maximum spread · minimum price · **no hard-to-trade microcaps unless specifically
pre-registered** · slippage sensitivity at **5 / 10 / 25 bps**. *A paper edge in thin names is useless
to users if it can't be executed.*

**Method — CAP-025 Intraday Replay & Entry-Funnel Diagnostics** (avoids RNG-001's daily-OHLC false
positive): post-activation fill rate · target-after-entry vs stop-after-entry · day-level P&L (idle
capital = 0) · **date-clustered bootstrap** over a train/test split · slippage sensitivity ·
spread/liquidity capacity.

**Deliverable:** intraday-replay + opening-continuation Evidence Package **+ a lightweight Morning
Opportunities Candidate Report** (no full UI this sprint): a table reusing SCAN-001 — `ticker · gap % ·
RVOL · Discovery Confidence · entry trigger · VWAP status · liquidity/spread · result label`. **Paper
deployment requires CEE attached from day one.**

---

## Usability / capacity block (both TREND-001 and GAPPER-001 evidence packages)

To keep the output aimed at *user investment usefulness*, each evidence package reports: **suggested
account-size range · expected turnover · average number of positions · capacity estimate · worst
historical drawdown · expected cash usage · user suitability (core / defensive / opportunistic).**

---

## Week 3 — Promote paper candidates

- **TREND-001 passes** → trend sleeve/book to paper. **GAPPER-001 passes** → small opportunistic paper
  book. Every promoted book runs **Continuous Evidence from day one**.
- **If both fail** → prioritize **LOW-002** (defensive sleeve / portfolio blend) **only after a short
  postmortem confirms no reusable strategy candidate emerged.**
- **No insider / Quiver event data in ranking/sizing** unless a new *approved* pre-registered hypothesis
  exists (EAD triage + `rejected_reference_only` stay active).

**Target user-facing lineup:** Core = Momentum (live) / **Trend** · Defensive = Low-vol / Sector /
Combined · Opportunistic = **Gapper** / Discovery · Reference-only = Insider · Congress · Lobby ·
Gov-contracts.

---

## Deferred / reserved

- **INSIDER-002 — Insider-Confirmed Momentum / Microcap Confirmation** — a *new* hypothesis, **after**
  TREND-001 and GAPPER-001; insider stays reference-only until it passes a fresh pre-registered test.
- **No new Quiver datasets.**

---

## Locked sprint sequencing

**Week 0** — 1) finalize TREND-001 v0.3 scope · 2) ETF Data Availability Gate · 3) factor-store
freshness / Monday rebalance · 4) deploy/schedule CEE · 5) ADR-0040 minimal metrics · 6) gappers/SCAN
freshness. *(TREND-001 pre-registration proceeds in parallel.)*
**Week 1** — run TREND-001 → registered evidence package → decide (paper / reject / revise-only-if-pre-registered).
**Week 2** — pre-register GAPPER-001 → CAP-025 intraday replay/funnel → evidence package + Candidate Report.
**Week 3** — promote any passing strategy to a small paper book, CEE day one; keep insider/Quiver event
data out of ranking/sizing absent a new approved hypothesis.

## What this sprint is explicitly NOT

Not relaxing the evidence standard · not chasing 10 ideas · not a signal/parameter search · not
reviving Range fade logic · not using insider as direct alpha · not a full GAPPER UI · not another
governance artifact.

---

*Next action on your confirmation: **freeze the TREND-001 pre-registration and run the Data
Availability Gate** — not GAPPER, not insider, not more Quiver, not UI.*
