# P8 Session 2 — Scanner Engine (criteria evaluation) — Results

| Field | Value |
|---|---|
| Document version | v0.1 (execution results) |
| Date | 2026-06-07 |
| Phase | P8 — Discovery screener + Range Insight (§2 of 7 — P8a) |
| Plan doc | `TradingWorkbench_P8_Session2_ScannerEngine_v0_1.md` |
| Predecessor | `p8-session1-discovery-feeds-complete` (§1) |
| Tag | **`p8-session2-scanner-engine-complete`** (moved onto the §2 todo commit) |
| Shipped as | PR **#75** — branch `feat/p8-session2-scanner-engine`; squash-merged `a8cffd4` |
| Verdict | **GO.** A saved criterion runs deterministically over a universe, matched/skipped recorded + audited. Full suite + 3 coverage gates + all 10 invariants green; first P8 migration round-trips. |

## What shipped

- **`app/services/scanner/criteria.py`** — the safe boolean-expression evaluator. `validate_criteria(expr)` runs `ast.parse(mode="eval")` then walks an **allowlist** (`Expression / BoolOp(And,Or) / UnaryOp(Not,USub,UAdd) / BinOp(+,-,*,/) / Compare(<,<=,>,>=,==,!=) / Constant(numeric, bool rejected) / Name(Load, id ∈ ALLOWED_NAMES)`) — everything else (`Call`, `Attribute`, `Subscript`, comprehension, `**`, str/bytes const, unknown name) raises `CriteriaError`. `ALLOWED_NAMES` is **derived from `CORE_INDICATORS`** (singles + multi-output sub-names `macd/signal/hist`, `bb_lower/bb_mid/bb_upper`) ∪ bar fields `{open,high,low,close,volume,price}`. `evaluate(parsed, values)` = `eval(code, {"__builtins__": {}}, values)` — safe because the tree was allowlist-validated. `ParsedCriteria` also carries `indicators` (reverse-mapped `CORE_INDICATORS` to compute).
- **`app/services/scanner/engine.py`** — `resolve_universe` for `{discovery_feeds, watchlist, symbols}` (dedup + upper; watchlist mirrors `morning_brief` core+swing−do_not_trade) + `run_scan`: per symbol → `bar_cache.get_bars` (400-day daily lookback) → `IndicatorComputer.compute` (only referenced indicators) → `_latest_values` → `evaluate`. **Skip-and-record**: empty bars → `no_bars`, any referenced value NaN/absent → `nan_indicator`; the scan never raises on a per-symbol problem.
- **Models + migration** — `scanner_definitions` (criteria, universe spec, timeframe) + `scanner_runs` (criteria snapshot, matched/skipped JSON + counts, status). Alembic `c2f5a8d31e7b` (down-rev `b6d1f4a8c3e2`); up→down→up verified. Registered in `app/db/models/__init__.py`.
- **`AuditAction.SCANNER_RUN`** — written on every run (criterion + universe + matched symbols → reconstructible from the criterion alone, P8 Decision 1). Documented as read-only / non-paging → no on-call runbook scenario.
- **`app/api/v1/scanner.py`** (prefix `/scanner`, after `discovery.router`) — `POST/GET/GET/DELETE /definitions[/{id}]`, `POST /definitions/{id}/run`, `GET /definitions/{id}/runs`, `GET /runs/{id}`. Auth-gated, user-scoped. Invalid criterion → 400; unknown/empty universe → 400; `app.state.bar_cache` absent → 503; non-owner → 404.

## Decisions settled (owner, 2026-06-07 — AskUserQuestion)

1. **Criterion syntax: bare supported-indicator names** (`RSI14 < 35 …`). The engine's indicators are fixed-period (no `rsi(7)`); the Direction's `rsi(14)` was illustrative. Drift-proof allowlist, trivial safe evaluator (no `Call`).
2. **Universe: a stored spec** {`discovery_feeds`, `watchlist`, `symbols`}. Preset index universes (S&P 500 / NASDAQ 100) **deferred** — no membership data exists yet.
3. **Per-symbol failure (Direction Q2): skip-and-record.** A bad symbol is recorded with a reason; the scan continues.

## Verification

- **27 new tests:** criteria (valid eval true/false, price-aliases-close, multi-output→core map, 12-case rejection battery, drift guard over `CORE_INDICATORS`); engine (match + no-match + `no_bars` + `nan_indicator` + field-only criterion + all three universe kinds with a seeded `TradingProfile`); endpoints (CRUD lifecycle, invalid→400, run persists+audits a `SCANNER_RUN` row, no-bar-cache→503, other-user→404).
- Full backend suite **exit 0** (2 known AAPL-fixture skips); ruff + mypy **(197 files)** clean; migration round-trips; **all 10 shell invariants** + the **ADR-0002 invariant test** + **3 coverage gates** (risk branch 0.904 / P2 / P3) green. **No frontend.**
- CI on PR #75: all jobs green first try (Python backend 5m44s). Merged on "merge on green".

## Notes / carry-forward

- The run endpoint instantiates the **real `IndicatorComputer()`**; tests therefore use a field-only criterion (`close > 50`) to stay deterministic without depending on indicator math. The §3 UI will exercise real indicators against live/cached bars.
- `eval` safety rests entirely on the allowlist running first — never relax the validator. `run_scan` re-parses defensively (a stored row could predate a vocabulary change).
- Edit (`PUT`) of a definition is deferred to §3 (saved-scan management UI); §2 is create/delete.

## Next

**P8 §3 — Discovery view UI.** The frontend over these endpoints: a **criteria builder** (with the supported-indicator vocabulary + `price`/field help), a **scope picker** (feeds / watchlist / explicit symbols), a **results table** (ranked matches + the indicator values that matched + skipped count), and **saved-scan management** (incl. the deferred edit). Zero-dep (Norton). Then §4 wires scheduled scanning + pushes results into the Opportunities view.
