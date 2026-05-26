# Backtesting Runbook

## How a backtest runs

`POST /api/v1/strategies/{id}/backtest` is **asynchronous** (P4 §2):
1. Returns 202 immediately with a `job_id` and `status=queued`.
2. A background `BacktestWorker` picks up the job and writes
   progress events (`backtest.started`, `backtest.progress`,
   `backtest.completed` / `backtest.failed` / `backtest.canceled`) to
   the `backtests` WS topic.
3. Final state and persisted `BacktestResult` row are available via
   `GET /api/v1/backtest-jobs/{job_id}` once `status=completed`.

Single-flight is enforced per strategy: a second submission while a job is
QUEUED or RUNNING returns 409.

Inside the worker:
1. Loads the strategy class from disk via the same loader the runtime uses.
2. Pulls bars from `BarCache` for the requested range (and fetches+caches
   any missing days from Alpaca).
3. Constructs `BacktestContext` (in-memory positions, simulated cash)
   instead of the real `StrategyContext`.
4. Iterates bar-by-bar, calling `on_bar` per symbol. Orders submitted on
   bar N fill at bar N+1's open (± `slippage_bps`).
5. At the end, force-closes any open positions at the last close price.
6. Computes metrics, persists a `BacktestResult` row, returns the full
   result.

## Cancelling a running job

`POST /api/v1/backtest-jobs/{job_id}/cancel` asks the worker to stop. The
worker checks the cancel flag between bars; once it observes the flag it
transitions the job to CANCELED and writes a partial result row (no equity
curve / no trades persisted). Cancelling a terminal job returns 409.

## Data source

Backtest bars come from the same `BarCache` that serves the runtime. First
backtest of a date range fetches from Alpaca; subsequent backtests of the
same range serve from disk. Free-tier IEX feed only (see Implementation
Plan v0.2 §16 for the implications).

## Slippage and commission

- **Slippage:** `slippage_bps` (default 5 bps = 0.05% of fill price). Buys
  pay up; sells receive less.
- **Commission:** `commission_per_share` (default 0; Alpaca paper has no
  commissions, and many brokers no longer charge for US equities).

To stress-test a strategy, run the same backtest with `slippage_bps=25`
(high friction) and see how metrics change.

## What's simulated, what isn't

| Aspect | Simulated | Notes |
|---|---|---|
| Market orders | Yes | Fill at next bar's open |
| Limit orders | **No** | Returns `non_market_orders_unsupported_in_backtest`. The reference RSI strategy works around this with a virtual stop check in `on_bar`. |
| Stop orders | **No** | Same as limit. |
| Bracket / OCO | **No** | Same. |
| Partial fills | No | Every fill is full qty |
| Slippage | Yes (linear, bps) | Constant; doesn't model order book impact |
| Borrow cost for shorts | No | Treats shorts as free |
| Overnight gaps | Yes (bars carry it naturally) | |
| Survivorship bias | Not addressed | Symbol universe is what you give it |

Limit/stop simulation lands per-strategy when a strategy needs it (per P2
Checklist §5.3 / Session 3 Gotcha #3).

## Metrics

| Field | Definition |
|---|---|
| `total_return` | (ending_equity / starting_equity) − 1 |
| `annualized_return` | (ending/starting) ^ (1/years) − 1 |
| `sharpe_ratio` | Daily-bucketed returns, annualized × √252, risk-free rate = 0 |
| `max_drawdown` | Largest peak-to-trough drop, as a negative fraction |
| `win_rate` | Fraction of closed trades with pnl > 0 |
| `profit_factor` | gross_profit / abs(gross_loss); ∞ if no losses |
| `trade_count` | Closed round-trips only |
| `avg_win` / `avg_loss` | Mean pnl among winners/losers |
| `avg_trade_duration_seconds` | Mean across closed trades |

**Sharpe caveat:** with < 2 trading days of data, Sharpe returns 0 by
convention. Don't read meaning into low-data-point Sharpes.

## Reproducibility

A backtest is fully deterministic given:
- Identical bars in the cache.
- Identical `params`.
- Identical `slippage_bps` and `commission_per_share`.

`tests/strategies/test_backtest_reproducibility.py` runs the reference
strategy twice on committed fixture bars and asserts every metric matches
down to 1e-9. CI enforces this (the pytest suite is itself a required
check).

If your own strategy's backtest gives different metrics across runs:
1. Check for `random` or `numpy.random` without a fixed seed.
2. Check for `set` iteration where the order matters.
3. Check for dict iteration where the order matters and assumes Python's
   insertion-ordered behavior.
4. Bar cache regenerated mid-test? (Shouldn't happen, but the parquet
   file's mtime can shift.)

## Running a backtest

From the UI:
1. Strategies page → click the strategy → Backtests tab → "Run backtest".
2. Fill the form (defaults are last 10 days, 1-minute bars, 5 bps slippage).
3. Click Run. The modal polls the job status until done (2–10 seconds for
   a short range; minutes for a long one).
4. Result opens in a results view with metrics, equity curve, and trade
   list.

From the CLI / curl:
```bash
curl -X POST http://127.0.0.1:8000/api/v1/strategies/1/backtest \
  -H "Content-Type: application/json" \
  -d '{
    "start": "2025-11-03T00:00:00+00:00",
    "end": "2025-11-10T00:00:00+00:00",
    "label": "default",
    "initial_equity": "100000",
    "slippage_bps": 5
  }'
# returns {"job_id": <id>, "status": "queued", ...}

# Poll:
curl http://127.0.0.1:8000/api/v1/backtest-jobs/<id>
```

## Range limits

The previous 1-year cap on the synchronous endpoint is gone. The async
worker doesn't enforce a hard range cap — long ranges run, just slowly.
A `start > end` request is still rejected (400).

## Don't draw conclusions from one backtest

A single 3-month backtest is a weak signal. Standard discipline:
- **Walk-forward** the period: split into train/test, optimize on train,
  validate on test.
- **Multiple slippage values:** if your edge disappears at 25 bps slippage,
  you may not have an edge.
- **Multiple symbols:** does it work on AAPL only? Or also on SPY, NVDA,
  etc.?
- **Multiple time periods:** a strategy that worked in 2020 may not work
  in 2024.

P2 ships none of this — it ships the *plumbing*. The discipline is yours.
