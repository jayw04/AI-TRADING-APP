# GAP-NATIVE-001 §1 — Box-Native Premarket Gapper Screener

| Field | Value |
|---|---|
| Document version | v0.2 (incorporates the owner review `Docs/implementation/comments.md`, 2026-07-10, 9.1/10 — probe + source-segmentation made hard gates) |
| Date | 2026-07-10 |
| Phase | Ops / AWS independence (post-ADR 0032 cutover hardening) |
| Session | §1 of 1 (single-session program) |
| Predecessor | ADR 0032 AWS cutover (2026-06-30/07-02); SCAN-001 gate activation (PR #272) |
| Successor | none planned — optional §2 (catalyst enrichment) only if the owner asks |
| Repository | github.com/jayw04/AI-TRADING-APP |
| Scope | Produce the daily `premarket_gappers_<date>.json` **on the AWS box** from Alpaca data, making the box the authoritative source for the SCAN-001 gate and the Opportunities panel; the laptop TradingView/Yahoo scanner is demoted to optional display enrichment. |
| Estimated wall time | 5–8 hours (incl. probe, tests, ADR, deploy; +1 trading morning for live verification) |
| Tag on completion | `gap-native-001-complete` |
| Out of scope | See §"What this session does NOT do" |

---

## Why this session exists

Owner directive (2026-07-10): **the AWS box is the home of the application and must not rely on the laptop for any operational input** — the PC is shut down from time to time. The 2026-07-10 pipeline audit found exactly one remaining workbench→laptop dependency: the premarket gappers file. It is produced on the PC (`claude-trading-view/premarket_gappers.sh`, ~07:30 CT, Yahoo gainers table + Benzinga/LLM catalysts) and scp'd to `/opt/workbench/claude-trading-view/` at ~08:00 CT by the "Sync Premarket Gappers to AWS" scheduled task. If the PC is off, the box's 09:25 ET SCAN-001 gate scan falls back to the newest *older* file with `stale: true` — fail-soft, but that trading day's gate evidence is degraded, and SCAN-001 is in the middle of its ~40-day forward-evidence accrual.

This session moves production of that file onto the box, sourced from Alpaca (an already-approved external dependency — no new-dependency ADR needed). After it ships, every workbench daily-operations input is produced on AWS: factor refresh (06:00 ET timer), insider monitor (EDGAR, 08:05/18:05 ET), range auto-select (Alpaca bars, 09:00 ET), and now gappers (Alpaca screener, 09:05 ET). The remaining laptop tasks ("Insider Conviction Scan", "Stack Heartbeat") belong to the sibling project and do not feed the workbench.

## What this session ships

1. `app/services/native_gapper_screener.py` — the screener: Alpaca movers/snapshot discovery → laptop-parity filters → top-10 → writes `premarket_gappers_<date>.json` (same schema, `catalyst: null`, plus a `source` field).
2. `app/jobs/native_gapper_scan.py` + lifespan wiring — 09:05 ET mon–fri primary run, 09:18 ET idempotent retry, behind `WORKBENCH_NATIVE_GAPPER_SCREENER_ENABLED` (default off).
3. Reader precedence in `app/services/premarket_gappers.py` — for today's date the **native file is authoritative**; a same-date external (laptop) file only contributes catalyst/headlines per symbol; external-only is the fallback. Payload gains `source`.
4. Evidence provenance — the SCAN-001 gate record gains `gappers_source` so the accrual can be segmented by input source (additive to `scan_001_premarket_gate/v1`).
5. ADR 0041 — "Box-authoritative operational data; box-native gapper screener" (records the owner directive and the SCAN-001 input-provenance change).
6. Data Source Registry entry (next free DCAP id) for the Alpaca screener/snapshot source.
7. Tests — screener unit tests (fake clients), reader precedence tests, job idempotence, panel-compat test.
8. `scripts/probe_native_gappers.py` — the §1.0 pre-flight probe (also the permanent troubleshooting tool).

## Prerequisites

- SCAN-001 gate active on the box (PR #272) — `data/premarket_gate_evidence/` accruing daily records. ✅ verified 2026-07-10.
- Alpaca credentials load inside the backend container via `app.brokers.alpaca.credentials.load_credentials()` (the pattern `benchmark_snapshot.py` uses). ✅ in production.
- `alpaca-py>=0.30.0` pinned (`apps/backend/pyproject.toml:23`) — ships `ScreenerClient` / `MarketMoversRequest` / snapshot requests. ✅.
- Factor store present on the box and refreshed weekdays 06:00 ET (`workbench-factor-refresh.timer`) — used only by the *fallback* discovery sweep. ✅.

## Open question to resolve before coding past §1.2 (gated on the §1.0 probe)

**Q1 — Does the Alpaca movers endpoint reflect premarket trading under our data entitlement (IEX feed, paper account)?** The movers screener ranks by percent change from previous close to latest trade. If, at ~09:00 ET, it returns (a) a live premarket-gap ranking → movers is the primary discovery source; (b) yesterday's close-to-close ranking or empty → discovery falls back to the snapshot sweep over the factor-store universe (§1.2, path B). The probe decides; the service is designed so either path feeds the same filter/rank/write stages.

---

## Detailed work

### §1.0 Pre-flight probe — `scripts/probe_native_gappers.py`

A standalone, read-only script (no app imports beyond the credentials loader) run **on the box between 08:45 and 09:15 ET** on a trading day, before the rest of the session is coded past the service skeleton:

```
uv run python scripts/probe_native_gappers.py            # inside the backend container
```

It must print, as JSON:

- `movers`: top-20 gainers from `ScreenerClient.get_market_movers(MarketMoversRequest(top=20))` — symbol, percent_change, price — plus the raw `last_updated` timestamp the endpoint reports.
- `snapshots_probe`: for the top-5 movers symbols and 5 known liquid names (AAPL, TSLA, NVDA, SPY, AMD): `latest_trade` (price, timestamp), `prev_daily_bar.close`, `daily_bar.volume` from `StockHistoricalDataClient.get_stock_snapshot(..., feed=IEX)`.
- `verdict` hints: whether movers' `last_updated` is this morning (premarket-live) and whether `daily_bar.volume` is non-zero pre-open (premarket volume visible on IEX).

Decision matrix (record the outcome in this doc's Notes before proceeding):

| Probe outcome | Discovery path |
|---|---|
| Movers premarket-live | **Path A (primary):** movers top-50 → snapshot verification for those symbols |
| Movers stale/empty pre-open | **Path B:** snapshot sweep over the factor-store dollar-volume universe (batched), movers dropped |
| Snapshots show zero premarket volume broadly | Stop — escalate to owner; IEX entitlement is insufficient and the honest options are a SIP subscription or accepting open-price gap detection at 09:31 (a different design) |

**The probe is a HARD GATE (owner review 2026-07-10 §1).** The screener is not enabled in
production until the in-window probe confirms all four of:

1. `latest_trade` timestamps are current premarket prints,
2. `prev_daily_bar.close` is usable as the prior close,
3. premarket volume is visible (or an acceptable substitute is defined) — if it is not
   visible, **do not fake it**; escalate to the owner,
4. the path completes comfortably before the 09:25 ET SCAN gate consumes the file.

The probe also records elapsed time per call so path timing (incl. a batched path-B sweep)
is measured, not assumed.

### §1.1 Settings (`app/config.py`)

```python
# --- Box-native premarket gapper screener (GAP-NATIVE-001, ADR 0041) ---
# Output directory for box-produced premarket_gappers_<date>.json files. Lives
# under data/ so the existing volume persists it; the external (laptop) dir
# stays a separate read-only mount and is enrichment-only (ADR 0041).
native_gappers_dir: str = "data/premarket_gappers_native"
```

The enable switch is an env var read in lifespan (NOT a settings field), mirroring `WORKBENCH_INSIDER_MONITOR_ENABLED` exactly — CI and test boots stay hermetic, no Alpaca calls:

```python
if os.environ.get("WORKBENCH_NATIVE_GAPPER_SCREENER_ENABLED", "").lower() in ("1", "true"):
```

### §1.2 The screener — `app/services/native_gapper_screener.py`

Module constants mirror the laptop scanner's filters (`claude-trading-view/premarket_gappers.sh:40-42`) so the two sources rank the same market the same way — parity is what lets the gate's accrual survive the source change:

```python
MIN_GAP_PCT = 5.0        # strictly greater, matching the sh scanner
MIN_PRICE = 3.0
MIN_PREMARKET_VOL = 50_000
TOP_N = 10
SOURCE = "box_native_alpaca_v1"
```

Public surface (sync Alpaca SDK calls run via `loop.run_in_executor`, the `benchmark_snapshot.py` pattern):

```python
async def scan_native_gappers(*, now: datetime | None = None) -> dict[str, Any]:
    """Discover → verify → filter → rank → payload dict. Read-only, fail-soft:
    any Alpaca error returns {"ok": False, "reason": ...}; never raises."""

def write_gappers_file(payload: dict[str, Any], directory: str) -> str:
    """Atomically write premarket_gappers_<date>.json (tmp + os.replace)."""
```

Two-stage pipeline inside `scan_native_gappers`:

1. **Discovery** — Path A: `ScreenerClient.get_market_movers(MarketMoversRequest(top=50))`, gainers only. Path B (fallback, and the automatic degrade if A returns nothing): factor-store `dollar_volume_universe(latest_sep_date, 1000)` swept via batched `get_stock_snapshot` (batches of 200 symbols). Path B is honest-scope-limited — the store is small-cap-sparse, and gappers are often small caps — which is why A is preferred when live.
2. **Verification/features** — one `get_stock_snapshot` call for the discovered symbols (feed=IEX): `gap_pct = (latest_trade.price − prev_daily_bar.close) / prev_daily_bar.close × 100`, `premarket_volume = daily_bar.volume` (today's accumulating bar, pre-open = premarket volume), `price = latest_trade.price`. Names whose latest trade is older than the prior close's session (no premarket print) are dropped — a gap needs a live premarket price.

Output payload — **byte-compatible with the laptop schema** (the consumers `premarket_adapter.premarket_panel` and the Opportunities panel need exactly `symbol/price/gap_pct/premarket_volume`; `catalyst: null` + `headlines: []` is already a valid row — see UCTT in `premarket_gappers_2026-07-09.json`):

```json
{
  "scanned_at": "2026-07-13T13:05:02Z",
  "source": "box_native_alpaca_v1",
  "gappers": [
    {"rank": 1, "symbol": "XYZ", "price": 12.34, "gap_pct": 18.2,
     "premarket_volume": 2400000, "catalyst": null, "headlines": []}
  ]
}
```

Boundary notes (module docstring, mirroring `premarket_gappers.py`'s): read-only market data; no LLM import; never touches the OrderRouter; advisory only. The module is a *service* invoked by a job — nothing in the order path imports it.

### §1.3 The job — `app/jobs/native_gapper_scan.py` + lifespan wiring

```python
async def run_native_gapper_scan(*, force: bool = False) -> dict[str, Any]:
    """Scheduled entry point. Skips weekends; skips if today's native file already
    exists (idempotent — makes the 09:18 retry a no-op after a good 09:05 run);
    scan → write → structured log. Fail-soft: never raises into the scheduler."""
```

Lifespan (inside the existing `settings.scheduler_enabled` block, gated by the env flag, two cron ids on the insider-monitor pattern):

```python
for _ng_id, _ng_hour, _ng_min in (
    ("native_gapper_scan", 9, 5),
    ("native_gapper_scan_retry", 9, 18),
):
    scheduler.scheduler.add_job(
        run_native_gapper_scan,
        _ReplayCron(day_of_week="mon-fri", hour=_ng_hour, minute=_ng_min,
                    timezone="America/New_York"),
        id=_ng_id, max_instances=1, coalesce=True, replace_existing=True,
    )
logger.info("native_gapper_scan_scheduled")
```

Timing rationale — 09:05, not earlier or later:

- Earlier (e.g. 08:30, the laptop's slot) forfeits 35 minutes of premarket volume accumulation, and `MIN_PREMARKET_VOL` on thin IEX prints would over-filter.
- Later than ~09:18 leaves no retry room before the 09:25 gate scan consumes the file.
- 09:05 + a 09:18 idempotent retry gives two shots at Alpaca flakiness with the file still landing ≥7 minutes before the consumer.

Structured log events: `native_gapper_scan_complete` (with `count`, `discovery_path`, `elapsed_s`), `native_gapper_scan_skipped_exists`, `native_gapper_scan_failed` (with `reason`).

### §1.4 Reader precedence — `app/services/premarket_gappers.py`

`read_latest_gappers()` keeps its signature and payload shape (`{date, scanned_at, count, gappers, stale}` + new `source`) so all consumers are untouched. New resolution order, per the owner directive (box-authoritative):

1. **Native file for today's NY date exists** → it is the operational payload. If the external dir also has today's file, join `catalyst`/`headlines` onto matching symbols (display enrichment only — symbols, prices, and ranking come from the native file).
2. **No native file today, external file today exists** → use the external file (transition safety: if the native job fails and the PC happens to be on, the day is not lost).
3. **Neither** → newest file from either dir, `stale: true` (existing behavior).

The rationale for native-wins (not external-wins): the directive is that AWS must not *rely* on the PC. If external-wins, the operational input silently changes provenance depending on whether the PC was on — the gate evidence would mix sources uncontrollably. Native-wins makes provenance deterministic: `box_native_alpaca_v1` every day the box is healthy, and the external file's only surviving role is cosmetic (catalyst text on the Opportunities page).

Implementation detail: extract the current glob/parse logic into a `_read_dir(directory)` helper used for both dirs; `source` is `"box_native_alpaca_v1"`, `"external_scanner"`, or the file's own `source` field when present.

### §1.5 Evidence provenance — `app/services/premarket_scan.py`

`run_premarket_scan` passes through the payload's `source` as `gappers_source` in the report dict; the gate job persists it in the daily evidence record. Additive field — the `schema` string stays `scan_001_premarket_gate/v1` (readers of these records are our own scripts; an added key breaks nothing), but the change is noted in ADR 0041 so the eventual SCAN-001 verdict analysis **segments the accrual by `gappers_source`** rather than treating Yahoo-sourced and Alpaca-sourced days as one population (Evidence Principles: never silently mix universes).

### §1.6 ADR 0041 — `Docs/adr/0041-box-native-gapper-screener.md`

Short ADR (accepted-on-merge) recording:

- The owner directive (2026-07-10): operational data the box relies on must be produced on the box; sibling-app/laptop producers are enrichment-only.
- The decision: box-native Alpaca screener is the authoritative gappers source; reader precedence native > external; laptop sync retained but demoted.
- The SCAN-001 consequence: input provenance changes mid-accrual; `gappers_source` added to evidence records; verdict analysis must segment by source.
- The honest-scope deltas vs. the Yahoo scanner: IEX premarket coverage is thinner than the consolidated tape (fewer/laggier small-cap prints); no catalyst attribution; movers-vs-sweep discovery per the §1.0 probe outcome.
- Registry: the Alpaca screener/snapshot source gets the next free DCAP id in the Data Source Registry.

### §1.7 Tests

| File | Pins |
|---|---|
| `tests/services/test_native_gapper_screener.py` | filter parity (gap/price/vol strict-greater), top-N ranking, gap_pct math vs. fake snapshots, path-A→B degrade when movers empty, stale-print drop, atomic write + schema round-trip through `read_latest_gappers` |
| `tests/services/test_premarket_gappers_precedence.py` | native-wins-today, catalyst join by symbol, external fallback, neither→stale, `source` field values |
| `tests/jobs/test_native_gapper_scan.py` | weekend skip, exists→skip (idempotent retry), fail-soft on screener error (no raise), structured events |
| `tests/services/test_premarket_scan.py` (extend) | `gappers_source` passthrough into the report |

All Alpaca clients faked (tiny stub classes, the repo's established pattern) — no network in tests; the lifespan flag keeps CI boots from registering the job at all.

### §1.8 Deploy & transition (on the box, per the `aws_migration_phase1` deploy recipe)

1. Merge PR; deploy to the box **outside RTH and ≥60 min from any scheduled rebalance** (owner rule).
2. Add `WORKBENCH_NATIVE_GAPPER_SCREENER_ENABLED=1` to the prod compose override; recreate the backend.
3. Confirm boot events: `native_gapper_scan_scheduled` alongside the existing `premarket_*_scheduled` lines.
4. Next trading morning, verify per the Manual smoke below.
5. **Transition period (~2 weeks): leave the laptop scan + sync tasks running.** This is the
   only window where source parity is directly observable. Run
   `scripts/compare_gappers_sources.py` (in-container) on days both files exist; it reports the
   explicit parity metrics from the owner review (§3): daily native count, daily external
   count, symbol overlap % of the external list, top-10 rank overlap, mean gap_pct and
   premarket-volume deltas on overlapping symbols, and which of the gate record's candidates
   each source contained. Record findings in this doc's Notes.
6. **Source-segmentation hard rule (owner review §2):** during the transition, accrual is
   reported both overall and by `gappers_source`. No SCAN-001/GAPPER-001 verdict may pool
   `external_scanner` and `box_native_alpaca_v1` days unless the comparison shows acceptable
   parity; if overlap is consistently low, the sources are different candidate populations and
   the native source starts a **new evidence tranche**. (Alpaca/IEX may miss small-cap prints
   the Yahoo table captured — if candidate quality changes, mixed-source validation becomes
   uninterpretable.)
7. After the window: laptop tasks stay enabled *only* for catalyst enrichment at the owner's option; nothing operational references them. (Do NOT touch "Stack Heartbeat" — protected, sibling project.)
8. Follow-up (not this session, owner review §7): a small Opportunities-page source badge —
   `Box Native / External / Stale`.

---

## Manual smoke

Plumbing smoke — runnable any time, on the box:

```bash
# 1. probe (read-only; off-hours it shows last-session data — that's expected)
sudo docker exec workbench-backend uv run python scripts/probe_native_gappers.py

# 2. force one scan cycle end-to-end (bypasses the exists-skip, writes the file)
sudo docker exec workbench-backend python3 -c "
import asyncio
from app.jobs.native_gapper_scan import run_native_gapper_scan
print(asyncio.run(run_native_gapper_scan(force=True)))"

# 3. the reader resolves it, native-wins, shape intact
sudo docker exec workbench-backend python3 -c "
from app.services.premarket_gappers import read_latest_gappers
p = read_latest_gappers(); print(p['date'], p['source'], p['count'], p['stale'])"
```

Load-bearing assertion — next trading morning (the real verification):

- 09:05–09:06 ET: `native_gapper_scan_complete` in the backend log; `data/premarket_gappers_native/premarket_gappers_<today>.json` exists with 1–10 rows.
- 09:25 ET: the day's `premarket_scan_<today>.json` gate record shows `"stale": false` and `"gappers_source": "box_native_alpaca_v1"` — **with the laptop's sync task deliberately not yet run or the file removed for the rehearsal**, proving the box produced its own input.

## Walk-away discipline

Routine session: **≥1 hour** between ready-for-review and merge. No order path, no risk engine, no audit subsystem is touched; the highest-consequence change is reader precedence for an advisory data feed.

## What this session does NOT do

- **No catalyst/headline generation on the box** — that needs Yahoo/Benzinga scraping + LLM summarization (new external surface + cost). `catalyst: null` is valid today; enrichment stays the laptop file's optional job. A box-side §2 would be its own scoped session.
- **No SIP data subscription** — IEX limitations are documented as honest scope, not silently papered over. Escalate to the owner only if the §1.0 probe shows IEX is unusable.
- **No change to the gate methodology** — thresholds, the Candidate Engine, the funnel, and the 40-day accrual design are untouched; only input provenance changes, and it is labeled.
- **No Opportunities UI changes** — the panel already renders null-catalyst rows; a "source" badge is a nice-to-have for later.
- **No decommissioning of laptop tasks** — the scan/sync schtasks stay through the transition window; "Stack Heartbeat" and "Insider Conviction Scan" are sibling-project assets and are out of bounds entirely.
- **No narrowing of the `../claude-trading-view:ro` mount** — the compose hardening follow-up (exporting to a dedicated subdir) is pre-existing and separate.
- **No generalization to other sibling data** — the 2026-07-10 audit found gappers to be the *only* workbench operational input from the laptop; if another appears later, ADR 0041's rule covers the decision, not this session's code.

## Notes & gotchas

0a. **2026-07-10 probe smoke (out-of-window, 09:50 ET — plumbing validation only):** movers
    endpoint live (`last_updated` current, 20 gainers), IEX snapshots working, **SIP not
    entitled** (403 on recent SIP), and one decisive catch — illiquid names can return
    months-old `latest_trade` prints (QSEAR: March), so the screener's current-print drop is
    load-bearing. Raw movers output includes warrants/units and sub-$1 names; the plain-symbol
    + price filters handle them. The in-window premarket questions (probe hard-gate items 1
    and 3) remain for the Mon 2026-07-13 08:50 ET run (`workbench-gapper-probe-0713.timer`).
0b. **Implementation sequencing note:** the service/job/reader/tests were implemented on
    2026-07-10 *ahead of* the in-window probe (review §1 asks skeleton-only until the probe).
    Mitigation: the code is default-off and the PR does not merge — and the flag is not
    enabled — until the Monday probe passes the four hard-gate checks; the A→B degrade means
    both probe outcomes are already coded. If the probe hits the stop-and-escalate row, the
    PR is amended or parked, not merged.
0c. **Owner review folded in (comments.md, 9.1/10):** funnel diagnostics in the morning log
    (§5), scan-status taxonomy `scan_failed` / `scan_success_zero_candidates` /
    `scan_success_non_empty` with failed-runs-write-nothing (§6), hard source-segmentation +
    new-tranche rule (§2, ADR 0041 Decision 4), explicit parity metrics + comparison script
    (§3), path-B sweep diagnostics via the funnel counts (§4), daily-report
    `native_gapper_scan_missing_today` alert, `source` required in every native file,
    same-directory atomic tmp+replace, malformed-native-file fallback test.

1. **Probe before building past the skeleton.** Q1 (movers premarket behavior on IEX entitlement) genuinely forks the discovery implementation. Coding path A without the probe risks a rewrite.
2. **Laptop `date` gotcha does not apply here** — the job runs in the container on America/New_York APScheduler time; but remember the box host clock is ET while the container is UTC: compute "today" via the existing `EASTERN` helper, never `date.today()`.
3. **Atomic writes matter**: the 09:25 consumer globs the directory; a half-written JSON at 09:25 must be impossible (`tmp` + `os.replace`, same as other evidence writers).
4. **Movers `top` caps at 50** in the Alpaca API — that's the discovery ceiling for path A; fine, since the laptop scanner's Yahoo table is a similar-order list.
5. **Split/dividend day caveat**: `prev_daily_bar.close` is unadjusted vs. the morning's prints in the same way Yahoo's table is — a split can fake a gap. The laptop scanner has the same exposure; the store-coverage + $10/$20M gates downstream have absorbed this so far. Note it; don't solve it here.
6. **`read_latest_gappers` is also called by the Opportunities aggregator per request** — keep the two-dir resolution cheap (two globs, no I/O beyond the chosen files).
7. When adding the DCAP registry entry, take the **next free id** from the registry file — don't hardcode from memory (DCAP-007 was Quiver; others may have landed since).
