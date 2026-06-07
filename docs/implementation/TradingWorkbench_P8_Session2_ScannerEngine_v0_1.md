# Trading Workbench — P8 §2: Scanner Engine (criteria evaluation)

| Field | Value |
|---|---|
| Document version | v0.1 |
| Date | 2026-06-07 |
| Phase | P8 — Discovery screener + Range Insight (§2 of 7 — P8a) |
| Predecessor | `p8-session1-discovery-feeds-complete` (§1) |
| Successor | `TradingWorkbench_P8_Session3_*` (Discovery view UI — §3) |
| Direction | `TradingWorkbench_P8_Direction_v0.1.md` (Decision 1, 6; open Q1, Q2) |
| Repository | github.com/jayw04/AI-TRADING-APP |
| Scope | The scanner engine: store a user-authored boolean criterion + universe spec, evaluate it against the latest indicator values for each symbol in the universe (from cached bars), and persist an audited run. Backend only — the Discovery view UI is §3. |
| Estimated wall time | 5–7 hours |
| Tag on completion | `p8-session2-scanner-engine-complete` |
| Out of scope | See §"What this session does NOT do" |

---

## Why this session exists

§1 landed the candidate-symbol *seed source* (Alpaca most-actives + movers). §2 is the engine that turns "a universe of symbols" + "a criterion" into "the symbols that match" — the heart of the Discovery screener. A trader writes a boolean expression over the platform's supported indicators (e.g. `RSI14 < 35 and ATR14 / close > 0.02`), picks a universe, and the engine evaluates it deterministically against cached bars and records the run.

Two architectural invariants shape the whole design:

- **Decision 1 — user-configured, not AI-recommended.** Criteria are authored by the user, evaluated deterministically, and audit-logged so "why did this symbol appear" is reconstructible *from the criterion alone*. No LLM anywhere in §2.
- **Decision 6 — the criterion is a boolean expression in the platform's own indicator vocabulary; no new mini-language, no separate parser.** We reuse Python's own grammar (`ast.parse`) and restrict it to a safe allowlist — the criterion references the *supported indicator names* as bare variables.

## What this session ships

1. `app/services/scanner/criteria.py` — a **restricted-AST boolean-expression evaluator**: allowlist of `BoolOp / UnaryOp(Not, -) / BinOp(+,-,*,/) / Compare / Constant(number) / Name(supported)`; the supported-name set is **derived from `CORE_INDICATORS`** (drift-proof) plus bar fields; `validate_criteria` + `evaluate`.
2. `app/services/scanner/engine.py` — universe resolution ({`discovery_feeds`, `watchlist`, `symbols`}) + `run_scan` (per-symbol: bars → indicators → evaluate; **skip-and-record** on missing/NaN).
3. `app/db/models/scanner_definition.py` + `app/db/models/scanner_run.py` + Alembic migration (head `b6d1f4a8c3e2` → new) — registered in `app/db/models/__init__.py`.
4. `AuditAction.SCANNER_RUN` + audit write on every run.
5. `app/api/v1/scanner.py` + `schemas/scanner.py` — create / list / get / delete a definition; **run** a definition; list a definition's runs; get one run. Auth-gated, user-scoped.
6. Tests: criteria evaluator (valid eval + every rejection class + drift guard), engine (match/skip/universe resolution, mocked bar cache), endpoints (CRUD + run + ownership + invalid-criterion 400).

## Prerequisites

- §1 complete (`p8-session1-discovery-feeds-complete`) — `app/market_data/discovery.get_discovery_feeds` is the `discovery_feeds` universe source.
- Migration head is `b6d1f4a8c3e2` (P7 §5). The §2 migration's `down_revision = "b6d1f4a8c3e2"`.
- `app.state.bar_cache` is the bar source (None in data-only boots → the run endpoint returns 503, not a misleading empty result).

## Decisions settled for §2 (owner, 2026-06-07 — AskUserQuestion)

- **Criterion syntax: bare supported-indicator names.** `RSI14 < 35 and ATR14 / close > 0.02`. The allowed-name set is built from `CORE_INDICATORS` (single: `SMA20/50/200`, `EMA9/20/21/50`, `RSI14`, `ATR14`, `VWAP`, `RELVOL20`; multi-output expanded: `MACD`→`macd/signal/hist`, `BB`→`bb_lower/bb_mid/bb_upper`) plus bar fields `open/high/low/close/volume/price` (`price` aliases `close`). The Direction's `rsi(14)` example was illustrative; bare names match the *actual* fixed-period vocabulary (there is no arbitrary-period `rsi(7)`), keep the safe evaluator trivial (no `Call` nodes), and are drift-proof.
- **Universe: a stored spec on the definition** — `kind ∈ {discovery_feeds, watchlist, symbols}` (+ `symbols` list for the explicit kind). Preset index universes (S&P 500, NASDAQ 100) are **deferred** — no membership data exists yet; that's a later session.
- **Per-symbol failure (Direction Q2): skip-and-record.** A symbol with no bars or a NaN referenced indicator is recorded in the run's `skipped` list with a reason; the scan continues. The run reports `evaluated / matched / skipped` counts. One bad symbol never aborts the scan.

## Detailed work

### §2.1 — `criteria.py` (the safe evaluator)

```python
class CriteriaError(ValueError): ...        # invalid / unsafe criterion (→ 400)

# Built from app.indicators.computer.CORE_INDICATORS — drift-proof.
_MULTI = {"MACD": ("macd", "signal", "hist"), "BB": ("bb_lower", "bb_mid", "bb_upper")}
INDICATOR_NAMES: frozenset[str]   # singles ∪ flattened multi sub-names
FIELD_NAMES = frozenset({"open", "high", "low", "close", "volume", "price"})
ALLOWED_NAMES = INDICATOR_NAMES | FIELD_NAMES

@dataclass(frozen=True)
class ParsedCriteria:
    code: CodeType                # compiled ast.Expression
    names: frozenset[str]         # referenced ALLOWED_NAMES
    indicators: frozenset[str]    # CORE_INDICATORS to compute (reverse-mapped)

def validate_criteria(expr: str) -> ParsedCriteria:
    # ast.parse(expr, mode="eval"); walk allowlist; collect Name ids;
    # reject anything not in ALLOWED_NAMES or any disallowed node → CriteriaError.

def evaluate(parsed: ParsedCriteria, values: dict[str, float]) -> bool:
    # eval(parsed.code, {"__builtins__": {}}, values) → bool(...)
```

Allowlisted node types **only**: `Expression, BoolOp(And|Or), UnaryOp(Not|USub), BinOp(Add|Sub|Mult|Div), Compare(Lt|LtE|Gt|GtE|Eq|NotEq), Constant(int|float), Name(Load, id ∈ ALLOWED_NAMES)`. Everything else — `Call, Attribute, Subscript, comprehensions, str/bytes constants, `**`, bit-ops, walrus, lambda — raises `CriteriaError`. Because the tree is validated to arithmetic/compare/bool over floats with empty `__builtins__`, `eval` is safe (this is the same AST-walk muscle as P7 §3's `code_safety.py`, inverted to an allowlist). `indicators` reverse-maps each referenced name to the `CORE_INDICATORS` entry to compute (`macd`→`MACD`, `RSI14`→`RSI14`).

### §2.2 — `engine.py` (universe + run)

```python
SCAN_TIMEFRAME_DEFAULT = "1Day"
_LOOKBACK_DAYS = {"1Day": 400}   # ≥200 daily bars for SMA200; default 400

@dataclass(frozen=True)
class SymbolMatch:  symbol: str; values: dict[str, float]      # the referenced values, for the "why"
@dataclass(frozen=True)
class SymbolSkip:   symbol: str; reason: str                   # "no_bars" | "nan_indicator"
@dataclass(frozen=True)
class ScanResult:   matched: list[SymbolMatch]; skipped: list[SymbolSkip]; evaluated: int; universe_size: int

async def resolve_universe(session, *, kind, symbols, user_id, discovery_feeds_fn) -> list[str]:
    # discovery_feeds → most_actives ∪ gainers ∪ losers symbols (deduped, upper)
    # watchlist       → TradingProfile.watchlist_json core+swing_candidates − do_not_trade
    # symbols         → the explicit list (deduped, upper)

async def run_scan(session, *, definition, bar_cache, indicator_computer,
                   discovery_feeds_fn, now) -> ScanResult:
    parsed = validate_criteria(definition.criteria)
    universe = await resolve_universe(...)
    for sym in universe:
        bars = await bar_cache.get_bars(sym, tf, start, now)        # start = now − lookback
        if bars.empty: skipped.append(SymbolSkip(sym, "no_bars")); continue
        series = indicator_computer.compute(bars, names=list(parsed.indicators), symbol=sym, timeframe=tf)
        values = _latest_values(bars, series, parsed.names)         # fields + latest indicator values
        if values is None: skipped.append(SymbolSkip(sym, "nan_indicator")); continue
        if evaluate(parsed, values): matched.append(SymbolMatch(sym, {n: values[n] for n in parsed.names}))
    return ScanResult(matched, skipped, evaluated=len(universe) − len(no_bars-skips?), universe_size=len(universe))
```

`_latest_values` extracts `open/high/low/close/volume` from the last bar (`price`=close), and the latest of each referenced indicator series (multi-output via the sub-key); returns `None` if any *referenced* value is NaN/absent (→ skip `nan_indicator`). The engine never raises on a per-symbol problem.

### §2.3 — Models + migration

`scanner_definitions`: `id`, `user_id`(FK users, idx), `name`(String 120), `criteria`(Text), `universe_kind`(String 16), `universe_symbols_json`(JSON null), `timeframe`(String 8, default `"1Day"`), `created_at`/`updated_at`(DateTime tz).

`scanner_runs`: `id`, `scanner_definition_id`(FK CASCADE, idx), `user_id`(FK, idx), `run_at`(DateTime tz), `status`(String 16 — `"ok"`|`"error"`), `criteria_snapshot`(Text), `universe_kind`(String 16), `timeframe`(String 8), `universe_size`/`evaluated_count`/`matched_count`/`skipped_count`(Int), `matched_json`(JSON — `[{symbol, values}]`), `skipped_json`(JSON — `[{symbol, reason}]`), `error`(Text null). Index `(scanner_definition_id, run_at)`.

Alembic `down_revision = "b6d1f4a8c3e2"`; `create_table` both + indexes; `downgrade` drops both. Reviewed up/down; round-trips.

### §2.4 — Audit

`AuditAction.SCANNER_RUN = "SCANNER_RUN"`. On each run, before commit:
`AuditLogger.write(session, actor_type=USER, actor_id=str(user_id), action=SCANNER_RUN, target_type="scanner_definition", target_id=definition.id, user_id=user_id, payload={criteria, universe_kind, timeframe, universe_size, matched_count, skipped_count, matched_symbols:[...]})`. This makes the run reconstructible from the criterion (Decision 1). SCANNER_RUN is a **read-only scan** (no orders / no state change beyond its own run-history row) — informational, not a paging event; no on-call runbook scenario (cf. the suppressed-order "logged-not-audited" precedent — here it *is* audited, but it is not operationally consequential).

### §2.5 — API (`app/api/v1/scanner.py`, prefix `/scanner`)

- `POST /scanner/definitions` `{name, criteria, universe:{kind, symbols?}, timeframe?}` → `validate_criteria` (CriteriaError → **400**) → row → 201.
- `GET /scanner/definitions` → the user's definitions.
- `GET /scanner/definitions/{id}` → one (404 if not owner).
- `DELETE /scanner/definitions/{id}` → 204 (cascades runs).
- `POST /scanner/definitions/{id}/run` → resolve `app.state.bar_cache` (missing → **503**) + `IndicatorComputer()` + `get_discovery_feeds` → `run_scan` → persist `ScannerRun` + audit → return the run.
- `GET /scanner/definitions/{id}/runs?limit=` → recent runs (newest first).
- `GET /scanner/runs/{run_id}` → one run (full `matched`/`skipped`; 404 if not owner).

Registered after `discovery.router` in `app/api/v1/__init__.py`.

### §2.6 — Tests

- **criteria** (`tests/services/test_scanner_criteria.py`): a valid expression evaluates true/false over a values dict; **rejections** — unknown name, `Call` (`rsi(14)`), `Attribute`, `Subscript`, string constant, `__import__`/dunder, comprehension, `**`; the referenced-indicator reverse-map (`macd`→`MACD`); **drift guard** — every `CORE_INDICATORS` single + multi sub-name is in `ALLOWED_NAMES`.
- **engine** (`tests/services/test_scanner_engine.py`): match + non-match + `no_bars` skip + `nan_indicator` skip with a fake bar cache + a stub indicator computer; universe resolution for all three kinds (fake `discovery_feeds_fn`, a seeded `TradingProfile`, an explicit list).
- **endpoints** (`tests/api/test_scanner_endpoint.py`): create→get→list→delete; invalid criterion → 400; run with a fake `app.state.bar_cache` → persisted run + matched/skipped in the body + a `SCANNER_RUN` audit row; bar cache absent → 503; other-user definition → 404.

## Manual smoke

```
# create a definition, run it (needs app.state.bar_cache; Norton blocks live Alpaca so use cached fixtures):
curl -s -XPOST localhost:8000/api/v1/scanner/definitions -H "Authorization: Bearer $TOK" \
  -d '{"name":"oversold","criteria":"RSI14 < 35","universe":{"kind":"symbols","symbols":["AAPL","MSFT"]}}' | jq .id
curl -s -XPOST localhost:8000/api/v1/scanner/definitions/1/run -H "Authorization: Bearer $TOK" \
  | jq '{status, matched_count, skipped_count, matched: [.matched[].symbol]}'
```

Load-bearing assertion: a saved criterion runs deterministically over the universe, the run row + audit row are written, and a thin/missing symbol is *skipped*, not fatal.

## Walk-away discipline

New tables + an audit action, but no order-path / risk / live touch → **≥1 hour** between ready-for-review and merge.

## What this session does NOT do

- **No frontend** — the Discovery view (criteria builder, scope picker, results table, saved-scan management) is **§3**.
- **No scheduled scanning / Opportunities integration** — **§4** (APScheduler + push to the Opportunities view).
- **No preset index universes** (S&P 500 / NASDAQ 100 membership) — deferred; §2 universes are feeds / watchlist / explicit list.
- **No `PUT` (edit) endpoint** — §3 (saved-scan management UI); §2 is create/delete (edit = delete+recreate for now).
- **No result caching / freshness policy** (Direction Q1) — each run recomputes and is stored; caching is a §4 scheduling concern.
- **No non-1Day timeframe support** beyond storing the column — §2 scans daily (the pre-market screener cadence); other timeframes are future.
- **No LLM anywhere** (Decision 1) — deterministic evaluation only; the no-LLM invariant stays satisfied without an allowlist entry.
- **No order-path / risk-engine change, no new CI invariant.**

## Notes & gotchas

1. **`eval` is safe *only because* the AST is allowlist-validated first** with `{"__builtins__": {}}`. Never `eval` an un-validated criterion. The validator runs at **save time** (400 on bad input) *and* `run_scan` re-parses defensively (a row could predate a vocabulary change).
2. **Drift-proof vocabulary** — `ALLOWED_NAMES` is *derived* from `CORE_INDICATORS`, so a new engine indicator is automatically allowable; the drift-guard test asserts the derivation covers every core single + multi sub-name (a rename that breaks the `_MULTI` mapping fails CI).
3. **NaN is a skip, not a False** — a symbol whose referenced indicator is NaN (insufficient bars for SMA200, a halted name) is `skipped` with reason `nan_indicator`, never silently counted as "didn't match." Coverage honesty (Decision 1).
4. **`app.state.bar_cache` may be absent** (data-only boots / tests that don't wire it) — the run endpoint returns **503** rather than a misleading empty scan. Tests inject a fake cache onto `app.state`.
5. **`price` aliases `close`** — both resolve to the last bar's close; documented in the criterion help (§3 surfaces it).
6. **Universe dedup + `do_not_trade`** — the watchlist universe mirrors `morning_brief`'s resolution (`core` + `swing_candidates` minus `do_not_trade`, upper-cased, deduped).
