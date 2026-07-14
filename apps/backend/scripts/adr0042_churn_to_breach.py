"""ADR 0042 canary — PRE-LOCK phase: establish the protected legs, then reach the frozen loss cap.

Replaces the previous script, which had three gate-blocking defects:

  * it flattened EVERY position, destroying the legs the post-lock assertions depend on — that is
    what produced the previous structurally-invalid RED;
  * its deadline was hard-coded to a calendar date and silently expired;
  * its breach sizing used a fixed notional, collided with ``POSITION_CAP_QTY``, and churned
    uselessly against rejections instead of sizing from the account's own limits.

The breach is reached by REAL realised losses (~0.4% per round trip on genuine turnover), flowing
through the same ``day_change = equity - last_equity`` path that tripped account 1 on 2026-07-13.

⚠ THE LIMITS ARE NEVER MOVED TO MEET THE ACCOUNT. If the loss cap cannot be reached within the
account's own position, exposure and buying-power limits, this exits with
``BREACH_SETUP_UNREACHABLE_UNDER_CURRENT_LIMITS``. Lowering ``max_daily_loss`` to manufacture a
breach is a bypass, not a test.

Resumable: the checkpoint is written after every cycle, so a dropped connection costs a cycle, not
the run. Single-instance: two concurrent harness processes is exactly the condition that produced
the cross-process double reservation on 2026-07-14.
"""

from __future__ import annotations

import asyncio
import sys
from decimal import Decimal as D
from pathlib import Path

import httpx

from app.brokers.alpaca.credentials import credentials_for_mode
from app.brokers.registry import BrokerRegistry
from app.db.enums import OrderSide, OrderSourceType, OrderType, TimeInForce
from app.db.session import get_sessionmaker
from app.events.bus import EventBus
from app.orders.router import OrderRouter
from app.risk import OrderRequest, RiskEngine
from scripts.adr0042_canary_lib import (
    ACCT,
    CHURN_SYMBOLS,
    LEGS,
    PROTECTED,
    TARGET_OVERSHOOT,
    USER,
    BreachUnreachable,
    CanaryRefused,
    Checkpoint,
    Evidence,
    SingleInstance,
    admissible_shares,
    load_limits,
    snapshot_state,
)

# Below this, a cycle's turnover cannot move the needle and the run would churn forever.
MIN_USEFUL_NOTIONAL = D("2000")
PER_ORDER_CEILING = D("25000")
OUT = Path("/app/data/adr0042_evidence_pre_lock.json")


def req(sym: str, side: OrderSide, qty: D) -> OrderRequest:
    return OrderRequest(
        user_id=USER, account_id=ACCT, symbol_ticker=sym, side=side, qty=qty,
        type=OrderType.MARKET, tif=TimeInForce.DAY, source_type=OrderSourceType.MANUAL,
    )


async def _mid_prices(sf, symbols: list[str]) -> dict[str, D]:
    creds = await credentials_for_mode("paper", user_id=USER, session_factory=sf)
    headers = {"APCA-API-KEY-ID": creds.api_key, "APCA-API-SECRET-KEY": creds.api_secret}
    async with httpx.AsyncClient(timeout=20) as c:
        r = await c.get(
            "https://data.alpaca.markets/v2/stocks/quotes/latest",
            params={"symbols": ",".join(symbols)}, headers=headers,
        )
    out: dict[str, D] = {}
    for sym, q in (r.json().get("quotes") or {}).items():
        bid, ask = D(str(q.get("bp") or 0)), D(str(q.get("ap") or 0))
        if bid > 0 and ask > 0:
            out[sym] = (bid + ask) / 2
    return out


async def _establish_legs(sf, ad, router, ev, cp) -> None:
    snap = await snapshot_state(sf, ad)

    # A locked account cannot buy. Starting the canary in that state guarantees a structurally
    # invalid RED, so refuse rather than produce one.
    if snap.lock_active and not all(snap.positions.get(s, D(0)) >= q for s, q in LEGS):
        raise CanaryRefused(
            "the account is ALREADY LOCKED and the protected legs are absent. No buy can pass "
            "while locked, so the post-lock assertions could not run. Reset the trading day and "
            "start clean — do not produce a RED that says nothing about the risk engine."
        )

    for sym, want in LEGS:
        have = snap.positions.get(sym, D(0))
        if have >= want:
            print(f"  leg {sym}: already hold {have} — skip")
            continue
        pre = await snapshot_state(sf, ad)
        o = await router.submit(req(sym, OrderSide.BUY, want - have))
        ev.record_order(
            step=f"leg_{sym}", snapshot=pre,
            request={"symbol": sym, "side": "BUY", "qty": str(want - have)}, response=o,
        )
        print(f"  leg {sym}: BUY {want - have} -> {o.status}")
        await asyncio.sleep(3)

    await asyncio.sleep(4)
    snap = await snapshot_state(sf, ad)
    ok = all(snap.positions.get(s, D(0)) >= q for s, q in LEGS)
    ev.assert_("legs_established", ok, str({k: str(v) for k, v in snap.positions.items()}))
    if not ok:
        raise CanaryRefused("the protected legs could not be established")
    cp.legs_established = True
    cp.phase = "CHURN"
    cp.save()


async def main() -> int:  # noqa: PLR0915 — a linear setup phase reads better as one sequence
    with SingleInstance():
        sf = get_sessionmaker()
        reg = BrokerRegistry(sf)
        await reg.load_all()
        ad = reg.get(USER)
        bus = EventBus()
        router = OrderRouter(
            ad, RiskEngine(sf, broker_registry=reg, bus=bus), sf, bus, broker_registry=reg
        )

        cp = Checkpoint.load()
        ev = Evidence(phase="PRE_LOCK")
        limits = await load_limits(sf)
        ev.doc["risk_limits"] = limits.as_dict()
        if limits.max_daily_loss is None:
            raise CanaryRefused("no max_daily_loss configured; the canary has nothing to breach")
        target = -(limits.max_daily_loss + TARGET_OVERSHOOT)

        print(f"ADR 0042 canary — PRE-LOCK — account {ACCT}")
        print(f"  loss cap       : ${limits.max_daily_loss:,.2f}   (NEVER moved)")
        print(f"  breach target  : ${target:,.2f}")
        print(f"  protected legs : {list(PROTECTED)}")
        print(f"  churn symbols  : {list(CHURN_SYMBOLS)}")
        print(f"  deadline       : {cp.deadline_at}   (relative budget, not a calendar date)")
        print(f"  resuming       : cycle {cp.cycles}, phase {cp.phase}\n")

        await _establish_legs(sf, ad, router, ev, cp)

        while True:
            snap = await snapshot_state(sf, ad)
            print(
                f"  cycle {cp.cycles:3}  day_change ${snap.day_change:,.2f}"
                f"  -> target ${target:,.2f}",
                flush=True,
            )

            if snap.day_change <= target:
                cp.breach_reached = True
                cp.phase = "BREACHED"
                cp.save()
                ev.assert_(
                    "breach_reached", True,
                    f"day_change ${snap.day_change:,.2f} <= ${target:,.2f}, "
                    f"lock_active={snap.lock_active}",
                )
                break

            if cp.expired():
                ev.assert_(
                    "breach_reached", False,
                    f"budget exhausted at ${snap.day_change:,.2f}; the limit was NOT moved",
                )
                ev.write(OUT)
                print("\nDEADLINE — the limit was NOT lowered to meet the account.")
                return 1

            acct = ad.get_account()
            buying_power = D(str(acct.get("buying_power") or acct.get("cash") or 0))
            gross_used = sum(
                (abs(D(str(p.get("market_value") or 0))) for p in ad.get_positions()), D(0)
            )
            prices = await _mid_prices(sf, list(CHURN_SYMBOLS))

            planned: list[tuple[str, D, D]] = []
            for sym in CHURN_SYMBOLS:
                px = prices.get(sym)
                if px is None:
                    continue
                shares = admissible_shares(
                    price=px, limits=limits, gross_used=gross_used,
                    buying_power=buying_power, ceiling=PER_ORDER_CEILING,
                )
                if shares > 0:
                    planned.append((sym, shares, shares * px))

            turnover = sum((n for _, _, n in planned), D(0))
            if turnover < MIN_USEFUL_NOTIONAL:
                # The account's OWN limits do not admit enough turnover. The answer is NOT to
                # relax them — that is the same error as moving the daily-loss cap.
                ev.assert_(
                    "breach_reachable", False,
                    f"admissible turnover ${turnover:,.0f} < ${MIN_USEFUL_NOTIONAL:,.0f}",
                )
                ev.write(OUT)
                raise BreachUnreachable(
                    f"BREACH_SETUP_UNREACHABLE_UNDER_CURRENT_LIMITS: the account's own limits "
                    f"admit only ${turnover:,.0f} of turnover per cycle (buying power "
                    f"${buying_power:,.0f}, gross exposure used ${gross_used:,.0f}). The loss cap "
                    f"cannot be reached without changing risk configuration — and changing it "
                    f"would be a bypass, not a test."
                )

            cp.cycles += 1
            for sym, shares, notional in planned:
                pre = await snapshot_state(sf, ad)
                o = await router.submit(req(sym, OrderSide.BUY, shares))
                ev.record_order(
                    step=f"churn_buy_{sym}", snapshot=pre,
                    request={"symbol": sym, "side": "BUY", "qty": str(shares),
                             "notional": str(notional)},
                    response=o,
                )
                if not str(o.status).endswith("submitted"):
                    print(f"    buy {sym} x{shares} -> {o.status}", flush=True)
                await asyncio.sleep(1.5)
            await asyncio.sleep(5)

            for p in ad.get_positions():
                if p["symbol"] in PROTECTED:
                    continue                       # ⚠ the legs are NEVER sold by the churn
                await router.submit(req(p["symbol"], OrderSide.SELL, D(str(p["qty"]))))
                await asyncio.sleep(1.5)
            await asyncio.sleep(6)
            cp.note("cycle", n=cp.cycles, day_change=str(snap.day_change))

        final = await snapshot_state(sf, ad)
        ev.doc["final"] = final.as_dict()
        ev.assert_(
            "legs_survived_churn",
            all(final.positions.get(s, D(0)) >= q for s, q in LEGS),
            str({k: str(v) for k, v in final.positions.items()}),
        )
        digest = ev.write(OUT)
        print(f"\nPRE-LOCK COMPLETE — evidence sha256 {digest}")
        print("Next: python scripts/adr0042_canary_run.py   (POST-LOCK assertions)")
        return 0 if ev.passed() else 1


if __name__ == "__main__":
    try:
        raise SystemExit(asyncio.run(main()))
    except (BreachUnreachable, CanaryRefused) as exc:
        print(f"\n{type(exc).__name__}: {exc}", file=sys.stderr)
        raise SystemExit(2) from exc
