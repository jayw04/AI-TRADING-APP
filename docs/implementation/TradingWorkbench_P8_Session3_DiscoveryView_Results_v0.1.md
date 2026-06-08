# P8 Session 3 — Discovery View UI — Results

| Field | Value |
|---|---|
| Document version | v0.1 (execution results) |
| Date | 2026-06-07 |
| Phase | P8 — Discovery screener + Range Insight (§3 of 7 — P8a) |
| Plan doc | `TradingWorkbench_P8_Session3_DiscoveryView_v0_1.md` |
| Predecessor | `p8-session2-scanner-engine-complete` (§2) |
| Tag | **`p8-session3-discovery-view-complete`** (moved onto the §3 todo commit) |
| Shipped as | PR **#76** — branch `feat/p8-session3-discovery-view`; squash-merged `5f2ca09` |
| Verdict | **GO.** A trader can author/save/run a scan from the UI and act on the matches. Backend full suite + frontend vitest + all 10 invariants + 3 coverage gates green; no migration. |

## What shipped

- **Backend (closes §2's two deferrals):**
  - `GET /api/v1/scanner/vocabulary` → `ScannerVocabulary{indicators, fields}` (sorted, **derived from `CORE_INDICATORS`** via `app/services/scanner/criteria.py` `INDICATOR_NAMES`/`FIELD_NAMES`). The criterion helper is drift-proof — never a hardcoded frontend list.
  - `PUT /api/v1/scanner/definitions/{id}` — edit a saved scan **in place** (id + `scanner_runs` history preserved, unlike delete+recreate); re-validates via the shared `_validate_body` (extracted, now used by both create + update).
- **Frontend:**
  - `src/api/scanner.ts` — typed client (`vocabulary/list/create/update/remove/run/listRuns/getRun`).
  - `src/pages/Discovery/index.tsx` — a saved-scan sidebar + editor (criteria textarea + **insert-chips** from the vocabulary [operators + indicators + fields] + **inline validation** surfacing the create/update 400 `detail`; universe `<select>` `discovery_feeds`/`watchlist`/`symbols` with a symbols input; create/save/run/delete) + a **results table** (Symbol | one column per referenced value `.toFixed(2)` | `+ watchlist`; `matched/universe (evaluated, skipped)` summary) + run history (click a run → `getRun`). **Add-to-watchlist** merges the symbol into `watchlist.swing_candidates` via the existing `tradingProfileApi.update` (idempotent, case-insensitive). Plain `useState/useEffect` (mirrors `AuthorWithAI`).
  - `/discovery` added to `NAV_ITEMS` in `routes.tsx` (auto-rendered in the sidebar).

## Decisions settled (owner, 2026-06-07 — AskUserQuestion)

1. **Criteria input: free-text + vocabulary helper.** Matches the §2 free-text backend exactly; full expressiveness (`ATR14 / close`); inline validation via the server's 400 `detail`; zero-dep.
2. **Result-row action: add-to-watchlist.** Open-in-Charts **deferred** (the Charts page takes no symbol param — needs a separate Charts change); apply-template is **§7** (range template).

## Verification

- **3 backend tests** (PUT preserves id + edits fields; PUT invalid criterion → 400; vocabulary contains `RSI14`/`macd`/`close`/`price`) + **5 frontend tests** (lists scans + renders vocabulary chips; chip insert appends a token; create calls `scannerApi.create` with the body; a 400 `detail` is surfaced verbatim; run renders the matched table + `+ watchlist` calls `tradingProfileApi.update` with the merged `swing_candidates`).
- **Backend:** full suite exit 0 (2 known AAPL-fixture skips); ruff + mypy **(197)** clean; all **10 shell invariants** + **3 coverage gates** (risk 0.904/P2/P3) green. **No migration / no new audit action.**
- **Frontend:** vitest **141** (+5, 28 files) + tsc + eslint clean.
- **CI flake:** `Build image (agent)` failed once on a **Docker Hub registry timeout** booting buildkit (`registry-1.docker.io … context deadline exceeded`, in `Set up Buildx` — before any code build; §3 touched nothing in the agent image). Re-ran the failed job → passed (21s). All test jobs + other builds green first try. Merged on "merge on green".

## Notes / carry-forward

- **Plain state, not react-query** — keeps the page test to just `MemoryRouter` (a react-query page needs a `QueryClientProvider` wrapper). The definitions list refetches after each mutation.
- **Open-in-Charts is the one deferred action** — wiring it needs the Charts page to read a `?symbol=` param on mount (a Charts change), out of §3 scope. Apply-template lands in §7.
- The results-table columns are the union of referenced value keys; stable within a run since all matched rows of one criterion share the same names.

## Next

**P8 §4 — scheduled scanning + Opportunities integration (closes P8a).** APScheduler (the morning-brief cadence) runs enabled scans pre-market (default 7:30 AM ET per Direction Decision 4); results push into the **Opportunities view** alongside Pine alerts (Direction §1). Resolves the result-freshness question (Direction Q1) — when/how often a scheduled scan re-runs. After §4, P8a (Discovery, §1–4) is complete; P8b (§5–7 Range Insight + the range-trading template that picks up P7's `authoring_method="template"`) follows.
