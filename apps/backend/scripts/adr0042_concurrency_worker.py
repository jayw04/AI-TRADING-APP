"""ADR 0042 canary — the SECOND OS PROCESS for the concurrency assertion.

⚠ WHY A SEPARATE PROCESS

The previous canary fired its two concurrent reductions with ``asyncio.gather`` inside ONE process.
The reservation was guarded by a per-account ``asyncio.Lock``, which serialises coroutines in that
process — so the assertion PASSED while the cross-process hole stayed wide open. It would have
returned GREEN on precisely the defect it was written to catch.

On 2026-07-14 two independent Python processes each received ALLOW/VERIFIED_REDUCTION for the same
183 shares. Only the broker stopped the second order. **The broker is not a safety mechanism.**

So this worker is launched as a genuinely separate interpreter, with its own event loop and its own
database connections, and it synchronises with its twin on a wall-clock barrier immediately before
the decision. Its verdict is written to a file the parent reads back.

Invoked as:  python scripts/adr0042_concurrency_worker.py <symbol> <qty> <barrier_epoch> <out.json>
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import time
from decimal import Decimal as D
from pathlib import Path

from app.brokers.registry import BrokerRegistry
from app.db.enums import OrderSide, OrderSourceType, OrderType, TimeInForce
from app.db.session import get_sessionmaker
from app.events.bus import EventBus
from app.orders.router import OrderRouter
from app.risk import OrderRequest, RiskEngine
from scripts.adr0042_canary_lib import ACCT, USER, max_ledger_id


async def main() -> int:
    symbol, qty, barrier, out = sys.argv[1], D(sys.argv[2]), float(sys.argv[3]), Path(sys.argv[4])

    sf = get_sessionmaker()
    reg = BrokerRegistry(sf)
    await reg.load_all()
    ad = reg.get(USER)
    bus = EventBus()
    router = OrderRouter(
        ad, RiskEngine(sf, broker_registry=reg, bus=bus), sf, bus, broker_registry=reg
    )
    before = await max_ledger_id(sf)

    # Everything above is warm-up. Sit on the barrier so both processes enter the decision at the
    # same instant — otherwise they never actually race and a pass would be vacuous.
    while time.time() < barrier:
        await asyncio.sleep(0.002)

    started = time.time()
    try:
        o = await router.submit(
            OrderRequest(
                user_id=USER, account_id=ACCT, symbol_ticker=symbol, side=OrderSide.SELL,
                qty=qty, type=OrderType.MARKET, tif=TimeInForce.DAY,
                source_type=OrderSourceType.STRATEGY,
            )
        )
        status = str(getattr(o, "status", o))
        payload = {
            "pid": os.getpid(),
            "submitted_at": started,
            "returned_at": time.time(),
            "status": status,
            "order_id": getattr(o, "id", None),
            "broker_order_id": getattr(o, "broker_order_id", None),
            "rejection_reason": getattr(o, "rejection_reason", None),
            "ledger_id_before": before,
            "error": None,
        }
    except Exception as exc:  # noqa: BLE001 — the parent adjudicates; this worker only reports
        payload = {
            "pid": os.getpid(),
            "submitted_at": started,
            "returned_at": time.time(),
            "status": f"EXC:{type(exc).__name__}",
            "order_id": None,
            "broker_order_id": None,
            "rejection_reason": str(exc)[:200],
            "ledger_id_before": before,
            "error": str(exc)[:200],
        }

    out.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
