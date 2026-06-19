# Trading Workbench — P10 §2: Daily Gross-Exposure Overlay Engine

| Field | Value |
|---|---|
| Document version | v1.0 (execution-ready — ADR 0020 Accepted; final review folded: determinism invariant, restart-recovery smoke, concrete audit JSON, overlay_event_id, gross gauges, partial-fill note. The 2 remaining picks resolved to defaults below.) |
| Date | 2026-06-19 |
| Phase | P10 — Portfolio-Level Risk Engineering |
| Session | §2 of the PortfolioRisk roadmap (§1 vol-targeting, §3/§3C sector caps, §6 breaker, §7 fractional shares all done) |
| Predecessor | P10 §1 vol targeting (shipped, `momentum-portfolio` v0.4.0) + ADR 0020 (Draft) |
| Successor | P10 §4 exposure smoothing |
| Repository | github.com/jayw04/AI-TRADING-APP |
| Scope | Bring the §1-validated EWMA vol-target gross scale to the **live** loop as a separate, opt-in Overlay layer that re-sizes the held book daily without re-selecting names. |
| Estimated wall time | 6–9 hours (touches the engine/scheduler — the safety-critical live execution path) |
| Tag on completion | `p10-s2-overlay-complete` |
| Out of scope | See "What this session does NOT do" |

---

## Why this session exists

`momentum-portfolio` selects names **weekly** and cannot react to an intra-week vol
spike or regime turn — the single biggest residual risk in the owner's reviews
(momentum-crash). P10 §1 built and walk-forward-validated (across GFC/COVID/2022) an
EWMA vol-target gross scale that more than halves max drawdown, but it currently lives
**only inside the backtester's return series** (`_vol_target_overlay`). It does not act
on the live book. This session brings that proven scale to the live loop as a **daily
Overlay layer**, per ADR 0020: a separate, testable module that scales *gross exposure*
of the alpha engine's book — never selecting, never overriding names.

## What this session ships

1. A new **overlay module** `app/strategies/overlay/` — a pure computation
   `(market_state, params) -> desired_gross ∈ [0, 1]` (a **scalar**, never weights),
   reusing the §1 `_gross_scale` EWMA-vol logic. No broker import, no DB writes, no order
   concepts (ADR 0020 invariants).
2. A **bounded framework addition**: a strategy may declare an optional
   `daily_overlay_schedule` (cron, default `None`); the engine registers it alongside
   the existing weekly `schedule` (`max_instances=1` + `coalesce`, like the §6 job).
3. The engine's **compute → validate → execute** overlay path: on a daily (non-rebalance)
   tick, compute `desired_gross`, validate it, diff the *held* book against
   `desired_gross × book × weights`, and route deltas through `OrderRouter.submit()`
   (ADR 0002) — **without re-selecting names**. **Idempotent** (same-day re-fire on an
   already-applied target is a no-op) and **drift-gated** (skip when `|Δgross| < ε`).
4. `momentum-portfolio` **wiring** (default OFF): `use_daily_overlay: bool = False` +
   `daily_overlay_schedule`, in BOTH `default_params` and `params_schema` (schema-parity
   invariant).
5. A structured **audit fingerprint** per overlay run — `overlay_version`, `date`,
   `gross_target`, `proxy_vol`, `reason`, `strategy_version` — distinguishing an overlay
   re-size from a weekly rebalance and making it replayable.
6. **Operational metrics** (Prometheus): overlay executions, skips (drift/idempotent),
   failures (fail-open), average gross target, scheduler reliability.
7. **Tests** at the engine/strategy bar: off-by-default is inert; daily tick scales down
   in high vol; caps at 1.0 (no leverage); fails open when proxy unavailable; never
   re-selects names; overlay deltas pass the risk engine; **idempotent re-fire is a
   no-op**; **sub-ε drift is skipped**.
8. **Runbook** note in `docs/runbook/` describing the overlay, its boundary, the failure
   matrix, and the operator response.

## Prerequisites

- **ADR 0020 accepted** (currently Draft) — this session implements its decision; do not
  start code until it is accepted. ← blocking.
- P10 §1 vol-scale (`_gross_scale`, `_investable_equity`, `_vol_target_overlay`) present
  and green.
- Engine/scheduler (`app/services/scheduler.py`, `app/lifespan.py`) as shipped; the §6
  breaker-monitor interval job is a working example of adding a recurring job.

## Open questions

**Resolved by review + ADR 0020 (2026-06-19):**

1. **Re-size semantics** → **proportional scale** of every sleeve to `desired_gross`,
   preserving the alpha engine's intra-book weights. The overlay emits a **scalar**
   gross, never `desired_weights` (emitting weights would alter composition — an ADR
   0020 invariant violation).
2. **Smoothing** → **deferred to §4.** This session ships the raw daily scale plus a
   minimal **drift threshold** (skip if `|Δgross| < ε`) as execution *hygiene*; the
   EWMA/threshold *damping* of the gross series is §4's job. (Keep ε small and distinct
   from §4's smoothing band so the two don't conflate.)

**Resolved to defaults for v1.0 (revisit only if implementation surfaces a reason):**

3. **Cadence field shape** → `daily_overlay_schedule` **cron string** (symmetry with
   `schedule`, reuse the cron parser), expressed with **day names** to dodge the
   APScheduler day-of-week off-by-one (gotcha 3).
4. **Drift threshold ε** → default **1% of gross** (review suggestion 6); confirm
   against backtested turnover during implementation.

## Detailed work

### §A — Overlay module (`app/strategies/overlay/`) — COMPUTE only

A pure, broker-free, order-unaware computation. It returns a **scalar**, never weights:

```python
def desired_gross(
    *,
    market_returns: Sequence[float],   # proxy (SPY) daily returns, strictly historical
    vol_target_annual: float,
    vol_ewma_span: int,
) -> float:
    """Gross-exposure multiplier in [0, 1]: min(1.0, vol_target / realized_annual_vol),
    realized = EWMA(span) of proxy daily returns × √252. Caps at 1.0 (never leverages).
    Fails OPEN (returns 1.0) when the proxy series is too short to estimate σ — matching
    the §1 strategy posture and ADR 0020's fail-open boundary. Returns ONLY a scalar
    gross; it knows nothing about positions, deltas, or orders (ADR 0020 invariants)."""
```

This is the §1 `_gross_scale` math, extracted so the backtest overlay and the live
overlay share one implementation. Unit-tested in isolation (no store, no engine, no
broker).

### Overlay invariants (from ADR 0020 — restated for the implementer)

The overlay layer **never** selects/ranks symbols, changes factor scores or the alpha
ranking, changes sector/bucket caps, emits orders itself, or leverages (gross ≤ 1.0). It
**only** scales gross exposure of the book the alpha engine produced, fails open on bad
data, and preserves intra-book weights. It is **deterministic** — identical `(positions,
prices, params, date)` → identical `desired_gross`, which is what makes an overlay run
replayable from its audit fingerprint. Check every overlay change against this list.

### §B — Framework: optional daily cadence

- Strategy base gains an optional `daily_overlay_schedule: str | None = None`.
- The engine registration (mirroring the weekly `schedule` and the §6 interval job)
  registers a second job per strategy that declares one. On fire, it invokes the
  **overlay-only path** (§C), NOT `_select_targets`.
- Validate the cron with the existing parser; **use day names** to avoid the documented
  APScheduler `from_crontab` day-of-week off-by-one.

### §C — Engine overlay path: COMPUTE → VALIDATE → EXECUTE → AUDIT

Four explicit stages on a daily tick (the overlay produces desired state; the execute
stage owns orders — ADR 0020):

1. **COMPUTE** — call `desired_gross` (§A) from the proxy series. Fail open → 1.0 on
   missing/short data.
2. **VALIDATE** — assert `desired_gross ∈ [0, 1]`; compute `Δgross = |desired_gross −
   current_gross|`. **Idempotency / drift gate:** if the book is already at the target
   for today, or `Δgross < ε`, **no-op** (skip — counts a `skipped` metric). This is the
   stage that prevents duplicate re-sizing on a double scheduler fire.
3. **EXECUTE** — diff the held book against `desired_gross × book_value × intra-book
   weights` (proportional scale, weights preserved — **no name selection**), and route
   each delta through `OrderRouter.submit()` so it passes the full risk engine (ADR
   0002/0004).
4. **AUDIT** — write the structured fingerprint (§F).

**Failure matrix (fail open / fail safe — never fail closed into a liquidation):**

| Failure | Action |
|---|---|
| Missing SPY proxy | gross = 1.0 (no scaling) |
| Bad / non-finite volatility | gross = 1.0 |
| Empty / too-short history | gross = 1.0 |
| `Δgross < ε` or already applied today | skip (idempotent no-op) |
| Scheduler job fails | retry next tick (`max_instances=1`, `coalesce`) |
| Order rejected at the router | execution stage handles per normal order flow; never bypasses the risk engine |

### §D — Backtest

`_vol_target_overlay` already models this at the return-series level (§1); this session
adds no new backtest math. Optionally assert the live overlay path reproduces the
backtest overlay on a fixture (consistency check), but the backtester stays the eval
ground truth (ADR 0014).

### §E — `momentum-portfolio` wiring (default OFF)

Add `use_daily_overlay: bool = False` and `daily_overlay_schedule: str | None = None` to
BOTH `default_params` and `params_schema` (schema-parity invariant — see gotcha 1). Off
reproduces v0.4.0 weekly-only behavior byte-for-byte and is inert for the live paper book
(id=2) until a deliberate, backtested param change.

### §F — Audit fingerprint, operational metrics, tests, runbook

- **Audit fingerprint (one schema):** each overlay run logs a structured payload, and
  every order it generates carries the run's `overlay_event_id` so a run is traceable
  end to end (Overlay → Orders → Fills → Audit):

  ```json
  {
    "overlay_event_id": "ovl_<uuid>",
    "overlay_version": "1.0",
    "strategy_version": "0.5.0",
    "date": "2026-06-19",
    "gross_before": 0.91,
    "gross_target": 0.63,
    "gross_after": 0.63,
    "proxy_vol": 0.27,
    "reason": "scaled"
  }
  ```

  `reason` ∈ `scaled` / `skip_drift` / `skip_idempotent` / `fail_open`. `gross_before` vs
  `gross_after` makes a partial application (see gotcha 7) visible.
- **Operational metrics (Prometheus):** counters for overlay executions, skips
  (drift/idempotent), and fail-open events; **gauges for current gross, average gross,
  and minimum gross** + scheduler success — P10 is now partly operational engineering, so
  these are first-class dashboard metrics.
- **Tests:** per "What this session ships" #7 — including the idempotent-re-fire no-op
  and the sub-ε drift skip.
- **Runbook:** overlay purpose, the ADR-0020 boundary table, the failure matrix (§C),
  operator response, and how to tell an overlay re-size from a rebalance via the
  fingerprint.

## Manual smoke

1. With `use_daily_overlay=False` (default): run the weekly tick → book identical to
   v0.4.0 (no overlay orders emitted on a non-rebalance day).
2. Enable on a **paper** strategy with a low `vol_target_annual` and a synthetic
   high-vol proxy window → a daily tick emits *reducing* deltas (gross < 1.0), all
   passing the risk engine, audit-tagged as overlay re-sizes, **with the held name set
   unchanged**.
3. Starve the proxy series → daily tick emits no orders (gross = 1.0, fail open, logged
   with `reason=fail_open`).
4. **Idempotency:** fire the daily tick twice in the same day → the second fire is a
   no-op (`reason=skip_idempotent`), no duplicate re-sizing.
5. **Drift gate:** nudge the proxy so `|Δgross| < ε` → tick skips (`reason=skip_drift`).
6. **Restart recovery:** restart the backend mid-day → the scheduler resumes, the overlay
   runs **once** for the day, and a same-day re-fire after restart is idempotent (no
   duplicate scaling).

## Walk-away discipline

**≥ 2 hours.** This session modifies the **engine/scheduler — the live execution path**,
which is held to the same elevated walk-away as risk-gate / live-path work.

## What this session does NOT do

- No **intraday / sub-daily** overlay — daily cadence only.
- No **exposure smoothing** — raw daily scale here; EWMA/threshold damping is **§4**.
- No **per-bucket (sector) caps in the overlay** — §3/§3C handle sector caps at
  construction; the overlay ships gross-only for now.
- No **VIX / breadth inputs** to the scale — needs a data-dependency ADR (§5); the
  overlay uses only the SPY proxy already available.
- No **companion overlay strategy** and no **cross-strategy** position sharing (ADR 0020
  rejected (B)).
- No **gross > 1.0 / leverage** — risk-reducing only.
- No change to **weekly stock selection** cadence or logic (frozen per Review v2).
- Not enabling the overlay on the **live paper book** (id=2) — that is a later, backtested
  opt-in.
- No **Overlay Registry** (review suggestion 10) — deferred until a second overlay
  exists; the audit fingerprint's `overlay_version` is the lightweight stand-in for now.
- No standalone **Execution Engine** — §2 keeps the execute stage inside the overlay
  path (calling OrderRouter); extracting a real Execution Engine is a future step named
  in ADR 0020's re-evaluation triggers.

## Notes & gotchas

1. **Schema-parity invariant:** every new param must land in BOTH `default_params` and
   `params_schema` (`test_schema_matches_default_params` + the frontend form depend on
   it).
2. **`app/` edits need a backend rebuild;** `strategies_user/` is volume-mounted. The
   overlay module + engine change live in `app/` → `docker compose build backend` (or
   test via the host venv, as §1 did, to avoid perturbing the running paper strategy).
3. **Cron day-of-week off-by-one:** APScheduler `from_crontab` treats `0 = Monday` with
   no remap — use **day names** in any overlay cron to avoid the bug that made
   `momentum-portfolio` miss its first Monday rebalance.
4. **Do not regress reviewed-and-praised behaviors:** fail-open-regime / fail-hold-factor-
   data, no per-name stops, rebalance-crash-retry, turnover threshold + rank hysteresis.
5. **Fail open, never closed:** a data gap must yield gross = 1.0 (no scaling), never a
   forced liquidation. The overlay can only *reduce* exposure when it has a valid signal.
6. **This is a framework change to the safety-critical live loop** — keep the PR scoped
   to the overlay path; do not refactor unrelated engine code in the same PR.
7. **Partial fills — known future gap (NOT solved in §2).** If only part of an overlay
   re-size fills, `gross_after ≠ gross_target` and the book sits between states until the
   next tick re-converges (idempotency + the daily cadence make this self-healing, not
   silent). The fingerprint's `gross_before`/`gross_after` make it observable. A proper
   **Partial-Fill Recovery** (intra-day re-attempt, fill reconciliation) belongs to the
   future Operational Recovery ADR / Execution Engine, not here.
