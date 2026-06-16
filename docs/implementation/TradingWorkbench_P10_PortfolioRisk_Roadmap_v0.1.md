# Trading Workbench — P10 Portfolio-Level Risk Engineering (Roadmap / Direction)

| Field | Value |
|---|---|
| Document version | v0.3 (2026-06-15: +§9 deferred data models & methodology — overlay action invariant, PIT survivorship spec, execution-cost baseline, from review comments §2) |
| Date | 2026-06-15 |
| Phase | P10 — Portfolio-Level Risk Engineering |
| Predecessor | P9 §4 `momentum-portfolio` (now v0.5.0); paper-active id=2 |
| Repository | github.com/jayw04/AI-TRADING-APP |
| Scope | Turn the `momentum-portfolio` book from a pure cross-sectional alpha sleeve into a risk-managed portfolio: vol targeting, sector caps, daily exposure overlay, exposure smoothing — *without* adding alpha signals or sacrificing the current simplicity. |
| Source | Owner's two reviews of `momentum_portfolio.py` (`strategy-review/review comment.md`, 2026-06-15): v1 (10 weaknesses) and **v2 (8 critical issues, re-prioritized)**. |
| Status | EWMA vol targeting (v0.4.0) + **sector caps (v0.5.0, #118)** implemented, both **default off**. Broad-history store (28.5 yr) built. **Review v2 re-prioritizes — see below.** |

---

## Why this phase exists

The owner's review of the v0.3.0 strategy reached a clear verdict: the file is *implementable, explainable, robust, and operationally realistic* — and its single biggest remaining weakness is **unmanaged momentum-crash risk, not stock-selection logic**. Classical cross-sectional momentum carries well-documented crash risk (fast reversals, crowding unwinds, factor rotations: e.g. Mar 2009, Aug 2007). The v0.3.0 `SPY < 200d MA → cash` regime filter helps with slow bear markets but does nothing for violent intra-week reversals.

The review's strongest strategic recommendation: **the best next step is portfolio-level risk engineering, not more alpha signals** — while preserving the current simplicity. P10 is that work. It deliberately *delays* ML, advanced regime models, predictive overlays, nonlinear weighting, and macro composites (the review flags all of these as "delay everything else").

This doc captures the full review (so the reasoning is not lost), records what shipped in Priority 1, and scopes Priorities 2–4 plus the data dependencies they need.

---

## The review, captured (10 weaknesses)

Ordered as the owner ranked them. Most are explicitly tagged "NOT now / eventually."

1. **Pure cross-sectional momentum** — inherits classical momentum crash risk. SPY<200DMA helps slow bears but not fast reversals / crowding unwinds / factor rotations. *Rec: a simplified crash overlay (daily EWMA vol scaling, VIX percentile, breadth) — not full complexity.* → **Priority 1 (vol) + later VIX/breadth.**
2. **Weekly frequency too slow for crash protection** — crashes happen intra-week. *Rec: keep weekly stock selection, add a daily exposure overlay.* → **Priority 2.**
3. **Equal weighting suboptimal** — robust initially; eventually inverse-vol / capped risk-parity-lite. *NOT now.*
4. **No portfolio-level volatility control** — all names equal notional; no vol targeting / gross control / dynamic scaling. *Rec: `gross_scale ∈ [0,1]` from EWMA vol / VIX / breadth. "Likely the highest-ROI future upgrade."* → **Priority 1 (the foundation of it).**
5. **No drawdown-protection logic** — only the market filter. *Rec: a portfolio-level de-risk trigger, NOT per-stock stops (correctly avoided).* → later, builds on Priority 1.
6. **No capacity / liquidity constraints** — ADV / participation / spread / liquidity-shock handling. Important because momentum crowds into mega-cap leaders. *Later; needs ADV data we already have (SEP volume).*
7. **No correlation awareness** — equal-weight names can become "one AI-beta trade" (NVDA/AMD/AVGO/MSFT/META). *Rec: sector caps, correlation clustering, factor-exposure constraints.* → **Priority 3 (sector caps) is the cheap first cut.**
8. **No execution-cost modeling** — market orders only; eventually slippage/spread/impact. *Later (backtest realism).*
9. **No persistence / cooldown logic** — names hovering at threshold can churn. *Hysteresis already helps (review: "Good"). Eventually min-hold / rebalance-cooldown ONLY if turnover proves excessive.*
10. **Market filter too binary** — SPY<200DMA all-or-nothing can whipsaw. *Later: gradual exposure scaling instead of all-or-nothing cash.* → naturally subsumed by Priorities 1–2 (continuous gross scaling).

**Review's praise (preserve these):** "fail open for market regime; fail hold for factor data" called "one of the best design choices in the entire file"; the no-per-name-stops decision called correct; rebalance-crash-retries and turnover-threshold/hysteresis all endorsed. **P10 must not regress these.**

### Prioritized near-term work (review's own list)

| Priority | Item | Status |
|---|---|---|
| 1 | Portfolio-level EWMA volatility scaling | ✅ **Implemented v0.4.0 (default off)** |
| 2 | Optional daily exposure overlay (keep weekly selection) | Scoped — §2 below |
| 3 | Sector exposure caps | Scoped — §3 below (gated on sector data) |
| 4 | Simple exposure smoothing | Scoped — §4 below |

Everything else (ML, advanced regime, predictive overlays, nonlinear weighting, macro composites): **delayed deliberately.**

---

## Review v2 (2026-06-15) — deeper, re-prioritized review (now authoritative)

A second, deeper owner review of the *current documented state* raised 8 "critical issues" and **revised the sequencing**. It supersedes the v1 ordering above where they differ. Verdict: the project's challenge is no longer finding strategies — it's *"building robust portfolio-risk and deployment infrastructure around a valid momentum premium."* **Strongest guardrail: freeze the core momentum logic — no signal creep, overlay explosion, or predictive complexity.**

### The 8 critical issues → status

| # | Critical issue | Status (2026-06-15) |
|---|---|---|
| 1 | **Backtest window too short** (2024-06+) — must expand to ≥2007 (GFC, 2011, 2015, COVID, 2022) before enabling *anything* live | **Depth done**: full-history store `factor_data_full.duckdb` = **1997→2026 (~28.5 yr)**, 6.44M rows. ⚠ **Breadth gap**: universe is *today's* 1,252-name pool → still survivorship-biased for historical windows (see §6). |
| 2 | **Daily-overlay framework is the hardest problem** — do NOT build dual-cadence inside one strategy | **Reframed** (supersedes §2 rec): use a **separate overlay engine** — selection strategy owns names, overlay engine owns gross exposure (alpha / portfolio-construction / overlay / execution / risk as distinct layers). |
| 3 | **Vol-scaling may be overfit to 2024-26 AI momentum** — DD gain huge, Sharpe gain slight | **Rolling walk-forward validation is MANDATORY before enabling vol-scaling live.** Now unblocked by the 28.5-yr store. |
| 4 | **Hidden correlation risk** ("NVDA/AVGO/AMD/MU/SMCI = one trade") — already real & harmful | **Sector caps moved AHEAD of the daily overlay.** Caps shipped (#118, default off); enable after data swap + backtest. |
| 5 | **Breaker only checks on order submission** — an overnight crash with no orders never trips it | **Elevated to HIGH PRIORITY** (was "future polish"): a continuous 1-min APScheduler `CircuitBreakerService.check()` over accounts with open positions. |
| 6 | **Fractional shares more important than it looks** — ~67% deployment distorts factor exposure/diversification | **Moved up** — possibly ahead of the daily overlay. Whole-share rounding systematically biases toward cheap names. |
| 7 | **No portfolio-level correlation model** (covariance / clusters / factor overlap) | Future institutional layer — *not now* (sector caps are the cheap first cut). |
| 8 | **Risk engine still mostly reactive** (order-time only) | Future: continuous portfolio-risk monitoring (realized vol, exposure/beta drift, factor concentration, liquidity). #5 is the first slice. |

### Revised priority order (v2)

1. **Expand historical SEP** — *mandatory* (depth ✅; breadth/survivorship still open → §6).
2. **Sector data + caps** — *economically urgent* (✅ built #118; enable after swap + backtest).
3. **Continuous breaker-monitoring job** — *operationally critical* (new high-priority build).
4. **Fractional shares** — *huge realism improvement*.
5. **Rolling walk-forward tests** — *before enabling vol-scaling live*.
- Then: vol-scaling → sector caps → **daily overlay (as a separate engine)** → smoothing. **Lower/delayed:** daily-overlay complexity, advanced overlays, macro composites, VIX, ML, predictive models.

### Suggested long-term architecture (institutional layer separation)

| Layer | Responsibility |
|---|---|
| Alpha Engine | momentum selection |
| Portfolio Engine | risk scaling, sector caps |
| Overlay Engine | gross exposure (the daily overlay lives here, *not* in the strategy) |
| Execution Engine | order scheduling / pacing |
| Risk Engine | breaker + continuous monitoring |

`momentum-portfolio` currently mixes all of these (OK initially); the daily-overlay work is the natural point to begin separating them.

---

## §1 — Priority 1: EWMA vol targeting ✅ IMPLEMENTED (v0.4.0)

**Shipped** (this PR; `momentum-portfolio` v0.3.0 → **v0.4.0**, default OFF):

- `MomentumPortfolio._gross_scale()` → a gross-exposure multiplier in `[0, 1]`:
  `min(1.0, vol_target_annual / realized_annual_vol)`, where `realized_annual_vol` =
  EWMA (span `vol_ewma_span`) of the market proxy's (SPY) daily returns × √252.
  High-vol regimes scale the book down; the **cap at 1.0 means the overlay never
  adds leverage**. It **fails open** (returns 1.0, logs `vol_scaling_unavailable_failopen`)
  when the proxy series is unavailable — matching the regime filter's reviewed-and-praised posture.
- Wired into `_investable_equity()` so it composes with `cash_buffer_pct`, `max_position_pct`, and the binary regime gate.
- New params (added to BOTH `default_params` and `params_schema` — schema-parity invariant):
  - `use_vol_scaling: bool = False` — **opt-in**; off preserves v0.3.0 behavior byte-for-byte.
  - `vol_target_annual: float = 0.15`
  - `vol_ewma_span: int = 20`
- Backtest harness: `run_momentum_backtest(..., vol_target_annual=, vol_ewma_span=)` now optionally runs a daily EWMA-vol-target **overlay on the book's return series** (`_vol_target_overlay`, no look-ahead — scale for day *t* uses returns strictly before *t*) and reports `vol_scaled_curve` + `vol_scaled_metrics` alongside the unscaled book. Purely additive: the core book curve is unchanged.
- Tests: 4 strategy tests (off-by-default leaves sizing unchanged; reduces exposure in high vol; caps at full in low vol; fails open when proxy unavailable) + 3 backtest tests (overlay dampens high vol; no-lookahead prefix invariance; optional-and-additive). ruff + mypy clean; full strategies + factor_data suites green (165 tests).

**Why default OFF.** Enabling vol targeting changes the deployed book's risk profile and must be validated by a backtest before it governs real (paper or live) orders — ADR 0014 (backtests are primary eval ground truth). Off-by-default also guarantees the change is inert for the currently-active paper strategy (id=2), whose stored params don't set it. Flipping it on is a deliberate, backtested opt-in — consistent with "conservative defaults, configurable extremes."

**Backtest evidence** (local Sharadar store, n=200 universe, top-quintile weekly, 80 usable rebalances, ~late-2024 → 2026-06-12; target 15%, span 20):

| Book | Total return | CAGR | Sharpe | Max drawdown |
|---|---|---|---|---|
| v0.3 (fully invested) | +80.9% | +48.3% | 1.23 | **−38.8%** |
| equal-weight baseline | +34.6% | +21.8% | 1.04 | −22.2% |
| **vol-scaled (15% target)** | +29.9% | +19.0% | **1.29** | **−15.9%** |

Reading: in this strong trending (semis/AI) regime, vol targeting gives up raw upside but **improves risk-adjusted return (Sharpe 1.23 → 1.29) and more than halves the max drawdown (−38.8% → −15.9%)** — exactly the crash-risk reduction the review prioritized. ⚠ **Caveat:** the store is date-bounded (ingest `--from 2024-06-01`), so 361 earlier rebalances were skipped (thin cross-sections) and the usable window is short and momentum-friendly. The *return haircut is regime-specific*; the *drawdown / Sharpe improvement is the durable signal*. A broader backtest (deeper SEP history) should precede any decision to enable it on the live paper book.

### Walk-forward across regimes (2026-06-15) — answers Review v2 Critical Issue #3

Now that the full-history store exists (~28.5 yr), a rolling walk-forward of the overlay (n=80 factor book, top-quintile, 15% target) across the review's required stress regimes — the overfitting check ("is the benefit real across regimes, or just 2024-26 AI momentum?"):

| Regime | Book ret | Book Sharpe | Book maxDD | Vol-scaled ret | VS Sharpe | VS maxDD | ΔmaxDD |
|---|---|---|---|---|---|---|---|
| GFC + 2009 | −41.3% | −0.30 | −65.5% | −17.2% | −0.33 | −33.5% | **+32.0pp** |
| 2010–13 (2011) | +54.4% | 0.83 | −26.8% | +34.3% | 0.74 | −24.0% | +2.8pp |
| 2013–16 (2015) | +16.3% | 0.36 | −23.7% | +10.4% | 0.29 | −20.5% | +3.2pp |
| 2019–22 (COVID) | +74.7% | 0.66 | −45.1% | +27.4% | 0.58 | −24.6% | +20.5pp |
| 2022–26 (rate+AI) | +260.8% | 1.06 | −39.8% | +82.6% | 1.07 | −14.7% | +25.1pp |

**Verdict:** **NOT overfit to 2024-26** — drawdown reduction is consistent across every regime, and the *largest* reductions land in the crash regimes it targets (GFC, COVID, 2022). But it is a **drawdown tool, not a Sharpe booster**: Sharpe is roughly neutral in every window (1.06→1.07 in 2022-26; slightly lower elsewhere) and returns are cut everywhere (lower gross exposure). The trade is explicit — proportional upside give-up for large, regime-robust crash protection. **This clears the review's mandatory walk-forward gate; enabling it remains a risk-appetite decision.** ⚠ Universe is today's pool (survivorship-biased, esp. GFC) and this is the fully-invested factor book (≠ the live $10k/max-5/whole-share book) — read the *relative ΔmaxDD* as the signal, not absolute returns. Script: `apps/backend/scripts/walk_forward_vol_scaling.py` (local-only).

**Not done in Priority 1 (deliberately):** VIX percentile and breadth inputs to the scale (item 1/4) — they need data we don't yet ingest (see §5). Priority 1 uses only the SPY proxy already available via `ctx.get_recent_bars`.

---

## §2 — daily exposure overlay (SCOPED, not started — DEFERRED behind sector caps & fractional shares per Review v2)

> **UPDATE (Review v2):** **do NOT build dual-cadence inside one strategy** (the (A) recommendation below is superseded). Build a **separate overlay engine**: the selection strategy owns names, the overlay engine owns gross exposure — the first step of the alpha / portfolio-construction / overlay / execution / risk layer separation. This is the hardest remaining architectural problem and is deliberately sequenced *after* sector caps, the breaker-monitoring job, fractional shares, and walk-forward validation.

**Goal:** keep weekly stock *selection*, but adjust *gross exposure* daily so an intra-week vol/regime shift de-risks the book before the next Monday.

**Architectural problem (the real work here):** the strategy framework has **no portfolio hook** and `momentum-portfolio` runs a single weekly cron (`0 14 * * 1`); `on_bar` is per-symbol and the strategy no-ops every tick after the weekly rebalance (P9 §4 §3.1). A *daily* overlay needs a daily trigger. Two candidate designs — decide before building:

- **(A) Second schedule on the same strategy.** Give the strategy a daily tick that, on non-rebalance days, recomputes `_gross_scale()` and trims/adds toward the scaled target without re-selecting names. Requires the engine to support a strategy holding two cron cadences (it currently registers one `schedule`). Likely a framework change.
- **(B) Companion overlay strategy.** A separate daily strategy that only scales gross exposure of the book the weekly strategy holds. Cleaner separation but introduces cross-strategy coordination (who owns the positions?) — friction with the single-OrderRouter / one-strategy-owns-its-symbols model.

**Recommendation:** (A), as a bounded framework addition (a strategy may declare an optional `daily_schedule`), is more aligned with the existing model than (B)'s cross-strategy coupling. **This needs its own session doc** and probably a small framework ADR before code.

**Out of scope for §2:** changing stock selection cadence; intraday (sub-daily) overlays.

---

## §3 — sector exposure caps ✅ BUILT (#118, default off) — moved AHEAD of §2 per Review v2

> **UPDATE (Review v2):** built and merged — `momentum-portfolio` v0.5.0. Persists Sharadar `sector`/`industry`; `FactorAccessor.sectors()`; strategy `max_sector_pct` caps names/sector + backfills, fails open. **Default off.** The full-history store's TICKERS ingest populated sector (21,719 names). **To enable:** swap the full store into the live position → set `max_sector_pct` (e.g. 0.40) → backtest. Re-prioritized *ahead* of the daily overlay (concentration is already real; the overlay is still architectural).

**Goal:** cap the book's weight in any one sector so momentum can't silently concentrate the whole book into one beta (review #7).

**Blocker — data dependency:** the factor store is **price-only** (SEP). Sector classification is not yet ingested. Options:
- Sharadar `TICKERS` has `sector` / `industry` fields → cheapest, already in the data we're licensed for.
- FMP fundamentals (the deferred P9 §5 layer) also carries sector.

**Therefore §3 is gated on either (a) extending the `TICKERS` ingest to persist sector, or (b) the P9 §5 FMP layer.** Until then, the correlation risk is *monitored, not capped* — and the live paper book's actual holdings (likely semis/AI-heavy per the Sunday dry-run) are the evidence for how urgent this is.

**Likely shape once data exists:** in `_select_targets`, after the quintile cut, enforce `max_sector_pct` by dropping the lowest-scored names in any over-cap sector. Conservative default (e.g. 30%).

---

## §4 — Priority 4: exposure smoothing (SCOPED, smallest)

**Goal:** damp day-to-day changes in `gross_scale` (and, with §2, the daily overlay) so the book doesn't whipsaw its gross exposure on noisy vol estimates. E.g. smooth `gross_scale` with a short EWMA, or only act when it moves more than a threshold (a turnover-threshold analog for gross, reusing the `min_trade_pct` idea). Sits directly on top of §1/§2. Smallest of the four.

---

## §5 — Data-dependency ADRs needed before parts of P10

These are the new external/data dependencies P10 implies. Per the "adding a new data dependency requires an ADR" invariant:

- **VIX (and/or realized-breadth) series** — for the review's "VIX percentile / breadth deterioration" inputs to `gross_scale` (items 1, 4, 5). VIX is not an Alpaca equity and is not in the SEP universe → **new data source → ADR.** Decide source (Alpaca index data? a vendor? CBOE) and PIT discipline. *Until this lands, vol targeting uses the SPY-proxy realized-vol estimate only (as shipped in §1).*
- **Sector classification** — for §3. If sourced from Sharadar `TICKERS`, likely *no* new ADR (already an accepted dependency, ADR 0018) — just an ingest extension. If from FMP, it rides the P9 §5 FMP ADR. **Decide the source as part of §3 scoping.**

No data-dep ADR is required for Priorities 1, 2, or 4 (all use already-available SPY bars / position state).

---

## §6 — Continuous breaker monitoring (NEW, Review v2 Critical Issue #5 — HIGH priority)

**Problem:** `CircuitBreakerService.check()` only runs at order submission, so a portfolio that crashes overnight (no orders submitted) never trips the daily-loss breaker until the next order attempt. Operationally unacceptable.

**Build:** a ~1-minute APScheduler job (in `lifespan`/the engine) that calls `CircuitBreakerService.check()` for every account with open positions — trips + HALTs the same way the order-path check does. Purely additive, self-contained, no new data dependency. (This is the job already noted as "P5+ polish" in `docs/runbook/risk-gates.md`; Review v2 elevates it.) Tests at the risk-engine bar (ADR 0004; ≥95% coverage).

## §7 — Fractional shares (NEW, Review v2 Critical Issue #6 — elevated, possibly ahead of §2)

**Problem:** whole-share sizing on the ~$10k book deploys only ~67% and systematically biases *away* from expensive mega-cap momentum leaders — distorting factor exposure, diversification, and backtest realism.

**Build:** fractional-qty support through the order path (OrderRouter / Alpaca adapter — Alpaca supports fractional) + strategy sizing (`Decimal` fractional qty instead of `floor`). Touches the order path → risk-engine + audit discipline; needs its own session doc. Biggest single deployment-realism win.

## §8 — Universe breadth / survivorship (NEW, the open half of Review v2 Critical Issue #1)

**Problem:** the broad-history ingest fixed history *depth* (28.5 yr) but the candidate pool is *today's* active mega/large names — so a historical `universe_asof` (e.g. 2008) can't include names that were large then but have since delisted (survivorship bias in historical backtests). SEP is survivorship-free *per ticker*; the *pool selection* is not.

**Build:** derive a point-in-time, survivorship-unbiased candidate pool (e.g. top-N by trailing dollar-volume from the full `TICKERS` set per as-of date, including delisted names) and ingest their SEP history. This is the prerequisite for trustworthy GFC/2011/2015-era backtests and any LIVE alpha claim. Larger ingest; sequence after the overlays are validated on the (biased-but-informative) current pool.

---

## §9 — Deferred data models & methodology (review comments §2)

The second-pass review asked for these to be *defined now* even though they're deferred — pre-committing the shapes prevents schema churn later. None are built yet; this is the agreed target.

### §9.1 Future data models (placeholders, not yet tables)

```
portfolio_snapshots                 factor_exposures              correlation_snapshots
- ts                                - ts                          - ts
- account_id                        - strategy_id                 - symbol_a
- gross_exposure / net_exposure     - factor_name                 - symbol_b
- cash / equity                     - exposure_value              - correlation
- unrealized_pnl / realized_pnl                                   - window
- leverage / drawdown_pct
- vol_scale
```

- `portfolio_snapshots` is the accounting time-series the breaker, overlays, reconciliation, and walk-forward analytics will all read instead of recomputing on demand. (Today the breaker computes gross/PnL on the fly — see momentum status §5J.)
- `factor_exposures` / `correlation_snapshots` back the correlation/sector/factor overlays. Defining them now fixes the keys the overlay engine will join on.

### §9.2 Overlay-engine action semantics (formal invariant)

The overlay engine, when built, has exactly one job and a hard boundary:

> **The overlay engine only modifies *target gross exposure* (and per-bucket caps). It never selects symbols, never emits orders, and never overrides the alpha engine's name choices.** Selection ownership stays with the alpha (momentum) engine; the overlay scales/【caps】 the book the alpha produced.

Concretely: alpha emits target weights → overlay applies a risk multiplier / gross target / sector cap → the (unchanged) selection is sized to the adjusted gross → orders route through the OrderRouter as today. This makes the vol-scale (§1) and sector-cap (§3) overlays instances of one pattern, and keeps the audit trail clean (selection vs. sizing are separable).

### §9.3 Survivorship-bias PIT methodology (short spec)

The point-in-time methodology the §8 unbiased-pool work must follow:

- **Delistings:** a delisted name's final price is realized to cash on its last trading day; it is *not* dropped from history (SEP is survivorship-free per ticker).
- **Bankruptcies:** treated as a delisting to ~0; the loss is realized, not silently removed.
- **Mergers/acquisitions:** position closed at the deal price on the effective date; no forward-fill past it.
- **Ticker reuse:** symbols are mapped by Sharadar's permanent ticker identity, not the string — a reused ticker is a *different* entity, never chained across the gap.
- **As-of selection:** the candidate pool for date *D* is built only from names tradeable *at D* (including those later delisted) — never from today's survivors.

### §9.4 Backtest execution-cost assumptions (baseline)

So results aren't over-read, every current backtest assumes:

- **zero commissions** (Alpaca is commission-free for US equities),
- **market-order execution at the bar price** (no limit modeling),
- **no market-impact model**,
- **no borrow/short costs** (the book is long-only).

These are *optimistic* — real fills include spread/slippage. Treat backtested Sharpe/return as an upper bound; a configurable bps slippage+commission model is the first realism upgrade (out of scope here).

---

## Out of scope for P10 (the review's "delay everything")

- ML / predictive overlays of any kind.
- Advanced / multi-state regime models (beyond the binary filter + continuous vol scale).
- Nonlinear or optimization-based weighting (full risk parity, mean-variance).
- Macro composite signals.
- New alpha signals / factors (P10 is risk engineering, not alpha — that's the P9 §5+ FMP factor work, tracked separately).
- Execution-cost modeling in live sizing (item 8) — backtest realism only, later.
- Per-name stop losses (review: correctly avoided; do not add).

---

## Notes & gotchas

1. **Priority 1 is default OFF and inert for the live paper book (id=2).** Enabling it on the live book requires (a) a broader-history backtest and (b) a deliberate param update + reload — not a code default flip.
2. **`strategies_user/` is volume-mounted; `app/` is baked into the backend image.** A `momentum_portfolio.py` edit is picked up on the next reload/restart; a `backtest.py` (or any `app/`) edit needs `docker compose build backend`. The v0.4.0 work was tested via the **host venv**, not the container, precisely to avoid a rebuild that would perturb the running paper strategy.
3. **The §1 backtest window is short and momentum-friendly** (store is `--from 2024-06-01`). Do not over-read the return haircut; the drawdown/Sharpe improvement is the signal. Broaden SEP history before enabling vol scaling live.
4. **Schema-parity invariant:** any new param must land in BOTH `default_params` and `params_schema` (the `test_schema_matches_default_params` test + the frontend form depend on it).
5. **Do not regress the reviewed-and-praised behaviors:** fail-open-regime / fail-hold-factor-data, no per-name stops, rebalance-crash-retry, turnover threshold + rank hysteresis.
6. **§2's daily overlay is the one item with a genuine framework question** (single vs. dual cron cadence) — resolve it in a dedicated session doc + likely a small ADR before writing code.
