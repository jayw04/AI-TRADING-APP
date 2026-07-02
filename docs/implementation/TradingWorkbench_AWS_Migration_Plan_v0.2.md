# TradingWorkbench — AWS Migration Plan (v0.2)

> **v0.2 (2026-06-29):** owner approved v0.1 (9.8/10) and added six items (§13). Decision recorded as
> **[ADR 0032](../adr/0032-aws-ec2-paper-stack-deployment.md)**; operational steps in
> **[Docs/runbook/aws-migration.md](../runbook/aws-migration.md)**; bootstrap at `deploy/aws/ec2-user-data.sh`.

| Field | Value |
|---|---|
| Date | 2026-06-29 |
| Owner | Jay Wang |
| Scope | Move the **paper** stack (backend · scheduler · strategy engine · MCP servers · agent · DB · logs) to an always-on AWS EC2 instance. **No live trading migration.** |
| Strategy | **Parallel-run then cut over**: the laptop keeps running until AWS is proven; one clean cutover; laptop becomes warm standby for 2–4 weeks. |
| AWS credit | **$990** available → cost is a non-constraint (steady-state ≈ $35/mo ≈ ~2 yrs runway). Optimize for reliability, not cost. |
| Locked decisions | Access = **SSH tunnel only** (no public ports) · State = **migrate the live paper DB + books** · Instance = **t4g.medium (4 GB, arm64)** · Provisioning = **bootstrap script + runbook** (manual launch) |
| Region | **us-east-1** (close to Alpaca + Anthropic; matches credit/pricing) |

---

## 1. Why now (the operational case)

Today's failures are infrastructure, not code: the laptop sleeps, restarts reset cache, intraday bars get missed, and every paper book depends on the machine staying awake. An always-on cloud box removes that entire class of failure. Two codebase-specific bonuses:

- **AWS fixes the Norton-SSL blocker.** Norton's TLS MITM blocks `data.alpaca.markets` on the laptop (ADR 0017 worked around it via OS trust store); on EC2 the MITM is simply absent — live data + parquet fixtures work natively.
- **The stack is already cloud-shaped.** `docker-compose.yml` runs all 5 services with `restart: unless-stopped`, every port bound to `127.0.0.1`, and `scripts/backup_db.sh`/`restore_db.sh` already exist. This is a re-home, not a re-architecture.

**Non-goals:** live trading migration (separate ADR after 2–4 clean weeks); RDS/Postgres (Phase 4, only if SQLite contention forces it); rebuilding the TradingView **desktop** MCP automation — that's a research tool and stays on the laptop.

---

## 2. Invariants that MUST survive the move (read before touching anything)

1. **Master key ↔ database are a matched pair.** Broker credentials are Fernet-encrypted *in the SQLite DB*; the key is `WORKBENCH_MASTER_KEY` (`app/security/crypto.py`, backend refuses to boot without it). Move the DB **and** the same master key together, or the backend can't decrypt creds and won't trade.
2. **Exactly one scheduler dispatches at a time.** There is **no rebalance idempotency** yet (root cause of the *Conservative book leverage blowout* — a rebalance fired 3× → 3.8× leverage). The laptop and EC2 schedulers must **never** both target the live Alpaca paper accounts. The whole cutover design below exists to guarantee this.
3. **Audit hash-chain integrity.** After any DB move/restore, run `scripts/verify_audit_integrity.py`. (Two benign pre-existing chain breaks are known/expected; verify no *new* ones.)
4. **Loopback-only binding stays.** Keep every container on `127.0.0.1`; reach the app via SSH port-forward. No app port in any public security-group rule.
5. **Timezone = `America/New_York`.** Set at the instance AND container level. The APScheduler cron has a known day-of-week off-by-one (`0=Mon`); strategy schedules were authored assuming ET — keep ET so they fire on the intended days.

---

## 3. Target architecture

```
Your machine ──SSH tunnel (key-only)──►  EC2 t4g.medium · Ubuntu 24.04 arm64 · TZ America/New_York
  (browser →                                 │
   localhost:5173/8000                        ├── Docker + docker compose (restart: unless-stopped, enabled on boot)
   over the tunnel)                           │     ├── backend   (8000, SQLite /app/data)
                                              │     ├── mcp-server (8765, chart data)
                                              │     ├── workbench-mcp (8766, state SSE)
                                              │     ├── agent      (8767, Anthropic)
                                              │     └── frontend   (5173)
                                              │
  AWS SSM Parameter Store (SecureString) ─────┤  secrets fetched at boot → /opt/workbench/.env (root-only)
  S3 bucket (versioned)  ◄────────────────────┤  nightly backup_db.sh → s3://…  + evidence packages
  EBS gp3 + daily DLM snapshot  ◄─────────────┤  block-level backup
  CloudWatch Logs / Alarms  ◄─────────────────┘  container logs + scheduler-missed alarm
```

Outbound only: Alpaca (`paper-api`/`data.alpaca.markets`), Anthropic (`api.anthropic.com`). Inbound: **SSH (22) from your IP only** — nothing else.

---

## 4. Cost vs the $990 credit

| Item | Monthly (us-east-1, on-demand) |
|---|---|
| t4g.medium (2 vCPU/4 GB, 24×7) | ~$24.5 |
| EBS gp3 root, 30 GB | ~$2.4 |
| Daily snapshots (DLM, ~30 GB churn) | ~$2–4 |
| S3 backups + evidence (versioned, small) | <$1 |
| CloudWatch Logs + alarms | ~$2–5 |
| Data transfer (API egress) | ~$1–3 |
| **Total** | **≈ $33–40/mo** |

$990 credit ≈ **~24 months** of steady-state, with room for a Phase-4 `db.t4g.micro` RDS (~$13/mo) later. **Action:** check the credit's **expiry date** in Billing → Credits; if it expires sooner than the runway, that's fine — we're nowhere near the cap. No reserved-instance/Savings-Plan optimization needed.

---

## 5. Secrets inventory & handling (AWS SSM Parameter Store)

Store each as a **SecureString** SSM parameter under `/workbench/prod/…`; the bootstrap script fetches them into a root-only `/opt/workbench/.env` at boot. **Never** bake secrets into the AMI, user-data plaintext, or git.

| Secret | Source today | Notes |
|---|---|---|
| `WORKBENCH_MASTER_KEY` | laptop `.env` | **CRITICAL — must equal the key that encrypted the migrated DB.** Copy the existing value; do not regenerate. |
| `ANTHROPIC_API_KEY` | laptop `.env` | agent / morning-brief / proposals; `AGENT_DAILY_BUDGET_USD` cap stays (ADR 0013). |
| `WORKBENCH_MCP_KEY` | laptop `.env` | per-user MCP bearer. |
| `AGENT_API_KEY` | laptop `.env` | agent→backend bearer. |
| `MCP_BACKEND_TOKEN` | laptop `.env` | chart-MCP↔backend shared secret. |
| Alpaca **paper** creds | **encrypted in the DB** (preferred path) | Travel inside `workbench.sqlite`; decryptable only with the matching master key. `.env` Alpaca fields are a legacy/dev fallback and stay blank in prod. |
| Alpaca **live** creds | n/a | **Do not provision.** Live is out of scope. |

IAM: an instance role granting `ssm:GetParameter*` on `/workbench/prod/*` and `s3:PutObject` on the backup bucket only. No long-lived keys on the box.

---

## 6. Data/volumes to migrate (from `docker-compose.yml` mounts)

| Host path | Contents | Migrate? |
|---|---|---|
| `./data/workbench.sqlite` | DB: strategies, schedules, encrypted creds, audit log, accounts_state | **Yes — at cutover** (Phase 3), with the matching master key. |
| `./apps/backend/bars_cache` | OHLCV parquet cache (≤5 GB) | Optional — warms faster if copied; otherwise rebuilds on demand. |
| `./apps/backend/strategies_user` | User strategy `.py` templates | **Yes** — copy the dir. |
| `../claude-trading-view` (RO) | Sibling premarket-gappers feed | Optional/degraded — the Opportunities widget is advisory only (never an order signal). Defer; clone the sibling later if wanted. |

---

## 7. Phased plan

### Phase 0 — Decide & document (now)
- This plan (v0.1).
- **ADR** (next free number, ~0032): *"Deploy the paper stack on AWS EC2"* — records the new external-infra dependency, the SSH-tunnel posture, secrets-via-SSM, and the single-scheduler cutover rule (per repo convention: new external dependency ⇒ ADR).
- Deliverables drafted: `docker-compose.prod.yml`, EC2 user-data bootstrap script, systemd/cron units, CloudWatch config, cutover checklist.

### Phase 1 — Stand up the box (parallel run, scheduler **isolated**)
Goal: prove the box boots, builds arm64, fetches data Norton-free, serves the UI over the tunnel — **without touching the live books.**
1. You: launch t4g.medium, Ubuntu 24.04 (arm64), 30 GB gp3, SG = SSH-from-your-IP only, attach the SSM/S3 instance role, set TZ. (Commands in the runbook; run interactive bits via `! <cmd>`.)
2. user-data bootstrap (Phase 0 script): install Docker + compose plugin, set `TZ=America/New_York`, fetch SSM secrets → `/opt/workbench/.env`, `git clone` the repo, `docker compose build`.
3. **Isolation guard:** Phase 1 runs with a **scratch/empty DB** (no migrated strategies ⇒ scheduler has nothing to dispatch) and **paper creds pointed at a throwaway Alpaca paper account** (or none). The real DB is NOT restored yet.
4. Smoke: `/healthz` green on all services; SSH-tunnel into the UI; log in; confirm a live Alpaca data pull succeeds (the Norton win); load a strategy file; confirm the agent answers (Anthropic reachable).

### Phase 2 — Reliability
- Docker service enabled on boot; `restart: unless-stopped` already set.
- **CloudWatch Logs** for container stdout/stderr; **alarm** on "scheduler heartbeat missed before the open" + instance status-check.
- **Pre-open healthcheck** (cron/systemd-timer, ~08:00 ET): verify stack up + market-session gate sane before RTH (replaces the laptop's MarketHours healthcheck).
- **Backups:** nightly `backup_db.sh` → S3 (versioned); **DLM** daily EBS snapshot; weekly `verify_audit_integrity.py`.
- Re-home the OS tasks (table below).

### Phase 3 — Cutover (keep local running → cut off when AWS is ready)
See the checklist in §9. One stop-the-laptop → restore-on-EC2 → start-one-scheduler sequence.

### Phase 4 — Later (separate decisions)
- **RDS PostgreSQL** — trigger = recurring SQLite contention (the 201-symbol rebalance incident is the canary).
- **S3 evidence packages**, **Grafana/CloudWatch dashboards**.
- **Live trading** — its own ADR + 7-day cooldown, only after 2–4 clean paper weeks.

---

## 8. OS scheduled-task migration (Windows → Linux)

| Today (laptop) | On EC2 |
|---|---|
| `workbench-autostart.bat` (logon-start stack) | Docker enabled on boot + `restart: unless-stopped` — **the core fix** (no logon/sleep dependency). |
| `range-preopen-wake.ps1` | **Deleted** — no sleep to wake from. |
| `range-postrun-verify.ps1`, `range-barfreshness-diagnostic.ps1` | systemd-timer / cron at the ET times they used. |
| `register_*`/`weekly_live_evidence_refresh.ps1`, `weekly_range_calibration_refresh.ps1` | cron (weekly) → docs-only artifact (PR step stays manual or via a token). |
| `port001_first_rebalance_check.ps1` | cron one-shot / timer at the scheduled rebalance. |

> Convert each task's trigger time to **ET** (some were authored in CT). The in-app APScheduler keeps handling strategy rebalances; these timers are the *outer* health/verification/evidence jobs.

---

## 9. Cutover checklist (the careful part)

**Pre-flight (AWS proven in parallel, laptop still live):** Phase 1+2 green for ≥1 session; SSH tunnel works; data pull works; backups + alarms confirmed.

**Cutover window (pick a market-closed time — evening/weekend):**
1. **Freeze the laptop.** `docker compose down` on the laptop **and disable** `workbench-autostart` + the Windows scheduled tasks. ✅ *Now zero schedulers are running.*
2. **Snapshot the source of truth.** `scripts/backup_db.sh` on the laptop → copy `workbench.sqlite` (+ `strategies_user/`, optionally `bars_cache/`) to EC2 (scp over the tunnel or via S3).
3. **Confirm the master key matches.** `WORKBENCH_MASTER_KEY` in SSM == the laptop's value. (If not, the backend won't decrypt — stop and fix.)
4. **Restore on EC2.** Place the DB at `/opt/workbench/data/`, swap the throwaway paper creds for the real paper account, `docker compose up -d`.
5. **Verify integrity & identity.** `/healthz` green; `verify_audit_integrity.py` shows no *new* chain breaks; the UI lists the expected strategies, schedules, and accounts; positions reconcile against Alpaca.
6. **Confirm a single dispatcher.** EC2 scheduler is the only one armed (laptop is down). Watch logs through the **next scheduled rebalance** end-to-end before walking away.
7. **Laptop = warm standby** for 2–4 weeks: keep it patched and the pre-cutover snapshot retained, but its stack and tasks stay **disabled**.

**Hard rule:** at no point are the laptop and EC2 schedulers both armed against the live paper accounts.

---

## 10. Rollback

If EC2 misbehaves post-cutover: `docker compose down` on EC2 (disarm its scheduler) → bring the laptop stack back up from the **pre-cutover snapshot** → investigate offline. Because of the single-scheduler rule, rollback is symmetric and safe: only one side is ever armed. Retain the pre-cutover DB snapshot until live operation is signed off.

---

## 11. Risks & open items

- **arm64 build** — all deps (pandas/numpy/pyarrow/duckdb/cryptography) have arm64 wheels; build *on the instance* to avoid cross-compile. (Low risk; verified in Phase 1.)
- **2 GB would be tight** → chose 4 ␣GB t4g.medium; still add a 2–4 GB swapfile as a rebalance-spike cushion.
- **No rebalance idempotency** — the cutover guardrails cover the migration, but adding aggregate-level idempotency/risk-gating is a worthwhile *separate* hardening item (de-risks all future double-dispatch, not just cutover).
- **Frontend is the Vite dev server** (`Dockerfile.dev`). Fine for a single-user box over a tunnel; a prod build is a nice-to-have, not required for Phase 1.
- **Credit expiry** — confirm date; runway far exceeds need regardless.

---

## 12. Deliverables & division of labor

**I produce (Phase 0):** the ADR; a **CloudFormation template** (`deploy/aws/cloudformation/workbench-paper-stack.yaml`) that provisions the AWS environment (EC2 + IAM + SG + EIP + versioned S3 backup bucket + daily EBS-snapshot policy + budget alarm + log group) and injects the bootstrap as UserData; `docker-compose.prod.yml` (TZ, prod-leaning frontend, no source bind-mounts); the EC2 user-data bootstrap script (Docker + SSM fetch + clone + build, env-overridable so CFN drives it); systemd/cron units for the re-homed tasks; CloudWatch agent + alarm config; the SSM-parameter put commands; and the step-by-step launch/cutover runbook. *(CloudFormation provisions the **resources**; the bootstrap remains the single source of truth for **box config** — they compose, not overlap.)*

**You run (account-level — I can't provision AWS or do interactive logins):** create/verify the AWS account + IAM, put the SSM SecureString parameters, launch the instance, and execute the runbook commands (interactive ones via `! <cmd>` so output lands here).

---

## 13. Review additions folded in (v0.2)

Six items from the v0.1 review, with where each now lives:

1. **Scheduler heartbeat table/check before cutover.** New `scheduler_heartbeat` table (schema in ADR 0032 §Implementation) + `scripts/scheduler_health_check.py`. Makes the armed host observable and a double-arm detectable. **Backend code task — a Phase-2 prerequisite to cutover.**
2. **Manual "scheduler disabled" flag.** `WORKBENCH_SCHEDULER_ENABLED` (default `true`); the standby host runs it `false` so the laptop can stay installed but **inert**. This is the primary enforcement of the single-scheduler invariant. **Backend config task.**
3. **CloudWatch alarm for missed 09:00 / 10:00 / rebalance jobs.** Sourced from the heartbeat's `last_dispatch_at`; runbook Phase 2 §3.
4. **Post-cutover 3-day observation checklist.** Runbook Phase 3.5 (pre-open health, on-time dispatch, breaker sanity, audit chain, backups, cost) → sign-off gate before retiring the standby.
5. **Cost guardrail alarm.** AWS Budgets at $50/$150 per month (runbook §0) — a runaway signal, not a bill, since the credit covers ~24 months.
6. **Explicit "no live credentials on EC2" verification.** Hard pin `WORKBENCH_LIVE_TRADING_ALLOWED=false`; bootstrap aborts if any `ALPACA_LIVE_*` appears; verified at Phase 1 smoke and re-verified at cutover (runbook).

> The two **code** items (1, 2) are specified in ADR 0032 but **not yet implemented** — they are tracked Phase-2 tasks and are prerequisites to the Phase-3 cutover. Items 3–6 are infra/ops captured in the runbook.

---

*Status: v0.2 approved. Deliverables created — ADR 0032 (Draft), `deploy/aws/ec2-user-data.sh`, runbook. Remaining before cutover: implement the heartbeat table + scheduler flag (code), write `docker-compose.prod.yml`, then provision SSM + launch the t4g.medium.*
