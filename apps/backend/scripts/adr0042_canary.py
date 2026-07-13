"""ADR 0042 — the paper-account canary. Release gate, not a smoke test.

Runs the owner's 10-step sequence on account 3 (the permanent risk-engine verification
account) and collects the ledger evidence for each step.

    A FILLED CANARY ORDER IS NOT A PASS.

The gate is: ledger rows reconcile with broker events, no duplicate reservations, no zero
crossing, no stale-snapshot approvals, no source-specific bypass, no unclassified decision, no
increasing order through steps 9/13, and every verified reduction through BOTH gates.

THE BREACH IS REAL. `max_daily_loss` is frozen at $3,000 in the manifest BEFORE anything
trades, and the breach is produced by churn trades that realise genuine losses so that
`day_change = equity - last_equity` crosses the threshold through the SAME account-state path
that tripped account 1 at 09:30:25 ET on 2026-07-13. The limit is never moved to meet the
account — that would exercise the gate while bypassing the calculation that arms it, and a
green canary would then prove strictly less than it appeared to.

Ordering is forced by the system under test: the long positions must be opened BEFORE the lock,
because once locked no buy passes. That is a constraint, not a convenience.

    python scripts/adr0042_canary.py --check      # preconditions only; trades nothing
    python scripts/adr0042_canary.py --run        # the full sequence (places PAPER orders)
"""

from __future__ import annotations

import argparse
import asyncio
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import select

from app.brokers.registry import BrokerRegistry
from app.db.enums import (
    RiskScopeType,
)
from app.db.models.account import Account, AccountMode
from app.db.models.risk_limits import RiskLimits
from app.db.models.risk_reservation import RESERVATION_HELD, RiskReservation
from app.db.models.strategy import Strategy
from app.db.session import get_sessionmaker

D = Decimal

# ---- FROZEN (canary manifest v1.0; set before any activity) --------------------------
CANARY_USER_ID = 3
CANARY_ACCOUNT_ID = 3
MAX_DAILY_LOSS = D("3000")
LEG_A = ("AAPL", 500)   # the leg used for the concurrency test (needs >= 500)
LEG_B = ("MSFT", 100)
CHURN = "SPY"           # opened and closed repeatedly to realise the loss

RESULTS: list[dict] = []


def _log(step: str, status: str, detail: str) -> None:
    RESULTS.append({"step": step, "status": status, "detail": detail})
    icon = {"PASS": "PASS", "FAIL": "FAIL", "INFO": "····"}[status]
    print(f"  [{icon}] {step}: {detail}")


async def preconditions(session, reg) -> bool:
    """Refuse to run unless the account is exactly what the manifest says it is."""
    ok = True
    account = await session.get(Account, CANARY_ACCOUNT_ID)
    if account is None or account.mode is not AccountMode.paper:
        _log("pre.account", "FAIL", "account 3 is missing or not PAPER")
        return False
    if account.circuit_breaker_tripped_at is not None:
        _log("pre.breaker", "FAIL", "breaker already tripped — not a clean baseline")
        ok = False

    strategies = (
        (await session.execute(select(Strategy).where(Strategy.user_id == CANARY_USER_ID)))
        .scalars().all()
    )
    live = [s for s in strategies if s.status.value not in ("idle", "archived")]
    if live:
        _log("pre.no_strategy", "FAIL", f"strategies not idle: {[s.name for s in live]}")
        ok = False

    limits = (
        await session.execute(
            select(RiskLimits).where(
                RiskLimits.user_id == CANARY_USER_ID,
                RiskLimits.broker_mode == AccountMode.paper,
                RiskLimits.scope_type == RiskScopeType.GLOBAL,
            )
        )
    ).scalars().first()
    if limits is None or limits.max_daily_loss != MAX_DAILY_LOSS:
        got = limits.max_daily_loss if limits else None
        _log(
            "pre.frozen_limit", "FAIL",
            f"max_daily_loss must be FROZEN at {MAX_DAILY_LOSS} before any activity; got {got}",
        )
        ok = False
    else:
        _log("pre.frozen_limit", "PASS", f"max_daily_loss = {MAX_DAILY_LOSS} (frozen)")

    ad = reg.get(CANARY_USER_ID)
    positions = ad.get_positions()
    open_orders = ad.list_orders(status="open", limit=100)
    acct = ad.get_account()
    if positions:
        _log("pre.flat", "FAIL", f"account is not flat: {[p['symbol'] for p in positions]}")
        ok = False
    if open_orders:
        _log("pre.no_open_orders", "FAIL", f"{len(open_orders)} open orders exist")
        ok = False

    held = (
        await session.execute(
            select(RiskReservation).where(
                RiskReservation.account_id == CANARY_ACCOUNT_ID,
                RiskReservation.state == RESERVATION_HELD,
            )
        )
    ).scalars().all()
    if held:
        _log("pre.no_reservations", "FAIL", f"{len(held)} reservations already held")
        ok = False

    if ok:
        _log(
            "pre.baseline", "PASS",
            f"equity ${float(acct['equity']):,.2f} · flat · no open orders · breaker clear",
        )
    return ok


async def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--check", action="store_true", help="preconditions only; trades nothing")
    ap.add_argument("--run", action="store_true", help="execute the sequence (PLACES ORDERS)")
    args = ap.parse_args()

    sf = get_sessionmaker()
    reg = BrokerRegistry(sf)
    await reg.load_all()

    print(f"\nADR 0042 canary — account {CANARY_ACCOUNT_ID} — {datetime.now(UTC):%Y-%m-%d %H:%M UTC}")
    print("=" * 78)
    print("\nStep 0 — baseline reconciliation")
    async with sf() as session:
        ok = await preconditions(session, reg)

    if not ok:
        print("\nPRECONDITIONS FAILED — refusing to run. Fix the baseline first.")
        return 1
    if not args.run:
        print("\nPreconditions OK. Re-run with --run to execute (this PLACES PAPER ORDERS).")
        return 0

    print(
        "\n--run is not yet implemented: steps 1-9 place real paper orders and must not be\n"
        "executed until this branch is DEPLOYED to the box and the market is OPEN.\n"
        "Deploy first, then run at the open."
    )
    return 2


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
