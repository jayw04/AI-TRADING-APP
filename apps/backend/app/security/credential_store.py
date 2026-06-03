"""Persistent encrypted credential store.

Operations:
  - get(user_id, kind) → plaintext (or None if not set / revoked)
  - set(user_id, kind, plaintext) — set or rotate
  - revoke(user_id, kind) — soft-revoke (keeps ciphertext one week for
    forensic recovery, then hard-deleted by a scheduled job)
  - list_kinds(user_id) → metadata only (kind, last_used_at, created_at,
    has_value). Plaintext NEVER returned by list.

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

from datetime import UTC, datetime, timedelta
from enum import StrEnum

import structlog
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.user_credential import UserCredential
from app.security.crypto import decrypt, encrypt
from app.utils.time import ensure_aware as _ensure_aware

logger = structlog.get_logger(__name__)


class CredentialKind(StrEnum):
    """Every secret stored in user_credentials."""

    ALPACA_PAPER_KEY = "alpaca_paper_key"
    ALPACA_PAPER_SECRET = "alpaca_paper_secret"
    ALPACA_LIVE_KEY = "alpaca_live_key"
    ALPACA_LIVE_SECRET = "alpaca_live_secret"
    ANTHROPIC_API_KEY = "anthropic_api_key"
    PINE_WEBHOOK_SECRET = "pine_webhook_secret"
    TOTP_SECRET = "totp_secret"
    # P5.5 §3: bearer token the workbench-mcp server presents to the backend.
    # Resolved to the owning user by app/auth/stub.py::_resolve_from_bearer_token.
    WORKBENCH_MCP_KEY = "workbench_mcp_key"
    # P6 §1a: bearer token the agent service (apps/agent/) presents to the
    # backend HTTP API (e.g. GET /api/v1/agent/budget). Per Decision 2 the agent
    # uses this as a first-class bearer credential. Resolved by
    # app/auth/stub.py::_resolve_from_bearer_token.
    AGENT_API_KEY = "agent_api_key"


class CredentialNotFoundError(RuntimeError):
    """Raised by .get(..., required=True) when the credential doesn't exist."""


REVOKED_RETENTION = timedelta(days=7)

# _ensure_aware is the shared app.utils.time.ensure_aware (P5 §5 extracted the
# canonical copy; imported as _ensure_aware above to keep the call sites below).


class CredentialMetadata:
    """Sanitized view: what /credentials lists. NEVER includes plaintext."""

    def __init__(
        self,
        *,
        kind: CredentialKind,
        has_value: bool,
        created_at: datetime | None,
        updated_at: datetime | None,
        last_used_at: datetime | None,
        revoked_at: datetime | None,
    ):
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
    ) -> str | None:
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
        row.last_used_at = datetime.now(UTC)
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
        now = datetime.now(UTC)
        existing = await self._fetch_active(user_id, kind)
        if existing is not None:
            existing.ciphertext = ciphertext
            existing.updated_at = now
            existing.revoked_at = None
        else:
            self._session.add(
                UserCredential(
                    user_id=user_id,
                    kind=kind.value,
                    ciphertext=ciphertext,
                    created_at=now,
                    updated_at=now,
                )
            )
        await self._session.commit()
        logger.info("credential_set", user_id=user_id, kind=kind.value)

    async def revoke(self, user_id: int, kind: CredentialKind) -> None:
        """Soft-delete. The ciphertext stays for 7 days for forensic
        recovery; the scheduled cleanup job hard-deletes after that."""
        existing = await self._fetch_active(user_id, kind)
        if existing is None:
            return
        existing.revoked_at = datetime.now(UTC)
        await self._session.commit()
        logger.info("credential_revoked", user_id=user_id, kind=kind.value)

    async def list_kinds(self, user_id: int) -> list[CredentialMetadata]:
        """Return metadata for every kind for this user. Includes
        not-set kinds so the UI can show 'not configured' state."""
        result = (
            await self._session.execute(
                select(UserCredential).where(UserCredential.user_id == user_id)
            )
        ).scalars().all()
        by_kind: dict[str, UserCredential] = {r.kind: r for r in result}
        out: list[CredentialMetadata] = []
        for kind in CredentialKind:
            row = by_kind.get(kind.value)
            if row is None:
                out.append(
                    CredentialMetadata(
                        kind=kind,
                        has_value=False,
                        created_at=None,
                        updated_at=None,
                        last_used_at=None,
                        revoked_at=None,
                    )
                )
            else:
                out.append(
                    CredentialMetadata(
                        kind=kind,
                        has_value=(row.revoked_at is None),
                        created_at=row.created_at,
                        updated_at=row.updated_at,
                        last_used_at=row.last_used_at,
                        revoked_at=row.revoked_at,
                    )
                )
        return out

    async def hard_delete_revoked(self) -> int:
        """Scheduled cleanup: delete rows revoked > REVOKED_RETENTION ago.
        Called by APScheduler daily. Returns count deleted.

        Comparison coerces both sides to aware-UTC (SQLite gotcha)."""
        cutoff = datetime.now(UTC) - REVOKED_RETENTION
        # Pull candidates first so we can coerce the SQLite-returned
        # naive datetimes before comparing.
        candidates = (
            await self._session.execute(
                select(UserCredential).where(UserCredential.revoked_at.isnot(None))
            )
        ).scalars().all()
        to_delete: list[int] = []
        for r in candidates:
            revoked = _ensure_aware(r.revoked_at)
            # The WHERE clause guarantees revoked_at is non-null; the guard
            # keeps the type checker honest about _ensure_aware's Optional.
            if revoked is not None and revoked < cutoff:
                to_delete.append(r.id)
        if not to_delete:
            return 0
        await self._session.execute(
            delete(UserCredential).where(UserCredential.id.in_(to_delete))
        )
        await self._session.commit()
        return len(to_delete)

    # ---------------- internals ----------------

    async def _fetch_active(
        self,
        user_id: int,
        kind: CredentialKind,
    ) -> UserCredential | None:
        return (
            await self._session.execute(
                select(UserCredential)
                .where(UserCredential.user_id == user_id)
                .where(UserCredential.kind == kind.value)
                .where(UserCredential.revoked_at.is_(None))
            )
        ).scalars().first()
