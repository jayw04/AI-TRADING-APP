#!/usr/bin/env python3
"""Sweep-reconcile local orders that are stuck non-terminal while the broker has
already finished them — the local<->broker drift caused by a dropped trade-updates
stream event (Norton flapping on the laptop; see the gotcha memory + ADR 0032).

WHY: when the Alpaca trade-updates websocket reconnects, a fill/cancel that lands in
the gap is NOT re-delivered, so the local order stays SUBMITTED with no Fill row even
though the broker filled it (the position is still correct via the REST position-sync).
Such orders are invisible on the Orders page's Today (fills) and History (terminal)
tabs. This script re-applies the missed broker outcome through the CANONICAL handler
(``TradeUpdateConsumer._handle``) so the Fill row, order status, ``terminal_at``,
position recompute, and the ``ORDER_FILL_INGESTED`` audit entry all land exactly as the
live stream would have produced them. Idempotent (re-running is a no-op).

RUN IN THE BACKEND CONTAINER (needs per-account creds via BrokerRegistry + the
AuditLogger hash chain — a raw audit_log insert is blocked by the immutability trigger):

    # dry-run (default — shows the plan, changes nothing):
    docker compose exec -T backend python scripts/reconcile_stuck_orders.py
    # apply:
    docker compose exec -T backend python scripts/reconcile_stuck_orders.py --apply

INTENDED USE: run the dry-run, eyeball the plan, then ``--apply`` immediately BEFORE the
ADR-0032 cutover DB snapshot so a clean order ledger travels to EC2. Read-only against
the broker (``get_order`` only); never submits or cancels anything at the broker.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from decimal import Decimal

from sqlalchemy import func, select

from app.brokers.registry import BrokerRegistry
from app.db.enums import TERMINAL_ORDER_STATUSES
from app.db.models.fill import Fill
from app.db.models.order import Order
from app.db.session import get_sessionmaker
from app.events.bus import EventBus
from app.orders.lifecycle import TradeUpdateConsumer
from app.orders.positions import PositionRecomputer

# Broker (Alpaca) statuses that mean "the order is DONE at the broker".
BROKER_FILLED = "filled"
BROKER_CANCEL = {"canceled", "expired", "rejected", "replaced"}
# Everything else (new, accepted, partially_filled, pending_*, done_for_day) = still
# genuinely working at the broker → leave it alone (do NOT force a terminal state).


async def _local_filled_qty(sf, order_id: int) -> Decimal:
    async with sf() as s:
        total = (
            await s.execute(
                select(func.coalesce(func.sum(Fill.qty), 0)).where(
                    Fill.order_id == order_id
                )
            )
        ).scalar_one()
    return Decimal(str(total or 0))


async def main(apply: bool) -> int:
    sf = get_sessionmaker()

    # 1) local orders that are NOT terminal but DID reach the broker (have an id).
    async with sf() as s:
        rows = (
            await s.execute(
                select(Order).where(Order.broker_order_id.isnot(None))
            )
        ).scalars().all()
        stuck = [
            (o.id, o.account_id, o.broker_order_id, o.status, Decimal(str(o.qty)))
            for o in rows
            if o.status not in TERMINAL_ORDER_STATUSES
        ]

    print(f"non-terminal local orders with a broker id: {len(stuck)}")
    if not stuck:
        print("nothing to sweep — order ledger is clean.")
        return 0

    reg = BrokerRegistry(sf)
    await reg.load_all()
    bus = EventBus()
    consumer = TradeUpdateConsumer(sf, bus, PositionRecomputer(sf, bus))

    plan: list[tuple] = []
    for order_id, account_id, boid, lstatus, lqty in stuck:
        adapter = reg.get(account_id)
        if adapter is None:
            print(f"  order {order_id}: no adapter for account {account_id} — skip")
            continue
        try:
            bo = await asyncio.to_thread(adapter.get_order, boid)
        except Exception as exc:  # noqa: BLE001 — broker unreachable/404 → skip, don't guess
            print(f"  order {order_id}: broker get_order failed "
                  f"({type(exc).__name__}: {str(exc)[:60]}) — skip")
            continue

        bstatus = str(bo.get("status"))
        if bstatus == BROKER_FILLED:
            bqty = Decimal(str(bo.get("filled_qty") or 0))
            bavg = Decimal(str(bo.get("filled_avg_price") or 0))
            delta = bqty - await _local_filled_qty(sf, order_id)
            if delta > 0 and bavg > 0:
                plan.append(("fill", order_id, account_id, boid, lstatus, bstatus,
                             delta, bavg, bo.get("filled_at")))
            else:
                print(f"  order {order_id}: broker filled but no fill delta "
                      f"(broker={bqty}, local already booked) — skip")
        elif bstatus in BROKER_CANCEL:
            plan.append(("terminal", order_id, account_id, boid, lstatus, bstatus,
                         None, None, None))
        else:
            print(f"  order {order_id}: broker still open ({bstatus}) — leave")

    print(f"\n=== PLAN ({'APPLY' if apply else 'DRY-RUN'}): {len(plan)} action(s) ===")
    for kind, oid, acct, _boid, lstatus, bstatus, delta, bavg, _ts in plan:
        if kind == "fill":
            print(f"  FILL  order {oid} (acct {acct}): {lstatus} -> FILLED  "
                  f"delta={delta} @ {bavg}")
        else:
            print(f"  TERM  order {oid} (acct {acct}): {lstatus} -> {bstatus.upper()}")

    if not plan:
        print("no actionable drift.")
        return 0
    if not apply:
        print("\nDRY-RUN only — re-run with --apply to write these.")
        return 0

    for kind, oid, _acct, boid, _lstatus, bstatus, delta, bavg, ts in plan:
        if kind == "fill":
            payload = {
                "event": "fill",
                "broker_order_id": boid,
                # deterministic id → idempotent (re-run sees delta=0 and skips).
                "execution_id": f"recon-{boid}-{delta}",
                "qty": str(delta),
                "price": str(bavg),
                "timestamp": str(ts),
            }
        else:
            payload = {"event": bstatus, "broker_order_id": boid, "raw": {}}
        await consumer._handle(payload)
        print(f"  applied {kind} for order {oid}")

    async with sf() as s:
        remaining = [
            o.id
            for o in (
                await s.execute(select(Order).where(Order.broker_order_id.isnot(None)))
            ).scalars().all()
            if o.status not in TERMINAL_ORDER_STATUSES
        ]
    print(f"\nremaining non-terminal (with broker id): {len(remaining)} {remaining}")
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--apply", action="store_true",
                    help="write the reconciliations (default: dry-run).")
    args = ap.parse_args()
    sys.exit(asyncio.run(main(args.apply)))
