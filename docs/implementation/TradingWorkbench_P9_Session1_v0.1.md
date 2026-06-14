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

## 0. Reconciliation (2026-06-14, during build) — universe definition changed

§1's "FIRST pin the membership recipe against real data" step (§4.4) did its job
and surfaced a data-coverage finding that invalidates the **S&P 500** premise:

- The `SHARADAR/SP500` constituents datatable **in this subscription returns only
  28 names** (the Dow blue-chips: AAPL, AXP, BA, CAT, CSCO, CVX, DD, GE, GS, HD,
  IBM, INTC, JNJ, JPM, KO, MCD, MMM, MRK, MSFT, NKE, PFE, PG, TRV, TSLA, UNH, VZ,
  WMT, XOM). It is the free **sample** of the constituents product, not the full
  ~500-name index. (Its structure *was* pinned: `added` = original add date,
  `historical` = quarter-end membership snapshots, `current` = today — but only
  for those 28 names, so it can't define an S&P 500 universe.)
- `SEP` (prices) and `TICKERS` (21,853 names, with `firstpricedate` /
  `lastpricedate` lifetime bounds + `isdelisted`) **are** full and
  survivorship-free. `DAILY` (point-in-time market cap) returns 0 rows — not
  subscribed.
- §0's GO checked SP500 *accessibility*, not *completeness* — the gap §1's
  pin-the-recipe step is designed to catch (per §8 note 8, a §0 record gap to
  reconcile, recorded here).

**Owner decision (2026-06-14):** v1 universe = a **point-in-time liquidity
universe** from `SEP` + `TICKERS` — top-`n` by trailing dollar volume, tradeable
as of the rebalance date (`firstpricedate <= as_of <= lastpricedate`). Price-only,
point-in-time, survivorship-free, no extra subscription. This replaces the S&P 500
membership universe throughout §1 (§2 below, §4.4, §4.6). See
`docs/runbook/factor-data.md` §2.

**Knock-on changes from this decision:**
- `universe_asof` is built on dollar-volume ranking + lifetime-bound eligibility,
  not the SP500 change-log. The `UniverseUnavailable` floor guard is retained
  (now keyed to the SEP price-history floor, not the change-log floor).
- The `sp500` table is **dropped** from the schema (§4.2) — a 28-name sample
  table would be misleading; it is not ingested.
- Ingestion is **resumable** (`--skip-existing`), superseding §0's "single-shot,
  no checkpointing" (which assumed the 500-name pull). The liquidity candidate
  pool is larger than 500 and the vendor caps at ~1M rows/day.
- Tests use **synthetic** data (no committed binary fixture) — raw vendor
  re-export is disallowed (ADR 0018 §6).

**Follow-up — done (2026-06-14, owner-authorized):** both **ADR 0018**
(Implementation-notes universe-scope note + new re-evaluation trigger) and P9
**Direction v0.2** (Reconciliation banner + struck v1-decisions row) now record
the universe as a PIT liquidity top-N. No open reconciliation items remain.

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
- An **ingestion entrypoint** (`apps/backend/scripts/ingest_sharadar.py`) — idempotent,
  single-shot (§0 measured the full pull at ~5 min — no checkpointing; §4.3).
- **Tests** — the survivorship-free + `universe_asof` assertions are the load-bearing ones
  (§4.6), plus schema + idempotent-re-ingest + reproducibility.
- A short **runbook** note (`docs/runbook/factor-data.md`) — how to (re)ingest, where the store
  lives, the licensing reminder.

## 3. Prerequisites

- **§0 returned GO** (2026-06-13, PR #99) — its filled §6 supplies the §1 inputs, already
  resolved:
  - **S&P 500 membership:** `SHARADAR/SP500` change-log, `action ∈ {added, current, historical}`
    (§1 pins the interval recipe — §4.4); **change-log floor `1957-03-04`** → no clamp for 1998.
  - **schemas** confirmed for `SEP` / `TICKERS` / `ACTIONS` / `SP500` (§4.2 DDL matches).
  - **ingest ~5 min, rate limit 1M/day → single-shot, no checkpointing** (§4.3).
  - **dependency: REST via `httpx` + `pandas`** (no vendor SDK).
  - *(FMP carry-forward, §5+ only: legacy `/api/v3` is 403-gated; use the `/stable` API.)*
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
  date   DATE NOT NULL, action VARCHAR NOT NULL,  -- §0: action ∈ {added, current, historical}
  ticker VARCHAR NOT NULL, name VARCHAR
);

-- ingest bookkeeping (idempotency; §0 confirmed single-shot ingest — no checkpoint cursor)
CREATE TABLE IF NOT EXISTS ingest_runs (
  dataset VARCHAR, started_at TIMESTAMP, finished_at TIMESTAMP,
  rows    BIGINT, status VARCHAR   -- 'running'|'ok'|'failed'
);
```

### 4.3 Ingestion (idempotent, single-shot)

- `SharadarProvider.fetch_table(name, **filters)` pages the datatables endpoint via
  `qopts.cursor_id` until exhausted, returning a `DataFrame`. Key as a query param; **never
  logged** (ADR 0018 §5). (§0 confirmed REST via `httpx` + `pandas` is sufficient — no SDK.)
- `FactorDataStore.ingest_sep(...)` / `ingest_tickers()` / `ingest_actions()` /
  `ingest_sp500()` upsert into the tables above. **Idempotent**: re-running ingestion converges
  to the same state (DuckDB `INSERT ... ON CONFLICT` / `DELETE`+`INSERT` per table; `sep` keyed
  by `(ticker,date)`).
- **Single-shot — no checkpointing (§0-resolved).** §0 measured the full S&P 500 `SEP` pull at
  **~5 min** (AAPL full history 7,155 rows in 0.6s × ~500 names; Sharadar rate limit 1M/day). A
  single-shot idempotent ingest is fine and `ingest_runs` is bookkeeping only. The
  checkpoint/resume path is **not** built — it was conditional on a long-ingest §0 finding that
  did not materialize.

### 4.4 `universe_asof(date)`

```python
def universe_asof(store: FactorDataStore, as_of: date) -> list[str]:
    """S&P 500 constituents as of `as_of`, reconstructed from the SHARADAR/SP500
    change-log.

    §0 found the change-log uses action ∈ {added, current, historical} — NOT a
    simple added/removed pair. FIRST IMPLEMENTATION STEP of §1: pin the exact
    membership-interval semantics against two known index changes (a name added
    then later removed) — i.e. how a *removal date* is represented (a 'historical'
    status row, an end-date, or a later removal event). Build the interval logic
    from that, not from an assumed add/remove model.

    Bounded below by the change-log floor — §0 measured it at 1957-03-04, so the
    guard never triggers for a 1998+ window; it is retained defensively and raises
    UniverseUnavailable below the floor rather than returning a wrong universe.
    """
```

- The floor guard is retained as defense, but **§0 resolved the risk**: the change-log floor is
  **1957-03-04**, ~40y before the 1998 price history, so no backtest-start clamp is needed. The
  guard still raises `UniverseUnavailable` below the floor rather than returning a wrong set. The
  load-bearing §1 unknown is now the **action-semantics recipe** above, not the floor.

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
3. **Membership *semantics*, not the floor, are the §1 risk.** §0 confirmed the change-log floor
   is `1957-03-04` (no clamp for 1998) — but also that `action ∈ {added, current, historical}`,
   not `{added, removed}`. §1's first task is to pin the membership-interval recipe from the real
   semantics (§4.4); the floor guard stays defensive (raises below the floor, never guesses).
4. **Idempotent ingest, keyed correctly.** `sep` PK is `(ticker, date)`; re-ingest must
   converge. Verify with the idempotent-ingest test, not by eyeballing counts.
5. **Store location + gitignore.** `data/factor_data.duckdb` lives under the already-ignored
   `data/`. Never commit the store or raw vendor pulls (size + licensing, ADR 0018 §6).
6. **Key hygiene.** `NASDAQ_DATA_LINK_API_KEY` is printed as a *length* only, never a value, and
   never written to logs/audit (ADR 0018 §5).
7. **Checkpointing not built — §0 resolved it.** §0 measured the full ingest at ~5 min, so §1 is
   single-shot idempotent (§4.3); the cursor/resume path is intentionally absent.
8. **§0's filled §6 is this session's spec for schemas + the membership recipe.** If §1 finds a
   column/recipe mismatch against §0, that is a §0 record error to reconcile, not a thing to
   paper over in code.
