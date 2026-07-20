# On-Call Playbook (P5 §8.7)

Skim format. Per symptom: what's probably wrong → what to check → how to fix.
Built to be read at 3am. The deeper explanations live in the per-subsystem
runbooks; this is the index of failure modes from P5 §1–§8.

---

## "I can't log in"

**Symptom:** `POST /api/v1/auth/login` returns 401 / 403 / 429.

**Check:**
- **429** → rate limited (sliding window + cooldown after 5 failures). The
  `workbench_auth_failures_total{reason="rate_limited"}` metric confirms.
- **401** "Invalid credentials" → wrong password OR expired/incorrect TOTP code.
- **403** → TOTP not enrolled for the account.

**Fix:**
- TOTP drift: confirm the authenticator shows the current code (30s rotation).
- Lost password (no reset flow in MVP): reset the hash directly —
  ```bash
  docker compose exec backend python -c "
  import asyncio, bcrypt
  from sqlalchemy import update
  from app.db.session import get_sessionmaker
  from app.db.models.user import User
  async def reset(email, pw):
      h = bcrypt.hashpw(pw.encode(), bcrypt.gensalt(rounds=12)).decode()
      async with get_sessionmaker()() as s:
          await s.execute(update(User).where(User.email==email).values(password_hash=h)); await s.commit()
  asyncio.run(reset('you@example.com','newpassword'))"
  ```
- Lost TOTP: re-bootstrap via `scripts/create_user.py` for that user.

## "Healthz returns 503"

**Symptom:** `/healthz` → `{"status":"fail",...}`.

**Check** the `checks` field for which subsystem failed.

**Fix:**
- `database=fail` → DB unreachable. `docker compose ps`; restart backend.
- `master_key=fail` → `.env` missing/corrupt `WORKBENCH_MASTER_KEY`; fix; restart.
- `broker_registry=fail: accounts exist but no adapters` → credentials missing
  for an account. Set them (Settings → Credentials); restart (adapters load on boot).
- `scheduler=fail` → APScheduler died; restart backend.

(A tripped circuit breaker is `degraded`, **200** — not a 503. See below.)

## "Strategy stuck in PENDING_LIVE past 24h"

**Symptom:** `ActivationCountdown` shows elapsed but status stays PENDING_LIVE.

**Check:** scheduler running? Look for `activation_completion` runs (~every 60s)
and a non-zero `workbench_background_job_last_run_seconds{job="activation_completion"}`
that isn't growing unbounded. Confirm `live_activation_initiated_at` is set and
24h has actually elapsed.

**Fix:** restart the backend (the completion job is idempotent and catches up).
See `docs/runbook/activation.md` § Failure modes.

## "Circuit breaker keeps tripping"

**Symptom:** an account's breaker re-trips soon after reset.

**Check:** daily PnL vs `max_daily_loss` (default LIVE $500). Read the
`CIRCUIT_BREAKER_TRIPPED` audit payload (`realized_pnl_today`,
`unrealized_pnl_now`). Is the algo genuinely losing, or is unrealized PnL stale
because the broker is flaky? Check
`workbench_broker_api_errors_total{operation="get_positions"}`.

**Fix:**
- Genuinely losing → stop, debug, re-validate on paper before re-activating.
- Limit too tight → raise it at Settings → Risk Limits → LIVE (audit-logged).
- Broker flakiness inflating the count → fix the adapter/network first.

## "Replay reports a mismatch" (`REPLAY_MISMATCH`) — **CRITICAL**

**Symptom:** `workbench_replay_verifications_total{verdict="mismatch"}` increments, a
`REPLAY_MISMATCH` audit row appears, or `replay_decisions.py` exits non-zero. Replay (P11 §4,
ADR 0021) reconstructs an automated decision from its audit fingerprint and recomputes the
decision rule from the *recorded inputs*. A **mismatch means the recorded decision is not
justified by its recorded evidence** — a logic regression, a fingerprint missing a load-bearing
input, or an input computed inconsistently. Replay is read-only — it verifies, never corrects.

**Check:** read the `REPLAY_MISMATCH` audit payload (`audit_log_id`, `decision_type`,
`recorded`, `recomputed`, `note`) — it points at the original decision's audit row. Re-run the
verifier on it for the full picture:

    python scripts/replay_decisions.py --audit-id <audit_log_id>

By `decision_type`:
- `CIRCUIT_BREAKER_TRIPPED` — the recorded trip's `net_pnl` (= `realized_pnl_today +
  unrealized_pnl_now`) either does not reproduce, or does not satisfy `net_pnl ≤ −max_daily_loss`.
  This is the *spurious-trip* class (see "Circuit breaker keeps tripping"): the breaker tripped on
  an input that doesn't justify it — suspect a start-of-day equity-baseline bug.
- `RECONCILIATION_DISCREPANCY` — the recorded discrepancy `kind` does not match the
  classification recomputed from the recorded `local`/`broker` quantities (a §3 classification bug).

**Fix:**
- First confirm it is not a **replay engine** fault: a `verdict="error"` (not `mismatch`) means a
  malformed payload, not an unjustified decision — fix the verifier/payload, not the decision.
- A real `mismatch` is **stop-and-investigate**: the automation that produced the original
  decision has a bug (or its fingerprint is incomplete). Find the producing code path
  (`decision_type` → the trip in `circuit_breaker.py` / the diff in `reconciliation.py`), fix it,
  and add a regression test. Do **not** edit the audit log — it is the evidence.
- `replay_coverage_ratio` < 1.0 is expected, not an alert: it honestly reports the fraction of
  decision types replay can verify today (overlay + risk-check are `unreplayable` pending durable
  fingerprints).

## "Reconciliation reports a discrepancy" (broker ⇄ local drift)

**Symptom:** `workbench_reconciliation_discrepancies_total` increments, or a
`RECONCILIATION_DISCREPANCY` audit row appears. The 300s reconciliation pass
(P11 §3, ADR 0021) does an INDEPENDENT broker `get_positions()` fetch per account
and diffs it against the local `positions` table. It is **alert-only** — it never
submits a corrective order; it only surfaces the drift for you to judge.

**Check:** read the audit payload (`domain`, `kind`, `severity`, `symbol`,
`local`, `broker`) and the latest `reconciliation_runs` row for the account:

    SELECT ran_at, result, n_checked, n_discrepancies, detail_json
    FROM reconciliation_runs WHERE account_id = $ID ORDER BY id DESC LIMIT 5;

`kind` tells you the shape:
- `qty_mismatch` — both sides hold the symbol, quantities differ.
- `missing_local` — broker holds a position local does not (a fill we missed, or
  a stalled `PositionSync`).
- `missing_broker` — local holds a position the broker does not (a closed/expired
  position we didn't clear, or a sync that deleted late).

**Fix:**
- First suspect a **stalled PositionSync**, not a real trade: check the sync job
  and `workbench_broker_api_errors_total{operation="get_positions"}`. A healthy
  re-sync usually clears a transient `qty_mismatch`/`missing_*`.
- If the drift persists after a clean sync, treat it as a real position the books
  disagree on: inspect recent fills/orders for the symbol, reconcile against the
  Alpaca dashboard, and correct manually (a manual order through the OrderRouter —
  reconciliation will not do this for you).
- A `result` of `unavailable` means the broker was unreachable that pass (no
  conclusion drawn) — not a discrepancy. Recurring `unavailable` → broker/network.

## "Duplicate order / an actor double-acted" (P11 §5, **P1 — immediate**)

**Symptom:** two `order` rows for the same intent in one period (a doubled rebalance or
overlay re-size), or `recovery_failures_total` spikes after a restart. ADR 0021 property 1
(idempotency) is the guard; a duplicate means a guard did not hold.

**Check:**
- Was there a **restart at a cron tick**? Resume-on-boot is idempotent (`register()` returns
  the existing run), so a restart alone never double-registers — but the weekly-rebalance
  `_last_rebalance_week` guard is **in-memory** and resets on restart. A restart *exactly at*
  the Monday 14:00 tick is the only window APScheduler could re-fire the rebalance.
- Read the duplicate `order` rows' `source_type` / timestamps and the `automation_runs_total`
  for the actor; check `recovery_attempts_total{recovery_type="resume_on_boot"}`.

**Fix:**
- **Halt the actor first** (deactivate the strategy → IDLE; this does not stop already-filled
  orders). Reconcile (§3) and replay (§4) the period to confirm the duplicate is real, not a
  re-delivered fill (fills are idempotent on `execution_id`).
- If it was a tick-time-restart double-rebalance: the cross-restart guard today is the cron
  schedule, not a durable mark — if this recurs, the named follow-on is a **durable
  last-rebalanced-week flag** (ADR 0021 re-evaluation trigger). File it; do not hand-patch the
  in-memory guard under incident pressure.
- Never "undo" via a compensating automated order — close manually through the OrderRouter.

## "Scheduler tick was delayed or missed" (P11 §5, **P4 — monitor only**)

**Symptom:** `workbench_scheduler_job_last_success_timestamp{job_id=…}` is stale, scheduler
success dips below 99.9% (§2), or `/ops/state` shows a job `degraded`.

**Check:** was the host/Docker down (laptop asleep, Docker Desktop not started)? Resume-on-boot
re-registers all jobs on the next boot — a missed weekly tick simply runs at the next scheduled
time; the actor converges next cycle (it never "catches up" by firing twice — single-flight +
`coalesce`).

**Fix:** bring the stack up (see `deployment.md` / the autostart task). Confirm the job
re-registered (`scheduler_job_events_total{event="executed"}` advances). No manual catch-up
fire is needed or wanted — a delayed tick is fail-safe (less action), not an incident to force.

## "Strategy in cooldown, I want to retry NOW"

**Fix:** Strategy detail → CooldownIndicator → "Clear now" (audit-logged), or
`POST /api/v1/strategies/$ID/cooldown/clear`.

## "Live order rejected with CONFIRMATION_MISMATCH"

**Check:** the typed confirmation must equal the order symbol (case-insensitive,
whitespace-stripped). `AAPL.US ≠ AAPL`.

**Fix:** re-submit with the exact symbol shown.

## "Live order rejected — STRATEGY_NOT_LIVE / STRATEGY_PENDING_LIVE / AGENT_LIVE_DISABLED"

**Check:** these are the §7 live-path guard codes. STRATEGY orders require
`strategy.status == LIVE`; a strategy still in PENDING_LIVE (mid 24h cooldown)
gets `STRATEGY_PENDING_LIVE`; agent-sourced live orders are refused
(`AGENT_LIVE_DISABLED`, P6 territory).

**Fix:** finish activation (`docs/runbook/activation.md`); agents cannot trade
live in P5.

## "Orders are slow"

**Symptom:** `workbench_order_submission_duration_seconds` p99 > 5s.

**Check:** `workbench_broker_api_errors_total` (broker flaky?), backend logs for
broker retries, network latency to `api.alpaca.markets`.

**Fix:** broker-side → wait it out (§5 fail-open keeps submission working).
Our side → profile the router / risk engine.

## "Audit log integrity check fails"

**Symptom:** `verify_audit_integrity.py` reports `row_hash`/`prev_hash` mismatches.

**Check:** when was it introduced? `git log apps/backend/alembic/versions/` for
recent audit-touching migrations; shell history for manual SQL.

**Fix:** a broken chain does **not** break operations. For forensics, restore
the last known-good backup and replay. Find the root cause before trusting the
chain again. (Direct UPDATE/DELETE is blocked by the `audit_log_no_update` /
`audit_log_no_delete` triggers, so a break almost always means a file-level edit
that bypassed the app, or a backfill bug.)

## "Backup didn't run last night"

**Check:** logs for `daily_backup_complete` / `daily_backup_failed`;
`workbench_background_job_last_run_seconds{job="daily_backup"}`.

**Fix:** run by hand: `docker compose exec backend bash scripts/backup_db.sh`.
If the manual run fails, check disk (`df -h`). If manual works but the schedule
doesn't, check the scheduler via `/healthz`.

## "Disk is filling up"

**Check:** `du -sh data/*`; `data/backups/` should be ≤ ~30 files (retention);
a large `data/workbench.sqlite-wal` means checkpoints aren't happening.

**Fix:** prune old backups (verify retention logic); restart backend to force a
WAL checkpoint; rotate host logs via logrotate (out of scope for the workbench).

## "An alert I don't recognize"

**Check:** the metric name against §8.3 (the twelve `workbench_*` metrics).
Cross-reference your Prometheus alerting rules. Alert-rule tuning is out of
scope for this playbook.

## "MKTPROJ_MODEL_PROMOTED appeared in the audit log"

**What it is:** the MKT-PROJ-001 §4 guardrail-1 action — a market-projection
model artifact moved candidate→production via
`scripts/research/mkt_proj_001/promote_model.py`. Legitimate promotions verify
the FULL sha256 against the merged §3 evidence manifest before flipping status.

**Check:** the payload's `artifact_hash` matches `registered_model.artifact_hash`
in `docs/implementation/evidence/mkt_proj_001/ml_walkforward_PRE_CLOSE_TOMORROW.json`
on main, and the payload's `authority` cites the ModelCard v1.0 owner decision.
A promotion with a non-matching hash, an unexpected model_version, or no
corresponding merged evidence is an incident: set the row's status back to
`retired`, and the API/card degrades to unavailable on the next serve.

## "Market Projection card shows 'data drift under review'"

**What it is:** the §4 guardrail-8 auto-downgrade — the train/serve (IEX vs
SIP) drift ladder tripped (≥1.0σ one day, ≥0.5σ same feature 3 consecutive
served days, or >20% of features ≥0.5σ one day). The badge downgrade is
automatic; **restoration is operator-only by design**.

**Check:** `data/market_projection/drift_state.json` (reasons + since) and the
per-day ledger `drift_ledger.jsonl`. Investigate the offending features
(premarket-quality fields and volume baselines are the expected suspects).

**Fix (only after review):** delete `drift_state.json` (or set `"status": "ok"`)
inside the container; the next API read restores the validated badge. Never
script this — the asymmetry (auto-down, manual-up) is the guardrail.
