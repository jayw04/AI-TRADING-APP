# Runbook — AWS EC2 paper-stack migration & cutover

Operational companion to **ADR 0032** and `Docs/implementation/TradingWorkbench_AWS_Migration_Plan_v0.2.md`.
Paper-only. The governing rule, above everything else:

> **Never have two armed schedulers against the same Alpaca paper accounts.**
> Laptop and EC2 are armed *exclusively*. `WORKBENCH_SCHEDULER_ENABLED=true` on exactly one host at a time.

Commands you run interactively (AWS CLI, SSH) are prefixed `$`. Where a step needs the laptop, it says so.
Run interactive logins (e.g. `aws configure`) in this session via `! <command>` so output lands here.

---

## 0. One-time AWS account setup (you)

> **Using CloudFormation (recommended):** `deploy/aws/cloudformation/workbench-paper-stack.yaml`
> creates the IAM role, security group, Elastic IP, **versioned S3 backup bucket, daily EBS-snapshot
> policy, cost-budget alarm, and log group** for you — so steps **1, 2, 4** below are handled by the
> stack. You still do step **3** (SSM secrets — CFN never holds secret values) and step **5** (key pair).

1. **Region:** `us-east-1`. **Budget guardrail:** the CFN stack creates a monthly budget alarm
   (`MonthlyBudgetUsd`, default $50) — even though the $990 credit covers ~24 months, a runaway is a
   signal, not a bill. (Manual path: Console → Billing → Budgets.)
2. **IAM instance role** — created by the stack (`ssm:GetParameter*` on `/workbench/prod/*`,
   `s3:PutObject` to the backup bucket, CloudWatch + Session Manager). Manual path: create the role
   with those scopes.
3. **SSM SecureString params** (copy values from the laptop `.env`; **do not** regenerate the master
   key — it is paired to the DB):
   ```
   $ for k in WORKBENCH_MASTER_KEY ANTHROPIC_API_KEY WORKBENCH_MCP_KEY AGENT_API_KEY MCP_BACKEND_TOKEN; do
       aws ssm put-parameter --region us-east-1 --type SecureString \
         --name "/workbench/prod/$k" --value "<paste-from-laptop-.env>" --overwrite
     done
   # Optional — read-only deploy token so the instance can clone the PRIVATE repo:
   $ aws ssm put-parameter --region us-east-1 --type SecureString \
       --name "/workbench/prod/GITHUB_DEPLOY_TOKEN" --value "<fine-grained-PAT-read-only>" --overwrite
   ```
   **Do NOT** create any `/workbench/prod/ALPACA_LIVE_*`. Paper creds are inside the DB, not SSM.
4. **S3 backup bucket** (versioned) — created by the stack (`BackupBucketName`, globally unique).
   Manual path: `s3://workbench-backups-<acct>/` with versioning on.
5. **EC2 key pair** for SSH (passed to the stack as `KeyName`).

---

## Phase 1 — Stand up the box (scratch DB, scheduler DISARMED). Laptop keeps running.

1. **Launch the environment.** Either —

   **A. CloudFormation (recommended)** — one command creates the box + IAM + SG + EIP + bucket +
   snapshots + budget, and self-provisions DISARMED (`SchedulerEnabled=false`):
   ```
   $ aws cloudformation deploy --region us-east-1 \
       --stack-name workbench-paper \
       --template-file deploy/aws/cloudformation/workbench-paper-stack.yaml \
       --capabilities CAPABILITY_IAM \
       --parameter-overrides \
         KeyName=<your-keypair> VpcId=<vpc-id> SubnetId=<public-subnet-id> \
         SshLocationCidr=<your.ip>/32 BackupBucketName=<globally-unique> \
         BudgetEmail=<you@example.com> SchedulerEnabled=false
   $ aws cloudformation describe-stacks --stack-name workbench-paper \
       --query "Stacks[0].Outputs" --output table   # SSH tunnel cmd, EIP, etc.
   ```
   **B. Manual console** — t4g.medium, Ubuntu 24.04 (arm64), 30 GB gp3, the role from §0.2,
   SG = **SSH(22) from your IP only**; paste `deploy/aws/ec2-user-data.sh` as User data
   (CONFIG: `SCHEDULER_ENABLED="false"`).
2. **Tunnel in** (no public app ports):
   `$ ssh -N -L 5173:127.0.0.1:5173 -L 8000:127.0.0.1:8000 ubuntu@<ip>`
   Browse `http://localhost:5173`.
3. **Smoke checks (all must pass before Phase 2):**
   - [ ] `$ ssh ubuntu@<ip> 'cd /opt/workbench/app && docker compose ps'` — all services healthy.
   - [ ] `/healthz` green for backend, both MCP servers.
   - [ ] **Norton-free data:** trigger an Alpaca data pull (chart/bars) → succeeds (the laptop's TLS block is gone).
   - [ ] Log in to the UI over the tunnel.
   - [ ] Agent answers a prompt (Anthropic reachable; cost cap intact).
   - [ ] **Scheduler is DISARMED:** logs show `scheduler_disarmed`; `scheduler_heartbeat` row has `armed=false`.
   - [ ] **No-live-creds verification** (addition): `$ ssh ubuntu@<ip> 'grep -E "ALPACA_LIVE_|LIVE_TRADING_ALLOWED" /opt/workbench/.env'` → only `WORKBENCH_LIVE_TRADING_ALLOWED=false`, no live secrets.

---

## Phase 2 — Reliability (still parallel; laptop still the live host)

Prerequisites to cutover — do not skip:

1. **Scheduler heartbeat + check (code prereq, ADR 0032).** Confirm the `scheduler_heartbeat` table exists and `scripts/scheduler_health_check.py` returns non-zero on a stale/missing beat and on `>1 armed host_id`.
2. **CloudWatch Logs** for container stdout/stderr (CloudWatch agent installed by bootstrap or here).
3. **Missed-job alarms (addition):** alarm if, on a trading day, no dispatch is recorded by **09:05 ET**, **10:05 ET**, and within 10 min of each scheduled rebalance — sourced from the heartbeat (`last_dispatch_at`). Also alarm on instance status-check fail and `scheduler_health_check.py` non-zero.
4. **Pre-open healthcheck** timer (~08:30 ET): stack up + market-session gate sane (replaces the laptop MarketHours healthcheck).
5. **Backups:** nightly `scripts/backup_db.sh` → S3 (versioned); DLM **daily EBS snapshot**; weekly `scripts/verify_audit_integrity.py`.
6. **Re-home OS tasks** (see plan §8) as cron/systemd-timers in ET.
7. **Automated factor-data refresh (fixes a real staleness gap, found 2026-06-30).** The factor books
   (momentum / sector-rotation / low-vol / combined) RANK on `data/factor_data.duckdb` via `ctx.factors`,
   but the laptop had **no daily incremental** — the only ingest was a one-time back-fill with
   `--skip-existing`, so the live store silently went **~18 days stale** (sep through 6/12 on 6/30).
   On EC2, schedule **`deploy/aws/factor-refresh.sh`** (systemd timer / cron) **pre-market on trading
   days (~06:00 ET)**: it snapshots the live store, incrementally upserts recent SEP/actions, then does a
   short-downtime atomic swap + backend restart. Prereqs:
   - put `NASDAQ_DATA_LINK_API_KEY` (and `FMP_API_KEY`) into SSM `/workbench/prod/*` **and add them to
     the `.env`-build fetch loop** (same pattern as the other secrets — keys belong in SSM, not the box);
   - ensure `survivorship_pool.txt` is present in the data dir (copied at cutover with the data stores).
   This is the durable answer to "data refresh runs directly on EC2" — the store can no longer lapse.

---

## Phase 3 — Cutover (the only risky window). Pick a market-CLOSED time.

> Goal: move the real DB and flip exactly one scheduler from laptop → EC2, with a verifiable gap of **zero armed schedulers** in between.

1. **Disarm + stop the laptop.** On the laptop: `docker compose down`; **disable** `workbench-autostart` + the Windows scheduled tasks.
   ✅ *Zero schedulers armed now.* Verify: laptop `scheduler_heartbeat.armed=false` (or stack down).
2. **Snapshot the source of truth (laptop):** `scripts/backup_db.sh` → copy `data/workbench.sqlite` (+ `apps/backend/strategies_user/`, optionally `bars_cache/`) to EC2 over the tunnel or via S3. **Also seed the factor-data stores** the books rank on: copy **repo-root `data/factor_data.duckdb`** (the live store — NOT the `apps/backend/data` copy) + `survivorship_pool.txt` to EC2 `/opt/workbench/data/`.
3. **Master-key match check:** confirm SSM `WORKBENCH_MASTER_KEY` == the laptop value that encrypted this DB. (Mismatch → backend can't decrypt; STOP.)
4. **Restore on EC2:** place `workbench.sqlite` at `/opt/workbench/data/`; ensure paper creds in the DB resolve to the real paper account.
5. **No-live-creds re-verify (addition):** `grep -E 'ALPACA_LIVE_' /opt/workbench/.env` empty; resolved broker base URL = `paper-api.alpaca.markets`.
6. **Integrity + identity:** `verify_audit_integrity.py` shows **no new** chain breaks; UI lists the expected strategies/schedules/accounts; positions reconcile vs Alpaca.
7. **Catch up the factor data (so the first EC2 rebalance ranks on fresh prices):** run `deploy/aws/factor-refresh.sh` once (it incrementally pulls SEP since the seeded store's last date), then confirm `sep` max date is current. After this, the daily timer (Phase 2 §7) keeps it fresh.
8. **Arm EC2 — and only EC2.** Set `WORKBENCH_SCHEDULER_ENABLED=true` (env + restart backend). Confirm `scheduler_heartbeat` shows **exactly one** armed `host_id` (the EC2 one) and `scheduler_health_check.py` is green.
9. **Watch one full cycle.** Stay until the next scheduled rebalance dispatches end-to-end and reconciles. Then walk away.

---

## Phase 3.5 — Post-cutover 3-day observation (addition)

EC2 is now the live host; the laptop is a disarmed standby. For **3 trading days**, each day:

- [ ] **Pre-open (≈09:00 ET):** stack healthy; heartbeat fresh; single armed `host_id`; no overnight restarts that lost state.
- [ ] **Each scheduled job:** dispatched on time (heartbeat `last_dispatch_at` advances); no missed-job alarm.
- [ ] **Risk/breaker sanity:** no spurious circuit-breaker trips; exposure/leverage within limits (watch for any double-dispatch symptom — there is still no rebalance idempotency).
- [ ] **Audit chain:** `verify_audit_integrity.py` clean (no new breaks).
- [ ] **Backups ran:** last night's S3 DB backup + EBS snapshot present.
- [ ] **Cost/budget:** no budget alarm; spend tracking ≈ $1–1.5/day.

Sign-off after 3 clean days → standby window extends to 2–4 weeks, then the laptop standby can be retired.

---

## Rollback (any time pre-sign-off)

Because only one host is ever armed, rollback is symmetric and safe:
1. On EC2: `docker compose down` (disarm).
2. On the laptop: restore the **pre-cutover** DB snapshot, bring the stack up, set `WORKBENCH_SCHEDULER_ENABLED=true`.
3. Confirm a single armed `host_id` (laptop). Investigate EC2 offline.

Retain the pre-cutover DB snapshot until live operation is signed off. **Never** bring both hosts up armed to "compare."

---

## Quick reference

| Need | Command |
|---|---|
| Tunnel to UI/API | `ssh -N -L 5173:127.0.0.1:5173 -L 8000:127.0.0.1:8000 ubuntu@<ip>` |
| Stack status | `ssh ubuntu@<ip> 'cd /opt/workbench/app && docker compose ps'` |
| Who is armed? | query `scheduler_heartbeat` (`armed=true`, fresh `last_beat_at`) — must be exactly one host |
| Arm / disarm | set `WORKBENCH_SCHEDULER_ENABLED` (true/false) + restart backend |
| Verify audit chain | `scripts/verify_audit_integrity.py` (no *new* breaks) |
| Manual DB backup | `scripts/backup_db.sh` → S3 |
