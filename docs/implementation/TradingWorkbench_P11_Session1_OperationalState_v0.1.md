# Trading Workbench — P11 §1: Operational State + Feature Registry

| Field | Value |
|---|---|
| Document version | **v1.0 — frozen for execution** (2026-06-19; the derive-vs-persist open question resolved → DERIVE, no new schema) |
| Date | 2026-06-19 |
| Phase | **P11** — Operations & Reliability |
| Session | §1 of 5 (foundation; ADR 0021 acceptance milestone already done) |
| Predecessor | P11 Direction **v1.0** (frozen charter) + **ADR 0021 Accepted** (`f1e3276`) |
| Successor | P11 §2 — Observability + KPIs |
| Repository | `github.com/jayw04/AI-TRADING-APP` |
| Scope | A **read-only** surface answering *"what is actually enabled/running today, and is it healthy?"* — a static **feature registry** (key · ADR · flag · verified-status) + a **resolver** that derives the four operational states (Implemented → Enabled → Healthy → Verified) from existing sources, exposed via one API endpoint + a CLI. **No new schema, no order-path changes.** |
| Estimated wall time | 4–6 hours (registry + resolver + endpoint + CLI + tests + runbook) |
| Tag on completion | `p11-session1-complete` |
| Out of scope | See "What this session does NOT do" |

---

## Why this session exists

P11's objective is to make every automated action **Observable, Reproducible, Recoverable,
Auditable** (Direction v1.0 §0). The cheapest, highest-leverage first step — and the one
that unblocks the rest — is **Observable, at the coarsest grain**: a single place that
answers *"what is actually running today?"*. Today that answer is scattered across strategy
params, scheduler registrations, ADRs, and backtest verdicts; no one surface states it.

The Direction defines four **distinct** states per feature — **Implemented** (code on
`main`) → **Enabled** (running on a book) → **Healthy** (running correctly) → **Verified**
(cleared its promotion backtest). §1 builds the registry + resolver for those states. It is
deliberately the *smallest* slice: **basic** health only (is the actor's job registered /
not stale); the full KPI-based health + dashboard is §2. It writes nothing and touches no
order path — pure read-only observability.

## What this session ships

1. **Feature registry** — `app/ops/feature_registry.py`: a typed, static catalog of the
   platform's operational features (the overlays, the breaker monitor, the strategy
   sector cap, scheduled rebalance), each with its governing ADR, enable-flag param,
   kind, and **verified-status** (the promotion-backtest outcome, incl. §5 = `no_go`).
2. **Operational-state resolver** — `app/ops/state.py`: `resolve_operational_state(...)`
   derives the four states per feature from existing sources (live strategy params +
   registered scheduler jobs + the registry's static verified-status). **No new table.**
3. **Read-only API endpoint** — `GET /api/v1/ops/state` → the feature-state list as JSON.
4. **CLI** — `scripts/ops_state.py`: prints the same table for the no-UI operator (the
   dashboard surface is §2).
5. **Registry-integrity test** — every flag-based feature's `enable_flag` maps to a real
   strategy param (a schema-parity-style guard so the registry can't drift from the code).
6. **Resolver + endpoint tests** + a **runbook** note (`docs/runbook/operations.md`, new).

## Prerequisites

- **ADR 0021 Accepted** (the contract this phase implements) — done (`f1e3276`).
- **P11 Direction v1.0** frozen — done.
- The strategy engine exposes `_running` (`RunningStrategy.instance.params`, `.job_id`,
  `.overlay_job_id`) and holds the `AsyncIOScheduler` (`get_jobs()` / `get_job(id)`); the
  feature flags exist as `momentum-portfolio` params (`use_vol_scaling`,
  `use_daily_overlay`, `overlay_gross_smooth_span`, `use_breadth_overlay`,
  `use_vix_overlay`, `max_sector_pct`) — all shipped in P10. The §6 breaker monitor
  registers a `breaker_monitor` interval job in `lifespan`.

## Open questions — RESOLVED (2026-06-19)

1. **Operational-state store — derive vs. persist → DERIVE (no new schema).** State is
   read live from strategy params + registered jobs + the static registry. This matches
   the Direction's "avoid new schema if the data exists" and keeps §1 the smallest slice.
   A persisted **`system_health` / `*_runs` operational data model** (Direction §4 deferred
   list) is introduced in §2/§3 when history/KPIs need it — not now. Doc frozen at v1.0.

## Detailed work

### §A — Feature registry (`app/ops/feature_registry.py`)

A static, typed catalog — the single source of truth for *what features exist and how to
tell if they're on*. No DB; lives in code so it can't silently drift.

```python
from dataclasses import dataclass

@dataclass(frozen=True)
class OperationalFeature:
    key: str               # stable id, e.g. "daily_overlay"
    title: str             # human label
    kind: str              # "overlay" | "monitor" | "selection" | "infra"
    governing_adr: str     # "ADR 0020"
    enable_flag: str | None  # strategy param that turns it on; None = infra/always-on
    verified: str          # "validated" | "pending" | "no_go" | "n_a"  (promotion-backtest outcome)
    note: str = ""

FEATURES: tuple[OperationalFeature, ...] = (
    OperationalFeature("vol_target", "Vol-target overlay (§1)", "overlay", "ADR 0014/0020",
                       "use_vol_scaling", "validated", "walk-forward across regimes; a drawdown tool"),
    OperationalFeature("daily_overlay", "Daily gross-exposure overlay (§2)", "overlay", "ADR 0020",
                       "use_daily_overlay", "pending", "needs promotion backtest before enabling"),
    OperationalFeature("exposure_smoothing", "Exposure smoothing (§4)", "overlay", "ADR 0020",
                       "overlay_gross_smooth_span", "pending", "None/0 = off"),
    OperationalFeature("breadth_overlay", "Breadth regime overlay (§5)", "overlay", "ADR 0022",
                       "use_breadth_overlay", "no_go", "promotion backtest NO-GO; stays off"),
    OperationalFeature("vix_overlay", "VIX regime overlay (§5)", "overlay", "ADR 0022",
                       "use_vix_overlay", "no_go", "promotion backtest NO-GO; stays off"),
    OperationalFeature("sector_cap", "Strategy sector cap (§3)", "selection", "ADR 0018",
                       "max_sector_pct", "n_a", "None = off"),
    OperationalFeature("breaker_monitor", "Continuous breaker monitor (§6)", "monitor", "ADR 0021/0004",
                       None, "validated", "60s lifespan job; infra, no per-strategy flag"),
)
```

`verified` is intentionally a **static, curated** field (the promotion verdict is a human
research decision, not a runtime fact) — it mirrors the roadmap's Implemented-vs-Proven
table so the two never disagree. Updating a verdict is a one-line registry edit + commit.

### §B — Operational-state resolver (`app/ops/state.py`)

```python
@dataclass(frozen=True)
class FeatureState:
    key: str
    title: str
    governing_adr: str
    flag: str | None
    implemented: bool   # always True — it's in the registry (code on main)
    enabled: bool       # see resolution below
    healthy: str        # "ok" | "degraded" | "n_a"  (BASIC in §1; full KPIs are §2)
    verified: str       # from the registry

async def resolve_operational_state(
    session_factory, engine
) -> list[FeatureState]: ...
```

**State resolution (derive; no new table):**
- **Implemented** — `True` for every registry entry.
- **Enabled** —
  - *flag features:* `True` iff any **engine-runnable** strategy (DB `strategies` with a
    runnable status) has the flag truthy in its **merged** params (`{**cls.default_params,
    **row.params_json}` — same merge the engine uses). `max_sector_pct`/`overlay_gross_smooth_span`
    are "enabled" when set (non-None / >0).
  - *infra features* (`enable_flag is None`): `True` iff the actor's scheduler job is
    registered (e.g. `scheduler.get_job("breaker_monitor") is not None`).
- **Healthy (BASIC, §1)** — `"n_a"` when not enabled. When enabled: `"ok"` if the
  feature's backing scheduler job is registered (overlay → the owning strategy's
  `overlay_job_id`; monitor → its interval job); else `"degraded"`. **Freshness/last-run
  and KPI-based health are §2** (this is the deliberate floor — see Out of scope).
- **Verified** — passthrough from the registry.

The resolver reads the engine's `_running` for params + job ids and the scheduler for infra
jobs; it opens a read-only DB session for the strategy rows. No writes, no order path.

### §C — API endpoint (`app/api/v1/ops.py`)

A new read-only router, mounted under the existing `/api/v1` app (pattern: the other
`app/api/v1/*.py` routers). Bound to localhost like the rest; read-only, no auth change.

```
GET /api/v1/ops/state
→ 200 { "as_of": "<iso>", "features": [ {key,title,governing_adr,flag,
        implemented,enabled,healthy,verified,note}, ... ] }
```

### §D — CLI (`scripts/ops_state.py`)

Host-venv script that calls `resolve_operational_state` and prints a fixed-width table
(key · enabled · healthy · verified · ADR). The no-UI operator surface; ASCII-only output
(Windows cp1252 — learned the hard way in the §5 backtest script).

### §E — Tests + runbook

- **`tests/ops/test_feature_registry.py`** — registry integrity: every flag-based
  feature's `enable_flag` is a real key in `MomentumPortfolio.default_params` (drift
  guard); `verified` ∈ the allowed set; keys unique.
- **`tests/ops/test_operational_state.py`** — resolver: a strategy with `use_daily_overlay=True`
  → `daily_overlay.enabled`; off → not enabled; infra `breaker_monitor` enabled iff its job
  registered; `healthy="n_a"` when off; `verified` passthrough (§5 overlays = `no_go`).
- **Endpoint test** — `GET /api/v1/ops/state` returns 200 + the feature list.
- **Runbook** — `docs/runbook/operations.md` (new): how to read the ops-state surface, what
  each state means, and the "Healthy" definition (Direction §2).

## Manual smoke

1. `GET /api/v1/ops/state` on the running stack → every registry feature present; the §5
   `breadth_overlay`/`vix_overlay` show `verified="no_go"`, `enabled=false`.
2. `python apps/backend/scripts/ops_state.py` → the same table, readable.
3. Temporarily set `use_daily_overlay=true` on a **paper** strategy + reload → `daily_overlay`
   flips to `enabled=true`, `healthy="ok"` (its overlay job is registered); revert.
4. Confirm the resolver opens only read-only sessions and submits no orders (grep the diff:
   no `OrderRouter`/`submit` import in `app/ops/`).

## Walk-away discipline

**≥ 1 hour.** Read-only, off the order path, no schema change — the routine bar (not the
≥2h live-path/risk bar). It touches no risk, order, or audit code.

## What this session does NOT do

- **No full KPI-based health** (scheduler success %, fail-open rate, duplicate-exec count,
  last-run freshness) — that is **§2** (Observability). §1 health is the basic job-present
  check only.
- **No persisted operational data model** (`system_health` / `*_runs` tables) — §1 derives
  state live; persistence comes when §2/§3 need history.
- **No reconciliation / replay / recovery** (§3/§4/§5).
- **No dashboard UI** — JSON endpoint + CLI only; the dashboard surface is §2 (Direction
  open question #2).
- **No enabling of any overlay** — this surface *reports* enable-state; flipping flags is a
  separate, backtest-gated decision (§5 = NO-GO).
- **No order-path or risk-engine change**, no new external dependency, no audit writes.

## Notes & gotchas

1. **`verified` is curated, not computed.** The promotion verdict is a human research
   decision; keep it a registry constant synced with the P10 roadmap's Implemented-vs-Proven
   table. A future §-backtest that flips a verdict is a one-line registry edit.
2. **`docs/` vs `Docs/` git case quirk** (seen repeatedly this phase): when adding the new
   `app/ops/` files / `docs/runbook/operations.md`, `git add` with the path case that
   matches the index, or verify with `git status` that the file actually staged.
3. **ASCII-only CLI output** — the §5 backtest script crashed on Windows cp1252 over `→`/`§`;
   keep `ops_state.py` output plain ASCII.
4. **Merged params, not raw `params_json`** — "enabled" must use the engine's merge
   (`default_params` ⊕ `params_json`), or a feature on-by-default-but-absent-from-`params_json`
   reads as off. (Today all flags default off, but don't bake that assumption in.)
5. **Engine may be unavailable in some contexts** (tests, alpaca-disabled) — the resolver
   must degrade gracefully (treat infra jobs as not-registered → `enabled=false`/`healthy="n_a"`)
   rather than raise, mirroring how `FactorAccessor` handles a missing store.
