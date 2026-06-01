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
