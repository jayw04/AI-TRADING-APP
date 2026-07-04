#!/usr/bin/env python3
"""Review the equity-beta-cap governor's report-only DRY-RUN from a live rebalance (read-only).

PORT-001 lever #2 ships ``enforce_beta_cap=False`` + ``beta_cap_report_only=True``: on every weekly
rebalance the governor computes the book's look-through equity-beta risk contribution and the
would-be haircut, and LOGS it (a ``signals`` row: ``symbol=PORTFOLIO``, ``payload.reason="beta_cap"``)
without touching the book. This script reads that logged report back — the ground truth from the
actual rebalance, NOT a re-reconstruction — and tells the owner whether flipping
``enforce_beta_cap=True`` would be a no-op or a material de-risk.

Run INSIDE the backend container (uses the app DB session):
    docker compose exec -T backend python scripts/review_beta_cap_dryrun.py
    docker compose exec -T backend python scripts/review_beta_cap_dryrun.py --strategy-id 9 --since-days 3

Exit codes: 0 = a dry-run was found and interpreted; 2 = no dry-run logged in the window
(the rebalance may not have run yet — check the schedule / engine logs).
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select  # noqa: E402

from app.db.models.signal import Signal  # noqa: E402
from app.db.session import get_sessionmaker  # noqa: E402

_BETA_CAP_REASONS = {"beta_cap", "beta_cap_skip", "beta_cap_failopen"}


async def _fetch(strategy_id: int, since: datetime) -> list[Signal]:
    """Most-recent-first governor signals for the strategy since ``since``."""
    sm = get_sessionmaker()
    async with sm() as session:
        rows = (
            await session.execute(
                select(Signal)
                .where(Signal.strategy_id == strategy_id, Signal.received_at >= since)
                .order_by(Signal.received_at.desc())
            )
        ).scalars().all()
    return [s for s in rows if (s.payload_json or {}).get("reason") in _BETA_CAP_REASONS]


def _interpret(report: dict) -> tuple[str, str]:
    """Return ``(headline, recommendation)`` for a ``reason="beta_cap"`` report."""
    cap = report.get("cap", 0.80)
    rc0 = report.get("equity_beta_rc_before")
    if report.get("applied"):
        scale = report.get("scale_equity_beta")
        gb, ga = report.get("gross_before"), report.get("gross_after")
        rc1 = report.get("equity_beta_rc_after")
        freed = report.get("cash_freed")
        headline = (
            f"WOULD DE-RISK: equity-beta RC {rc0:.3f} > cap {cap} -> scale equity x{scale:.3f}, "
            f"gross {gb:.3f}->{ga:.3f} (cash freed {freed:.3f}), RC {rc0:.3f}->{rc1:.3f}"
        )
        rec = (
            "MATERIAL de-risk. Enforcing would trim the equity-beta names by "
            f"{(1 - scale) * 100:.0f}% and raise ~{freed:.1%} cash on the next rebalance. "
            "Owner decision: flip enforce_beta_cap=True only if this haircut magnitude is acceptable."
        )
        return headline, rec
    note = report.get("note", "within budget")
    headline = (
        f"WITHIN BUDGET: equity-beta RC {rc0:.3f} <= cap {cap} ({note}) — no haircut"
        if rc0 is not None else f"governor skipped: {note}"
    )
    rec = (
        "Enforcing is a NO-OP right now (book already within the equity-beta budget). "
        "Safe to flip enforce_beta_cap=True — the governor only ever acts if a future "
        "rebalance breaches the cap."
    )
    return headline, rec


def _print(sig: Signal) -> None:
    report = sig.payload_json or {}
    reason = report.get("reason")
    ts = sig.received_at.isoformat()
    print(f"\n=== beta-cap dry-run @ {ts}  (signal id={sig.id}, strategy_id={sig.strategy_id}) ===")
    print(f"  reason={reason}  enforced={report.get('enforced')}")
    if reason == "beta_cap":
        head, rec = _interpret(report)
        print(f"  {head}")
        print(f"  n_priced={report.get('n_priced')} n_equity={report.get('n_equity')}")
        print(f"\n  >> RECOMMENDATION: {rec}")
    elif reason == "beta_cap_skip":
        print(f"  SKIPPED: {report.get('note')} — cannot assess; do NOT flip until a clean dry-run runs.")
    elif reason == "beta_cap_failopen":
        print(f"  FAIL-OPEN (book left unchanged): {report.get('error')} — investigate before flipping.")
    print("\n  raw report:")
    print("  " + json.dumps(report, indent=2, default=str).replace("\n", "\n  "))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--strategy-id", type=int, default=9, help="combined-book strategy id (default 9)")
    ap.add_argument("--since-days", type=int, default=4,
                    help="look back this many days for a dry-run (default 4 — covers a Mon run reviewed by Fri)")
    ap.add_argument("--all", action="store_true", help="print every dry-run in the window, not just the latest")
    args = ap.parse_args()

    import asyncio
    since = datetime.now(UTC) - timedelta(days=args.since_days)
    sigs = asyncio.run(_fetch(args.strategy_id, since))

    if not sigs:
        print(f"No beta-cap dry-run logged for strategy_id={args.strategy_id} in the last "
              f"{args.since_days}d.\nThe rebalance may not have run yet (schedule '40 14 * * mon' = "
              "Mon 14:40 UTC) — check the engine logs, then re-run.")
        return 2

    to_show = sigs if args.all else sigs[:1]
    for s in to_show:
        _print(s)
    if not args.all and len(sigs) > 1:
        print(f"\n({len(sigs) - 1} older dry-run(s) in the window; pass --all to see them.)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
