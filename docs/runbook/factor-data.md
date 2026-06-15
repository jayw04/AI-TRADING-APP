# Runbook — Factor-Data Spine (P9 §1)

This runbook covers the point-in-time, survivorship-free factor-data store
introduced in P9 §1: what it is, how to (re)ingest it, where it lives, the
universe definition, the vendor rate limit, and the licensing rules.

> **One-line summary:** `app/factor_data/` is a standalone, read-only subsystem
> that ingests the Sharadar `SEP` / `TICKERS` / `ACTIONS` datatables into a local
> DuckDB file (`apps/backend/data/factor_data.duckdb`, gitignored) and exposes
> survivorship-free price access plus a point-in-time tradeable universe. It never
> touches the order path, the risk engine, or `BarCache` (ADR 0018).

---

## 1. What it is

- **Store:** an embedded DuckDB file. Default path
  `apps/backend/data/factor_data.duckdb` (override with
  `WORKBENCH_FACTOR_DATA_DB_PATH`). Lives under the already-gitignored `data/` —
  **never commit the store or raw vendor pulls** (size + licensing, §5).
- **Tables:** `sep` (daily prices, PK `(ticker, date)`), `tickers` (reference +
  lifetime price-date bounds), `actions` (splits/divs/delistings), `ingest_runs`
  (bookkeeping).
- **Provider:** `app/factor_data/providers/sharadar.py` — a read-only httpx REST
  client for the Nasdaq Data Link v3 datatables, with `qopts.cursor_id`
  pagination. Injects the OS trust store before any HTTPS (ADR 0017) so it works
  under Norton on the dev box.

## 2. The universe definition (read this first)

P9 was scoped against an **S&P 500** membership universe. During §1's
"pin the recipe first" step we discovered that the `SHARADAR/SP500` constituents
datatable **in this subscription returns only 28 names** (the Dow blue-chips) —
it is the free *sample* of the constituents product, not the full ~500-name
index. `SEP` (prices) and `TICKERS` (21,853 names, with `firstpricedate` /
`lastpricedate` lifetime bounds and the `isdelisted` flag) **are** full and
survivorship-free; `DAILY` (point-in-time market cap) returns 0 rows (not
subscribed).

Per the owner's decision (2026-06-14), the v1 universe is therefore a
**point-in-time liquidity universe**, reconstructed from `SEP` + `TICKERS` alone:

> `universe_asof(as_of, n=500, lookback_days=63)` = the top-`n` US tickers by
> trailing dollar volume (`SUM(close * volume)` over the trailing window) that
> were **tradeable as of `as_of`** — i.e. `firstpricedate <= as_of <=
> lastpricedate`.

This is price-only (honors "v1 is price-only"), point-in-time (uses no data after
`as_of`), and survivorship-free (a name delisted *after* `as_of` but liquid
*then* is included; a name delisted *before* `as_of` is excluded). It needs no
extra subscription. A date earlier than the price-history floor raises
`UniverseUnavailable` rather than returning a wrong set.

**Coverage caveat (important for honesty):** the universe is only as
survivorship-free as the `SEP` coverage you ingest. To avoid re-introducing
survivorship bias, the candidate pool must include delisted/shrunk names — do
**not** scope ingestion by *today's* market-cap class (e.g. `scalemarketcap`),
which would silently drop names that were liquid in the past but aren't now. The
honest pool is "every name that ever traded with meaningful volume." See §4 for
how the rate limit shapes this.

## 3. Prerequisites

- `NASDAQ_DATA_LINK_API_KEY` in `.env` (loaded as a `Settings` env-alias per
  ADR 0018 §5 — **not** the encrypted CredentialStore).
- The host backend venv (`apps/backend/.venv`). Ingestion runs from there — no
  Docker, no stack — same posture as the fixture-gen / range-insight scripts.
- ADR-0017 OS-trust-store path on `main` (so ingestion reaches Nasdaq Data Link
  under Norton). The provider and the ingest script both inject it.

## 4. (Re)ingesting

Idempotent — re-running converges to the same state (`sep` keyed by
`(ticker, date)`; `tickers` by ticker; `actions` replaced per-ticker).

```bash
# Reference table (full, ~22k rows, one pull) + SEP/ACTIONS for a ticker list
PYTHONPATH=apps/backend apps/backend/.venv/Scripts/python.exe \
    apps/backend/scripts/ingest_sharadar.py --tickers AAPL,MSFT,NVDA,KO

# From a file (comma- or newline-separated), resuming across days
PYTHONPATH=apps/backend apps/backend/.venv/Scripts/python.exe \
    apps/backend/scripts/ingest_sharadar.py --tickers-file universe_pool.txt --skip-existing

# Only the reference table
PYTHONPATH=apps/backend apps/backend/.venv/Scripts/python.exe \
    apps/backend/scripts/ingest_sharadar.py --datasets tickers
```

**Rate limit + scope.** Nasdaq Data Link caps at **~1M rows/day**. `SEP` and
`ACTIONS` are pulled **per ticker** (each ticker's full history is ~7k rows / a
fraction of a second), so a broad pool spans multiple days. The script
deliberately **refuses a full-market `SEP` pull** — you must pass an explicit
ticker list/file, so a run can never silently blow the daily limit. Re-run with
`--skip-existing` to resume: tickers already present in `sep` are skipped, not
re-fetched. (This supersedes the §0 "single-shot, ~5 min, no checkpointing"
finding, which assumed the 500-name S&P universe; the liquidity universe's
candidate pool is larger, so resumable ingestion is the operational reality.)

## 5. Licensing (do not skip)

- **No raw vendor data in the repo.** Raw-table re-export is disallowed
  (ADR 0018 §6). The store file and any raw pulls stay under the gitignored
  `data/` and are never committed.
- **Tests use synthetic data, not vendor bytes.** `tests/factor_data/` fabricates
  a tiny price slice at test time (`conftest.py`) — there is no committed DuckDB
  fixture and no real Sharadar data in the repo.
- **No agent/MCP exposure** of factor data yet — revisit when a factor surface is
  actually built (ADR 0018 §6; derived-score exposure is still TBD pending a
  terms review).

## 5b. Factors + the strategy accessor (P9 §2)

The first factor is **price momentum** (6–1 month total return, owner-locked):
`app/factor_data/factors/` computes it (`momentum.py`), standardizes it
cross-sectionally (`cross_section.py`: winsorize → z-score + percentile rank), and
ties universe → momentum → scores in `engine.momentum_scores(store, as_of)`.

Strategies reach factor data **only** through `StrategyContext.factors` (and the
identical `BacktestContext.factors`), a sandboxed read-only `FactorAccessor`:

```python
df = self.ctx.factors.momentum_scores()        # as of latest store date; cols: momentum/winsorized/zscore/rank/score
mom = self.ctx.factors.momentum_for("AAPL")     # single name; None if history insufficient
names = self.ctx.factors.universe()             # PIT tradeable universe
```

- The accessor opens DuckDB **read-only**, holds no DB session/network, and imports
  no order path. `as_of=None` → the store's latest price date; a future `as_of`
  clamps down (never forward) — no look-ahead.
- **Provisioning:** the backend lifespan builds the accessor only if
  `data/factor_data.duckdb` exists; otherwise `ctx.factors` raises
  `FactorDataUnavailable` (degrade, don't crash). So **ingest before a strategy
  expects factors.** A locked store (mid-ingest) also degrades to disabled.
- `momentum_scores` raises `FactorUnavailable` if fewer than 20 names have a valid
  momentum (a tiny cross-section is noise) — ingest a broad pool (§4) for the full
  ~500-name universe.

## 5c. Running a backtest (P9 §3)

`app/factor_data/backtest.py` runs the §2 momentum factor as a **weekly,
survivorship-free, cross-sectional** backtest over the §1 spine (standalone — it
does not touch the single-name `Backtester`):

```bash
PYTHONPATH=apps/backend apps/backend/.venv/Scripts/python.exe - <<'PY'
from datetime import date
from app.factor_data.store import FactorDataStore
from app.factor_data.backtest import run_momentum_backtest
r = run_momentum_backtest(FactorDataStore(read_only=True), date(2015,1,1), date(2020,12,31))
print("rebalances:", len(r.rebalances), "skipped(thin):", len(r.skipped_rebalances))
print("book total/CAGR/Sharpe/MDD:", r.metrics)
print("base total/CAGR/Sharpe/MDD:", r.baseline_metrics)
PY
```

- **Construction (owner-locked):** weekly rebalance on the last trading day of each
  ISO week; equal-weight **long the top quintile** by momentum `score`; weights
  apply from the next trading day (no same-bar look-ahead).
- **Delisting = final price → cash:** a held name earns daily returns to its last
  trading day, then its sleeve freezes as cash until the next rebalance — survivorship
  carries through to the *holding* side, not just the universe.
- **Baseline:** an equal-weight-universe book runs alongside (`r.baseline_metrics`)
  so the momentum book's excess return is meaningful (ADR 0014).
- **Daily mark-to-market:** the equity curve is daily, so Sharpe (×√252) and max
  drawdown (reused from `app/strategies/metrics.py`) are correct.
- **Thin early dates** (cross-section < 20 names) are skipped and listed in
  `r.skipped_rebalances` — not silently dropped. Ingest a broad pool (§4) so the
  universe and quintiles are non-trivial; a tiny store yields a thin/degenerate run.
- Read-only, no orders, no DB/UI — the report is an in-memory object (§3 scope).

## 5d. Paper-activation drive (P9 §4) — register + activate the momentum book

The momentum-portfolio strategy runs through the engine on PAPER. Driving it live
needs **market hours** + the running stack; the steps:

1. **Prep (any time, no stack):** ingest the candidate universe and build the
   symbol list.
   ```bash
   # broad pool → SEP (date-bounded so it stays under the 1M-rows/day cap)
   PYTHONPATH=apps/backend apps/backend/.venv/Scripts/python.exe \
       apps/backend/scripts/ingest_sharadar.py \
       --tickers-file apps/backend/data/paper_universe_pool.txt \
       --datasets sep --from 2024-06-01 --skip-existing
   # write the top-200 liquidity universe + SPY → data/paper_symbols.txt
   #   (universe_asof(latest, n=200) + "SPY"; SPY is for the regime filter,
   #    read from Alpaca at runtime — it is NOT in Sharadar SEP)
   ```
2. **Bring the stack up** (market hours; ⚠ use PowerShell for Docker — git-bash
   `docker` hangs). **Norton can stay ON** — ADR 0017's `truststore` (injected at
   `app/main.py` startup, before the broker connect) routes TLS through the OS trust
   store, which trusts Norton's inspection root; proven under Norton (host-venv
   probe + ingest). *Caveat:* that root lives in the **Windows** store, but the
   **Docker (Linux) backend** reads the container's CA store — so IF Norton
   intercepts the container's WSL2 traffic, the cold-boot Alpaca connect can still
   fail (`CERTIFICATE_VERIFY_FAILED`). Don't disable Norton preemptively: bring the
   stack up, check `/healthz`; only toggle Norton (or run the backend host-venv,
   where truststore uses the Windows root) if the broker subsystem actually fails.
   The backend must connect to the intended paper account
   (the `ALPACA_PAPER_API_KEY` in `.env`) and `AccountSyncService` must populate
   `accounts_state` (else live-equity sizing falls back to the estimate).
3. **Register + activate** (creates the strategy IDLE → starts it → PAPER + cron):
   ```bash
   PYTHONPATH=apps/backend apps/backend/.venv/Scripts/python.exe \
       apps/backend/scripts/paper_activate_momentum.py \
       --email <email> --password '<pw>' --totp <6-digit> \
       --symbols-file apps/backend/data/paper_symbols.txt
   #   --dry-run first to preview the payload (no login/mutation)
   ```
   Sizing params are dry-run-locked for a ~$10k account: `max_names=5`,
   `max_position_pct=0.20`, `top_quantile=0.20`, `min_score=0.0`, regime filter on.
4. **Trigger:** the weekly cron `0 14 * * 1` (Mon 14:00 UTC ≈ 10:00 ET) fires the
   rebalance automatically — activate before then and it runs on its own. To fire
   sooner for the validation, re-create with `--schedule '*/5 * * * *'` (the
   rebalance-once-per-ISO-week guard means one rebalance then no-ops; revert to the
   weekly cron after — each tick fetches bars for all symbols).
5. **Verify:** the paper book holds ~4–5 equal-weight top-momentum names (a $10k
   whole-share book underdeploys ~67% — pricey names round to 0 shares; fractional
   shares would be the fix), every order shows `source_type=STRATEGY` in the audit
   log, and the risk engine evaluated each (ADR 0002). No live account is touched.

## 6. Key hygiene

`NASDAQ_DATA_LINK_API_KEY` is read via `get_settings().nasdaq_data_link_api_key`
(app code) or `os.environ` (the standalone script, outside `app/`). It is logged
only as a **length**, never a value, and never written to logs or the audit log
(ADR 0018 §5).

## 7. Quick health check

```bash
PYTHONPATH=apps/backend apps/backend/.venv/Scripts/python.exe - <<'PY'
from datetime import date
from app.factor_data.store import FactorDataStore
from app.factor_data.universe import universe_asof
s = FactorDataStore()
print("price bounds:", s.price_date_bounds())
print("sep / tickers / actions rows:",
      s.row_count("sep"), s.row_count("tickers"), s.row_count("actions"))
print("universe 2015-06-30:", universe_asof(s, date(2015, 6, 30), n=10))
s.close()
PY
```

A delisted name still returns history (the survivorship-free guarantee):

```python
s.get_prices("CBNJ2", date(1990, 1, 1), date(2026, 1, 1))  # 147 rows, ends 1998-07-31
```
