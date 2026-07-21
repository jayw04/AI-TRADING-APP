#!/usr/bin/env python3
"""Initialize the deployment lifecycle for ONE strategy (P7 §7-A/§7-B, ADR 0044).

One-shot, idempotent, DRY-RUN BY DEFAULT. Writes ONLY the authoritative
``strategy_state['deployment']`` blob (``NEVER_DEPLOYED`` / ``has_ever_deployed=false``
/ ``first_deployed_at=null`` / ``active_seed_attempt=null``, rev 0). It READS
``strategy_state['operational_hold']`` solely for verification (to echo it) and NEVER
mutates it — lifecycle initialization and the retrospective hold formalization are
DELIBERATELY separate commands with separate verification (ADR 0044). The hold marker
is echoed read-only so the operator can confirm it is untouched before and after.

Safety contract:
  * refuses (exit 3, no write) if a deployment blob already exists — one-shot, never
    overwrites an existing lifecycle;
  * refuses (exit 4) if the strategy row does not exist;
  * default is a DRY RUN — pass ``--apply`` to write;
  * on ``--apply`` the write is a single transaction (commit or nothing).

If initialization fails for any reason, no state is mutated and the existing hold
(hence activation blocking) is untouched.

Run INSIDE the backend container (uses the app DB session):
    docker compose exec -T backend python scripts/init_deployment_lifecycle.py --strategy-id 11
    docker compose exec -T backend python scripts/init_deployment_lifecycle.py --strategy-id 11 --apply
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select  # noqa: E402
from sqlalchemy.ext.asyncio import AsyncSession  # noqa: E402

from app.db.models.strategy import Strategy as StrategyRow  # noqa: E402
from app.db.models.strategy_state import StrategyState  # noqa: E402
from app.strategies.deployment_state import initial_blob  # noqa: E402
from app.strategies.operational_hold import K_OPERATIONAL_HOLD  # noqa: E402

_K_DEPLOYMENT = "deployment"  # must match momentum_daily.py _K_DEPLOYMENT


@dataclass
class InitResult:
    strategy_id: int
    action: str  # would_write | wrote | already_initialized | strategy_not_found
    planned_blob: dict | None
    existing_deployment: dict | None
    operational_hold_raw: dict | None  # READ-ONLY echo; never mutated here

    @property
    def exit_code(self) -> int:
        return {"would_write": 0, "wrote": 0,
                "already_initialized": 3, "strategy_not_found": 4}[self.action]


async def _read_state(session: AsyncSession, strategy_id: int, key: str) -> dict | None:
    return (
        await session.execute(
            select(StrategyState.value).where(
                StrategyState.strategy_id == strategy_id, StrategyState.key == key
            )
        )
    ).scalars().first()


async def init_deployment_lifecycle(
    session: AsyncSession, strategy_id: int, *, apply: bool
) -> InitResult:
    """Plan (and, if ``apply``, perform) the one-shot lifecycle initialization within
    ``session``. Does NOT commit — the caller owns the transaction so state + nothing-
    else commit together. Writes only ``deployment``; reads ``operational_hold`` for
    verification only and never mutates it."""
    if await session.get(StrategyRow, strategy_id) is None:
        return InitResult(strategy_id, "strategy_not_found", None, None, None)

    hold_raw = await _read_state(session, strategy_id, K_OPERATIONAL_HOLD)  # read-only echo
    existing = await _read_state(session, strategy_id, _K_DEPLOYMENT)
    if existing is not None:
        # One-shot: never overwrite an existing lifecycle (idempotent no-op).
        return InitResult(strategy_id, "already_initialized", None, existing, hold_raw)

    planned = initial_blob().to_dict()
    if apply:
        session.add(StrategyState(strategy_id=strategy_id, key=_K_DEPLOYMENT,
                                  value=planned, updated_at=datetime.now(UTC)))
        return InitResult(strategy_id, "wrote", planned, None, hold_raw)
    return InitResult(strategy_id, "would_write", planned, None, hold_raw)


def _print(res: InitResult, *, apply: bool) -> None:
    print(f"\n=== deployment-lifecycle init  (strategy_id={res.strategy_id}, "
          f"mode={'APPLY' if apply else 'DRY-RUN'}) ===")
    print(f"  operational_hold (read-only, NOT modified by this script): "
          f"{json.dumps(res.operational_hold_raw, default=str)}")
    if res.action == "strategy_not_found":
        print("  ✖ strategy row not found — nothing initialized.")
        return
    if res.action == "already_initialized":
        print("  ✖ deployment blob ALREADY EXISTS — one-shot init refuses to overwrite:")
        print("    " + json.dumps(res.existing_deployment, indent=2, default=str).replace("\n", "\n    "))
        return
    verb = "WROTE" if res.action == "wrote" else "WOULD WRITE"
    print(f"  {verb} strategy_state['{_K_DEPLOYMENT}'] =")
    print("    " + json.dumps(res.planned_blob, indent=2, default=str).replace("\n", "\n    "))
    if res.action == "would_write":
        print("\n  (dry run — no state changed. Re-run with --apply to write.)")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--strategy-id", type=int, required=True,
                    help="target strategy id (REQUIRED — no default, to avoid a wrong target)")
    ap.add_argument("--apply", action="store_true",
                    help="perform the write (default is a dry run)")
    args = ap.parse_args()

    import asyncio

    from app.db.session import get_sessionmaker

    async def _run() -> InitResult:
        sm = get_sessionmaker()
        async with sm() as session, session.begin():
            return await init_deployment_lifecycle(session, args.strategy_id, apply=args.apply)

    res = asyncio.run(_run())
    _print(res, apply=args.apply)
    return res.exit_code


if __name__ == "__main__":
    raise SystemExit(main())
