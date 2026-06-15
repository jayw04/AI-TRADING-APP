"""Re-provision the encrypted credential store from .env after a master-key reset.

When WORKBENCH_MASTER_KEY is regenerated, every existing `user_credentials` row
(encrypted under the old key) becomes undecryptable. The backend reads broker
creds from the store (P5 §4, app/brokers/alpaca/credentials.py), so it cannot
connect until the store is re-populated under the NEW key.

This writes the creds available in .env back into the store (CredentialStore.set
upserts, overwriting the stale rows) for the dev user, under the current
WORKBENCH_MASTER_KEY. TOTP/password are handled separately by create_user.py.

Run from the REPO ROOT (so the default db_url ./data/workbench.sqlite resolves to
the Docker-mounted DB), host venv or container:

    apps/backend/.venv/Scripts/python.exe apps/backend/scripts/rebootstrap_credentials.py

Values are read from .env and never printed; only the credential KINDS set.
"""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

# Load .env into os.environ FIRST so crypto.py sees WORKBENCH_MASTER_KEY and we
# can read the source cred values. Root .env (we run from repo root).
load_dotenv(Path(".env"), override=False)

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # make `app` importable

from sqlalchemy import select  # noqa: E402

from app.config import get_settings  # noqa: E402
from app.db.models import User  # noqa: E402
from app.db.session import get_sessionmaker  # noqa: E402
from app.security.credential_store import CredentialKind, CredentialStore  # noqa: E402

# .env var name -> credential kind to store it under.
_MAP = [
    ("ALPACA_PAPER_API_KEY", CredentialKind.ALPACA_PAPER_KEY),
    ("ALPACA_PAPER_API_SECRET", CredentialKind.ALPACA_PAPER_SECRET),
    ("ALPACA_LIVE_API_KEY", CredentialKind.ALPACA_LIVE_KEY),
    ("ALPACA_LIVE_API_SECRET", CredentialKind.ALPACA_LIVE_SECRET),
    ("ANTHROPIC_API_KEY", CredentialKind.ANTHROPIC_API_KEY),
    ("WORKBENCH_MCP_KEY", CredentialKind.WORKBENCH_MCP_KEY),
]


async def main() -> int:
    settings = get_settings()
    email = settings.dev_user_email.lower()
    Session = get_sessionmaker()
    async with Session() as session:
        user = await session.scalar(select(User).where(User.email == email))
        if user is None:
            print(f"ERROR: user {email} not found (run seed_dev_data.py first)", file=sys.stderr)
            return 1
        store = CredentialStore(session)
        set_kinds, skipped = [], []
        for env_name, kind in _MAP:
            val = os.environ.get(env_name, "").strip()
            if val:
                await store.set(user.id, kind, val)
                set_kinds.append(kind.value)
            else:
                skipped.append(env_name)
        await session.commit()
    print(f"user_id={user.id} ({email})")
    print(f"set under new master key: {set_kinds}")
    print(f"skipped (not in .env): {skipped}")
    print("NOTE: TOTP + password are handled by create_user.py --rotate-totp")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
