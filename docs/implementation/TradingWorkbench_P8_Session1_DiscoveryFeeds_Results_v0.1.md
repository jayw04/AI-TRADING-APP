# P8 Session 1 — Alpaca Discovery Feeds + Caching — Results

| Field | Value |
|---|---|
| Document version | v0.1 (execution results) |
| Date | 2026-06-07 |
| Phase | P8 — Discovery screener + Range Insight (§1 of 7 — **opens P8a**) |
| Plan doc | `TradingWorkbench_P8_Session1_DiscoveryFeeds_v0_1.md` |
| Predecessor | `p7-session8-polish-complete` (P7 complete) |
| Tag | **`p8-session1-discovery-feeds-complete`** (moved onto the §1 todo commit) |
| Shipped as | PR **#74** — branch `feat/p8-session1-discovery-feeds`; squash-merged `6c4ecc3` |
| Verdict | **GO.** The candidate-symbol seed source is in. Full backend suite + 3 coverage gates + all 10 shell invariants green; no migration, no frontend. |

## What shipped

- **`app/market_data/discovery.py`** — `get_discovery_feeds(top)` → `{most_actives, gainers, losers, last_updated, stale, error}`. Backed by a 5-minute in-process TTL cache keyed by `top` (dict + `asyncio.Lock` double-check + lazy SDK import + `run_in_executor`) — the exact shape `app/market_data/quotes.py` uses. Fetches both Alpaca screener feeds in one pass via `ScreenerClient.get_most_actives` / `get_market_movers` (`raw_data=False` → typed models, narrowed with `cast`). **Stale-on-error:** a live-fetch failure with a warm cache returns the prior payload with `stale=true`; a cold failure returns an empty feed with `error` set to a fixed generic string (`"discovery feeds unavailable"` — never the raw exception). Never raises.
- **`app/api/v1/discovery.py`** — `GET /api/v1/discovery/feeds` (auth-gated via the `get_current_user` stub; `1 ≤ top ≤ 100`), registered after `opportunities.router`.
- **`app/api/v1/schemas/discovery.py`** — `DiscoveryActiveStock` / `DiscoveryMover` / `DiscoveryFeedsResponse`.

## Decisions settled (owner, 2026-06-07 — AskUserQuestion)

1. **Feeds:** most-actives + market-movers only — **no news** (P8 Direction Decision 1 forbids news-*based* scanner criteria; news would only ever be a seed list).
2. **Caching (Direction Q1):** in-memory TTL ~5 min, mirroring `quotes.py`. No table, no migration; resets on restart.
3. **Failure (Direction Q2):** stale-on-error, else empty + flag. The Discovery feed never hard-fails the page (no 5xx).

## Verification

- **New tests (7):** service — fetch+shape, cache-hit-within-TTL (one fetch), stale-on-error (warm cache served, `stale=true`), cold-error (empty + `error`, `stale=false`), distinct-`top`-keys. Endpoint — happy shape, error-passes-through-200.
- Full backend suite **exit 0** (no failures); ruff + mypy **(190 files)** clean; 3 coverage gates (risk branch 0.904 / P2 / P3) pass; all **10 shell invariants** pass (no-LLM, audit-immutability, eval-harness-paper-only, llm-opt-in-bypass-gated, broker/strategy isolation, MCP + workbench-MCP read-only, no-env-credentials, agent-no-DB). **No migration.** No frontend in §1.
- CI on PR #74: all jobs green first try (Python backend 5m21s; all image builds + other Python jobs pass). Merged on owner's "merge on green."

## Notes / carry-forward

- **Live Alpaca remains Norton-blocked locally** — the live screener fetch is exercised only on a non-Norton stack (WSL/CI). The endpoint's structural contract (200 + documented shape, graceful cold-failure) is what's locally verified.
- The error string is deliberately generic; if the UI (§3) wants to distinguish "rate-limited" vs "unauthorized," that classification is a later refinement — §1 keeps the raw exception out of the response on purpose.

## Next

**P8 §2 — Scanner engine (criteria evaluation).** `app/services/scanner.py`: evaluate user-authored boolean criteria (same indicator language as strategies — Direction Decision 6, e.g. `rsi(14) < 35 and atr(14) / close > 0.02`) against the cached bars for the candidate universe seeded by §1. Introduces the `scanner_definitions` (criteria storage) and `scanner_runs` (audited history) tables — the first P8 migration. Open Q1 (result freshness) + Q2 (per-symbol Alpaca failure handling within a scan) resolve at §2 drafting.
