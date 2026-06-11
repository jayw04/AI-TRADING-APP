# Runbook — Credential Encryption (P5 §4)

This runbook covers the Fernet-based encrypted credential store introduced in
P5 §4: master-key handling, the per-credential lifecycle, leak response, TOTP
rotation, and how to inspect credential metadata without decrypting.

> **One-line summary:** every per-user secret (broker keys, Anthropic key, Pine
> webhook secret, TOTP secret) is encrypted at rest with a single Fernet master
> key held in the `WORKBENCH_MASTER_KEY` environment variable. The DB holds only
> ciphertext; the master key lives outside the DB.

---

## 1. The master key

### What it is
- A 32-byte random key, URL-safe base64-encoded → a 44-char string ending in
  `=`. It is a Fernet key (AES-128-CBC + HMAC-SHA256), not raw AES bits.
- Stored in `WORKBENCH_MASTER_KEY`. The backend reads it from the **process
  environment** (not via pydantic settings), so it must be exported into the
  environment of every process that touches secrets: the backend, the Alembic
  migration, and `scripts/create_user.py`.

### Generating
```bash
apps/backend/.venv/Scripts/python.exe scripts/generate_master_key.py   # Windows
apps/backend/.venv/bin/python scripts/generate_master_key.py           # Linux/macOS
```
Copy the output into `.env` as `WORKBENCH_MASTER_KEY=<key>`. `.env` is
git-ignored (`.env*` in `.gitignore`) — **never commit it**.

### How it reaches each process
- **Backend (docker compose):** `env_file: .env` exports every line into the
  container environment, so `os.environ["WORKBENCH_MASTER_KEY"]` resolves.
- **Backend (local):** `./scripts/dev.sh` / your shell must have the variable
  exported. If it's missing, the backend **refuses to boot** (`sys.exit(1)`
  with `master_key_missing_or_invalid` logged). There is no degraded mode.
- **Migration & `create_user.py`:** export `WORKBENCH_MASTER_KEY` in the shell
  before running them, e.g. `export WORKBENCH_MASTER_KEY=$(grep ^WORKBENCH_MASTER_KEY= .env | cut -d= -f2-)`.

### Backup
- Back up the master key **separately** from the database backup. The whole
  point is that a DB dump alone leaks no working credentials; storing the key
  next to the DB backup defeats that.
- Treat it like a production root password: never log it, never paste it into
  chat, store it in a password manager / secrets vault.

### Rotation (manual; not automated in §4)
Rotating the master key means re-encrypting every existing ciphertext:
1. Stand up the new key alongside the old.
2. For each `user_credentials` row: decrypt with the old key, encrypt with the
   new key, write back.
3. Swap `WORKBENCH_MASTER_KEY` to the new key and restart the backend.

A `scripts/rotate_master_key.py` helper is **documented here but not part of the
§4 MVP** — scheduled rotation is P5+ polish. Until it ships, rotation is a
careful one-off operation against a backed-up DB.

---

## 2. Per-credential lifecycle

```
Not set ──set()──▶ Active ──revoke()──▶ Revoked ──(7 days)──▶ Hard-deleted
   ▲                  │
   └──────set()───────┘   (rotate: overwrites ciphertext in place)
```

- **Set / rotate** (`CredentialStore.set`): inserts or overwrites the active
  ciphertext for `(user_id, kind)`. No history is kept — rotation must actually
  reduce the attack surface, so the prior ciphertext is gone.
- **Revoke** (`CredentialStore.revoke`): soft-delete. `revoked_at` is stamped;
  `get()` returns `None` immediately, but the ciphertext lingers for **7 days**
  (`REVOKED_RETENTION`) so an accidental revoke can be recovered.
- **Hard-delete** (`CredentialStore.hard_delete_revoked`): the daily scheduled
  cleanup removes rows revoked more than 7 days ago.

The credential kinds: `alpaca_paper_key`, `alpaca_paper_secret`,
`alpaca_live_key`, `alpaca_live_secret`, `anthropic_api_key`,
`pine_webhook_secret`, `totp_secret`, and the two service bearer tokens
`workbench_mcp_key` (P5.5 §3) and `agent_api_key` (P6 §1a).

---

## 2a. Service bearer tokens (`workbench_mcp_key`, `agent_api_key`)

Two credential kinds are **bearer tokens that a sidecar service presents to the
backend HTTP API**, resolved back to the owning user by
`app/auth/stub.py::_resolve_from_bearer_token`:

- `workbench_mcp_key` — the read-only `workbench-mcp` server (SSE on :8766).
  **Reused by the chart-data `mcp-server` (Streamable HTTP on :8765)**, whose
  user-scoped read tools (`get_account_state`, `list_strategies`, …) call the
  backend's `/api/v1/account` etc. and need a user-resolving bearer (P3 / ADR
  0016). So one `WORKBENCH_MCP_KEY` value authenticates **two** containers.
- `agent_api_key` — the proposal-generation `agent` service.

These differ from broker/Anthropic keys in one critical way: **they live in two
places that must stay in sync.**

1. **Backend DB** — the encrypted `CredentialStore` entry, so the backend
   accepts the bearer token (`GET /api/v1/users/me/credentials/` etc.).
2. **`.env`** — `WORKBENCH_MCP_KEY` / `AGENT_API_KEY`, which `docker compose`
   injects into the sidecar container so it knows what token to send.

If the two diverge, the sidecar sends a token the backend doesn't recognize and
every call 401s. The `workbench-mcp` server additionally **refuses to boot**
(`RuntimeError: WORKBENCH_MCP_KEY env var required`) if its env var is empty —
so a missing key shows up as a crash-looping container, not a silent failure.

### Generate / register a `workbench_mcp_key`

There is no dedicated CLI; mint a random value and write it to both sides with
the same secret:

```bash
# 1. Generate a strong token.
KEY=$(python -c "import secrets; print(secrets.token_urlsafe(32))")

# 2. Register it in the backend DB for the dev user (runs inside the container).
docker compose exec -T -e WBKEY="$KEY" backend python - <<'PY'
import asyncio, os
from sqlalchemy import select
from app.config import get_settings
from app.db.models import User
from app.db.session import get_sessionmaker
from app.security.credential_store import CredentialKind, CredentialStore

async def main():
    s = get_settings()
    async with get_sessionmaker()() as session:
        user = await session.scalar(select(User).where(User.email == s.dev_user_email))
        store = CredentialStore(session)
        await store.set(user.id, CredentialKind.WORKBENCH_MCP_KEY, os.environ["WBKEY"])
        await session.commit()
        print("stored_ok=", await store.get(user.id, CredentialKind.WORKBENCH_MCP_KEY) == os.environ["WBKEY"])

asyncio.run(main())
PY

# 3. Put the SAME value in .env, then recreate the container.
#    WORKBENCH_MCP_KEY=<value of $KEY>
docker compose up -d --force-recreate workbench-mcp
```

Verify end-to-end (200 with the key, 401 without):

```bash
curl -s -o /dev/null -w "%{http_code}\n" \
  -H "Authorization: Bearer $KEY" \
  http://localhost:8000/api/v1/users/me/credentials/
```

### Rotating from the UI

The Settings → Credentials page (`workbench_mcp_key` card) only updates the **DB**
side. After a UI rotate you **must** also update `WORKBENCH_MCP_KEY` in `.env`
and recreate **both** containers that present it —
`docker compose up -d --force-recreate workbench-mcp mcp-server` — or the stale
token keeps 401ing (the `mcp-server` chart-MCP receives it via an explicit
`WORKBENCH_MCP_KEY: ${WORKBENCH_MCP_KEY:-}` passthrough in `docker-compose.yml`).
The same applies to `agent_api_key` / `AGENT_API_KEY` and the `agent` service.

---

## 3. Leak scenarios

| What leaked | Exposure | Action |
|---|---|---|
| **Master key only** (DB safe) | Nothing directly — the attacker needs ciphertext too. | Rotate the master key at the next maintenance window. Audit how it leaked. |
| **DB only** (master key safe) | Usernames + audit log. **No working credentials** — every secret is ciphertext. | Restore from a clean state if tampered; no credential rotation strictly required, but rotate as a precaution. |
| **Both** | Every secret is recoverable. | Treat as full compromise: rotate **every** credential (broker keys at the broker, Anthropic key at Anthropic, regenerate Pine secrets, re-enroll TOTP) AND generate a new master key. Revoke broker API keys at the source first. |

Root-on-the-host is explicitly out of scope: an attacker who can read process
memory can read the master key regardless of encryption.

---

## 4. TOTP rotation

TOTP is **not** managed by the generic credentials API (`PUT/DELETE
/api/v1/users/me/credentials/totp_secret` both return 400). The user-facing
surfaces are:

- **Initial setup / rotation:** `scripts/create_user.py` (writes the secret to
  the store via `CredentialStore.set(user_id, TOTP_SECRET, ...)` and marks
  `users.totp_verified_at`). Requires `WORKBENCH_MASTER_KEY` exported.
- **Self-service enrollment:** `POST /api/v1/auth/totp/setup` + `POST
  /api/v1/auth/totp/verify` (P5 §3 endpoints, now backed by the store).

`users.totp_verified_at` remains a plaintext column — it's a non-secret status
flag, not the secret. The secret itself is ciphertext in `user_credentials`.

---

## 5. Inspecting credential metadata

You can see *what* is set and *when* it was used, but you **cannot** read
plaintext without the master key.

```bash
sqlite3 apps/backend/data/workbench.sqlite \
  "SELECT user_id, kind, created_at, updated_at, last_used_at, revoked_at,
          length(ciphertext) AS ct_len
   FROM user_credentials ORDER BY user_id, kind;"
```

- `ct_len` shows the ciphertext is present and non-trivial; the bytes are opaque.
- Forensic check: `Fernet.extract_timestamp(token)` reveals when a credential
  was originally encrypted — compare against `created_at` if you suspect
  tampering.

The API surface (`GET /api/v1/users/me/credentials/`) returns the same metadata
(set/not-set + timestamps) and **never** returns plaintext.

---

## 6. Emergency downgrade (do not use routinely)

The §4 migration's `downgrade()` restores the plaintext `users.totp_secret` /
`users.pine_webhook_secret` columns by decrypting the stored ciphertext. It is
an **emergency-only** path: after a downgrade, treat the DB as a
"secrets-in-plaintext / data-is-leaked" state and rotate every credential
immediately. It requires `WORKBENCH_MASTER_KEY` to decrypt.
