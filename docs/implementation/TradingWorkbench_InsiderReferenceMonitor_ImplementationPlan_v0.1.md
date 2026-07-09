# Insider Reference Monitor — Implementation Plan

| Field | Value |
|---|---|
| Document version | v0.1 (draft for owner review — do not build against this version) |
| Date | 2026-07-09 |
| Phase | Capability onboarding (product surface) — not a research program session |
| Predecessor | `TradingWorkbench_InsiderReferenceMonitor_Onboarding_v0.1.md` (spec, PR #400) + INSIDER-001 §1 infra (PR #279, on main) |
| Successor | INSIDER-002 pre-registration (only after the GAPPER-001 verdict; triage sheet is Reserved) |
| Repository | github.com/jayw04/AI-TRADING-APP |
| Scope | Ship the "Insider Activity Monitor": daily EDGAR Form 4 ingestion over a configurable universe into the existing PIT Event Store, a read-only enriched reference endpoint, and a UI surface with the locked reference-only language. Owned by **user 3** (identity/scoping only — account 3 never trades). |
| Estimated wall time | 6–9 hours across 2 PRs (backend 4–6h, frontend+deploy 2–3h) |
| Tag on completion | `insider-reference-monitor-v1` |
| Out of scope | See §7 — notably: no paper book, no scoring/ranking, no INSIDER-002 study, no sibling swing-book port |

---

## 0. Open questions to resolve before v1.0 (owner review)

**OQ1 — the user-3 role.** "We can use user 3 account for this" is implemented here as: **user 3
(`momentum-conservative@globalcomplyai.com`, freed by the ADR-0036 consolidation) becomes the
owning identity for the monitor** — the job writes global data, but the UI surface and any
per-user scoping hang off user 3, the same way user 2 owns the range surfaces. Account 3
(`Alpaca Paper (Conservative)`, fresh $100k) **stays flat forever under this feature: the monitor
places no orders, and the `rejected_reference_only` invariant prohibits it structurally.**
⚠ If you instead intended a *paper observation book that trades on insider events* — that is the
already-rejected INSIDER-001 hypothesis and would violate the reference-only invariant; it is not
buildable without an approved INSIDER-002 pre-registration. Per CLAUDE.md, flagging rather than
assuming: **confirm identity/scoping-only is the intent.** (Also: user 3's display name/email still
say "momentum-conservative" — OQ1b: rename the user label to "Insider Monitor" or leave as-is?)

**OQ2 — monitor universe size.** EDGAR ingestion is per-CIK polling (SEC fair-access: ~10 req/s,
declared User-Agent). Options:

| Option | Universe | Daily cost | Recommendation |
|---|---|---|---|
| A | Sibling's 134 names | trivial | too small — wastes our data advantage |
| B (**recommended v1**) | Factor-store PIT small/mid-cap slice, capped at **~1,500 CIKs**, refreshed weekly from `dollar_volume_universe` | ~3–5 min/day sharded | 10× the sibling with headroom under fair-access |
| C | Full DCAP-008 pool (9,040) | ~15–20 min/day, needs sharding across hours | v2 — do it via EDGAR **daily full-index** files instead of per-CIK polling (a different ingest path; deferred) |

**OQ3 — UI placement.** Recommended: a **dedicated card on the Dashboard** (visible to all users;
it is context, not a per-book widget) + the required language block. Alternative: its own page
under Research/Discovery. Card-first is less code and matches the "Performance vs Benchmarks"
card pattern from `feat/dashboard-benchmarks`.

---

## 1. Why this session exists

INSIDER-001 left the platform with a validated, reusable event-driven stack (native EDGAR
ingestion, PIT Event Store, Security Master) and a rejected trading hypothesis. The sibling app
proves the *monitoring workflow* has standalone product value — but it watches only 134 names with
none of our context data. This session turns the owned infrastructure into a user-visible,
honestly-labelled daily insider-activity surface (owner decision 2026-07-09), delivering product
value now while INSIDER-002 stays gated behind the GAPPER-001 verdict.

## 2. What this session ships

1. `app/altdata/insider_monitor.py` — universe resolution + read-time enrichment (pure functions).
2. `app/jobs/insider_reference_monitor.py` — daily ingest job (18:05 ET) + premarket catch-up (08:05 ET), registered in `lifespan.py` behind a config flag.
3. `GET /api/v1/insider-reference` — read-only, auth'd, enriched, every row carrying `reference_only: true` + the evidence note.
4. Frontend "Insider Activity Monitor" Dashboard card with the locked language block.
5. Tests: job idempotency, endpoint shape, the reference-only flag assertion, enrichment fallbacks.
6. CI-invariant allowlist entry (`check_reference_only_invariant.sh`) for the new display-side modules + registry/runbook doc updates.
7. Box deploy + first live ingest + end-to-end smoke.

## 3. Prerequisites

- INSIDER-001 §1 infra on main (`app/altdata/sec/{client,form4,cik_map,ingest}.py`, `app/altdata/events/store.py`) — **verified present 2026-07-09**.
- `rejected_reference_only` guard + 15th CI invariant on main — **verified** (`insider_buy → INSIDER-001` mapped).
- Factor store live on the box with `tickers`/`metrics` (marketcap) and SEP (ADV) — **verified** (daily refresh green).
- Owner sign-off on OQ1–OQ3 → this doc frozen at v1.0.

## 4. Detailed work

### §4.1 Universe + enrichment module — `app/altdata/insider_monitor.py`

```python
MONITOR_EVENT_TYPE = "insider_buy"          # already in REFERENCE_ONLY_PROGRAMS
INSIDER_MONITOR_USER_ID = 3                 # owning identity (OQ1) — scoping only, never orders

def resolve_monitor_universe(store: FactorDataStore, *, cap: int = 1500) -> list[str]:
    """Small/mid-cap monitor universe from the PIT factor store (OQ2 option B):
    dollar_volume_universe(as_of=today) filtered to small/mid marketcap deciles, capped.
    Falls back to the sibling's 134-name list (vendored constant) if the store is unreadable
    — the monitor degrades, never breaks."""

@dataclass(frozen=True)
class InsiderReferenceRow:
    ticker: str; company: str; insider_name: str; insider_role: str      # officer/director/10%-owner
    transaction_type: str                                                # "P" only in v1
    transaction_date: date; filing_date: date; filed_at: datetime        # PIT anchor
    transaction_value: Decimal | None
    open_market: bool
    cluster_count: int                       # distinct insiders, same ticker, trailing 14d
    pct_of_marketcap: float | None           # enrichment; None when metrics missing
    pct_of_adv: float | None                 # value / 20d avg dollar volume
    sector: str | None; size_bucket: str | None
    freshness_hours: float                   # now - filed_at
    reference_only: bool = True              # ALWAYS True; test-pinned

def recent_reference_rows(events_store, factor_store, *, window_days: int = 14) -> list[InsiderReferenceRow]:
    """Read-through: corporate_events(insider_buy, filed_at >= now-window) → enrich → sort by
    filed_at DESC (freshness ONLY — no score, no ranking; spec §'What not to build')."""
```

Design notes: enrichment is computed **at read time**, never persisted as a score column — there
is deliberately no place a "conviction score" could accrete. Cluster count is a window `COUNT
(DISTINCT insider)` over the Event Store, not a stored aggregate. `pct_of_*` are display context
with `None` fallbacks (an event on a name outside the factor store still displays).

### §4.2 Daily job — `app/jobs/insider_reference_monitor.py`

```python
async def run_insider_reference_ingest() -> None:
    """18:05 ET weekdays (+ 08:05 ET catch-up): resolve universe → app.altdata.sec.ingest over
    it (since=last 3 calendar days, idempotent by accession) → upsert_events into the PIT store
    → log {universe, fetched, new_events, elapsed}. Best-effort; failures log + surface in the
    daily report, never raise into the scheduler."""
```

- Registered in `lifespan.py` next to the gapper jobs, behind `WORKBENCH_INSIDER_MONITOR_ENABLED`
  (**default OFF** — conservative-defaults convention; flipped ON via the box `.env` at deploy).
- Cron: `5 18 * * mon-fri` + `5 8 * * mon-fri`, ET (engine schedules are ET per #366; these are
  APScheduler jobs registered with the ET-pinned trigger like the gapper jobs).
- SEC fair-access: reuse the existing client's User-Agent + throttle; shard the universe so no
  burst exceeds ~8 req/s.
- The 3-day `since` overlap re-covers weekend/late filings; accession-keyed upsert makes it a
  no-op on already-seen filings.

### §4.3 Endpoint — `app/api/v1/insider_reference.py`

```
GET /api/v1/insider-reference?window_days=14&min_value=10000
→ 200 {
    "reference_only": true,
    "evidence_note": "Reference Only — INSIDER-001 found no standalone residual alpha. Not a
                      validated trading signal. Not used for ranking, sizing, or orders.",
    "evidence_doc": "docs/implementation/evidence/insider_001_s4_reproduction/",
    "as_of": "...", "universe_size": 1500, "count": N,
    "rows": [ InsiderReferenceRow... ]   # sorted by filed_at DESC only
  }
```

- Auth'd like every v1 endpoint; readable by ALL users (context surface), owned/operated under
  user 3. `min_value` is a display-hygiene filter (default $10k), not ranking.
- **Test-pinned:** every row and the envelope carry `reference_only: true`; a test asserts the
  endpoint module imports nothing from `app/risk`, `app/orders`, or strategy selection modules.

### §4.4 Reference-only enforcement (spec step 4)

- Add the three new modules to `check_reference_only_invariant.sh`'s **display-side allowlist**
  (they legitimately name `insider_buy`); the order-path/ranking module scan stays untouched.
- New test `tests/altdata/test_insider_monitor_reference_only.py`: (a) rows always flagged,
  (b) module-import isolation, (c) `REFERENCE_ONLY_PROGRAMS["insider_buy"]` still maps to a
  `rejected` program (drift guard with `programs.py`).

### §4.5 Frontend — Dashboard card `InsiderActivityMonitor.tsx`

- Table: ticker · company · role · value (+ `pct_of_marketcap` / `pct_of_adv` as secondary text) ·
  cluster badge (≥2) · transaction date → filing date (freshness) · sector/size tag.
- The locked language block renders **above the table, always visible** (not a tooltip), with the
  INSIDER-001 evidence link. Header: "Insider Activity Monitor — Reference Only".
- No row click-through to order tickets or strategy pages; ticker links to the chart page only.
- Empty state: "No qualifying open-market insider buys in the last 14 days" (sparse is normal —
  the sibling often has 0/day).

### §4.6 Docs

- Registry: add the monitor as a **platform capability** row (CAP-026, "Insider Reference
  Monitor — reference-only context surface"), NOT a program row; cross-link the triage sheet.
- Runbook: job failure modes (EDGAR 403/throttle, factor-store missing → fallback universe),
  where logs land, how to re-run a day by hand.
- `Docs/Strategies/Insider Strategy.md` gains a header note: monitoring workflow onboarded to the
  platform (reference-only); swing book remains sibling-only.

## 5. Manual smoke (box, post-deploy)

```bash
# 1. flag on + backend rebuilt; job registered:
sudo docker logs workbench-backend 2>&1 | grep insider_reference   # → ..._scheduled
# 2. force one ingest (in-container, same entrypoint the job uses):
sudo docker exec workbench-backend python -c "import asyncio; \
  from app.jobs.insider_reference_monitor import run_insider_reference_ingest; \
  asyncio.run(run_insider_reference_ingest())"
# 3. endpoint (as any user):
curl -s -b cookies 'localhost:8000/api/v1/insider-reference?window_days=14' | python3 -m json.tool
#    → reference_only: true at envelope + every row; rows sorted by filed_at desc
# 4. UI: Dashboard card renders the language block + rows; no order affordance anywhere.
# 5. load-bearing assertion: account 3 order count is ZERO before and after:
#    SELECT count(*) FROM orders WHERE account_id=3;   → unchanged
```

## 6. Walk-away discipline

≥1 hour per PR (routine; no risk/order-path code). The CI-invariant allowlist edit gets an extra
explicit reviewer look (it touches an invariant's config, not its logic).

## 7. What this session does NOT do

- **No orders, no paper book, no positions on account 3** — identity/scoping only (OQ1).
- No composite score, no ranked ordering, no "conviction" vocabulary anywhere.
- No INSIDER-002 work (triage sheet is Reserved; pre-reg waits for the GAPPER-001 verdict).
- No sibling swing-book port; the sibling system keeps running untouched.
- No full-index EDGAR ingestion (OQ2 option C — v2).
- No notifications/alerts (ntfy/SNS) — v1 is pull-only; alerting is a v2 decision.
- No changes to `reference_only.py` guard logic or the invariant script's scan rules.

## 8. Notes & gotchas

1. Engine strategy schedules are ET (#366) — the new APScheduler jobs must use the ET-pinned
   trigger pattern from the gapper jobs, not naive UTC crons.
2. `docker logs` are lost on container recreate — the job must log a one-line daily summary that
   the daily report can pick up (the 7/8 range outage taught this).
3. SEC EDGAR requires a declared User-Agent and ~10 req/s ceiling; the existing client complies —
   do not parallelize the shard loop beyond it.
4. The factor store swaps at 06:04 ET daily (refresh) — the 08:05 catch-up job must open the
   store read-only per-run, never hold a handle across the swap.
5. Git case footgun: stage docs via lowercase `docs/`.
6. `WORKBENCH_INSIDER_MONITOR_ENABLED` default OFF means tests/CI boots stay hermetic (no EDGAR
   calls); the box flips it ON explicitly.
