"""Re-provision creds + reconcile DB state for RECREATED paper accounts.

When a paper account is reset by DELETE + CREATE (new account, new keys), two things
go stale in our system:
  1. The encrypted credential store still holds the OLD keys (the registry reads from
     the store, NOT from .env — credentials.py:credentials_for_mode / ADR 0003), so the
     backend can't reach the new account.
  2. Rows that referenced the deleted account are now wrong — most importantly any
     non-terminal orders (they will NEVER fill; the broker account is gone), which the
     pending-aware risk gates (ADR 0025) and the strategy idempotency guard count as
     "in flight" — and the deleted account's equity_snapshots history.

This script, per recreated account (default users 2,3,4 ↔ ALPACA_PAPER_1/2/3):
  (a) writes the new key/secret from .env into the credential store (CredentialStore.set);
  (b) CANCELs every non-terminal order on that account (audited ORDER_CANCELED_LOCAL);
  (c) deletes that account's equity_snapshots (deleted-account history).

It does NOT touch positions (the recreated accounts have none) and does NOT touch
account 1 (not recreated). accounts_state self-heals on the next account_sync once the
backend is restarted to rebuild the registry adapters under the new keys.

Run from the REPO ROOT (so ./data/workbench.sqlite resolves to the Docker-mounted DB),
with WORKBENCH_MASTER_KEY set (it's read from .env). DRY-RUN by default — pass --apply
to write. Key/secret VALUES are never printed.

    apps/backend/.venv/Scripts/python.exe apps/backend/scripts/reset_recreated_accounts.py            # plan
    apps/backend/.venv/Scripts/python.exe apps/backend/scripts/reset_recreated_accounts.py --apply    # execute

Then: restart the backend (docker compose restart backend) so the registry picks up the
new keys, and re-validate the sync.
"""
from __future__ import annotations

import argparse
import asyncio
import os
import sys
from datetime import UTC, datetime
from pathlib import Path

from dotenv import load_dotenv

# override=True: .env is the source of truth for this re-provision (the new keys live
# there). It also wins over any stale WORKBENCH_MASTER_KEY/DB_URL in the calling shell.
# Run from the REPO ROOT so .env's relative ./data/workbench.sqlite resolves to the
# bind-mounted DB the backend uses.
load_dotenv(Path(".env"), override=True)  # WORKBENCH_MASTER_KEY + source creds
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # make `app` importable

from sqlalchemy import delete, select, update  # noqa: E402

from app.audit import AuditAction, AuditActorType, AuditLogger  # noqa: E402
from app.db.enums import TERMINAL_ORDER_STATUSES, OrderStatus  # noqa: E402
from app.db.models.account import Account, AccountMode  # noqa: E402
from app.db.models.equity_snapshot import EquitySnapshot  # noqa: E402
from app.db.models.order import Order  # noqa: E402
from app.db.session import get_sessionmaker  # noqa: E402
from app.security.credential_store import CredentialKind, CredentialStore  # noqa: E402

# user_id -> .env var prefix for that account's NEW paper key/secret.
USER_ENV = {2: "ALPACA_PAPER_1", 3: "ALPACA_PAPER_2", 4: "ALPACA_PAPER_3"}


async def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="execute (default: dry-run plan)")
    ap.add_argument("--users", default="2,3,4", help="comma-separated user ids (default 2,3,4)")
    args = ap.parse_args(argv)
    users = [int(x) for x in args.users.split(",") if x.strip()]
    dry = not args.apply
    tag = "PLAN (dry-run)" if dry else "APPLY"
    now = datetime.now(UTC)

    Session = get_sessionmaker()
    async with Session() as session:
        store = CredentialStore(session)
        for uid in users:
            prefix = USER_ENV.get(uid)
            if not prefix:
                print(f"[user {uid}] no .env mapping — skip")
                continue
            key = (os.environ.get(f"{prefix}_API_KEY") or "").strip()
            sec = (os.environ.get(f"{prefix}_API_SECRET") or "").strip()
            acct = await session.scalar(
                select(Account).where(
                    Account.user_id == uid, Account.broker == "alpaca",
                    Account.mode == AccountMode.paper,
                )
            )
            if acct is None:
                print(f"[user {uid}] no paper account row — skip")
                continue
            print(f"\n[user {uid} / account {acct.id} ({acct.label})] {tag}")

            # (a) creds
            if key and sec:
                print(f"  creds: set ALPACA_PAPER_KEY/SECRET from {prefix}_* "
                      f"(key id {key[:4]}…)")
                if not dry:
                    await store.set(uid, CredentialKind.ALPACA_PAPER_KEY, key)
                    await store.set(uid, CredentialKind.ALPACA_PAPER_SECRET, sec)
            else:
                print(f"  creds: ⚠ {prefix}_API_KEY/SECRET missing in .env — NOT set")

            # (b) cancel stale non-terminal orders (deleted broker account).
            # Core select/update on existing columns only — avoids loading the full
            # ORM row, so this runs even if the live DB predates a newer column
            # (e.g. orders.estimated_notional from a not-yet-applied migration).
            stale = (await session.execute(
                select(Order.id, Order.user_id).where(
                    Order.account_id == acct.id,
                    Order.status.notin_(TERMINAL_ORDER_STATUSES),
                )
            )).all()
            print(f"  orders: {len(stale)} non-terminal -> CANCELED")
            if not dry:
                for oid, ouid in stale:
                    await session.execute(
                        update(Order).where(Order.id == oid).values(
                            status=OrderStatus.CANCELED,
                            rejection_reason="reconciled: paper account recreated (reset)",
                            terminal_at=now, updated_at=now,
                        )
                    )
                    AuditLogger.write(
                        session, actor_type=AuditActorType.SYSTEM, actor_id="reset-script",
                        action=AuditAction.ORDER_CANCELED_LOCAL, target_type="order",
                        target_id=oid, user_id=ouid,
                        payload={"reason": "account_recreated_reset", "account_id": acct.id},
                    )

            # (c) drop deleted-account equity history
            snaps = (await session.execute(
                select(EquitySnapshot.id).where(EquitySnapshot.account_id == acct.id)
            )).scalars().all()
            print(f"  equity_snapshots: {len(snaps)} -> delete")
            if not dry:
                await session.execute(
                    delete(EquitySnapshot).where(EquitySnapshot.account_id == acct.id)
                )

        if not dry:
            await session.commit()
            print("\nCOMMITTED.")
        else:
            print("\n(dry-run — nothing written. Re-run with --apply.)")

    print("\nNEXT: restart the backend (docker compose restart backend) so the registry "
          "rebuilds adapters under the new keys, then re-validate the sync.")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
