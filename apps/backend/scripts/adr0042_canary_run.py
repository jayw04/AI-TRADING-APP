"""ADR 0042 canary — POST-LOCK phase: the assertion sequence, run exactly once.

Preconditions, REFUSED rather than worked around:
  * the account must be genuinely locked (measured, not assumed);
  * the protected legs must be present — a locked account cannot buy, so if the legs are gone the
    assertions cannot run and any RED would say nothing about the risk engine.

Every order records a PRE-ORDER SNAPSHOT (day_change, max_daily_loss, lock state, breaker state,
positions) so no assertion rests on an assumption about the account's condition. Every rejection is
verified to have left an immutable ledger record.

⚠ THE CONCURRENCY ASSERTION USES TWO OS PROCESSES. The previous version used `asyncio.gather` in
one process, where the per-account `asyncio.Lock` serialised the callers — so it PASSED while the
cross-process hole stayed open, which is how two ALLOW decisions came to consume the same 183
shares with only the broker stopping the second. A broker rejection is NOT the safety mechanism and
may never be counted as one.
"""

from __future__ import annotations

import asyncio
import json
import subprocess
import sys
import time
from decimal import Decimal as D
from pathlib import Path

from sqlalchemy import text

from app.brokers.registry import BrokerRegistry
from app.db.enums import OrderSide, OrderSourceType, OrderType, TimeInForce
from app.db.session import get_sessionmaker
from app.events.bus import EventBus
from app.orders.router import CancelRejectedByRisk, OrderRouter
from app.risk import OrderRequest, RiskEngine
from scripts.adr0042_canary_lib import (
    ACCT,
    LEGS,
    USER,
    CanaryRefused,
    Checkpoint,
    Evidence,
    SingleInstance,
    _count_open,
    ledger_rows_for,
    load_limits,
    max_ledger_id,
    snapshot_state,
)

OUT = Path("/app/data/adr0042_evidence_post_lock.json")
WORK = Path("/app/data")
LEG = LEGS[0][0]                      # the reduction target (F)
LEG2 = LEGS[1][0] if len(LEGS) > 1 else LEGS[0][0]


def mk(sym, side, qty, src=OrderSourceType.STRATEGY, **kw) -> OrderRequest:
    return OrderRequest(
        user_id=USER, account_id=ACCT, symbol_ticker=sym, side=side, qty=qty,
        type=kw.pop("type", OrderType.MARKET), tif=TimeInForce.DAY, source_type=src, **kw,
    )


def _sent(o) -> bool:
    return str(getattr(o, "status", "")).endswith("submitted")


def _rejected(o) -> bool:
    return str(getattr(o, "status", "")).endswith("rejected")


async def _submit(router, ev, sf, ad, step, request, order_req):
    """Every order: snapshot the state first, record request and response, return both."""
    pre = await snapshot_state(sf, ad)
    o = await router.submit(order_req)
    ev.record_order(step=step, snapshot=pre, request=request, response=o)
    return o, pre


async def _audit_trail_for(sf, since: int, ev, step: str) -> list[dict]:
    """§ audit — a rejected order must leave an immutable record. Debugging a refusal that left no
    trace is the situation the ledger exists to prevent."""
    rows = await ledger_rows_for(sf, since_id=since)
    ok = bool(rows) and all(
        r["risk_policy_version"] and r["decision"] and r["reason_codes"] and r["decided_at"]
        for r in rows
    )
    ev.assert_(
        f"{step}.audit_trail",
        ok,
        f"{len(rows)} ledger row(s): "
        + ", ".join(f"#{r['id']} {r['decision']}/{r['risk_effect']} {r['reason_codes']}"
                    for r in rows[:4]),
    )
    return rows


async def _max_risk_check_id(sf) -> int:
    async with sf() as s:
        return int((await s.execute(text("SELECT COALESCE(MAX(id), 0) FROM risk_checks"))).scalar())


async def _risk_check_rows_for(sf, since_id: int) -> list[dict]:
    """The pre-ADR-0042 gate trail.

    ⚠ `risk_checks` carries no account_id, and a REJECTED order has order_id = NULL, so these rows
    cannot be scoped to account 3 by column. They are scoped by id > since_id instead, which is
    sound here ONLY because the canary is the sole writer during the assertion sequence. This is
    recorded rather than hidden: it is a property of the run, not of the schema.
    """
    async with sf() as s:
        rows = (await s.execute(
            text("SELECT id, order_id, decision, reason_codes, evaluated_at FROM risk_checks "
                 "WHERE id > :i ORDER BY id"),
            {"i": since_id},
        )).mappings().all()
    return [dict(r) for r in rows]


async def _refusal_is_auditable(sf, since_ledger: int, since_rc: int, ev, step: str) -> None:
    """A refusal must be traceable — in ADR-0042's ledger, or in the upstream gate trail."""
    ledger = await ledger_rows_for(sf, since_id=since_ledger)
    checks = await _risk_check_rows_for(sf, since_rc)
    rejects = [r for r in checks if str(r["decision"]).upper().startswith("REJECT")
               and r["reason_codes"]]
    ok = bool(ledger) or bool(rejects)
    where = ("adr0042_ledger" if ledger else "risk_checks" if rejects else "NOWHERE")
    ev.assert_(
        f"{step}.refusal_is_auditable", ok,
        f"recorded in {where}: "
        + ", ".join(f"#{r['id']} {r['decision']}/{r['risk_effect']} {r['reason_codes']}"
                    for r in ledger[:3])
        + ", ".join(f"#{r['id']} {r['decision']} {r['reason_codes']}" for r in rejects[:3]),
    )
    ev.doc.setdefault("refusal_gates", {})[step] = {
        "adr0042_ledger_rows": len(ledger),
        "upstream_risk_check_rejects": [
            {"id": r["id"], "reason_codes": r["reason_codes"]} for r in rejects[:4]],
        "refused_by": where,
    }


def _mark_price(ad, symbol: str) -> D | None:
    """The live mark, from the position the canary already holds (market_value / qty).

    Deliberately NOT a hard-coded constant: a synthetic price is what broke assertion 5. Taken from
    the broker's own valuation of the position, so the notional the cap will compute is the notional
    we reasoned about.
    """
    for p in ad.get_positions() or []:
        if p["symbol"] != symbol:
            continue
        qty = D(str(p.get("qty") or 0))
        mv = D(str(p.get("market_value") or 0))
        if qty > 0 and mv > 0:
            return (mv / qty).quantize(D("0.01"))
    return None


async def _settle_open_orders(ad, ev, step: str, budget_s: float = 90.0) -> bool:
    """Wait until nothing is in flight at the broker, bounded.

    2026-07-16: assertion 2's own SELL 50 was still working when the race began, so reducible was
    450 - 50 = 400 while the workers each asked for the raw 450 position. Both were refused by the
    QUANTITY gate (EXCEEDS_REDUCIBLE_QUANTITY) before the cross-process CAPACITY claim was ever
    reached — the load-bearing test silently measured nothing, and reported FAIL for a reason that
    had nothing to do with the property. The engine was right to refuse: you cannot sell shares you
    have already committed to selling.

    Settling first makes reducible == the position, so a request for the whole position is
    individually satisfiable and jointly contended — which is the race the assertion exists to run.
    """
    t0 = time.time()
    n = _count_open(ad)
    while n and time.time() - t0 < budget_s:
        await asyncio.sleep(2.0)
        n = _count_open(ad)
    ok = n == 0
    ev.assert_(f"{step}.settled_before_race", ok,
               f"{n} order(s) still open after {time.time()-t0:.0f}s — a race against in-flight "
               f"capacity would refuse both workers on QUANTITY and never test the CAPACITY claim")
    return ok


async def _concurrency_assertion(sf, ad, ev) -> None:
    """TWO REAL PROCESSES. Exactly one may claim the capacity."""
    # Nothing may be in flight: the workers must contend for the WHOLE position, or they are
    # refused on quantity before the capacity claim is exercised (see _settle_open_orders).
    if not await _settle_open_orders(ad, ev, "concurrency"):
        ev.assert_("concurrency.setup", False,
                   "could not reach a quiescent book; refusing to run a vacuous race")
        return

    held = next((D(str(p["qty"])) for p in ad.get_positions() if p["symbol"] == LEG), D(0))
    if held <= 0:
        ev.assert_("concurrency.setup", False, f"no {LEG} position to contend for")
        return

    before = await max_ledger_id(sf)
    barrier = time.time() + 6.0
    outs = [WORK / "adr0042_conc_a.json", WORK / "adr0042_conc_b.json"]
    for p in outs:
        p.unlink(missing_ok=True)

    procs = [
        subprocess.Popen(          # noqa: S603 — fixed argv, no shell
            [sys.executable, "scripts/adr0042_concurrency_worker.py",
             LEG, str(held), str(barrier), str(out)],
            cwd="/app",
        )
        for out in outs
    ]
    for p in procs:
        p.wait(timeout=120)

    results = [json.loads(p.read_text(encoding="utf-8")) for p in outs if p.exists()]
    ev.doc["concurrency"] = {"held": str(held), "barrier": barrier, "workers": results}

    if len(results) != 2:
        ev.assert_("concurrency.both_ran", False, f"only {len(results)} worker(s) reported")
        return
    ev.assert_(
        "concurrency.distinct_processes",
        results[0]["pid"] != results[1]["pid"],
        f"pids {results[0]['pid']} and {results[1]['pid']}",
    )
    overlap = abs(results[0]["submitted_at"] - results[1]["submitted_at"])
    ev.assert_("concurrency.actually_raced", overlap < 2.0,
               f"submissions {overlap:.3f}s apart (a non-overlapping pass would be vacuous)")

    submitted = [r for r in results if r["status"].endswith("submitted")]
    ev.assert_(
        "concurrency.exactly_one_submitted",
        len(submitted) == 1,
        f"statuses {[r['status'] for r in results]} — two submissions would mean two decisions "
        f"consumed the same reducible capacity",
    )

    rows = await ledger_rows_for(sf, since_id=before)
    allows = [r for r in rows if r["decision"] == "ALLOW"]
    ev.assert_(
        "concurrency.exactly_one_ALLOW_in_ledger",
        len(allows) == 1,
        f"{len(allows)} ALLOW row(s) of {len(rows)}: "
        + ", ".join(f"#{r['id']} {r['decision']}/{r['risk_effect']} cap_v="
                    f"{r['capacity_state_version']}" for r in rows[:4]),
    )
    refused = [r for r in rows if "EXCEEDS_REDUCIBLE_CAPACITY" in (r["reason_codes"] or "")]
    ev.assert_(
        "concurrency.loser_refused_on_capacity",
        len(refused) == 1,
        f"{len(refused)} row(s) carrying EXCEEDS_REDUCIBLE_CAPACITY — the loser must be refused "
        f"by the CLAIM, not by the broker",
    )
    ev.assert_(
        "concurrency.no_broker_backstop_needed",
        all(not (r.get("rejection_reason") or "").lower().count("insufficient")
            for r in results),
        "no broker insufficient-quantity rejection — the broker may never be the safety mechanism",
    )

    await asyncio.sleep(6)
    after = next((D(str(p["qty"])) for p in ad.get_positions() if p["symbol"] == LEG), D(0))
    ev.assert_("concurrency.never_crossed_zero", after >= 0, f"{LEG} position after = {after}")


async def main() -> int:  # noqa: PLR0915 — a linear assertion sequence reads better as one block
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
        ev = Evidence(phase="POST_LOCK")
        limits = await load_limits(sf)
        ev.doc["risk_limits"] = limits.as_dict()

        snap = await snapshot_state(sf, ad)
        ev.doc["initial"] = snap.as_dict()
        print(f"ADR 0042 canary — POST-LOCK — account {ACCT}")
        print(f"  day_change     : ${snap.day_change:,.2f}")
        print(f"  max_daily_loss : ${snap.max_daily_loss:,.2f}")
        print(f"  lock active    : {snap.lock_active}")
        print(f"  breaker        : {snap.breaker_tripped_at}")
        print(f"  positions      : { {k: str(v) for k, v in snap.positions.items()} }\n")

        # ---- preconditions: refuse rather than produce a meaningless RED --------------------
        if not snap.lock_active:
            raise CanaryRefused(
                f"the account is NOT locked (day_change ${snap.day_change:,.2f} vs cap "
                f"${snap.max_daily_loss:,.2f}). Run the PRE-LOCK phase first. The limit is NOT "
                f"to be lowered to manufacture a lock."
            )
        missing = [s for s, q in LEGS if snap.positions.get(s, D(0)) < q]
        if missing:
            raise CanaryRefused(
                f"protected legs missing while LOCKED: {missing}. A locked account cannot buy, "
                f"so the reduction assertions cannot run. This would be a structurally invalid "
                f"RED — refusing instead."
            )
        cp.phase = "ASSERTING"
        cp.save()

        # ---- 1: the lock genuinely refuses a new buy ----------------------------------------
        print("1 — a risk-INCREASING order must be rejected while locked")
        n0 = await max_ledger_id(sf)
        o, _ = await _submit(router, ev, sf, ad, "buy_rejected",
                             {"symbol": LEG, "side": "BUY", "qty": "1"},
                             mk(LEG, OrderSide.BUY, D("1")))
        ev.assert_("1.buy_rejected", _rejected(o), f"BUY 1 {LEG} -> {o.status}")
        await _audit_trail_for(sf, n0, ev, "1")

        # ---- 2: a verified reduction passes BOTH gates, breaker still tripped ----------------
        print("\n2 — a VERIFIED REDUCTION must pass the loss gate AND the breaker gate")
        n0 = await max_ledger_id(sf)
        pre = await snapshot_state(sf, ad)
        o, _ = await _submit(router, ev, sf, ad, "reduction_allowed",
                             {"symbol": LEG, "side": "SELL", "qty": "50"},
                             mk(LEG, OrderSide.SELL, D("50")))
        ev.assert_("2.reduction_allowed", _sent(o), f"SELL 50 {LEG} -> {o.status}")
        ev.assert_("2.breaker_not_reset", pre.breaker_tripped_at is not None,
                   f"the breaker was tripped at {pre.breaker_tripped_at} and was NOT reset")
        ev.assert_("2.limit_not_moved", pre.max_daily_loss == limits.max_daily_loss,
                   f"max_daily_loss still ${pre.max_daily_loss:,.2f}")
        rows = await _audit_trail_for(sf, n0, ev, "2")
        ev.assert_("2.ledger_says_verified_reduction",
                   any(r["decision"] == "ALLOW" and r["risk_effect"] == "RISK_REDUCING"
                       for r in rows),
                   "ledger records ALLOW/RISK_REDUCING")

        # ---- 3: an oversell that would cross zero is refused ---------------------------------
        print("\n3 — an oversell crossing zero must be rejected")
        n0 = await max_ledger_id(sf)
        rc0 = await _max_risk_check_id(sf)
        o, _ = await _submit(router, ev, sf, ad, "oversell_rejected",
                             {"symbol": LEG, "side": "SELL", "qty": "100000"},
                             mk(LEG, OrderSide.SELL, D("100000")))
        ev.assert_("3.oversell_rejected", _rejected(o), f"SELL 100000 {LEG} -> {o.status}")
        # An oversell is refused by SHORT_NOT_ALLOWED — a STRICTER, EARLIER gate than ADR-0042 —
        # so ADR-0042 never adjudicates it and writes no ledger row. 2026-07-16: demanding an
        # ADR-0042 row here asserted the wrong table and reported FAIL while the property itself
        # (3.oversell_rejected) PASSED. The requirement the ledger exists to enforce is that NO
        # refusal is untraceable; being caught by a stricter gate first is defence in depth, not a
        # gap. So: the refusal must be recorded WITH A REASON somewhere immutable — ADR-0042's
        # ledger or the risk_checks trail — and WHICH gate refused it is recorded as evidence.
        await _refusal_is_auditable(sf, n0, rc0, ev, "3")

        # ---- 4: TWO PROCESSES may not consume the same reducible capacity --------------------
        print("\n4 — CROSS-PROCESS: two independent processes, one capacity")
        await asyncio.sleep(5)
        await _concurrency_assertion(sf, ad, ev)

        # ---- 5: cancelling a protective sell-to-close is refused -----------------------------
        print("\n5 — cancellation is classified, not waved through")
        n0 = await max_ledger_id(sf)
        # The limit must be UNFILLABLE (so the sell rests and can be cancelled) but must still be a
        # SANE price. 2026-07-16: a hard-coded 9999 was ~20x MSFT's mark, and the position-notional
        # cap values the projected position at the ORDER's price -> 19 x 9999 ~ $190k vs the $25k
        # cap -> POSITION_CAP_NOTIONAL rejected it upstream of the ADR-0042 gate, so the protective
        # sell never rested and the cancel property was never tested. The cap was right; the
        # synthetic price was the defect. Price off the live mark instead: 1.25x is comfortably
        # unfillable for a SELL yet leaves the projected notional realistic.
        mark = _mark_price(ad, LEG2)
        if mark is None:
            ev.assert_("5.setup", False, f"no mark for {LEG2}; cannot price a sane resting limit")
            resting = None
        else:
            limit = (mark * D("1.25")).quantize(D("0.01"))
            resting, _ = await _submit(
                router, ev, sf, ad, "resting_protective_sell",
                {"symbol": LEG2, "side": "SELL", "qty": "1", "type": "LIMIT",
                 "limit": str(limit), "mark": str(mark)},
                mk(LEG2, OrderSide.SELL, D("1"), OrderSourceType.MANUAL,
                   type=OrderType.LIMIT, limit_price=limit),
            )
        if _sent(resting):
            try:
                await router.cancel(resting.id)
                ev.assert_("5.cancel_protective_refused", False,
                           "the protective sell-to-close WAS cancelled")
            except CancelRejectedByRisk as exc:
                ev.assert_("5.cancel_protective_refused", True,
                           f"refused: {', '.join(exc.reasons)}")
        else:
            ev.assert_("5.cancel_protective_refused", False,
                       f"could not rest a protective sell: "
                       f"{getattr(resting, 'status', 'not submitted')}")
        await _audit_trail_for(sf, n0, ev, "5")

        # ---- 6: source neutrality ------------------------------------------------------------
        print("\n6 — MANUAL is classified exactly like STRATEGY")
        n0 = await max_ledger_id(sf)
        o, _ = await _submit(router, ev, sf, ad, "manual_reduction",
                             {"symbol": LEG2, "side": "SELL", "qty": "1", "source": "MANUAL"},
                             mk(LEG2, OrderSide.SELL, D("1"), OrderSourceType.MANUAL))
        ev.assert_("6.manual_reduction_allowed", _sent(o), f"MANUAL SELL 1 {LEG2} -> {o.status}")
        rows = await _audit_trail_for(sf, n0, ev, "6")
        ev.assert_("6.source_recorded_not_privileged",
                   any(r["decision"] == "ALLOW" and r["risk_effect"] == "RISK_REDUCING"
                       for r in rows),
                   "a MANUAL reduction is ALLOW/RISK_REDUCING on its merits")

        # ---- final reconciliation ------------------------------------------------------------
        await asyncio.sleep(6)
        final = await snapshot_state(sf, ad)
        ev.doc["final"] = final.as_dict()
        ev.doc["ledger"] = await ledger_rows_for(sf, since_id=0)
        ev.assert_("final.no_short_position",
                   all(q >= 0 for q in final.positions.values()),
                   str({k: str(v) for k, v in final.positions.items()}))
        ev.assert_("final.limit_unchanged", final.max_daily_loss == limits.max_daily_loss,
                   f"max_daily_loss ${final.max_daily_loss:,.2f}")

        cp.phase = "DONE"
        cp.save()
        digest = ev.write(OUT)
        print("\n" + "=" * 72)
        print(f"  ADR 0042 CANARY: {'PASS' if ev.passed() else 'FAIL'}")
        print(f"  evidence: {OUT}  sha256 {digest}")
        print("=" * 72)
        return 0 if ev.passed() else 1


if __name__ == "__main__":
    try:
        raise SystemExit(asyncio.run(main()))
    except CanaryRefused as exc:
        print(f"\nCanaryRefused: {exc}", file=sys.stderr)
        raise SystemExit(2) from exc
