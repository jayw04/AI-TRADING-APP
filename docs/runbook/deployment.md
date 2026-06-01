# Deployment Runbook — Fresh Box (P5 §8.6)

From "fresh Linux box with Docker" to "first paper order submitted" in roughly
60 minutes for a competent operator. This is the operating manual for the
workbench.

> **Local-dev note.** The development box is Windows with no Docker and Norton
> SSL inspection (which blocks `data.alpaca.markets`). The steps below are the
> **Linux/Docker deployment** path; the live broker steps run on a non-Norton
> host (a deploy box, WSL, or CI). See `docs/runbook/` siblings for the local
> story.

## Prerequisites

- Linux host (Ubuntu 22.04+; tested on 24.04).
- Docker Engine 24+ with the Compose plugin.
- 2 vCPU, 4 GB RAM, 20 GB disk minimum.
- Outbound network to: `api.alpaca.markets`, `paper-api.alpaca.markets`,
  `api.anthropic.com` (agent, optional), `github.com`.
- Inbound: the stack binds to `127.0.0.1` only (backend `:8000`, MCP `:8765`,
  frontend dev `:5173`). For external access, terminate TLS at a reverse proxy
  (Caddy/nginx) that proxies to `127.0.0.1:8000`. **The workbench does not bind
  public IPs.**

## Step 1 — Clone

```bash
cd /opt
sudo git clone https://github.com/jayw04/AI-TRADING-APP.git workbench
sudo chown -R "$USER:$USER" workbench
cd workbench
git checkout p5-complete    # or p5-session8-complete during bring-up
```

## Step 2 — Master key

Generate a 44-char Fernet key and put it in the repo-root `.env` (gitignored):

```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
# add the output to .env:
#   WORKBENCH_MASTER_KEY=<paste>
chmod 600 .env
grep -E "^\.env" .gitignore    # confirm .env is ignored
```

> Loss of the master key **and** the DB is unrecoverable. Loss of the key alone
> is recoverable: rotate it and re-enter credentials. See
> `docs/runbook/credentials.md`.

## Step 3 — Data directory

```bash
mkdir -p data/backups
chmod 700 data data/backups
```

The data dir holds the SQLite DB (with Fernet-encrypted credentials) and the
daily backups — owner-only.

## Step 4 — Start

```bash
docker compose up -d
docker compose logs -f backend
```

Expect a clean boot:

```
crypto_master_key_verified
broker_registry_adapter_loaded  (none yet on a fresh install)
scheduler_started
activation_completion_scheduled
metrics_snapshot_scheduled
daily_backup_scheduled
lifespan_startup_complete
```

`master_key_missing_or_invalid` → the backend `sys.exit(1)`s; fix `.env` and
restart.

## Step 5 — Verify `/healthz`

```bash
curl -s http://127.0.0.1:8000/healthz | jq
```

On a fresh install expect **`status: "ok"`** with `broker_registry: "no_accounts"`:

```json
{
  "status": "ok",
  "db": "ok",
  "checks": {
    "database": "ok",
    "master_key": "ok",
    "broker_registry": "no_accounts",
    "scheduler": "ok",
    "circuit_breakers_clear": "ok"
  },
  "version": "...",
  "uptime_seconds": 12
}
```

`status` is `degraded` if a circuit breaker is tripped (still served, 200) and
`fail` only if the DB is unreachable or the master key is bad (503).

## Step 6 — First user

```bash
docker compose exec backend python scripts/create_user.py
```

Follow the prompts. **Save the TOTP secret (QR / base32) in your authenticator
immediately** — it is not shown again. Log in at `http://127.0.0.1:5173` (or
behind your proxy) with email + password + TOTP code.

## Step 7 — Paper credentials

UI → `Settings → Credentials`. Set the Alpaca **paper** key + secret (from the
Alpaca paper dashboard). Optionally set the Anthropic key (agent) and the
TradingView Pine webhook secret.

## Step 8 — Paper account

UI → `Settings → Accounts → Create account`: `mode=paper`, `broker=alpaca`.
Refresh `/healthz` — `broker_registry` should now read `ok`.

## Step 9 — Smoke test

UI → Trade page → select the paper account → `AAPL`, BUY, MARKET, qty 1, DAY →
submit. The order should accept with a populated `broker_order_id` (check the
Orders page). If it rejects, see `docs/runbook/on-call.md` ("Orders are slow",
risk-limit entries).

## Step 10 — Reverse proxy (production only)

Terminate TLS at a proxy that forwards to `127.0.0.1:8000`. Example Caddy:

```
workbench.example.com {
    reverse_proxy 127.0.0.1:8000
}
```

`/healthz` and `/metrics` are reachable through the proxy or directly on
`127.0.0.1:8000`. **Do not expose `/metrics` publicly** — it includes strategy
and account counts (bind it to the scrape host or an allow-listed path).

## Step 11 — Backups

Daily backups run at 02:00 (scheduler timezone). After a day:

```bash
ls -la data/backups/        # expect workbench-YYYY-MM-DD.sqlite per day
docker compose exec backend bash scripts/backup_db.sh   # run on demand
docker compose exec backend python scripts/verify_audit_integrity.py
# expect: "Verified N rows; 0 errors."
```

Restore (backend must be stopped first): `./scripts/restore_db.sh <backup>`.

## What you have now

- Backend on `127.0.0.1:8000` (or behind your proxy); one TOTP-enrolled user;
  one paper account with credentials; daily backups; subsystem `/healthz`;
  Prometheus `/metrics`; immutable, hash-chained audit log.
- All P5 CI invariants enforced (6 shell + ADR-0002 pytest + audit-immutability
  pytest + 3 coverage gates).

Next: `docs/runbook/credentials.md`, `risk-gates.md`, `activation.md`,
`on-call.md`.

> **A note on scale.** SQLite WAL + APScheduler in-process is single-host,
> single-instance by design (ADRs / CLAUDE.md). The `audit_log` hash chain's
> atomic insert relies on SQLite's single-writer guarantee; moving to Postgres
> would require switching that to a sequence + advisory lock. Multi-instance HA
> is out of scope for P5.
