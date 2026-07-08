# TradingWorkbench — Strategy Production Sprint Plan (v0.4)

**Date:** 2026-07-08 · **Owner:** Jay Wang · **Status:** ✅ **ACCEPTED — operating plan (2026-07-08).**
Folds the v0.3 review redlines. Implementation started: Week-0 Data Availability Gate + TREND-001
pre-registration (`TradingWorkbench_TREND001_PreRegistration_v0.1.md`). Reviewer refinements folded into
the pre-registration (ETF data source = Alpaca bars + total-return seam, not the equity factor store;
KMLM/DBMF benchmark is descriptive given short overlap; power check sweeps an effect-size range → MDE;
a bond TR-gate failure is stop-and-review, not a silent drop).
**Source:** v0.3 + review comments (2026-07-08).
**Changes v0.3 → v0.4:** sprint success **decoupled from strategy approval** (§Sprint success);
three-way verdict restored (**Approved / Diversifier / Rejected**) with a pre-registered Diversifier
path + **power check** for TREND-001; the 12-1 + 200-day-MA conjunction **pinned as an exact boolean**;
**total-return pricing made a hard Data-Availability-Gate criterion** (not documentation); KMLM/DBMF
promoted to a **secondary benchmark**; ex-UUP / ex-DBC sensitivity added; GAPPER-001 gains a
**candidate-provenance statement + minimum-sample gate** and a widened **slippage grid (to 100 bps)**
with half-spread entry modelling; liquidity floor **pre-registered now** (not "unless pre-registered");
"market/sector positive" defined exactly; a **pre-registered paper-phase protocol** added to Week 3;
revisions = **new program ID**; the Candidate Report inherits the **ADR-0037 label whitelist**.

> **The shift (unchanged).** Move from building infrastructure to producing **2–3 evidence-backed,
> user-visible strategy candidates** — **without relaxing the evidence bar.** A clean rejection is
> still a success. Each program runs the unchanged discipline: pre-registration → evidence package →
> verdict → stopping rule → (if it passes) a small paper book under Continuous Evidence from day one.

---

## Sprint success (pre-registered — NEW in v0.4)

The sprint's goal is to prove the platform is useful to individual investors. That is **not** the same
as producing approved strategies, and an honest bar means zero approvals is a possible outcome. So the
sprint's own success metric is pre-registered separately from the strategies':

- **Sprint success =** two completed, reproducible, pre-registered Evidence Packages (TREND-001,
  GAPPER-001) with clear verdicts and usability/capacity blocks — **plus ≥1 paper book if and only if
  a program passes.**
- **Every verdict ships as an investor-facing evidence brief** ("we tested X, here is the evidence,
  here is the verdict") under the ADR-0037 label vocabulary. A rejection produces a publishable brief;
  the sprint therefore cannot fail by being honest.
- **Sprint failure =** an evidence package that is incomplete, irreproducible, or post-hoc-modified —
  not a rejection verdict.

---

## Guardrails (non-negotiable)

- **Evidence standard unchanged** — pre-registration, approval requires a CI excluding zero, the
  stopping rule (no looping on parameters), reproducible / survivorship-free / cost-aware.
- **No more broad EAD/Quiver dataset hunting** — the Dataset Triage gate stays in force.
- **Insider / Congress / Lobby / GovContract stay reference-only** (`rejected_reference_only`).
- **Reuse the platform** — Factor Lab `run_program`, PORT-001 ERC + vol-target overlay, SCAN-001,
  CAP-025 intraday replay, the bootstrap/Evidence-Package engines.
- **One primary rule per program** — a single pre-registered primary design; everything else is a
  *sensitivity test*, never a candidate strategy. No signal-combination or parameter search.
- **Revision = new program ID (v0.4).** A revised design is TREND-002 / GAPPER-002 with a fresh
  pre-registration — never an edit of the original program. The stopping rule has no back door.

---

## How Week 0 gates the sprint (partial gate)

- **TREND-001 pre-registration runs *in parallel* with Week 0** — it is research design, not live ops.
- **TREND-001 result interpretation** is gated on: factor-store freshness verified · the ETF Data
  Availability Gate (incl. the **total-return criterion**, below) · the TREND-001 **power check**
  recorded (§Week 1).
- **GAPPER-001 execution** is gated on: SCAN/gapper freshness · the ADR-0040 minimal metrics · the
  **candidate-provenance statement + minimum-sample gate** (§Week 2).
- **Any paper deployment** is gated on: CEE report scheduled *or* operationally runnable, **and the
  pre-registered paper-phase protocol** (§Week 3).

Flow: **pre-reg in parallel → execute after the data checks → go to paper after the Week-0 controls.**

---

## Week 0 — Operational readiness + scope lock

| # | Item | Definition of done |
|---|---|---|
| 0.1 | **Finalize TREND-001 v0.4 scope** | Owner-confirmed (universe, exact primary boolean, cadence, benchmarks, verdict metric + Diversifier thresholds, power check plan) |
| 0.2 | **Data Availability Gate** (below) | Per-ETF checks pass or the excluded set is recorded; gappers/SCAN/intraday freshness confirmed |
| 0.3 | **Factor-store freshness / Monday proof** | Four factor books RANK (not HOLD) on the fresh store at Mon 10:00 ET |
| 0.4 | **CEE deploy + schedule** | `scripts/reports/` in the backend image; systemd timer; **SNS alert on INVESTIGATE** |
| 0.5 | **ADR-0040 minimal metrics** | The four counters (logging/counters only — full monitoring is a PR follow-up) |
| 0.6 | **Total-return pricing (report-only) — decoupled from TREND-001** | PORT-001 #3 in report-only mode. TREND-001 is instead gated by the **total-return criterion in the Data Availability Gate** (v0.4 — see below) |
| 0.7 | **Registry reconcile (doc-only, non-blocking)** | Capability count 23 → **25** (CAP-024/025) + ADR-0040 |

**Data Availability Gate (v0.4 — total-return is now a hard criterion).** Per ETF, before TREND-001
execution:
- daily OHLCV exists · data extends through the latest expected trading date · no large unexplained
  gaps · ticker resolves through the factor store;
- **adjusted-close / total-return series available and verified. An ETF with only close-only data is
  EXCLUDED by this gate** — same as insufficient history. Rationale: TLT/IEF returns are substantially
  distributions; a close-only basis systematically understates bond returns and can flip the
  cash-vs-bonds switch and the verdict. *Documenting a known-wrong basis does not make a verdict
  valid.*
- **Pre-declared exclusion rule:** an ETF failing any criterion is excluded *before* any results are
  computed, and the final universe is recorded.
- Also: gappers-file freshness · SCAN candidate-file freshness · intraday-bar availability for
  GAPPER-001.

**ADR-0040 minimal metrics (Week 0; do not block TREND-001 pre-reg; required before GAPPER paper):**
`market_order_priced_from_bar_cache_count` · `market_order_reference_price_missing_count` ·
`market_order_bar_cache_miss_count` · `market_order_unpriced_count`.

---

## Week 1 — TREND-001 · Multi-Asset Time-Series Trend

Multi-asset time-series / absolute-momentum — **not** an equity cross-sectional momentum variant, and
distinct from the rejected TV-001-Supertrend.

**Primary hypothesis (pre-registered):** *assets with a positive medium-term own-trend outperform
owning the same assets (and cash) after volatility targeting and costs.*

**Universe (primary, subject to the Data Availability Gate):** SPY · QQQ · IWM · EFA · EEM · TLT · IEF ·
GLD · DBC · UUP. **Sensitivity-only:** KMLM sleeve (shorter history).

**Primary signal — exact boolean (v0.4, pinned):**
- **Hold asset i iff:** `TR_12m_skip1(i) > 0 AND price(i) > MA200(i)` — evaluated on total-return
  (adjusted) prices at the monthly rebalance date. **Both conditions gate holding; failing either at a
  rebalance ⇒ that sleeve is in cash until the next rebalance.** Entry and exit use the same boolean —
  there is no separate exit rule.
- **Skip-month note (pre-registered choice):** the 12-1 skip is retained deliberately for consistency
  with the platform's momentum convention; **12-month-including-last is a sensitivity**, not the
  primary. (The skip is an equity cross-sectional convention; for TS-trend on ETFs either is
  defensible — the choice is recorded here so it is a decision, not a habit.)
- **Sensitivity (never the primary):** 3/6/12-month ensemble score · MA-only · TR-only ·
  12m-including-last · weekly cadence · ex-UUP and ex-DBC universes (v0.4 — tests whether the edge is
  mostly "avoided the perennial decliners").

**Portfolio:** long-only · vol-targeted · risk-budgeted (PORT-001 ERC + vol-target overlay) · cash when
the boolean fails. **Cash leg (pre-registered): T-bill/BIL proxy** (preferred for realism; zero-yield as
a sensitivity).

**Cadence (do NOT optimize):** primary **monthly, first trading day**; weekly as sensitivity only.

**Benchmarks:**
- **Primary:** equal-weight buy-and-hold of the same ETF universe, monthly rebalanced (*does the trend
  rule add value over simply owning the same assets?*).
- **Secondary (v0.4 — the investor's real alternative):** **a managed-futures/trend ETF (KMLM and/or
  DBMF), over the overlapping window.** If the platform's trend book does not beat simply buying the
  trend ETF after costs, the honest product recommendation to an individual investor is "buy the ETF"
  — and the evidence brief says so. That answer is itself platform value.
- **Tertiary:** SPY · 60/40 SPY/TLT · the T-bill proxy.

**Backtest period:** the longest common history across the primary ETFs (expect ~2007+; DBC/EFA/EEM
constrain); the modern full universe (incl. KMLM sleeve) as a sensitivity.

**Power check (v0.4 — pre-registered, run BEFORE the backtest verdict):** with ~230 monthly
observations and trend's crisis-concentrated payoff, a ΔSharpe bootstrap CI may be unable to exclude
zero *even under the historical effect size*. Before interpreting results: simulate the primary design's
CI width under the literature/historical effect size for this universe and window. **If the design
cannot plausibly reject the null even when the effect is real, that is recorded in the evidence package
as a power limitation — and the Diversifier path (below) becomes the realistic bar.** A "rejection"
that is actually a power failure must be labelled as such.

**Verdict (v0.4 — three-way, all thresholds pre-registered before the run):**
- **Approved:** bootstrap CI on **ΔSharpe vs the primary benchmark excludes zero** (stationary/circular
  **block** bootstrap — vol targeting induces autocorrelation an iid bootstrap understates; block
  length pre-registered).
- **Diversifier (restored, pre-registered path):** ΔSharpe CI spans zero **but** BOTH:
  **MaxDD reduction ≥ [X]% relative** and **ΔCalmar > 0 with its CI excluding zero** (set X at
  pre-registration, before any results — suggested starting point 25% relative MaxDD reduction).
  A Diversifier verdict makes the program eligible for a **defensive paper sleeve**, not the core
  lineup. *This is not a relaxed bar — it measures the claim TS-trend actually makes (crisis convexity
  and drawdown control), which headline Sharpe is weakest at capturing.*
- **Rejected:** neither path clears. Guardrails on all paths: CAGR drag not excessive (pre-set) ·
  robust across ETF-only and equity-index subsets · survives cost/slippage.

**Deliverable:** pre-registration (incl. power check + Diversifier thresholds) + backtest Evidence
Package (incl. the usability/capacity block). Week-1 decision: paper candidate (Approved or
Diversifier-to-defensive-sleeve) / reject / revise **as TREND-002 only**. Paper deployment requires CEE
from day one **and the §Week-3 paper protocol**.

---

## Week 2 — GAPPER-001 · Gap + RVOL Opening Continuation

Turns the *validated* SCAN-001 Candidate Engine into a candidate **trade** strategy — the most
user-visible candidate. **Not** a Range Trader revival: **continuation**, not fade.

**Primary hypothesis (pre-registered):** *high-quality gap/RVOL candidates that hold above VWAP / the
opening-range high after the first 30 minutes continue — intraday.*

**Candidate provenance + minimum-sample gate (v0.4 — NEW, blocking):**
- **State where historical candidates come from.** If SCAN-001 candidate files exist only since SCAN
  went live, the event count may be far too small for a verdict. Two pre-registered options — pick one
  in the pre-registration:
  - **(a) Point-in-time reconstruction:** SCAN-001's selection logic is re-run over historical data.
    The reconstruction itself is part of the pre-registration (inputs, as-of data, any filter that
    differs from live) — this is where look-ahead sneaks in, so it is reviewed as design, not code
    detail.
  - **(b) Live-files-only:** accept the small window and the gate below decides.
- **Minimum-sample gate:** **≥100 eligible gap events across ≥40 distinct dates after the liquidity
  floor** (300+ events / 60+ dates preferred). **Below the floor the verdict is `insufficient_sample`
  — not Rejected, not Approved** — and Week 2's deliverable becomes "evidence accumulation started,"
  which is an honest outcome. A tiny sample must not masquerade as a verdict in either direction.

**Primary design (locked — one design; the rest are sensitivity):**
SCAN-001 candidate → **enter on the 30-min opening-range high break** → **require price above VWAP** →
**require market & sector positive (defined below)** → **exit at same-day close**.
- **"Market/sector positive" — exact definition (v0.4):** SPY **and** the candidate's sector ETF
  (GICS-mapped SPDR) both **above their prior session close** at the entry bar. (Alternatives — above
  today's open, above VWAP — are sensitivities, not the primary.)
- **Entry price modelling (v0.4):** entries fill at the OR-high break price **plus half the prevailing
  spread** (breakout entries buy into momentum — adverse selection on fills is the base case, not the
  sensitivity).
- **Sensitivity:** 15-min high break · 1/3/5-day hold · ATR trailing stop · VWAP-only filter.
  *GAPPER-001 is not a parameter search.*

**Liquidity floor (v0.4 — pre-registered NOW, default-exclude):** minimum price **$5** · minimum
median dollar volume **$20M/day (20-day)** · maximum time-of-entry spread **25 bps**. Anything below
the floor is excluded from the universe *before* results are computed. (The v0.3 "no microcaps unless
pre-registered" inverted the default; the floor is now the pre-registration.)

**Slippage grid (v0.4 — widened for the gapper universe):** sensitivity at **5 / 10 / 25 / 50 / 100
bps.** Gap-day small/mid-caps routinely trade 30–100+ bps effective spreads at the 30-minute mark; a
grid that stops at 25 bps is a large-cap grid. The evidence package reports the **breakeven slippage**
(the bps level at which the edge dies) as a headline number — that, plus the capacity estimate, is what
tells an individual investor whether the strategy is *usable*, not just *real*.

**Method — CAP-025 Intraday Replay & Entry-Funnel Diagnostics** (avoids RNG-001's daily-OHLC false
positive): post-activation fill rate · target-after-entry vs stop-after-entry · day-level P&L (idle
capital = 0) · **date-clustered bootstrap** over a train/test split · slippage sensitivity ·
spread/liquidity capacity.

**Deliverable:** intraday-replay + opening-continuation Evidence Package **+ a lightweight Morning
Opportunities Candidate Report** (no full UI this sprint): a table reusing SCAN-001 — `ticker · gap % ·
RVOL · Discovery Confidence · entry trigger · VWAP status · liquidity/spread · result label`.
**Label discipline (v0.4):** the report inherits the **ADR-0037 whitelist verbatim** (Watch · Research
· Backtest Pending · Validated Pattern · Rejected Pattern); no Buy/Sell/target/conviction vocabulary,
and the "entry trigger" column is descriptive of the *studied rule*, never phrased as an instruction to
the reader. This is the sprint's most user-visible artifact and therefore its compliance surface.
Paper deployment requires CEE from day one **and the §Week-3 paper protocol**.

---

## Usability / capacity block (both evidence packages — unchanged + one addition)

Each evidence package reports: **suggested account-size range · expected turnover · average number of
positions · capacity estimate · worst historical drawdown · expected cash usage · user suitability
(core / defensive / opportunistic) · breakeven slippage (GAPPER) / cost drag at 2× assumed costs
(TREND).**

---

## Week 3 — Promote paper candidates (v0.4 — with a pre-registered paper protocol)

**Paper-phase protocol (pre-registered with each program — NEW):** promotion to paper is not the end of
pre-registration; the paper phase has its own pass/fail declared before it starts:
- **Minimum duration:** TREND-001 ≥ **1 quarter** (≥3 monthly rebalances); GAPPER-001 ≥ **8–12 weeks
  or ≥40 paper trades**, whichever is later.
- **Drift thresholds vs. the backtest:** realized fill quality, turnover, hit rate, and cost drag
  within pre-set bands of the evidence package (bands set at pre-registration). CEE INVESTIGATE →
  reviewed within one business day; a pre-set hard band breach → **halt the paper book** (halting is
  the success of the control, not a failure of the sprint).
- **Nothing becomes user-visible before its paper protocol completes.** The evidence brief may be
  published (with its Backtest-verdict label) — the *live sleeve* may not.

- **TREND-001 Approved** → trend sleeve/book to paper (core track). **TREND-001 Diversifier** →
  defensive paper sleeve. **GAPPER-001 passes** → small opportunistic paper book. Every promoted book
  runs Continuous Evidence from day one.
- **If both fail** → prioritize **LOW-002** only after a short postmortem confirms no reusable
  strategy candidate emerged — **and the two evidence briefs still ship** (§Sprint success).
- **No insider / Quiver event data in ranking/sizing** unless a new *approved* pre-registered
  hypothesis exists (EAD triage + `rejected_reference_only` stay active).

**Target user-facing lineup:** Core = Momentum (live) / **Trend** · Defensive = Low-vol / Sector /
Combined / **Trend-as-Diversifier (if that verdict)** · Opportunistic = **Gapper** / Discovery ·
Reference-only = Insider · Congress · Lobby · Gov-contracts.

---

## Deferred / reserved (unchanged)

- **INSIDER-002 — Insider-Confirmed Momentum / Microcap Confirmation** — a *new* hypothesis, **after**
  TREND-001 and GAPPER-001; insider stays reference-only until it passes a fresh pre-registered test.
- **No new Quiver datasets.**

---

## Locked sprint sequencing (v0.4)

**Week 0** — 1) finalize TREND-001 v0.4 scope (exact boolean · Diversifier thresholds · power-check
plan) · 2) ETF Data Availability Gate incl. **total-return criterion** · 3) factor-store freshness /
Monday proof · 4) CEE deploy/schedule · 5) ADR-0040 minimal metrics · 6) gappers/SCAN freshness +
**GAPPER candidate-provenance decision**. *(TREND-001 pre-registration proceeds in parallel.)*
**Week 1** — run the power check → run TREND-001 → registered evidence package → verdict
(Approved / Diversifier / Rejected / revise-as-TREND-002).
**Week 2** — pre-register GAPPER-001 (provenance + sample gate + liquidity floor) → CAP-025 replay /
funnel → evidence package + Candidate Report (ADR-0037 labels).
**Week 3** — promote per the paper protocol; publish the evidence briefs regardless of verdicts; keep
insider/Quiver event data out of ranking/sizing absent a new approved hypothesis.

## What this sprint is explicitly NOT (unchanged + one line)

Not relaxing the evidence standard · not chasing 10 ideas · not a signal/parameter search · not
reviving Range fade logic · not using insider as direct alpha · not a full GAPPER UI · not another
governance artifact · **not coupling the sprint's success to strategy approval — honesty cannot be a
failure mode.**

---

*Next action on your confirmation: **freeze the TREND-001 pre-registration (exact boolean, Diversifier
thresholds, power-check plan) and run the Data Availability Gate with the total-return criterion** —
not GAPPER, not insider, not more Quiver, not UI.*

---

### Changelog — v0.3 → v0.4 (from review)

1. **Sprint success pre-registered separately from strategy approval** (new §Sprint success): two
   reproducible evidence packages + investor-facing briefs = success; rejection ≠ failure;
   incomplete/post-hoc packages = the only failure mode.
2. **Three-way verdict restored for TREND-001** (Approved / **Diversifier** / Rejected) with the
   Diversifier path pre-registered (MaxDD-reduction + ΔCalmar thresholds set before the run) —
   measures TS-trend's actual claim (crisis convexity), which ΔSharpe under-powers.
3. **Power check added** before TREND-001 verdict interpretation; a power failure must be labelled a
   power limitation, not a rejection. **Block bootstrap** specified (vol-targeting autocorrelation).
4. **Primary signal pinned as an exact boolean** (TR12-1 > 0 AND price > MA200, same rule for
   entry/exit, monthly); skip-month recorded as a deliberate choice with including-last as sensitivity.
5. **Total-return pricing became a hard Data-Availability-Gate criterion** — close-only ETFs are
   excluded, not documented (TLT/IEF distribution bias can flip the verdict).
6. **KMLM/DBMF promoted to secondary benchmark** — the individual investor's real alternative is
   buying the trend ETF; if the book doesn't beat it after costs, the honest brief says "buy the ETF."
7. **ex-UUP / ex-DBC universe sensitivities** added.
8. **GAPPER candidate provenance + minimum-sample gate** (≥100 events / ≥40 dates or verdict =
   `insufficient_sample`); PIT reconstruction, if used, is pre-registered as design.
9. **GAPPER slippage grid widened to 50/100 bps**, entries modelled at break + half-spread, breakeven
   slippage reported as a headline; **liquidity floor pre-registered now** ($5 / $20M ADV / 25 bps),
   default-exclude; **market/sector positive defined exactly** (SPY + sector SPDR above prior close).
10. **Paper-phase protocol pre-registered** (duration, drift bands, halt rule; nothing user-visible
    before it completes).
11. **Revision = new program ID** (TREND-002 / GAPPER-002) — the stopping rule has no back door.
12. **Candidate Report inherits the ADR-0037 label whitelist verbatim**; entry-trigger column is
    descriptive, never instructional.
