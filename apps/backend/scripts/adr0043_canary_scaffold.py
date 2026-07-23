"""ADR-0043 canary scaffold — create ONLY the isolated canary user 3 + account 3.

Governed, single-transaction, fail-closed. It creates EXACTLY two rows — user_id=3 and
account_id=3 (broker ``alpaca``, mode ``paper``, label "ADR-0043 canary") — and nothing else. It
NEVER creates positions/orders/reservations/loss-control/breaker/strategy/risk-limit rows, and NEVER
reads or mutates the momentum user 1 / account 1 or any credential ciphertext. The only writes beyond
the two rows are SQLite id-sequence repair, so later ordinary inserts cannot collide with the
explicitly-assigned id 3.

Explicit id=3 is deliberate: the deployed canary code and governance artifacts bind USER=3 / ACCT=3.

Idempotent: a rerun succeeds ONLY if user 3 + account 3 already match the frozen canary identity
EXACTLY. Any partial or contradictory state stops with a specific error — it never edits rows into
conformance.

The whole operation runs in one transaction; if the protected user-1 / account-1 / credential digests
change for any reason, or any precondition fails, it rolls back and the DB is untouched.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import sys

from sqlalchemy import text

from app.db.models.account import Account, AccountMode
from app.db.models.user import User

# ---- frozen canary identity (the ONLY rows this tool may create) ----
CANARY_USER_ID = 3
CANARY_ACCOUNT_ID = 3
CANARY_EMAIL = "adr0043-canary@localhost"
CANARY_DISPLAY = "ADR-0043 Canary"
CANARY_BROKER = "alpaca"
CANARY_MODE = AccountMode.paper
CANARY_LABEL = "ADR-0043 canary"

_TERMINAL = ("filled", "canceled", "cancelled", "rejected", "expired", "replaced")


class CanaryScaffoldError(RuntimeError):
    """Any fail-closed refusal: precondition failure, identity conflict, or invariant violation."""


def _sha(obj) -> str:
    return hashlib.sha256(json.dumps(obj, sort_keys=True, default=str).encode()).hexdigest()


async def _row(session, table: str, rid: int) -> dict | None:
    r = (await session.execute(text(f"SELECT * FROM {table} WHERE id = :i"), {"i": rid})).mappings().first()
    return dict(r) if r is not None else None


async def _protected_digests(session) -> dict:
    """Digests of exactly the things this tool must never change: user 1, account 1, and user-1's
    credential ciphertexts (by hex, so a change to the encrypted bytes is detected without decrypting)."""
    u1 = await _row(session, "users", 1)
    a1 = await _row(session, "accounts", 1)
    creds = (await session.execute(text(
        "SELECT kind, hex(ciphertext) AS ch, revoked_at FROM user_credentials WHERE user_id = 1 ORDER BY kind"
    ))).mappings().all()
    return {
        "user1_row": _sha(u1) if u1 else None,
        "account1_row": _sha(a1) if a1 else None,
        "user1_creds": _sha([dict(c) for c in creds]),
    }


async def _counts(session) -> dict:
    async def scalar(q: str):
        return (await session.execute(text(q))).scalar()

    open_orders_q = (
        "SELECT COUNT(*) FROM orders WHERE lower(status) NOT IN ("
        + ",".join(f"'{t}'" for t in _TERMINAL) + ")"
    )
    return {
        "users": await scalar("SELECT COUNT(*) FROM users"),
        "accounts": await scalar("SELECT COUNT(*) FROM accounts"),
        "open_orders": await scalar(open_orders_q),
        "held_reservations": await scalar("SELECT COUNT(*) FROM risk_reservations WHERE state = 'HELD'"),
        "integrity": await scalar("PRAGMA integrity_check"),
    }


def _user3_conformant(u3: dict | None) -> bool:
    return bool(u3) and u3.get("email") == CANARY_EMAIL and u3.get("display_name") == CANARY_DISPLAY


def _account3_conformant(a3: dict | None) -> bool:
    return (
        bool(a3)
        and a3.get("user_id") == CANARY_USER_ID
        and str(a3.get("broker")) == CANARY_BROKER
        and str(a3.get("mode")) in (CANARY_MODE.value, str(CANARY_MODE))
        and a3.get("label") == CANARY_LABEL
    )


async def _preconditions(session) -> tuple[list[str], dict]:
    """Every condition that must hold immediately before a FRESH insert. Reported as a list of
    violations so the operator sees exactly which gate failed."""
    v: list[str] = []
    report: dict = {}
    if not await _row(session, "users", 1):
        v.append("user 1 does not exist")
    if not await _row(session, "accounts", 1):
        v.append("account 1 does not exist")
    report["user2_exists"] = bool(await _row(session, "users", 2))
    report["account2_exists"] = bool(await _row(session, "accounts", 2))
    if await _row(session, "users", CANARY_USER_ID):
        v.append("user 3 already exists")
    if await _row(session, "accounts", CANARY_ACCOUNT_ID):
        v.append("account 3 already exists")
    ncred = (await session.execute(text(
        "SELECT COUNT(*) FROM user_credentials WHERE user_id = :u"), {"u": CANARY_USER_ID})).scalar()
    if ncred:
        v.append(f"user 3 already has {ncred} credential(s)")
    cnt = await _counts(session)
    if cnt["open_orders"]:
        v.append(f"{cnt['open_orders']} open order(s) exist")
    if cnt["held_reservations"]:
        v.append(f"{cnt['held_reservations']} HELD reservation(s) exist")
    return v, report


async def _sequence_report(session, *, repair: bool) -> dict:
    """Ensure later ordinary inserts cannot collide with the explicit id 3. Handles BOTH id-generation
    mechanisms: AUTOINCREMENT tables (sqlite_sequence) are repaired to >= max(id); rowid tables need
    no repair (next rowid is max(id)+1) but are verified and reported. Never assumes which applies."""
    report: dict = {}
    has_seq_table = (await session.execute(text(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='sqlite_sequence'"))).scalar()
    for tbl in ("users", "accounts"):
        mx = int((await session.execute(text(f"SELECT COALESCE(MAX(id),0) FROM {tbl}"))).scalar())
        seq = None
        if has_seq_table:
            seq = (await session.execute(text(
                "SELECT seq FROM sqlite_sequence WHERE name = :n"), {"n": tbl})).scalar()
        if seq is not None:
            new = max(int(seq), mx)
            if repair:
                await session.execute(text(
                    "UPDATE sqlite_sequence SET seq = :s WHERE name = :n"), {"s": new, "n": tbl})
            report[tbl] = {"mechanism": "autoincrement", "max_id": mx, "seq": new, "next": new + 1}
        else:
            report[tbl] = {"mechanism": "rowid", "max_id": mx, "next": mx + 1}
        if report[tbl]["next"] <= mx:
            raise CanaryScaffoldError(f"sequence repair invariant failed for {tbl}: next <= max_id")
    return report


async def scaffold(session_factory, *, apply: bool = True) -> dict:
    """Create user 3 + account 3 in one fail-closed transaction, or roll back on any violation.

    apply=False performs the whole checked flow (including the digest-invariance proof) then rolls
    back — a true dry run that writes nothing.
    """
    async with session_factory() as session:
        pre_dig = await _protected_digests(session)
        pre_cnt = await _counts(session)
        u2_exists = bool(await _row(session, "users", 2))
        a2_exists = bool(await _row(session, "accounts", 2))
        try:
            u3 = await _row(session, "users", CANARY_USER_ID)
            a3 = await _row(session, "accounts", CANARY_ACCOUNT_ID)
            created: list[str] = []
            if u3 or a3:
                if _user3_conformant(u3) and _account3_conformant(a3):
                    mode = "idempotent_noop"
                else:
                    bad: list[str] = []
                    if u3 and not _user3_conformant(u3):
                        bad.append(f"user 3 exists but does not match frozen identity ({u3})")
                    if a3 and not _account3_conformant(a3):
                        bad.append(f"account 3 exists but does not match frozen identity ({a3})")
                    if u3 and not a3:
                        bad.append("partial state: user 3 exists without account 3")
                    if a3 and not u3:
                        bad.append("partial state: account 3 exists without user 3")
                    raise CanaryScaffoldError(
                        "canary identity conflict — refusing to edit rows into conformance: "
                        + "; ".join(bad))
                seq = await _sequence_report(session, repair=False)
            else:
                viol, _rep = await _preconditions(session)
                if viol:
                    raise CanaryScaffoldError("preconditions failed (fail-closed): " + "; ".join(viol))
                session.add(User(id=CANARY_USER_ID, email=CANARY_EMAIL, display_name=CANARY_DISPLAY))
                session.add(Account(id=CANARY_ACCOUNT_ID, user_id=CANARY_USER_ID, broker=CANARY_BROKER,
                                    mode=CANARY_MODE, label=CANARY_LABEL))
                await session.flush()
                created = [f"user:{CANARY_USER_ID}", f"account:{CANARY_ACCOUNT_ID}"]
                mode = "created"
                seq = await _sequence_report(session, repair=apply)

            # Invariant proof: the protected momentum rows + user-1 creds must be byte-identical.
            post_dig = await _protected_digests(session)
            changed = [k for k in pre_dig if pre_dig[k] != post_dig[k]]
            if changed:
                raise CanaryScaffoldError(
                    f"INVARIANT VIOLATION — protected rows changed {changed}; rolling back")

            post_cnt = await _counts(session)

            if apply:
                await session.commit()
            else:
                await session.rollback()
                mode = f"{mode}:dry_run"
        except Exception:
            await session.rollback()
            raise

    return {
        "mode": mode,
        "created": created,
        "frozen_identity": {
            "user_id": CANARY_USER_ID, "account_id": CANARY_ACCOUNT_ID, "email": CANARY_EMAIL,
            "display_name": CANARY_DISPLAY, "broker": CANARY_BROKER, "mode": CANARY_MODE.value,
            "label": CANARY_LABEL},
        "user2_exists": u2_exists,
        "account2_exists": a2_exists,
        "protected_digests_before": pre_dig,
        "protected_digests_after": post_dig,
        "protected_unchanged": changed == [],
        "counts_before": pre_cnt,
        "counts_after": post_cnt,
        "sequence": seq,
    }


async def _amain(argv=None) -> int:
    ap = argparse.ArgumentParser(description="ADR-0043 canary scaffold (user 3 + account 3 only)")
    ap.add_argument("--apply", action="store_true", help="commit (default is a dry run that rolls back)")
    args = ap.parse_args(argv)
    from app.db.session import get_sessionmaker

    try:
        result = await scaffold(get_sessionmaker(), apply=args.apply)
    except CanaryScaffoldError as exc:
        print(f"REFUSED: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(result, indent=2, default=str))
    return 0


def main() -> int:
    return asyncio.run(_amain())


if __name__ == "__main__":
    raise SystemExit(main())
