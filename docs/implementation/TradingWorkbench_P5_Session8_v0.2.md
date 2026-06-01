# P5 Session 8 — Production Hardening

| Field | Value |
|---|---|
| Document version | **v0.2** (updated in-place from v0.1; 14 drift corrections from Sessions 0–7 Results + candid acknowledgment of execution-surfaced drift) |
| Date | 2026-06-01 |
| Phase | **P5 — Live Trading**, **§8** (entirely; final P5 session) |
| Predecessor | `TradingWorkbench_P5_Session7_v0.2.md` (tag `p5-session7-complete`, PR #45 @ `9f589e5`-built; predecessor branch was at `p5-session6-complete`) |
| Repository | `github.com/jayw04/AI-TRADING-APP` |
| Scope | Make the workbench safe to run beyond a developer laptop. Immutable audit log (DB triggers blocking UPDATE/DELETE, integrity verification script). Subsystem-aware `/healthz` endpoint. Prometheus `/metrics` with the dozen metrics that actually matter. Structured-log redaction guard for credentials. Daily SQLite backup with 30-day retention. Deployment runbook for a fresh box. On-call playbook for the dozen common failure modes. Single PR. |
| Estimated wall time | 5 hours |
| Stopping point | `git tag p5-session8-complete` (and `git tag p5-complete` after final P5 verification passes) |
| Out of scope | TLS termination (handled by reverse proxy outside the docker-compose). Multi-host deployment / Kubernetes / autoscaling — the workbench is single-host for the foreseeable future. PagerDuty / OpsGenie integration (the on-call playbook is a doc; pager rotation is up to you). External secret stores (KMS / Vault) — the master-key-in-env model from §4 is the deployment model. Postgres / external DB — SQLite WAL stays through P5. Multi-instance HA — single-instance only. Disaster recovery tooling beyond the backup script. Log aggregation infrastructure (the workbench writes JSON to stdout; you wire that into whatever you have). |

---

## Updated in v0.2 (drift corrections + candid acknowledgment of what we can't predict)

This file was updated 2026-06-01 against what Sessions 1–7 actually shipped (v0.1 was drafted 2026-05-23, before any of them executed). Sources: Session Zero Results, Session 2 v1.0 + Results, Session 3 Results, Session 4 Results, Session 5 v0.2 + Results, Session 6 v0.2 + Results, Session 7 v0.2 + Results.

### Part 1 — Drift corrections applied below (the knowable ones)

1. **`AuditLogger` lives at `app/audit/logger.py` (NOT `app/services/audit_log.py`); is sync (NOT async); `write()` does NOT take `await`.** Session 5, 6, 7 Results all confirmed. Session 8 v0.1 has the wrong module path everywhere and treats `write` as async. This is the most consequential drift in this session — §8.1's hash-chain integration with `AuditLogger.write()` must match the sync signature. The §8.1 raw-SQL INSERT approach still works (it's the same atomic-write pattern), but the function body is sync and uses synchronous SQL execution.

2. **Audit log immutability is PARTIALLY shipped already.** Session 7 Results documents "audit-immutability tests all green" as part of Session 7's CI. This is a **pytest-level** assertion that ORM code paths don't mutate audit_log (probably a Session 5 or 6 add-on, not the full DB-trigger version). §8.1's contribution is the **storage-layer DB triggers** (`audit_log_no_update`, `audit_log_no_delete`), the **hash chain columns** (`row_hash`, `prev_hash`), the **verify_audit_integrity.py** script, and the **grep-based CI invariant** (`check_audit_immutability.sh`). The existing pytest test stays; §8 adds defense-in-depth at the storage and CI layer.

3. **CI invariant count after §8: five shell + new audit-immutability = six shell; plus ADR 0002 pytest; plus the existing audit-immutability pytest from Session 7; plus three Python coverage gates.** Session 7 Results explicitly listed "5 shell invariants + ADR 0002 + audit-immutability" at the point Session 7 shipped. The five shell at that point: `check_strategy_isolation.sh`, `check_mcp_readonly.sh`, `check_no_llm_in_order_path.sh`, `check_broker_isolation.sh`, `check_no_env_credentials.sh`. Session 8's `check_audit_immutability.sh` makes it six shell invariants. Plus the ADR 0002 pytest invariant. Plus the audit-immutability pytest from Session 7. Plus three Python coverage gates that aren't called "invariants" but live in the same CI category. The §8 count needs to be calibrated against this baseline, not against v0.1's imagined "eight invariants → ninth invariant" inventory.

4. **`check_adr0002.sh` referenced in Prerequisites — does NOT exist.** Session Zero, Session 4 v1.0 confirmed: ADR 0002 is enforced by `tests/test_adr_0002_invariant.py` + the `_router_token` tripwire. Remove from Prerequisites Check.

5. **Paths and tooling.** Windows working dir (`C:\LLM-RAG-APP\ai-trading-app`); `uv` not on PATH — use `.\.venv\Scripts\python.exe`; pytest needs `--cov-branch` for the risk gate. Affects Prerequisites, §8.5 backup verification, §8.6 deployment runbook (the deployment runbook itself is for Linux deploys so paths stay Linux there), §8.11 commit/PR.

6. **`docker compose exec backend uv run ...` patterns swept** to `.\.venv\Scripts\python.exe` in local-dev contexts. §8.6 deployment runbook keeps the `docker compose exec` form since deployment IS the docker context.

7. **PR merge convention is `--squash`** (Sessions 4, 5, 6, 7 all used squash). §8.11 needs the same.

8. **`AccountMode` not `BrokerMode`; `OrderSourceType` not `OrderSource`.** Session 8 has fewer of these (it's mostly observability layer), but the on-call playbook §8.7 and the tests in §8.8 use them.

9. **`ReasonCode` enum is the convention for typed rejection codes** (Session 6 + 7). On-call playbook §8.7 references reject codes — use the typed names.

10. **Strategy → account mapping has no `account_id` FK** (Session 5 Results, used heavily in Session 7). Doesn't affect §8 substantively — Session 8 is observability, not strategy operations — but the on-call playbook entry "Strategy in cooldown but I want to retry NOW" and "Circuit breaker keeps tripping" reference accounts; phrase carefully.

11. **Shared `ensure_aware()` helper at `app/utils/time.py`** (Session 5 §5.0). §8.2's healthz scheduler-recency check compares `last_run_at` (likely SQLite-stored DateTime) against `datetime.now(timezone.utc)`. Same pattern: coerce via `ensure_aware`.

12. **`app/api/v1/__init__.py` is the central router registry**, not `main.py`. §8.2 healthz wiring should use this pattern. Healthz lives outside `v1/` (it's unauthenticated and version-stable), so it may register directly via the main app — but verify against current `app/main.py` shape.

13. **Frontend uses `apiFetch` + plain useEffect polling** (Session 6 + 7 pattern; no React Query). Session 8 doesn't have substantial frontend work but the `/metrics` and `/healthz` endpoints may need ops-dashboard frontend hooks — keep the pattern.

14. **Walk-away discipline ≥1h for §8.** Session 4 skipped it (Results punch list); Sessions 5, 6, 7 honored it. §8 doesn't expand the live-money surface (Session 7 did that), so a single hour is sufficient — Session 7's ≥2h was the elevated discipline; §8 returns to the normal ≥1h.

### Part 2 — Candid acknowledgment of what this drift analysis CANNOT predict

Sessions 5, 6, 7 each surfaced 6-10 execution-time deviations from their v0.2 plans. Session 8 has the largest surface area of any P5 session — observability touches the audit log, every endpoint, the broker registry, the scheduler, the credential store, the order router, the risk engine — and almost every Sessions 1-7 deliberate-deviation has implications for §8.

**Categories most likely to surface during execution:**

- **`AuditLog` model column shape.** §8.1 adds `row_hash: String(64) NOT NULL` and `prev_hash: String(64) NULL`. Verify the current AuditLog model in `apps/backend/app/db/models/audit_log.py` (note: Session 7 Results says "five UPPER audit actions added"; this confirms the model is in the new location, but exact column types/conventions need verification).

- **`AuditLogger.write` actual signature in `app/audit/logger.py`.** §8.1.4 wraps the existing write. Verify the parameter list — Session 5 + 6 + 7 calls show `actor_type=`, `actor_id=`, `action=`, `target_type=`, `target_id=`, `payload=`, `user_id=` — but the actual order and required-vs-optional may differ. Verify before rewriting.

- **Whether `AuditLogger.write` is a static method or instance method.** §8.1.4 sketches it as `@staticmethod async def write(session, ...)`. Session 6/7 Results call it as `AuditLogger.write(self._session, ...)` — consistent with static — but verify.

- **Existing audit-immutability pytest (Session 7 inherited).** Find the test that's already green; understand what it asserts. §8's storage triggers + grep CI invariant + verify_audit_integrity.py are layered defense on top of whatever Session 7 already added. Don't duplicate; don't conflict.

- **`run_activation_completion` scheduler entry.** §8.2 healthz checks scheduler.last_run_at; Session 7 Results shows the activation scheduler uses `scheduler.add_job(..., id="activation_completion", max_instances=1, coalesce=True)`. Verify how to read `last_run_at` from APScheduler (it's accessed via the scheduler's job store, not a direct attribute).

- **`BrokerRegistry` state inspection.** §8.2 healthz checks "≥1 adapter loaded, or no_accounts." Session 2 v1.0 introduced BrokerRegistry; Session 4 made `_construct/_try_construct/load_all/refresh` async. Verify how to read the current adapter count (probably `len(registry._adapters)` but verify the actual attribute).

- **Backup script's interaction with WAL.** §8.5's `backup.sh` runs `sqlite3 .backup` against the WAL DB. Verify the WAL mode is on (it should be per Session 2 v1.0) and that the backup procedure preserves WAL atomicity.

- **Prometheus metric registration.** §8.3 registers a dozen metrics via `prometheus_client`. Verify the dep is already in `pyproject.toml` (likely from P3 work; Session 5 Results mentioned `structlog + prometheus_client` indirectly). Confirm before assuming.

- **The `/healthz` and `/metrics` routes — how to register at the app root.** §8.2 and §8.3 want unauthenticated routes outside `/api/v1/`. Verify the actual app structure in `apps/backend/app/main.py` — Sessions 5-7 confirmed the v1 router goes through `app/api/v1/__init__.py`, but the root app's other routes (healthz, metrics) may have a different convention.

- **The `app/observability/` package — does it already exist?** §8.1.4 imports `from app.observability.audit_hash import compute_row_hash`. v0.1 assumes the package exists; verify whether `app/observability/` is a new directory or if metrics/logging already live there from an earlier session.

**Process recommendation for implementation:**

1. **Read `app/audit/logger.py` first.** Confirm the actual `AuditLogger.write` signature. The §8.1.4 hash-chain integration depends on this.

2. **Read `app/db/models/audit_log.py` next.** Confirm the column conventions (timestamp type, payload column type — JSON or TEXT, etc.).

3. **Run `python -m pytest -q tests/test_audit_*` or equivalent** to find the existing audit-immutability test. Understand what it asserts before adding the trigger-based version.

4. **Verify `prometheus_client` is in pyproject.toml** before §8.3.

5. **Confirm `apps/backend/app/observability/` exists** or treat its creation as part of §8.1 / §8.3.

6. **Capture deviations in Session 8 Results** following the established pattern.

**§8 is the final P5 session.** When it ships, you've completed P5 and the workbench can run beyond the developer laptop. The walk-away discipline matters: read with attention to the §8.1 trigger interaction (the raw-SQL INSERT approach is correct in principle but needs to match the actual `AuditLogger.write` signature), and to the §8.2 healthz subsystem checks (a subsystem you forget to verify is the one that silently fails).

---

## ⚠ Real-money posture

This session is the answer to: "what happens when something goes wrong at 3am?"

The previous sessions built defenses against algorithmic and human error during the trading day. §8 builds defenses against:
- **Bugs that corrupt the audit trail.** If a future PR accidentally writes an UPDATE to audit_log, you'd lose the immutability that makes the log evidentiary. DB triggers enforce append-only at the storage layer.
- **Silent subsystem failures.** Healthz that returns 200 because the HTTP server is up but the broker registry is empty is worse than no health check. Subsystem-aware checks ensure the green light means "really working."
- **Operating in the dark.** Without metrics, you don't know whether your strategies are submitting orders, getting rejected, or stuck in cooldown until you check the UI. The dozen Prometheus metrics give you the dashboard.
- **Lost state on disk failure.** Daily backups + 30-day retention means the worst case is "lose one trading day's audit, restore from yesterday."
- **The 3am failure.** The on-call playbook is the durable place for "the symptoms are X, the cause is usually Y, the fix is Z." Future-you reading the playbook at 3am will thank present-you for writing it now.

Load-bearing assertion: **the full P1-§7 smoke is byte-identical.** §8 adds observability and durability surface area without changing any order-routing behavior.

---

## Session Goal

After this session:

- **Immutable audit log.** DB triggers `audit_log_no_update` and `audit_log_no_delete` raise on any UPDATE/DELETE attempt. New script `scripts/verify_audit_integrity.py` checks every row's `prev_hash` chains to its predecessor (SHA-256 of canonical row representation). New `audit_log.row_hash` and `audit_log.prev_hash` columns populated on insert by application code (the only path that writes to audit_log).

- **`/healthz` endpoint** at `GET /healthz` (unauthenticated, intentionally — load balancers and monitors need to hit it). Returns:
  ```json
  {
    "status": "ok",                    // "ok" | "degraded" | "fail"
    "checks": {
      "database": "ok",
      "master_key": "ok",
      "broker_registry": "ok",         // ≥1 adapter loaded, or "no_accounts" (still ok)
      "scheduler": "ok",                // last_run_at within 2× interval
      "circuit_breakers_clear": "degraded" // any account tripped
    },
    "version": "p5-session8-complete",
    "uptime_seconds": 12345
  }
  ```
  HTTP 200 if status=ok or degraded; 503 if status=fail. The distinction: degraded means "trading may be impaired" (e.g., a breaker tripped); fail means "the system can't serve traffic" (e.g., DB unreachable).

- **`/metrics` endpoint** at `GET /metrics` (unauthenticated; bound to 127.0.0.1 only via the docker-compose binding from P0). Returns Prometheus exposition format with twelve metrics:
  - `workbench_orders_submitted_total{outcome, account_mode, source}` — counter
  - `workbench_live_orders_submitted_total{outcome}` — counter (subset of above, surfaced separately for alerting)
  - `workbench_strategies_active{status}` — gauge by status
  - `workbench_strategies_in_cooldown` — gauge
  - `workbench_circuit_breakers_tripped` — gauge
  - `workbench_pending_live_strategies` — gauge
  - `workbench_background_job_last_run_seconds{job}` — gauge (seconds since last successful run)
  - `workbench_credential_stale_seconds{kind}` — gauge (seconds since last credential rotation, per kind)
  - `workbench_order_submission_duration_seconds{outcome}` — histogram
  - `workbench_broker_api_errors_total{adapter, operation}` — counter
  - `workbench_auth_failures_total{reason}` — counter
  - `workbench_audit_log_rows_total` — gauge (sanity check on growth)

- **Structured log redaction.** A processor injected into structlog filters every log entry for known credential patterns (`PKLIVE...`, `sk-ant-...`, Fernet tokens) and replaces them with `[REDACTED:kind]`. New module `app/observability/redact.py`. Test coverage: every credential kind from §4 is detected and redacted.

- **Daily SQLite backup.** New script `scripts/backup_db.sh` uses SQLite's `.backup` command (atomic, WAL-aware) to write `data/backups/workbench-YYYY-MM-DD.sqlite`. Daily APScheduler job runs at 02:00 local time. 30-day retention; older backups deleted in the same pass. New `scripts/restore_db.sh` documents the manual restore procedure.

- **Deployment runbook** at `docs/runbook/deployment.md` — fresh-box procedure from clone → first paper order. Covers: prereqs (docker, master key generation), `.env` config, first user creation, paper-credentials setup, paper smoke validation. ≤ 60 minutes wall-time on a competent operator.

- **On-call playbook** at `docs/runbook/on-call.md` — the dozen common failure modes from §1-§7 with symptom / cause / fix. Built to be skimmed at 3am.

- **Final P5 verification (§8.10)** — exhaustive cross-session smoke that validates every gate from §1-§7 fires correctly. The procedure that produces the durable "P5 is complete" signal.

- **`git tag p5-complete`** after §8.10 passes. The phase is closed.

What does NOT happen this session:

- **No TLS.** The workbench binds to 127.0.0.1 (per P0 docker-compose config). External access goes through a reverse proxy (Caddy, nginx) that you configure on the host. The runbook mentions this but doesn't ship config.
- **No multi-instance HA.** Single-host, single-instance. APScheduler is in-process. Adding a second instance would require Postgres + an external job lock (P5+ polish if real workloads demand it).
- **No external metric storage.** `/metrics` exposes Prometheus exposition format; you run Prometheus / Grafana / whatever externally. The workbench doesn't ship them.
- **No PagerDuty integration.** The on-call playbook is a doc. Pager rotation is up to the operator (you).

---

## Prerequisites Check

```powershell
# from repo root; uv is not on PATH — use the venv python
cd C:\LLM-RAG-APP\ai-trading-app
git checkout main; git pull origin main
git describe --tags --abbrev=0           # expect: p5-session7-complete

# All 5 shell CI invariants pass (post-Session 7 inventory)
bash apps/backend/scripts/check_strategy_isolation.sh
bash apps/backend/scripts/check_mcp_readonly.sh
bash apps/backend/scripts/check_no_llm_in_order_path.sh
bash apps/backend/scripts/check_broker_isolation.sh
bash apps/backend/scripts/check_no_env_credentials.sh

# Three coverage gates
.\apps\backend\.venv\Scripts\python.exe apps\backend\scripts\check_risk_coverage.py
.\apps\backend\.venv\Scripts\python.exe apps\backend\scripts\check_p2_coverage.py
.\apps\backend\.venv\Scripts\python.exe apps\backend\scripts\check_p3_coverage.py

# ADR 0002 + existing audit-immutability pytest invariants (Session 7 baseline)
cd apps\backend
.\.venv\Scripts\python.exe -m pytest tests/test_adr_0002_invariant.py -q
# Find and run the existing audit-immutability test (added pre-§8 per Session 7
# Results). Likely path:
.\.venv\Scripts\python.exe -m pytest -q -k "audit_immutab"

# Baseline backend suite green
.\.venv\Scripts\python.exe -m pytest -q --cov=app --cov-branch --cov-report=xml
cd ..\..

# Verify SQLite is in WAL mode (Session 2 v1.0 default)
cd apps\backend
.\.venv\Scripts\python.exe -c "import sqlite3; c=sqlite3.connect(r'data\workbench.sqlite'); print(c.execute('PRAGMA journal_mode').fetchone())"
# Expect: ('wal',)

# Confirm prometheus_client status
findstr /R "prometheus" pyproject.toml
# It MAY already be present (Session 5 Results notes structlog + prometheus_client
# in the stack). If absent, add it: .\.venv\Scripts\python.exe -m pip install prometheus_client
# and update pyproject.toml.

# Verify audit_log table and that the 5 UPPER P5 audit actions have rows in dev
.\.venv\Scripts\python.exe -c "import sqlite3; c=sqlite3.connect(r'data\workbench.sqlite'); print(c.execute('SELECT count(*) FROM audit_log').fetchone())"
.\.venv\Scripts\python.exe -c "import sqlite3; c=sqlite3.connect(r'data\workbench.sqlite'); print(list(c.execute('SELECT DISTINCT action FROM audit_log ORDER BY action')))"

# Confirm app/audit/logger.py exists (NOT app/services/audit_log.py — Session 5+ pattern)
dir app\audit\logger.py
# Expect: file exists

# Confirm app/utils/time.py::ensure_aware exists (Session 5 §5.0)
findstr /S /R "ensure_aware" app\utils\time.py
# Expect: matches

cd ..\..
```

Live runtime gates are **deferred** per the standing Norton SSL + no-Docker posture. The in-suite tests in §8.8 stand in for the load-bearing assertions; the live diff runs in WSL/CI before the tag is promoted to a release.

```bash
git checkout -b feat/p5-session8-production-hardening
```

- [ ] On `main`, at `p5-session7-complete`.
- [ ] All 5 shell invariants + ADR 0002 + existing audit-immutability pytest green.
- [ ] Three coverage gates pass.
- [ ] Baseline backend suite green.
- [ ] SQLite in WAL mode.
- [ ] `prometheus_client` available (or scheduled to be added).
- [ ] `app/audit/logger.py` exists.
- [ ] `app/utils/time.py::ensure_aware` exists.

---

## §8.1 — Immutable Audit Log

The audit_log table is the durable record of every consequential action. After §8, no code path — including bugs in future PRs — can mutate or delete its rows.

### 8.1.1 — Hash Chain Columns

Edit `apps/backend/app/db/models/audit_log.py`. Add two columns:

```python
# Self-hash: SHA-256 over canonical row representation. Computed and
# written by AuditLogger.write. Used by verify_audit_integrity.py to
# detect tampering.
row_hash: Mapped[str] = mapped_column(String(64), nullable=False, default="")

# Previous-row hash: the row_hash of the previous row in this user's
# audit chain. Chains form a per-user linked list — if a row is deleted
# or reordered, the chain breaks.
prev_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
```

> **Why per-user chains, not a global chain?** With a global chain, every insert is a serialization point (you must read the latest row's hash to compute the new prev_hash). Per-user chains parallelize by user. In single-user MVP this doesn't matter, but the schema accommodates multi-user.

### 8.1.2 — Migration

```bash
cd apps/backend
.\.venv\Scripts\python.exe -m alembic revision --autogenerate -m "P5: audit_log immutability — row_hash + triggers"
```

Open the migration. Add the columns AND the triggers:

```python
"""P5: audit_log immutability — row_hash + triggers

Revision ID: <generated>
"""
from alembic import op
import sqlalchemy as sa


def upgrade():
    # Columns
    op.add_column("audit_log", sa.Column("row_hash", sa.String(64), nullable=False, server_default=""))
    op.add_column("audit_log", sa.Column("prev_hash", sa.String(64), nullable=True))

    # Backfill row_hash for existing rows — see §8.1.4 for the algorithm.
    # We do this as a one-shot Python op (not raw SQL) because hashing is
    # not natively available in SQLite without an extension.
    from app.observability.audit_hash import compute_row_hash_for_backfill
    conn = op.get_bind()
    rows = conn.execute(sa.text(
        "SELECT id, user_id, actor_type, actor_id, action, "
        "target_type, target_id, payload, created_at "
        "FROM audit_log ORDER BY id"
    )).fetchall()
    per_user_prev: dict[int, str | None] = {}
    for row in rows:
        prev_hash = per_user_prev.get(row.user_id)
        row_hash = compute_row_hash_for_backfill(row, prev_hash=prev_hash)
        conn.execute(sa.text(
            "UPDATE audit_log SET row_hash=:rh, prev_hash=:ph WHERE id=:id"
        ), {"rh": row_hash, "ph": prev_hash, "id": row.id})
        per_user_prev[row.user_id] = row_hash

    # Drop the temporary server_default now that all rows have a real hash
    with op.batch_alter_table("audit_log") as batch:
        batch.alter_column("row_hash", server_default=None)

    # Triggers — block UPDATE and DELETE on audit_log.
    # SQLite triggers can RAISE to abort the operation.
    op.execute("""
        CREATE TRIGGER audit_log_no_update
        BEFORE UPDATE ON audit_log
        BEGIN
            SELECT RAISE(ABORT, 'audit_log is append-only; UPDATE forbidden');
        END;
    """)
    op.execute("""
        CREATE TRIGGER audit_log_no_delete
        BEFORE DELETE ON audit_log
        BEGIN
            SELECT RAISE(ABORT, 'audit_log is append-only; DELETE forbidden');
        END;
    """)


def downgrade():
    op.execute("DROP TRIGGER IF EXISTS audit_log_no_update;")
    op.execute("DROP TRIGGER IF EXISTS audit_log_no_delete;")
    with op.batch_alter_table("audit_log") as batch:
        batch.drop_column("prev_hash")
        batch.drop_column("row_hash")
```

> **Side effect of the triggers**: existing tests that wipe audit_log via DELETE will start failing. The §8.1.5 fixture handles this by disabling the trigger inside test fixtures.

### 8.1.3 — Hash Module

Create `apps/backend/app/observability/audit_hash.py`:

```python
"""SHA-256 hash chain for audit_log rows.

The hash is over a canonical JSON representation of the row plus the
previous row's hash. Any change to a row, any reordering, any insertion
of a forged row breaks the chain — verify_audit_integrity.py detects this.

Canonical form: JSON with sort_keys=True, separators=(",", ":"), no spaces.
Decimals serialized via str(). Datetimes via isoformat().
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime
from decimal import Decimal
from typing import Any, Optional


def _canonicalize(value: Any) -> Any:
    """Recursively convert non-JSON-native types to canonical strings."""
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, dict):
        return {k: _canonicalize(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_canonicalize(v) for v in value]
    return value


def compute_row_hash(
    *,
    id: int,
    user_id: Optional[int],
    actor_type: str,
    actor_id: str,
    action: str,
    target_type: Optional[str],
    target_id: Optional[int],
    payload: dict,
    created_at: datetime,
    prev_hash: Optional[str],
) -> str:
    """Compute SHA-256 over the canonical representation.

    The id is included — re-inserting a row at a different id would
    produce a different hash, so identity matters."""
    canonical = {
        "id": id,
        "user_id": user_id,
        "actor_type": actor_type,
        "actor_id": actor_id,
        "action": action,
        "target_type": target_type,
        "target_id": target_id,
        "payload": _canonicalize(payload),
        "created_at": created_at.isoformat(),
        "prev_hash": prev_hash or "",
    }
    serialized = json.dumps(canonical, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def compute_row_hash_for_backfill(row, *, prev_hash: Optional[str]) -> str:
    """SQLAlchemy Row-compatible variant for the migration backfill.
    Handles JSON column stored as text."""
    payload = row.payload
    if isinstance(payload, str):
        payload = json.loads(payload)
    # SQLite returns created_at as a string; coerce.
    created_at = row.created_at
    if isinstance(created_at, str):
        created_at = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
    return compute_row_hash(
        id=row.id,
        user_id=row.user_id,
        actor_type=row.actor_type,
        actor_id=row.actor_id,
        action=row.action,
        target_type=row.target_type,
        target_id=row.target_id,
        payload=payload or {},
        created_at=created_at,
        prev_hash=prev_hash,
    )
```

### 8.1.4 — `AuditLogger` Writes Hashes

Edit `apps/backend/app/audit/logger.py`. `AuditLogger.write()` is the existing **sync** API (Session 5 Results: "AuditLogger is sync, in `app.audit`"). The hash chain integration adds a `prev_hash` lookup and a precomputed `row_hash` via raw SQL INSERT.

> **Why raw SQL INSERT instead of ORM add + flush + update?** The DB triggers added in §8.1.2 block UPDATE on `audit_log`. The ORM pattern of "insert then update row_hash with the assigned id" would trip the trigger. The fix: compute the next id atomically via `(SELECT COALESCE(MAX(id), 0) + 1 FROM audit_log)`, hash against that id BEFORE the INSERT, then INSERT with the hash already filled in. SQLite WAL serializes writers, so the MAX+1 race window is zero. (If we ever swap to Postgres, switch to a sequence + advisory lock; the runbook records this.)

```python
import json
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import desc, select, text
from sqlalchemy.orm import Session

from app.db.models.audit_log import AuditLog
from app.observability.audit_hash import compute_row_hash


class AuditLogger:
    @staticmethod
    def write(
        session: Session,
        *,
        actor_type: Any,
        actor_id: Optional[str] = None,
        action: Any,
        target_type: Optional[str] = None,
        target_id: Optional[int] = None,
        payload: Optional[dict] = None,
        user_id: Optional[int] = None,
    ) -> None:
        """Append-only insert with hash chain (sync).

        Atomic write: precomputes row_hash against (MAX(id) + 1) and
        INSERTs in a single statement. SQLite WAL serializes writers,
        so the MAX+1 race window is zero.

        Caller is responsible for committing the session (Session 5
        deviation: AuditLogger.write does not commit; the calling
        service decides transaction boundaries).
        """
        now = datetime.now(timezone.utc)
        actor_type_str = (
            actor_type.value if hasattr(actor_type, "value") else str(actor_type)
        )
        action_str = (
            action.value if hasattr(action, "value") else str(action)
        )
        payload_dict = payload or {}

        # Look up previous hash for this user (None for first row).
        prev_hash: Optional[str] = None
        if user_id is not None:
            prev_hash = session.execute(
                select(AuditLog.row_hash)
                .where(AuditLog.user_id == user_id)
                .order_by(desc(AuditLog.id))
                .limit(1)
            ).scalar_one_or_none()

        # Atomically: get next id, hash against it, INSERT in one statement.
        next_id = session.execute(
            text("SELECT COALESCE(MAX(id), 0) + 1 FROM audit_log")
        ).scalar()

        row_hash = compute_row_hash(
            id=next_id, user_id=user_id,
            actor_type=actor_type_str, actor_id=actor_id,
            action=action_str, target_type=target_type, target_id=target_id,
            payload=payload_dict, created_at=now, prev_hash=prev_hash,
        )

        session.execute(text(
            "INSERT INTO audit_log "
            "(id, user_id, actor_type, actor_id, action, target_type, "
            " target_id, payload, created_at, row_hash, prev_hash) "
            "VALUES (:id, :user_id, :actor_type, :actor_id, :action, "
            " :target_type, :target_id, :payload, :created_at, :row_hash, :prev_hash)"
        ), {
            "id": next_id, "user_id": user_id,
            "actor_type": actor_type_str, "actor_id": actor_id,
            "action": action_str, "target_type": target_type,
            "target_id": target_id, "payload": json.dumps(payload_dict),
            "created_at": now.isoformat(), "row_hash": row_hash,
            "prev_hash": prev_hash,
        })
```

**Verify before relying on this code**: read the actual `AuditLogger.write()` signature in `app/audit/logger.py`. The parameter list above matches what Sessions 5, 6, 7 call (`actor_type`, `actor_id`, `action`, `target_type`, `target_id`, `payload`, `user_id`). If the current code uses different parameter names or accepts an `AsyncSession`, adjust accordingly. Notes & Gotchas #22 calls this out.

> **The MAX(id)+1 approach has a theoretical race with concurrent inserts.** In SQLite with WAL mode (Session 2 v1.0 confirmed WAL is on), write transactions are serialized — only one writer at a time. So the race window is zero. If we ever swap to Postgres, this becomes a hot-spot and we'd switch to a sequence + advisory lock pattern; documented in the deployment runbook.

### 8.1.5 — Test Fixture Adjustment

Existing test fixtures that wipe `audit_log` between tests will now hit the trigger. Edit `apps/backend/tests/conftest.py`:

```python
@pytest.fixture(autouse=True)
async def reset_audit_log(session_factory):
    """Disable audit_log triggers for the duration of the test, wipe the
    table, restore the triggers. This is the only legitimate path to
    bypass the triggers — and it's confined to test setup.

    NEVER do this in production code paths. The grep-check in §8.1.6
    enforces."""
    from sqlalchemy import text
    async with session_factory() as session:
        await session.execute(text("DROP TRIGGER IF EXISTS audit_log_no_delete"))
        await session.execute(text("DROP TRIGGER IF EXISTS audit_log_no_update"))
        await session.execute(text("DELETE FROM audit_log"))
        await session.execute(text(
            "CREATE TRIGGER audit_log_no_update BEFORE UPDATE ON audit_log "
            "BEGIN SELECT RAISE(ABORT, 'audit_log is append-only; UPDATE forbidden'); END;"
        ))
        await session.execute(text(
            "CREATE TRIGGER audit_log_no_delete BEFORE DELETE ON audit_log "
            "BEGIN SELECT RAISE(ABORT, 'audit_log is append-only; DELETE forbidden'); END;"
        ))
        await session.commit()
    yield
```

### 8.1.6 — CI Invariant: No Trigger Drops in Production Code

Create `apps/backend/scripts/check_audit_immutability.sh`:

```bash
#!/bin/bash
# P5 §8 invariant: no production code path drops the audit_log triggers
# or executes UPDATE/DELETE against audit_log directly. The triggers are
# the storage-layer enforcement; this script catches the application-layer
# attempts.
#
# Allowed locations:
#  - apps/backend/alembic/versions/ (the migration itself)
#  - apps/backend/tests/conftest.py (test fixture; covered by §8.1.5)

set -e

ROOT="apps/backend"

# Patterns we forbid
PATTERNS=(
    "DROP TRIGGER.*audit_log"
    "UPDATE audit_log"
    "DELETE FROM audit_log"
)

VIOLATIONS=""
for pattern in "${PATTERNS[@]}"; do
    found=$(find "$ROOT/app" -name "*.py" -exec grep -lE "$pattern" {} \; 2>/dev/null || true)
    if [ -n "$found" ]; then
        VIOLATIONS+="${found}\n"
    fi
done

if [ -n "$VIOLATIONS" ]; then
    echo "ERROR: production code touches audit_log via UPDATE/DELETE or drops its triggers."
    echo ""
    echo -e "$VIOLATIONS"
    echo ""
    echo "audit_log is append-only. Use AuditLogger.write() to add rows."
    echo "If you genuinely need to bypass for a one-off migration, do it in"
    echo "alembic/versions/ with an ADR explaining why."
    exit 1
fi

echo "Audit immutability invariant OK"
exit 0
```

```bash
chmod +x apps/backend/scripts/check_audit_immutability.sh
bash apps/backend/scripts/check_audit_immutability.sh
# Expect: "Audit immutability invariant OK"
```

Wire into `.github/workflows/ci.yml`:

```yaml
      - name: Audit immutability invariant
        run: bash apps/backend/scripts/check_audit_immutability.sh
```

This becomes the **ninth** CI invariant.

### 8.1.7 — Integrity Verification Script

Create `apps/backend/scripts/verify_audit_integrity.py`:

```python
"""Walk every audit_log row in id order; verify row_hash matches the
computed canonical hash AND prev_hash matches the previous row in the
same user's chain.

Run on a schedule (cron / GitHub Action) against a DB backup OR live.
Failure modes:
  - "row_hash mismatch on row X": that row was modified after insert.
  - "prev_hash mismatch on row X": a row was inserted/removed between X
    and its predecessor in the user's chain.
  - "first row for user N has non-null prev_hash": chain start corrupted.

Exit codes:
  0 — all chains intact.
  1 — at least one chain corrupted (details on stderr).
"""
from __future__ import annotations

import sys
from pathlib import Path

# Make app importable
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.observability.audit_hash import compute_row_hash
import sqlite3
import json
from datetime import datetime


def verify(db_path: str) -> int:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cur = conn.execute("""
        SELECT id, user_id, actor_type, actor_id, action,
               target_type, target_id, payload, created_at,
               row_hash, prev_hash
        FROM audit_log
        ORDER BY id
    """)
    per_user_last: dict[int, str | None] = {}
    errors = 0
    total = 0
    for row in cur:
        total += 1
        expected_prev = per_user_last.get(row["user_id"])

        # Check prev_hash matches our chain
        if (row["prev_hash"] or None) != (expected_prev or None):
            print(
                f"ERROR row {row['id']}: prev_hash mismatch. "
                f"Stored={row['prev_hash']!r}, expected={expected_prev!r}",
                file=sys.stderr,
            )
            errors += 1

        # Compute expected row_hash
        payload = row["payload"]
        if isinstance(payload, str):
            payload = json.loads(payload) if payload else {}
        elif payload is None:
            payload = {}
        created_at = row["created_at"]
        if isinstance(created_at, str):
            created_at = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
        expected_hash = compute_row_hash(
            id=row["id"], user_id=row["user_id"],
            actor_type=row["actor_type"], actor_id=row["actor_id"],
            action=row["action"], target_type=row["target_type"],
            target_id=row["target_id"], payload=payload,
            created_at=created_at, prev_hash=row["prev_hash"],
        )
        if row["row_hash"] != expected_hash:
            print(
                f"ERROR row {row['id']}: row_hash mismatch. "
                f"Stored={row['row_hash']}, computed={expected_hash}",
                file=sys.stderr,
            )
            errors += 1

        per_user_last[row["user_id"]] = row["row_hash"]

    print(f"Verified {total} rows; {errors} errors.")
    return 0 if errors == 0 else 1


if __name__ == "__main__":
    db = sys.argv[1] if len(sys.argv) > 1 else "data/workbench.sqlite"
    sys.exit(verify(db))
```

Run after migration to confirm clean state:

```bash
docker compose exec backend uv run python scripts/verify_audit_integrity.py
# Expect: "Verified N rows; 0 errors."
```

- [ ] row_hash + prev_hash columns added; migration backfills.
- [ ] DB triggers block UPDATE and DELETE.
- [ ] AuditLogger.write uses MAX(id)+1 pattern for atomic hash insert.
- [ ] check_audit_immutability.sh is the 9th invariant.
- [ ] verify_audit_integrity.py walks chains cleanly.

---

## §8.2 — `/healthz` Endpoint

Create `apps/backend/app/api/healthz.py`:

```python
"""Health check endpoint for load balancers and monitors.

DOES NOT require auth — health checks need to work before login is
possible, and exposing this is safe (no secrets; just status booleans).

Status levels:
  "ok"       — every subsystem reports healthy.
  "degraded" — trading is impaired but the system can serve traffic
               (e.g., a circuit breaker is tripped on some account).
  "fail"     — the system can't serve traffic safely (e.g., DB unreachable).

HTTP:
  200 — status ∈ {ok, degraded}.
  503 — status == fail.
"""
from __future__ import annotations

import time
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, Request, Response
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import async_session_factory


router = APIRouter(tags=["health"])


VERSION_TAG = "p5-session8-complete"
_BOOT_TIME = time.monotonic()


class HealthzResponse(BaseModel):
    status: str
    checks: dict[str, str]
    version: str
    uptime_seconds: int


@router.get("/healthz", response_model=HealthzResponse)
async def healthz(request: Request, response: Response) -> HealthzResponse:
    checks: dict[str, str] = {}
    overall = "ok"

    # 1. Database connectivity
    try:
        async with async_session_factory() as session:
            await session.execute(text("SELECT 1"))
        checks["database"] = "ok"
    except Exception as exc:
        checks["database"] = f"fail: {exc.__class__.__name__}"
        overall = "fail"

    # 2. Master key loaded
    try:
        from app.security.crypto import _get_fernet
        _get_fernet()    # raises if not loaded
        checks["master_key"] = "ok"
    except Exception:
        checks["master_key"] = "fail"
        overall = "fail"

    # 3. Broker registry has adapters (or no accounts yet — both OK)
    try:
        broker_registry = getattr(request.app.state, "broker_registry", None)
        if broker_registry is None:
            checks["broker_registry"] = "no_state"
            if overall != "fail":
                overall = "degraded"
        else:
            adapter_count = len(getattr(broker_registry, "_adapters", {}))
            # Confirm at least: that we have an accounts count
            async with async_session_factory() as session:
                from app.db.models.account import Account
                from sqlalchemy import func, select
                acc_count = (await session.execute(
                    select(func.count(Account.id))
                )).scalar()
            if acc_count == 0:
                checks["broker_registry"] = "no_accounts"  # OK — fresh install
            elif adapter_count == 0:
                checks["broker_registry"] = "fail: accounts exist but no adapters"
                overall = "fail"
            else:
                checks["broker_registry"] = "ok"
    except Exception as exc:
        checks["broker_registry"] = f"fail: {exc.__class__.__name__}"
        overall = "fail"

    # 4. Background scheduler healthy
    try:
        scheduler = getattr(request.app.state, "scheduler", None)
        if scheduler is None or not getattr(scheduler, "running", False):
            checks["scheduler"] = "fail: not running"
            overall = "fail"
        else:
            checks["scheduler"] = "ok"
    except Exception as exc:
        checks["scheduler"] = f"fail: {exc.__class__.__name__}"
        overall = "fail"

    # 5. Circuit breakers — degraded (not fail) if any tripped
    try:
        async with async_session_factory() as session:
            from app.db.models.account import Account
            from sqlalchemy import func, select
            tripped_count = (await session.execute(
                select(func.count(Account.id))
                .where(Account.circuit_breaker_tripped_at.isnot(None))
            )).scalar() or 0
        if tripped_count > 0:
            checks["circuit_breakers_clear"] = f"degraded: {tripped_count} tripped"
            if overall == "ok":
                overall = "degraded"
        else:
            checks["circuit_breakers_clear"] = "ok"
    except Exception:
        # Don't fail the health check just because we couldn't read this
        checks["circuit_breakers_clear"] = "unknown"

    if overall == "fail":
        response.status_code = 503

    return HealthzResponse(
        status=overall,
        checks=checks,
        version=VERSION_TAG,
        uptime_seconds=int(time.monotonic() - _BOOT_TIME),
    )
```

Mount in `apps/backend/app/main.py`:

```python
from app.api import healthz as healthz_router
app.include_router(healthz_router.router)    # NOT under /api/v1 — orchestrators expect /healthz
```

> **Why no auth on healthz?** Load balancers, monitors, and container orchestrators (docker-compose, Kubernetes) need to probe health without credentials. The endpoint exposes booleans and counts, not actual data. The 127.0.0.1 binding from P0 means external access requires going through your reverse proxy, which can choose to expose `/healthz` or not.

- [ ] Five subsystem checks: database, master_key, broker_registry, scheduler, circuit_breakers_clear.
- [ ] Returns 503 only if overall=fail.
- [ ] Mounted at `/healthz` (not `/api/v1/healthz`).

---

## §8.3 — `/metrics` Endpoint

Create `apps/backend/app/observability/metrics.py`:

```python
"""Prometheus metrics. Exposed at /metrics on the backend.

Twelve metrics chosen so that the operator can answer the questions
they'll actually ask:
  - "Is trading happening?" (orders submitted total)
  - "Is it going to LIVE?" (live orders submitted total)
  - "What's my current activity?" (strategies active by status)
  - "Is anything stuck?" (cooldown, breaker, pending live counts)
  - "Are my background jobs running?" (job last_run timestamps)
  - "Have my credentials been rotated recently?" (credential staleness)
  - "How fast is order submission?" (duration histogram)
  - "Is the broker flaky?" (broker api errors)
  - "Is anyone trying to break in?" (auth failures)
  - "Is the audit log growing as expected?" (row count)
"""
from __future__ import annotations

from prometheus_client import (
    Counter, Gauge, Histogram, generate_latest,
    CONTENT_TYPE_LATEST,
)


# ============================================================
# Counters
# ============================================================

orders_submitted_total = Counter(
    "workbench_orders_submitted_total",
    "Total orders submitted, by outcome, mode, source",
    labelnames=["outcome", "account_mode", "source"],
)

live_orders_submitted_total = Counter(
    "workbench_live_orders_submitted_total",
    "LIVE orders submitted (subset surfaced separately for alerting)",
    labelnames=["outcome"],
)

broker_api_errors_total = Counter(
    "workbench_broker_api_errors_total",
    "Errors from broker adapter calls",
    labelnames=["adapter", "operation"],
)

auth_failures_total = Counter(
    "workbench_auth_failures_total",
    "Authentication failures by reason",
    labelnames=["reason"],
)


# ============================================================
# Gauges (snapshotted by a periodic job; see §8.3.2)
# ============================================================

strategies_active = Gauge(
    "workbench_strategies_active",
    "Active strategies by status",
    labelnames=["status"],
)

strategies_in_cooldown = Gauge(
    "workbench_strategies_in_cooldown",
    "Strategies currently in §6 cooldown",
)

circuit_breakers_tripped = Gauge(
    "workbench_circuit_breakers_tripped",
    "Accounts with circuit breaker currently tripped",
)

pending_live_strategies = Gauge(
    "workbench_pending_live_strategies",
    "Strategies in PENDING_LIVE (within 24h activation cooldown)",
)

background_job_last_run_seconds = Gauge(
    "workbench_background_job_last_run_seconds",
    "Seconds since last successful run of background job",
    labelnames=["job"],
)

credential_stale_seconds = Gauge(
    "workbench_credential_stale_seconds",
    "Seconds since last rotation of credential, per kind",
    labelnames=["kind"],
)

audit_log_rows_total = Gauge(
    "workbench_audit_log_rows_total",
    "Total rows in audit_log (sanity check on growth)",
)


# ============================================================
# Histograms
# ============================================================

order_submission_duration_seconds = Histogram(
    "workbench_order_submission_duration_seconds",
    "Order submission duration",
    labelnames=["outcome"],
    buckets=(0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0),
)


def render() -> tuple[bytes, str]:
    """Render the registry as Prometheus exposition format."""
    return generate_latest(), CONTENT_TYPE_LATEST
```

Create `apps/backend/app/api/metrics.py`:

```python
"""Prometheus /metrics endpoint."""
from fastapi import APIRouter, Response

from app.observability.metrics import render


router = APIRouter(tags=["metrics"])


@router.get("/metrics")
async def metrics():
    body, content_type = render()
    return Response(content=body, media_type=content_type)
```

Mount alongside healthz in `main.py`:

```python
from app.api import metrics as metrics_router
app.include_router(metrics_router.router)    # GET /metrics
```

### 8.3.1 — Wire Up the Counters

The counters fire from the existing code paths. Edit `apps/backend/app/services/order_router.py`:

```python
from app.observability import metrics as obs


# In submit(), wrap the broker call with a Histogram timer:
import time
start = time.monotonic()
# ... submit logic ...
finally:
    duration = time.monotonic() - start
    obs.order_submission_duration_seconds.labels(
        outcome=outcome.status.value,
    ).observe(duration)
    obs.orders_submitted_total.labels(
        outcome=outcome.status.value,
        account_mode=account.mode.value,
        source=request.source.value,
    ).inc()
    if account.mode == AccountMode.live:
        obs.live_orders_submitted_total.labels(
            outcome=outcome.status.value,
        ).inc()
```

Edit `apps/backend/app/api/v1/auth.py` to increment `auth_failures_total` on each rejection (with `reason` ∈ `{bad_password, bad_totp, rate_limited, no_totp_enrolled}`).

Edit `apps/backend/app/brokers/alpaca_*.py` to increment `broker_api_errors_total` on exceptions in adapter methods.

### 8.3.2 — Snapshot Job for Gauges

Gauges need periodic snapshotting. Create `apps/backend/app/jobs/metrics_snapshot.py`:

```python
"""Snapshot gauge values from the DB. Runs every 30s."""
from __future__ import annotations

from datetime import datetime, timezone

import structlog
from sqlalchemy import func, select

from app.db.enums import StrategyStatus
from app.db.models.account import Account
from app.db.models.audit_log import AuditLog
from app.db.models.strategy import Strategy
from app.db.models.user_credential import UserCredential
from app.observability import metrics as obs


logger = structlog.get_logger(__name__)


async def run_metrics_snapshot(session_factory) -> None:
    async with session_factory() as session:
        # strategies_active by status
        rows = (await session.execute(
            select(Strategy.status, func.count(Strategy.id))
            .group_by(Strategy.status)
        )).all()
        # Reset all known statuses to 0 so transitions away from a status
        # don't leave a stale gauge value.
        for s in StrategyStatus:
            obs.strategies_active.labels(status=s.value).set(0)
        for status, count in rows:
            obs.strategies_active.labels(status=status).set(count)

        # in_cooldown
        cd = (await session.execute(
            select(func.count(Strategy.id))
            .where(Strategy.cooldown_until.isnot(None))
            .where(Strategy.cooldown_until > datetime.now(timezone.utc))
        )).scalar() or 0
        obs.strategies_in_cooldown.set(cd)

        # circuit_breakers_tripped
        cb = (await session.execute(
            select(func.count(Account.id))
            .where(Account.circuit_breaker_tripped_at.isnot(None))
        )).scalar() or 0
        obs.circuit_breakers_tripped.set(cb)

        # pending_live
        pl = (await session.execute(
            select(func.count(Strategy.id))
            .where(Strategy.status == StrategyStatus.PENDING_LIVE)
        )).scalar() or 0
        obs.pending_live_strategies.set(pl)

        # audit_log_rows_total
        al = (await session.execute(
            select(func.count(AuditLog.id))
        )).scalar() or 0
        obs.audit_log_rows_total.set(al)

        # credential_stale_seconds per kind
        creds = (await session.execute(
            select(UserCredential.kind, func.max(UserCredential.updated_at))
            .where(UserCredential.revoked_at.is_(None))
            .group_by(UserCredential.kind)
        )).all()
        now = datetime.now(timezone.utc)
        for kind, last_updated in creds:
            if last_updated is None:
                continue
            stale_seconds = (now - last_updated).total_seconds()
            obs.credential_stale_seconds.labels(kind=kind).set(stale_seconds)

    logger.debug("metrics_snapshot_complete")
```

Wire into `lifespan.py`:

```python
from app.jobs.metrics_snapshot import run_metrics_snapshot

scheduler.add_job(
    lambda: run_metrics_snapshot(app.state.session_factory),
    trigger="interval", seconds=30,
    id="metrics_snapshot",
    max_instances=1, coalesce=True,
)
```

The `background_job_last_run_seconds` gauge is updated by a small wrapper:

```python
def track_job(job_id: str, fn):
    async def wrapped():
        import time
        try:
            await fn()
        finally:
            obs.background_job_last_run_seconds.labels(job=job_id).set(0)
            # ... actually want elapsed since last successful, so set on success only ...
    return wrapped
```

Or simpler: each job ends with `obs.background_job_last_run_seconds.labels(job=...).set(0)` and a separate periodic snapshot increments all of them. Either pattern works; pick one and document it.

- [ ] Twelve Prometheus metrics defined.
- [ ] Order router emits counter + histogram on every submission.
- [ ] Auth failures + broker errors emit counters.
- [ ] Snapshot job populates gauges every 30s.

---

## §8.4 — Log Redaction

Create `apps/backend/app/observability/redact.py`:

```python
"""structlog processor that scrubs known credential patterns from log
entries before they reach stdout.

The patterns we recognize:
  - Fernet tokens (start with 'gAAAAA' — the encoded version byte)
  - Alpaca paper keys (start with 'PKTEST' or 'PK')
  - Alpaca live keys (start with 'PKLIVE')
  - Anthropic API keys (start with 'sk-ant-')
  - 32-character base32 strings (TOTP secrets are 16-32 chars base32)
  - Generic 'password=', 'secret=', 'api_key=' assignments

This is defense in depth, not the primary defense. Credentials should
never be passed to logger.* calls in the first place — but if a future
PR accidentally does, the redactor catches it.
"""
from __future__ import annotations

import re
from typing import Any


# Order matters: more specific patterns first.
PATTERNS: list[tuple[re.Pattern, str]] = [
    (re.compile(r"gAAAAA[A-Za-z0-9_\-=]{40,}"), "[REDACTED:fernet]"),
    (re.compile(r"sk-ant-[A-Za-z0-9_\-]{20,}"), "[REDACTED:anthropic]"),
    (re.compile(r"PKLIVE[A-Z0-9]{10,}"), "[REDACTED:alpaca_live]"),
    (re.compile(r"PKTEST[A-Z0-9]{10,}"), "[REDACTED:alpaca_paper]"),
    # Generic catch-all (last)
    (re.compile(
        r"(password|secret|api_key|api_secret|totp_secret|webhook_secret)\s*[=:]\s*['\"]?([A-Za-z0-9+/=_\-]{8,})['\"]?",
        re.IGNORECASE,
    ), r"\1=[REDACTED:generic]"),
]


def _redact_value(value: Any) -> Any:
    if isinstance(value, str):
        for pattern, replacement in PATTERNS:
            value = pattern.sub(replacement, value)
        return value
    if isinstance(value, dict):
        return {k: _redact_value(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_redact_value(v) for v in value]
    return value


def redact_processor(_logger, _method, event_dict):
    """structlog processor: redact known credential patterns from every
    field of every log event."""
    return {k: _redact_value(v) for k, v in event_dict.items()}
```

Wire into structlog config (in `apps/backend/app/lifespan.py` or wherever structlog is set up):

```python
import structlog
from app.observability.redact import redact_processor

structlog.configure(
    processors=[
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        redact_processor,    # NEW — must run before the renderer
        structlog.processors.JSONRenderer(),
    ],
    # ... rest of config ...
)
```

> **Why not redact in the renderer?** Putting it before the renderer means downstream processors (like `add_log_level`) don't accidentally re-expose redacted content. The closer to "the bytes leaving the process" the better; the closer to "the values being passed to the logger" is also good. Pre-render is a reasonable compromise.

- [ ] `redact.py` with 5 pattern families.
- [ ] Processor wired into structlog.
- [ ] Tests cover every kind from §4.

---

## §8.5 — Daily DB Backup

SQLite in WAL mode complicates `cp`-based backup: the .db file is a partial state until the WAL is checkpointed. The right approach is SQLite's `.backup` command, which produces an atomic snapshot regardless of in-flight transactions.

Create `scripts/backup_db.sh`:

```bash
#!/bin/bash
# Daily SQLite backup using the .backup command (atomic, WAL-safe).
# Output: data/backups/workbench-YYYY-MM-DD.sqlite
# Retention: 30 days; older backups are deleted in the same pass.

set -e

DB_PATH="${WORKBENCH_DB_PATH:-/app/data/workbench.sqlite}"
BACKUP_DIR="${WORKBENCH_BACKUP_DIR:-/app/data/backups}"
RETENTION_DAYS="${WORKBENCH_BACKUP_RETENTION_DAYS:-30}"

mkdir -p "$BACKUP_DIR"

TODAY=$(date -u +%Y-%m-%d)
TARGET="${BACKUP_DIR}/workbench-${TODAY}.sqlite"

if [ -f "$TARGET" ]; then
    echo "Backup for ${TODAY} already exists at ${TARGET} — skipping"
    exit 0
fi

# Atomic backup via SQLite's .backup command
sqlite3 "$DB_PATH" ".backup '${TARGET}'"

# Verify the backup is readable
sqlite3 "$TARGET" "PRAGMA integrity_check;" | head -1 | grep -q "^ok$" || {
    echo "ERROR: backup integrity check failed for ${TARGET}"
    rm -f "$TARGET"
    exit 1
}

# Prune older than retention
find "$BACKUP_DIR" -name "workbench-*.sqlite" -type f -mtime "+${RETENTION_DAYS}" -delete

# Print result
SIZE=$(stat -c%s "$TARGET" 2>/dev/null || stat -f%z "$TARGET" 2>/dev/null)
echo "Backup complete: ${TARGET} (${SIZE} bytes)"
exit 0
```

```bash
chmod +x scripts/backup_db.sh
```

Wire into the scheduler. Edit `apps/backend/app/lifespan.py`:

```python
import subprocess

async def run_daily_backup():
    """Run scripts/backup_db.sh — daily DB backup."""
    try:
        result = await asyncio.create_subprocess_exec(
            "/app/scripts/backup_db.sh",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await result.communicate()
        if result.returncode != 0:
            logger.error("daily_backup_failed",
                         returncode=result.returncode,
                         stderr=stderr.decode())
        else:
            logger.info("daily_backup_complete", stdout=stdout.decode().strip())
    except Exception:
        logger.exception("daily_backup_exception")


# In the lifespan startup block:
scheduler.add_job(
    run_daily_backup,
    trigger="cron", hour=2, minute=0,    # 02:00 daily
    id="daily_backup",
    max_instances=1, coalesce=True,
)
```

> **Cron at 02:00 local time, not UTC.** The reasoning: 02:00 in the operator's timezone is the operator's quietest hour. If the operator is across timezones (a deployment in EU servicing a US trader), use UTC. APScheduler's `cron` trigger uses the scheduler's configured timezone — set to UTC for unambiguity in the docker-compose config.

Create `scripts/restore_db.sh` for the documented restore procedure:

```bash
#!/bin/bash
# Manual restore from a backup.
#
# Usage: ./scripts/restore_db.sh <backup-path>
#
# This is destructive — overwrites the current DB. The backend MUST be
# stopped first. The script verifies the backend is down by checking
# /healthz; refuses to proceed if /healthz is reachable.

set -e

BACKUP="$1"
DB_PATH="${WORKBENCH_DB_PATH:-/app/data/workbench.sqlite}"

if [ -z "$BACKUP" ]; then
    echo "Usage: $0 <backup-path>"
    exit 1
fi
if [ ! -f "$BACKUP" ]; then
    echo "ERROR: backup not found at $BACKUP"
    exit 1
fi

# Verify backend is DOWN
if curl -s --max-time 2 http://127.0.0.1:8000/healthz >/dev/null 2>&1; then
    echo "ERROR: backend is running. Stop with 'docker compose stop backend' first."
    exit 1
fi

# Confirm
echo "About to restore $BACKUP → $DB_PATH"
echo "Current DB will be backed up to ${DB_PATH}.pre-restore-$(date -u +%s)"
read -p "Continue? [y/N] " yn
case "$yn" in
    [Yy]*) ;;
    *) echo "Aborted"; exit 0 ;;
esac

# Snapshot current DB
if [ -f "$DB_PATH" ]; then
    cp "$DB_PATH" "${DB_PATH}.pre-restore-$(date -u +%s)"
fi

# Restore via .backup (which works as a copy too) — preserves WAL state
sqlite3 "$BACKUP" ".backup '${DB_PATH}'"

# Verify
sqlite3 "$DB_PATH" "PRAGMA integrity_check;" | head -1 | grep -q "^ok$" || {
    echo "ERROR: restored DB failed integrity check"
    exit 1
}

# Verify audit chains
sqlite3 "$DB_PATH" "SELECT count(*) FROM audit_log;"
uv run --directory apps/backend python scripts/verify_audit_integrity.py "$DB_PATH"

echo "Restore complete. Start backend with 'docker compose up -d backend'."
```

```bash
chmod +x scripts/restore_db.sh
```

- [ ] backup_db.sh uses SQLite .backup; verifies integrity; prunes after 30d.
- [ ] Scheduled at 02:00 daily.
- [ ] restore_db.sh refuses to run while backend is up.

---

## §8.6 — Deployment Runbook

Create `docs/runbook/deployment.md`:

```markdown
# Deployment Runbook — Fresh Box

This runbook takes you from "fresh Linux box with docker" to "first
paper order successfully submitted" in roughly 60 minutes for a
competent operator. It is the operating manual for the workbench.

## Prerequisites

- Linux host (Ubuntu 22.04+ or equivalent). Tested on Ubuntu 24.04.
- Docker Engine 24+ with Compose plugin.
- 2 vCPU, 4GB RAM, 20GB disk minimum. The workbench is light, but
  Alpaca's market-data subscription buffers can spike memory briefly.
- Outbound network to:
    - api.alpaca.markets, paper-api.alpaca.markets (broker)
    - api.anthropic.com (agent, if used)
    - github.com, cdn.jsdelivr.net (TradingView assets)
- Inbound: 127.0.0.1:8000 (backend), 127.0.0.1:8765 (MCP), 127.0.0.1:5173 (dev only).
  For external access, terminate TLS at a reverse proxy (Caddy or nginx)
  that proxies to 127.0.0.1:8000. The workbench does NOT bind to public IPs.

## Step 1 — Clone

```bash
cd /opt
sudo git clone https://github.com/jayw04/AI-TRADING-APP.git workbench
sudo chown -R "$USER:$USER" workbench
cd workbench
git checkout p5-complete    # or p5-session8-complete during the bring-up
```

## Step 2 — Master Key

```bash
./scripts/generate_master_key.sh
```

Copy the output. Add to `.env` in the repo root:

```
WORKBENCH_MASTER_KEY=<paste here>
```

Verify `.env*` is gitignored:

```bash
grep -E "^\.env" .gitignore
```

Set restrictive permissions:

```bash
chmod 600 .env
```

> Loss of the master key + loss of the DB ≠ recoverable. Loss of the
> master key alone is recoverable (rotate; everyone must re-enter their
> credentials). See `docs/runbook/credentials.md` for the rotation
> procedure.

## Step 3 — Data Directory Permissions

```bash
mkdir -p data/backups
chmod 700 data
chmod 700 data/backups
```

The data directory contains the SQLite DB (with encrypted credentials)
and backups. 700 (owner-only access) is appropriate.

## Step 4 — Start

```bash
docker compose up -d
```

This brings up:
- backend (FastAPI + Python; binds 127.0.0.1:8000)
- mcp-server (binds 127.0.0.1:8765)
- frontend (Vite; binds 127.0.0.1:5173 in dev, or static-built in prod)

Tail the backend log to confirm clean boot:

```bash
docker compose logs -f backend
```

Expect:
```
crypto_master_key_verified
broker_registry_initialized adapters=0
scheduler_started jobs=...
```

If you see `master_key_missing` or `master_key_invalid`, your `.env` is
wrong. Check the value, restart.

## Step 5 — Verify `/healthz`

```bash
curl http://127.0.0.1:8000/healthz | jq
```

Expect:
```json
{
  "status": "degraded",
  "checks": {
    "database": "ok",
    "master_key": "ok",
    "broker_registry": "no_accounts",
    "scheduler": "ok",
    "circuit_breakers_clear": "ok"
  },
  ...
}
```

`degraded` is the expected starting state — no accounts created yet.

## Step 6 — First User

```bash
docker compose exec backend ./scripts/create_user.sh
```

Follow the prompts. You'll be given a TOTP secret (QR code + base32).
**Save the QR code or base32 secret in your authenticator app
immediately** — it won't be shown again. Then run the verification step
that the script asks for.

After this step, login at `http://127.0.0.1:5173` (or behind your
reverse proxy) uses `email + password + TOTP code`.

## Step 7 — Paper Credentials

Log in via the UI. Navigate to `Settings → Credentials`. Set:

- `Alpaca Paper API Key` — from https://app.alpaca.markets/paper/dashboard/overview
- `Alpaca Paper API Secret` — paired with the key.

Optional:
- `Anthropic API Key` — required if you'll use the agent (P3).
- `TradingView Pine Webhook Secret` — required if you'll use TV alerts (P4 §1).

## Step 8 — Paper Account

Navigate to `Settings → Accounts → Create account`. Use `mode=paper`,
broker=`alpaca`, label of your choice.

Refresh. `Healthz` should now return `status=ok` (with broker_registry=ok).

## Step 9 — Smoke Test

In the UI:
1. Navigate to the Trade page.
2. Select the paper account.
3. Enter `AAPL`, BUY, MARKET, qty=1, TIF=DAY.
4. Submit.

The order should accept (broker_order_id populated). Confirm in
`Orders` page.

If the order rejects, check the logs:

```bash
docker compose logs backend | tail -50
```

Common issues:
- `MAX_ORDERS_PER_DAY` — risk limit at default 200 paper. Adjust if hit.
- `INSUFFICIENT_BUYING_POWER` — paper accounts come with $100k default;
  if you've submitted many orders, your paper buying power may be low.
  Reset the paper account via Alpaca dashboard.

## Step 10 — Reverse Proxy (Production Only)

For external access, terminate TLS at a reverse proxy. Example Caddy:

```
workbench.example.com {
    reverse_proxy 127.0.0.1:8000
    # Frontend dev server: proxy /vite path to 5173 if running in dev;
    # in production, the frontend is statically built and served by backend.
}
```

The workbench's `/healthz` endpoint can be hit through the proxy or
directly via 127.0.0.1:8000 — both work.

## Step 11 — Backup Verification

After a day of running, verify backups are accumulating:

```bash
ls -la data/backups/
```

Expect one file per day, named `workbench-YYYY-MM-DD.sqlite`.

Test a restore against a throwaway path:

```bash
docker compose exec backend sqlite3 \
  "/app/data/backups/workbench-$(date -u +%Y-%m-%d).sqlite" \
  "SELECT count(*) FROM orders;"
```

If this returns a sensible count, your backup pipeline works.

## What you have now

- Backend serving on 127.0.0.1:8000 (or behind your reverse proxy)
- One user, with TOTP enrolled
- One paper account, with credentials configured
- Daily backups at 02:00 UTC
- All eight P5 CI invariants enforced by the codebase

Next steps depend on your use case — see:
- `docs/runbook/credentials.md` for credential lifecycle.
- `docs/runbook/risk-gates.md` for risk-limit tuning.
- `docs/runbook/activation.md` for the paper → live flow.
- `docs/runbook/on-call.md` for failure-mode triage.
```

- [ ] Runbook ≤ 60 minutes wall-time.
- [ ] Covers prereqs → first paper order.
- [ ] Mentions reverse-proxy pattern (without shipping config).

---

## §8.7 — On-Call Playbook

Create `docs/runbook/on-call.md`:

```markdown
# On-Call Playbook

Skim format. For each symptom: what's probably wrong, what to check
first, how to fix.

## "I can't log in"

**Symptom**: `POST /api/v1/auth/login` returns 401 or 429.

**Check**:
- 429 → rate limited. Wait 15 minutes (the §3 sliding window resets).
- 401 with `invalid credentials` → typo in password OR TOTP code expired.
- 401 with `rate limited` (in the body, not the status) → 60-min cooldown after 5 failures.
- Frontend error: cookies blocked by browser? Check Application → Cookies.

**Fix**:
- For TOTP drift: confirm authenticator app shows the correct code RIGHT NOW (codes rotate every 30s).
- For lost password: there is no password-reset flow in MVP. Reset directly in the DB:
  ```bash
  docker compose exec backend python -c "
  import asyncio, bcrypt
  from app.db.session import async_session_factory
  from app.db.models.user import User
  from sqlalchemy import update
  async def reset(email, new_pw):
      h = bcrypt.hashpw(new_pw.encode(), bcrypt.gensalt(rounds=12))
      async with async_session_factory() as s:
          await s.execute(update(User).where(User.email == email).values(password_hash=h.decode()))
          await s.commit()
  asyncio.run(reset('jay@example.com', 'newpassword'))
  "
  ```
- For lost TOTP: re-run `scripts/create_user.sh --reset-totp <email>` (if implemented) or update via SQL.

## "Healthz returns 503"

**Symptom**: `/healthz` → `{"status": "fail", ...}`.

**Check** which subsystem failed (the `checks` field).

**Fix**:
- `database=fail`: DB unreachable. `docker compose ps`. Restart backend.
- `master_key=fail`: `.env` corrupted or unset. Verify `WORKBENCH_MASTER_KEY` is set; restart.
- `broker_registry=fail`: accounts exist but adapters didn't load. Likely missing credentials. Set via Settings → Credentials. Restart backend (it re-loads on boot).
- `scheduler=fail`: APScheduler died. Restart backend.

## "Strategy in PENDING_LIVE for more than 25 hours"

**Symptom**: Strategy stuck in PENDING_LIVE; ActivationCountdown shows negative time.

**Check**:
- Scheduler running? `grep activation_completion /var/log/workbench/backend.log | tail -5`
- Should see `activation_completion_pass` messages every ~60s.

**Fix**:
- If the scheduler is dead: restart backend.
- If alive but the strategy is still stuck: run the job manually (see `docs/runbook/activation.md` § "Failure modes").

## "Circuit breaker keeps tripping"

**Symptom**: Same account's breaker trips repeatedly soon after reset.

**Check**:
- Daily PnL relative to `max_daily_loss`. The default LIVE limit is $500; if your real PnL volatility is higher, the limit is too tight.
- Look at the audit log payload from the trip: `realized_pnl_today`, `unrealized_pnl_now`, `net_pnl`. Is the algorithm actually losing, or is it false-positive on stale unrealized data?

**Fix**:
- If algo is genuinely losing: stop trading, debug the algo, only re-activate after a paper-trade validation.
- If the limit is too tight: edit at `Settings → Risk Limits → LIVE`. Audit-logged.
- If unrealized PnL is the issue (e.g., broker returns 0 because adapter is flaky): the breaker is over-counting. Check `broker_api_errors_total{adapter="alpaca",operation="get_positions"}` metric — if it's nonzero, fix the adapter issue first.

## "Strategy in cooldown but I want to retry NOW"

**Symptom**: Strategy stuck in 60s §6 cooldown.

**Fix**: Strategy detail page → CooldownIndicator → "Clear now" button.
Audit-logged.

Or:
```bash
curl -X POST -b /tmp/cookies.txt http://127.0.0.1:8000/api/v1/strategies/$ID/cooldown/clear
```

## "Live order rejected with CONFIRMATION_MISMATCH"

**Symptom**: Manual LIVE order rejected even though you typed the ticker.

**Check**:
- The typed text must equal the order's symbol (case-insensitive, whitespace stripped).
- "AAPL.US" ≠ "AAPL" — the dot is part of the ticker.

**Fix**: Re-submit with the exact symbol shown in the order form.

## "Orders are slow"

**Symptom**: `workbench_order_submission_duration_seconds` histogram p99 > 5s.

**Check**:
- `workbench_broker_api_errors_total` — is the broker flaky?
- Backend logs for repeated retries on broker calls.
- Network latency to api.alpaca.markets (`ping`, `curl -w '%{time_total}'`).

**Fix**:
- If broker side: there's not much to do beyond waiting it out. The §5 fail-open patterns mean buying-power check returns "sufficient" without the broker, so submission still works.
- If our side: profile the order_router and risk_engine code paths.

## "Audit log integrity check fails"

**Symptom**: `verify_audit_integrity.py` reports row_hash or prev_hash mismatches.

**Check**:
- WHEN was the corruption introduced? `git log` the migrations directory; look for recent audit_log-touching migrations.
- Was there a manual SQL update? Check shell history.

**Fix**:
- A failing chain doesn't break operations — the workbench continues to function.
- For forensic purposes, restore from the last known-good backup and replay activity from then.
- Determine the root cause before re-enabling triggers (the triggers fire on UPDATE — if a migration disabled them, look for that).

## "Backup didn't run last night"

**Symptom**: `data/backups/` missing today's file.

**Check**:
- `grep daily_backup /var/log/workbench/backend.log | tail -10`
- Did the scheduler fire? Did the script exit non-zero?

**Fix**:
- Run manually: `docker compose exec backend /app/scripts/backup_db.sh`
- If the manual run also fails, check disk space (`df -h /app/data`).
- If the script succeeds manually but not on schedule, check APScheduler health via `/healthz`.

## "Disk is filling up"

**Symptom**: Disk usage growing.

**Check** in order:
1. `du -sh data/*` — what's biggest?
2. `data/backups/` — should be ≤ 30 files. If more, retention prune isn't working.
3. `data/workbench.sqlite-wal` — large WAL means checkpoints aren't happening. Restart backend forces a checkpoint.
4. Logs (`/var/log/workbench/`) — rotate via logrotate, not in scope for the workbench.

**Fix**:
- Backups: delete oldest manually; check retention logic.
- WAL: restart backend; consider tuning `wal_autocheckpoint` PRAGMA.
- Logs: configure logrotate on the host.

## "I see an alert I don't recognize"

**Symptom**: A metric exceeds some threshold and you're paging on it.

**Check**: the metric name. The twelve metrics from §8.3 are documented
in `docs/runbook/metrics.md` (if you've set one up — beyond this runbook's scope).
Cross-reference with the alerting rules in your Prometheus config.

**Fix**: out of scope for this playbook — depends on the alert.
```

- [ ] Playbook covers the dozen common failure modes from §1-§7.
- [ ] Skim format: symptom / check / fix per scenario.

---

## §8.8 — Tests

Create `apps/backend/tests/observability/test_p5_audit_immutability.py`:

```python
"""Verify the audit_log triggers actually block UPDATE/DELETE."""
import pytest
from datetime import datetime, timezone
from sqlalchemy import text


@pytest.mark.asyncio
async def test_direct_update_audit_log_raises(session_factory):
    """An UPDATE statement against audit_log fires the trigger."""
    # First insert a row via the legitimate path
    async with session_factory() as session:
        from app.audit.logger import AuditLogger
        from app.db.enums import AuditAction, AuditActorType
        AuditLogger.write(
            session,
            actor_type=AuditActorType.SYSTEM,
            actor_id="test",
            action=AuditAction.STRATEGY_LIVE_ACTIVATED,
            target_type="test", target_id=1,
            payload={}, user_id=1,
        )

    # Try to update — must raise
    async with session_factory() as session:
        with pytest.raises(Exception) as exc:
            await session.execute(text("UPDATE audit_log SET payload = '{}' WHERE id = 1"))
            await session.commit()
        assert "append-only" in str(exc.value).lower() or "forbidden" in str(exc.value).lower()


@pytest.mark.asyncio
async def test_direct_delete_audit_log_raises(session_factory):
    async with session_factory() as session:
        from app.audit.logger import AuditLogger
        from app.db.enums import AuditAction, AuditActorType
        AuditLogger.write(
            session,
            actor_type=AuditActorType.SYSTEM, actor_id="test",
            action=AuditAction.STRATEGY_LIVE_ACTIVATED,
            target_type="test", target_id=1,
            payload={}, user_id=1,
        )

    async with session_factory() as session:
        with pytest.raises(Exception):
            await session.execute(text("DELETE FROM audit_log WHERE id = 1"))
            await session.commit()


@pytest.mark.asyncio
async def test_audit_chain_continuity_per_user(session_factory):
    """Three rows for one user link via prev_hash."""
    from app.audit.logger import AuditLogger
    from app.db.enums import AuditAction, AuditActorType
    async with session_factory() as session:
        for i in range(3):
            AuditLogger.write(
                session,
                actor_type=AuditActorType.SYSTEM, actor_id=f"test{i}",
                action=AuditAction.STRATEGY_LIVE_ACTIVATED,
                target_type="test", target_id=i,
                payload={"i": i}, user_id=1,
            )

    async with session_factory() as session:
        from app.db.models.audit_log import AuditLog
        from sqlalchemy import select
        rows = (await session.execute(
            select(AuditLog).where(AuditLog.user_id == 1).order_by(AuditLog.id)
        )).scalars().all()

    assert len(rows) == 3
    assert rows[0].prev_hash is None
    assert rows[1].prev_hash == rows[0].row_hash
    assert rows[2].prev_hash == rows[1].row_hash


@pytest.mark.asyncio
async def test_verify_audit_integrity_clean_chain(session_factory):
    """The verify script reports zero errors on a clean chain."""
    from app.audit.logger import AuditLogger
    from app.db.enums import AuditAction, AuditActorType
    async with session_factory() as session:
        for i in range(5):
            AuditLogger.write(
                session,
                actor_type=AuditActorType.SYSTEM, actor_id=f"a{i}",
                action=AuditAction.STRATEGY_LIVE_ACTIVATED,
                target_type="test", target_id=i,
                payload={"i": i}, user_id=1,
            )

    # Verify via the canonical hash function
    from app.observability.audit_hash import compute_row_hash
    from app.db.models.audit_log import AuditLog
    from sqlalchemy import select
    async with session_factory() as session:
        rows = (await session.execute(
            select(AuditLog).order_by(AuditLog.id)
        )).scalars().all()
    prev_hash = None
    for row in rows:
        expected = compute_row_hash(
            id=row.id, user_id=row.user_id,
            actor_type=row.actor_type, actor_id=row.actor_id,
            action=row.action, target_type=row.target_type,
            target_id=row.target_id, payload=row.payload,
            created_at=row.created_at, prev_hash=prev_hash,
        )
        assert row.row_hash == expected
        assert row.prev_hash == prev_hash
        prev_hash = row.row_hash
```

Create `apps/backend/tests/observability/test_p5_healthz.py`:

```python
"""Healthz subsystem checks."""
import pytest


@pytest.mark.asyncio
async def test_healthz_returns_ok_on_clean_system(client):
    r = await client.get("/healthz")
    assert r.status_code in (200, 503)
    body = r.json()
    assert body["status"] in ("ok", "degraded", "fail")
    assert "database" in body["checks"]
    assert "master_key" in body["checks"]


@pytest.mark.asyncio
async def test_healthz_no_auth_required(client):
    """Specifically: no session cookie. Loadbalancers won't have one."""
    r = await client.get("/healthz")
    assert r.status_code != 401


@pytest.mark.asyncio
async def test_healthz_503_when_db_down(monkeypatch, client):
    """Simulate DB connection error."""
    async def broken_execute(*args, **kwargs):
        raise RuntimeError("DB down")

    from sqlalchemy.ext.asyncio import AsyncSession
    monkeypatch.setattr(AsyncSession, "execute", broken_execute)

    r = await client.get("/healthz")
    assert r.status_code == 503
    body = r.json()
    assert body["status"] == "fail"
    assert "database" in body["checks"]
    assert "fail" in body["checks"]["database"]


@pytest.mark.asyncio
async def test_healthz_degraded_when_breaker_tripped(session_factory, client):
    from app.db.models.account import Account
    from app.db.enums import AccountMode
    from datetime import datetime, timezone
    async with session_factory() as session:
        session.add(Account(
            user_id=1, broker="alpaca", mode=AccountMode.paper,
            label="Paper", created_at=datetime.now(timezone.utc),
            circuit_breaker_tripped_at=datetime.now(timezone.utc),
        ))
        await session.commit()

    r = await client.get("/healthz")
    # 200 because degraded, not fail
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "degraded"
    assert "degraded" in body["checks"]["circuit_breakers_clear"]
```

Create `apps/backend/tests/observability/test_p5_metrics.py`:

```python
"""Metrics endpoint smoke."""
import pytest


@pytest.mark.asyncio
async def test_metrics_returns_prometheus_format(client):
    r = await client.get("/metrics")
    assert r.status_code == 200
    text = r.text
    # Exposition format markers
    assert "# HELP workbench_orders_submitted_total" in text
    assert "# TYPE workbench_orders_submitted_total counter" in text
    assert "workbench_strategies_active" in text
    assert "workbench_audit_log_rows_total" in text


@pytest.mark.asyncio
async def test_metrics_increments_on_order_submission(client, paper_account):
    # Submit a paper order to bump the counter
    await client.post("/api/v1/orders", json={
        "account_id": paper_account,
        "symbol": "AAPL", "side": "buy", "type": "market",
        "qty": "1", "tif": "day", "source": "manual",
    })

    r = await client.get("/metrics")
    text = r.text
    # The counter line for paper+manual should exist with a nonzero value
    import re
    match = re.search(
        r'workbench_orders_submitted_total\{[^}]*account_mode="paper"[^}]*\}\s+(\d+)',
        text,
    )
    assert match, "expected metric line not found"
    count = int(match.group(1))
    assert count >= 1
```

Create `apps/backend/tests/observability/test_p5_redaction.py`:

```python
"""Log redaction processor catches every credential pattern from §4."""
import pytest

from app.observability.redact import redact_processor, _redact_value


def test_redacts_fernet_token():
    token = "gAAAAABh" + "x" * 60
    msg = f"key=gAAAAABh{'x' * 60} more text"
    out = _redact_value(msg)
    assert "gAAAAABh" not in out
    assert "[REDACTED:fernet]" in out


def test_redacts_anthropic_key():
    key = "sk-ant-1234567890abcdefghij"
    msg = f"api_key={key}"
    out = _redact_value(msg)
    assert key not in out
    assert "[REDACTED:anthropic]" in out


def test_redacts_alpaca_live():
    key = "PKLIVE1234567890ABCD"
    msg = f"Authorization: {key}"
    out = _redact_value(msg)
    assert key not in out
    assert "[REDACTED:alpaca_live]" in out


def test_redacts_alpaca_paper():
    key = "PKTEST1234567890ABCD"
    msg = f"key={key}"
    out = _redact_value(msg)
    assert key not in out
    assert "[REDACTED:alpaca_paper]" in out


def test_redacts_generic_assignment():
    msg = "secret=mySuperSecretValue12345"
    out = _redact_value(msg)
    assert "mySuperSecretValue12345" not in out
    assert "[REDACTED:generic]" in out


def test_redacts_nested_dict():
    event = {
        "msg": "log entry",
        "details": {"api_key": "sk-ant-thisShouldNotAppear12345"},
    }
    out = _redact_value(event)
    serialized = str(out)
    assert "thisShouldNotAppear12345" not in serialized


def test_redacts_via_processor():
    event_dict = {"msg": "creds: sk-ant-1234567890abcdefghij"}
    out = redact_processor(None, None, event_dict)
    assert "sk-ant-1234567890abcdefghij" not in str(out)


def test_passes_through_non_string_values():
    event_dict = {"count": 42, "active": True, "items": [1, 2, 3]}
    out = redact_processor(None, None, event_dict)
    assert out["count"] == 42
    assert out["active"] is True
    assert out["items"] == [1, 2, 3]
```

Run:

```powershell
cd apps\backend
.\.venv\Scripts\python.exe -m pytest tests/observability/ -v
.\.venv\Scripts\python.exe -m pytest -q --cov-branch

# Six shell invariants (Session 7 baseline was 5; §8 adds check_audit_immutability)
bash scripts/check_strategy_isolation.sh
bash scripts/check_mcp_readonly.sh
bash scripts/check_no_llm_in_order_path.sh
bash scripts/check_broker_isolation.sh
bash scripts/check_no_env_credentials.sh
bash scripts/check_audit_immutability.sh   # NEW — added by §8.1.6

# ADR 0002 + audit-immutability pytest invariants
.\.venv\Scripts\python.exe -m pytest tests/test_adr_0002_invariant.py -q
.\.venv\Scripts\python.exe -m pytest -q -k "audit_immutab"

# Three coverage gates
.\.venv\Scripts\python.exe scripts\check_risk_coverage.py
.\.venv\Scripts\python.exe scripts\check_p2_coverage.py
.\.venv\Scripts\python.exe scripts\check_p3_coverage.py
cd ..\..
```

- [ ] 4 audit immutability tests pass.
- [ ] 4 healthz tests pass.
- [ ] 2 metrics tests pass.
- [ ] 8 redaction tests pass.
- [ ] **Nine** CI invariants green.

---

## §8.9 — Manual Smoke

```bash
./scripts/dev.sh &
sleep 30
./scripts/login_helper.sh

# 1. Healthz: degraded → ok flow
curl -s http://127.0.0.1:8000/healthz | jq

# 2. Metrics: scrape and check at least one expected counter
curl -s http://127.0.0.1:8000/metrics | grep -E "^workbench_" | head -20

# 3. Submit a paper order; verify counter increments
PAPER_ACC_ID=$(curl -s -b /tmp/cookies.txt http://127.0.0.1:8000/api/v1/accounts | jq -r '.items[] | select(.mode=="paper") | .id')
BEFORE=$(curl -s http://127.0.0.1:8000/metrics | grep -E 'workbench_orders_submitted_total.*account_mode="paper".*source="manual"' | head -1 | awk '{print $NF}')

curl -s -b /tmp/cookies.txt -X POST http://127.0.0.1:8000/api/v1/orders \
  -H "Content-Type: application/json" \
  -d "{
    \"account_id\": ${PAPER_ACC_ID},
    \"symbol\": \"AAPL\", \"side\": \"buy\", \"type\": \"market\",
    \"qty\": \"1\", \"tif\": \"day\", \"source\": \"manual\"
  }" >/dev/null

AFTER=$(curl -s http://127.0.0.1:8000/metrics | grep -E 'workbench_orders_submitted_total.*account_mode="paper".*source="manual"' | head -1 | awk '{print $NF}')
echo "Counter before=${BEFORE} after=${AFTER}"
# Expect: AFTER > BEFORE

# 4. Audit chain verification
docker compose exec backend uv run python scripts/verify_audit_integrity.py
# Expect: "Verified N rows; 0 errors."

# 5. Trigger blocks direct UPDATE
docker compose exec backend uv run sqlite3 /app/data/workbench.sqlite \
  "UPDATE audit_log SET payload = '{}' WHERE id = 1;" 2>&1 | head -3
# Expect: "Error: audit_log is append-only; UPDATE forbidden" (or similar)

# 6. Trigger blocks direct DELETE
docker compose exec backend uv run sqlite3 /app/data/workbench.sqlite \
  "DELETE FROM audit_log WHERE id = 1;" 2>&1 | head -3
# Expect: similar error

# 7. Backup runs cleanly
docker compose exec backend /app/scripts/backup_db.sh
docker compose exec backend ls -la /app/data/backups/
# Expect: workbench-YYYY-MM-DD.sqlite present

# 8. Backup is valid SQLite
docker compose exec backend sqlite3 \
  "/app/data/backups/workbench-$(date -u +%Y-%m-%d).sqlite" \
  "SELECT count(*) FROM orders;"

# 9. Log redaction: emit a log line with a fake credential, scrape, verify redacted
docker compose exec backend uv run python -c "
import structlog
log = structlog.get_logger()
log.info('test_event', fake_key='sk-ant-shouldNotAppearInLogs1234567890')
"
docker compose logs backend --tail 5 | grep -c "shouldNotAppearInLogs" || echo "REDACTED OK"
# Expect: 0 matches → "REDACTED OK"

# 10. Load-bearing: P1-§7 paper smoke still works
curl -s -b /tmp/cookies.txt -X POST http://127.0.0.1:8000/api/v1/orders \
  -H "Content-Type: application/json" \
  -d "{
    \"account_id\": ${PAPER_ACC_ID},
    \"symbol\": \"AAPL\", \"side\": \"buy\", \"type\": \"market\",
    \"qty\": \"1\", \"tif\": \"day\", \"source\": \"manual\"
  }" | jq '{status, broker_order_id}'
# Expect: status=accepted, broker_order_id non-null

docker compose down
```

- [ ] Healthz returns appropriate status.
- [ ] Metrics endpoint serves Prometheus format with expected metrics.
- [ ] Counters increment on order submission.
- [ ] Audit integrity verifier reports 0 errors.
- [ ] Direct UPDATE/DELETE on audit_log fails at the DB level.
- [ ] Daily backup succeeds; restoration is intact SQLite.
- [ ] Log redaction catches credential patterns.
- [ ] **Paper smoke unchanged.**

---

## §8.10 — Final P5 Verification

This is the exhaustive cross-session check that produces the `p5-complete` signal. Run after §8 merges to main.

```bash
# Sanity: on main, at p5-session8-complete
git checkout main
git pull
git describe --tags --abbrev=0
# Expect: p5-session8-complete

# 1. ALL CI invariants pass (6 shell + 2 pytest + 3 coverage gates)
bash apps/backend/scripts/check_strategy_isolation.sh
bash apps/backend/scripts/check_mcp_readonly.sh
bash apps/backend/scripts/check_no_llm_in_order_path.sh
bash apps/backend/scripts/check_broker_isolation.sh
bash apps/backend/scripts/check_no_env_credentials.sh
bash apps/backend/scripts/check_audit_immutability.sh
docker compose exec backend uv run python -m pytest tests/test_adr_0002_invariant.py -q
docker compose exec backend uv run python -m pytest -q -k "audit_immutab"
docker compose exec backend uv run python apps/backend/scripts/check_risk_coverage.py
docker compose exec backend uv run python apps/backend/scripts/check_p2_coverage.py
docker compose exec backend uv run python apps/backend/scripts/check_p3_coverage.py

# 2. Full test suite green (this is the cross-session "P5 complete" smoke,
# run inside the container which is the production execution context)
docker compose exec backend uv run pytest -q --cov-branch --tb=short

# 3. Bring up the stack from a clean state (already up if step 2 ran in
# container; this is the from-scratch verification path)
docker compose down -v
docker compose up -d
sleep 60

# 4. ALL P5 docs present
ls docs/adr/0004*.md docs/adr/0005*.md
ls docs/runbook/credentials.md docs/runbook/risk-gates.md \
   docs/runbook/live-order-safety.md docs/runbook/activation.md \
   docs/runbook/deployment.md docs/runbook/on-call.md

# 5. §1 — AccountMode enum + LiveAccountBanner
docker compose exec backend uv run python -c "
from app.db.enums import AccountMode
assert AccountMode.paper and AccountMode.live
print('§1 OK')
"

# 6. §2 — BrokerRegistry with both adapters loadable
docker compose exec backend uv run python -c "
from app.brokers.alpaca_paper_adapter import AlpacaPaperAdapter
from app.brokers.alpaca_live_adapter import AlpacaLiveAdapter
from app.brokers.registry import BrokerRegistry
print('§2 OK')
"

# 7. §3 — Auth works (TOTP, sessions, rate limiting)
./scripts/login_helper.sh
# Cookie set in /tmp/cookies.txt

# 8. §4 — Credentials encrypted in DB
docker compose exec backend uv run sqlite3 /app/data/workbench.sqlite \
  "SELECT length(ciphertext) FROM user_credentials LIMIT 5;"
# Expect: rows with ciphertext lengths ~100-200 bytes (encrypted)

# 9. §5 — Risk-state endpoint, breaker, PDT
PAPER_ACC_ID=$(curl -s -b /tmp/cookies.txt http://127.0.0.1:8000/api/v1/accounts | jq -r '.items[] | select(.mode=="paper") | .id')
curl -s -b /tmp/cookies.txt http://127.0.0.1:8000/api/v1/accounts/${PAPER_ACC_ID}/risk-state | jq

# 10. §6 — Cooldown endpoint
STRAT_ID=$(curl -s -b /tmp/cookies.txt http://127.0.0.1:8000/api/v1/strategies | jq -r '.items[0].id')
if [ "$STRAT_ID" != "null" ]; then
  curl -s -b /tmp/cookies.txt http://127.0.0.1:8000/api/v1/strategies/${STRAT_ID}/cooldown | jq
fi

# 11. §7 — Activation endpoints
if [ "$STRAT_ID" != "null" ]; then
  curl -s -b /tmp/cookies.txt http://127.0.0.1:8000/api/v1/strategies/${STRAT_ID}/activation | jq
fi

# 12. §8 — Healthz, metrics, backup, audit immutability
curl -s http://127.0.0.1:8000/healthz | jq
curl -s http://127.0.0.1:8000/metrics | head -20
docker compose exec backend /app/scripts/backup_db.sh
docker compose exec backend uv run python scripts/verify_audit_integrity.py

# 13. THE LOAD-BEARING ASSERTION: paper smoke byte-identical
curl -s -b /tmp/cookies.txt -X POST http://127.0.0.1:8000/api/v1/orders \
  -H "Content-Type: application/json" \
  -d "{
    \"account_id\": ${PAPER_ACC_ID},
    \"symbol\": \"AAPL\", \"side\": \"buy\", \"type\": \"market\",
    \"qty\": \"1\", \"tif\": \"day\", \"source\": \"manual\"
  }" | jq '{status, reason_code, broker_order_id}'
# Expect: status=accepted, broker_order_id non-null

docker compose down

# 14. Tag p5-complete
git tag -a p5-complete -m "P5 complete — live trading paths shipped"
git push origin p5-complete
```

- [ ] All nine CI invariants green.
- [ ] Full test suite green.
- [ ] All P5 docs (2 ADRs + 6 runbooks) present.
- [ ] §1-§8 functional checks pass.
- [ ] Paper smoke byte-identical.
- [ ] `p5-complete` tag pushed.

---

## §8.11 — Commit and PR

```bash
git add apps/backend/app/db/models/audit_log.py
git add apps/backend/alembic/versions/
git add apps/backend/app/observability/
git add apps/backend/app/audit/logger.py
git add apps/backend/app/services/order_router.py
git add apps/backend/app/api/healthz.py
git add apps/backend/app/api/metrics.py
git add apps/backend/app/api/v1/auth.py
git add apps/backend/app/brokers/
git add apps/backend/app/jobs/metrics_snapshot.py
git add apps/backend/app/lifespan.py
git add apps/backend/app/main.py
git add apps/backend/app/pyproject.toml
git add apps/backend/scripts/check_audit_immutability.sh
git add apps/backend/scripts/verify_audit_integrity.py
git add apps/backend/tests/observability/
git add apps/backend/tests/conftest.py
git add scripts/backup_db.sh scripts/restore_db.sh
git add docs/runbook/deployment.md docs/runbook/on-call.md
git add .github/workflows/ci.yml

git commit -m "feat(p5): production hardening — observability, integrity, backups (P5 §8)

The final P5 session. Production-readiness without changing any
order-routing behavior.

- Immutable audit_log via DB triggers (audit_log_no_update,
  audit_log_no_delete) — bugs in future PRs cannot corrupt the trail.
- audit_log.row_hash + prev_hash columns; SHA-256 hash chain per user.
  Atomically computed via MAX(id)+1 pattern (SQLite WAL serializes writes
  so the race window is zero). AuditLogger.write uses raw INSERT.
- scripts/verify_audit_integrity.py walks every chain; exit 1 on mismatch.
- check_audit_immutability.sh is the 9th CI invariant: forbids
  UPDATE/DELETE on audit_log or trigger drops in production code paths.
- /healthz endpoint (unauthenticated, by design): 5 subsystem checks
  (database, master_key, broker_registry, scheduler, circuit_breakers_clear).
  Returns 503 only on overall=fail; 200 on ok or degraded.
- /metrics endpoint with 12 Prometheus metrics: order counters by
  outcome/mode/source, LIVE order counter, strategy gauges, breaker
  count, cooldown count, pending_live count, job last-run gauges,
  credential staleness, order duration histogram, broker error counter,
  auth failure counter, audit log row count.
- Snapshot job populates gauges every 30s.
- Log redaction processor catches 5 credential pattern families before
  they hit stdout. Wired into structlog before the renderer.
- scripts/backup_db.sh uses SQLite .backup (atomic, WAL-aware). Daily
  at 02:00 via APScheduler. 30-day retention. scripts/restore_db.sh
  refuses to run while backend is up.
- docs/runbook/deployment.md — fresh-box procedure (≤60 min wall-time).
- docs/runbook/on-call.md — dozen common failure modes, skim format.
- 18 backend tests across observability/.
- 9 CI invariants now enforced.

NOT in this PR:
- TLS (reverse proxy handles).
- Multi-instance HA.
- External metric storage (you run Prometheus / Grafana yourself).
- PagerDuty integration.

Load-bearing: full P1-§7 paper smoke byte-identical. The order routing
code paths gained observability hooks (counters + histograms) but no
behavior changes."

git push -u origin feat/p5-session8-production-hardening

gh pr create \
  --title "feat(p5): production hardening (P5 §8) — closes P5" \
  --body "P5 Session 8 — the final session. Production-readiness layer:
observability, integrity, backups, runbooks.

After merge: run §8.10 final P5 verification → tag p5-complete.

Load-bearing: paper smoke unchanged.

PLEASE: do not merge in flow. This is the last P5 PR; spend the time to
read each new module."

gh pr checks
# Walk away ≥1 hour (matches Sessions 5, 6, 7 discipline; §7's ≥2h was the
# elevated bar because §7 opened the live path — §8 returns to the normal 1h
# since observability changes don't expand the live-money surface).

# Squash-merge convention (matches Sessions 4, 5, 6, 7)
gh pr merge --squash --subject "feat(p5): production hardening (P5 §8) (#NN)" --delete-branch
git checkout main && git pull
git tag -a p5-session8-complete -m "P5 §8 production hardening complete"
git push origin p5-session8-complete

# Now run §8.10 final verification, then:
git tag -a p5-complete -m "P5 complete — live trading shipped"
git push origin p5-complete
```

- [ ] PR opened; CI green incl. all 6 shell invariants + ADR 0002 pytest + audit-immutability pytest.
- [ ] Walked away ≥1 hour.
- [ ] All CI invariants pass.
- [ ] PR merged.
- [ ] `p5-session8-complete` tag pushed.
- [ ] §8.10 final P5 verification passed.
- [ ] **`p5-complete` tag pushed. P5 is closed.**

---

## Verification Checklist (full session)

- [ ] §8.1 Audit log immutable: triggers block UPDATE/DELETE; row_hash chain verified.
- [ ] §8.2 /healthz with 5 subsystem checks.
- [ ] §8.3 /metrics with 12 Prometheus metrics; snapshot job populates gauges.
- [ ] §8.4 Log redaction catches 5 credential pattern families.
- [ ] §8.5 Daily backup with 30-day retention; restore script.
- [ ] §8.6 Deployment runbook fresh-box procedure.
- [ ] §8.7 On-call playbook with the dozen common failure modes.
- [ ] §8.8 18 backend tests pass.
- [ ] §8.9 Manual smoke covers every new surface; paper baseline unchanged.
- [ ] §8.10 Final P5 verification passes.
- [ ] §8.11 PR merged; both tags pushed.

---

## Notes & Gotchas

1. **The MAX(id)+1 hash insertion pattern relies on SQLite WAL's writer serialization.** Gotcha-of-record: SQLite WAL allows multiple readers but only one writer at a time. The MAX query and the INSERT are in the same transaction; no other writer can interleave. If we ever swap to Postgres or another DB that allows concurrent writers, this becomes a race — switch to a sequence column or an advisory lock. The deployment runbook §8.6 notes this.

2. **The DB triggers fire for ALL SQL — even from migrations.** Gotcha §8.1.2: the migration adds the triggers AFTER backfilling row_hash. If you add the triggers first then try to backfill via UPDATE, the trigger blocks you. Order matters: backfill, then drop server_default, then create triggers.

3. **Test fixture must drop+recreate triggers, not just DELETE FROM audit_log.** Gotcha §8.1.5: the trigger fires on DELETE FROM. The conftest fixture drops the triggers, wipes the table, then recreates them. This is the only place in the codebase that does this; the CI invariant from §8.1.6 explicitly allows the test fixture path.

4. **Per-user hash chains, not a global chain.** Gotcha §8.1.1: a global chain serializes all audit writes (every insert reads the latest row). Per-user chains parallelize. For single-user MVP this is overkill but the schema doesn't have to change for multi-user.

5. **Healthz is unauthenticated by design.** Gotcha §8.2: load balancers, monitors, orchestrators need it without credentials. The endpoint exposes status booleans and counts, not data. The 127.0.0.1 binding from P0 keeps external access to your reverse proxy's discretion.

6. **The `degraded` status means trading is impaired, not that the system is broken.** Gotcha §8.2: a tripped circuit breaker is degraded — orders rejected on that account, but the system is otherwise healthy. Load balancers should treat degraded as "still serve traffic" (200) and only treat fail as "remove from rotation" (503). Get this distinction right in your alerting.

7. **`/metrics` is bound to 127.0.0.1.** Gotcha §8.3: from the docker-compose binding. Prometheus scraping must happen from the same host (via the docker network) or through a reverse proxy with an allow-list. Don't expose `/metrics` publicly — the gauges include strategy and account counts that you don't want to advertise.

8. **The `workbench_orders_submitted_total` counter cardinality.** Gotcha §8.3: labels are `(outcome, account_mode, source)`. Outcome has ~5 values; mode has 2; source has ~3. Total cardinality ~30. Safe. If you add more labels (e.g., symbol), cardinality explodes. Don't.

9. **Snapshot gauges resets to 0 every snapshot.** Gotcha §8.3.2: when computing `strategies_active` by status, we set every known status to 0 first, then populate from the query. Otherwise a status with no strategies stays stuck at its last seen value (Prometheus gauges are "remember the last set value" by default).

10. **Log redaction is defense in depth, not the primary defense.** Gotcha §8.4: don't pass credentials to logger.* calls in the first place. The redactor catches accidental leaks; the primary defense is "credentials never enter the structured log payload to begin with." If you find yourself relying on the redactor, fix the upstream code.

11. **The redaction patterns use ordered evaluation.** Gotcha §8.4: more specific patterns (Fernet, Anthropic, Alpaca) run first; the generic `password=` catch-all runs last. If the order were reversed, the generic pattern would catch parts of specific patterns and leave residue. Tests cover this ordering.

12. **SQLite .backup is atomic but slow on large DBs.** Gotcha §8.5: for the workbench's expected DB size (≤500MB even after years of trading), .backup takes ≤5 seconds. If you ever scale past a few GB, switch to filesystem-level snapshots (LVM, ZFS). The runbook §8.6 mentions this.

13. **Backup retention prune is best-effort.** Gotcha §8.5: `find ... -mtime +30 -delete` uses mtime, which can be wrong if a file was touched. If you copy backups to S3 or another store, the prune logic there is separate. We don't ship S3 sync; that's your operational concern.

14. **restore_db.sh refuses while backend is up.** Gotcha §8.5: it curls /healthz to verify backend is down. If your backend is up but bound to a different port, or if healthz is broken, the script's safety check fails and refuses — that's correct. Don't add a `--force` flag; the manual override would defeat the purpose.

15. **The deployment runbook estimates 60 minutes wall-time for a competent operator.** Gotcha §8.6: this is the actual delta from clone to first paper order. Inexperienced operators take longer; that's OK. The runbook is a checklist, not a tutorial. If you find an operator struggling at a step, update the runbook to clarify.

16. **The on-call playbook is built to be skimmed.** Gotcha §8.7: when you're paged at 3am, you don't want to read paragraphs. Symptom → check → fix per scenario. Resist the urge to add deep explanations; link to the deeper runbooks instead.

17. **Don't bundle anything else into this PR.** Gotcha §8.11: this is the final P5 PR. After it lands, run §8.10 (the cross-session verification) to confirm the whole phase still hangs together. Then tag `p5-complete`. P6 is the next phase, not a session.

18. **After `p5-complete`, the next work is P6 — agent autonomy (B3 mode).** Out of scope for this session. The point of finishing P5 cleanly is so P6 has a stable foundation: live trading works, gates are in place, audit is immutable, observability is wired. Don't start P6 work in the §8 PR.

19. **`AuditLogger` is sync, lives at `app/audit/logger.py`** (drift item #1). The v0.1 doc had it as async at `app/services/audit_log.py`. §8.1.4's hash-chain integration uses the sync API and does NOT call `await`. Verify the actual signature in current code before pasting; Notes & Gotchas #22 has the full list of execution-time verifications.

20. **Audit-immutability is layered defense.** Session 7 already shipped a pytest-level audit-immutability test (drift item #2). §8.1 adds: (a) **storage-layer DB triggers** (`audit_log_no_update`, `audit_log_no_delete`); (b) **hash chain columns** with cryptographic verification via `verify_audit_integrity.py`; (c) **grep-based CI invariant** `check_audit_immutability.sh`. The pytest test from Session 7 stays — don't duplicate, don't conflict. Each layer catches a different attack: the pytest catches accidental ORM `update()` calls in code; the trigger catches direct SQL UPDATE/DELETE that slipped past the ORM; the hash chain catches a database file edit that bypassed the application entirely.

21. **CI invariant inventory after §8 ships.** Six shell invariants (`check_strategy_isolation.sh`, `check_mcp_readonly.sh`, `check_no_llm_in_order_path.sh`, `check_broker_isolation.sh`, `check_no_env_credentials.sh`, `check_audit_immutability.sh`). Two pytest invariants (`tests/test_adr_0002_invariant.py`, the audit-immutability test inherited from Session 7). Three coverage gates (`check_risk_coverage.py`, `check_p2_coverage.py`, `check_p3_coverage.py`). The v0.1 doc called this "nine invariants"; the actual breakdown is 6 + 2 + 3 = 11 quality gates total, but the customary count of "invariants" excludes the coverage gates. Adjust the CI workflow descriptions accordingly.

22. **Expect execution-surfaced drift.** Sessions 5, 6, 7 each surfaced 6-10 execution-time deviations from their v0.2 plans. Session 8 has the largest surface area of any P5 session — observability touches the audit log (§8.1), every endpoint via /healthz subsystem checks (§8.2), every order path via metrics counters (§8.3), the credential store via log redaction (§8.4), the SQLite WAL via backup (§8.5), and the entire stack via the deployment runbook (§8.6) and on-call playbook (§8.7). Before pasting §8.1.4 code, read `app/audit/logger.py` for the actual `AuditLogger.write` signature. Before pasting §8.2 code, read `app/main.py` for how unauthenticated routes are registered. Before pasting §8.3 code, verify `prometheus_client` is in dependencies. Before pasting §8.5 code, verify the SQLite database path (Session 4 confirmed `data/workbench.sqlite` from the backend cwd). Capture deviations in Session 8 Results — Session 7 Results documented eight Session 7 deviations from its v0.2 plan, and Session 8's list will be at least that long.

23. **The `app/observability/` package may not exist yet.** §8.1.4 imports `from app.observability.audit_hash import compute_row_hash`. If the package is new, create it as part of §8.1.3 with an empty `__init__.py` plus `audit_hash.py`. §8.3's metrics module also lives here (`app/observability/metrics.py`). If `app/observability/` already exists from earlier work, just add the new modules.

24. **§8 is the final P5 session. Walk away ≥1h discipline applies, but no more.** Session 7 needed ≥2h because it opened the live-money path; §8 returns to the normal ≥1h since observability doesn't expand the live-money surface. After §8.10 final verification passes, tag `p5-complete` and stop. P5 is closed. Don't start P6 work in this PR — it'd defeat the discipline of closing a phase cleanly.

---

*End of P5 Session 8 v0.2. Updated in-place from v0.1 (2026-05-23) with 14 drift corrections from Sessions 0–7 Results — including the consequential `AuditLogger` sync-vs-async mismatch (resolved by rewriting §8.1.4 to the sync API), the corrected CI invariant inventory (6 shell + 2 pytest + 3 coverage gates vs v0.1's imagined "nine invariants"), and a candid acknowledgment of unknown execution-surfaced drift. §8 is the final P5 session; after it ships and §8.10 passes, tag `p5-complete`.*
