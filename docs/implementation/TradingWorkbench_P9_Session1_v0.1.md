# P9 Session §1 v0.1 — Sharadar Price/Universe Spine in DuckDB

| Field | Value |
|---|---|
| Document version | v0.1 |
| Date | 2026-06-13 |
| Phase | **P9** — Point-in-time data backbone + multi-factor equity model |
| Session | **§1 of P9** (first implementation session) |
| Predecessor | P9 §0 Session Zero (data-access GO) · P9 Direction v0.2 + ADR 0018 (Accepted, merged `1799887` / #97) |
| Successor | P9 §2 — price-momentum factor + sandboxed factor accessor |
| Repository | `github.com/jayw04/AI-TRADING-APP` |
| Governing ADRs | 0018 (FMP + Sharadar PIT factor data — Accepted), 0017 (OS trust store for outbound TLS), 0014 (backtests = ground truth), 0002 (single OrderRouter — untouched; this is read-only data) |
| Scope | Ingest Sharadar `SEP` + `TICKERS` + `ACTIONS` + the `SP500` change-log into a local **DuckDB** PIT store; expose **survivorship-free** adjusted-price access and **`universe_asof(date)`** for the S&P 500. No factors, no backtest, no FMP. |
| Estimated wall time | 5–8 hours (new dependency + a vendor ingestion path + a new store + the survivorship/universe tests that are the point) |
| Tag on completion | `p9-session1-complete` |
| Out of scope | Factor math (§2), backtest (§3), FMP/fundamentals + SF3/13F (§5+), the `BarCache` provider-abstraction refactor (deferred — see §7), any order-path/live change |

---

## 1. Why this session exists

The v1 factor is **price momentum**, which needs exactly one thing the platform does not have:
a **survivorship-free, point-in-time price + universe spine**. §1 builds that and nothing
else. Everything downstream — the momentum factor (§2), the weekly cross-sectional backtest
(§3) — is a pure function of what §1 exposes, so §1's correctness *is* the honesty of the
phase.

Two properties must hold or the rest is dishonest (the same two §0 verified empirically):

- **Survivorship-free**: delisted names are present with full price history to their last
  trading day. A universe built from *today's* listed names systematically overstates returns.
- **Point-in-time**: `universe_asof(date)` returns the S&P 500 membership *as it was on that
  date*, reconstructed from the `SP500` change-log — never today's snapshot applied to the past.

§1 deliberately builds a **standalone** path. It does **not** refactor the existing
Alpaca `BarCache` (ADR 0018's provider-abstraction is real but deferred — §7), because momentum
reads the new cross-sectional spine, not `BarCache.get_bars`. Keeping §1 additive avoids
touching a load-bearing path that backtests and Range Insight depend on.

## 2. What this session ships

- A **`duckdb`** dependency (apps/backend/pyproject.toml) and a local PIT store at
  `data/factor_data.duckdb` (already gitignored via `data/`).
- A **Sharadar provider** (`app/factor_data/providers/sharadar.py`) — a read-only REST client
  (httpx, OS-trust-store-injected) for the `SEP` / `TICKERS` / `ACTIONS` / `SP500` datatables,
  with cursor pagination. (REST vs SDK per the §0 finding — default REST.)
- A **DuckDB PIT store** (`app/factor_data/store.py`) — schema + idempotent ingest + queries.
- **`universe_asof(date) -> list[str]`** (`app/factor_data/universe.py`) — survivorship-free,
  PIT S&P 500 membership from the change-log.
- **Survivorship-free price access** — `get_prices(ticker, start, end, adjusted=True)`.
- An **ingestion entrypoint** (`apps/backend/scripts/ingest_sharadar.py`) — idempotent, with
  checkpoint/resume **iff** the §0 ingest-time finding warrants it (§4.3).
- **Tests** — the survivorship-free + `universe_asof` assertions are the load-bearing ones
  (§4.6), plus schema + idempotent-re-ingest + reproducibility.
- A short **runbook** note (`docs/runbook/factor-data.md`) — how to (re)ingest, where the store
  lives, the licensing reminder.

## 3. Prerequisites

- **§0 returned GO**, with its §6 Results filled — specifically these §1 inputs:
  - the **S&P 500 membership construction recipe** + the **change-log earliest date** (bounds
    `universe_asof`);
  - the exact **`SEP` / `TICKERS` / `ACTIONS` / `SP500` schemas** (column names/types);
  - the **rate limit + estimated full-ingest time** (decides whether §4.3 checkpointing is
    required or optional);
  - the **REST-vs-SDK** decision.
- `NASDAQ_DATA_LINK_API_KEY` in `.env` (loaded as a `Settings` env-alias per ADR 0018 §5).
- ADR-0017 OS-trust-store path on `main` (merged `d5a9596`) — so ingestion reaches Nasdaq Data
  Link under Norton.
- Host backend venv; ingestion runs from there (no Docker, no stack) — same posture as the
  fixture-gen / range-insight scripts.

> If §0 has **not** been executed, run it first. §1 is drafted but **not executed** against
> unverified data — that is the whole reason §0 exists.

## 4. Detailed work

### 4.1 Dependency + module layout

```
apps/backend/pyproject.toml         + duckdb>=1.1          # new runtime dep
apps/backend/app/factor_data/
  __init__.py
  config.py            # store path (default data/factor_data.duckdb), Settings wiring
  providers/
    sharadar.py        # REST client: fetch_table(name, **filters) -> pandas.DataFrame
  store.py             # FactorDataStore: schema, ingest_*, get_prices, connection mgmt
  universe.py          # universe_asof(date) -> list[str]
apps/backend/scripts/ingest_sharadar.py   # CLI: idempotent (re)ingest, host venv
docs/runbook/factor-data.md
```

`app/factor_data/` is a **new, self-contained package** — it does not import the order path,
the risk engine, or `BarCache`. The Sharadar client injects the OS trust store before any
HTTPS (ADR 0017) exactly as the standalone scripts do.

### 4.2 DuckDB schema

Column names/types are **pinned to §0's recorded schemas**; the DDL below is the expected
shape (verify against §0 before writing the migration-equivalent `CREATE TABLE`s). DuckDB is
schema-on-write here for clarity and test stability.

```sql
-- survivorship-free daily prices (incl. delisted names)
CREATE TABLE IF NOT EXISTS sep (
  ticker      VARCHAR NOT NULL,
  date        DATE    NOT NULL,
  open        DOUBLE, high DOUBLE, low DOUBLE, close DOUBLE,
  volume      BIGINT,
  closeadj    DOUBLE,        -- split/div-adjusted close — factors price from this
  closeunadj  DOUBLE,
  lastupdated DATE,
  PRIMARY KEY (ticker, date)
);

-- the as-of ticker universe (delisting flags + price-date bounds)
CREATE TABLE IF NOT EXISTS tickers (
  ticker        VARCHAR PRIMARY KEY,
  name          VARCHAR, exchange VARCHAR, category VARCHAR,
  isdelisted    BOOLEAN,
  firstpricedate DATE, lastpricedate DATE,
  lastupdated   DATE
);

-- corporate actions (splits / divs / delistings)
CREATE TABLE IF NOT EXISTS actions (
  date     DATE, action VARCHAR, ticker VARCHAR, name VARCHAR,
  value    DOUBLE, contraticker VARCHAR
);

-- S&P 500 membership change-log → the source of universe_asof
CREATE TABLE IF NOT EXISTS sp500 (
  date   DATE NOT NULL, action VARCHAR NOT NULL,  -- 'added' | 'removed'
  ticker VARCHAR NOT NULL, name VARCHAR
);

-- ingest bookkeeping (idempotency + checkpoint/resume)
CREATE TABLE IF NOT EXISTS ingest_runs (
  dataset VARCHAR, started_at TIMESTAMP, finished_at TIMESTAMP,
  rows    BIGINT, cursor VARCHAR, status VARCHAR   -- 'running'|'ok'|'failed'
);
```

### 4.3 Ingestion (idempotent, optionally checkpointed)

- `SharadarProvider.fetch_table(name, **filters)` pages the datatables endpoint via
  `qopts.cursor_id` until exhausted, returning a `DataFrame`. Key as a query param; **never
  logged** (ADR 0018 §5).
- `FactorDataStore.ingest_sep(...)` / `ingest_tickers()` / `ingest_actions()` /
  `ingest_sp500()` upsert into the tables above. **Idempotent**: re-running ingestion converges
  to the same state (DuckDB `INSERT ... ON CONFLICT` / `DELETE`+`INSERT` per table; `sep` keyed
  by `(ticker,date)`).
- **Checkpoint/resume is conditional on the §0 finding.** If §0's estimated full-`SEP` ingest
  time is short (minutes), a single-shot ingest is fine. If it is long (the ~500 names × 1998+
  pull is non-trivial), `ingest_runs.cursor` persists progress so an interrupted run resumes
  rather than restarts. **Do not build checkpointing speculatively** — let §0's number decide,
  and record which path was taken in this doc's notes on execution.

### 4.4 `universe_asof(date)`

```python
def universe_asof(store: FactorDataStore, as_of: date) -> list[str]:
    """S&P 500 constituents as of `as_of`, reconstructed from the change-log.

    Membership = every ticker whose most-recent sp500 event on/before `as_of`
    is 'added'. Bounded below by the change-log floor (§0 finding):
    `as_of` earlier than the floor raises UniverseUnavailable, NOT a silently
    wrong universe.
    """
```

- The floor guard is **load-bearing**: per the §0 review, a change-log that starts in (say)
  2008 cannot reconstruct a 1998 universe. §1 raises rather than returns a wrong set; §3's
  backtest start is then clamped to the floor (a §3 decision, recorded in §0/§1 results).

### 4.5 Survivorship-free price access

```python
def get_prices(store, ticker: str, start: date, end: date,
               adjusted: bool = True) -> pandas.DataFrame:
    """Daily prices for `ticker` in [start, end]. Returns history for DELISTED
    names too (the survivorship-free guarantee). `adjusted=True` returns
    closeadj; raw otherwise. Empty frame (not an error) if no rows."""
```

### 4.6 Tests (the load-bearing ones first)

- **★ Survivorship-free**: a **known delisted** ticker (from §0) returns non-empty
  `get_prices` history ending at its delisting — *not* "unknown ticker". This is the single
  most important test in P9.
- **★ `universe_asof` correctness**: at a past date, a name **added later** is **absent**; a
  name **present then but since removed/delisted** is **included**; the count is plausible
  (~500). A date below the change-log floor **raises** `UniverseUnavailable`.
- **Idempotent ingest**: ingest → row counts; re-ingest the same slice → identical counts/state.
- **Schema**: tables + columns + PKs as in §4.2.
- **Reproducibility**: two `universe_asof(d)` calls return identical ordered lists.
- Tests run against a **small committed DuckDB fixture** (a handful of names incl. one delisted,
  a slice of the change-log) — **not** a live API call (mirrors the bar-fixture pattern; no raw
  vendor *dataset* committed, only a tiny derived test slice — confirm against the §0 licensing
  finding before committing any vendor-derived bytes). New high-stakes module → aim for the P2/P3
  coverage bar on `app/factor_data/` (esp. `universe.py`).

## 5. Manual smoke

From the host venv (no Docker), after `ingest_sharadar.py` populates the store:

```bash
PYTHONPATH=apps/backend apps/backend/.venv/Scripts/python.exe - <<'PY'
from datetime import date
from app.factor_data.store import FactorDataStore
from app.factor_data.universe import universe_asof
s = FactorDataStore()                       # opens data/factor_data.duckdb
u = universe_asof(s, date(2015, 6, 30))     # a past date
print("S&P 500 as of 2015-06-30:", len(u), "names")
px = s.get_prices("<a known delisted ticker>", date(2007,1,1), date(2009,12,31))
print("delisted-name rows:", len(px), "last date:", px['date'].max())
PY
```

**Pass:** `universe_asof` returns ~500 names for a past date; the delisted name returns a
non-empty price history ending at its delisting. (The order-path baseline assertion that other
sessions end on does not apply — §1 touches no order path.)

## 6. Walk-away discipline

≥ 1 hour. §1 adds a read-only data subsystem with **no order-path, risk-engine, or audit-log
surface**; the ordinary routine minimum applies. (Contrast the ≥2h sessions that touch risk/live/
audit.)

## 7. What this session does NOT do

- **No factor computation** — momentum is §2.
- **No backtest, no portfolio construction** — §3.
- **No FMP / fundamentals / SF3 / 13F** — §5+ (v1 is price-only).
- **No `BarCache` refactor.** ADR 0018's provider abstraction is real but **deferred**: §1 is a
  standalone path. When the Alpaca-behind-the-interface refactor is eventually done, it carries a
  `# VERIFY-CAPABILITY-EXISTS` marker (confirm the exact `BarCache.get_bars` signature + every
  caller first — Direction §4).
- **No live anything**, no order-path touch, no new CI invariant.
- **No agent/MCP exposure** of factor data (licensing — ADR 0018 §6; revisit when a factor
  surface is actually built).
- **No raw vendor dataset committed** to the repo — only a tiny derived test fixture, and only
  if the §0 licensing finding permits.

## 8. Notes & gotchas

1. **Inject the OS trust store first.** `truststore.inject_into_ssl()` before any HTTPS in the
   Sharadar client + the ingest script, or it `CERTIFICATE_VERIFY_FAILED`s under Norton (ADR
   0017; the app does this at startup, a standalone script must do it itself).
2. **Survivorship-free is the hinge.** The delisted-name test (§4.6 ★) is the difference between
   an honest momentum backtest and a misleading one. Do not skip or weaken it.
3. **Membership floor is real.** `universe_asof` below the change-log floor must **raise**, not
   guess. A silently-wrong pre-floor universe is exactly the bias P9 exists to avoid.
4. **Idempotent ingest, keyed correctly.** `sep` PK is `(ticker, date)`; re-ingest must
   converge. Verify with the idempotent-ingest test, not by eyeballing counts.
5. **Store location + gitignore.** `data/factor_data.duckdb` lives under the already-ignored
   `data/`. Never commit the store or raw vendor pulls (size + licensing, ADR 0018 §6).
6. **Key hygiene.** `NASDAQ_DATA_LINK_API_KEY` is printed as a *length* only, never a value, and
   never written to logs/audit (ADR 0018 §5).
7. **Don't pre-build checkpointing.** Let §0's ingest-time number decide (§4.3); record the
   choice here on execution.
8. **§0's filled §6 is this session's spec for schemas + the membership recipe.** If §1 finds a
   column/recipe mismatch against §0, that is a §0 record error to reconcile, not a thing to
   paper over in code.
