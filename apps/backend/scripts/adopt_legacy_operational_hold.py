#!/usr/bin/env python3
"""Adopt a LEGACY (pre-schema-v1) operational-hold marker into a schema-v1 ACTIVE hold.

For a hold that became effective before the operational-hold schema existed (the acct-4
cold-start case), the persisted ``operational_hold`` marker is NOT parseable by the new
code (``schema_version`` absent → ``read_hold`` raises ``HoldStateInvalid``). That means
enforcement blocks activation fail-closed (good), but the marker can be neither
``formalize``-d nor ``clear``-ed — so the strategy can never be governed-activated until
the marker is adopted into schema-v1.

This one governed migration reads the legacy marker, validates it against the operator's
assertion, writes a canonical schema-v1 **ACTIVE** hold (rev 1, ``effective_at`` = the
legacy ``paused_at``, ``source=RETROSPECTIVE_FORMALIZATION``) that **preserves the entire
original marker** under a ``legacy_marker`` key, and emits exactly one retrospective
``STRATEGY_HOLD_PLACED``. The hold stays ACTIVE — activation remains blocked; clearing is
a separate, later-adjudicated step. DRY-RUN BY DEFAULT.

Safety contract:
  * requires the strategy id + the expected legacy ``--reason-code`` and ``--paused-at``;
  * refuses (exit 5, no writes) if the marker is absent, already schema-v1 (non-adopted),
    or its legacy (status, reason_code, paused_at) differ from the assertion;
  * idempotent: a second run on the adopted marker is a no-op (exit 0, no second event);
  * default is a DRY RUN — pass ``--apply`` to write;
  * after apply, the marker is schema-v1 ACTIVE and enforcement blocks via the CLEAN path
    (``StrategyOnHold``), and ``HoldService.clear`` becomes possible.

Run INSIDE the backend container:
    docker compose exec -T backend python scripts/adopt_legacy_operational_hold.py \
        --strategy-id 11 --reason-code AWAITING_COLD_START_FIX \
        --paused-at 2026-07-20T22:48:22Z --placed-by user:4 \
        --evidence-ref "snapshot_sha256=8fa766f3..." --evidence-ref "audit=STRATEGY_UNREGISTERED#5733" \
        --evidence-ref "run=605" --evidence-ref "plan=momentum_daily_coldstart_repair_plan_v1.0" \
        --approval-ref "<adjudication ref>"
    # then re-run with --apply
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.strategies.hold_service import (  # noqa: E402
    LegacyHoldAdoptionRefused,
    adopt_legacy_operational_hold,
)
from app.strategies.operational_hold import HoldStoreUnavailable  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--strategy-id", type=int, required=True)
    ap.add_argument("--reason-code", required=True, help="expected legacy reason_code")
    ap.add_argument("--paused-at", required=True, help="expected legacy paused_at (ISO8601)")
    ap.add_argument("--legacy-status", default="PAUSED", help="expected legacy status (default PAUSED)")
    ap.add_argument("--placed-by", required=True)
    ap.add_argument("--evidence-ref", action="append", default=[], dest="evidence_refs")
    ap.add_argument("--approval-ref", default=None)
    ap.add_argument("--apply", action="store_true", help="write (default is a dry run)")
    args = ap.parse_args()

    import asyncio

    from app.db.session import get_sessionmaker

    async def _run():
        sm = get_sessionmaker()
        async with sm() as s, s.begin():
            return await adopt_legacy_operational_hold(
                s, strategy_id=args.strategy_id, expected_reason_code=args.reason_code,
                expected_paused_at=args.paused_at, expected_legacy_status=args.legacy_status,
                placed_by=args.placed_by, evidence_refs=args.evidence_refs or None,
                approval_ref=args.approval_ref, apply=args.apply,
            )

    print(f"\n=== legacy operational-hold adoption  (strategy_id={args.strategy_id}, "
          f"mode={'APPLY' if args.apply else 'DRY-RUN'}) ===")
    try:
        res = asyncio.run(_run())
    except LegacyHoldAdoptionRefused as exc:
        print(f"  ✖ REFUSED (no writes): {exc}")
        return 5
    except HoldStoreUnavailable as exc:
        print(f"  ✖ REFUSED — store unavailable (fail-closed): {exc}")
        return 5

    # Prove the legacy content is preserved verbatim inside the new blob.
    preserved = res.planned_blob.get("legacy_marker") == res.legacy_marker
    print(f"  legacy marker PRESERVED verbatim in schema-v1 blob: {'YES' if preserved else 'NO — ABORT'}")
    if res.action == "already_adopted":
        print("  ✔ already adopted — marker is schema-v1 with preserved legacy_marker; no second write.")
    elif res.action == "adopted":
        print(f"  ✔ ADOPTED — wrote schema-v1 ACTIVE hold (rev 1) + retrospective "
              f"STRATEGY_HOLD_PLACED audit id {res.audit_id}.")
    else:  # would_adopt
        print("  WOULD ADOPT — write this schema-v1 ACTIVE blob (rev 1) + one retrospective "
              "STRATEGY_HOLD_PLACED:")
    scrubbed = {k: v for k, v in res.planned_blob.items() if k != "legacy_marker"}
    print("    schema-v1 blob (legacy_marker elided): "
          + json.dumps(scrubbed, indent=2, default=str).replace("\n", "\n    "))
    if res.action == "would_adopt":
        print("\n  (dry run — no state/audit written. Re-run with --apply to adopt.)")
    if not preserved:
        return 6  # should be impossible
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
