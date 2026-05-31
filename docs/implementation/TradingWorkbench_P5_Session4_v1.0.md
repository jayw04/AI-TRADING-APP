# P5 Session 4 — Credential Encryption: Per-User Secrets at Rest

| Field | Value |
|---|---|
| Document version | **v1.0** (frozen for execution; supersedes v0.1 — see "Why v1.0" below) |
| Date | 2026-05-31 |
| Phase | **P5 — Live Trading**, **§4** (entirely) |
| Predecessor | `TradingWorkbench_P5_Session3_v0.1.md` (tag `p5-session3-complete`, PR #39 at `66c19b0`) — with Session 3 Results adjustments folded in below |
| Repository | `github.com/jayw04/AI-TRADING-APP` |
| Scope | Introduce Fernet-based encryption for per-user secrets at rest. New `user_credentials` table holds ciphertexts keyed by `(user_id, kind)`. Master key in `WORKBENCH_MASTER_KEY` env var. Migrate four secret families: TOTP secret (from `users.totp_secret`), Pine webhook secret (from `users.pine_webhook_secret`), broker API keys (env → store), Anthropic API key (env → store). `credentials_for_mode()` in `app/brokers/alpaca/credentials.py` — the P5 §2 swap-point — swaps from env-var lookup to credential-store lookup; the function becomes async, callers propagate the `await`. Settings UI shows credential metadata (masked). New CI invariant `check_no_env_credentials.sh` (eighth invariant). The old `users.totp_secret` and `users.pine_webhook_secret` columns are dropped after the data migration completes. Bundle the `app/auth/future.py` deletion (Session 3 close-out). Single PR. |
| Estimated wall time | 5 hours |
| Stopping point | `git tag p5-session4-complete` |
| Out of scope | KMS / Vault / cloud secret stores. Hardware security modules. Key rotation automation (manual rotate is supported; scheduled rotation is P5+ polish). Per-credential expiry / rotation reminders. Audit-trail of read access (writes are audited; reads aren't — too chatty, mostly noise). Decryption performance benchmarking. Credential sharing between users (multi-user MVP is single-user-per-tenant). Rename of `app/auth/stub.py` (filename is now a misnomer per Session 3 Results, but renaming touches dozens of imports — defer to a hygiene PR). |

---

## Why v1.0 (drift from v0.1 — verified against the shipped Sessions 1, 2, 3)

The v0.1 doc (2026-05-23) was written before Sessions 1, 2, and 3 actually shipped. The core design holds, but eleven facts have drifted. Each item below is verified against `main` at `p5-session3-complete` (`66c19b0`) via Session Zero Results, Session 2 Results, and Session 3 Results.

1. **`uv` is not on PATH in this environment.** Use `apps\backend\.venv\Scripts\python.exe` for pytest, alembic, and any tool invocations. Pytest needs `--cov-branch` or the risk gate falsely reports 0.000 (same gotcha Session 2 hit).
2. **Repo paths are Windows.** Working directory is `C:\LLM-RAG-APP\ai-trading-app`, not `~/code/AI-TRADING-APP`. Bash invocations of CI scripts still work (Git Bash on Windows); Python invocations use the venv.
3. **`scripts/create_user.sh` does not exist; it is `scripts/create_user.py`.** Session 3 shipped a standalone Python script (argparse + `getpass`) instead of the planned bash-wrapping-docker-compose-exec approach. Runs directly against the backend session factory, Docker-free, supports `--email`, `--display-name`, `--db-url`. Any v0.1 reference to `create_user.sh` is wrong in v1.0.
4. **`app/auth/stub.py` filename is preserved but the body is real auth.** Session 3 kept the filename to avoid renaming dozens of import sites. The file is no longer a stub; its docstring records this. Session 4 touches it via §4.9 (TOTP read swap); no rename in this session.
5. **`_aware()` datetime coercion lives in `stub.py`.** Session 3 added this because SQLite round-trips timezone-aware datetimes as naive. Session 4's `CredentialStore` does similar datetime comparisons (`last_used_at`, `revoked_at < cutoff`) — must handle the same coercion. See §4.3 below.
6. **`app/auth/internal.py` exists and is unrelated.** Session 3 shipped a shared-secret (`X-Workbench-Auth` / `MCP_BACKEND_TOKEN`) dependency for service-to-service MCP calls. Distinct from the credential store, which is for per-user secrets at rest. Session 4 does NOT manage `MCP_BACKEND_TOKEN` — that stays as an env var (service-to-service, not user-facing).
7. **`app/auth/future.py` is stale and should be deleted.** Session 3 Results punch list. It still reads "P0 ships with a single seeded dev user (id=1)" — a comment that's no longer accurate. Session 4 bundles the deletion (one-line addition to §4.16's git-add list).
8. **CI invariant count is seven, not the "seven + check_adr0002.sh" v0.1 assumed.** Session Zero Results confirms: `check_adr0002.sh` does NOT exist. ADR 0002 is enforced by `tests/test_adr_0002_invariant.py` + the `_router_token` tripwire established in Session 2. The seven existing invariants are: `check_strategy_isolation.sh`, `check_mcp_readonly.sh`, `check_no_llm_in_order_path.sh`, `check_risk_coverage.py`, `check_p2_coverage.py`, `check_p3_coverage.py`, `check_broker_isolation.sh`. Session 4's `check_no_env_credentials.sh` brings the total to eight.
9. **The swap-point function is `credentials_for_mode(mode)`** in `app/brokers/alpaca/credentials.py`, established in Session 2 v1.0 §2.3 as "the single swap-point for P5 §4." NOT a `BrokerRegistry._load_credentials_for` method (which doesn't exist). The function takes a mode string ('paper' | 'live'), returns `AlpacaCredentials`, and is currently called by `BrokerRegistry._construct()`. Session 4 swaps the body to read from `CredentialStore` instead of env; signature stays the same shape; **but the function becomes async** because the store is async. Callers propagate `await`.
10. **`_router_token` discipline must not be weakened.** Session 2's load-bearing invariant: broker mutators (`submit_order` / `cancel_order` / `replace_order`) are gated by `_router_token`, only `OrderRouter` passes it. Session 4's credential-store swap changes how adapters are *constructed*, not how they're *called*. The router → adapter call path stays exactly as Session 2 left it. Verify-during-execution.
11. **Runtime gates are explicitly deferred.** Sessions 0, 2, 3 all documented the same posture: live-stack runtime gates (paper smoke, full pytest with the count, frontend build) are deferred to a non-Norton environment because Norton SSL blocks `data.alpaca.markets` on the dev box and Docker isn't available locally. Session 4's §4.14 follows the same pattern: in-suite tests are the load-bearing assertion, with the live diff deferred to WSL/CI before the tag is promoted to a release.

---

## ⚠ Real-money posture (recap)

This session is the second of two foundation-level security upgrades (auth was the first). Once §4 ships:

1. **No production code path reads broker keys, Anthropic keys, or TOTP secrets from env vars.** The credential store is the only source. The CI invariant `check_no_env_credentials.sh` makes this enforceable from CI.

2. **A DB dump no longer leaks secrets.** Prior to §4, anyone with `data/workbench.sqlite` could mint TOTP codes, read Pine webhook secrets, and submit Anthropic API requests using your key. After §4, those columns are ciphertext; the master key lives outside the DB.

3. **The master key is the single point of failure.** If `WORKBENCH_MASTER_KEY` leaks AND the DB dumps, every secret is compromised. The runbook treats master-key handling with the same discipline as a production root password: never commit, never log, never paste into Slack.

4. **ADR 0002 discipline is preserved.** The credential-store swap changes adapter *construction*; it does not touch the OrderRouter → adapter *call path*. `_router_token` still gates broker mutators (Session 2 invariant). `tests/test_adr_0002_invariant.py` stays green without modification.

The threat model: **moderate-effort adversary with read access to the host's disk** (e.g., a misplaced backup, a stolen laptop, a compromised cloud bucket). Defending against this raises the bar substantially — full DB compromise without master key compromise leaks usernames and the audit log, but no working credentials. Defending against root-on-the-host is out of scope — at that point the attacker can read the master key from process memory anyway.

---

## Session Goal

After this session:
- `app/security/crypto.py` exposes `encrypt(plaintext) → bytes`, `decrypt(ciphertext) → str`, and `verify_master_key()`. Backed by `cryptography.fernet.Fernet`.
- The master key is read from `WORKBENCH_MASTER_KEY` env var on startup. Backend refuses to boot without it (clear error message, exit code 1).
- New `user_credentials(id, user_id, kind, ciphertext, created_at, updated_at, last_used_at, revoked_at)` table. `kind` is an enum: `ALPACA_PAPER_KEY`, `ALPACA_PAPER_SECRET`, `ALPACA_LIVE_KEY`, `ALPACA_LIVE_SECRET`, `ANTHROPIC_API_KEY`, `PINE_WEBHOOK_SECRET`, `TOTP_SECRET`.
- Migration moves data: TOTP secret from `users.totp_secret` → `user_credentials(kind=TOTP_SECRET)`. Pine webhook secret from `users.pine_webhook_secret` → `user_credentials(kind=PINE_WEBHOOK_SECRET)`. Env-var broker keys → `user_credentials(kind=ALPACA_*)` for `user_id=1` (best-effort bootstrap; warning if env vars absent).
- New `app/security/credential_store.py` exposes `get(user_id, kind) → str | None`, `set(user_id, kind, plaintext)`, `revoke(user_id, kind)`, `list_kinds(user_id) → list[CredentialMetadata]`.
- `credentials_for_mode()` in `app/brokers/alpaca/credentials.py` swaps body from env-var reads to credential-store reads. **Becomes async.** Callers (`BrokerRegistry._construct`) propagate the `await`.
- `AgentRuntime` (P3) reads Anthropic key from credential store instead of env.
- `app/api/v1/alerts.py` (TV webhook receiver, P4 §1) reads Pine webhook secret from credential store, using `hmac.compare_digest` for constant-time comparison against each active user's stored secret.
- Auth/login (`app/api/v1/auth.py`, Session 3) reads TOTP secret from credential store, not from the (now-dropped) `users.totp_secret` column.
- New endpoints under `/api/v1/users/me/credentials/`: GET (returns metadata only; never plaintext), POST per kind (set/rotate), DELETE per kind. TOTP excluded from generic POST (auth flow owns it).
- Settings → Credentials page: card per kind showing "set" / "not set" / "last_used_at" with rotate / delete buttons.
- New CI invariant `check_no_env_credentials.sh` greps for `os.environ.get(...)` reads of credential names outside `app/security/` and `alembic/versions/`. Eighth invariant.
- The old `users.totp_secret` and `users.pine_webhook_secret` columns are **dropped** after the data migration completes (two-step migration: copy → backfill verification → drop).
- `app/auth/future.py` is deleted (Session 3 punch-list close-out, bundled here).
- P5 §3's auth flow still works. P1's paper smoke still works. P3's agent still works. P4 §1's TV webhook still works. **Load-bearing.**

What does NOT happen this session:
- No KMS. Master key in env var only.
- No automated rotation. The rotate endpoint exists; rotation is a manual user action.
- No multi-tenant key isolation. One master key encrypts every user's credentials. Sufficient for single-tenant MVP; multi-tenant deployments would want per-tenant master keys (P6+).
- No per-credential audit trail of reads. Writes (set/rotate/delete) are audit-logged; reads aren't.
- No credential expiry. Some brokers rotate API keys on a schedule; the user is responsible for rotating in the workbench when they do.
- No rename of `app/auth/stub.py` to `dependency.py` (would touch dozens of import sites; defer to a hygiene PR).

---

## Prerequisites Check

```powershell
# from repo root; uv is not on PATH — use the venv python
cd C:\LLM-RAG-APP\ai-trading-app
git checkout main; git pull origin main
git describe --tags --abbrev=0          # expect: p5-session3-complete

# Required dep
findstr /R "\"cryptography\"" apps\backend\pyproject.toml
# If missing: cd apps\backend; .\.venv\Scripts\python.exe -m pip install cryptography

# Verify P5 §2 swap-point + P5 §3 auth + P3 agent are in their pre-§4 state
findstr /S /R "from app.security.credential_store" apps\backend\app
# Expect: empty (this is what we're adding)

findstr /S /R "credentials_for_mode" apps\backend\app\brokers\alpaca\credentials.py
# Expect: matches (Session 2 swap-point)

findstr /S /R "ANTHROPIC_API_KEY" apps\backend\app\agent
# Expect: matches in app\agent\runtime.py (P3 env read, swapping out)

# All seven CI invariants pass (we're adding the eighth this session)
bash apps/backend/scripts/check_strategy_isolation.sh
bash apps/backend/scripts/check_mcp_readonly.sh
bash apps/backend/scripts/check_no_llm_in_order_path.sh
bash apps/backend/scripts/check_broker_isolation.sh
.\.venv\Scripts\python.exe apps\backend\scripts\check_risk_coverage.py
.\.venv\Scripts\python.exe apps\backend\scripts\check_p2_coverage.py
.\.venv\Scripts\python.exe apps\backend\scripts\check_p3_coverage.py

# ADR 0002 invariant test (not a shell script — see Session Zero Results)
cd apps\backend
.\.venv\Scripts\python.exe -m pytest tests/test_adr_0002_invariant.py -q
cd ..\..

# Baseline backend suite green
cd apps\backend
.\.venv\Scripts\python.exe -m pytest -q --cov=app --cov-branch --cov-report=xml
cd ..\..
```

Live runtime gates (login + paper order) are **deferred** here: Norton SSL blocks `data.alpaca.markets` on this dev box. The byte-identical proof for the four load-bearing flows (auth, paper order, agent, Pine webhook) is carried by the in-suite tests in §4.13; the live curl/diff runs in WSL/CI before the tag is promoted to a release.

- [ ] On `main` at `p5-session3-complete`, clean tree.
- [ ] `cryptography` in deps.
- [ ] All seven existing invariants pass; ADR 0002 invariant test green.
- [ ] Backend suite green; risk branch-coverage ≥ 0.85.

```bash
git checkout -b feat/p5-session4-credentials
```

---

## §4.1 — Master Key Generation

Create `scripts/generate_master_key.py` (Python instead of bash — consistent with Session 3's create_user.py decision: Docker-free, runs anywhere Python runs):

```python
#!/usr/bin/env python3
"""generate_master_key.py — emit a fresh Fernet master key.

Usage:
    python scripts/generate_master_key.py

Prints the key to stdout. Copy this into your .env file as
WORKBENCH_MASTER_KEY. DO NOT commit your .env. DO NOT share the key.

Rotating the master key is a non-trivial operation: every existing
ciphertext must be re-encrypted. See docs/runbook/credentials.md
(P5+ polish; not in §4 MVP).
"""
from cryptography.fernet import Fernet

if __name__ == "__main__":
    print(Fernet.generate_key().decode("ascii"))
```

```powershell
cd C:\LLM-RAG-APP\ai-trading-app
.\apps\backend\.venv\Scripts\python.exe scripts\generate_master_key.py
# Output: 44-char base64 string ending in '='. Save this.
```

The key is 32 bytes of random data, base64-encoded → 44 chars. It's a Fernet URL-safe key, not raw AES bits.

> **DO NOT commit your `.env`.** Verify `.gitignore` includes `.env*`. The master key is the single most sensitive piece of data the workbench produces. If it leaks, every credential becomes recoverable (assuming the DB also leaked). If you suspect a leak, rotate immediately per the runbook.

- [ ] `generate_master_key.py` created and tested.
- [ ] Master key generated and added to `.env`.
- [ ] `.env*` confirmed in `.gitignore`.

---

## §4.2 — Crypto Module

Create `apps/backend/app/security/__init__.py`:

```python
"""Security primitives: crypto + credential store.

ONLY this package may import `cryptography` directly. Everything else
accesses crypto operations through the public functions exposed here.

The check_no_env_credentials.sh invariant enforces that no production
code path outside this package reads broker/AI/auth secrets from env vars.
"""
from app.security.crypto import (
    encrypt,
    decrypt,
    verify_master_key,
    MasterKeyMissingError,
    InvalidCiphertextError,
)
from app.security.credential_store import (
    CredentialKind,
    CredentialMetadata,
    CredentialStore,
    CredentialNotFoundError,
)

__all__ = [
    "encrypt", "decrypt", "verify_master_key",
    "MasterKeyMissingError", "InvalidCiphertextError",
    "CredentialKind", "CredentialMetadata", "CredentialStore",
    "CredentialNotFoundError",
]
```

Create `apps/backend/app/security/crypto.py`:

```python
"""Fernet encryption with a process-level master key.

The master key is loaded once at startup from WORKBENCH_MASTER_KEY env var.
Subsequent encrypt/decrypt calls use that key without re-reading the env.

Fernet wraps AES-128-CBC with HMAC-SHA256 for authenticated encryption.
That's plenty for our threat model (host-disk read by moderate adversary).
For higher-stakes deployments, KMS/HSM-backed envelope encryption would
be the upgrade path — but Fernet's interface (encrypt() returns bytes,
decrypt() takes bytes) maps to whatever backend we'd swap in.
"""
from __future__ import annotations

import os
from typing import Optional

import structlog
from cryptography.fernet import Fernet, InvalidToken


logger = structlog.get_logger(__name__)


MASTER_KEY_ENV_VAR = "WORKBENCH_MASTER_KEY"


class MasterKeyMissingError(RuntimeError):
    """Raised when the master key env var is unset or invalid. Backend
    refuses to boot."""


class InvalidCiphertextError(RuntimeError):
    """Raised when decrypt() can't decode a ciphertext. Either the master
    key is wrong (rotation happened or env var was changed) or the data
    is corrupted."""


_cached_fernet: Optional[Fernet] = None


def _get_fernet() -> Fernet:
    """Load the master key once. After first call, cached."""
    global _cached_fernet
    if _cached_fernet is None:
        key = os.environ.get(MASTER_KEY_ENV_VAR, "").strip()
        if not key:
            raise MasterKeyMissingError(
                f"{MASTER_KEY_ENV_VAR} environment variable is required. "
                f"Generate one with scripts/generate_master_key.py and add to .env."
            )
        try:
            _cached_fernet = Fernet(key.encode("ascii"))
        except (ValueError, TypeError) as exc:
            raise MasterKeyMissingError(
                f"{MASTER_KEY_ENV_VAR} is not a valid Fernet key: {exc}. "
                f"Generate a new one with scripts/generate_master_key.py."
            ) from exc
    return _cached_fernet


def verify_master_key() -> None:
    """Call at startup to fail fast if the master key is missing or
    malformed. Logs that the key is loaded (helpful for rotation later)."""
    f = _get_fernet()
    # Sanity round-trip
    ciphertext = f.encrypt(b"verify")
    plaintext = f.decrypt(ciphertext)
    assert plaintext == b"verify", "Fernet round-trip failed at startup"
    logger.info("crypto_master_key_verified")


def encrypt(plaintext: str) -> bytes:
    """Encrypt a UTF-8 string. Returns the Fernet token as bytes.

    Fernet tokens include the encryption timestamp, IV, ciphertext, and
    HMAC. They're URL-safe base64 — typically 100-200 bytes for short
    plaintexts. Storing as `bytes` (BLOB) in SQLite, not as text.
    """
    if not isinstance(plaintext, str):
        raise TypeError("encrypt() requires a str input")
    if not plaintext:
        raise ValueError("encrypt() cannot encrypt empty string")
    return _get_fernet().encrypt(plaintext.encode("utf-8"))


def decrypt(ciphertext: bytes) -> str:
    """Decrypt to UTF-8. Raises InvalidCiphertextError on any failure."""
    if not ciphertext:
        raise InvalidCiphertextError("Empty ciphertext")
    try:
        plaintext_bytes = _get_fernet().decrypt(ciphertext)
    except InvalidToken as exc:
        raise InvalidCiphertextError(
            "Cannot decrypt — wrong master key or corrupted data."
        ) from exc
    return plaintext_bytes.decode("utf-8")


def _reset_cache_for_tests() -> None:
    """Test-only: clear the cached Fernet so a different key can be tested."""
    global _cached_fernet
    _cached_fernet = None
```

> **Why bytes and not text for the ciphertext column?** Fernet tokens are URL-safe base64, so technically they're ASCII-safe. We store as `LargeBinary` (BLOB) anyway because: (1) it signals "this is opaque data, not text" to anyone reading the schema; (2) if we ever swap to a non-base64 backend (raw AES-GCM, for example), no migration is needed; (3) SQLite stores BLOBs compactly.

- [ ] `crypto.py` exposes `encrypt`, `decrypt`, `verify_master_key`.
- [ ] Master key cached after first read.
- [ ] Clear errors for missing or bad keys.

---

## §4.3 — Credential Store Module

Create `apps/backend/app/security/credential_store.py`:

```python
"""Persistent encrypted credential store.

Operations:
  - get(user_id, kind) → plaintext (or None if not set / revoked)
  - set(user_id, kind, plaintext) — set or rotate
  - revoke(user_id, kind) — soft-revoke (keeps ciphertext one week for
    forensic recovery, then hard-deleted by a scheduled job)
  - list_kinds(user_id) → metadata only (kind, last_used_at, created_at,
    has_been_set). Plaintext NEVER returned by list.

Audit-logging:
  - set/rotate/revoke all write to audit_log with action CREDENTIAL_*
  - get does NOT audit (would dwarf the rest of the audit log)

Datetime handling:
  SQLite round-trips timezone-aware datetimes as naive (same gotcha
  Session 3 handled in app/auth/stub.py via _aware()). Every datetime
  comparison in this module coerces both sides to aware-UTC explicitly
  via _ensure_aware() before comparing. See Notes & Gotchas #4.

After P5 §4, this is the ONLY module that may decrypt secrets at runtime.
Other modules call .get(); the plaintext stays in that one call's local
scope and is passed directly to the consumer (broker SDK, Anthropic SDK,
TOTP verifier).
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Optional

import structlog
from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.user_credential import UserCredential
from app.security.crypto import decrypt, encrypt


logger = structlog.get_logger(__name__)


class CredentialKind(str, Enum):
    """Every secret stored in user_credentials."""
    ALPACA_PAPER_KEY = "alpaca_paper_key"
    ALPACA_PAPER_SECRET = "alpaca_paper_secret"
    ALPACA_LIVE_KEY = "alpaca_live_key"
    ALPACA_LIVE_SECRET = "alpaca_live_secret"
    ANTHROPIC_API_KEY = "anthropic_api_key"
    PINE_WEBHOOK_SECRET = "pine_webhook_secret"
    TOTP_SECRET = "totp_secret"


class CredentialNotFoundError(RuntimeError):
    """Raised by .get(..., required=True) when the credential doesn't exist."""


REVOKED_RETENTION = timedelta(days=7)


def _ensure_aware(dt: datetime | None) -> datetime | None:
    """Coerce a possibly-naive datetime to aware-UTC.

    SQLite returns datetimes without tzinfo even when they were stored
    with timezone. Same approach as app/auth/stub.py::_aware (Session 3).
    """
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


class CredentialMetadata:
    """Sanitized view: what /credentials lists. NEVER includes plaintext."""

    def __init__(self, *, kind: CredentialKind, has_value: bool,
                 created_at: datetime | None, updated_at: datetime | None,
                 last_used_at: datetime | None, revoked_at: datetime | None):
        self.kind = kind
        self.has_value = has_value
        self.created_at = _ensure_aware(created_at)
        self.updated_at = _ensure_aware(updated_at)
        self.last_used_at = _ensure_aware(last_used_at)
        self.revoked_at = _ensure_aware(revoked_at)


class CredentialStore:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(
        self,
        user_id: int,
        kind: CredentialKind,
        *,
        required: bool = False,
    ) -> Optional[str]:
        """Return the plaintext for (user_id, kind), or None if not set
        and required=False. Touches last_used_at on read."""
        row = await self._fetch_active(user_id, kind)
        if row is None:
            if required:
                raise CredentialNotFoundError(
                    f"Credential not set: user_id={user_id} kind={kind.value}"
                )
            return None
        plaintext = decrypt(row.ciphertext)
        row.last_used_at = datetime.now(timezone.utc)
        await self._session.commit()
        return plaintext

    async def set(
        self,
        user_id: int,
        kind: CredentialKind,
        plaintext: str,
    ) -> None:
        """Set or rotate. The prior ciphertext is overwritten in-place;
        we DON'T keep history (Fernet tokens carry no useful provenance
        and storing history would mean rotation doesn't actually reduce
        the attack surface)."""
        if not plaintext:
            raise ValueError("Plaintext cannot be empty")
        ciphertext = encrypt(plaintext)
        now = datetime.now(timezone.utc)
        existing = await self._fetch_active(user_id, kind)
        if existing is not None:
            existing.ciphertext = ciphertext
            existing.updated_at = now
            existing.revoked_at = None
        else:
            self._session.add(UserCredential(
                user_id=user_id,
                kind=kind.value,
                ciphertext=ciphertext,
                created_at=now,
                updated_at=now,
            ))
        await self._session.commit()
        logger.info("credential_set", user_id=user_id, kind=kind.value)

    async def revoke(self, user_id: int, kind: CredentialKind) -> None:
        """Soft-delete. The ciphertext stays for 7 days for forensic
        recovery; the scheduled cleanup job hard-deletes after that."""
        existing = await self._fetch_active(user_id, kind)
        if existing is None:
            return
        existing.revoked_at = datetime.now(timezone.utc)
        await self._session.commit()
        logger.info("credential_revoked", user_id=user_id, kind=kind.value)

    async def list_kinds(self, user_id: int) -> list[CredentialMetadata]:
        """Return metadata for every kind for this user. Includes
        not-set kinds so the UI can show 'not configured' state."""
        result = (await self._session.execute(
            select(UserCredential).where(UserCredential.user_id == user_id)
        )).scalars().all()
        by_kind: dict[str, UserCredential] = {r.kind: r for r in result}
        out: list[CredentialMetadata] = []
        for kind in CredentialKind:
            row = by_kind.get(kind.value)
            if row is None:
                out.append(CredentialMetadata(
                    kind=kind, has_value=False,
                    created_at=None, updated_at=None,
                    last_used_at=None, revoked_at=None,
                ))
            else:
                out.append(CredentialMetadata(
                    kind=kind, has_value=(row.revoked_at is None),
                    created_at=row.created_at, updated_at=row.updated_at,
                    last_used_at=row.last_used_at, revoked_at=row.revoked_at,
                ))
        return out

    async def hard_delete_revoked(self) -> int:
        """Scheduled cleanup: delete rows revoked > REVOKED_RETENTION ago.
        Called by APScheduler daily. Returns count deleted.

        Comparison coerces both sides to aware-UTC (SQLite gotcha)."""
        cutoff = datetime.now(timezone.utc) - REVOKED_RETENTION
        # Pull candidates first so we can coerce the SQLite-returned
        # naive datetimes before comparing.
        candidates = (await self._session.execute(
            select(UserCredential).where(UserCredential.revoked_at.isnot(None))
        )).scalars().all()
        to_delete = [r.id for r in candidates
                     if _ensure_aware(r.revoked_at) < cutoff]
        if not to_delete:
            return 0
        await self._session.execute(
            delete(UserCredential).where(UserCredential.id.in_(to_delete))
        )
        await self._session.commit()
        return len(to_delete)

    # ---------------- internals ----------------

    async def _fetch_active(
        self, user_id: int, kind: CredentialKind,
    ) -> Optional[UserCredential]:
        return (await self._session.execute(
            select(UserCredential)
            .where(UserCredential.user_id == user_id)
            .where(UserCredential.kind == kind.value)
            .where(UserCredential.revoked_at.is_(None))
        )).scalars().first()
```

- [ ] `credential_store.py` with `get`, `set`, `revoke`, `list_kinds`, `hard_delete_revoked`.
- [ ] `_ensure_aware()` helper coerces SQLite-returned naive datetimes.
- [ ] Plaintext never returned by `list_kinds`.
- [ ] Reads update `last_used_at`.

---

## §4.4 — Database Model + Migration

Create `apps/backend/app/db/models/user_credential.py`:

```python
"""user_credentials — encrypted secrets per (user_id, kind)."""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, LargeBinary, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class UserCredential(Base):
    __tablename__ = "user_credentials"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True,
    )
    kind: Mapped[str] = mapped_column(String(64), nullable=False)
    ciphertext: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        # An active (non-revoked) credential per (user, kind) is unique.
        # Revoked rows linger up to 7 days, so we can't enforce a strict
        # UNIQUE(user_id, kind); the application layer enforces "one active".
        Index("ix_user_credentials_user_kind", "user_id", "kind"),
        Index("ix_user_credentials_revoked_at", "revoked_at"),
    )
```

Register in `apps/backend/app/db/models/__init__.py`:

```python
from .user_credential import UserCredential  # noqa: F401
```

Generate the migration:

```powershell
cd apps\backend
.\.venv\Scripts\python.exe -m alembic revision --autogenerate -m "P5 §4: user_credentials + data migration"
```

This must land cleanly on top of Session 3's migration (`8c1e26e3d0a6_p5_s3_users_password_hash_totp_sessions_.py`). Verify the autogenerate detects:
- New `user_credentials` table
- Drop of `users.totp_secret`
- Drop of `users.pine_webhook_secret`

Then **append a data-migration block manually** before the column drops. Open the generated migration and structure it as:

```python
"""P5 §4: user_credentials table + data migration

Revision ID: <generated>
Revises: 8c1e26e3d0a6
"""
from datetime import datetime, timezone
from cryptography.fernet import Fernet
import os
import alembic.op as op
import sqlalchemy as sa


def upgrade() -> None:
    # 1) Create user_credentials table (autogenerate)
    op.create_table(
        "user_credentials",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("kind", sa.String(length=64), nullable=False),
        sa.Column("ciphertext", sa.LargeBinary(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_user_credentials_user_kind", "user_credentials",
                    ["user_id", "kind"])
    op.create_index("ix_user_credentials_revoked_at", "user_credentials",
                    ["revoked_at"])
    op.create_index("ix_user_credentials_user_id", "user_credentials",
                    ["user_id"])

    # 2) Data migration — requires master key
    key = os.environ.get("WORKBENCH_MASTER_KEY", "").strip()
    if not key:
        raise RuntimeError(
            "WORKBENCH_MASTER_KEY env var required for migration. "
            "Run scripts/generate_master_key.py and set in .env BEFORE upgrade."
        )
    fernet = Fernet(key.encode("ascii"))
    now = datetime.now(timezone.utc)
    bind = op.get_bind()

    # Move TOTP secrets (any user with a non-null totp_secret)
    totp_rows = bind.execute(sa.text(
        "SELECT id, totp_secret FROM users WHERE totp_secret IS NOT NULL"
    )).fetchall()
    for user_id, secret in totp_rows:
        ct = fernet.encrypt(secret.encode("utf-8"))
        bind.execute(sa.text(
            "INSERT INTO user_credentials "
            "(user_id, kind, ciphertext, created_at, updated_at) "
            "VALUES (:uid, :kind, :ct, :ts, :ts)"
        ), {"uid": user_id, "kind": "totp_secret", "ct": ct, "ts": now})

    # Move Pine webhook secrets
    pine_rows = bind.execute(sa.text(
        "SELECT id, pine_webhook_secret FROM users "
        "WHERE pine_webhook_secret IS NOT NULL"
    )).fetchall()
    for user_id, secret in pine_rows:
        ct = fernet.encrypt(secret.encode("utf-8"))
        bind.execute(sa.text(
            "INSERT INTO user_credentials "
            "(user_id, kind, ciphertext, created_at, updated_at) "
            "VALUES (:uid, :kind, :ct, :ts, :ts)"
        ), {"uid": user_id, "kind": "pine_webhook_secret", "ct": ct, "ts": now})

    # Best-effort: capture env-var broker + Anthropic keys for user_id=1
    # (the bootstrap user). Multi-user deployments capture nothing here;
    # users set their own credentials via the UI after upgrade.
    has_user_1 = bind.execute(sa.text(
        "SELECT 1 FROM users WHERE id = 1"
    )).fetchone()
    if has_user_1:
        env_map = {
            "alpaca_paper_key":   os.environ.get("ALPACA_PAPER_API_KEY"),
            "alpaca_paper_secret": os.environ.get("ALPACA_PAPER_API_SECRET"),
            "alpaca_live_key":    os.environ.get("ALPACA_LIVE_API_KEY"),
            "alpaca_live_secret": os.environ.get("ALPACA_LIVE_API_SECRET"),
            "anthropic_api_key":  os.environ.get("ANTHROPIC_API_KEY"),
        }
        for kind, value in env_map.items():
            if value:
                ct = fernet.encrypt(value.encode("utf-8"))
                bind.execute(sa.text(
                    "INSERT INTO user_credentials "
                    "(user_id, kind, ciphertext, created_at, updated_at) "
                    "VALUES (1, :kind, :ct, :ts, :ts)"
                ), {"kind": kind, "ct": ct, "ts": now})

    # 3) Drop old columns
    with op.batch_alter_table("users") as batch:
        batch.drop_column("totp_secret")
        batch.drop_column("pine_webhook_secret")


def downgrade() -> None:
    """Emergency rollback. Restores plaintext columns; treat as a
    'data is leaked' state and rotate every credential immediately."""
    op.add_column("users", sa.Column("totp_secret", sa.String(), nullable=True))
    op.add_column("users", sa.Column("pine_webhook_secret", sa.String(), nullable=True))

    key = os.environ.get("WORKBENCH_MASTER_KEY", "").strip()
    if not key:
        raise RuntimeError(
            "WORKBENCH_MASTER_KEY required to decrypt during downgrade."
        )
    fernet = Fernet(key.encode("ascii"))
    bind = op.get_bind()

    totp = bind.execute(sa.text(
        "SELECT user_id, ciphertext FROM user_credentials "
        "WHERE kind = 'totp_secret' AND revoked_at IS NULL"
    )).fetchall()
    for user_id, ct in totp:
        pt = fernet.decrypt(ct).decode("utf-8")
        bind.execute(sa.text(
            "UPDATE users SET totp_secret = :pt WHERE id = :uid"
        ), {"pt": pt, "uid": user_id})

    pine = bind.execute(sa.text(
        "SELECT user_id, ciphertext FROM user_credentials "
        "WHERE kind = 'pine_webhook_secret' AND revoked_at IS NULL"
    )).fetchall()
    for user_id, ct in pine:
        pt = fernet.decrypt(ct).decode("utf-8")
        bind.execute(sa.text(
            "UPDATE users SET pine_webhook_secret = :pt WHERE id = :uid"
        ), {"pt": pt, "uid": user_id})

    op.drop_index("ix_user_credentials_user_id", table_name="user_credentials")
    op.drop_index("ix_user_credentials_revoked_at", table_name="user_credentials")
    op.drop_index("ix_user_credentials_user_kind", table_name="user_credentials")
    op.drop_table("user_credentials")
```

Test the migration:

```powershell
cd apps\backend
# Ensure master key is set
$env:WORKBENCH_MASTER_KEY="<your key>"

# Forward
.\.venv\Scripts\python.exe -m alembic upgrade head

# Verify columns dropped
.\.venv\Scripts\python.exe -c "import sqlite3; c=sqlite3.connect('data/workbench.sqlite'); print([r[1] for r in c.execute('PRAGMA table_info(users)').fetchall()])"
# Expect: no 'totp_secret' or 'pine_webhook_secret'

# Round-trip — needs master key for both directions
.\.venv\Scripts\python.exe -m alembic downgrade -1
.\.venv\Scripts\python.exe -m alembic upgrade head
```

- [ ] Migration runs forward with master key set.
- [ ] Old columns dropped after data move.
- [ ] Downgrade restores plaintext columns (emergency-only path).
- [ ] Round-trip works.

---

## §4.5 — Backend Boot: Master Key Verification

Edit `apps/backend/app/lifespan.py`. Add `verify_master_key()` early in startup, **before** `BrokerRegistry.load_all()` and **before** `AgentRuntime` initialization, so the store is ready when consumers need it.

```python
from app.security import verify_master_key, MasterKeyMissingError

# Inside the startup block, very early (after structlog config, before
# database connection):
try:
    verify_master_key()
except MasterKeyMissingError as exc:
    logger.error("master_key_missing_or_invalid", error=str(exc))
    # Fail loud, fail fast. No "degraded mode".
    import sys
    sys.exit(1)

# ... existing db connection, engine, session_factory setup ...

# THEN (after session_factory is built, before BrokerRegistry):
# (no changes here; BrokerRegistry construction stays as Session 2 left it)
broker_registry = BrokerRegistry(session_factory)
await broker_registry.load_all()
```

**Important ordering**: `verify_master_key()` must be called **before** `broker_registry.load_all()`, because `load_all()` invokes the new async `credentials_for_mode()` (§4.6), which calls `CredentialStore.get()`, which calls `decrypt()`, which needs the master key.

- [ ] `verify_master_key()` called early in startup.
- [ ] Backend exits with code 1 + clear message if key missing.
- [ ] Ordering: verify → DB → session_factory → registry → adapters → router.

---

## §4.6 — `credentials_for_mode()` Swap (the P5 §2 swap-point)

Edit `apps/backend/app/brokers/alpaca/credentials.py`. The function's role is unchanged — given a mode string, return `AlpacaCredentials`. The body swaps env-var reads for credential-store reads. **The function becomes async.**

```python
# Before (Session 2 form, abridged):
# def credentials_for_mode(mode: str) -> AlpacaCredentials:
#     s = get_settings()
#     m = (mode or "paper").lower()
#     if m == "live":
#         if not s.alpaca_live_api_key or not s.alpaca_live_api_secret:
#             raise CredentialsError(...)
#         return AlpacaCredentials(api_key=s.alpaca_live_api_key,
#                                  api_secret=s.alpaca_live_api_secret,
#                                  paper=False)
#     ...

# After (P5 §4):
from sqlalchemy.ext.asyncio import async_sessionmaker, AsyncSession
from app.security import CredentialStore, CredentialKind, CredentialNotFoundError


async def credentials_for_mode(
    mode: str,
    user_id: int,
    session_factory: async_sessionmaker[AsyncSession],
) -> AlpacaCredentials:
    """Build AlpacaCredentials for an explicit mode ('paper'|'live'),
    for the given user_id, by reading from the credential store.

    Live still never silently falls back to paper (same posture as the
    original env-var version): missing live credentials → CredentialsError.

    Async because the credential store is async. Callers propagate await.
    """
    m = (mode or "paper").lower()
    if m not in ("paper", "live"):
        raise CredentialsError(f"mode must be 'paper' or 'live', got '{m}'.")

    async with session_factory() as session:
        store = CredentialStore(session)
        if m == "live":
            key = await store.get(user_id, CredentialKind.ALPACA_LIVE_KEY)
            secret = await store.get(user_id, CredentialKind.ALPACA_LIVE_SECRET)
            if not key or not secret:
                raise CredentialsError(
                    f"Live mode requested but ALPACA_LIVE_KEY / "
                    f"ALPACA_LIVE_SECRET not set for user_id={user_id}. "
                    f"Set via Settings → Credentials."
                )
            return AlpacaCredentials(api_key=key, api_secret=secret, paper=False)

        # paper
        key = await store.get(user_id, CredentialKind.ALPACA_PAPER_KEY)
        secret = await store.get(user_id, CredentialKind.ALPACA_PAPER_SECRET)
        if not key or not secret:
            raise CredentialsError(
                f"ALPACA_PAPER_KEY / ALPACA_PAPER_SECRET not set for "
                f"user_id={user_id}. Set via Settings → Credentials."
            )
        return AlpacaCredentials(api_key=key, api_secret=secret, paper=True)
```

Update `BrokerRegistry._construct()` in `apps/backend/app/brokers/registry.py` to match the async signature:

```python
# Before (Session 2):
# def _construct(self, account: Account) -> BrokerAdapter:
#     if account.broker != "alpaca":
#         raise ValueError(f"No adapter for broker={account.broker!r}")
#     creds = credentials_for_mode(account.mode.value)
#     adapter = AlpacaAdapter(credentials=creds)
#     return adapter

# After (P5 §4):
async def _construct(self, account: Account) -> BrokerAdapter:
    if account.broker != "alpaca":
        raise ValueError(f"No adapter for broker={account.broker!r}")
    creds = await credentials_for_mode(
        account.mode.value, account.user_id, self._session_factory,
    )
    adapter = AlpacaAdapter(credentials=creds)
    # Construction stays network-free (no connect()). Session 2 §2.3 discipline.
    return adapter
```

And update `_try_construct`:

```python
async def _try_construct(self, account: Account) -> None:  # was sync
    try:
        self._adapters[account.id] = await self._construct(account)
        logger.info("broker_registry_adapter_loaded",
                    account_id=account.id, broker=account.broker,
                    mode=account.mode.value)
    except Exception as exc:
        logger.warning("broker_registry_adapter_failed",
                       account_id=account.id, error=str(exc))
```

And `load_all` / `refresh` propagate the await:

```python
async def load_all(self) -> None:
    async with self._session_factory() as session:
        rows = (await session.execute(select(Account))).scalars().all()
    for row in rows:
        await self._try_construct(row)

async def refresh(self, account_id: int) -> None:
    async with self._session_factory() as session:
        row = await session.get(Account, account_id)
    if row is None:
        return
    prior = self._adapters.pop(account_id, None)
    if prior is not None:
        self._safe_disconnect(prior)
    await self._try_construct(row)
```

> **`_router_token` discipline preserved**: this change is entirely in adapter *construction*. The router → adapter *call path* is untouched. `tests/test_adr_0002_invariant.py` stays green (no new `submit_order` callers outside `app/orders/`).

- [ ] `credentials_for_mode()` swapped to async + store reads.
- [ ] `BrokerRegistry._construct/_try_construct/load_all/refresh` propagate `await`.
- [ ] No changes to the router → adapter call path.
- [ ] `tests/test_adr_0002_invariant.py` still passes.

---

## §4.7 — Agent Runtime Swap

Edit `apps/backend/app/agent/runtime.py`. The Anthropic key is now per-user via the credential store, not a process-global env var.

```python
# OLD:
# import os
# class AgentRuntime:
#     def __init__(self, ...):
#         self._anthropic_key = os.environ.get("ANTHROPIC_API_KEY", "")
#         ...

# NEW:
from app.security import CredentialStore, CredentialKind


class AgentRuntime:
    def __init__(self, session_factory, ...):  # session_factory already injected
        # No longer holds the key. Reads from store per request.
        self._session_factory = session_factory
        ...

    async def _get_anthropic_key(self, user_id: int) -> str:
        async with self._session_factory() as session:
            store = CredentialStore(session)
            key = await store.get(user_id, CredentialKind.ANTHROPIC_API_KEY)
            if not key:
                raise RuntimeError(
                    f"Anthropic API key not set for user_id={user_id}. "
                    f"Set via Settings → Credentials."
                )
            return key
```

Where `AgentRuntime` previously used `self._anthropic_key` to construct the Anthropic client, it now calls `await self._get_anthropic_key(user_id)` per request. The user_id is already available — every agent request flows through an authenticated endpoint (per Session 3).

- [ ] AgentRuntime reads Anthropic key from store per request.
- [ ] No process-global Anthropic key stored.
- [ ] Existing agent tests updated to seed the store.

---

## §4.8 — TV Webhook Receiver Swap

Edit `apps/backend/app/api/v1/alerts.py`. The Pine webhook receiver currently matches the presented secret against `users.pine_webhook_secret`. After §4, the column is gone; the receiver matches against the credential store.

```python
# OLD (sketch):
# user_row = await session.execute(
#     select(User).where(User.pine_webhook_secret == presented_secret)
# )
# if user_row is None: raise HTTPException(403)

# NEW: match against credential store, constant-time
import hmac
from app.security import CredentialStore, CredentialKind


async def _authenticate_webhook(presented_secret: str, session) -> int | None:
    """Find which user this Pine webhook belongs to.
    Constant-time match against every active user's stored secret."""
    store = CredentialStore(session)
    # Pull all users (cheap — single-tenant MVP has few users)
    users = (await session.execute(select(User))).scalars().all()
    for user in users:
        stored = await store.get(user.id, CredentialKind.PINE_WEBHOOK_SECRET)
        if stored is None:
            continue
        if hmac.compare_digest(stored, presented_secret):
            return user.id
    return None
```

> **Performance note** (also Notes & Gotchas #5): this is O(users) decrypts per webhook. Fine for single-digit users. If multi-user deployments grow, the optimization is a SHA-256 lookup index on a separate column — but that's out of scope for §4.

- [ ] Webhook receiver uses credential store + `hmac.compare_digest`.
- [ ] `users.pine_webhook_secret` no longer referenced anywhere in `app/`.

---

## §4.9 — Auth/Login Swap (TOTP)

Edit `apps/backend/app/api/v1/auth.py`. The TOTP verification step in login (Session 3) reads from `users.totp_secret`. After §4, it reads from the credential store.

```python
# OLD (Session 3, sketch):
# if not verify_totp(user.totp_secret, body.totp_code):
#     raise HTTPException(401)

# NEW:
from app.security import CredentialStore, CredentialKind

# Inside login(), after password verification:
store = CredentialStore(session)
totp_secret = await store.get(user.id, CredentialKind.TOTP_SECRET)
if totp_secret is None:
    # User hasn't completed TOTP setup. Per Session 3 flow, login refuses
    # until /auth/totp/setup + /auth/totp/verify complete.
    raise HTTPException(status_code=403, detail="TOTP not configured. "
                        "Run scripts/create_user.py to set it.")
if not verify_totp(totp_secret, body.totp_code):
    raise HTTPException(status_code=401, detail="Invalid TOTP code")
```

Similar swap in `/auth/totp/setup` and `/auth/totp/verify` (Session 3 endpoints): instead of writing to/reading from `user.totp_secret`, they write to/read from `CredentialStore` with `kind=TOTP_SECRET`.

Update `scripts/create_user.py` similarly: where it writes `user.totp_secret = secret`, it now writes via `CredentialStore.set(user.id, CredentialKind.TOTP_SECRET, secret)`.

- [ ] Login reads TOTP from store.
- [ ] `/auth/totp/setup` + `/auth/totp/verify` write to store.
- [ ] `scripts/create_user.py` writes TOTP via store.
- [ ] No code path reads `users.totp_secret` (column is dropped anyway).

---

## §4.10 — Credentials API

Create `apps/backend/app/api/v1/credentials.py`. Endpoints under `/api/v1/users/me/credentials/`:

- `GET /` — returns `list[CredentialMetadata]` for the current user. **NEVER returns plaintext.**
- `PUT /{kind}` — sets or rotates a credential. Body: `{"value": "..."}`. **Refuses TOTP_SECRET** (use the auth flow instead).
- `DELETE /{kind}` — revokes a credential.

```python
"""User credential management — set, list metadata, revoke."""
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.stub import CurrentUser, get_current_user
from app.db.session import get_session
from app.security import CredentialKind, CredentialStore


router = APIRouter(prefix="/api/v1/users/me/credentials", tags=["credentials"])


class CredentialIn(BaseModel):
    value: str


class CredentialMetadataOut(BaseModel):
    kind: str
    has_value: bool
    created_at: str | None
    updated_at: str | None
    last_used_at: str | None
    revoked_at: str | None


@router.get("/", response_model=list[CredentialMetadataOut])
async def list_credentials(
    current_user: CurrentUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    store = CredentialStore(session)
    items = await store.list_kinds(current_user.id)
    return [
        CredentialMetadataOut(
            kind=item.kind.value,
            has_value=item.has_value,
            created_at=item.created_at.isoformat() if item.created_at else None,
            updated_at=item.updated_at.isoformat() if item.updated_at else None,
            last_used_at=item.last_used_at.isoformat() if item.last_used_at else None,
            revoked_at=item.revoked_at.isoformat() if item.revoked_at else None,
        )
        for item in items
    ]


@router.put("/{kind}", status_code=status.HTTP_204_NO_CONTENT)
async def set_credential(
    kind: str,
    body: CredentialIn,
    current_user: CurrentUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    try:
        ck = CredentialKind(kind)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Unknown credential kind: {kind}")
    if ck == CredentialKind.TOTP_SECRET:
        raise HTTPException(
            status_code=400,
            detail="TOTP secret is managed via /auth/totp/setup, not this endpoint.",
        )
    if not body.value:
        raise HTTPException(status_code=400, detail="Value cannot be empty")
    store = CredentialStore(session)
    await store.set(current_user.id, ck, body.value)
    # If this is a broker credential, refresh the registry so the
    # adapter picks up the new keys without restarting.
    if ck in (CredentialKind.ALPACA_PAPER_KEY, CredentialKind.ALPACA_PAPER_SECRET,
              CredentialKind.ALPACA_LIVE_KEY, CredentialKind.ALPACA_LIVE_SECRET):
        # Lazy import to avoid circular
        from fastapi import Request
        # ... (the endpoint signature would need Request; or use a service
        # injection layer to get broker_registry directly. Pattern matches
        # Session 2 §2.5's create_account refresh.)


@router.delete("/{kind}", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_credential(
    kind: str,
    current_user: CurrentUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    try:
        ck = CredentialKind(kind)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Unknown credential kind: {kind}")
    if ck == CredentialKind.TOTP_SECRET:
        raise HTTPException(
            status_code=400,
            detail="TOTP secret is managed via /auth/totp/setup, not this endpoint.",
        )
    store = CredentialStore(session)
    await store.revoke(current_user.id, ck)
```

Wire into `app/main.py`:

```python
from app.api.v1 import credentials as credentials_router
app.include_router(credentials_router.router)
```

- [ ] Three endpoints (GET, PUT, DELETE).
- [ ] TOTP excluded from generic PUT/DELETE.
- [ ] Plaintext NEVER in GET response.

---

## §4.11 — Frontend: Credentials Page

Add `apps/frontend/src/api/credentials.ts`:

```typescript
import { apiClient } from "./client";

export interface CredentialMetadata {
  kind: string;
  has_value: boolean;
  created_at: string | null;
  updated_at: string | null;
  last_used_at: string | null;
  revoked_at: string | null;
}

export const credentialsApi = {
  list: () => apiClient.get<CredentialMetadata[]>("/api/v1/users/me/credentials/"),
  set: (kind: string, value: string) =>
    apiClient.put(`/api/v1/users/me/credentials/${kind}`, { value }),
  revoke: (kind: string) =>
    apiClient.delete(`/api/v1/users/me/credentials/${kind}`),
};
```

Add `apps/frontend/src/pages/Settings/Credentials.tsx`. A card per `CredentialKind` showing:
- Badge: "Set" (green) / "Not set" (gray)
- Last used: relative timestamp if set
- Buttons: "Set" / "Rotate" (opens modal for new value) / "Revoke" (confirmation)

The plaintext field is `type="password"` and never persisted in component state after submission (cleared via `setValue("")` after successful PUT).

Add to App.tsx route `/settings/credentials` behind `RequireAuth`.

- [ ] `Credentials.tsx` renders one card per kind.
- [ ] Set/rotate/revoke flows work.
- [ ] Plaintext cleared after submit.

---

## §4.12 — CI Invariant: No Env Credentials

Create `apps/backend/scripts/check_no_env_credentials.sh`:

```bash
#!/bin/bash
# check_no_env_credentials.sh
#
# P5 §4 invariant: no production code path may read broker keys, Anthropic
# keys, or auth secrets from environment variables. The only allowed
# env-var read for these names is in app/security/ (the credential store
# itself) and in alembic/versions/ (the data migration).
#
# Mirrors check_strategy_isolation.sh + check_broker_isolation.sh: a
# grep-level invariant that catches drift between PRs.

set -e

ROOT="apps/backend/app"

# The names we care about
NAMES="ALPACA_API_KEY|ALPACA_API_SECRET|ALPACA_PAPER_API_KEY|ALPACA_PAPER_API_SECRET|ALPACA_LIVE_API_KEY|ALPACA_LIVE_API_SECRET|ANTHROPIC_API_KEY|PINE_WEBHOOK_SECRET"

# os.environ.get("NAME"...) or os.environ["NAME"] for these
PATTERN="os\\.environ\\[?(\\.get)?\\(?[\"'](${NAMES})[\"']"

# Allow-list: the security package + alembic versions
VIOLATIONS=$(find "$ROOT" -name "*.py" \
  -not -path "${ROOT}/security/*" \
  -exec grep -lE "$PATTERN" {} \; 2>/dev/null || true)

# Also check apps/backend/alembic but allow it
# (migration legitimately reads master key + env-var broker keys for bootstrap)

if [ -n "$VIOLATIONS" ]; then
    echo "ERROR: env-var reads of credential names found outside app/security/."
    echo ""
    for f in $VIOLATIONS; do
        echo "  $f:"
        grep -nE "$PATTERN" "$f" | sed 's/^/    /'
    done
    echo ""
    echo "These names must be read via app.security.credential_store.CredentialStore."
    echo "If you genuinely need an env-var fallback, write an ADR first."
    exit 1
fi

echo "Credential env-isolation invariant OK"
exit 0
```

Test:

```bash
chmod +x apps/backend/scripts/check_no_env_credentials.sh
bash apps/backend/scripts/check_no_env_credentials.sh
# Expect: "Credential env-isolation invariant OK"

# Negative test
echo 'KEY = os.environ.get("ALPACA_API_KEY")' >> apps/backend/app/agent/runtime.py
bash apps/backend/scripts/check_no_env_credentials.sh && echo "BUG" || echo "OK: caught"
git checkout apps/backend/app/agent/runtime.py
bash apps/backend/scripts/check_no_env_credentials.sh
```

Wire into `.github/workflows/ci.yml`, matching the existing invariant steps' `if:` / `working-directory` shape:

```yaml
      - name: Credential env-isolation invariant check (backend)
        if: matrix.project == 'backend'
        run: bash apps/backend/scripts/check_no_env_credentials.sh
```

**After this PR ships, the CI invariant club is eight:**

| Invariant | Script | Source |
|---|---|---|
| Strategy isolation | `check_strategy_isolation.sh` | P2 |
| MCP read-only | `check_mcp_readonly.sh` | P3 |
| No LLM in order path | `check_no_llm_in_order_path.sh` | P4/ADR 0006v2 |
| Risk coverage ≥85% | `check_risk_coverage.py` | P2 |
| P2 coverage | `check_p2_coverage.py` | P2 |
| P3 coverage | `check_p3_coverage.py` | P3 |
| Broker isolation | `check_broker_isolation.sh` | P5 §2 |
| **Credential env-isolation (NEW)** | `check_no_env_credentials.sh` | P5 §4 |

ADR 0002 (single OrderRouter) is enforced by `tests/test_adr_0002_invariant.py` + the `_router_token` tripwire, not a shell script — see Session Zero Results + Session 2 v1.0.

- [ ] Script created, positive + negative tested.
- [ ] Wired into CI.

---

## §4.13 — Backend Tests

Create `apps/backend/tests/security/test_crypto.py` — round-trip + error handling for `encrypt`/`decrypt`/`verify_master_key`. (Test code as in v0.1; no drift.)

Create `apps/backend/tests/security/test_credential_store.py` — set/get/revoke/list/hard_delete_revoked, including the SQLite naive-datetime case for `hard_delete_revoked`.

Create `apps/backend/tests/api/test_p5_credentials_endpoint.py` — the three credentials endpoints, plus TOTP exclusion.

Run:

```powershell
cd apps\backend
.\.venv\Scripts\python.exe -m pytest tests/security tests/api/test_p5_credentials_endpoint.py -q
.\.venv\Scripts\python.exe -m pytest -q --cov=app --cov-branch --cov-report=xml
.\.venv\Scripts\python.exe scripts\check_risk_coverage.py
.\.venv\Scripts\python.exe scripts\check_p2_coverage.py
.\.venv\Scripts\python.exe scripts\check_p3_coverage.py
cd ..\..
bash apps/backend/scripts/check_strategy_isolation.sh
bash apps/backend/scripts/check_mcp_readonly.sh
bash apps/backend/scripts/check_no_llm_in_order_path.sh
bash apps/backend/scripts/check_broker_isolation.sh
bash apps/backend/scripts/check_no_env_credentials.sh

# ADR 0002 invariant test
cd apps\backend
.\.venv\Scripts\python.exe -m pytest tests/test_adr_0002_invariant.py -q
cd ..\..
```

- [ ] Crypto + store + endpoint tests pass (~27 new).
- [ ] Full backend suite green; risk branch-coverage ≥ 0.85.
- [ ] All **eight** invariants pass (seven existing + new credential env-isolation).
- [ ] `tests/test_adr_0002_invariant.py` still green.

---

## §4.14 — Manual smoke (load-bearing; Norton-deferred)

The four load-bearing flows that must still work after §4:

1. **Auth (P5 §3)**: log in via `/login` page with email + password + TOTP. Cookie sets. `/api/v1/auth/me` returns the user.
2. **Paper order (P1 + P5 §1-§2)**: submit a paper market order for AAPL qty=1. Order routes through registry → adapter → audit log. Audit chain byte-identical to pre-§4 (modulo timestamps/ids).
3. **Anthropic agent (P3)**: send a question to the agent endpoint. Agent reads Anthropic key from store, calls the API, returns a response.
4. **Pine webhook (P4 §1)**: POST a synthetic TradingView alert to the webhook endpoint with the user's Pine secret. Webhook authenticates via store, surfaces the alert in Opportunities.

**Deferred to WSL/CI** per the same Norton SSL + no-Docker pattern as Sessions 0, 2, 3. The in-suite tests in §4.13 stand in for the load-bearing assertions; the live diff runs in WSL/CI before the tag is promoted to a release.

- [ ] (WSL/CI) Login + paper order + agent + webhook all work after §4 ships.
- [ ] In-suite: all four flows have at least one test that exercises the credential-store path.

---

## §4.15 — Runbook update

Create `docs/runbook/credentials.md`. Cover:

1. **Master key** — generation, storage (.env), backup, leak response, rotation procedure (note: rotation requires re-encrypting every existing ciphertext — a one-off script in `scripts/rotate_master_key.py` that's documented but not part of §4 MVP).
2. **Per-credential lifecycle** — Not set → Active → Revoked → Hard-deleted. 7-day retention window for accidental-revoke recovery.
3. **Leak scenarios** — master key only, DB only, both. What to do in each case.
4. **TOTP rotation** — via `scripts/create_user.py` or `/auth/totp/setup` + `/auth/totp/verify`. Not the generic credentials API.
5. **Inspecting credential metadata** — sqlite3 commands showing kind/timestamps but not plaintext (can't decrypt without master key).

- [ ] Runbook covers master key, lifecycle, leak scenarios, TOTP rotation, inspection.

---

## §4.16 — Commit, PR, tag

```bash
git add apps/backend/app/security/
git add apps/backend/app/db/models/user_credential.py
git add apps/backend/app/db/models/__init__.py
git add apps/backend/alembic/versions/
git add apps/backend/app/lifespan.py
git add apps/backend/app/brokers/registry.py
git add apps/backend/app/brokers/alpaca/credentials.py
git add apps/backend/app/agent/runtime.py
git add apps/backend/app/api/v1/alerts.py
git add apps/backend/app/api/v1/auth.py
git add apps/backend/app/api/v1/credentials.py
git add apps/backend/app/main.py
git add apps/backend/scripts/check_no_env_credentials.sh
git add apps/backend/tests/security/
git add apps/backend/tests/api/test_p5_credentials_endpoint.py
git add scripts/generate_master_key.py
git add scripts/create_user.py                       # updated to use credential store
git add apps/frontend/src/api/credentials.ts
git add apps/frontend/src/pages/Settings/Credentials.tsx
git add apps/frontend/src/App.tsx
git add .github/workflows/ci.yml
git add docs/runbook/credentials.md

# Bundled close-out (Session 3 punch list)
git rm apps/backend/app/auth/future.py

git commit -m "feat(p5): credential encryption — Fernet store for all secrets (P5 §4)"
git push -u origin feat/p5-session4-credentials

gh pr create --base main --title "feat(p5): credential encryption (P5 §4)" --body "..."

# Walk away ≥1h, then re-read with attention to the data migration and the
# credentials_for_mode async swap.

gh pr merge --squash --subject "feat(p5): credential encryption (P5 §4) (#NN)" --delete-branch
git checkout main && git pull
git tag -a p5-session4-complete -m "P5 §4 credential encryption complete"
git push origin p5-session4-complete
```

PR body should state: critical security upgrade; four load-bearing flows verified in-suite (auth, paper order, agent, Pine webhook); live runtime smoke deferred to WSL/CI per Norton; ADR 0002 invariant test still green; `credentials_for_mode()` swap-point honored (signature shape preserved, body switched, async propagation handled); `app/auth/future.py` deletion bundled as Session 3 close-out; NOT in scope: KMS, automated rotation, multi-tenant key isolation, `stub.py` rename.

- [ ] PR opened; CI green incl. eight invariants.
- [ ] Walk-away ≥1h; data migration re-read; async propagation verified.
- [ ] Merged; `p5-session4-complete` tagged; `tasks/todo.md` updated.

---

## Verification Checklist (full session)

- [ ] §4.1 Master key generated, in `.env`, not in git.
- [ ] §4.2 Crypto module with `encrypt`/`decrypt`/`verify_master_key`.
- [ ] §4.3 CredentialStore with get/set/revoke/list/hard_delete_revoked; `_ensure_aware()` coerces SQLite naive datetimes.
- [ ] §4.4 user_credentials table + data migration round-trips with master key.
- [ ] §4.5 Backend refuses to boot without master key; ordering: verify → DB → registry.
- [ ] §4.6 `credentials_for_mode()` swapped to async + store reads; registry callers propagate await; `_router_token` discipline preserved.
- [ ] §4.7 AgentRuntime swap: per-user Anthropic keys.
- [ ] §4.8 TV webhook swap: constant-time match against stored secrets.
- [ ] §4.9 Auth/login + setup + create_user.py swap: TOTP via credential store.
- [ ] §4.10 `/credentials/` endpoints; TOTP excluded from generic PUT/DELETE.
- [ ] §4.11 Settings → Credentials page renders, set/rotate/revoke work.
- [ ] §4.12 `check_no_env_credentials.sh` CI tripwire created and wired (eighth invariant).
- [ ] §4.13 27+ backend tests pass; eight invariants pass; ADR 0002 test green.
- [ ] §4.14 In-suite proof of four load-bearing flows; live runtime deferred to WSL/CI.
- [ ] §4.15 Runbook covers master key + lifecycle + leak scenarios.
- [ ] §4.16 PR merged, tag pushed; `app/auth/future.py` deleted as bundled close-out.

---

## Notes & Gotchas

1. **The master key is the single point of failure.** Gotcha-of-record. If it leaks AND the DB leaks, every secret is recoverable. Treat it like a production root password: never commit, never log, never paste. The runbook in §4.15 is the durable place for this discipline; the .env file is the operational reality.

2. **The data migration requires the master key at migration time.** Alembic's `upgrade()` reads `WORKBENCH_MASTER_KEY` from env to encrypt the migrated secrets. If the env var is unset, the migration fails with a clear error. **Set the master key before running the migration**, otherwise you'll have a half-migrated DB.

3. **Backend refuses to boot without the master key.** §4.5: `sys.exit(1)`, not a raise. The error reaches stdout/stderr clearly; the user knows what to do. Alternatives (boot in "degraded" mode, fall back to env vars) would defeat the purpose of the encryption — there's no halfway-working state we want to support.

4. **`_ensure_aware()` coerces SQLite naive datetimes.** Same gotcha Session 3 handled in `stub.py::_aware`: SQLite returns timezone-aware datetimes as naive. Every comparison in `credential_store.py` that touches a stored datetime (`hard_delete_revoked`, the metadata returned by `list_kinds`) coerces with `_ensure_aware()`. Without this, the cleanup job and the metadata view would behave subtly wrong on SQLite.

5. **`credentials_for_mode()` became async.** The Session 2 §2.3 swap-point promise was "same signature, env→store." The signature *shape* is preserved (mode in, AlpacaCredentials out), but the function is now async — credential store ops are async, no way around it. Callers (`BrokerRegistry._construct/_try_construct/load_all/refresh`) propagate the await. Grep-confirm: `grep -RE "credentials_for_mode" apps/backend/app` — every call site is awaited.

6. **`app/auth/internal.py` is unrelated.** Session 3 shipped a shared-secret dependency for MCP service-to-service calls (`X-Workbench-Auth` / `MCP_BACKEND_TOKEN`). That's NOT a per-user credential; it's a service identity. The credential store does NOT manage it. `MCP_BACKEND_TOKEN` stays as an env var because it's set by the operator (you), not by individual users.

7. **The N-decrypts-per-webhook cost.** §4.8: matching a presented Pine secret against stored secrets requires decrypting every active user's secret. For single-digit users that's fine; for multi-user scales the optimization is a SHA-256(secret) lookup index in a separate column. Not §4 scope.

8. **TOTP rotation goes through the auth flow, not the generic credentials PUT.** §4.10's `set_credential` explicitly refuses TOTP_SECRET. The user-facing surface for TOTP is `scripts/create_user.py` (initial setup) or the §3 auth endpoints (`/auth/totp/setup` + `/auth/totp/verify`). Don't add a "rotate TOTP" button to the Credentials page — it'd duplicate auth logic.

9. **Plaintext never returned by `list_kinds`.** Strict invariant. If you ever add a debug endpoint that returns plaintext for inspection, gate it behind a feature flag that's off by default, audit-log every call, and never expose it on the public API surface.

10. **Revoked rows stay for 7 days, then hard-deleted by a scheduled job.** §4.3's `hard_delete_revoked()`. The job runs daily via APScheduler — wire it into `lifespan.py` alongside the existing scheduled jobs.

11. **Best-effort env-var capture during migration only fires for `user_id=1`.** §4.4's data migration is the bootstrap migration for the existing single-user setup. After §4 ships, new users set credentials via the UI; no env-var migration applies to them.

12. **Fernet ciphertexts include a creation timestamp.** Useful for forensics — `Fernet.extract_timestamp(token)` reveals when a credential was originally encrypted. If you suspect ciphertext tampering, comparing the extracted timestamp against `user_credentials.created_at` is a sanity check.

13. **Downgrade restores plaintext.** §4.4's `downgrade()`: undoing the migration writes the secrets back as plaintext into the old columns. Downgrade is for emergency rollback only; treat it as a "data is leaked" state and rotate all secrets immediately after. The runbook in §4.15 doesn't document downgrade as a routine operation precisely because it's an emergency-only path.

14. **`check_no_env_credentials.sh` excludes `app/security/` AND the alembic versions directory.** §4.12: the migration legitimately reads `WORKBENCH_MASTER_KEY` and the bootstrap env vars to perform the data move. The CI script's `-not -path` clauses cover `app/security/`; alembic versions are outside `app/` so they're already excluded by the `ROOT` scope.

15. **ADR 0002 discipline is preserved without modification.** The credential-store swap touches adapter *construction*, not the OrderRouter → adapter *call path*. `_router_token` still gates broker mutators. `tests/test_adr_0002_invariant.py` stays green without edits because no new `submit_order` callers appear outside `app/orders/`.

16. **ADR 0008 implication (flexibility principle).** The credential store's `CredentialKind` enum is fixed at seven kinds in §4. Adding a new credential kind in the future (e.g., for a different model provider, or for a second broker) is an additive change: new enum value, no schema change, no migration. This means future AI tooling integrations don't require §4-level rework — exactly the behavior ADR 0008 commits to.

17. **`app/auth/future.py` deletion is bundled.** Session 3 Results flagged this as a stale file. Session 4 §4.16 includes `git rm apps/backend/app/auth/future.py` because Session 4 is touching adjacent auth code anyway and the file is misleading. Not a separate hygiene PR.

18. **Walk away before merging.** This PR touches the data migration, `credentials_for_mode()`, the broker registry, the agent runtime, the webhook receiver, the auth flow, and adds a new CI invariant. ~700 lines of code change plus the migration. Fresh eyes catch the subtleties — especially in the migration.

19. **Don't bundle P5 §5 (live-mode risk gates) into this PR.** Each P5 session is its own tag.

---

*End of P5 Session 4 v1.0. Supersedes v0.1 (which was drafted before Sessions 1, 2, 3 actually shipped).*
