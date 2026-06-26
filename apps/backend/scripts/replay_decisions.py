"""P11 §4 — replay automated decisions from the audit log and report verdicts.

Reconstructs each recorded automated decision from its durable audit fingerprint and
recomputes the decision rule from the *recorded inputs*, asserting it reproduces (validates
the decision, not the broker outcome). Read-only. Exits non-zero on any MISMATCH, so it is
usable as a CI gate and an ops spot-check. ASCII-only output (Windows cp1252).

From the REPO ROOT (so the default DB path resolves to the mounted DB):

    apps/backend/.venv/Scripts/python.exe apps/backend/scripts/replay_decisions.py --since 2026-06-01
    apps/backend/.venv/Scripts/python.exe apps/backend/scripts/replay_decisions.py --audit-id 12345

``--since`` / ``--until`` take ISO dates/datetimes (UTC assumed if no tz). ``--audit-id``
replays a single audit_log row (any action; an unsupported action prints SKIPPED).
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from datetime import UTC, datetime
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(".env"), override=False)
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # make `app` importable

from sqlalchemy import select  # noqa: E402

from app.db.models.audit_log import AuditLog  # noqa: E402
from app.db.session import get_sessionmaker  # noqa: E402
from app.services.replay import (  # noqa: E402
    Verdict,
    replay_audit_row,
    run_replay,
)


def _parse_dt(s: str | None) -> datetime | None:
    if not s:
        return None
    dt = datetime.fromisoformat(s)
    return dt if dt.tzinfo else dt.replace(tzinfo=UTC)


async def _run(args: argparse.Namespace) -> int:
    session_factory = get_sessionmaker()

    if args.audit_id is not None:
        async with session_factory() as session:
            row = await session.get(AuditLog, args.audit_id)
            if row is None:
                print(f"audit_log id {args.audit_id} not found")
                return 2
            verdicts = [replay_audit_row(row)]
    else:
        # Persist a replay_runs row + emit metrics via the service, then re-read the
        # window for the per-row table (the service tallies; we want the detail).
        since, until = _parse_dt(args.since), _parse_dt(args.until)
        async with session_factory() as session:
            run = await run_replay(session, since=since, until=until, limit=args.limit)
        from app.services.replay import REPLAY_REGISTRY  # local import: post-run detail
        async with session_factory() as session:
            stmt = select(AuditLog).where(AuditLog.action.in_(list(REPLAY_REGISTRY.keys())))
            if since is not None:
                stmt = stmt.where(AuditLog.ts >= since)
            if until is not None:
                stmt = stmt.where(AuditLog.ts <= until)
            stmt = stmt.order_by(AuditLog.id)
            if args.limit is not None:
                stmt = stmt.limit(args.limit)
            rows = (await session.execute(stmt)).scalars().all()
        verdicts = [replay_audit_row(r) for r in rows]
        print(
            f"replay_run: checked={run.n_checked} matched={run.n_matched} "
            f"mismatched={run.n_mismatched} skipped={run.n_skipped} error={run.n_error} "
            f"({run.duration_ms}ms, algo={run.algorithm_version}, registry={run.registry_version})"
        )

    hdr = f"{'audit_id':>9s}  {'decision_type':30s}  {'verdict':9s}  note"
    print(hdr)
    print("-" * max(len(hdr), 60))
    n_mismatch = 0
    for vd in verdicts:
        if vd.verdict is Verdict.MISMATCH:
            n_mismatch += 1
        print(f"{vd.audit_log_id:>9d}  {vd.decision_type:30s}  {vd.verdict.value:9s}  {vd.note}")
    return 1 if n_mismatch else 0


def main() -> int:
    p = argparse.ArgumentParser(description="Replay automated decisions from the audit log.")
    p.add_argument("--since", help="ISO date/datetime lower bound (UTC if no tz)")
    p.add_argument("--until", help="ISO date/datetime upper bound (UTC if no tz)")
    p.add_argument("--audit-id", type=int, help="replay a single audit_log row")
    p.add_argument("--limit", type=int, help="max rows to replay")
    args = p.parse_args()
    return asyncio.run(_run(args))


if __name__ == "__main__":
    raise SystemExit(main())
