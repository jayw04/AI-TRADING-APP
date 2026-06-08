# Trading Workbench — P8 §4: Scheduled Scanning + Opportunities Integration (closes P8a)

| Field | Value |
|---|---|
| Document version | v0.1 |
| Date | 2026-06-07 |
| Phase | P8 — Discovery screener + Range Insight (§4 of 7 — **closes P8a**) |
| Predecessor | `p8-session3-discovery-view-complete` (§3) |
| Successor | `TradingWorkbench_P8_Session5_*` (Range Insight computation — opens P8b) |
| Direction | `TradingWorkbench_P8_Direction_v0.1.md` (Decision 4; open Q1) |
| Repository | github.com/jayw04/AI-TRADING-APP |
| Scope | A pre-market cron runs each user's scheduled Discovery scans; their matches surface in the Opportunities view alongside Pine alerts. Closes the Discovery half (P8a). |
| Estimated wall time | 3–5 hours |
| Tag on completion | `p8-session4-scheduled-scanning-complete` |
| Out of scope | See §"What this session does NOT do" |

## Why this session exists

§1–3 gave the trader an on-demand screener. §4 makes it *operational*: a saved scan can run **pre-market on its own**, and the matches land in the Opportunities view the trader already checks each morning — "scan overnight, review the candidates through the day." This is the workflow the Direction's end-to-end narrative describes (the 7:30 AM scheduled scan → the Discovery/Opportunities review). It closes P8a (Discovery, §1–4); P8b (§5–7, Range Insight + template) follows.

## What this session ships

1. **Migration** — `scanner_definitions.scheduled` (a scan opts into the cron) + `scanner_runs.trigger` (`manual` | `scheduled`; only scheduled runs feed Opportunities).
2. **`run_and_record`** — extracted from the run endpoint into `app/services/scanner/service.py` so the endpoint (trigger=`manual`) and the cron (trigger=`scheduled`) share one persist+audit path.
3. **`app/jobs/scheduled_scans.py`** — `run_scheduled_scans`: a 15-min tick that runs each user's scheduled scans once their configured `discovery_scan_time` (trading_profile, default 7:30 ET) has passed today; idempotent per (user, date); weekday-only. Registered in `lifespan.py`.
4. **Opportunities** — a 7th `discovery_matches` widget (backend `_fetch_discovery_matches` reads the latest scheduled run today; schema + frontend `DiscoveryMatchesWidget`).
5. **`scheduled` toggle** — the scanner create/update schema + the Discovery page editor (a checkbox).
6. **Tests** — cron (due/not-due/idempotent/weekend/custom-time/unscheduled-ignored), the Opportunities widget (scheduled-only, latest-today), scanner `scheduled` flag, frontend (checkbox → create payload; widget render).

## Prerequisites

- §3 complete (`p8-session3-discovery-view-complete`) — the `/scanner` endpoints + the Discovery page.
- The APScheduler infra (`app/lifespan.py`, gated behind `alpaca_startup_enabled`; timezone America/New_York), the morning-brief job pattern, and `app/utils/time.EASTERN`.
- Migration head `c2f5a8d31e7b` (§2). The §4 migration's `down_revision = "c2f5a8d31e7b"`.

## Decisions settled for §4 (owner, 2026-06-07 — AskUserQuestion)

- **Schedule cron: a 15-min pre-market tick with a configurable time.** A `CronTrigger` registers once at a fixed time, so a per-user configurable time (Decision 4) uses the existing completion-cron "tick + check elapsed, skip-if-done-today" pattern instead. Honors `discovery_scan_time` (trading_profile `session_preferences_json`, default 7:30 ET) **and** survives the server being down at the exact minute. No profile migration (free-form JSON sub-key).
- **Opportunities: a new `discovery_matches` widget.** A scan match isn't a strategy "signal" — a dedicated widget (carrying the scan name + matched values + the definition id) is cleaner than overloading the signals table with a new `SignalType`.
- **Freshness (Direction Q1): scheduled runs only, today's latest.** Only the pre-market scheduled run feeds Opportunities (the most recent scheduled run from today, ET). On-demand §3 runs stay on the Discovery page.

## Detailed work

### §4.1 — Migration + models

```sql
ALTER TABLE scanner_definitions ADD COLUMN scheduled BOOLEAN NOT NULL DEFAULT false;
ALTER TABLE scanner_runs        ADD COLUMN trigger  VARCHAR(12) NOT NULL DEFAULT 'manual';
```
(`batch_alter_table`; `server_default` backfills existing rows.) Model constants: `TRIGGER_MANUAL="manual"`, `TRIGGER_SCHEDULED="scheduled"`.

### §4.2 — `run_and_record` (shared persist path)

`run_and_record(session, *, definition, bar_cache, indicator_computer, discovery_feeds_fn, now, trigger=TRIGGER_MANUAL) -> ScannerRun` — runs the scan, builds + adds the `ScannerRun` (with `trigger`), writes the `SCANNER_RUN` audit (payload includes `trigger`); the caller commits. The run endpoint and the cron both call it.

### §4.3 — `run_scheduled_scans` (the cron)

15-min interval. `now_et = now.astimezone(EASTERN)`; skip weekends + a missing bar cache. For each user with `scheduled` definitions: parse `discovery_scan_time` (default 7:30; bad input → default); if `now_et < due` → not due; if a `trigger='scheduled'` run exists since today's ET-midnight → already ran; else run all the user's scheduled definitions via `run_and_record(trigger='scheduled')` and commit. Per-user failures logged, not fatal. Registered in `lifespan.py` after the morning brief (`add_job(run_scheduled_scans, 'interval', minutes=15, …, kwargs={session_factory, bar_cache, indicator_computer})`).

### §4.4 — Opportunities `discovery_matches` widget

`_fetch_discovery_matches(session, user_id, now)`: the latest `ScannerRun` where `trigger='scheduled'` and `run_at >= today-ET-midnight`, joined to the definition name → items `{symbol, scan_name, definition_id, run_id, values, run_at}` (capped at 50). Added to `OpportunitiesResponse`. Frontend: `OppDiscoveryMatchItem` type + `DiscoveryMatchesWidget.tsx` in the grid after Pine alerts.

### §4.5 — `scheduled` toggle

`ScannerDefinitionCreate.scheduled: bool = False` + response field; create/update set it. Discovery page: a checkbox ("Run automatically pre-market … matches appear in Opportunities").

## Manual smoke

1. Discovery → create a scan, tick "Run automatically pre-market", save.
2. With the dev stack up (alpaca enabled so the scheduler runs; Norton blocks live Alpaca, so use cached fixtures), set `discovery_scan_time` in the past and wait for the 15-min tick (or call `run_scheduled_scans` directly) → a `trigger='scheduled'` `ScannerRun` is created once.
3. Open Opportunities → the **Discovery matches** widget shows the matched symbols.
4. Re-run the tick → no second run today (idempotent).

## Walk-away discipline

A new cron + a migration, but no order-path / risk / live touch → **≥1 hour**.

## What this session does NOT do

- **No Range Insight** — that's P8b (§5–7).
- **No per-definition schedule times** — one per-user pre-market time (trading_profile); each scan is on/off.
- **No `discovery_scan_time` UI picker** — the time is set via the existing trading-profile PUT (free-form JSON); the Discovery page links there. A dedicated picker is a future nicety.
- **No on-demand runs in Opportunities** — only scheduled runs surface (Direction Q1).
- **No new audit action** — scheduled runs reuse `SCANNER_RUN` (with `trigger` in the payload).
- **No new CI invariant; no order-path / risk change; no LLM.**

## Notes & gotchas

1. **Tick-and-check, not a fixed cron** — a single `CronTrigger` can't honor a per-user configurable time, and a fixed-time cron misses the day if the server is down then. The 15-min tick + "skip if a scheduled run exists today" mirrors the activation/promotion completion crons and the morning brief.
2. **`run_at >= today-ET-midnight`, not a rolling window** — the freshness boundary is the ET calendar day, matching "the pre-market scan for today."
3. **`trigger` is the Opportunities filter** — manual (on-demand) runs never surface there; only `scheduled`.
4. **Idempotency keys on (user, scheduled-run-exists-today)** — not per-definition, so one tick runs all of a user's scheduled scans together, once.
5. **Bar cache absent → the cron no-ops** (logged) rather than erroring — same defensive posture as the run endpoint's 503.
