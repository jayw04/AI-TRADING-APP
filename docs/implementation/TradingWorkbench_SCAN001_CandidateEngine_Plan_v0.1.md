# Trading Workbench — Daily Candidate Selection Engine: Research Plan & Pre-Registration (v0.1)

> ## Research Program `SCAN-001`
> | | |
> |---|---|
> | **Program type** | **Platform Capability** (the first non-strategy program — `MOM/RNG/MF/SEC/LOW/TREND` are strategies; this is shared infrastructure they all consume) |
> | **Name** | Daily Candidate Selection Engine |
> | **Research goal** | **Which daily, pre-open filters select the small universe of stocks most likely to exhibit tradeable intraday opportunities?** Build the curated-watchlist engine *before* the intraday strategies, so they all trade the same evidence-selected candidates instead of scanning 4,000+ names blindly. |
> | **Status** | **PLANNING** (pre-registration draft; no scan has run). |
> | **Owner** | Jay |
> | **Platform value** | The reusable **morning scanner** that feeds the whole Intraday Research Framework — a capability, not a one-off for the Range Trader. |
> | **ADR** | TBD (assign if the engine becomes a standing scheduled subsystem). |

| Field | Value |
|---|---|
| Document | **SCAN-001** — plan + **pre-registered** filter set & evidence gate. |
| Version | **v0.1 (2026-06-22)** — initial draft from the owner's SCAN-001 / Intraday Research Framework roadmap (`Docs/design/`). |
| Governing | **ADR 0014** (backtests = ground-truth) · ADR 0019 (Research Engine, read-only) · the Evidence Engineering methodology (`docs/methodology/`). |
| Data | **Alpaca** (primary — minute/daily bars, volume, premarket) + **FMP** (enrichment — float, market cap, sector, earnings calendar) + **internal calcs** (RVOL, ATR, gap %, overnight return). **No new paid vendors** in v1. ⚠ **Prerequisite met:** the bar-cache stale-data bug is fixed (open-bucket re-fetch) — candidate filters now read *current* bars. |

---

## 0. Why SCAN-001 exists (the business framing, not the technical one)

> The original Range Trader was **stock-agnostic** — it treated every symbol the same. Institutional
> intraday traders don't: they begin each day by **selecting a small universe** (5–20 names) with the
> highest probability of intraday opportunity, then trade *only those*. The selection step is where most
> of the intraday edge lives, and it is **reusable across every intraday strategy** (mean-reversion,
> breakout, VWAP, gap-fade…). So the platform builds the **Candidate Engine first**, as a capability.

This is the platform-not-strategy thesis applied to intraday: the scanner is the durable asset; the
intraday strategies are interchangeable research programs built on top of it. SCAN-001 answers *which
filters select good candidates* — a question whose answer outlives any single strategy.

## 1. Hypothesis (frozen)

The platform question: **does a pre-open filter pipeline select a candidate set that delivers materially
better intraday opportunity than the unfiltered universe (or a random/liquid baseline)?**

- **H1 (selectivity):** the filtered candidate set exhibits **higher realized intraday range / movement**
  (e.g. high-of-day − low-of-day as % of open, or realized intraday volatility) than the baseline,
  out-of-sample — a difference whose bootstrap 95% CI excludes zero.
- **H2 (tradeability):** the candidates produce **more, cleaner intraday setups** for at least one
  downstream strategy family (measured later via the strategy's own evidence, not assumed here).
- **H3 (filter attribution):** *which* filters carry the signal — single-filter vs combined — so the
  engine keeps only filters that earn their place (no kitchen-sink screening).

A negative result (filters don't beat the baseline) is a **success** — a citable "the curation doesn't pay"
finding that saves building intraday strategies on a false premise.

### 1a. Pre-registered behavior expectation (frozen BEFORE results)

| Dimension | Expectation | Why |
|---|---|---|
| Candidate-set intraday range | **higher** than the liquid-universe baseline | the filters target high-movement names |
| Day-to-day candidate overlap | **low–moderate** | gap/RVOL names rotate daily |
| Best single filter | **Relative Volume or Gap %** | the two most-cited institutional intraday screens |
| Earnings filter effect | **reduces blow-up tails** | excludes binary-event names |

## 2. The filters (frozen, single pre-registered set — no sweep-to-fit)

Computed **pre-open (08:30–09:25 ET)** per name over the liquid universe. Frozen thresholds (conservative
defaults; reported as a labeled robustness band, NOT tuned to maximize historical hit-rate):

| Filter | Threshold (frozen) | Source |
|---|---|---|
| **Gap %** | \|open − prev close\| / prev close > **3%** | Alpaca (prev daily close + premarket/open) |
| **Relative Volume (RVOL)** | premarket vol / N-day avg premarket vol > **2×** | Alpaca + internal |
| **Price** | > **$10** | Alpaca (avoids sub-$ noise) |
| **Dollar volume** | prev-day $-volume > **$20M** | Alpaca (liquidity floor) |
| **ATR** | ATR(14) / price > **2%** | internal |
| **Earnings filter** | **exclude** names reporting today / overnight | FMP earnings calendar |
| **News/catalyst (optional)** | flag-only (not a hard filter in v1) | Benzinga (already in the gappers scanner) |

**Output:** ranked **top 10–20 candidates** per trading day (rank by a transparent composite, e.g. RVOL×Gap),
each with its filter values — the daily watchlist.

## 3. Construction (the engine, read-only research prototype)

A new `scripts/candidate_engine.py` (mirrors the evidence-script pattern): for each historical trading day,
reconstruct the **point-in-time** pre-open snapshot (no look-ahead — only data available by 09:25 ET that
day), apply the frozen filters, rank, emit the top-N. **Reuses** the gappers scanner primitives (#221) and
the bar cache (now fresh). Pure functions, unit-tested. **No order routing — read-only research only** (the
candidate set is evidence, not a trade signal).

> **Stopping rule (frozen).** If the filtered candidate set shows **no intraday-opportunity edge over the
> baseline (H1 fails) AND no single filter attributes signal (H3 flat)** on out-of-sample data, the curation
> hypothesis is **archived** as a citable rejection — the platform would then trade the liquid universe
> directly rather than over-engineer a scanner. This bounds the program.

## 4. Pre-registered evidence gate (frozen BEFORE results)

| Criterion | Bar |
|---|---|
| **Selectivity (H1)** | candidate-set intraday-range metric beats the liquid-universe baseline; bootstrap 95% CI of the difference excludes 0 |
| **Significance** | paired circular-block bootstrap over trading days (≥2000 resamples, fixed seed) |
| **Consistency** | positive in ≥ ⌈W/2⌉+1 walk-forward windows (regimes) |
| **Filter attribution (H3)** | per-filter and combined contribution reported; keep only filters that add signal |
| **Point-in-time** | strictly pre-open data only — no look-ahead, survivorship-aware universe |
| **No-overfit clause** | thresholds are conservative defaults set *before* results; {robustness band} reported, not optimized to the metric |

**Verdict (decision tree) — pre-registered probabilities + learning objective:**

| Outcome | Trigger | Prob. | What we learn (regardless) | Platform impact |
|---|---|---|---|---|
| **A — Validated capability** | H1 clears (curation beats baseline) | **50%** | The morning scan genuinely concentrates intraday opportunity | Ship the **Candidate Engine** as a standing capability feeding the Intraday Framework |
| **B — Partial** | H1 marginal but H3 finds ≥1 strong filter | **30%** | Some filters work (e.g. RVOL); prune the rest | Slimmer engine on the validated filters |
| **C — Rejected** | H1 fails and H3 flat | **15%** | Curation doesn't pay on this universe — trade the liquid set directly | Knowledge asset; skip the scanner |
| **D — Inconclusive** | borderline / thin data | **5%** | Need more history / a different universe | Research archive → revisit |

## 5. Method (what the run produces)

1. **Universe + PIT snapshots** — liquid universe per day; pre-open feature panel (gap%, RVOL, ATR, $-vol, price, earnings flag) computed from data available by 09:25 ET.
2. **Filter pipeline** — apply frozen thresholds; rank; top-N.
3. **Opportunity metric** — per candidate, the *realized* intraday range / movement that day (the thing intraday strategies monetize).
4. **Baseline comparison (H1)** — candidate-set metric vs liquid-universe (and a random-N) baseline + paired bootstrap.
5. **Walk-forward** sub-windows (consistency across regimes).
6. **Filter attribution (H3)** — single-filter and ablation.
7. **Evidence package** (`script → JSON → Markdown`, seeded/reproducible) → `docs/implementation/evidence/scan_001_candidate_engine/`.

## 6. Benchmarks
- **Liquid-universe** (primary — does curation beat "trade everything liquid"?).
- **Random-N** from the liquid universe (controls for "any 15 names" vs "the filtered 15").
- (Later) per-strategy P&L when an intraday strategy trades candidates vs the baseline.

## 7. Out of scope (v1)
Automated intraday trading on the candidates (that's the downstream strategy programs); Level-2 / tick data; paid vendors (Polygon); float from a paid source (FMP float is the v1 enrichment); the news filter as a *hard* gate (flag-only in v1). Live activation is gated on a VALIDATED verdict + governance.

## 8. Platform value & the Intraday Research Framework

On a VALIDATED verdict, SCAN-001 becomes the shared **Daily Candidate Selection Engine** feeding a family
of intraday research programs — each a separate, interchangeable program on top of the same engine:

| Strategy | Status |
|---|---|
| Intraday Mean Reversion (the former Range Trader) | Research |
| Opening Range Breakout (ORB) | Planned |
| VWAP Reversion | Planned |
| Gap Fade | Planned |
| First-Hour Fade | Planned |
| Intraday Momentum | Planned |

The engine is the durable, reusable capability; the strategies become configuration over it. This is the
intraday analogue of the **Factor Lab** (research = configuration over shared infrastructure).

## 9. Research risk register

| Risk | Mitigation |
|---|---|
| Look-ahead leakage (using post-09:25 data) | strict PIT snapshot; only data available by the scan time |
| Stale/bad bars poison the filters | ✅ bar-cache open-bucket fix (current bars); a dataset-health/freshness gate before each scan |
| Survivorship bias in the universe | survivorship-aware universe; document the source |
| Over-fitting the thresholds | frozen conservative defaults; robustness band, not tuned-to-metric |
| Filter redundancy (kitchen sink) | H3 attribution prunes filters that don't earn their place |

## 10. Production path & research cost

**Lifecycle:** `Hypothesis → Research → Evidence → Governance → Candidate → (engine ships as capability) → Continuous Evidence.`

| Resource | Estimate |
|---|---|
| Developer time | ~1–2 sessions (engine script + PIT panel + evidence package) |
| CPU hours | low (daily snapshots over a few years of liquid universe) |
| Dataset | **none new** — Alpaca + FMP already in place |
| Complexity | **medium** — the PIT pre-open feature panel is the real work; ranking/filtering is thin |
| Reuse % | **~70%** — gappers scanner (#221), bar cache, bootstrap/walk-forward/report scaffold inherited |

### 10a. Research-calibration metrics (pre-registered)
- **Research Confidence: Medium** — strong institutional precedent for RVOL/Gap screens, but unproven on *this* universe + data.
- **Research Complexity: Medium** — PIT correctness is the hard part.
- **Research Duration:** Planned 2026-06-22 → Started _(on build)_ → Completed _(in evidence package)_.

## 11. Open questions (confirm before build)
- **Q1 — Universe:** the same survivorship-free liquid universe used elsewhere, or a separate intraday-liquid set?
- **Q2 — Opportunity metric:** intraday range %, realized intraday vol, or a setup-count proxy as the H1 metric?
- **Q3 — Scan time:** fix at 09:25 ET (just before open) for the PIT snapshot?
- **Q4 — Top-N:** 10, 15, or 20 candidates as the headline?

---

> **Registry note.** On approval, register `SCAN-001` in the Research Program Registry — **Type: Platform
> Capability · Status: Planning · Platform Value: Daily Candidate Selection Engine** — the first
> capability-type program alongside the strategy programs.
