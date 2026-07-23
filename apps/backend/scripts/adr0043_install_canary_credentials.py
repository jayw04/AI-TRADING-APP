"""ADR-0043 canary credential install — set user 3's isolated paper key + secret ATOMICALLY.

Installs exactly two encrypted records for the canary user (default user 3): its Alpaca PAPER key and
secret, as ONE transaction. It never reads, decrypts, overwrites, revokes, or reseeds any OTHER
user's credential (the momentum user 1 must stay byte-identical), and never prints the secret or the
full key.

Why a bespoke wrapper: CredentialStore.set() commits per call, so two set() calls could leave a
persistent half-installed pair if the second write fails. This writes BOTH encrypted records in one
transaction, re-reads them in-transaction, round-trip-verifies each, proves user 1 unchanged, and
commits only when exactly one active record of each kind exists — otherwise it rolls back completely.

Secret handling: the secret is read from STDIN (pipe the root-only 0600 file into the process), never
from argv/env. The API key is a NON-SECRET argument; evidence carries only its 6-char prefix.

  dry run (default): run the gate + atomic write + in-txn proofs, then ROLL BACK (writes nothing).
  --apply:           commit the pair.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import sys
from datetime import UTC, datetime

from sqlalchemy import func, select, text

from app.db.models.user_credential import UserCredential
from app.security.credential_store import CredentialKind
from app.security.crypto import decrypt, encrypt

CANARY_KEY_PREFIX = "PKZYTY"
_TERMINAL = ("filled", "canceled", "cancelled", "rejected", "expired", "replaced")


class InstallError(RuntimeError):
    """Any fail-closed refusal: gate failure, non-atomic state, or invariant violation."""


async def _user1_cred_digest(session) -> str:
    rows = (await session.execute(text(
        "SELECT kind, hex(ciphertext) AS ch, revoked_at FROM user_credentials "
        "WHERE user_id = 1 ORDER BY kind"))).all()
    return hashlib.sha256(
        json.dumps([list(r) for r in rows], sort_keys=True, default=str).encode()).hexdigest()


async def _active_count(session, user_id: int, kind: CredentialKind) -> int:
    return int((await session.execute(
        select(func.count()).select_from(UserCredential).where(
            UserCredential.user_id == user_id,
            UserCredential.kind == kind.value,
            UserCredential.revoked_at.is_(None)))).scalar())


async def _active_row(session, user_id: int, kind: CredentialKind) -> UserCredential | None:
    return (await session.execute(
        select(UserCredential).where(
            UserCredential.user_id == user_id,
            UserCredential.kind == kind.value,
            UserCredential.revoked_at.is_(None)))).scalars().first()


async def _pre_install_gate(session, user_id: int, expected_user1_digest: str, api_key: str) -> list[str]:
    v: list[str] = []
    if not api_key.startswith(CANARY_KEY_PREFIX):
        v.append(f"api key prefix != {CANARY_KEY_PREFIX} (got {api_key[:6]!r})")
    nu = int((await session.execute(text("SELECT COUNT(*) FROM users WHERE id=:u"), {"u": user_id})).scalar())
    if nu != 1:
        v.append(f"user {user_id} not present exactly once (count={nu})")
    a = (await session.execute(text(
        "SELECT user_id,broker,mode,label FROM accounts WHERE id=:a"), {"a": user_id})).first()
    if a is None:
        v.append(f"account {user_id} does not exist")
    elif not (a[0] == user_id and str(a[1]) == "alpaca" and str(a[2]) == "paper" and a[3] == "ADR-0043 canary"):
        v.append(f"account {user_id} identity mismatch: {tuple(a)}")
    ncred = int((await session.execute(text(
        "SELECT COUNT(*) FROM user_credentials WHERE user_id=:u AND revoked_at IS NULL"),
        {"u": user_id})).scalar())
    if ncred:
        v.append(f"user {user_id} already has {ncred} active credential(s)")
    d = await _user1_cred_digest(session)
    if d != expected_user1_digest:
        v.append(f"user-1 credential digest changed ({d[:12]}… != expected {expected_user1_digest[:12]}…)")
    oo = int((await session.execute(text(
        "SELECT COUNT(*) FROM orders WHERE lower(status) NOT IN ("
        + ",".join(f"'{t}'" for t in _TERMINAL) + ")"))).scalar())
    if oo:
        v.append(f"{oo} open order(s) exist")
    hr = int((await session.execute(text(
        "SELECT COUNT(*) FROM risk_reservations WHERE state='HELD'"))).scalar())
    if hr:
        v.append(f"{hr} HELD reservation(s) exist")
    return v


async def _upsert(session, user_id: int, kind: CredentialKind, plaintext: str, now: datetime) -> None:
    if not plaintext:
        raise InstallError(f"empty plaintext for {kind.value}")
    ct = encrypt(plaintext)
    existing = await _active_row(session, user_id, kind)
    if existing is not None:
        existing.ciphertext = ct
        existing.updated_at = now
        existing.revoked_at = None
    else:
        session.add(UserCredential(user_id=user_id, kind=kind.value, ciphertext=ct,
                                   created_at=now, updated_at=now))


async def install(session_factory, *, user_id: int, api_key: str, secret: str,
                  expected_user1_digest: str, apply: bool) -> dict:
    async with session_factory() as session:
        viol = await _pre_install_gate(session, user_id, expected_user1_digest, api_key)
        if viol:
            raise InstallError("pre-install gate failed (fail-closed): " + "; ".join(viol))
        try:
            now = datetime.now(UTC)
            await _upsert(session, user_id, CredentialKind.ALPACA_PAPER_KEY, api_key, now)
            await _upsert(session, user_id, CredentialKind.ALPACA_PAPER_SECRET, secret, now)
            await session.flush()
            # exactly one active of each kind, in-transaction
            for kind in (CredentialKind.ALPACA_PAPER_KEY, CredentialKind.ALPACA_PAPER_SECRET):
                n = await _active_count(session, user_id, kind)
                if n != 1:
                    raise InstallError(f"expected exactly 1 active {kind.value} in-txn, got {n}")
            kr = await _active_row(session, user_id, CredentialKind.ALPACA_PAPER_KEY)
            sr = await _active_row(session, user_id, CredentialKind.ALPACA_PAPER_SECRET)
            # round-trip proof (decrypt stored == input) — proves correct storage without printing
            if decrypt(kr.ciphertext) != api_key:
                raise InstallError("stored key failed round-trip verification")
            if decrypt(sr.ciphertext) != secret:
                raise InstallError("stored secret failed round-trip verification")
            # protected invariance: user-1 credential digest unchanged in-transaction
            u1_after = await _user1_cred_digest(session)
            if u1_after != expected_user1_digest:
                raise InstallError("user-1 credential digest changed in-transaction; rolling back")
            evidence = {
                "user_id": user_id,
                "alpaca_paper_key_active_count": await _active_count(
                    session, user_id, CredentialKind.ALPACA_PAPER_KEY),
                "alpaca_paper_secret_active_count": await _active_count(
                    session, user_id, CredentialKind.ALPACA_PAPER_SECRET),
                "key_prefix": api_key[:len(CANARY_KEY_PREFIX)],
                "key_ciphertext_sha256": hashlib.sha256(kr.ciphertext).hexdigest(),
                "secret_ciphertext_sha256": hashlib.sha256(sr.ciphertext).hexdigest(),
                "key_created_at": kr.created_at, "key_updated_at": kr.updated_at,
                "secret_created_at": sr.created_at, "secret_updated_at": sr.updated_at,
                "round_trip_verified": True,
                "user1_cred_digest": u1_after,
                "user1_cred_digest_unchanged": u1_after == expected_user1_digest,
            }
            if apply:
                await session.commit()
            else:
                await session.rollback()
        except Exception:
            await session.rollback()
            raise
    evidence["applied"] = apply
    evidence["mode"] = "installed" if apply else "dry_run:rolled_back"
    return evidence


async def _amain(argv=None) -> int:
    ap = argparse.ArgumentParser(description="ADR-0043 canary credential install (user-3 paper key+secret)")
    ap.add_argument("--user-id", type=int, default=3)
    ap.add_argument("--api-key", required=True, help="NON-SECRET Alpaca paper key id (prefix PKZYTY…)")
    ap.add_argument("--expected-user1-cred-digest", required=True,
                    help="user-1 credential digest that must stay unchanged")
    ap.add_argument("--apply", action="store_true", help="commit (default is a dry run that rolls back)")
    args = ap.parse_args(argv)

    secret = sys.stdin.read().strip()  # the root-only 0600 file is piped in; never argv/env
    if not secret:
        print("REFUSED: empty secret on stdin", file=sys.stderr)
        return 2
    from app.db.session import get_sessionmaker

    try:
        ev = await install(get_sessionmaker(), user_id=args.user_id, api_key=args.api_key,
                           secret=secret, expected_user1_digest=args.expected_user1_cred_digest,
                           apply=args.apply)
    except InstallError as exc:
        print(f"REFUSED: {exc}", file=sys.stderr)
        return 2
    finally:
        secret = "\x00" * len(secret)  # best-effort scrub
        del secret
    print(json.dumps(ev, indent=2, default=str))
    return 0


def main() -> int:
    return asyncio.run(_amain())


if __name__ == "__main__":
    raise SystemExit(main())
