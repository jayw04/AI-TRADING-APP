"""Set one user's market grants. Writes only ``users.market_access``.

From apps/backend, against the database in settings (the laptop store unless
WORKBENCH_DB_URL says otherwise). This does not connect to a broker.

    python scripts/set_market_access.py --email trader@example.com --markets cn
    python scripts/set_market_access.py --email trader@example.com --markets us,cn

Do not point it at the live AWS database during this development phase.
"""

from __future__ import annotations

import argparse
import asyncio
import sys

from sqlalchemy import select

from app.auth.market_access import canonical_market_access
from app.db.models.user import User
from app.db.session import get_sessionmaker


async def _set(email: str, markets: str) -> int:
    stored = canonical_market_access(markets)
    async with get_sessionmaker()() as session:
        user = (await session.execute(select(User).where(User.email == email))).scalar_one_or_none()
        if user is None:
            print("no user with that email", file=sys.stderr)
            return 1
        user.market_access = stored
        await session.commit()
        print(f"user {user.id} market_access={stored}")
        return 0


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--email", required=True)
    ap.add_argument("--markets", required=True, help="us, cn, or us,cn")
    args = ap.parse_args()
    try:
        code = asyncio.run(_set(args.email, args.markets))
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        code = 2
    raise SystemExit(code)


if __name__ == "__main__":
    main()
