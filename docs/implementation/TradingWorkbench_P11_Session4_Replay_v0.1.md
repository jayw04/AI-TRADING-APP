# Trading Workbench — P11 §4: Replay (reconstruct & re-verify automated decisions)

| Field | Value |
|---|---|
| Document version | **v1.0 — frozen for execution** (2026-06-20; 4 OQs confirmed + review folded: registry-driven verifiers (Protocol + `REPLAY_REGISTRY`), a capability registry distinguishing `SUPPORTED`/`UNSUPPORTED`/`UNREPLAYABLE`, the MATCH/MISMATCH/SKIPPED/ERROR verdict model, a determinism-invariant box, a `replay_coverage` metric alongside consistency, a pipeline diagram, the one-bad-record→ERROR error policy, `registry_version` on runs, `REPLAY_MISMATCH`=CRITICAL, "verification service not simulation"). Trimmed (out): `audit_schema_version`/`decision_version` columns (forward-looking, add on schema evolution) and a `rows_per_second` metric (dashboard-derivable). |
| Date | 2026-06-20 |
| Phase | **P11** — Operations & Reliability |
| Session | §4 of 5 (Replay) |
| Predecessor | P11 §3 — Reconciliation (PR **#180**, tag `p11-session3-complete` on merge) |
| Successor | P11 §5 — Recovery hardening |
| Repository | `github.com/jayw04/AI-TRADING-APP` |
| Scope | A registry-driven **replay verifier** that reconstructs an automated decision from its **durable audit fingerprint** and recomputes the decision rule from the recorded inputs, asserting it matches what was recorded. Validates **the decision, not the broker outcome** (ADR 0021 / Direction §0). Read-only; introduces `replay_runs` + a `REPLAY_MISMATCH` audit action; flips the §2-reserved **replay-consistency** KPI live and adds **replay coverage**. |
| Estimated wall time | 6–9 hours (verifier registry + per-decision recompute fns + Alembic table + audit action + CLI + daily KPI job + registry/metrics wiring + ~100% tests + runbook) |
| Tag on completion | `p11-session4-complete` |
| Out of scope | See "What this session does NOT do" |

---

## Why this session exists

ADR 0021's *replayable* property and the Direction's §0 objective: **any automated decision
must be reconstructable and re-verifiable from its audit fingerprint.** The audit log already
records *what the automation decided*; replay proves *the decision was correct given its
recorded inputs* — transforming the audit log from a historical record ("this happened") into
**verifiable evidence** ("this happened for the right reason").

> **Replay is a verification service, not a simulation service.** It re-verifies a recorded
> decision against its recorded inputs. It does not simulate the market, re-execute strategy
> code, or re-run the order path.

Replay validates **the decision, not the outcome** (Direction §2): the broker may legitimately
fill differently, the market may have moved — replay does **not** re-check the fill. It
recomputes the *decision rule* from the *recorded inputs* and asserts the recorded *decision*
reproduces. A mismatch means the recorded decision does **not** follow from its recorded inputs
— a logic regression, a fingerprint that omits a load-bearing input, or an input computed
inconsistently. That is forensically consequential, so a mismatch is itself audit-logged
(`REPLAY_MISMATCH`, **CRITICAL**) and alerted.

This is the session that flips §2's **reserved** replay-consistency KPI row (target 100%) from
"— *§4*" to live, and reuses §1's registry + §2's metrics + §3's persisted-run pattern
(`replay_runs` mirrors `reconciliation_runs`) — replay is just another recurring/​on-demand actor.

### Guiding invariants (non-negotiable)

> **1. Read-only, decision-not-outcome.** Replay reads the audit log + the recorded fingerprint,
> recomputes the decision rule from the *recorded* inputs, and compares to the *recorded*
> decision. It never re-executes strategy code, never calls the broker, never touches the order
> path, and never mutates state (beyond appending its own `replay_runs` row + any
> `REPLAY_MISMATCH` audit entry).

> **2. Determinism.** Given the same audit fingerprint, the same replay `algorithm_version`, and
> the same audit schema, replay **must always produce the same verdict.** Recompute functions
> are pure — no clock, no I/O, no randomness, no ambient state. This is what makes a historical
> `replay_runs` row reproducible after future code evolves: a new algorithm version is a new
> verifier; old runs replay identically under their recorded version.

### Pipeline

```
   audit_log row
        │
        ▼
  REPLAY_REGISTRY          (decision_type → ReplayVerifier; capability: SUPPORTED/UNSUPPORTED/UNREPLAYABLE)
        │
        ▼
  ReplayVerifier.replay(payload)   (pure recompute of the decision rule from recorded inputs)
        │
        ▼
   ReplayVerdict           (MATCH | MISMATCH | SKIPPED | ERROR)
        │
        ├─▶ metrics  (replay_verifications_total · replay_consistency_ratio · replay_coverage_ratio · replay_duration_seconds)
        │
        └─▶ audit_log  (REPLAY_MISMATCH — only on MISMATCH; CRITICAL)
        │
        ▼
   replay_runs row         (window · n_checked/matched/mismatched/skipped/error · versions · duration)
```

### What "replayable today" actually means (grounding, not aspiration)

A pre-draft audit-fingerprint survey (mirroring the §3 *intent-domain* honesty check) found that
only decisions whose **durable** fingerprint carries **both the inputs and the decision** are
recomputable today. This is formalized as the **replay capability registry** — each decision
type has a capability state, and `UNSUPPORTED` (not built yet) is deliberately distinguished
from `UNREPLAYABLE` (the fingerprint is missing required inputs — a different engineering
problem):

| Decision | Capability | Fingerprint store | Why |
|---|---|---|---|
| **Circuit-breaker trip** (`CIRCUIT_BREAKER_TRIPPED`) | **SUPPORTED** | `audit_log` | Durable: `realized_pnl_today`, `unrealized_pnl_now`, `net_pnl`, `max_daily_loss` → recompute `net_pnl ≤ −max_daily_loss` |
| **Reconciliation discrepancy** (`RECONCILIATION_DISCREPANCY`, §3) | **SUPPORTED** | `audit_log` + `reconciliation_runs` | Durable: `local`, `broker`, `domain` → recompute the diff classification (pure function) |
| Portfolio overlay scaling | **UNREPLAYABLE** | `signals` via `log_signal("PORTFOLIO", …)` → **dropped** | Fingerprint not durably persisted (non-resolving ticker). Needs the durable-fingerprint follow-on — **the same gap that defers §3 intent.** |
| Risk-check rejection (`ORDER_REJECTED_BY_RISK`) | **UNREPLAYABLE** | `audit_log` + `risk_checks` | Only `reason_codes` persisted; the point-in-time qty/limits/positions that drove the check are **not** captured. |

So §4 v1 replays the **two SUPPORTED decisions** — the circuit-breaker trip (the flagship: a
real `net_pnl ≤ −max_daily_loss` recompute) and the reconciliation-discrepancy classification (a
pure function of the two recorded quantities). The **UNREPLAYABLE** cases share one root cause (a
missing durable fingerprint) and one fix, named below as a dedicated follow-on so it isn't
silently dropped. The registry is the single source of truth aligning this doc with the code.

## What this session ships

1. **`replay_runs` table** (Alembic) — one row per replay pass: `ran_at`, `window_start/end`,
   `n_checked` / `n_matched` / `n_mismatched` / `n_skipped` / `n_error`, `duration_ms`,
   `algorithm_version`, `registry_version`, `detail_json` (the non-MATCH verdicts, compact).
   Mirrors `reconciliation_runs` (telemetry, **not** hash-chained — the mismatch *event* is the
   audit row).
2. **Replay service** (`app/services/replay.py`):
   - `Verdict` StrEnum: `MATCH` / `MISMATCH` / `SKIPPED` / `ERROR`.
   - `ReplayVerdict` dataclass (`audit_log_id`, `decision_type`, `verdict`, `recorded`,
     `recomputed`, `note`).
   - `ReplayVerifier` `Protocol` (`decision_type: str`; `capability: str`; `replay(payload) -> ReplayVerdict`).
   - Concrete verifiers: `BreakerTripVerifier`, `ReconciliationDiscrepancyVerifier` (pure).
   - `REPLAY_REGISTRY: dict[str, ReplayVerifier]` (keyed by the `AuditAction` value) +
     `REGISTRY_VERSION` + a `CAPABILITY` catalog (SUPPORTED/UNSUPPORTED/UNREPLAYABLE) for coverage.
   - `replay_audit_row(row) -> ReplayVerdict` — registry dispatch; unknown action → `SKIPPED`;
     a verifier raising → `ERROR` (never propagates).
   - `run_replay(session, *, since=None, until=None, limit=None) -> ReplayRun` — iterate
     replayable `audit_log` rows in the window, verify each, persist a `replay_runs` row, audit
     each `MISMATCH`, emit metrics. Read-only beyond its own rows. Imports **no** OrderRouter /
     broker / `anthropic`.
3. **`AuditAction.REPLAY_MISMATCH`** — forensic record when a recorded decision does not
   reproduce from its recorded inputs (payload: `audit_log_id`, `decision_type`, `recorded`,
   `recomputed`, `note`). **CRITICAL** severity.
4. **Metrics** — `replay_verifications_total{decision_type, verdict}` Counter;
   `replay_consistency_ratio` Gauge (matched ÷ (matched+mismatched), last pass);
   `replay_coverage_ratio` Gauge (SUPPORTED decision types ÷ total catalogued);
   `replay_duration_seconds` Histogram (mirrors §3 buckets).
5. **CLI verifier** (`scripts/replay_decisions.py`) — replay a date range or a single
   `audit_log` id; prints a verdict table; **exits non-zero on any MISMATCH** (CI/ops usable).
   ASCII-only output (cp1252-safe).
6. **Daily KPI job** (lifespan, 24h cron) — `run_replay(since=now-24h)`; emits the consistency +
   coverage gauges so the dashboard KPI stays fed without rescanning all history. Registered as a
   `replay` infra feature in the ops registry (`INFRA_JOB_IDS["replay"]`).
7. **Tests** (~100% of the new service) + **on-call** scenario ("Replay reports a mismatch") +
   **operations runbook §4** + flipping the §2 reserved replay-consistency KPI row to live +
   adding the coverage KPI row.

## Prerequisites

- **P11 §3 merged** (`p11-session3-complete`): §4 reuses the persisted-run pattern, the
  registry infra-feature pattern, and replays §3's `RECONCILIATION_DISCREPANCY` fingerprint.
- A populated `audit_log` with at least one `CIRCUIT_BREAKER_TRIPPED` row to smoke against
  (the daily-loss spurious-trip incident on the rebootstrapped account provides real rows).
- No new external dependency; no schema change beyond the additive `replay_runs` table.

## Detailed work

### A. `replay_runs` table + model

```sql
CREATE TABLE replay_runs (
    id                INTEGER PRIMARY KEY,
    ran_at            TIMESTAMP NOT NULL,          -- tz-aware
    window_start      TIMESTAMP NULL,              -- replayed audit_log.ts range (NULL = all)
    window_end        TIMESTAMP NULL,
    n_checked         INTEGER NOT NULL DEFAULT 0,  -- replayable rows considered
    n_matched         INTEGER NOT NULL DEFAULT 0,
    n_mismatched      INTEGER NOT NULL DEFAULT 0,
    n_skipped         INTEGER NOT NULL DEFAULT 0,  -- non-replayable action rows encountered
    n_error           INTEGER NOT NULL DEFAULT 0,  -- verifier raised on the row
    duration_ms       INTEGER NULL,
    algorithm_version VARCHAR(8) NOT NULL,         -- "1.0" (the recompute contract)
    registry_version  VARCHAR(8) NOT NULL,         -- the verifier-set version
    detail_json       TEXT NULL                    -- the non-MATCH verdicts (compact)
);
CREATE INDEX ix_replay_runs_ran ON replay_runs (ran_at);
```

Telemetry only — **not** hash-chained (consistent with `reconciliation_runs`; the consequential
*event* is the `REPLAY_MISMATCH` audit row). `algorithm_version` + `registry_version` make a
historical run reproducible after future verifier changes. (`audit_schema_version` /
`decision_version` are intentionally **not** columns yet — add them when the audit schema
actually versions; the determinism invariant already names schema as a replay input.)

### B. Replay service (`app/services/replay.py`)

```python
ALGORITHM_VERSION = "1.0"
REGISTRY_VERSION = "1.0"

class Verdict(StrEnum):
    MATCH = "match"          # replay succeeded — decision reproduces
    MISMATCH = "mismatch"    # decision inconsistent with its recorded inputs (CRITICAL)
    SKIPPED = "skipped"      # decision type intentionally unsupported / not a replayable action
    ERROR = "error"          # the replay engine failed on this row (malformed payload, etc.)

@dataclass(frozen=True)
class ReplayVerdict:
    audit_log_id: int
    decision_type: str
    verdict: Verdict
    recorded: dict
    recomputed: dict
    note: str = ""

class ReplayVerifier(Protocol):
    decision_type: str          # the AuditAction value it handles
    capability: str             # 'supported' | 'unsupported' | 'unreplayable'
    def replay(self, payload: dict) -> ReplayVerdict: ...

# Concrete, pure verifiers — no I/O, no clock (determinism invariant):
class BreakerTripVerifier:      # net_pnl = Decimal(realized)+Decimal(unrealized); MATCH iff
    ...                         #   net_pnl reproduces AND net_pnl <= -Decimal(max_daily_loss)
class ReconciliationDiscrepancyVerifier:   # recompute the diff `kind` from recorded local/broker
    ...

REPLAY_REGISTRY: dict[str, ReplayVerifier] = {
    AuditAction.CIRCUIT_BREAKER_TRIPPED.value: BreakerTripVerifier(),
    AuditAction.RECONCILIATION_DISCREPANCY.value: ReconciliationDiscrepancyVerifier(),
}
# Capability catalog (drives replay_coverage; UNSUPPORTED vs UNREPLAYABLE are distinct):
CAPABILITY: dict[str, str] = {
    "CIRCUIT_BREAKER_TRIPPED": "supported",
    "RECONCILIATION_DISCREPANCY": "supported",
    "OVERLAY_SCALING": "unreplayable",      # missing durable fingerprint
    "ORDER_REJECTED_BY_RISK": "unreplayable",
}

def replay_audit_row(row) -> ReplayVerdict:
    v = REPLAY_REGISTRY.get(row.action)
    if v is None:
        return ReplayVerdict(row.id, row.action, Verdict.SKIPPED, {}, {}, "no verifier")
    try:
        return v.replay(json.loads(row.payload_json))
    except Exception as e:          # one bad record never aborts the run (error policy)
        return ReplayVerdict(row.id, row.action, Verdict.ERROR, {}, {}, repr(e))

async def run_replay(session, *, since=None, until=None, limit=None) -> ReplayRun:
    # select audit_log rows whose action is in REPLAY_REGISTRY within [since, until]
    # → replay_audit_row each → tally → persist replay_runs → audit each MISMATCH → emit metrics
```

`BreakerTripVerifier` recomputes `net_pnl` from `realized_pnl_today + unrealized_pnl_now` (via
`Decimal(str(...))` — the payload stores strings; no float drift) and re-evaluates
`net_pnl ≤ −max_daily_loss`; **MATCH** iff the recomputed `net_pnl` equals the recorded `net_pnl`
*and* the trip condition holds (the row exists because it tripped). A recorded trip whose
recorded inputs do **not** satisfy the rule is a **MISMATCH** — exactly the class behind the
*spurious daily-loss trip* incident, which makes this the highest-value decision to replay first.

**Error policy (#11):** one malformed/raising row yields an `ERROR` verdict and the run
continues; the overall pass always completes and persists. `ERROR` ≠ `MISMATCH` — an engine
failure is operationally distinct from a justified-decision failure.

### C. CLI verifier (`scripts/replay_decisions.py`)

```
python scripts/replay_decisions.py --since 2026-06-01            # replay a window
python scripts/replay_decisions.py --audit-id 12345              # replay one decision
# prints: id · decision_type · verdict · recorded vs recomputed ; exits 1 on any MISMATCH
```

ASCII-only output (cp1252-safe, per the §5 walk-forward gotcha). Usable as a CI gate and an
ops spot-check.

### D. Daily KPI job + registry

A 24h cron (lifespan) runs `run_replay(since=now-24h)` and emits `replay_consistency_ratio` +
`replay_coverage_ratio`. Registered in `app/ops/feature_registry.py` as a `replay` infra feature
(kind `monitor`, `INFRA_JOB_IDS["replay"]`, `verified="validated"`, category `operations`). The
§2 KPI row flips from reserved to live; SLO 100% consistency, **CRITICAL** on any mismatch. A
**coverage** KPI row is added (informational — honestly communicates "consistency 100% over the
N% of decision types we can replay today").

### E. Metrics + audit

- `replay_verifications_total{decision_type, verdict}` Counter.
- `replay_consistency_ratio` Gauge — matched ÷ (matched + mismatched), last pass.
- `replay_coverage_ratio` Gauge — `supported` decision types ÷ total catalogued.
- `replay_duration_seconds` Histogram (mirrors §3 buckets). (Rows/sec is dashboard-derivable from
  `replay_duration_seconds` + `n_checked` — not a stored metric.)
- `AuditAction.REPLAY_MISMATCH` (audit-log skill: enum + on-call scenario + tests). CRITICAL.

## Manual smoke

1. Find a real trip: `SELECT id, payload FROM audit_log WHERE action='CIRCUIT_BREAKER_TRIPPED' LIMIT 1;`
2. `python scripts/replay_decisions.py --audit-id <that id>` → expect `MATCH`, exit 0.
3. Replay a 30-day window → table of `MATCH`/`SKIPPED`, exit 0; a `replay_runs` row persisted with
   `n_mismatched=0`; `replay_consistency_ratio` = 1.0 and `replay_coverage_ratio` reflecting the
   2 SUPPORTED types on `/metrics`.
4. Negative (in a test, not prod): a synthetic mismatched fingerprint → `MISMATCH`, a
   `REPLAY_MISMATCH` audit row, CLI exit 1; a malformed payload → `ERROR`, run still completes.

## Walk-away discipline

**≥2 hours** — §4 adds a new `AuditAction` (audit-subsystem touch → the skill's ≥2h bar), and
replay is a trust-surface verifier. Same gate honored on §3 (#180).

## What this session does NOT do

1. **Does not re-execute decision logic** — v1 reconstructs + recomputes the *rule* from recorded
   inputs (Direction OQ#4). Re-running pinned strategy/overlay code against historical bars is a
   heavier, version-pinned follow-on. (Replay is verification, not simulation.)
2. **Does not replay the overlay decision** — `UNREPLAYABLE`: the overlay fingerprint is not
   durably persisted (`log_signal("PORTFOLIO", …)` drops the non-resolving ticker). Deferred to
   the shared durable-fingerprint change (below).
3. **Does not replay risk-check rejections** — `UNREPLAYABLE`: `ORDER_REJECTED_BY_RISK` persists
   only `reason_codes`, not the point-in-time qty/limits/positions that drove the check.
4. **Does not verify broker outcomes, fills, market prices, or order routing** — replay checks
   the decision, never the outcome (Direction §2). Those belong to other subsystems.
5. **Does not add the durable-fingerprint persistence change itself** — it *names* it as a
   **dedicated ADR-tracked follow-on** that unblocks overlay replay (here) **and** §3's intent
   reconciliation. Likely a small `overlay_runs` table (or a reserved-symbol `log_signal` bypass)
   + a `risk_checks.payload_json` column. Referenced from §5; **not** folded into §4.
6. **Does not make replay continuous/real-time** — on-demand CLI + a daily KPI job; not a
   per-minute job (rescanning the whole log every minute is wasteful and adds no safety).
7. **No frontend** — CLI + metric + audit only.

## Notes & gotchas

1. Match `reconciliation_runs` exactly for `replay_runs` (telemetry, not hash-chained;
   `algorithm_version` + `registry_version` + `duration_ms`; index on `ran_at`). **§5 reuses
   `replay_runs` / `reconciliation_runs` / operational health — it must invent no new persistence
   model** (review's cross-session note).
2. The migration's `down_revision` is the **current head** — after #180 merges, that head is
   `b3d8f1a2c7e9` (§3). Verify with `alembic heads` before writing the revision (the §3 draft
   initially pointed at a stale revision; `alembic heads` showing two heads caught it).
3. Decimal discipline: recompute breaker `net_pnl` with `Decimal(str(...))` over the recorded
   string fields — no float drift in the comparison. Pure recompute (no clock/IO) is what the
   **determinism invariant** requires; a test asserts the same payload yields the same verdict
   across repeated calls.
4. The §3 *intent-domain deferral* and §4's *overlay-replay UNREPLAYABLE* are the **same** missing
   capability (a durable overlay fingerprint). Resolve them together in the follow-on;
   cross-link both docs.
5. The registry is the single source of truth: a new replayable decision = one new
   `ReplayVerifier` + one `REPLAY_REGISTRY`/`CAPABILITY` entry (bump `REGISTRY_VERSION`), no
   dispatcher edits. A registry-integrity test pins `CAPABILITY` keys to real `AuditAction`
   values where applicable.
6. Future direction (not now): replay grows into its own subsystem (engine · verifier registry ·
   store · metrics · dashboard). The registry-driven design already points there; do not build it
   ahead of need.
