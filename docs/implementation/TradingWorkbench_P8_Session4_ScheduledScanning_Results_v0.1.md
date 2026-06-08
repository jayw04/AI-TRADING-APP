# P8 Session 4 — Scheduled Scanning + Opportunities Integration — Results

| Field | Value |
|---|---|
| Document version | v0.1 (execution results) |
| Date | 2026-06-08 |
| Phase | P8 — Discovery screener + Range Insight (§4 of 7 — **closes P8a**) |
| Plan doc | `TradingWorkbench_P8_Session4_ScheduledScanning_v0_1.md` |
| Predecessor | `p8-session3-discovery-view-complete` (§3) |
| Tag | **`p8-session4-scheduled-scanning-complete`** (moved onto the §4 todo commit) |
| Shipped as | PR **#77** — branch `feat/p8-session4-scheduled-scanning`; squash-merged `d6ee001` |
| Verdict | **GO. P8a (Discovery, §1–4) COMPLETE.** A scheduled scan runs pre-market and its matches surface in Opportunities. Full suite + 3 coverage gates + all 10 invariants green; migration round-trips. |

## What shipped

- **Migration `d3a8e1f6c2b9`** (down-rev `c2f5a8d31e7b`; up→down→up verified) — `scanner_definitions.scheduled` (Boolean, server_default false) + `scanner_runs.trigger` (String(12), server_default "manual"). Constants `TRIGGER_MANUAL`/`TRIGGER_SCHEDULED`.
- **`app/services/scanner/service.py` `run_and_record`** — extracted from the run endpoint: runs the scan, builds + adds the `ScannerRun` (with `trigger`), writes the `SCANNER_RUN` audit (payload includes `trigger`); the caller commits. The on-demand endpoint (`manual`) and the cron (`scheduled`) now share this one path.
- **`app/jobs/scheduled_scans.py` `run_scheduled_scans`** — a 15-min tick: `now_et = now.astimezone(EASTERN)`; skips weekends + a missing bar cache; per user with `scheduled` definitions, parses `discovery_scan_time` (trading_profile `session_preferences_json`, default 7:30; bad input → default), and if due (`now_et >= scan_time`) AND no `trigger='scheduled'` run since today's ET-midnight, runs all the user's scheduled definitions and commits. Per-user failures logged, not fatal. Registered in `lifespan.py` (interval 15 min, after the morning brief, in the alpaca-gated block).
- **Opportunities** — a 7th `discovery_matches` widget: `_fetch_discovery_matches` reads the latest `trigger='scheduled'` `ScannerRun` since today's ET-midnight (joined to the definition name) → items `{symbol, scan_name, definition_id, run_id, values, run_at}` (capped 50). `OppDiscoveryMatchItem`/`OppDiscoveryMatchesWidget` schema + `OpportunitiesResponse` field; frontend `DiscoveryMatchesWidget.tsx` in the grid after Pine alerts + the `types.ts` additions.
- **`scheduled` toggle** — `ScannerDefinitionCreate.scheduled` + response field; create/update set it; a checkbox on the Discovery page editor (state + reset + select + buildInput).

## Decisions settled (owner, 2026-06-07 — AskUserQuestion)

1. **Schedule cron: a 15-min pre-market tick with a configurable time.** A `CronTrigger` registers once at a fixed time, so the per-user `discovery_scan_time` uses the existing completion-cron "tick + check elapsed, skip-if-done-today" pattern — honors Decision 4's configurable time AND survives the server being down at the exact minute. No profile migration (free-form JSON sub-key).
2. **Opportunities: a new `discovery_matches` widget** (not Signal rows — a scan match isn't a strategy "signal"; no `SignalType` overload).
3. **Freshness (Direction Q1): scheduled runs only, today's latest.** On-demand §3 runs stay on the Discovery page.

## Verification

- **26 backend tests** — cron (`tests/jobs/test_scheduled_scans.py`: due→runs+trigger=scheduled+matched; idempotent second pass; not-due-before-time; unscheduled-ignored; weekend-skip; custom 06:00 time makes it due) + Opportunities widget (latest scheduled run today shows; a manual run does NOT surface) + scanner `scheduled` flag (create true/default false).
- **3 frontend tests** — the Discovery scheduled checkbox includes `scheduled:true` in the create payload; `DiscoveryMatchesWidget` renders items + values + empty state.
- Backend full suite **exit 0** (2 known AAPL-fixture skips); ruff + mypy **(199)** clean; migration round-trips; **all 10 shell invariants** + **3 coverage gates** (risk 0.904/P2/P3) green. Frontend vitest **144** (+3, 29 files) + tsc + eslint clean.
- CI on PR #77: **all jobs green first try** (Python backend 5m32s) — no Docker-Hub flake this time. Merged on "merge on green".

## Notes / carry-forward

- **Tick-and-check, not a fixed cron** — the idempotency key is (user, a scheduled run exists today), so one tick runs all of a user's scheduled scans together, once; a server down at 7:30 catches up on the next tick.
- **`run_at >= today-ET-midnight`** is the Opportunities freshness boundary (the ET calendar day), and `trigger='scheduled'` is the filter (manual runs never surface there).
- **No `discovery_scan_time` UI picker** — the time is set via the existing trading-profile PUT (free-form JSON); the Discovery checkbox hint points there. A dedicated picker is a future nicety.
- Live verification (the cron actually reaching `data.alpaca.markets` for fresh bars at 7:30 ET) is **Norton-deferred** to a non-Norton stack; the job + persistence + widget are unit-covered with a fake bar cache.

## P8a is complete

| § | Capability |
|---|---|
| §1 | Alpaca discovery feeds + caching (seed source) |
| §2 | Scanner engine — criteria evaluation (safe AST evaluator + tables + audit) |
| §3 | Discovery view UI (criteria builder + scope + results + watchlist) |
| §4 | Scheduled scanning + Opportunities integration |

A trader authors a deterministic criterion, runs it on demand or schedules it pre-market, and reviews the matches on the Discovery page or in the Opportunities view.

## Next

**P8b — Range Insight + the range-trading template (§5–7).** §5: Range Insight computation (`app/services/range_insight.py` — ATR, typical open→high/low moves, support/resistance, 80% confidence bands, range-bound vs trending classification; **descriptive, not predictive** — Direction Decision 2). §6: the Range Insight panel UI in the Charts right rail. §7: the range-trading strategy template + activation flow — which **picks up P7's reserved `authoring_method="template"`** (Direction Q6, deferred from P7 §8).
