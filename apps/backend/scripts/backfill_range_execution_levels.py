"""Backfill missing buy/sell levels on frozen range_execution_records.

Use when ``range_levels`` signals were never logged (stack down) but daily low/high rows exist.
Reconstructs the opening-range levels the strategy would have set — ``buy`` = OR low, ``sell`` = OR
high — from 1-minute RTH bars, using the SHARED formula in ``app.services.range_opening_levels``.

⚠ The window length is HISTORICAL, not current. ``opening_range_minutes`` was 30 until the owner
changed it to 15 mid-session on 2026-07-08, so reconstructing a June date with today's parameter
silently produces a too-narrow range that passes every sanity check. This script therefore resolves
the value **in force at 09:30 ET on the target date** from the ``STRATEGY_UPDATED`` audit trail, and
only falls back to the current parameter when the trail says nothing. Override with ``--or-minutes``.

Validated 2026-08-09 against days whose real signals survive (2026-07-28, 2026-08-07 at 15 min):
the reconstruction reproduced all 10 published buy/sell pairs exactly.

    docker compose exec -T backend python scripts/backfill_range_execution_levels.py --date 2026-07-27
    docker compose exec -T backend python scripts/backfill_range_execution_levels.py --date 2026-07-27 --execute
    # --force also OVERWRITES rows that already carry levels (use to correct a bad backfill)
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from sqlalchemy import select  # noqa: E402 — after the sys.path bootstrap above
from sqlalchemy.ext.asyncio import AsyncSession  # noqa: E402

from app.db.models.audit_log import AuditLog  # noqa: E402
from app.db.models.range_execution_record import RangeExecutionRecord  # noqa: E402
from app.db.models.strategy import Strategy  # noqa: E402
from app.db.session import get_sessionmaker  # noqa: E402
from app.market_data.bar_cache import _alpaca_fetch_bars  # noqa: E402
from app.services.range_opening_levels import (  # noqa: E402
    ET,
    SESSION_OPEN,
    filter_bars_to_window,
    levels_from_or_bars,
    opening_range_window,
    params_or_defaults,
)


async def _or_minutes_in_force(
    session: AsyncSession, strat_id: int, day: date, *, current: int
) -> tuple[int, str]:
    """The ``opening_range_minutes`` governing ``day``'s opening range, plus how it was decided.

    Reads the ``STRATEGY_UPDATED`` audit trail for ``{"opening_range_minutes": {"from", "to"}}``
    entries and takes the last change strictly before 09:30 ET on ``day``. Before the first
    recorded change, the correct value is that change's ``from``."""
    open_utc = datetime.combine(day, SESSION_OPEN, tzinfo=ET).astimezone(UTC)
    rows = (
        await session.execute(
            select(AuditLog.ts, AuditLog.payload_json)
            .where(
                AuditLog.action == "STRATEGY_UPDATED",
                AuditLog.target_id == str(strat_id),
                AuditLog.payload_json.like("%opening_range_minutes%"),
            )
            .order_by(AuditLog.ts)
        )
    ).all()

    changes: list[tuple[datetime, int, int]] = []
    for ts, raw in rows:
        try:
            payload = json.loads(raw) if isinstance(raw, str) else (raw or {})
            delta = payload["changed"]["params"]["opening_range_minutes"]
            frm, to = int(delta["from"]), int(delta["to"])
        except (TypeError, KeyError, ValueError, json.JSONDecodeError):
            continue  # a full-params snapshot, not a from/to diff — carries no transition
        changes.append((ts if ts.tzinfo else ts.replace(tzinfo=UTC), frm, to))

    if not changes:
        return current, "current strategy parameter (no recorded change)"
    prior = [c for c in changes if c[0] < open_utc]
    if not prior:
        first = changes[0]
        return first[1], f"pre-dates the {first[0]:%Y-%m-%d} change {first[1]}->{first[2]}"
    last = prior[-1]
    return last[2], f"set by the {last[0]:%Y-%m-%d %H:%M}Z change {last[1]}->{last[2]}"


def _or_levels(
    symbol: str, day: date, *, or_minutes: int, stop_buffer_pct: float
) -> tuple[Decimal | None, Decimal | None]:
    """(buy, sell) = (OR low, OR high) for the day, or (None, None) with no usable bars."""
    start = datetime(day.year, day.month, day.day, tzinfo=UTC)
    df = _alpaca_fetch_bars(symbol, "1Min", start, start + timedelta(days=1))
    if df.empty:
        return None, None
    w_start, w_end = opening_range_window(day, opening_range_minutes=or_minutes)
    levels = levels_from_or_bars(
        filter_bars_to_window(df, w_start, w_end), stop_buffer_pct=stop_buffer_pct
    )
    if levels is None:
        return None, None
    buy, sell, _stop = levels
    return Decimal(str(buy)), Decimal(str(sell))


async def _run(day: date, *, execute: bool, force: bool, or_minutes: int | None) -> int:
    Session = get_sessionmaker()
    updated = 0
    async with Session() as session:
        strat = (
            await session.execute(
                select(Strategy.id, Strategy.params_json)
                .where(Strategy.name.like("Range Trader%"))
                .order_by(Strategy.id)
                .limit(1)
            )
        ).first()
        if strat is None:
            print("No Range Trader strategy — nothing to do.")
            return 0
        strat_id, params = strat
        current_minutes, stop_buf = params_or_defaults(params)
        if or_minutes is not None:
            minutes, why = or_minutes, "--or-minutes override"
        else:
            minutes, why = await _or_minutes_in_force(
                session, strat_id, day, current=current_minutes
            )
        print(f"opening range for {day} = {minutes} min ({why}); current param = {current_minutes}")

        rows = (
            (
                await session.execute(
                    select(RangeExecutionRecord)
                    .where(RangeExecutionRecord.et_date == day)
                    .order_by(RangeExecutionRecord.symbol)
                )
            )
            .scalars()
            .all()
        )
        if not rows:
            print(f"No range_execution_records for {day}")
            return 0
        for row in rows:
            has_levels = row.avg_buy_price is not None and row.avg_sell_price is not None
            if has_levels and not force:
                print(f"  {row.symbol}: already has levels — skip")
                continue
            buy, sell = _or_levels(row.symbol, day, or_minutes=minutes, stop_buffer_pct=stop_buf)
            if buy is None or sell is None:
                print(f"  {row.symbol}: no OR bars — skip")
                continue
            if has_levels and buy == row.avg_buy_price and sell == row.avg_sell_price:
                print(f"  {row.symbol}: unchanged — skip")
                continue
            print(
                f"  {row.symbol}: buy={buy} sell={sell} "
                f"(was buy={row.avg_buy_price} sell={row.avg_sell_price})"
            )
            updated += 1
            if execute:
                row.avg_buy_price = buy
                row.avg_sell_price = sell
        if execute and updated:
            await session.commit()
    print(f"{'Updated' if execute else 'Would update'} {updated} row(s) for {day}")
    return updated


def main() -> None:
    ap = argparse.ArgumentParser(description="Backfill OR buy/sell on range_execution_records.")
    ap.add_argument("--date", required=True, type=date.fromisoformat)
    ap.add_argument("--execute", action="store_true", help="write (default: preview only)")
    ap.add_argument(
        "--force", action="store_true", help="also overwrite rows that already carry levels"
    )
    ap.add_argument(
        "--or-minutes", type=int, default=None, help="override the strategy's opening_range_minutes"
    )
    args = ap.parse_args()
    asyncio.run(_run(args.date, execute=args.execute, force=args.force, or_minutes=args.or_minutes))


if __name__ == "__main__":
    main()
