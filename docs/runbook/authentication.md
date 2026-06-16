# Authentication

The workbench requires authentication for all API endpoints (except the public
`/api/v1/auth/login` and `/api/v1/auth/login-config` endpoints) and all WebSocket
connections. This shipped in P5 §3 and replaced the P0 stub (which returned a
fixed `user_id=1`).

## Auth model

- **Password** (bcrypt, cost 12) + **TOTP** (RFC 6238, 6-digit code, 30s window,
  ±1 window of clock-skew tolerance).
- **Server-side sessions** with a 14-day rolling expiry. Cookie-based: the
  cookie holds a 256-bit random token; the DB stores only its SHA-256 hash.
- **No self-signup.** The CLI script bootstraps each user.

## Bootstrap (first user, or any new user)

The bootstrap script runs directly against the configured database — no Docker
required. Run it with the backend virtualenv from the repo root:

```bash
# Windows
apps/backend/.venv/Scripts/python.exe scripts/create_user.py
# Linux / macOS
apps/backend/.venv/bin/python scripts/create_user.py
# inside the container, if you run the Docker stack
docker compose exec backend python scripts/create_user.py
```

The target database must already be migrated to head:

```bash
cd apps/backend && .venv/Scripts/python.exe -m alembic upgrade head
```

Prompts (or pass `--email` / `--display-name` to skip them):

- Email (lowercased automatically)
- Display name (optional)
- Password (typed twice; not echoed)

The script hashes the password, generates a TOTP secret (marked verified — the
operator just saw it), writes a QR code PNG to `./totp_<id>.png`, and prints the
`otpauth://` URI. Scan the QR (or paste the URI) into your authenticator app
(Google Authenticator, Authy, 1Password, Bitwarden, …).

> **The QR PNG embeds the TOTP secret.** It is git-ignored (`totp_*.png`).
> Delete it once you've enrolled; never commit or share it.

## Logging in

Open the frontend (`http://127.0.0.1:5173`) — any route redirects to `/login`
until you authenticate. Enter email + password + the current TOTP code.

On success a `workbench_session` cookie is set (`httpOnly`, `SameSite=Strict`,
`Secure` everywhere except localhost, 14-day max-age). In dev, Vite proxies
`/api` and `/ws` to the backend so the browser sees a single origin and the
cookie flows without CORS-credentials configuration.

## Rotating your password

Re-run `scripts/create_user.py` with the same email. The script detects the
existing user and overwrites the password hash + TOTP secret. Scan the new QR.
Old TOTP codes stop working immediately; existing sessions remain valid until
they expire or are revoked.

## Session lifetime

- **Rolling expiry**: 14 days since `last_used_at`. Each authenticated request
  (HTTP or WS connect) rolls `last_used_at` and `expires_at` forward.
- A session continuously used never re-auths; one idle for two weeks is forced
  to log in again.

## Revoking a session

While logged in:

```
POST /api/v1/auth/sessions/{session_id}/revoke
```

`GET /api/v1/auth/me` returns your current `session_id`. A "my sessions" UI is
deferred to a later phase; for now query the `sessions` table directly to find
other sessions' ids.

## Rate limiting

- 5 failed login attempts per IP in 15 minutes → 429.
- The 6th attempt triggers a 60-minute cooldown for that IP.

The limit is in-memory and per-process; a backend restart resets it. Acceptable
for the single-tenant threat model. A multi-instance deployment would need a
shared (e.g. Redis) limiter.

## WebSocket auth

The `/ws` upgrade requires the same session cookie. Without a valid session the
gateway closes the socket with application close code **4401** (mirrors HTTP
401) before any messages flow.

## What's NOT in P5 §3

- Password reset via email — use the CLI script.
- Backup/recovery codes for TOTP — use the CLI script to regenerate.
- OAuth / SSO / SAML / magic links.
- Per-user roles or permissions — every user has full access to their own data.

## Login TOTP toggle (`WORKBENCH_LOGIN_TOTP_REQUIRED`)

Default **`true`** (conservative): `/auth/login` requires a valid TOTP code in
addition to the password. Set `WORKBENCH_LOGIN_TOTP_REQUIRED=false` in `.env` and
restart the backend to log in with **password only** — a single-user localhost
convenience. The login page reads `GET /api/v1/auth/login-config` (public,
pre-auth) and hides the TOTP field when it's off.

**Scope: login only.** Step-up TOTP on consequential actions is **always**
enforced regardless of this flag — LIVE account creation, strategy activation,
LLM opt-in, and live auto-dispatch each verify a fresh code independently. Turn
this off only on a trusted, single-user, localhost-bound machine; leave it on
(or set it back on) for anything exposed beyond `127.0.0.1`.

## Security notes

- The TOTP secret is stored in **plaintext** in P5 §3. P5 §4 wraps it in Fernet
  encryption alongside the broker API credentials (the column is renamed to
  `totp_secret_ciphertext` then).
- The `sessions` table stores SHA-256 token hashes (not bcrypt) — auth lookup
  happens on every request and a 256-bit random token isn't dictionary-attackable.
- CSRF defense is `SameSite=Strict` on the cookie, sufficient for a same-origin
  SPA. Multi-origin embedding (a later phase) would need explicit CSRF tokens.
