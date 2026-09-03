"""Remove a delisted ticker from every live strategy universe — audit-logged.

WHY (2026-07-13). SATS stopped printing bars on 2026-06-23 and stayed in all four live
universes (momentum / sector-rotation / low-volatility / combined-book) for three weeks. A
symbol with no bars is not an error anywhere: ``StrategyEngine._dispatch_bar_tick`` sees
``df.empty`` and ``continue``s, so the name is silently dropped from every ranking. Nothing
logs it, nothing alarms, and the universe count still reads 201.

The universe lives in ``strategies.symbols_json`` (the DB), NOT in the checked-in
``data/*_symbols.txt`` files — those only seed a strategy at provisioning time. So deploying
the file change does NOT fix a running book; this script does.

Changing a live strategy's universe is a consequential action, so it goes through the typed
``AuditLogger`` (STRATEGY_UPDATED) rather than a raw UPDATE. It does NOT touch the order path.

SAFETY: refuses to remove a ticker that any account still HOLDS. ``_current_holdings()``
iterates ``ctx.symbols``, so a held name dropped from the universe becomes an orphan the
strategy can no longer see or sell. Liquidate first, then remove.

    python scripts/remove_dead_ticker.py SATS            # dry run
    python scripts/remove_dead_ticker.py SATS --apply
"""

from __future__ import annotations

import argparse
import asyncio
from datetime import UTC, datetime

from sqlalchemy import select

from app.audit import AuditAction, AuditActorType, AuditLogger
from app.brokers.registry import BrokerRegistry
from app.db.models.strategy import Strategy
from app.db.session import get_sessionmaker


async def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("ticker")
    ap.add_argument("--apply", action="store_true", help="write the change (default: dry run)")
    args = ap.parse_args()
    ticker = args.ticker.upper()

    sf = get_sessionmaker()

    # --- SAFETY GATE: never orphan a live position -------------------------------------
    reg = BrokerRegistry(sf)
    await reg.load_all()
    holders: list[str] = []
    async with sf() as session:
        users = (await session.execute(select(Strategy.user_id).distinct())).scalars().all()
    for uid in sorted({u for u in users if u}):
        try:
            for p in reg.get(uid).get_positions():
                if str(p.get("symbol", "")).upper() == ticker:
                    holders.append(f"user {uid}: qty={p.get('qty')}")
        except Exception as exc:  # noqa: BLE001 — a broker we cannot read is not a green light
            print(f"  !! could not read positions for user {uid}: {exc}")
            return 1

    if holders:
        print(f"REFUSING: {ticker} is still HELD — {'; '.join(holders)}")
        print(
            "  Dropping a held name from the universe orphans it: _current_holdings() only\n"
            "  iterates ctx.symbols, so the strategy could no longer see OR sell the position.\n"
            "  Liquidate it first, then re-run."
        )
        return 1

    # --- apply -------------------------------------------------------------------------
    async with sf() as session:
        # EVERY strategy carrying the ticker — deliberately NOT filtered to engine-runnable
        # statuses. A HALTED book still holds a universe and will resume with it: the first
        # run of this script silently skipped momentum-portfolio because its daily-loss
        # breaker had tripped that morning, which would have left the dead ticker in place
        # exactly where it was hardest to notice.
        rows = (await session.execute(select(Strategy))).scalars().all()
        touched = 0
        for st in rows:
            syms = list(st.symbols_json or [])
            keep = [s for s in syms if s.upper() != ticker]
            if len(keep) == len(syms):
                continue
            touched += 1
            print(f"  strategy {st.id:2} {st.name:20} {len(syms)} -> {len(keep)} symbols")
            if not args.apply:
                continue

            st.symbols_json = keep
            st.updated_at = datetime.now(UTC)
            AuditLogger.write(
                session,
                actor_type=AuditActorType.SYSTEM,
                actor_id="remove_dead_ticker",
                action=AuditAction.STRATEGY_UPDATED,
                target_type="strategy",
                target_id=st.id,
                payload={
                    "changed": {"symbols_json": f"removed {ticker}"},
                    "reason": f"{ticker} is delisted/halted — it prints no bars, so it was "
                    f"being silently dropped from every ranking",
                    "symbols_before": len(syms),
                    "symbols_after": len(keep),
                },
                user_id=st.user_id,
            )
        if args.apply and touched:
            await session.commit()

    if not touched:
        print(f"{ticker} is not in any live universe — nothing to do.")
        return 0
    if args.apply:
        print(f"\nAPPLIED to {touched} strateg(ies), audit-logged as STRATEGY_UPDATED.")
        print("Restart the backend (or /reload each strategy) so the engine re-reads symbols.")
    else:
        print(f"\nDRY RUN — {touched} strateg(ies) would change. Re-run with --apply.")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
