# P9 Direction Document v0.1 — Point-in-Time Data Backbone + Multi-Factor Equity Model

| Field | Value |
|---|---|
| Document version | v0.2 (open questions resolved 2026-06-13; ready to draft §1) |
| Date | 2026-06-13 |
| Phase | **P9** — follows P8 (Discovery + Range Insight) |
| Status | Direction-set. Section 7 decisions locked; §0/§1 per-session docs may now be drafted. |
| v1 decisions | DuckDB PIT store · S&P 500 universe · weekly rebalance · **price-momentum** first factor (one factor end-to-end) · paper-only · accept ~5y FMP (fundamentals deferred) |
| Predecessor | P8 — Discovery view + Range Insight (tag `p8-q4-scan-apply-template-complete`; P8 closed) |
| Successor | TBD |
| Repository | `github.com/jayw04/AI-TRADING-APP` |
| Governing ADRs | **0018** (FMP + Sharadar PIT factor data — new, Draft), 0014 (backtests = primary eval ground truth), 0002 (single OrderRouter), 0005 (24h activation cooldown), 0006 v2 (no LLM in order path), 0017 (OS trust store for outbound TLS) |
| Inputs | Owner data-coverage analysis (`data/Data available 1.jpg`, `data/Data available 2.jpg`); MTG strategy-spec template (`Docs/Strategies/Trading+Plan+Clean.pdf`) |

---

## 1. Why P9 exists

P0–P8 built a disciplined **single-name, price/indicator** platform: manual + systematic
trading through one OrderRouter, a deterministic backtest harness, an agent advisory
layer, live trading behind cooldowns, and a Discovery screener seeded by Alpaca feeds.
What it has never had is **fundamental, institutional, macro, or survivorship-free
historical data** — so it cannot express, or honestly evaluate, a **cross-sectional
multi-factor equity model** (rank a universe by value / quality / growth / momentum /
institutional-flow / earnings signals and trade the spread).

The owner now has two data subscriptions that, together, supply exactly the inputs such
a model needs. P9's job is to turn those subscriptions into a **point-in-time data
backbone** and build the **first honest multi-factor model** on top of it — without
weakening any of the order-path, risk, or audit invariants that define the platform.

The discipline that matters most here is **honesty of evaluation**. Per ADR 0014,
backtests are the platform's ground truth. A factor backtest is trustworthy only if its
data is **survivorship-free** (includes delisted names) and **point-in-time** (joins each
date to what was knowable then). P9 is as much about building that PIT discipline into the
data layer as it is about the factors themselves.

## 2. The data backbone (per ADR 0018)

Two new read-only external dependencies, adopted under ADR 0018:

| Source | Role | Key datasets |
|---|---|---|
| **Nasdaq Data Link → Sharadar (FULL)** | Survivorship-free price + universe + 13F spine | `SEP` (adj. prices 1998+, incl. delisted), `TICKERS` (as-of universe), `ACTIONS` (splits/divs/delistings), `SF3` (13F institutional holdings) |
| **FMP** | Fundamental + macro + earnings layer | financials/ratios (~5y Starter depth), earnings surprises, treasury/economic series |

**Design constraint (the depth split):** price/return factors are computed from Sharadar
(deep, to 1998); fundamental factors accept the ~5y FMP window. Deep-history factor
backtests price from Sharadar and tolerate the shorter fundamental window (or an FMP tier
upgrade extends it later). Sample-only Sharadar tables (`SF1`, `DAILY`, `METRICS`/`SFP`)
are **not** relied upon — FMP covers fundamentals.

**Coverage honestly stated:** survivorship-free prices ✅ (Sharadar), fundamentals ✅
(FMP, ~5y), institutional flow ✅ (SF3), earnings surprises ✅ (FMP), macro ✅ (FMP).
Genuine gaps, **out of scope for P9**: news/social sentiment, options flow, intraday/tick.

## 3. What P9 ships (capabilities, not sessions)

1. **A point-in-time data backbone.** A provider abstraction in `app/market_data/` plus a
   local PIT store: Sharadar price/universe/actions/13F + FMP fundamentals/macro, with an
   **as-of universe** (`universe_asof(date)`) and **as-of fundamentals** so every join is
   look-ahead-free and survivorship-free.

2. **A factor library.** Deterministic, testable factor definitions computed from the PIT
   store — e.g. value (earnings/FCF yield, B/P), quality (margins, ROIC, accruals),
   growth, price momentum, **institutional-ownership** (SF3), earnings-surprise — each a
   pure function of as-of data, with a cross-sectional standardization (z-score / rank).

3. **A survivorship-free factor backtest.** A cross-sectional backtest path (universe →
   factor scores → portfolio construction → periodic rebalance → returns incl. delistings)
   that reuses the existing backtest discipline and reports against a baseline per ADR 0014.

4. **The first multi-factor strategy**, expressed through the **MTG strategy-spec template**
   (Style / Type / Holding Period / Stock Selection / Entry Signal / Entry Style / Take
   Profit / Position Sizing / Stop Loss / Bail-Out) — so the factor model is defined in the
   same lens the owner uses for every strategy, and routes orders through the existing
   OrderRouter / risk / activation path unchanged.

5. **Discovery + Range Insight enrichment.** Fundamental and institutional filters added to
   the Discovery screener (market cap, valuation, ownership, sector) and, where it fits,
   surfaced in the symbol panels — the native version of the "stock selection" the screener
   has only approximated from price/volume so far.

## 4. Architecture fit

- **Order path unchanged (ADR 0002).** The new vendors are read-only data. Factor signals
  influence *which* orders a strategy proposes; the order still flows through
  `OrderRouter.submit`, the risk engine, and (for live) the activation/cooldown gates.
- **Provider abstraction.** Alpaca's hardcoded fetch is refactored behind a typed source
  interface; `BarCache.get_bars` keeps its contract. Live execution + quotes stay Alpaca.
  `# VERIFY-CAPABILITY-EXISTS` — this is a non-trivial refactor of a load-bearing path that
  backtests, Range Insight, and the P6 §2-variant equity-curve reconstruction all depend on.
  The §1/§2 plan must first confirm the **exact current `BarCache.get_bars` signature and
  every caller** before refactoring behind an interface (the assumed-signature class of error,
  cf. the §4 `call_with_budget` fabrication).
- **Strategy access is sandboxed and explicit.** Strategies reach data only through
  `StrategyContext` (which today wraps `BarCache`). P9 adds a **factor/fundamental
  accessor** to the context — a deliberate, reviewable extension point; strategies still
  cannot reach the network or the DB directly.
- **Backtester reads PIT data.** The cross-sectional backtest path consumes the PIT store's
  as-of joins; the existing single-name `Backtester` is unchanged.
- **Credentials + TLS (ADR 0018, 0017).** Vendor keys are `Settings` env-aliases
  (`FMP_API_KEY`, `NASDAQ_DATA_LINK_API_KEY`); outbound calls use the OS-trust-store path.
- **No LLM in the data/order path (ADR 0006 v2).** Factor computation is deterministic
  Python. Any LLM involvement (e.g. agent commentary on factor exposures) stays advisory
  and outside the order path.

## 5. Session breakdown

Sequencing reflects the Section 7 decisions: the v1 factor is **price momentum**, which
needs only the **Sharadar price/universe spine** — so v1 front-loads that and **defers the
entire FMP fundamental layer** (and the SF3/13F + value/earnings factors) to later sessions.
This is the "prove the pipe with one factor" order the owner chose. Per-session docs are
drafted from here.

- **§0 — Data access verification (Session Zero).** Smoke both keys end-to-end from the
  host venv (a Sharadar `SEP`/`TICKERS` pull + a token FMP call), confirm the OS-trust-store
  path reaches both vendors, document rate limits + depth. Go/no-go; ships no product code.
- **§1 — Sharadar price/universe spine in DuckDB.** Ingest `SEP` (survivorship-free adj.
  prices, incl. delisted) + `TICKERS` + `ACTIONS` into a local **DuckDB** PIT store; build
  `universe_asof(date)` constrained to **S&P 500** membership; survivorship-free price
  access. (SF3/13F deferred — not needed for momentum.)
- **§2 — Price-momentum factor + factor accessor.** A deterministic momentum factor
  (e.g. 12-1 month total return), cross-sectional standardization (z-score/rank), the new
  sandboxed `StrategyContext` factor accessor, and tests. Prices-only — no FMP dependency.
- **§3 — Survivorship-free weekly factor backtest.** Cross-sectional backtest path:
  `universe_asof` → momentum scores → portfolio construction → **weekly** rebalance →
  returns *including delisted names*; baseline comparison + reproducibility test (ADR 0014).
  **Named decision for §3's v0.1:** the **delisting-return mechanism** — the return a name
  realizes on its last day when it delists/acquires mid-holding-period (e.g. final price → cash,
  or an applied delisting return). "Returns incl. delistings" is the honesty hinge on the
  *backtest* side; the exact mechanism must be decided in §3's plan, not discovered during
  implementation.
- **§4 — First factor strategy (MTG template), paper-only.** The momentum book expressed
  through the MTG strategy-spec template, taken through backtest → paper via the standard
  lifecycle. **No live** in P9 (Section 6).
- **§5+ (later) — FMP fundamental + macro ingestion → fundamental factors + Discovery
  enrichment.** Adds the FMP layer (as-of fundamentals, earnings, macro), then value /
  earnings-surprise / 13F factors, and fundamental/ownership filters in Discovery. This is
  where the ~5y FMP depth and SF3 come in — after the price slice is proven.

## 6. Out of scope for P9

- **News / social sentiment, options flow, intraday/tick data** — acknowledged real gaps;
  each would be its own dependency decision (new ADR).
- **Live factor auto-trading at scale** — a factor strategy may go live through the normal
  activation/cooldown path, but any *unattended multi-name rebalancing into real money* is
  a separate, gated decision (interacts with P6b §4.5 auto-dispatch + per-order friction).
- **LLM-driven factor selection / weighting in the order path** — out; deterministic only
  (ADR 0006 v2). LLM commentary stays advisory.
- **Multi-user / hosted deployment + the credential-storage change it implies** (ADR 0018
  re-evaluation trigger).
- **Replacing Alpaca** for execution or live quotes — Alpaca stays the broker + live feed.
- **Redistributing raw vendor datasets** over the API or MCP (ADR 0018 licensing posture).
- **An FMP tier upgrade** to extend fundamental depth — a later call, not assumed here.

## 7. Decisions (resolved 2026-06-13)

The Section 7 open questions were settled with the owner via the decision-turn process:

1. **PIT store format → DuckDB.** Embedded columnar engine; cross-sectional rank-the-
   universe scans are its sweet spot; local-first, zero server.
2. **Universe → S&P 500.** Large-cap, fastest honest first cut. Survivorship-free handling
   still applies *within* historical S&P 500 membership (names that left the index / delisted
   are included as-of). Widening to Russell 1000 / full universe is a later call.
3. **Rebalance cadence → weekly.** Fills the MTG template "Holding Period"; drives a
   weekly cross-sectional backtest. (Pairs deliberately with a price factor — see #4.)
4. **Factor scope → one factor end-to-end first: price momentum.** Prove the full pipe with
   a single prices-only factor before stacking factors. Momentum fits the weekly cadence and
   needs only the Sharadar price spine (no FMP), which is why it leads.
5. **Fundamental depth → accept ~5y FMP (deferred).** v1 is price-based, so the FMP window
   doesn't gate it; price factors still backtest to 1998. Revisit an FMP upgrade when
   fundamental factors arrive (§5+).
6. **Live vs paper → paper-only for P9.** Factor strategies validate through backtest →
   paper only; live deferred to a later, separately-gated decision (conservative default).
7. **Derived factor-score storage → recompute on demand for v1** (materialize later only if
   recompute proves slow). Keeps freshness simple; revisit as a perf optimization.
8. **Licensing → action item before §1 ships.** Confirm Sharadar + FMP terms permit the
   intended local computation and that no surface re-exposes raw vendor tables (ADR 0018 §6).
   Tracked as a §0 / §1 prerequisite, not a blocker to drafting.

## 8. Notes & gotchas

1. **The keys are already in `.env`** as `FMP_API_KEY` and `NASDAQ_DATA_LINK_API_KEY`
   (values not reproduced here). Per ADR 0018 they are `Settings` env-aliases, not
   CredentialStore entries.
2. **TLS is already solved.** ADR 0017's OS-trust-store path (default-on) means Sharadar +
   FMP calls work under Norton inspection from the host venv with no toggle — proven by the
   P2 AAPL-fixture generation on 2026-06-13.
3. **Survivorship-free is the whole point.** The single easiest way to ship a dishonest
   factor backtest is to build the universe from *today's* listed names. `TICKERS` +
   `ACTIONS` exist precisely to avoid that; any universe construction that ignores delisted
   names is a bug, not a simplification.
4. **Depth split is a design input, not an afterthought.** Price factors: Sharadar to 1998.
   Fundamental factors: FMP ~5y. A backtest that silently mixes the two windows will mislead.
5. **The MTG template is the strategy lens.** Every strategy the owner defines maps to
   Style / Type / Holding Period / Stock Selection / Entry / Take Profit / Position Sizing /
   Stop Loss / Bail-Out — the multi-factor strategy should be expressible in those terms,
   not as an opaque optimizer.
6. **This is direction, not a plan.** No code is written against this document. §1 is drafted
   only after Section 7 is resolved (Retrospective Rec #10: do not draft sessions
   speculatively before direction is settled).
