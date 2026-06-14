# P9 Session §2 v0.1 — Price-Momentum Factor + Sandboxed Factor Accessor

| Field | Value |
|---|---|
| Document version | v0.1 (draft — decisions in §3 to confirm before coding) |
| Date | 2026-06-14 |
| Phase | **P9** — Point-in-time data backbone + multi-factor equity model |
| Session | **§2 of P9** |
| Predecessor | P9 §1 — Sharadar price/universe spine in DuckDB (tag `p9-session1-complete`, merged `1a827e6` / #100) |
| Successor | P9 §3 — survivorship-free weekly factor backtest |
| Repository | `github.com/jayw04/AI-TRADING-APP` |
| Governing ADRs | 0018 (FMP + Sharadar PIT factor data — Accepted), 0014 (backtests = ground truth), 0006 v2 (no LLM in order/data path — factor math is deterministic), 0002 (single OrderRouter — untouched; factor data is read-only and never reaches order submission) |
| Scope | A deterministic **price-momentum** factor (6–1 month total return) over the §1 PIT spine, **cross-sectional standardization** (winsorize → z-score + percentile rank), and a **sandboxed `FactorAccessor`** wired into `StrategyContext`/`BacktestContext` so strategies can read PIT factor scores without reaching the network, the DB, or the order path. Prices-only — no FMP. |
| Estimated wall time | 5–8 hours (factor math + cross-section + the accessor + context wiring + the no-look-ahead/sandbox tests that are the point) |
| Tag on completion | `p9-session2-complete` |
| Out of scope | The backtest / portfolio construction / weekly rebalance (§3), FMP fundamentals + value/quality/earnings/13F factors (§5+), the MTG factor strategy (§4), the `BarCache` provider-abstraction refactor (deferred — Direction §7), any order-path/live/LLM change |

---

## 1. Why this session exists

§1 shipped the honest data spine: survivorship-free prices and a point-in-time
universe. §2 turns that spine into the **one signal** the v1 phase is built around
— **price momentum** — and exposes it to strategy code through a **deliberate,
reviewable sandbox boundary**. Everything downstream (the §3 weekly backtest, the
§4 strategy) is a consumer of what §2 produces: a per-name, cross-sectionally
standardized momentum score as of a date, reachable from a strategy only through
`StrategyContext`.

Two properties make or break the session, and both are about *honesty*, mirroring
§1's survivorship/PIT pair:

- **No look-ahead in the factor.** A momentum score "as of" date `D` must be a
  pure function of prices on or before `D` (in fact, on or before `D − skip`).
  Adding future prices to the store must not change a past score. This is the §2
  analog of §1's survivorship test and is the single most important assertion here.
- **The accessor is a real sandbox.** Strategies reach factor data only through
  `StrategyContext` (today it wraps `BarCache` + `IndicatorComputer`; §2 adds a
  read-only `FactorAccessor`). The accessor cannot import the order path or the
  broker, holds no DB session, and opens its DuckDB store **read-only**. Strategy
  isolation (`check_strategy_isolation.sh`) must stay green.

§2 is **additive**: it does not refactor `BarCache` (Direction §7 defers that) and
does not touch the single-name `Backtester`'s price path. The factor reads the §1
`FactorDataStore`, not `BarCache.get_bars`.

## 2. What this session ships

- **Momentum factor** (`app/factor_data/factors/momentum.py`) — a deterministic
  6–1 month total return from adjusted close, plus a batch helper over a list of
  tickers, with explicit insufficient-history handling (`NaN`/`None`, never a
  guess).
- **Cross-sectional standardization** (`app/factor_data/factors/cross_section.py`)
  — `winsorize`, `zscore`, `rank` (percentile), and a `standardize()` that returns
  the raw + winsorized + z-score + rank columns for a cross-section.
- **Factor engine** (`app/factor_data/factors/engine.py`) — `momentum_scores(store,
  as_of, n, lookback_days, skip_days)` that ties **universe_asof → per-name
  momentum → standardization** into one PIT DataFrame.
- **Sandboxed accessor** (`app/factor_data/accessor.py`) — `FactorAccessor`: a
  read-only facade over a `FactorDataStore` exposing `momentum_scores(as_of=None)`,
  `momentum_for(ticker, as_of=None)`, `universe(as_of=None)`, with `as_of`
  PIT-clamped to the store's latest price date. Degrades gracefully (raises a clear
  `FactorDataUnavailable`) when no store is provisioned.
- **Context wiring** — `StrategyContext` and `BacktestContext` gain a `.factors`
  property backed by an injected (optional) `FactorAccessor`; the strategy engine
  constructs a shared read-only accessor when the store exists.
- **Tests** — the no-look-ahead + sandbox assertions are load-bearing (§4.6), plus
  momentum math, standardization math, insufficient-history, and reproducibility.
  New high-stakes module → aim for the P2/P3 coverage bar on `app/factor_data/`.

## 3. Decisions (locked 2026-06-14, owner)

1. **Momentum window — 6–1 month, measured in trading days (owner choice).**
   `momentum(D) = closeadj[D − skip] / closeadj[D − (lookback + skip)] − 1`, with
   **`lookback_days = 105` trading days (~5 months)** and **`skip_days = 21`
   trading days (~1 month)** — i.e. the cumulative return over the 5 months ending
   one month before `D`. Trading days = actual `sep` rows, not calendar days.
   - The owner chose the shorter 6–1 window over the classic 12–1: a faster,
     more-responsive signal that pairs with the weekly rebalance (Direction §3),
     accepting higher turnover/noise. The factor is parameterized, so §3 can sweep
     windows if the backtest argues for it.
   - The **skip** excludes the most recent month, the standard fix for short-term
     reversal that otherwise contaminates a momentum signal.
   - Trading-day windows (row offsets) avoid weekend/holiday drift and missing-bar
     ambiguity; a name must have a price at both endpoints or its score is `NaN`.
2. **Standardization output — winsorize at 1st/99th percentile, then expose BOTH
   z-score and percentile rank; primary `score` = z-score of winsorized momentum
   (owner choice).** Winsorizing before z-scoring tames the fat tails that wreck a
   mean/std; the z-score preserves relative spacing between names (the standard
   factor-model input). Rank is exposed too so §3/§4 can switch without recompute.
3. **`as_of` default + clamp.** A live strategy calling the accessor with no
   `as_of` gets scores as of the **latest price date in the store** (≤ today).
   `as_of` later than the store max clamps down to it (never forward). Below the
   §1 price floor → `UniverseUnavailable` propagates.
4. **Minimum cross-section.** If fewer than **`min_names = 20`** names have a valid
   momentum on `as_of`, `momentum_scores` raises `FactorUnavailable` rather than
   standardizing a degenerate cross-section (a 3-name z-score is noise).

> If §3's backtest argues for a different window (e.g. back to 12–1) or
> standardization, only the defaults in `momentum.py` / `engine.py` move; the
> accessor and tests are parameterized.

## 4. Detailed work

### 4.1 Module layout (additive)

```
apps/backend/app/factor_data/
  factors/
    __init__.py
    momentum.py        # compute_momentum(prices, as_of, lookback, skip) + batch
    cross_section.py   # winsorize / zscore / rank / standardize
    engine.py          # momentum_scores(store, as_of, ...) -> DataFrame
  accessor.py          # FactorAccessor (read-only facade) + FactorDataUnavailable
apps/backend/app/strategies/context.py   # + .factors on StrategyContext
apps/backend/app/strategies/backtester.py # + .factors on BacktestContext (parity)
```

`app/factor_data/factors/` imports only `app.factor_data.store` + pandas/numpy — no
order path, no broker, no DB session. `FactorAccessor` is the only thing
`StrategyContext` imports new; it transitively pulls `factor_data` (read-only),
which keeps `check_strategy_isolation.sh` (forbids `app.brokers` under
`app/strategies/`) trivially green.

### 4.2 Momentum (`momentum.py`)

```python
def compute_momentum(
    prices: pd.DataFrame,   # one ticker's sep rows: columns date, close (=closeadj)
    as_of: date,
    *,
    lookback_days: int = 105,
    skip_days: int = 21,
) -> float | None:
    """12-1 momentum: cumulative adjusted-close return over the `lookback_days`
    trading-day window ending `skip_days` trading days before `as_of`.

    Uses only rows with date <= as_of (NO look-ahead). Returns None if there are
    fewer than (lookback_days + skip_days) trading rows on/before as_of, or if
    either endpoint price is missing/non-positive — never a guessed value.
    """
```

- Endpoints are **row offsets** into the on/before-`as_of` slice: `end = row[-1 −
  skip_days]`, `start = row[-1 − skip_days − lookback_days]`. Return `end/start −
  1`. This is robust to holidays and to a name's first/last trading day.
- A batch helper `compute_momentum_batch(store, tickers, as_of, ...) ->
  dict[str, float | None]` pulls each ticker's `get_prices(ticker, floor, as_of)`
  once and applies `compute_momentum`.

### 4.3 Cross-section (`cross_section.py`)

```python
def winsorize(s: pd.Series, lower: float = 0.01, upper: float = 0.99) -> pd.Series
def zscore(s: pd.Series) -> pd.Series           # (x - mean) / std (ddof=0); NaN-safe
def rank(s: pd.Series) -> pd.Series             # percentile rank in [0, 1]
def standardize(raw: pd.Series) -> pd.DataFrame # cols: raw, winsorized, zscore, rank
```

- All functions drop `NaN` for the statistics but preserve the index so a caller
  can re-join. `zscore` of a zero-variance cross-section returns all-zeros (not
  `inf`).

### 4.4 Engine (`engine.py`)

```python
def momentum_scores(
    store: FactorDataStore,
    as_of: date,
    *,
    n: int = 500,
    lookback_days: int = 105,
    skip_days: int = 21,
    min_names: int = 20,
) -> pd.DataFrame:
    """PIT cross-sectional momentum. Returns a DataFrame indexed by ticker with
    columns [momentum, winsorized, zscore, rank, score], sorted by score desc.
    `score` == zscore (the primary signal). Raises FactorUnavailable if fewer than
    `min_names` valid names. Deterministic — identical inputs -> identical frame."""
```

Pipeline: `universe_asof(store, as_of, n=n)` → `compute_momentum_batch` →
drop `None`s → `standardize` → assemble + sort. No data after `as_of` is read.

### 4.5 Sandboxed accessor (`accessor.py`)

```python
class FactorDataUnavailable(RuntimeError): ...

class FactorAccessor:
    """Read-only, PIT-clamped facade over a FactorDataStore for strategy code.
    Holds no DB session, opens no network, imports no order path. `store=None`
    means factor data is not provisioned -> every method raises
    FactorDataUnavailable with a clear message (mirrors how an absent Alpaca key
    degrades the bar cache)."""

    def __init__(self, store: FactorDataStore | None) -> None: ...
    def momentum_scores(self, as_of: date | None = None, *, n: int = 500) -> pd.DataFrame
    def momentum_for(self, ticker: str, as_of: date | None = None) -> float | None
    def universe(self, as_of: date | None = None, *, n: int = 500) -> list[str]
```

- `as_of=None` → the store's latest price date; an `as_of` past that clamps down.
- The accessor never exposes the raw `store` handle, `con`, or ingest methods —
  only the three read methods above.

### 4.6 Context wiring

- `StrategyContext.__init__` gains `factor_accessor: FactorAccessor | None = None`
  (optional, like `bus`); `@property def factors(self) -> FactorAccessor` returns
  it or raises `FactorDataUnavailable` if `None`. **Verified** against the current
  constructor (context.py:96–) and `BarCache.get_bars(symbol, timeframe, start,
  end) -> DataFrame` (bar_cache.py:84) — this is purely additive; no existing
  signature changes.
- `BacktestContext` gets the same `.factors` for §3 parity (backed by the same
  read-only store or a fixture accessor).
- The strategy engine constructs one shared `FactorAccessor(FactorDataStore(read_only
  =True))` when the DuckDB file exists, else `FactorAccessor(None)`. (Locate the
  single construction site of `StrategyContext` in the engine and inject there —
  confirm before editing; do not assume a second call site.)

### 4.7 Tests (load-bearing first)

- **★ No look-ahead**: build a synthetic store; compute `momentum_scores(D)`;
  append prices dated after `D`; recompute — **identical** scores. The §2 honesty
  hinge.
- **★ Sandbox**: `FactorAccessor(None)` raises `FactorDataUnavailable`; the
  accessor surface exposes no `store`/`con`/ingest; `check_strategy_isolation.sh`
  still green (no `app.brokers` import reachable from `app/strategies/`).
- **Momentum math**: a known geometric price path → exact 6–1 return; the **skip**
  window verifiably excludes the last 21 trading days; insufficient history → `None`.
- **Cross-section math**: `zscore` mean≈0/std≈1; zero-variance → zeros; `rank` in
  `[0,1]` monotonic; `winsorize` caps at the quantiles.
- **Engine**: synthetic universe → expected score ordering; `< min_names` →
  `FactorUnavailable`; `as_of` clamp.
- **Reproducibility**: two calls → identical frame/list.
- Tests use the synthetic-data fixture pattern from §1 (`tests/factor_data/conftest.py`)
  — no committed vendor bytes (ADR 0018 §6).

## 5. Manual smoke

From the host venv, against the §1-ingested store (`apps/backend/data/factor_data.duckdb`,
which has AAPL/MSFT/NVDA/KO + full TICKERS):

```bash
PYTHONPATH=apps/backend apps/backend/.venv/Scripts/python.exe - <<'PY'
from app.factor_data.store import FactorDataStore
from app.factor_data.accessor import FactorAccessor
acc = FactorAccessor(FactorDataStore(read_only=True))
df = acc.momentum_scores()          # as of latest store date
print(df[["momentum", "zscore", "rank"]].round(3))
print("AAPL momentum:", acc.momentum_for("AAPL"))
PY
```

**Pass:** a momentum value + z-score + rank per ingested name (with enough history),
deterministic across runs, and `momentum_for` on a name with insufficient history
returns `None` — not a fabricated number. (To exercise the full ~500-name
cross-section, ingest a broader ticker pool per `docs/runbook/factor-data.md` §2/§4;
the smoke above works on the small §1 set.) No order-path assertion applies — §2
touches no order path.

## 6. Walk-away discipline

≥ 1 hour. §2 adds a read-only factor-computation layer + a sandboxed read accessor;
**no order-path, risk-engine, or audit-log surface**, so the routine minimum applies.

## 7. What this session does NOT do

- **No backtest, no portfolio construction, no rebalance** — §3 (incl. the named
  delisting-return decision).
- **No FMP / fundamentals / value / quality / earnings / 13F factors** — §5+.
- **No MTG factor strategy** — §4.
- **No `BarCache` refactor / provider abstraction** — deferred (Direction §7; carries
  a `# VERIFY-CAPABILITY-EXISTS` when eventually done).
- **No live, no order-path touch, no new CI invariant**, no agent/MCP exposure of
  factor data (licensing — ADR 0018 §6).
- **No LLM** in the factor path — momentum is deterministic Python (ADR 0006 v2).

## 8. Notes & gotchas

1. **No look-ahead is the hinge.** The append-future-prices test (§4.6 ★) is the
   §2 analog of §1's delisted-name test. Do not weaken it.
2. **Trading-day offsets, not calendar math.** Endpoints are row offsets into the
   on/before-`as_of` slice; this is what makes the score robust to holidays and a
   name's listing/delisting edges.
3. **Read-only store, always.** The accessor opens DuckDB with `read_only=True`; a
   live strategy must never be able to mutate the factor store. (DuckDB also
   single-writers — a read-only handle avoids contending with an ingest.)
4. **Degrade, don't crash.** No store file → `FactorAccessor(None)` → clear
   `FactorDataUnavailable`, never an import-time or construction-time failure of the
   strategy engine.
5. **Survivorship carries through.** Momentum over `universe_asof(D)` already
   includes names that were tradeable at `D` but later delisted — keep computing
   their score from their own history; do not silently drop delisted names from a
   *past* cross-section.
6. **Confirm the single `StrategyContext` construction site** before wiring the
   accessor (the assumed-call-site class of error, cf. Direction §4 / the §4
   `call_with_budget` fabrication). The Explore pass found context.py:96 as the
   definition; verify the engine's injection point before editing.
