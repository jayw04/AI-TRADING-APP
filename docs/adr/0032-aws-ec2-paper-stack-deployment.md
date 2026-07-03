# ADR 0032 — AWS EC2 deployment of the paper trading stack

| Field | Value |
|---|---|
| Date | 2026-06-29 |
| Status | Accepted (2026-06-29, owner review 9.9/10) |
| Phase | Operations (cross-phase) |
| Supersedes | — |
| Related | 0002 (single OrderRouter), 0003 (Fernet credentials), 0004 (circuit breaker), 0005 (activation cooldown), 0017 (OS trust store for outbound TLS), 0021 (operational recovery contract), 0031 (per-strategy paper account isolation) |

## Context

The platform currently runs entirely on the owner's laptop. That machine has become an operational liability: it sleeps (scheduled rebalances do not fire), restarts reset in-memory cache, intraday strategies miss bars when the stack is down during the regular session, and every paper book depends on the machine staying awake. These are infrastructure failures, not code failures, and they make debugging harder because a missed trade may be a sleeping host rather than a bug.

We need an always-on host for the **paper** stack (backend, scheduler, strategy engine, the two MCP servers, the agent, the SQLite DB, logs). The decision is not *whether* to move — the failures force it — but *where* and, more importantly, *how to cut over without double-trading*. Because there is currently **no rebalance idempotency** (root cause of the 2026-06-22 momentum-conservative leverage blowout, where a rebalance dispatched three times to ~3.8× leverage), the migration's central hazard is two hosts dispatching to the same Alpaca paper accounts at once. The hosting choice is secondary to getting that one thing right.

This ADR also fixes the platform's **deployment lifecycle** — the states a deployment moves through: *Development → Parallel Validation → Cutover → Production Paper → (later, a separate ADR) Live*. The work here is the transition into **Production Paper**; everything below is about making that transition safe and the resulting state reliable every trading day.

## Decision

Two invariants govern this migration; everything else serves them.

> **Invariant 1 — Single active scheduler.** Exactly one host holds the **ACTIVE** role at any moment; every other host is **STANDBY**. An ACTIVE host's scheduler is armed and may dispatch orders to the Alpaca paper accounts (`WORKBENCH_SCHEDULER_ENABLED=true`); a STANDBY host's scheduler is disabled and dispatch is *forbidden* (`=false`). **Two ACTIVE hosts on the same accounts is the failure this migration exists to prevent.**

Today the laptop is ACTIVE and EC2 is STANDBY; at cutover they swap. The roles are deliberately abstract — the swap works in either direction with no code change. The invariant is enforced by (a) the `WORKBENCH_SCHEDULER_ENABLED` arm flag, (b) a heartbeat that makes the ACTIVE host observable, and (c) cutover discipline (a host goes STANDBY before another goes ACTIVE).

> **Invariant 2 — Infrastructure-independent determinism.** A strategy running on EC2 with the same database, configuration, and market data must produce the **same decisions** it would have on the laptop. Infrastructure may change; trading behavior must not. This migration improves operational reliability — it does not alter research results or trading logic.

> This invariant generalizes beyond EC2 into the platform-wide principle **Infrastructure Independence**: *infrastructure must never change research or trading decisions* — bigger than any single host or cloud (see `docs/design/Platform_Principles.md`). ADR 0032 is its first concrete application.

In service of those invariants and the move:

1. **Host** the paper stack on a single always-on **EC2 `t4g.medium`** (2 vCPU / 4 GB, Ubuntu 24.04 arm64) in **`us-east-1`** (lowest latency to Alpaca + Anthropic and the broadest AWS service coverage), timezone **`America/New_York`**, with a small swapfile for rebalance spikes and NTP time sync (chrony) so cron fires on time.
2. **Access** is **SSH tunnel only** — every container stays bound to `127.0.0.1` and the security group allows inbound **SSH from the owner's IP only**. No app port is ever in a public ingress rule.
3. **Secrets** live in **AWS SSM Parameter Store (SecureString)**, fetched at boot into a root-only `/opt/workbench/.env`. The Fernet `WORKBENCH_MASTER_KEY` and the encrypted database are a **matched pair** and move together; a host without the matching key cannot decrypt broker credentials and refuses to boot (ADR 0003).
4. **No live broker credentials on EC2.** The box **SHALL remain technically incapable of live trading until a separate Live Deployment ADR is accepted**: `ALPACA_LIVE_*` are absent, the deploy pins `WORKBENCH_LIVE_TRADING_ALLOWED=false`, and the bootstrap aborts if any live secret is present. (A hard, verified incapability — stronger than "out of scope.")
5. **Scheduler arming is explicit.** **`WORKBENCH_SCHEDULER_ENABLED`** (default `true` = ACTIVE) gates job dispatch *and* resume-on-boot. A **STANDBY** host (the laptop, post-cutover) sets it `false` so it stays installed but inert. The arm state is recorded in the heartbeat and logged.
6. **A scheduler heartbeat** (`scheduler_heartbeat` table, below) records which `host_id` is armed and when it last dispatched, so the armed host is observable and an accidental double-arm is detectable. This is a **prerequisite to cutover**, not a post-move nicety.
7. **Migrate by parallel-run then a single cutover.** Phase 1 stands up EC2 with a **scratch/empty DB** and a **throwaway paper account** (scheduler effectively idle — nothing to dispatch) to prove data access, tunnel, health, backups, and logs. The real DB is restored **only** during the cutover window, immediately after the laptop is stopped. **Cutover SHALL NOT proceed until the heartbeat confirms exactly one ACTIVE scheduler for one complete trading session** (`scheduler_health_check.py` green) — the heartbeat is part of the gate, not just telemetry.
8. **Promotion acceptance.** EC2 is "Production Paper" only after a **2-week observation with no missed schedules, no cache-loss-on-restart incidents, and no unplanned restarts**; until then the laptop is a retained warm standby (the rollback target). Live trading is a further, separate ADR.

## Rationale

**Why EC2 over the alternatives.** Lightsail is simpler and bundles pricing, but it gives less control over IAM, SSM, EBS snapshots, and networking — all of which this migration leans on (instance role for SSM/S3, snapshot lifecycle, locked-down SG). ECS/Fargate and Lambda are wrong-shaped: the stack is stateful (SQLite on a volume), long-running (scheduler, MCP SSE servers, agent), and single-tenant — there is nothing to autoscale and a lot to make harder. A plain VM matches the already-Dockerized, `restart: unless-stopped` stack almost exactly, so this is a re-home, not a re-architecture. The $990 of AWS credit makes the ~$35/mo cost irrelevant to the choice; control and a clean path to future production win.

**Why SSH tunnel, not a public endpoint.** This is a broker-credentialed trading app for a single operator. Exposing any app port to the internet trades a large attack surface for convenience that an SSH port-forward already provides. The containers are *already* loopback-bound, so the tunnel posture is the path of least change and least risk. A VPN (Tailscale/WireGuard) is a reasonable future UX upgrade; it is not needed to start.

**Why SSM, and why the key/DB pairing is load-bearing.** Broker credentials are Fernet-encrypted in the DB (ADR 0003); the master key is the single thing that makes them usable. Baking it into an AMI or user-data plaintext would leak it into snapshots and logs; SSM SecureString + an instance role scoped to `/workbench/prod/*` keeps it out of git, images, and shell history. The non-obvious failure mode — and the reason this is in the *Decision*, not a footnote — is that moving the DB **without** the same key silently breaks decryption and the backend won't trade. Key and DB are one artifact in two files.

**Why the single-scheduler invariant is enforced by flag + heartbeat + discipline, and not a lock.** The clean engineering answer would be a shared lease/lock that only one host can hold. But the laptop and EC2 deliberately have *separate* databases (the DB moves at cutover), so there is no shared coordination point to lock against without introducing one prematurely. Given that, the honest mechanism is: an explicit arm/disarm flag (so a host is inert by choice), a heartbeat with `host_id` (so the armed host is *visible* and a double-arm is *detectable*), and a cutover sequence that stops the old host before arming the new one. We accept that this is procedural rather than airtight; the heartbeat is the safety net that catches a procedural slip. A true cross-host lock becomes possible — and worth it — when/if the DB moves to RDS (Phase 4).

**Why scratch-DB-first.** The real DB carries the live schedules; restoring it on EC2 while the laptop is still armed would immediately create the two-armed-schedulers hazard. Running Phase 1 against an empty DB means the EC2 scheduler has nothing to dispatch no matter what, so we can prove the whole platform (data, tunnel, health, backups, logs, agent) with zero risk to the running books. The real DB is the *last* thing to move, under the controlled cutover.

## Implementation notes

**Scheduler arm flag** — config setting `WORKBENCH_SCHEDULER_ENABLED` (env, default `true`). When `false`, the scheduler service starts but registers/dispatches no jobs and logs `scheduler_disarmed`. On every startup the backend audit-logs `scheduler_arm_state` with the resolved value and `host_id`. The laptop, post-cutover, runs with this `false`.

**Scheduler heartbeat** — new table (Alembic migration `f3a1c7e9b2d4`; additive, reviewed):

```
scheduler_heartbeat(
  host_id          TEXT      PRIMARY KEY,  -- stable host identity (below)
  armed            BOOLEAN   NOT NULL,     -- WORKBENCH_SCHEDULER_ENABLED at this beat
  last_beat_at     TIMESTAMP NOT NULL,     -- refreshed every ~30s on the ACTIVE host
  last_dispatch_at TIMESTAMP,             -- forward-ready (OrderRouter hook); may be NULL
  code_version     TEXT                   -- git short-sha / app version: WHICH code dispatched
)
```

**Host identity (R4):** `host_id` is the explicit human-friendly `WORKBENCH_HOST_ID` (set in the prod overlay, e.g. `ec2-paper`) if present, else a **persisted `hostname-<uuid8>`** under `data/host_id` — a bare hostname can change, the persisted id does not. The ACTIVE host upserts each tick; `code_version` (R-heartbeat) makes "which code was dispatching" immediate when debugging.

`scripts/scheduler_health_check.py` (stdlib only) backs the CloudWatch alarm and the cutover gate — exit `0` (one fresh ACTIVE host), `1` (none), `2` (**double-arm**), `3` (db unreadable). The heartbeat is a **prerequisite to Phase 3 cutover**.

**Backups & time:** daily EBS snapshot + `backup_db.sh` → S3 (versioned), and **restore is periodically tested** — an unrestorable backup is an untested assumption (R7). The instance clock is kept in sync via chrony/NTP so the scheduler fires on time.

**No-live-creds pin** — deploy sets `WORKBENCH_LIVE_TRADING_ALLOWED=false`; backend refuses to arm if any `ALPACA_LIVE_*` is present while the pin is false. Cutover and boot both verify (runbook step): the resolved broker base URL is `paper-api.alpaca.markets` and no live secret exists in `/opt/workbench/.env` or SSM under `/workbench/prod/`.

**Secrets (SSM SecureString, `/workbench/prod/*`):** `WORKBENCH_MASTER_KEY` (critical, == the DB's key), `ANTHROPIC_API_KEY`, `WORKBENCH_MCP_KEY`, `AGENT_API_KEY`, `MCP_BACKEND_TOKEN`. Instance role: `ssm:GetParameter*` on `/workbench/prod/*` + `s3:PutObject` on the backup bucket only.

**Compose/profile:** a `docker-compose.prod.yml` overlay sets `TZ=America/New_York` on every service and the two flags above; keeps `restart: unless-stopped`; drops the frontend source bind-mount (prod-leaning). Docker is enabled on boot. Build **on the instance** (native arm64).

**Migration artifacts:** `Docs/implementation/TradingWorkbench_AWS_Migration_Plan_v0.2.md` (plan) and `Docs/runbook/aws-migration.md` (launch + cutover + 3-day observation + rollback). Bootstrap: `deploy/aws/ec2-user-data.sh`.

**Audit chain:** after any DB restore, run `scripts/verify_audit_integrity.py`; two benign pre-existing chain breaks are expected — verify no *new* ones (ADR P5 §8 immutability).

## Consequences

**Positive.** Scheduled jobs no longer depend on a laptop being awake; cache survives the host being long-lived; intraday strategies have an always-on engine before the open. The Norton TLS MITM that blocks `data.alpaca.markets` on the laptop (ADR 0017) is absent on EC2 — live data and parquet generation work natively. There is one canonical host and one source of truth.

**Negative.** AWS becomes a new external operational dependency (account, IAM, SSM, snapshots to maintain). Access via SSH tunnel is slightly less convenient than opening a browser tab. A single instance is a single point of failure until restore-from-snapshot is exercised; mitigated by daily EBS snapshots + S3 DB backups and a documented restore. During the standby window two code copies (laptop + EC2) exist and must not drift. The single-scheduler guarantee is procedural + detective, not a hard lock — accepted until a shared DB (RDS) makes a true lease possible. arm64 build must be verified (low risk; all deps have arm64 wheels).

**Neutral.** SQLite stays for the controlled single-node paper environment — a deliberate single-node *optimization*, not a production *limitation* (it is fast, simple, and backup-trivial for one writer); the move does not change the DB engine. The TradingView **desktop** MCP automation remains on the laptop (a research tool, not part of the paper stack).

## Alternatives considered (not chosen)

- **AWS Lightsail.** Simpler, bundled pricing. Rejected: weaker control over IAM/SSM/snapshots/SG that this migration depends on; the owner explicitly prefers EC2's path to future production. Reconsider if the IAM/networking control turns out to be unused overhead.
- **ECS/Fargate or Lambda (serverless).** Rejected: the stack is stateful (SQLite volume), long-running (scheduler, SSE MCP servers, agent), and single-tenant — nothing to autoscale, much to complicate. Reconsider only if the platform becomes multi-tenant.
- **Keep the laptop, prevent sleep / add a UPS.** Rejected: does not address restart-driven cache loss, single-machine fragility, or the Norton data block; the failure *class* remains. The reliability gap is structural, not a power-management setting.
- **Public HTTPS endpoint behind a locked security group.** Rejected for the start: exposes a broker-credentialed app to the internet for convenience the SSH tunnel already provides. Reconsider as a VPN (Tailscale/WireGuard) UX upgrade, never as open ingress.

## Re-evaluation triggers

- **A move to RDS PostgreSQL** is triggered by *any* of: recurring SQLite write contention (the 201-symbol simultaneous-rebalance pattern), a high-availability requirement, or multi-user / multi-writer access — at which point a real cross-host scheduler **lease** replaces the procedural single-active rule.
- **Single-instance downtime causes a missed session** that snapshot-restore does not cover quickly enough → revisit auto-recovery / multi-AZ / standby-instance posture.
- **A decision to trade live** → new ADR; the `WORKBENCH_LIVE_TRADING_ALLOWED` pin and the live-creds-absent rule flip only under the existing live opt-in gate (ADR 0006 v2 / 0007) and its cooldown (ADR 0005).
- **A scheduler double-arm is ever detected** by the heartbeat check → treat as an incident; harden from procedural toward a hard lock sooner than Phase 4.
- **AWS credit nears exhaustion or a budget alarm fires** → revisit instance sizing / reserved pricing (not expected within the ~24-month runway).
