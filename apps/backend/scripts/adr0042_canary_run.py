"""ADR 0042 canary — the executing harness. Places REAL PAPER ORDERS on account 3.

Manifest v1.0. ``max_daily_loss`` FROZEN at $3,000 before any activity (audited).

THE BREACH IS REAL. A buy of a wide-spread instrument marks to the BID immediately, so crossing
that spread is a genuine mark-to-market loss which arms the lock through the same
``day_change = equity - last_equity`` path that tripped account 1 at 09:30:25 ET on 2026-07-13.
The limit is never moved to meet the account.

THREE breach positions, not one, because user 3's ``max_position_notional`` is $25,000 — and the
answer to a cap that blocks the test is NOT to raise the cap. That is the same error as moving
the daily-loss limit to meet the account.

Ordering is forced by the system under test: the long legs are opened BEFORE the lock, because
once locked no buy passes.
"""

from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime
from decimal import Decimal

import httpx
from sqlalchemy import select, text

from app.brokers.alpaca.credentials import credentials_for_mode
from app.brokers.registry import BrokerRegistry
from app.db.enums import OrderSide, OrderSourceType, OrderType, TimeInForce
from app.db.models.account import Account
from app.db.models.risk_decision import RiskDecision as LedgerRow
from app.db.models.risk_reservation import RESERVATION_HELD, RiskReservation
from app.db.session import get_sessionmaker
from app.events.bus import EventBus
from app.orders.router import CancelRejectedByRisk, OrderRouter
from app.risk import OrderRequest, RiskEngine
from app.risk.decision_service import RiskDecisionService
from app.risk.risk_effect import ActionType, ProposedAction

D = Decimal

USER = 3
ACCT = 3
LEG = "F"
LEG_QTY = D("500")
LEG2 = "MSFT"
LEG2_QTY = D("20")
BREACH_SYMS = ["JJC", "IEUS", "KOKU"]
BREACH_NOTIONAL = D("24000")
CAP = D("-3000")

R: list[dict] = []


def rec(step: str, ok: bool, detail: str) -> None:
    R.append({"step": step, "status": "PASS" if ok else "FAIL", "detail": detail})
    print(f"  [{'PASS' if ok else 'FAIL'}] {step}: {detail}", flush=True)


async def day_change(sf) -> Decimal:
    async with sf() as s:
        r = (
            await s.execute(text("SELECT day_change FROM accounts_state WHERE account_id=3"))
        ).scalar_one_or_none()
    return D(str(r or 0))


def mk(sym: str, side: OrderSide, qty: Decimal, src=OrderSourceType.STRATEGY) -> OrderRequest:
    return OrderRequest(
        user_id=USER, account_id=ACCT, symbol_ticker=sym, side=side, qty=qty,
        type=OrderType.MARKET, tif=TimeInForce.DAY, source_type=src,
    )


def _sent(o) -> bool:
    return str(getattr(o, "status", "")).endswith("submitted")


def _rejected(o) -> bool:
    return str(getattr(o, "status", "")).endswith("rejected")


async def main() -> int:  # noqa: PLR0915 — a linear canary reads better as one sequence
    sf = get_sessionmaker()
    reg = BrokerRegistry(sf)
    await reg.load_all()
    ad = reg.get(USER)
    bus = EventBus()
    engine = RiskEngine(sf, broker_registry=reg, bus=bus)
    router = OrderRouter(ad, engine, sf, bus, broker_registry=reg)

    print(f"ADR 0042 CANARY - account {ACCT} - {datetime.now(UTC):%H:%M UTC}")
    print("=" * 78)

    print("\nStep 1 - controlled exposure (must precede the lock: once locked, no buy passes)")
    have = {p["symbol"]: D(str(p["qty"])) for p in ad.get_positions()}
    for sym, want in ((LEG, LEG_QTY), (LEG2, LEG2_QTY)):
        short = want - have.get(sym, D(0))
        if short <= 0:
            rec(f"1.leg_{sym}", True, f"already held x{have.get(sym)}")
            continue
        o = await router.submit(mk(sym, OrderSide.BUY, short))
        rec(f"1.leg_{sym}", _sent(o), f"BUY {short} -> {o.status}")
    await asyncio.sleep(4)

    print("\nStep 2 - enter daily-loss breach via a REAL mark-to-market loss")
    creds = await credentials_for_mode("paper", user_id=USER, session_factory=sf)
    h = {"APCA-API-KEY-ID": creds.api_key, "APCA-API-SECRET-KEY": creds.api_secret}
    async with httpx.AsyncClient(timeout=20) as c:
        resp = await c.get(
            "https://data.alpaca.markets/v2/stocks/quotes/latest",
            params={"symbols": ",".join(BREACH_SYMS)}, headers=h,
        )
    quotes = resp.json()["quotes"]

    for sym in BREACH_SYMS:
        if await day_change(sf) <= D("-3200"):
            print(f"  breach already reached; skipping {sym}")
            break
        q = quotes.get(sym) or {}
        bid, ask = D(str(q.get("bp") or 0)), D(str(q.get("ap") or 0))
        if bid <= 0 or ask <= 0:
            print(f"  {sym}: no quote; skipping")
            continue
        shares = (BREACH_NOTIONAL / ask).quantize(D("1"))
        mark = shares * (ask - bid)
        print(
            f"  {sym}: bid {bid} / ask {ask} - spread {(ask - bid) / ask * 100:.2f}% "
            f"-> BUY {shares} sh (${shares * ask:,.0f}), expected mark ~-${mark:,.0f}",
            flush=True,
        )
        o = await router.submit(mk(sym, OrderSide.BUY, shares))
        rec(f"2.buy_{sym}", _sent(o), f"BUY {shares} -> {o.status}")
        await asyncio.sleep(7)

    for _ in range(20):
        dc = await day_change(sf)
        if dc <= CAP:
            break
        await asyncio.sleep(3)
    dc = await day_change(sf)
    rec("2.breached", dc <= CAP, f"day_change = ${dc:,.2f} vs cap ${CAP:,.2f}")
    if dc > CAP:
        print("\nABORT: breach not reached. NOT lowering the limit - that is forbidden.")
        return 1

    print("\nStep 3 - a new BUY must be rejected while locked")
    o = await router.submit(mk(LEG, OrderSide.BUY, D("1")))
    rec("3.buy_rejected", _rejected(o), f"BUY 1 {LEG} -> {o.status}")

    print("\nStep 4 - a verified partial reduction must pass BOTH step 9 and step 13")
    async with sf() as s:
        tripped = (await s.get(Account, ACCT)).circuit_breaker_tripped_at
    print(f"  breaker tripped_at = {tripped}  (so step 13 is live too)")
    o = await router.submit(mk(LEG, OrderSide.SELL, D("50")))
    rec("4.reduction_allowed", _sent(o), f"SELL 50 {LEG} -> {o.status} (broker {o.broker_order_id})")
    rec("4.lock_not_reset", tripped is not None, "the breaker was NOT reset to let it through")

    print("\nStep 5 - an oversell that would cross zero must be rejected")
    o = await router.submit(mk(LEG, OrderSide.SELL, D("100000")))
    rec("5.oversell_rejected", _rejected(o), f"SELL 100000 {LEG} -> {o.status}")

    print("\nStep 6 - two concurrent reductions must not consume the same capacity")
    await asyncio.sleep(4)
    held = next((D(str(p["qty"])) for p in ad.get_positions() if p["symbol"] == LEG), D(0))
    each = (held * D("0.7")).quantize(D("1"))
    print(f"  holding {held} {LEG}; firing 2 x SELL {each} concurrently")
    a, b = await asyncio.gather(
        router.submit(mk(LEG, OrderSide.SELL, each)),
        router.submit(mk(LEG, OrderSide.SELL, each)),
        return_exceptions=True,
    )
    outcomes = [str(getattr(x, "status", type(x).__name__)) for x in (a, b)]
    n_sent = sum(1 for x in (a, b) if _sent(x))
    rec("6.exactly_one", n_sent == 1, f"{outcomes} -> {n_sent} submitted (must be exactly 1)")
    await asyncio.sleep(6)
    after = next((D(str(p["qty"])) for p in ad.get_positions() if p["symbol"] == LEG), D(0))
    rec("6.never_short", after >= 0, f"{LEG} position after = {after} (must be >= 0)")

    print("\nStep 7 - cancellation is classified, not waved through")
    resting = await router.submit(OrderRequest(
        user_id=USER, account_id=ACCT, symbol_ticker=LEG2, side=OrderSide.SELL, qty=D("1"),
        type=OrderType.LIMIT, tif=TimeInForce.DAY, limit_price=D("9999"),
        source_type=OrderSourceType.MANUAL,
    ))
    if _sent(resting):
        try:
            await router.cancel(resting.id)
            rec("7.cancel_protective_refused", False, "the protective sell-to-close WAS cancelled")
        except CancelRejectedByRisk as exc:
            rec("7.cancel_protective_refused", True, f"refused: {', '.join(exc.reasons)}")
    else:
        rec("7.cancel_protective_refused", False, f"could not rest a sell: {resting.status}")

    print("\nStep 8 - source neutrality (MANUAL treated exactly like STRATEGY)")
    m = await router.submit(mk(LEG2, OrderSide.SELL, D("1"), OrderSourceType.MANUAL))
    rec("8.manual_reduction", _sent(m), f"MANUAL SELL 1 {LEG2} -> {m.status}")

    print("\nStep 9 - a state change before submission VOIDS the approval")
    async with sf() as s:
        svc = RiskDecisionService(s)
        held = next((D(str(p["qty"])) for p in ad.get_positions() if p["symbol"] == LEG), D(0))
        act = ProposedAction(ActionType.ORDER_SUBMIT, LEG, OrderSide.SELL, max(D("1"), held))
        prior, lid, rid = await svc.decide(
            account_id=ACCT, adapter=ad, action=act, lock_state="DAILY_LOSS",
            lock_reason="daily_loss_exceeded", daily_pnl=dc, source_type="STRATEGY",
        )
        print(f"  classified {prior.risk_effect}/{prior.decision}, reservation {rid}")
        await router.submit(mk(LEG, OrderSide.SELL, D("1")))
        await asyncio.sleep(5)
        _res, lid2, _ = await svc.confirm_unchanged_or_reclassify(
            account_id=ACCT, adapter=ad, action=act, prior=prior, prior_ledger_id=lid,
            reservation_id=rid, lock_state="DAILY_LOSS", lock_reason="daily_loss_exceeded",
            daily_pnl=dc, source_type="STRATEGY",
        )
        rec("9.conflict_detected", lid2 != lid,
            f"ledger {lid} superseded by {lid2} - the approval was NOT reused")
        rr = (
            await s.execute(select(RiskReservation).where(RiskReservation.id == rid))
        ).scalars().first()
        rec("9.reservation_rolled_back", rr is not None and rr.state != RESERVATION_HELD,
            f"reservation {rid} -> {rr.state if rr else '?'} ({rr.release_reason if rr else ''})")

    print("\n" + "=" * 78)
    async with sf() as s:
        rows = (
            await s.execute(
                select(LedgerRow).where(LedgerRow.account_id == ACCT).order_by(LedgerRow.id)
            )
        ).scalars().all()
        held_res = (
            await s.execute(
                select(RiskReservation).where(
                    RiskReservation.account_id == ACCT,
                    RiskReservation.state == RESERVATION_HELD,
                )
            )
        ).scalars().all()

    print(f"\nDECISION LEDGER - {len(rows)} rows")
    for r in rows:
        print(f"  #{r.id:3} {r.action_type:13} {r.symbol:5} {str(r.side or '-'):4} "
              f"{str(r.qty or ''):>9} {r.lock_state:11} {r.risk_effect:16} {r.decision:12} "
              f"{json.loads(r.reason_codes)}")

    increasing_allowed = [
        r for r in rows if r.risk_effect == "RISK_INCREASING" and r.decision == "ALLOW"
    ]
    gate = [
        ("no unclassified decision", all(r.risk_effect and r.decision for r in rows)),
        ("no increasing order allowed", not increasing_allowed),
        ("every decision carries a policy version + state hash",
         all(r.risk_policy_version and r.before_state_hash for r in rows)),
        ("no orphan held reservations", len(held_res) == 0),
        ("all steps passed", all(x["status"] == "PASS" for x in R)),
    ]
    print("\nRELEASE GATE")
    for name, ok in gate:
        print(f"  [{'PASS' if ok else 'FAIL'}] {name}")

    green = all(ok for _, ok in gate)
    print("\n" + ("*** CANARY GREEN ***" if green else "*** CANARY RED ***"))
    return 0 if green else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
