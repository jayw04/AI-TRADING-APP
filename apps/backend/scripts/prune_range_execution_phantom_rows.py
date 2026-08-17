"""Delete frozen ``range_execution_records`` rows for symbols the book did not hold that day.

Before the per-day-membership fix, ``capture_window`` used a window-wide symbol union: every name that
published levels anywhere in the queried window got a row on *every* completed day of it. Because the
Range Trader rotates its 5th slot, querying a window that spans a rotation retroactively minted
blank-level rows for each rotated name on the days it was never held — and froze them.

This removes exactly those rows. It refuses to touch any row that carries a buy or sell level, so it
can only ever delete rows that render as blanks. Membership comes from the same helper the fixed
capture uses, so the two agree by construction.

    docker compose exec -T backend python scripts/prune_range_execution_phantom_rows.py \
        --from 2026-07-07 --to 2026-08-07            # preview (default)
    docker compose exec -T backend python scripts/prune_range_execution_phantom_rows.py \
        --from 2026-07-07 --to 2026-08-07 --execute  # delete
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from datetime import date
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from sqlalchemy import select  # noqa: E402 — after the sys.path bootstrap above

from app.db.models.range_execution_record import RangeExecutionRecord  # noqa: E402
from app.db.models.strategy import Strategy  # noqa: E402
from app.db.session import get_sessionmaker  # noqa: E402
from app.services.range_execution import (  # noqa: E402
    _levels_by_day,
    _membership_before,
    _membership_by_day,
)


async def _run(d_from: date, d_to: date, *, execute: bool) -> int:
    Session = get_sessionmaker()
    async with Session() as session:
        strat_id = await session.scalar(
            select(Strategy.id)
            .where(Strategy.name.like("Range Trader%"))
            .order_by(Strategy.id)
            .limit(1)
        )
        if strat_id is None:
            print("No Range Trader strategy — nothing to do.")
            return 0

        levels = await _levels_by_day(session, strat_id, d_from, d_to)
        members = await _membership_by_day(session, strat_id, levels, d_from, d_to)

        # A day's membership is only trustworthy when it rests on EVIDENCE — signals that day, or
        # carried forward from an earlier day that had them. With no signals in the window and none
        # in the lookback, ``_membership_by_day`` falls back to the CURRENT roster, which for any
        # pre-history day names the wrong 5th slot. Capture may use that guess; deletion must not.
        # (Proven: over 2026-06-24..07-02, which pre-dates the range_levels emit, the fallback would
        # have condemned 7 real TSLA rows because today's roster holds NFLX instead.)
        seeded = bool(await _membership_before(session, strat_id, d_from))
        published_days = sorted({day_iso for (day_iso, _tk) in levels})

        def evidence_based(d: date) -> bool:
            return seeded or any(pd <= d.isoformat() for pd in published_days)

        rows = (
            (
                await session.execute(
                    select(RangeExecutionRecord)
                    .where(
                        RangeExecutionRecord.et_date >= d_from,
                        RangeExecutionRecord.et_date <= d_to,
                    )
                    .order_by(RangeExecutionRecord.et_date, RangeExecutionRecord.symbol)
                )
            )
            .scalars()
            .all()
        )

        doomed = []
        skipped_no_evidence: set[date] = set()
        for r in rows:
            if r.symbol in members.get(r.et_date, set()):
                continue  # in the book that day — keep, blank levels or not
            if not evidence_based(r.et_date):
                skipped_no_evidence.add(r.et_date)
                continue
            if r.avg_buy_price is not None or r.avg_sell_price is not None:
                print(
                    f"  KEEP {r.et_date} {r.symbol}: not in that day's book but HAS levels — review"
                )
                continue
            doomed.append(r)

        for d in sorted(skipped_no_evidence):
            print(
                f"  SKIP {d}: no signal evidence for that day's book — refusing to judge membership"
            )

        for r in doomed:
            print(f"  drop {r.et_date} {r.symbol} (low={r.daily_low} high={r.daily_high})")
        if execute and doomed:
            for r in doomed:
                await session.delete(r)
            await session.commit()

    print(
        f"{'Deleted' if execute else 'Would delete'} {len(doomed)} of {len(rows)} row(s) "
        f"in {d_from}..{d_to}"
    )
    return len(doomed)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--from", dest="d_from", required=True, type=date.fromisoformat)
    ap.add_argument("--to", dest="d_to", required=True, type=date.fromisoformat)
    ap.add_argument(
        "--execute", action="store_true", help="actually delete (default: preview only)"
    )
    args = ap.parse_args()
    asyncio.run(_run(args.d_from, args.d_to, execute=args.execute))


if __name__ == "__main__":
    main()
