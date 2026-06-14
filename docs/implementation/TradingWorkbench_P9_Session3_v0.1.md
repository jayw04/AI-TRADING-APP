# P9 Session §3 v0.1 — Survivorship-Free Weekly Cross-Sectional Momentum Backtest

| Field | Value |
|---|---|
| Document version | v0.1 (draft — §3 decisions to confirm before coding) |
| Date | 2026-06-14 |
| Phase | **P9** — Point-in-time data backbone + multi-factor equity model |
| Session | **§3 of P9** |
| Predecessor | P9 §2 — price-momentum factor + sandboxed accessor (PR #101 / branch `feat/p9-session2-momentum-factor`) |
| Successor | P9 §4 — first factor strategy (MTG template), paper-only |
| Repository | `github.com/jayw04/AI-TRADING-APP` |
| Governing ADRs | 0014 (**backtests = primary eval ground truth** — this session *is* that, for the factor book), 0018 (PIT factor data), 0002 (single OrderRouter — untouched; a backtest submits no orders), 0006 v2 (no LLM in the path) |
| Scope | A standalone **cross-sectional** backtest path that runs the §2 momentum factor over the §1 PIT spine: weekly rebalance of an equal-weight book, a **daily mark-to-market** equity curve, **returns that include delisted names** via an explicit delisting-return mechanism, a passive baseline for comparison, and a reproducibility guarantee. Prices-only, paper-only, no orders. |
| Estimated wall time | 6–9 hours (backtest engine + daily mark-to-market + delisting handling + baseline + the survivorship/reproducibility tests that are the point) |
| Tag on completion | `p9-session3-complete` |
| Out of scope | The MTG factor strategy + lifecycle (§4), FMP/fundamental factors (§5+), live or paper *order* submission, DB persistence / UI of backtest results, portfolio optimization beyond equal-weight, transaction-cost modeling beyond a flat per-rebalance turnover cost, the `BarCache` refactor |

---

## 1. Why this session exists

§1 built the honest data; §2 built the honest signal. §3 is where the phase
earns its keep: a **survivorship-free, point-in-time backtest** that says whether
price momentum, run weekly over the liquidity universe, would have made money —
*including the names that delisted along the way*. Per ADR 0014 the backtest is
the ground truth a factor strategy must clear before it is allowed anywhere near
paper (§4), so §3's honesty is the gate for everything after it.

The two properties that make or break the session:

- **Returns include delistings.** A name held into its delisting must realize a
  return by an explicit, decided mechanism — never silently vanish from the book
  (which would inflate returns exactly the way a survivorship-biased universe
  does). This is the **named §3 decision** (§3 below, Direction §5) and must be
  pinned in this plan, not discovered in code.
- **No look-ahead, end-to-end.** Every rebalance at date `D` selects names from
  `momentum_scores(store, D)` (itself PIT, §2) and holds them forward; the equity
  curve reads only prices `≥ D`. Re-running the backtest, or extending the store
  with later data, must not change a historical equity point.

§3 is **standalone**: it does **not** touch the single-name `Backtester`
(`app/strategies/backtester.py`) or its `BacktestContext`. The cross-sectional
path consumes the §1 `FactorDataStore` directly (Direction §7). It reuses the
existing metric formulas (`app/strategies/metrics.py`: `sharpe_ratio`,
`max_drawdown`) so factor and single-name backtests report bit-identical math.

## 2. What this session ships

- **A cross-sectional backtest engine** (`app/factor_data/backtest.py`) —
  `run_momentum_backtest(store, start, end, ...) -> MomentumBacktestReport`:
  weekly rebalance → equal-weight book → daily mark-to-market → metrics.
- **A delisting-aware daily mark-to-market** — each held name's daily return comes
  from its `closeadj`; a name that delists mid-hold realizes the decided
  delisting return and its capital goes to cash until the next rebalance.
- **A passive baseline** — the equal-weight universe (same rebalance dates, same
  mark-to-market, same delisting mechanism), so the momentum book's excess return
  is meaningful (ADR 0014).
- **A `MomentumBacktestReport`** dataclass — daily equity curve, per-rebalance
  holdings + realized returns, and summary metrics (total return, CAGR, annualized
  Shardpe, max drawdown) for both the factor book and the baseline.
- **Tests** — survivorship (a delisted winner is held and realizes its mechanism
  return, not dropped) and reproducibility are load-bearing (§4.5), plus
  rebalance-date math, daily mark-to-market, baseline, and a tiny end-to-end run.
- A short **runbook** addition (`docs/runbook/factor-data.md` §5c) — how to run a
  backtest and read the report.

## 3. Decisions (locked 2026-06-14, owner)

1. **★ Delisting-return mechanism = final price → cash (owner choice).** When a
   held name's price series ends mid-holding-period (it delists / is acquired), it
   earns its daily returns up to its last trading day, realizes
   `last_closeadj / prev − 1` on that final day, and its sleeve then sits in **cash**
   until the next rebalance. Honest and fabrication-free (uses only `sep`), slightly
   optimistic (assumes exit at the last print). Defensible for a momentum **long**
   book: its holdings are recent winners, whose exits are dominated by acquisitions
   near/above the last price, not bankruptcies. (`ACTIONS`-classified haircuts were
   considered and deferred — a later refinement if §3's results look exit-optimistic.)
2. **Portfolio construction = long-only, equal-weight top quintile (owner choice).**
   Each rebalance, equal-weight long the top 20% by `score`, 100% invested, no
   shorts — matching the long-only paper book §4 will run. (Dollar-neutral
   long-short was considered; deferred — it isn't the §4 book and adds borrow
   realism the v1 backtest wouldn't model.)
3. **Rebalance cadence + timing.** Weekly (Direction §7). Rebalance on the **last
   trading day of each ISO week** in `[start, end]`; weights set from that day's
   `momentum_scores`, applied to the **next** trading day's returns onward (no
   same-bar look-ahead). Trading days = `sep` dates.
4. **Costs.** A flat **per-rebalance turnover cost** (default `10 bps` on traded
   notional) so the headline isn't cost-blind; defaulted conservative, configurable.
   No slippage model beyond this in v1.

## 4. Detailed work

### 4.1 Module layout (additive)

```
apps/backend/app/factor_data/
  backtest.py     # run_momentum_backtest + MomentumBacktestReport + delisting logic
apps/backend/tests/factor_data/test_backtest.py
docs/runbook/factor-data.md   # + §5c "Running a backtest"
```

`backtest.py` imports `app.factor_data` (store, universe, factors) +
`app.strategies.metrics` (reused formulas) + pandas/numpy. No order path, no
broker, no DB, no LLM.

### 4.2 The report

```python
@dataclass(frozen=True)
class MomentumBacktestReport:
    start: date
    end: date
    rebalances: list[date]
    equity_curve: list[tuple[date, float]]          # daily, factor book
    baseline_curve: list[tuple[date, float]]        # daily, equal-weight universe
    holdings: list[RebalanceHoldings]               # per-rebalance: date, tickers, weights, realized_return
    metrics: BacktestSummary                         # factor book
    baseline_metrics: BacktestSummary                # baseline
    config: BacktestRunConfig                        # the exact params (reproducibility)
```

`BacktestSummary` = `total_return, cagr, sharpe, max_drawdown` (Sharpe/MDD via
`app.strategies.metrics` over the **daily** curve, so the √252 annualization the
shared helper assumes is correct).

### 4.3 The run loop (PIT, delisting-aware)

```python
def run_momentum_backtest(
    store, start, end, *,
    n=500, lookback_days=105, skip_days=21,        # §2 factor params (6-1, owner-locked)
    top_quantile=0.20, long_short=False,           # §3.2 construction (to confirm)
    turnover_cost_bps=10.0,                         # §3.4
    delisting="last_price_to_cash",                # §3.1 (to confirm)
    initial_equity=100_000.0,
) -> MomentumBacktestReport: ...
```

1. **Rebalance dates**: the last `sep` trading day of each ISO week in `[start, end]`.
2. **At each rebalance `D`**: `scores = momentum_scores(store, D, n=n, ...)`; select
   the top-quantile tickers (and bottom-quantile if `long_short`); assign
   equal target weights; record `RebalanceHoldings`.
3. **Daily mark-to-market** from `D`'s next trading day to the next rebalance:
   for each held name, its daily return = `closeadj[t]/closeadj[t-1] − 1` from its
   own `sep` series. **Delisting**: if a held name has no price on day `t` but had
   one earlier in the segment, realize the **delisting-return mechanism** (§3.1) on
   its last available day and move that sleeve to cash for the rest of the segment.
4. **Costs**: on each rebalance, subtract `turnover_cost_bps` × (traded notional
   fraction) from equity.
5. **Baseline**: identical loop with the full `universe_asof(D)` equal-weighted.
6. Assemble daily `equity_curve` / `baseline_curve` and the summaries.

### 4.4 Survivorship + PIT discipline (the hinges)

- A name selected at `D` is held through the segment **from its own price history**
  — if it delisted at `D+3`, it contributes 3 days of return then the delisting
  mechanism, **not** an early drop. Dropping delisted names is the exact bias §1/§2
  guarded against; §3 must not reintroduce it on the *holding* side.
- Every score and price read at or after each rebalance uses only data `≤` that
  point in the loop's logical time; appending later data to the store must not move
  a historical equity point (tested in §4.5).

### 4.5 Tests (load-bearing first)

- **★ Survivorship on the holding side**: a synthetic universe with a name that is
  a top-quintile *winner* at a rebalance and then delists mid-segment — assert it
  is **held**, realizes the configured delisting return, and is **not** silently
  excluded; the book's return reflects it.
- **★ Reproducibility / no-look-ahead**: identical config → identical report
  (frame-equal curves + metrics); a backtest to `end=D` matches the `[start, D]`
  prefix of a backtest run to a later `end` (extending the store doesn't move
  history).
- **Rebalance dates**: last-trading-day-of-week selection over a known calendar.
- **Daily mark-to-market**: a hand-checked 2-name, 2-week book → exact equity path.
- **Delisting mechanism**: the chosen mechanism produces the expected realized
  return for a delisting name (and the `long_short`/baseline variants run).
- **Baseline**: equal-weight-universe curve computed and distinct from the book.
- Synthetic fixtures only (reuse `tests/factor_data/conftest.py` builders; extend
  with a delisting name in the momentum cohort) — no committed vendor bytes
  (ADR 0018 §6). Aim for the P2/P3 coverage bar on `backtest.py`.

## 5. Manual smoke

From the host venv, against an ingested store (broaden the pool per
`docs/runbook/factor-data.md` §4 so the universe and quantiles are non-trivial):

```bash
PYTHONPATH=apps/backend apps/backend/.venv/Scripts/python.exe - <<'PY'
from datetime import date
from app.factor_data.store import FactorDataStore
from app.factor_data.backtest import run_momentum_backtest
r = run_momentum_backtest(FactorDataStore(read_only=True), date(2015,1,1), date(2020,12,31))
print("rebalances:", len(r.rebalances))
print("book   total/CAGR/Sharpe/MDD:", round(r.metrics.total_return,3), round(r.metrics.cagr,3),
      round(r.metrics.sharpe,2), round(r.metrics.max_drawdown,3))
print("base   total/CAGR/Sharpe/MDD:", round(r.baseline_metrics.total_return,3),
      round(r.baseline_metrics.cagr,3), round(r.baseline_metrics.sharpe,2),
      round(r.baseline_metrics.max_drawdown,3))
PY
```

**Pass:** a daily equity curve and summary metrics for both the momentum book and
the baseline, deterministic across runs, with delisted names contributing their
realized returns (not dropped). No order-path assertion applies — §3 submits no
orders.

## 6. Walk-away discipline

≥ 1 hour. §3 is a read-only analysis path — no order-path, risk-engine, or
audit-log surface — so the routine minimum applies. (The *result* gates §4's paper
activation, but §3 itself touches nothing live.)

## 7. What this session does NOT do

- **No order submission, no paper, no live** — §3 computes returns; §4 expresses
  the book through the MTG template and the normal lifecycle.
- **No DB persistence or UI** of backtest results — a later concern; §3 returns a
  report object + the smoke.
- **No FMP / fundamental / multi-factor** — §5+. v1 is price-momentum only.
- **No portfolio optimizer** beyond equal-weight; **no transaction-cost model**
  beyond the flat per-rebalance turnover cost.
- **No `BarCache` refactor**, no change to the single-name `Backtester`.
- **No LLM** anywhere in the path (ADR 0006 v2).

## 8. Notes & gotchas

1. **Daily mark-to-market, weekly rebalance.** The equity curve is daily so
   `metrics.sharpe_ratio` (×√252) and `max_drawdown` are correct; weekly-only
   points would understate drawdown and mis-annualize Sharpe.
2. **Delisting is the honesty hinge — decide it before coding (§3.1).** The
   survivorship-on-the-holding-side test (§4.5 ★) is the §3 analog of §1's
   delisted-name test and §2's no-look-ahead test. Do not weaken it.
3. **Apply weights to the NEXT day's return.** Selecting at `D`'s close and earning
   `D`'s own return would be same-bar look-ahead; the book earns from `D+1` onward.
4. **Reuse `app/strategies/metrics.py`.** Do not re-implement Sharpe/MDD — the
   shared formulas keep factor and single-name backtests comparable (P6b §1a-drift
   lesson).
5. **Read-only store.** The backtest opens the store read-only; it never writes.
6. **min_names guard propagates.** Early rebalance dates with a thin cross-section
   raise `FactorUnavailable` (§2) — the backtest should clamp the start to the
   first date with a valid cross-section, and surface what it skipped rather than
   silently shortening the window.
