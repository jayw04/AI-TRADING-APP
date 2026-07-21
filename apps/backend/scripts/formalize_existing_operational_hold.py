#!/usr/bin/env python3
"""Formalize an ALREADY-ACTIVE operational hold with a retrospective audit event.

Emits EXACTLY ONE ``STRATEGY_HOLD_PLACED`` audit event (``source=
RETROSPECTIVE_FORMALIZATION``) for a hold that became effective before the
``STRATEGY_HOLD_PLACED`` action existed (the acct-4 cold-start case). It is NOT a
placement and does NOT create a second logical hold: it reads and validates the
existing hold, writes only the audit event through ``AuditLogger``, and never mutates
the hold blob (or any ``strategy_state``). DRY-RUN BY DEFAULT.

Why a dedicated command (not ``HoldService.place``): ``place`` on an existing identical
active hold is an idempotent no-op and writes no audit at all. Directly inserting an
audit row would bypass the sanctioned service boundary and the hash chain. Placing
another hold would violate "no second logical hold". This command is the sanctioned
path.

Safety contract:
  * requires the strategy id AND the expected active hold ``--expected-rev``,
    ``--expected-reason-code``, ``--expected-effective-at``;
  * refuses (exit 5, no write) if the hold is absent / cleared / malformed / unreadable,
    or if the live ``(rev, reason_code, effective_at)`` differ from the expectation;
  * deduplicates on ``(strategy_id, hold_rev, RETROSPECTIVE_FORMALIZATION)`` — a second
    run is an idempotent no-op (exit 0, no second event);
  * default is a DRY RUN — pass ``--apply`` to write the event;
  * proves the ``operational_hold`` blob is BYTE-IDENTICAL before and after, and prints
    the resulting audit id.

Run INSIDE the backend container (uses the app DB session):
    docker compose exec -T backend python scripts/formalize_existing_operational_hold.py \
        --strategy-id 11 --expected-rev <REV> \
        --expected-reason-code AWAITING_COLD_START_FIX \
        --expected-effective-at 2026-07-20T22:48:22Z \
        --evidence-ref "snapshot_sha256=8fa766f3..." \
        --evidence-ref "audit=STRATEGY_UNREGISTERED#5733" \
        --evidence-ref "run=605" \
        --evidence-ref "plan=momentum_daily_coldstart_repair_plan_v1.0" \
        --approval-ref "<adjudication ref>"
    # then re-run with --apply
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select  # noqa: E402
from sqlalchemy.ext.asyncio import AsyncSession  # noqa: E402

from app.db.models.strategy_state import StrategyState  # noqa: E402
from app.strategies.hold_service import (  # noqa: E402
    RetroFormalizationRefused,
    formalize_retrospective_hold_placed,
)
from app.strategies.operational_hold import (  # noqa: E402
    K_OPERATIONAL_HOLD,
    HoldStateInvalid,
    HoldStoreUnavailable,
)


def _canon(blob: dict | None) -> str:
    return json.dumps(blob, sort_keys=True, default=str)


async def _read_hold_raw(session: AsyncSession, strategy_id: int) -> dict | None:
    return (
        await session.execute(
            select(StrategyState.value).where(
                StrategyState.strategy_id == strategy_id,
                StrategyState.key == K_OPERATIONAL_HOLD,
            )
        )
    ).scalars().first()


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--strategy-id", type=int, required=True)
    ap.add_argument("--expected-rev", type=int, required=True,
                    help="the active hold revision the operator asserts (fail-closed check)")
    ap.add_argument("--expected-reason-code", required=True)
    ap.add_argument("--expected-effective-at", required=True,
                    help="ISO8601, must equal the live hold's effective_at")
    ap.add_argument("--evidence-ref", action="append", default=[], dest="evidence_refs")
    ap.add_argument("--approval-ref", default=None)
    ap.add_argument("--apply", action="store_true", help="write the event (default is a dry run)")
    args = ap.parse_args()

    import asyncio

    from app.db.session import get_sessionmaker

    async def _run():
        sm = get_sessionmaker()
        async with sm() as s:
            before = await _read_hold_raw(s, args.strategy_id)
        async with sm() as s, s.begin():
            res = await formalize_retrospective_hold_placed(
                s, strategy_id=args.strategy_id, expected_rev=args.expected_rev,
                expected_reason_code=args.expected_reason_code,
                expected_effective_at=args.expected_effective_at,
                evidence_refs=args.evidence_refs or None, approval_ref=args.approval_ref,
                apply=args.apply,
            )
        async with sm() as s:
            after = await _read_hold_raw(s, args.strategy_id)
        return res, before, after

    print(f"\n=== retrospective hold formalization  (strategy_id={args.strategy_id}, "
          f"mode={'APPLY' if args.apply else 'DRY-RUN'}) ===")
    try:
        res, before, after = asyncio.run(_run())
    except RetroFormalizationRefused as exc:
        print(f"  ✖ REFUSED (no audit written): {exc}")
        return 5
    except (HoldStateInvalid, HoldStoreUnavailable) as exc:
        print(f"  ✖ REFUSED — hold unreadable/malformed (fail-closed): {exc}")
        return 5

    identical = _canon(before) == _canon(after)
    print(f"  hold blob BYTE-IDENTICAL before/after: {'YES' if identical else 'NO — ABORT'}")
    print(f"  operational_hold (unchanged): {_canon(after)}")
    if res.action == "already_formalized":
        print(f"  ✔ already formalized — audit id {res.audit_id} exists for rev {res.hold_rev}; "
              "no second event written.")
    elif res.action == "wrote":
        print(f"  ✔ WROTE retrospective STRATEGY_HOLD_PLACED — audit id {res.audit_id}, "
              f"hold rev {res.hold_rev}.")
    else:  # would_write
        print(f"  WOULD WRITE retrospective STRATEGY_HOLD_PLACED for hold rev {res.hold_rev}:")
    print("    planned payload: " + json.dumps(res.planned_payload, indent=2, default=str)
          .replace("\n", "\n    "))
    if res.action == "would_write":
        print("\n  (dry run — no audit written. Re-run with --apply to record it.)")
    if not identical:
        return 6  # should be impossible (function never touches the blob) — hard fail
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
