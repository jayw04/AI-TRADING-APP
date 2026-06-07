# Trading Workbench — P8 §3: Discovery View UI

| Field | Value |
|---|---|
| Document version | v0.1 |
| Date | 2026-06-07 |
| Phase | P8 — Discovery screener + Range Insight (§3 of 7 — P8a) |
| Predecessor | `p8-session2-scanner-engine-complete` (§2) |
| Successor | `TradingWorkbench_P8_Session4_*` (scheduled scanning + Opportunities — §4) |
| Direction | `TradingWorkbench_P8_Direction_v0.1.md` |
| Repository | github.com/jayw04/AI-TRADING-APP |
| Scope | The Discovery page — author a criterion (free-text + vocabulary helper), pick a universe, save/run a scan, and act on the matches (add to watchlist). Plus the §2-deferred edit (PUT) endpoint + a drift-proof vocabulary endpoint. |
| Estimated wall time | 4–6 hours |
| Tag on completion | `p8-session3-discovery-view-complete` |
| Out of scope | See §"What this session does NOT do" |

## Why this session exists

§2 shipped the scanner engine + endpoints (criteria evaluation, runs, audit). §3 puts a face on it: a first-class **Discovery** page in the main nav where a trader authors a criterion, picks a scope, runs the scan, and sees the ranked matches — the native screener the Direction calls for. It also closes the two small backend gaps §2 deferred: **editing** a saved scan in place (preserving its run history) and a **vocabulary** endpoint so the criterion helper can't drift from the engine's supported indicators.

## What this session ships

1. **Backend** — `PUT /api/v1/scanner/definitions/{id}` (edit in place; re-validates) + `GET /api/v1/scanner/vocabulary` → `{indicators, fields}` (sorted, **derived from `CORE_INDICATORS`** via the criteria module). `_validate_body` extracted and shared by create + update.
2. **`src/api/scanner.ts`** — typed client (`vocabulary/list/create/update/remove/run/listRuns/getRun`).
3. **`src/pages/Discovery/index.tsx`** — the page; `/discovery` added to `NAV_ITEMS` (auto-nav).
4. **Tests** — 3 backend (PUT preserves id, PUT invalid→400, vocabulary) + 5 frontend (lists scans + chips, chip insert, create, 400-detail surfaced, run + add-to-watchlist).

## Prerequisites

- §2 complete (`p8-session2-scanner-engine-complete`) — the `/scanner` endpoints + `app/services/scanner/criteria.py` (`INDICATOR_NAMES`/`FIELD_NAMES`).
- Frontend `apiFetch`/`ApiError` (`src/api/client.ts`), `tradingProfileApi` (watchlist write), the global `QueryClientProvider` (unused here — plain state, see Notes).

## Decisions settled for §3 (owner, 2026-06-07 — AskUserQuestion)

- **Criteria input: free-text + vocabulary helper.** A criterion textarea (`RSI14 < 35 and ATR14 / close > 0.02`) with clickable **insert-chips** (operators + the supported indicator names + bar fields, served by `GET /scanner/vocabulary`) and **inline validation** — the create/update 400 (`detail`) is surfaced verbatim. Matches the §2 free-text backend exactly; full expressiveness; least code; zero-dep.
- **Result-row action: add-to-watchlist.** Each matched row shows the symbol + the indicator values that matched + a `+ watchlist` button (merges into the profile's `swing_candidates` via the existing `tradingProfileApi.update`). **Open-in-Charts deferred** (the Charts page takes no symbol param — needs a separate Charts change); **apply-template is §7** (range template).

## Detailed work

### §3.1 — Backend (PUT + vocabulary)

- `GET /scanner/vocabulary` (auth-gated): `ScannerVocabulary(indicators=sorted(INDICATOR_NAMES), fields=sorted(FIELD_NAMES))`. The helper is drift-proof — the names come from the same `CORE_INDICATORS`-derived set the evaluator allows.
- `PUT /scanner/definitions/{id}` (auth-gated, ownership-checked): re-validates the body (same `_validate_body` as create), updates the row in place (id + run history preserved), bumps `updated_at`. Edit-via-PUT beats delete+recreate because the latter cascade-deletes the definition's `scanner_runs`.

### §3.2 — `src/pages/Discovery/index.tsx`

Plain `useState/useEffect` (mirrors `AuthorWithAI`; no `QueryClientProvider` needed in tests). Layout: a `Saved scans` sidebar + an editor/results column.

- **Editor card** — name input; criteria textarea + a chip row (`< > <= >= and or /` + indicator chips + field chips, each `insertToken`s into the criterion); a universe `<select>` (`discovery_feeds` / `watchlist` / `symbols`) with a symbols input when `symbols`; Create/Save + Run (when saved) + Delete; a 400 `detail` error box; a success notice.
- **Results card** — `latestRun`: a `matched / universe (evaluated, skipped)` summary line + a table (Symbol | one column per referenced value, `.toFixed(2)` | `+ watchlist`). Empty → "No symbols matched."
- **Recent runs** — the definition's run history; clicking a row re-loads that run via `getRun`.
- **Add-to-watchlist** — `tradingProfileApi.get` → merge the symbol into `watchlist.swing_candidates` (dedup, case-insensitive) → `update`; idempotent ("already on your watchlist").

## Manual smoke

1. Nav → **Discovery**. "New scan", name it, type `RSI14 < 35`, pick "Specific symbols", enter `AAPL, MSFT`. Create.
2. Run scan → matched table renders (needs `app.state.bar_cache`; Norton blocks live Alpaca, so use a cached-fixture stack).
3. Click `+ watchlist` on a row → the profile's `swing_candidates` gains the symbol (verify in Settings → Trading Profile).
4. Type an invalid criterion (`rsi < 30`) → Save shows "invalid criterion: unknown name: rsi".

## Walk-away discipline

UI + two thin read/edit endpoints, no order-path / risk / audit-action change → **≥1 hour**.

## What this session does NOT do

- **No scheduled scanning / Opportunities integration** — §4 (APScheduler + push to the Opportunities view).
- **No open-in-Charts deep-link** — the Charts page takes no symbol param; deferred (needs a Charts change).
- **No apply-template action** — §7 (the range-trading template).
- **No structured criteria builder** — free-text + helper (settled).
- **No new table / migration / audit action** — §3 is UI + a PUT/GET over §2's tables.
- **No client-side AST validation** — the server is the single validator; its 400 `detail` is surfaced.
- **No preset index universes** — still deferred (no membership data).

## Notes & gotchas

1. **Plain state, not react-query** — keeps the page test to just `MemoryRouter` (a react-query page needs a `QueryClientProvider` wrapper in tests). The list refetches after each mutation via `refreshDefinitions`.
2. **Drift-proof helper** — the chip names come from `GET /scanner/vocabulary` (server-derived from `CORE_INDICATORS`), never a hardcoded frontend list, so a new engine indicator shows up automatically.
3. **Inline validation = the server's 400** — no AST in the browser; `errDetail` pulls `body.detail` from the `ApiError`.
4. **Watchlist merge is idempotent + case-insensitive** — re-adding a held symbol is a no-op with a friendly notice.
5. **Column set is the union of referenced value keys** — all matched rows of one criterion share the same names, so the table columns are stable within a run.
