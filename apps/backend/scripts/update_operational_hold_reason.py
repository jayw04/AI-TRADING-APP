#!/usr/bin/env python3
"""Re-label an ACTIVE operational hold whose GOVERNING REASON has changed. DRY-RUN BY DEFAULT.

For the acct-4 case: the hold was placed for AWAITING_COLD_START_FIX. That defect is repaired
and the inception path is validated; what now blocks activation is the weighting-defect impact
adjudication. The reason_code is stale, but the hold itself must stay in force.

WHY NOT clear-and-place. ``HoldService.place`` refuses a different-reason active hold and tells
the caller to clear-and-place — the right rule against silent replacement, the wrong mechanism for
a RE-LABEL. Clearing would momentarily leave the strategy unheld (activation-capable paths check
only ``is_active``), emit a STRATEGY_HOLD_CLEARED event that never happened in governance terms,
and detach the hold's lineage from the original containment evidence. This script uses
``HoldService.update_reason``, which keeps the hold continuously ACTIVE.

Safety contract:
  * requires the expected CURRENT ``--expected-rev`` AND ``--expected-reason-code`` — both must
    match the live hold or the mutation is refused (exit 5) with NO state and NO audit written;
  * requires status ACTIVE (a cleared hold is re-placed, not re-labelled);
  * preserves ``effective_at`` (the hold began when it began), ``placed_at``/``placed_by``, and
    EVERY extra key on the stored blob (``legacy_marker``, evidence snapshots) verbatim;
  * increments ``_rev``; records ``previous_reason_code`` on the blob;
  * writes state + the STRATEGY_HOLD_REASON_UPDATED audit event in ONE transaction;
  * NEVER reads, starts, or resets the activation cooldown;
  * idempotent: re-running once relabelled is a no-op (exit 0, no second audit event);
  * default is a DRY RUN — pass ``--apply`` to write.

Run INSIDE the backend container on the box:
    docker compose exec -T backend python scripts/update_operational_hold_reason.py \\
        --strategy-id 11 --expected-rev <rev> \\
        --expected-reason-code AWAITING_COLD_START_FIX \\
        --new-reason-code AWAITING_WEIGHTING_DEFECT_ADJUDICATION \\
        --new-reason "weighting-defect impact study not yet adjudicated" \\
        --updated-by user:4 \\
        --evidence-ref "census final adjudication" \\
        --evidence-ref "erratum=weighting_defect_erratum_v1.0" \\
        --implementation-commit b7a205a
    # review the dry-run diff, then re-run with --apply
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.strategies.hold_service import (  # noqa: E402
    HoldReasonUpdateRefused,
    HoldService,
)
from app.strategies.operational_hold import (  # noqa: E402
    HoldStateInvalid,
    HoldStoreUnavailable,
)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--strategy-id", type=int, required=True)
    ap.add_argument("--expected-rev", type=int, required=True,
                    help="the hold's CURRENT _rev (fail-closed assertion)")
    ap.add_argument("--expected-reason-code", required=True,
                    help="the hold's CURRENT reason_code (fail-closed assertion)")
    ap.add_argument("--new-reason-code", required=True)
    ap.add_argument("--new-reason", required=True)
    ap.add_argument("--updated-by", required=True)
    ap.add_argument("--updated-at", default=None, help="ISO8601 (default: now, UTC)")
    ap.add_argument("--evidence-ref", action="append", default=[], dest="evidence_refs")
    ap.add_argument("--implementation-commit", default=None,
                    help="recorded in the audit payload as evidence of the governing change")
    ap.add_argument("--apply", action="store_true", help="write (default is a dry run)")
    args = ap.parse_args()

    import asyncio
    from datetime import UTC, datetime

    from app.db.session import get_sessionmaker

    updated_at = args.updated_at or datetime.now(UTC).isoformat()
    refs = list(args.evidence_refs)
    if args.implementation_commit:
        refs.append(f"implementation_commit={args.implementation_commit}")

    async def _run():
        svc = HoldService(get_sessionmaker())
        before = await svc.read(args.strategy_id)
        res = await svc.update_reason(
            args.strategy_id, expected_rev=args.expected_rev,
            expected_reason_code=args.expected_reason_code,
            new_reason_code=args.new_reason_code, new_reason=args.new_reason,
            updated_at=updated_at, updated_by=args.updated_by,
            evidence_refs=refs or None, apply=args.apply,
        )
        after = await svc.read(args.strategy_id)
        return before, res, after

    print(f"\n=== operational-hold reason update  (strategy_id={args.strategy_id}, "
          f"mode={'APPLY' if args.apply else 'DRY-RUN'}) ===")
    try:
        before, res, after = asyncio.run(_run())
    except HoldReasonUpdateRefused as exc:
        print(f"  ✖ REFUSED (no state, no audit): {exc}")
        return 5
    except (HoldStateInvalid, HoldStoreUnavailable) as exc:
        print(f"  ✖ REFUSED — hold unreadable (fail-closed): {exc}")
        return 5

    print(f"  before: status={before.status} reason_code={before.reason_code!r} "
          f"rev={before.rev} effective_at={before.effective_at}")
    print(f"  after:  status={after.status} reason_code={after.reason_code!r} "
          f"rev={after.rev} effective_at={after.effective_at}")

    # The three invariants that make this a relabel rather than a replacement.
    continuous = before.is_active and after.is_active
    eff_same = before.effective_at == after.effective_at
    print(f"  hold remained ACTIVE throughout: {'YES' if continuous else 'NO — ABORT'}")
    print(f"  effective_at unchanged:          {'YES' if eff_same else 'NO — ABORT'}")
    print("  cooldown:                        NOT read, NOT started, NOT reset")

    if res.action == "already_updated":
        print(f"  ✔ already at {args.new_reason_code} — no second write, no second audit event.")
    elif res.action == "updated":
        print(f"  ✔ UPDATED rev {res.previous_rev} → {res.new_rev} + "
              f"STRATEGY_HOLD_REASON_UPDATED audit id {res.audit_id}.")
    else:  # would_update
        print(f"  WOULD UPDATE rev {res.previous_rev} → {res.new_rev} + one "
              f"STRATEGY_HOLD_REASON_UPDATED audit event. Planned blob:")
        scrubbed = {k: v for k, v in res.planned_blob.items() if k != "legacy_marker"}
        print("    " + json.dumps(scrubbed, indent=2, default=str).replace("\n", "\n    "))
        if "legacy_marker" in res.planned_blob:
            print("    legacy_marker: PRESERVED verbatim (elided from this echo)")
        print("\n  (dry run — no state/audit written. Re-run with --apply.)")

    if res.action != "would_update" and not (continuous and eff_same):
        return 6  # should be impossible — update_reason enforces both
    print("\n  NOTE: activation remains BLOCKED. This relabels why the book is held; "
          "it does not clear the hold.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
