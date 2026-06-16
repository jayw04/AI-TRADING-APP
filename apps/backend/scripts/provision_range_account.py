"""Provision a SECOND user's dedicated paper account + credentials (§5a 2–3).

Range Trader runs isolated on its own ``ALPACA_PAPER_1`` paper account, owned by
a **second user** so ``(user, broker, mode)`` resolves cleanly to it (strategies
have no ``account_id`` — P5 §7). This script does §5a steps 2 and 3 of
``docs/implementation/TradingWorkbench_RangeTrader_PaperActivation_v0.1.md``:

  2. Store the ``ALPACA_PAPER_1`` creds (from ``.env``) under the second user in
     the encrypted credential store, as that user's ``ALPACA_PAPER_KEY`` /
     ``ALPACA_PAPER_SECRET``.
  3. Create the ``accounts`` row (broker ``alpaca``, mode ``paper``) for them.

Step 1 — creating the user itself (password + TOTP) — is the existing
``create_user.py``; run it FIRST:

    python scripts/create_user.py --email range@local --display-name "Range Trader"

Then, from the REPO ROOT (so the default DB path resolves to the mounted DB):

    apps/backend/.venv/Scripts/python.exe apps/backend/scripts/provision_range_account.py \
        --email range@local --label "Alpaca Paper (Range)"

Idempotent: re-running upserts the creds and leaves an existing paper account in
place. ``--dry-run`` reports what would change without writing.

⚠ Prerequisite: the per-user-adapter lifespan fix (§5a step 4) must be deployed,
or this account's orders will still route to the startup (BFY6) account at
runtime regardless of the creds stored here.

Credential VALUES are never printed — only a sha256 fingerprint + length, so a
boot/provision log can confirm *which* key without leaking it.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

# Load .env so crypto.py sees WORKBENCH_MASTER_KEY and we can read the source
# cred values. Run from repo root.
load_dotenv(Path(".env"), override=False)

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # make `app` importable

from sqlalchemy import select  # noqa: E402

from app.db.models import User  # noqa: E402
from app.db.models.account import Account, AccountMode  # noqa: E402
from app.db.session import get_sessionmaker  # noqa: E402
from app.security.credential_store import CredentialKind, CredentialStore  # noqa: E402

DEFAULT_LABEL = "Alpaca Paper (Range)"
DEFAULT_KEY_ENV = "ALPACA_PAPER_1_API_KEY"
DEFAULT_SECRET_ENV = "ALPACA_PAPER_1_API_SECRET"


class ProvisionError(RuntimeError):
    """A provisioning precondition failed (missing user, missing creds)."""


def fingerprint(value: str | None) -> str:
    """Non-reversible fingerprint for logging — never the secret itself."""
    if not value:
        return "none"
    return f"sha256:{hashlib.sha256(value.encode()).hexdigest()[:8]} (len={len(value)})"


async def provision_paper_account(
    session_factory,
    *,
    email: str,
    api_key: str,
    api_secret: str,
    label: str = DEFAULT_LABEL,
    dry_run: bool = False,
) -> dict:
    """Upsert the user's paper creds and ensure their paper ``accounts`` row.

    Returns a summary dict (ids + which actions ran + key fingerprint). Raises
    :class:`ProvisionError` if the user doesn't exist yet (create_user.py runs
    first). Never returns or logs the credential values.
    """
    email = email.lower()
    async with session_factory() as session:
        user = await session.scalar(select(User).where(User.email == email))
        if user is None:
            raise ProvisionError(
                f"user {email!r} not found — run "
                f"`create_user.py --email {email}` first."
            )

        existing = await session.scalar(
            select(Account).where(
                Account.user_id == user.id,
                Account.broker == "alpaca",
                Account.mode == AccountMode.paper,
            )
        )

        if dry_run:
            return {
                "user_id": user.id,
                "account_id": existing.id if existing else None,
                "account_exists": existing is not None,
                "key_fp": fingerprint(api_key),
                "dry_run": True,
            }

        store = CredentialStore(session)
        await store.set(user.id, CredentialKind.ALPACA_PAPER_KEY, api_key)
        await store.set(user.id, CredentialKind.ALPACA_PAPER_SECRET, api_secret)
        actions = ["creds"]

        if existing is None:
            account = Account(
                user_id=user.id,
                broker="alpaca",
                mode=AccountMode.paper,
                label=label,
            )
            session.add(account)
            await session.flush()
            actions.append("account")
        else:
            account = existing

        await session.commit()
        return {
            "user_id": user.id,
            "account_id": account.id,
            "account_exists": existing is not None,
            "actions": actions,
            "key_fp": fingerprint(api_key),
            "dry_run": False,
        }


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Provision a second user's dedicated paper account + creds (§5a 2-3).",
    )
    p.add_argument("--email", required=True, help="The second user's email (created first via create_user.py).")
    p.add_argument("--label", default=DEFAULT_LABEL, help=f"Account label (default: {DEFAULT_LABEL!r}).")
    p.add_argument("--key-env", default=DEFAULT_KEY_ENV, help=f"Env var for the api key (default: {DEFAULT_KEY_ENV}).")
    p.add_argument("--secret-env", default=DEFAULT_SECRET_ENV, help=f"Env var for the api secret (default: {DEFAULT_SECRET_ENV}).")
    p.add_argument("--dry-run", action="store_true", help="Report what would change without writing.")
    return p.parse_args()


async def main() -> int:
    args = _parse_args()
    api_key = os.environ.get(args.key_env, "").strip()
    api_secret = os.environ.get(args.secret_env, "").strip()
    if not api_key or not api_secret:
        missing = [n for n, v in ((args.key_env, api_key), (args.secret_env, api_secret)) if not v]
        print(f"ERROR: missing env var(s): {missing} — not set in .env.", file=sys.stderr)
        return 1

    try:
        result = await provision_paper_account(
            get_sessionmaker(),
            email=args.email,
            api_key=api_key,
            api_secret=api_secret,
            label=args.label,
            dry_run=args.dry_run,
        )
    except ProvisionError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    print(f"user_id={result['user_id']} email={args.email.lower()}")
    print(f"  paper account id={result.get('account_id')} (existed={result['account_exists']})")
    print(f"  paper key {args.key_env} -> {result['key_fp']}")
    if result["dry_run"]:
        print("  DRY RUN — nothing written.")
    else:
        print(f"  actions: {result['actions']}")
        print("  NOTE: requires the §5a step 4 lifespan fix deployed, or orders still route to the startup account.")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
