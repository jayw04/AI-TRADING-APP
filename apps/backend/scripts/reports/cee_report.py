"""Continuous Evidence Engine report — activates the 3rd pillar.

The CEE module (`app/services/continuous_evidence.py`, Phases 1–2) was built + tested but had **no
consumer** — this is it. For every live paper book it runs the Research-Envelope check + the
Evidence Clock and prints, per book: the evidence maturity/debt, the overall investment state
(Consistent / Watch / Investigate / Insufficient), each metric vs its research band, and the
separate operational-drift track. Read-only (equity_snapshots), off the order path.

Run inside the backend container:
    python scripts/reports/cee_report.py [--window-days 400] [--json]
Exit code 2 if any book has escalated to INVESTIGATE (so a scheduler/alert can trip on it).
"""

from __future__ import annotations

import argparse
import asyncio
import json

from sqlalchemy import select

from app.db.enums import StrategyStatus
from app.db.models.account import Account, AccountMode
from app.db.models.strategy import Strategy
from app.db.session import get_sessionmaker
from app.services.continuous_evidence import INVESTIGATE, compute


async def _live_books(session) -> list[tuple[int, str]]:
    """(account_id, strategy_label) for every PAPER strategy, via the user's paper account."""
    strategies = (
        await session.execute(select(Strategy).where(Strategy.status == StrategyStatus.PAPER))
    ).scalars().all()
    books: list[tuple[int, str]] = []
    for s in strategies:
        account = (
            await session.execute(
                select(Account).where(
                    Account.user_id == s.user_id, Account.mode == AccountMode.paper
                )
            )
        ).scalars().first()
        if account is not None:
            books.append((account.id, s.name))
    return books


async def _run(window_days: int, as_json: bool) -> int:
    async with get_sessionmaker()() as session:
        books = await _live_books(session)
        results = await compute(session, books, window_days=window_days)

    if as_json:
        print(json.dumps([{
            "book": b.book, "account_id": b.account_id, "days_live": b.days_live,
            "maturity": b.maturity, "evidence_debt": b.evidence_debt, "state": b.state,
            "envelope_source": b.envelope_source,
            "metrics": [{"metric": m.metric, "observed": m.observed,
                         "band": [m.expected_low, m.expected_high], "state": m.state}
                        for m in b.metrics],
            "operational_state": b.operational.state,
        } for b in results], indent=2, default=str))
    else:
        print("=== Continuous Evidence Engine — live-book status ===")
        if not results:
            print("  (no live PAPER books found)")
        for b in results:
            print(f"\n▸ {b.book}  (acct {b.account_id})  [{b.state}]")
            print(f"    clock: {b.days_live} trading days · maturity={b.maturity} · "
                  f"debt={b.evidence_debt} · review every {b.review_cadence_days}d")
            print(f"    envelope: {b.envelope_source or '— none matched (INSUFFICIENT)'}")
            for m in b.metrics:
                obs = "—" if m.observed is None else f"{m.observed:+.3f}"
                print(f"      {m.metric:<13} obs={obs:<8} band=[{m.expected_low:+.2f},"
                      f"{m.expected_high:+.2f}]  → {m.state}")
            print(f"    operational: {b.operational.state}")

    investigate = [b.book for b in results if b.state == INVESTIGATE]
    if investigate:
        print(f"\n⚠ INVESTIGATE: {', '.join(investigate)} — a live book separated from its "
              f"research envelope (probabilistic drift). Review its evidence package.")
        return 2
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="Continuous Evidence Engine live-book report.")
    ap.add_argument("--window-days", type=int, default=400)
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()
    return asyncio.run(_run(args.window_days, args.json))


if __name__ == "__main__":
    raise SystemExit(main())
