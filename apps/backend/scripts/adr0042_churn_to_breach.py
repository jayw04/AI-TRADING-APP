"""ADR 0042 canary — reach the FROZEN $3,000 breach by real, realized losses.

MEASURED, not guessed. Alpaca paper fills at the MID, not the ask — so the "cross a wide
spread" idea I proposed is void (IEUS: quoted ask 71.75, FILLED at 69.57). What actually costs
money is the real round trip: four buys + four sells across ~$76k of turnover realized -$297.
That is ~0.39% per cycle, and it is genuine realized loss flowing through the true
``day_change = equity - last_equity`` path.

So: cycle until the account genuinely breaches. The limit is NEVER moved to meet the account.

Churn while UNLOCKED writes NO risk-decision rows (ADR 0042 is not in the unlocked path), so
this leaves the evidence ledger clean — the noise lands in `orders`, where it belongs.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from decimal import Decimal as D

from sqlalchemy import text

from app.brokers.registry import BrokerRegistry
from app.db.enums import OrderSide, OrderSourceType, OrderType, TimeInForce
from app.db.session import get_sessionmaker
from app.events.bus import EventBus
from app.orders.router import OrderRouter
from app.risk import OrderRequest, RiskEngine

USER, ACCT = 3, 3
CAP = D("-3000")
# Wide-spread names cost the most per round trip; F/MSFT add turnover cheaply.
# CHURN instruments only. The test LEGS (F, MSFT) are bought and HELD by the canary and must
# NEVER be cycled here — on the 2026-07-13 run this script flattened everything each cycle, so
# by the time the lock armed the account was flat and there was nothing left to reduce. That is
# what made the canary RED for a reason that had nothing to do with the risk engine.
CHURN_NAMES = [("IEUS", D("24000")), ("KOKU", D("24000"))]
PROTECTED = {"F", "MSFT"}   # the legs — hands off
DEADLINE_MINUTES = 25   # abort rather than overrun the session; never lower the limit instead


async def day_change(sf) -> D:
    async with sf() as s:
        r = (
            await s.execute(text("SELECT day_change FROM accounts_state WHERE account_id=3"))
        ).scalar_one_or_none()
    return D(str(r or 0))


def req(sym, side, qty):
    return OrderRequest(
        user_id=USER, account_id=ACCT, symbol_ticker=sym, side=side, qty=qty,
        type=OrderType.MARKET, tif=TimeInForce.DAY, source_type=OrderSourceType.MANUAL,
    )


async def main() -> int:
    sf = get_sessionmaker()
    reg = BrokerRegistry(sf)
    await reg.load_all()
    ad = reg.get(USER)
    bus = EventBus()
    router = OrderRouter(
        ad, RiskEngine(sf, broker_registry=reg, bus=bus), sf, bus, broker_registry=reg
    )

    deadline = datetime.now(UTC) + timedelta(minutes=DEADLINE_MINUTES)
    print(f"churn to breach — cap {CAP} — deadline {deadline:%H:%M} UTC", flush=True)
    cycle = 0
    while True:
        dc = await day_change(sf)
        print(f"  cycle {cycle:2}  day_change = ${dc:,.2f}", flush=True)
        if dc <= CAP:
            print(f"\nBREACHED: ${dc:,.2f} <= ${CAP:,.2f}")
            return 0
        if datetime.now(UTC) >= deadline:
            print(f"\nDEADLINE. day_change ${dc:,.2f} did NOT reach ${CAP:,.2f}.")
            print("NOT lowering the limit — that is forbidden. Closing the churn positions.")
            for p in ad.get_positions():
                if p["symbol"] in PROTECTED:
                    continue
                await router.submit(req(p["symbol"], OrderSide.SELL, D(str(p["qty"]))))
                await asyncio.sleep(1)
            return 1

        cycle += 1
        # BUY leg
        prices = {p["symbol"]: D(str(p.get("current_price") or 0)) for p in ad.get_positions()}
        for sym, notional in CHURN_NAMES:
            px = prices.get(sym) or D("0")
            if px <= 0:
                q = ad.get_account()  # noqa: F841 — force a broker touch; price comes from quote below
                import httpx

                from app.brokers.alpaca.credentials import credentials_for_mode
                creds = await credentials_for_mode("paper", user_id=USER, session_factory=sf)
                h = {"APCA-API-KEY-ID": creds.api_key, "APCA-API-SECRET-KEY": creds.api_secret}
                async with httpx.AsyncClient(timeout=15) as c:
                    r = await c.get(
                        "https://data.alpaca.markets/v2/stocks/quotes/latest",
                        params={"symbols": sym}, headers=h,
                    )
                qq = r.json()["quotes"][sym]
                px = (D(str(qq["bp"])) + D(str(qq["ap"]))) / 2
            shares = (notional / px).quantize(D("1"))
            if shares <= 0:
                continue
            o = await router.submit(req(sym, OrderSide.BUY, shares))
            if not str(o.status).endswith("submitted"):
                print(f"    buy {sym} x{shares} -> {o.status}", flush=True)
            await asyncio.sleep(1.5)

        await asyncio.sleep(5)

        # SELL leg — close ONLY the churn instruments. The legs are protected.
        for p in ad.get_positions():
            if p["symbol"] in PROTECTED:
                continue
            await router.submit(req(p["symbol"], OrderSide.SELL, D(str(p["qty"]))))
            await asyncio.sleep(1.5)
        await asyncio.sleep(6)


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
