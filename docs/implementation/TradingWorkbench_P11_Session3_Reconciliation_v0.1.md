# Trading Workbench — P11 §3: Reconciliation (broker ⇄ local, alert-only)

| Field | Value |
|---|---|
| Document version | **v1.0 — frozen for execution** (2026-06-19; 4 OQs confirmed + review folded: the never-changes-state invariant, reconciliation domains + future domains, graded run result `pass/warning/fail/error/unavailable`, per-discrepancy severity, detect→classify→surface, `algorithm_version`+`duration_ms` + a duration histogram, "intent reconciliation" rename) |
| Date | 2026-06-19 |
| Phase | **P11** — Operations & Reliability |
| Session | §3 of 5 (Reconciliation) |
| Predecessor | P11 §2 — Observability + KPIs (merged **#179**, tag `p11-session2-complete`) |
| Successor | P11 §4 — Replay |
| Repository | `github.com/jayw04/AI-TRADING-APP` |
| Scope | A periodic **reconciliation** job that compares **broker truth vs local state** (positions/orders) + the overlay's **intent-vs-achieved** gross, classifies discrepancies, and **alerts (audit + metric + ops-state health) but NEVER auto-corrects** (ADR 0021 property 4). Introduces the **first persisted operational table** (`reconciliation_runs`) and a new `RECONCILIATION_DISCREPANCY` audit action. |
| Estimated wall time | 6–9 hours (service + diff logic + Alembic table + audit action + scheduler/registry/metrics wiring + ≥95% tests + runbook) |
| Tag on completion | `p11-session3-complete` |
| Out of scope | See "What this session does NOT do" |

---

## Why this session exists

ADR 0021 property 4: *local position/order state is periodically reconciled against the
broker; a discrepancy **alerts** and is surfaced — it never silently auto-corrects into
new orders.* Today the platform *syncs* (PositionSync/AccountSync overwrite local from the
broker every ~10s) but never **independently checks** that local matches broker, nor that
an automated re-size achieved what it **intended** (the §2/overlay partial-fill gap: a
re-size that only partially fills leaves the book between states). §3 adds that check —
and, per ADR 0021's control model (and ADR 0002), it is **alert-only**: it reports drift,
the owner decides; it never emits corrective orders.

This is the first session to need **durable run records** (the §1/§2-deferred operational
data model), so it introduces `reconciliation_runs`. It reuses §1's registry + §2's
metrics/health rather than new concepts — reconciliation is just another recurring actor.
It depends directly on §2: **§2 Health (is the platform working?) → §3 Reality (does the
platform's view match the broker?).**

### Guiding invariant (non-negotiable)

> **Reconciliation never changes portfolio state.** Its sole responsibility is to determine
> whether observed reality matches expected state and to *surface* discrepancies through
> operational channels — never to repair them. (The same one-subsystem-executes discipline
> as ADR 0019 / 0020 / 0021: each subsystem observes or decides; only the order path acts.)

### Pipeline (detect → classify → surface → owner)

```
Scheduler ─▶ Broker fetch + Local read ─▶ Compare (detect) ─▶ Classify (domain · severity)
          ─▶ Persist (reconciliation_runs) ─▶ Surface (audit + metric + ops-state health) ─▶ Owner
```

Each stage is explicit: **detection** (the diff) is separate from **classification**
(domain + severity), which is separate from **surfacing** (alert), which hands off to the
**owner** (no auto-repair).

## What this session ships

1. **`reconciliation_runs` table** (Alembic) — one row per reconciliation pass: when, what
   was checked, how many discrepancies, a JSON summary. The first persisted ops-data-model
   table (§3/§4's home for durable run records).
2. **Reconciliation service** (`app/services/reconciliation.py`) — fetches broker positions
   (read-only, via the broker adapter `get_positions()`), diffs against the local
   `positions` table, classifies discrepancies, and (separately) compares the latest overlay
   fingerprint's `gross_target` vs the **achieved** gross. **Never writes orders.**
3. **Alert-only surfacing** — discrepancies are audit-logged (`RECONCILIATION_DISCREPANCY`)
   + counted (`reconciliation_discrepancies_total{type}`) + reflected in ops-state health.
   No corrective orders, ever (ADR 0021/0002).
4. **Recurring actor** — a `reconciliation` scheduler job (lifespan), so §2's listener +
   `automation_runs_total{actor="reconciliation"}` + health cover it; a `reconciliation`
   entry in the §1 feature registry.
5. **`RECONCILIATION_DISCREPANCY` audit action** + an **on-call runbook scenario** (the
   AuditAction → playbook invariant).
6. **Tests at the ≥95% risk-adjacent bar** + runbook update.

## Prerequisites

- **P11 §2 merged** (`8eafda4`): the scheduler listener, `automation_runs_total`, measured
  health in `/ops/state`, the feature registry + `category`.
- The broker adapter exposes read-only `get_positions() -> list[dict]` (`app/brokers/base.py`);
  the local `positions` table is keyed by `(account_id, symbol_id)`.
- The overlay writes an audit fingerprint with `gross_target`/`gross_after` (P10 §2) — the
  intent-vs-achieved check reads the latest such entry from `audit_log`.
- `AuditLogger` + the append-only hash-chained `audit_log` (P5 §8); Alembic for the table.

## Reconciliation domains

A **domain** is an independent reconciliation with its own tolerance + severity mapping.
§3 ships two; the rest are **future domains** the same framework extends to (no rework):

| Domain | Compares | §3? |
|---|---|---|
| **Position** | broker positions ⇄ local `positions` | ✅ §3 |
| **Intent** (was "overlay") | the latest automated target (overlay `gross_target`) ⇄ achieved | ✅ §3 |
| Order | expected ⇄ broker open orders | future |
| Account / Cash | broker cash / buying-power ⇄ local | future |

(The "Intent" domain is named generically — it will later compare orders / targets /
allocations, not just gross exposure.)

## Open questions — RESOLVED (2026-06-19)

1. **Source of truth & fetch path → the broker (Alpaca) is truth for positions/orders;
   fetch read-only via the broker adapter `get_positions()`** (a fresh fetch, independent
   of the sync snapshot, so the check also catches a *stalled sync*). *Confirm; alternative
   is to diff the two stored snapshots, but that wouldn't catch a frozen sync.*
2. **Cadence & tolerance → every 5 min (the SLO "reconcile latency < 5 min"); qty matched
   exactly (positions are discrete shares — fractional uses an epsilon, e.g. 1e-6); price/
   market-value drift is informational (logged, not a discrepancy).** *Confirm.*
3. **Persist a table vs ride `audit_log` → a `reconciliation_runs` table** (queryable run
   history + the start of the ops data model §4 extends with `replay_runs`). The audit log
   records the *discrepancy event*; the table records *every run* (incl. clean ones) for the
   KPI. *Confirm.*
4. **Overlay intent-vs-achieved in §3 or §4? → §3** (the Direction named it §3's "first
   consumer"); read the latest overlay fingerprint from `audit_log` and compare to achieved
   gross. *Confirm.*

## Detailed work

### §A — `reconciliation_runs` table (Alembic)

```sql
CREATE TABLE reconciliation_runs (
    id                INTEGER PRIMARY KEY,
    account_id        INTEGER NOT NULL REFERENCES accounts(id),
    ran_at            TIMESTAMP NOT NULL,
    domain            VARCHAR NOT NULL,  -- 'position' | 'intent'
    result            VARCHAR NOT NULL,  -- 'pass' | 'warning' | 'fail' | 'error' | 'unavailable'
    n_checked         INTEGER NOT NULL DEFAULT 0,
    n_discrepancies   INTEGER NOT NULL DEFAULT 0,
    duration_ms       INTEGER,           -- run latency (→ avg reconciliation latency)
    algorithm_version VARCHAR NOT NULL,  -- e.g. '1.0' — old runs stay reproducible when logic changes
    detail_json       TEXT               -- per-discrepancy summary (symbol · severity · local · broker · delta)
);
CREATE INDEX ix_reconciliation_runs_account_ran ON reconciliation_runs (account_id, ran_at);
```

**Run result (graded, review §2):** `pass` (no differences) · `warning` (minor tolerance
exceeded, e.g. small gross drift) · `fail` (a real mismatch, e.g. position qty) · `error`
(the reconciliation itself threw) · **`unavailable`** (broker unreachable → *no
reconciliation occurred* — distinct from `fail`, mirroring §2's `unknown`). On
`unavailable` the run is still recorded; nothing is concluded about reality.

Auto-generated migration reviewed per CLAUDE.md (clean imports, proper down-revision, no
destructive ops). The table is **append-only in spirit** (run history); not hash-chained
(it's operational telemetry, not the audit log).

### §B — Reconciliation service (`app/services/reconciliation.py`)

```python
@dataclass(frozen=True)
class Discrepancy:
    domain: str         # 'position' | 'intent'
    kind: str           # 'qty_mismatch' | 'missing_local' | 'missing_broker' | 'gross_drift'
    severity: str       # 'low' | 'medium' | 'high' | 'critical'
    symbol: str | None
    local: str | None
    broker: str | None
    note: str = ""

# Severity mapping (drives dashboards/alerts): missing symbol → high; qty mismatch →
# high; gross drift → medium; price/value drift → low (informational, not a discrepancy).

async def reconcile_positions(session, broker, account_id, *, qty_eps=Decimal("1e-6")) -> list[Discrepancy]:
    """Read-only: fetch broker positions, diff vs the local `positions` table by symbol.
    Classifies qty mismatch / missing-on-one-side + severity. NEVER writes orders or
    mutates positions."""

async def reconcile_intent(session, account_id, *, tol=0.02) -> list[Discrepancy]:
    """Intent domain: compare the latest automated target (overlay `gross_target` from the
    audit fingerprint) vs the achieved gross from current positions; flag `gross_drift`
    (severity medium) if |achieved - target| > tol (the partial-fill gap). Generalizes
    later to orders / targets / allocations."""
```

A pass per domain: detect → classify (domain · severity) → write a `reconciliation_runs`
row (graded `result` + `duration_ms` + `algorithm_version`) → **alert** on any discrepancy
(§C). Returns the discrepancies; emits nothing to the order path. On a broker fetch
failure the position run is recorded `unavailable` (no conclusion drawn).

### §C — Alert-only surfacing

- **Audit**: one `RECONCILIATION_DISCREPANCY` entry per discrepancy (actor=SYSTEM,
  target=account), payload = the `Discrepancy` summary. (New `AuditAction` enum value —
  audit-log skill + the on-call playbook scenario, §E.)
- **Metric**: `reconciliation_discrepancies_total{domain, severity}` +
  `automation_runs_total{actor="reconciliation", outcome}` + a
  `reconciliation_duration_seconds` **histogram** (latency → "avg reconciliation latency"
  SLO < 5 min).
- **Health**: the `reconciliation` feature surfaces `degraded` in `/ops/state` while an
  unresolved discrepancy stands (via its last-error gauge / a recent-discrepancy read).
- **No auto-correction**: the service has no `OrderRouter` import (a CI/grep guard like the
  research engine); remediation is an owner decision (mirrors ADR 0019).

### §D — Recurring actor + registry

- **Lifespan**: register a `reconciliation` interval job (5 min) on the shared scheduler —
  so §2's listener records its scheduler health and `automation_runs_total` its outcome.
- **Registry** (`app/ops/feature_registry.py`): add
  `OperationalFeature("reconciliation", "Broker/local reconciliation (§3)", "monitor",
  "ADR 0021", None, "n_a", category="operations")` + `INFRA_JOB_IDS["reconciliation"]`.

### §E — Audit action + tests + runbook

- **`AuditAction.RECONCILIATION_DISCREPANCY`** (+ audit-log allowlist + the on-call
  playbook scenario — the AuditAction→playbook invariant).
- **Tests (≥95%, risk-adjacent)**: position diff (match / qty-mismatch / missing-local /
  missing-broker) with a stub broker, asserting `severity`; intent within/beyond `tol`;
  a clean pass writes `result="pass"`, a real mismatch `result="fail"`, a minor tolerance
  breach `result="warning"`, a broker-fetch failure `result="unavailable"` (run still
  recorded, no conclusion); a discrepancy writes the row + audits + increments the metric;
  **the service never calls the order path** (assert no submit + a grep guard). Plus the
  registry drift guard (the new infra job-id) and a resolver test (reconciliation health).
- **Runbook** (`docs/runbook/operations.md` + on-call): what a `RECONCILIATION_DISCREPANCY`
  means and the operator response (investigate; reconcile manually — never an auto-fix).

## Manual smoke

1. Seed a local position that the (stub/paper) broker doesn't have → run the job →
   a `reconciliation_runs` row `result="fail"` (severity HIGH), a `RECONCILIATION_DISCREPANCY`
   audit entry, `reconciliation_discrepancies_total` increments, and `/ops/state` shows the
   `reconciliation` feature `degraded`. **No orders submitted** (check the order table).
2. Aligned local/broker → `result="pass"`, no audit/alert, feature `healthy`.
3. `GET /metrics` → `reconciliation_discrepancies_total` + `automation_runs_total{actor="reconciliation"}` present.

## Walk-away discipline

**≥ 2 hours.** §3 adds an audit action (immutable-log subsystem), a DB table + migration,
and a recurring actor on the live scheduler, and is **risk-adjacent** (it reads positions
and must provably never trade). Held to the audit/risk bar.

## What this session does NOT do

- **No auto-correction / remediation** — reconciliation is **alert-only** (ADR 0021 prop 4);
  it never emits corrective orders. A bounded, owner-gated auto-remediation is a future ADR.
- **No replay (§4) or recovery hardening (§5).**
- **No new alert subsystem / UI** — surfacing is audit + metric + `/ops/state` health (the
  `alerts` router is a TradingView receiver, unrelated). A notifications channel is future.
- **No order/risk-engine change**, no new external dependency.
- **No root-cause attribution** (Broker / Execution / Sync / Config / Unknown — review §5):
  deferred. It's speculative — the reconciler often can't reliably infer *why* reality
  drifted; `domain` + `severity` already drive the operator response. Add only if trend
  analysis later needs it.
- **No Order/Account/Cash domains** yet (future domains, table above) — §3 ships Position +
  Intent.

## Notes & gotchas

1. **Reconcile ≠ sync.** PositionSync *overwrites* local from the broker; reconciliation
   *compares and alerts* with an **independent fresh broker fetch** — so it also catches a
   *stalled/failed sync* (which a two-stored-snapshot diff would not).
2. **Never the order path.** The service must not import `OrderRouter`/submit; add a grep/CI
   guard (mirrors the research-engine read-only posture). The whole point is alert-not-act.
3. **AuditAction → playbook invariant** (CLAUDE.md "proven costly"): adding
   `RECONCILIATION_DISCREPANCY` requires the on-call playbook scenario in the same PR.
4. **Alembic review** (CLAUDE.md): hand-review the autogenerated migration (down-revision,
   no destructive ops); `reconciliation_runs` is additive.
5. **`docs/` vs `Docs/` git-add case quirk** (bit §1/§2/§5) — verify `git diff --cached
   --name-only` includes every new doc/migration before committing.
6. **Fractional positions** — qty compares with an epsilon (fractional shares, P10 §7), not
   exact equality.
7. **Tolerance, not zero, for gross drift** — a partial fill leaves a small intended-vs-
   achieved gap that self-heals next overlay cycle; only flag beyond `tol` to avoid noise.
