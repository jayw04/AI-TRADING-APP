# P9 Session §4 v0.1 — Momentum-Portfolio Strategy (MTG Template), Paper-Only

| Field | Value |
|---|---|
| Document version | v0.1 (draft — §3 decisions to confirm before coding) |
| Date | 2026-06-14 |
| Phase | **P9** — Point-in-time data backbone + multi-factor equity model |
| Session | **§4 of P9** |
| Predecessor | P9 §3 — weekly cross-sectional momentum backtest (PR #102, stacked on §2 #101) |
| Successor | P9 §5+ — FMP fundamentals + value/quality/earnings/13F factors |
| Repository | `github.com/jayw04/AI-TRADING-APP` |
| Governing ADRs | 0002 (**single OrderRouter** — every rebalance order flows through `ctx.submit_order`), 0005 (24h activation cooldown — live only; §4 is paper), 0014 (backtests = ground truth — §3's backtest is the factor's edge evidence), 0018 (PIT factor data), 0006 v2 (no LLM in the path — deterministic) |
| Scope | Express the §2/§3 momentum book as a **deterministic Strategy** that the engine runs: a weekly (cron-scheduled) cross-sectional rebalance that reads `ctx.factors`, holds the equal-weight top quintile within a fixed candidate universe, and submits every rebalance order through `OrderRouter` + the risk engine. **Paper-only** (no live in P9, Direction §6). |
| Estimated wall time | 6–9 hours (the strategy + the rebalance-diff logic + the MTG spec + unit tests against a synthetic context; the actual paper *activation run* is a separate market-hours verification step) |
| Tag on completion | `p9-session4-complete` |
| Out of scope | **Live** (any → LIVE; P9 is paper-only), FMP/fundamental factors (§5+), a portfolio-strategy framework hook (we fit the existing `schedule`+`on_bar` model — §3.1), intraday signals, dynamic weekly universe re-registration, the actual market-hours paper-activation drive (a Jay-gated verification step, §5 of this doc) |

---

## 0b. v0.2 — review hardening (2026-06-14, owner-directed)

After the v0.1 build, the owner's strategy review drove a `momentum-portfolio`
v0.2 (the version on `main`). Changes (all in `momentum_portfolio.py`, with a new
read-only `StrategyContext.get_account_equity()` accessor):

1. **Rebalance week marked only on success.** `on_bar` runs `_rebalance()` then sets
   `_last_rebalance_week`; an unexpected exception logs `rebalance_failed` and does
   **not** mark the week, so the next tick retries (a deliberate factor-data HOLD
   still counts as handled and marks the week).
2. **Live equity sizing.** Sizes from `ctx.get_account_equity()` (the
   `accounts_state` broker snapshot), falling back to `initial_equity_estimate`
   only when no snapshot exists. (Resolves v0.1 Finding 7. The new accessor is
   read-only — `accounts_state` scoped to the strategy's account, no broker/network.)
3. **Turnover control.** `min_trade_pct` (default 3%) skips adjustments to existing
   positions below that fraction of target notional; `rebalance_buffer_rank_pct`
   (default 5%) keeps a held name that is still within `(top_quantile + buffer)` of
   the cut (rank hysteresis) — both damp churn from boundary names.
4. **`min_score` defaults to 0.0** — avoid buying negative-momentum names by default.
5. **Market-regime filter.** When `use_market_regime_filter` (default on) and the
   market proxy (`market_filter_symbol`, default SPY) closed below its
   `market_ma_days` (200) MA, the book goes **risk-off to cash** (sell to flat). It
   **fails open** (trades, logs `regime_filter_unavailable_failopen`) if the SPY
   series is unavailable — so a data gap can't silently halt the book. **NB:** the
   proxy must be in the registered `symbols` for the filter to read it.
6. **Daily pricing.** `pricing_timeframe` defaults to `1Day` (a Monday-open intraday
   bar is incomplete).
7. **Defensive sort + cash buffer + position cap.** Scores are `sort_values`'d
   before the cut; `cash_buffer_pct` (2%) is held back; `max_position_pct` (10%) caps
   any single name.

20 unit tests cover each (incl. the failure-retry, regime bull/bear/fail-open,
live-vs-estimate, turnover, and hysteresis paths). The §3–§8 body below describes
the v0.1 shape; where it differs, v0.2 above is authoritative.

---

## 1. Why this session exists

§1–§3 proved the data, the signal, and the edge in a standalone backtest. §4 is
where the factor book becomes a *first-class platform citizen*: a Strategy the
engine schedules, whose every rebalance order passes through the **single
OrderRouter** and the **risk engine**, and whose decisions are **audit-logged** —
the same disciplined path manual and other strategies use (ADR 0002). The point
of §4 is not new signal; it is to show the momentum book runs *through the
platform's safety machinery*, paper-only, exactly as a real systematic book would.

The honesty hinge here is different from §1–§3: it is **isolation + routing**, not
survivorship. The strategy must reach factor data only through `ctx.factors`
(§2's sandbox), trade only its declared universe, and submit only through
`ctx.submit_order` — never the broker, the DB, or the network directly. The
existing CI invariants (strategy-isolation, single-router) must stay green.

## 2. The strategy, on the MTG template

The momentum book expressed through the MTG strategy-spec lens
(`Docs/Strategies/Trading+Plan+Clean.pdf`):

| MTG field | This strategy |
|---|---|
| **Strategy** | Cross-sectional price-momentum portfolio |
| **Style** | Systematic / rules-based, cross-sectional equity factor |
| **Type** | Long-only equity factor book (momentum) |
| **Holding Period** | ~1 week — positions held until the next weekly rebalance |
| **Stock Selection** | Top quintile by 6–1 month momentum **z-score** (§2), within a fixed top-N liquidity candidate universe (§1) |
| **Entry Signal** | Weekly rebalance: a name that is in the target top quintile and not yet held |
| **Entry Style** | Market order at rebalance, sized to an equal target weight |
| **Take Profit Signal** | None discrete — a name exits when it **drops out of the top quintile** at the next rebalance |
| **Take Profit Style** | Rebalance-driven (no fixed price target) |
| **Position Sizing** | Equal weight: target notional = `equity / k` per held name |
| **Stop Loss** | None per-name intraday — risk is managed by **diversification + weekly turnover** and the centralized risk engine (position/exposure/daily-loss caps), not a per-name stop |
| **Take Loss Style** | Rebalance-driven — a loser leaves the book when it falls out of the quintile |
| **Bail-Out Indicator** | The centralized circuit breaker / daily-loss cap (risk engine) halts the book; if factor data is unavailable, the strategy **holds** (no rebalance) rather than trading blind |

## 3. Decisions (locked 2026-06-14, owner)

1. **★ Session scope = build + unit-test the strategy + document the activation
   path (owner choice).** Ship the `MomentumPortfolio` strategy, its rebalance/diff
   logic, and unit tests against a synthetic `StrategyContext`; document the
   activation path. The actual market-hours **paper-activation drive** (register →
   activate to PAPER → observe a real weekly rebalance fill) is a **separate
   Jay-gated verification step** (§5) — same posture as the deferred §2-variant live
   work. Keeps §4 a clean, mergeable code PR.
2. **Rebalance cadence = weekly, Monday ~09:00 ET (owner choice).**
   `schedule = "0 14 * * 1"` (14:00 UTC). Rebalance at the week's start near the US
   open — a clean, liquid moment.
3. **Book size = top-200 liquidity candidates → ~10 held (owner choice, revised
   2026-06-14 per review Finding 2).** `symbols` at registration = top-**200**
   liquidity universe; hold the top ~10 (`max_names=10`) equal weight. The earlier
   top-50 choice was revised: top-50-by-dollar-volume is effectively mega-caps,
   where the momentum premium is historically *weakest*; top-200 keeps the book
   legible (~10 names) while selecting from the broader segment where the §3 edge
   actually lives. **Standardization scope:** the strategy calls
   `momentum_scores(n=len(ctx.symbols))` so z-scores are standardized over the
   registered candidate universe (the names actually tradeable), and the §3
   edge-evidence backtest is re-run at the **deployment config (n≈200)** — not only
   the n=500 default (§4.3).
4. **Position sizing = equal target notional `equity/k`, whole shares, market
   orders.** Fractional shares deferred (keeps the paper book legible and avoids an
   Alpaca fractional-order path in v1).

## 4. Detailed work

### 4.1 The strategy file (additive)

```
apps/backend/strategies_user/templates/momentum_portfolio.py   # the Strategy
apps/backend/tests/strategies/test_momentum_portfolio.py        # unit tests
```

A user-space strategy (under `strategies_user/`, the hot-reload root), so it is
**not** subject to `check_strategy_isolation.sh` import limits the way `app/`
engine code is — but it still reaches data/orders only through `ctx` by
construction (there is no other handle). It imports nothing from `app.brokers` /
`app.orders` directly.

```python
class MomentumPortfolio(Strategy):
    name = "momentum-portfolio"
    version = "0.1.0"
    symbols = []                     # set at registration = top-N liquidity candidates
    schedule = "0 14 * * 1"          # weekly, Mon 14:00 UTC (§3.2, to confirm)
    default_params = {
        "top_quantile": 0.20,        # hold the top 20% by score…
        "max_names": 10,             # …capped at k names
        "min_score": None,           # optional score floor (None = no floor)
    }
    params_schema = { ... }          # typed form (enum/number/integer), kept in sync w/ params
```

### 4.2 The weekly rebalance (inside `on_bar`, fired by the cron tick)

The engine's cron tick calls `on_bar` once per symbol; the strategy **rebalances
once per week on the first call of a new ISO week** and no-ops the rest:

```python
async def on_bar(self, bar: Bar) -> None:
    wk = bar.t.isocalendar()[:2]
    if wk == self._last_rebalance_week:
        return                        # already rebalanced this week
    self._last_rebalance_week = wk
    await self._rebalance(as_of=bar.t.date())
```

`_rebalance`:
1. `scores = self.ctx.factors.momentum_scores(n=len(self.ctx.symbols))` (PIT; §2).
   Passing `n` = the registered universe size standardizes z-scores over the
   **tradeable candidate universe** (not the accessor's broad `n=500` default), so
   the quintile cut and the z-scores share one cross-section (review Finding 2).
   On any of `FactorDataUnavailable` / `FactorUnavailable` / `UniverseUnavailable`
   → **hold** (log + return; the bail-out rule — see §8 note 3).
2. `eligible = scores[scores.index.isin(self.ctx.symbols)]` — only the tradeable
   candidate universe (mostly a no-op now that scores are standardized over it).
3. `target = ` top `ceil(len(eligible) * top_quantile)` capped at `max_names`,
   `min_score` floor applied → equal target weight `1/k`.
4. `current = ` per-symbol `ctx.get_position_for(sym)` over the candidate set
   (keyed by ticker; `get_positions()` keys by `symbol_id`).
5. **Diff → orders** through `ctx.submit_order` (every order, ADR 0002),
   **all SELLs before any BUYs** so exited capital is freed first (review Finding 6):
   - names in `current` but not `target` → **SELL** to flat;
   - names in `target` → **BUY/adjust** toward `equity/k` notional (whole shares).
   - **Rejection policy:** log-and-continue per name (a risk-engine rejection on
     one order never aborts the rest of the rebalance).
6. `ctx.log_signal(...)` the rebalance decision per name (audit trail).

Equity for sizing: a static `_equity_estimate` param in v1 (same pattern as
`range_trader.py`). **Known limitation (review Finding 7):** a rebalancing book
should size from *live* account equity; `StrategyContext` does not expose account
equity/buying-power today, so v1 uses the estimate. Adding a `ctx` equity accessor
is a follow-up (`# VERIFY-CAPABILITY-EXISTS` before relying on one).

### 4.3 Backtest evidence (ADR 0014)

The factor's edge is evidenced by **§3's standalone cross-sectional backtest**
(the honest, survivorship-free ground truth), **re-run at this strategy's
deployment configuration** (n≈200 → ~10 held; review Finding 2) — not only the §3
default `n=500` book. The n=500 run stays the broad-cross-section reference; the
deployment-config run is the artifact that justifies *this* book. If the
deployment-config edge is materially weaker than the n=500 reference (expected,
given mega-cap momentum decay), that is a decision input surfaced *before* paper
activation. The framework's per-strategy `Backtester` (bar-driven, single-name,
Alpaca bars) is **not** the right tool for a cross-sectional book and is **not**
retrofitted here.

**Activation prerequisite (review Finding 8 — resolved):** the "recent backtest
within 7 days" prerequisite in `ActivationService.check_prerequisites` gates
**LIVE** activation only (`initiate → PENDING_LIVE`). **PAPER** registration does
**not** require it, so §4's paper drive is unblocked. (A future LIVE promotion —
out of P9 scope — would need either a framework `Backtester` run or an accepted
external-reference path; decide then.)

### 4.4 Tests (the load-bearing ones first)

- **★ Rebalance-once-per-week**: many `on_bar` calls within one ISO week →
  exactly one rebalance; a call in a new week → a new rebalance.
- **★ Selection + diff**: with a synthetic `ctx` whose `factors.momentum_scores()`
  returns a known cross-section and `get_positions()` a known book, assert the
  exact SELL/BUY order set (leavers sold, joiners bought, sized to `equity/k`,
  whole shares), all via `ctx.submit_order`.
- **★ Bail-out taxonomy**: `momentum_scores()` raising **each** of
  `FactorDataUnavailable` / `FactorUnavailable` / `UniverseUnavailable` → no orders,
  strategy holds, one hold signal logged (review Finding 1).
- **★ Isolation**: names outside `ctx.symbols` are never ordered; no
  `app.brokers`/`app.orders` import in the strategy file.
- **Rejection log-and-continue**: a rejected SELL does not block the BUY batch
  (review Finding 6).
- **Params**: `params_schema` matches `default_params` (the drift gotcha in
  CLAUDE.md — code params ⇿ schema). `min_score` is a **nullable** number
  (default `None` = no floor) so the typed form round-trips (review Finding 10).
- Unit tests use a **fake/synthetic `StrategyContext`** (record submitted orders),
  not the live engine — fast and deterministic. Reuse the §2 synthetic factor
  store for `ctx.factors`.

## 5. Manual smoke / paper-activation (the Jay-gated verification step)

§4 ships the strategy + tests; the **live paper run** is a market-hours
verification (its own step, like the §2-variant live work):

1. Ingest a broad pool so the universe/quintiles are real (`docs/runbook/factor-data.md` §4).
2. Register `momentum-portfolio` with `symbols` = top-200 liquidity, on the paper account.
3. Activate to **PAPER**; on the next weekly cron tick (or a manual trigger),
   observe a rebalance: `momentum_scores` → top-10 → real `OrderRouter.submit`
   paper orders → fills → positions reflect the equal-weight book.
4. **Pass:** the paper book holds ~10 equal-weight top-momentum names, every order
   shows `source_type=STRATEGY` in the audit log, and the risk engine evaluated
   each (ADR 0002). No live account is touched (P9 is paper-only).

## 6. Walk-away discipline

≥ 1 hour for the strategy + tests PR (no order-path/risk/audit *code* change — the
strategy *uses* those paths, it does not modify them). The separate paper-activation
verification is gated on Jay + market hours, not a walk-away timer.

## 7. What this session does NOT do

- **No live trading.** P9 is paper-only (Direction §6); LIVE activation (24h
  cooldown, ADR 0005) is out.
- **No framework change** — no new portfolio/rebalance hook; we fit the existing
  `schedule` + `on_bar` + `ctx` model (§3.1 finding).
- **No FMP / multi-factor / value / quality** — §5+.
- **No fractional shares**, no portfolio optimizer, no per-name stops (factor book
  risk is diversification + the centralized risk engine).
- **No dynamic weekly universe re-registration** — the candidate universe is fixed
  at registration; selection happens within it.
- **No `BarCache` refactor**, no LLM (ADR 0006 v2).

## 8. Notes & gotchas

1. **Rebalance once per tick, not per symbol.** The cron tick calls `on_bar` per
   symbol; guard on the ISO week so the book rebalances once. (Framework has no
   portfolio hook — §3.1.)
2. **Intersect scores with `ctx.symbols`.** `momentum_scores()` spans the full
   `universe_asof`; the strategy can only trade its declared allowed-list — select
   the top quintile *within* it, or orders for unlisted names silently no-op.
3. **Hold on ANY "no factor data" exception (review Finding 1).** Catch
   `FactorDataUnavailable` **and** `FactorUnavailable` (thin cross-section — the
   *likeliest* trigger) **and** `UniverseUnavailable` (below floor) — not just the
   no-store case. Catching only one (or a bare `except Exception` that swallows
   real bugs) is the trap; the strategy catches the explicit three. This is the
   MTG "Bail-Out" row.
4. **params_schema ⇿ default_params in sync** (CLAUDE.md proven-costly list) — the
   typed form derives from the schema; drift breaks the UI. `min_score` is a
   nullable number (`None` = no floor) so the empty form value round-trips.
5. **Every order through `ctx.submit_order`.** No broker/DB/network in the strategy
   — ADR 0002 + strategy isolation. The risk engine evaluates each rebalance order.
6. **Restart safety (review Finding 5).** The in-memory `_last_rebalance_week`
   resets on restart, so the next tick rebalances — but because step 5 trades the
   **diff against actual positions**, a redundant rebalance is a near-no-op (only
   drift trims), not a full sell/buy churn. The diff also makes the rebalance
   idempotent under replay.
7. **Sells before buys; live-equity is a known gap (Findings 6, 7).** Submit all
   sells before any buys (free capital first), log-and-continue on a rejection.
   Sizing uses a static equity estimate in v1 — a rebalancing book ideally reads
   live equity (no `ctx` accessor for it yet).
8. **Fixed-UTC cron drifts across DST (review Finding 10).** `"0 14 * * 1"` is
   09:00 ET in winter but **10:00 EDT** in summer. Fine for "rebalance near the
   open," but the offset to the 09:30 ET open is not stable year-round.
9. **The paper drive is market-hours + Jay-gated.** Don't claim §4 "runs in paper"
   from unit tests alone; the live paper rebalance is the §5 verification step.
