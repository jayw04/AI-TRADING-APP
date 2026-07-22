"""ADR 0043 Phase 0 — the governed churn driver: establish the daily-loss lock, safely.

This is NOT a second canary. Its only job is to move the account across its own daily-loss boundary
so the ENFORCE assertions in ``adr0043_canary_run`` have a real lock to assert against. It therefore
stays deliberately simpler than that harness and shares none of the A2/A3 assertion vocabulary — a
driver that imitated the formal assertions would let setup work be mistaken for evidence.

THE ORDER-LEVEL CONTRACT (the whole point of this file)
------------------------------------------------------
    submit ONE setup order
        -> settle_order (the shared barrier — no driver-local reconciliation, no sleeps)
        -> verify local/broker convergence and every account invariant
        -> re-read the account and its limits
        -> decide whether another setup order is permitted

One order in flight, ever. No batching. Attempt 2 of Phase 0 failed because a wall-clock sleep stood
where the barrier now stands, so the driver kept trading against a ledger that had not caught up.

BOUNDED BY CONSTRUCTION
-----------------------
Every dimension that could otherwise be stretched "just a bit more" to reach the breach is frozen
BEFORE the first order: the symbols, the per-order notional ceiling, the number of round trips, the
overshoot allowance, the wall-clock budget, and the effective risk limits themselves (by digest). If
the breach is not reachable inside those bounds the run ends ``BREACH_UNREACHABLE`` — it does not
size up, swap symbols, or relax a limit. Relaxing the limit to meet the account is the exact bug
ADR 0043 exists to prevent.

PROTECTED POSITIONS ARE ISOLATED IN CODE
----------------------------------------
The setup symbols are proven disjoint from MSFT and from every ``ADR0043_PROTECTED`` symbol before
the first order, not merely by operator choice. The protected quantities are snapshotted and
re-verified after every settled leg.

ONCE THE BOUNDARY TRIPS
-----------------------
The driver stops increasing risk immediately and flattens whatever setup position it opened. That
flattening SELL goes through the ordinary risk engine and is permitted only if the engine itself
classifies it as a verified reduction — there is no churn bypass, because a bypass here would be the
same class of hole ADR 0042 closed.

⚠ RUNTIME IS AWS. This runs on the box against the live paper acct-3 rig. The offline tests
(``test_adr0043_churn_driver``) are the half that proves it cannot lie, without touching a broker.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal as D
from pathlib import Path
from typing import Any

from app.db.enums import OrderSide, OrderSourceType, OrderType, TimeInForce
from app.risk import OrderRequest
from scripts.adr0043_canary_lib import (
    ACCT,
    CHURN_SYMBOLS,
    LEGS,
    PROTECTED,
    STATE_NORMAL,
    STATE_REDUCTION_ONLY_DAILY_LOSS,
    USER,
    BreachUnreachable,
    CanaryRefused,
    CanaryStop,
    Evidence,
    GovernedSubmitter,
    Limits,
    SingleInstance,
    admissible_shares,
    broker_position_qty,
    control_events_for,
    count_open_orders,
    find_order_by_client_id,
    held_reservation_count,
    limits_fingerprint,
    load_limits,
    local_position_qty,
    order_fill_summary,
    order_identity_matches,
    snapshot_state,
)

OUT = Path(os.environ.get("ADR0043_CHURN_EVIDENCE", "/app/data/adr0043_churn_evidence.json"))
CHECKPOINT = Path(
    os.environ.get("ADR0043_CHURN_CHECKPOINT", "/app/data/adr0043_churn_state.json"))

# Symbols that may NEVER be churned, whatever the environment says. MSFT is named explicitly rather
# than only derived from PROTECTED: the protected list is configuration, and configuration is
# exactly what a tired operator edits at 3pm.
NEVER_CHURN: frozenset[str] = frozenset({"MSFT"}) | {s.upper() for s in PROTECTED} | {
    s.upper() for s, _ in LEGS
}

# ---------------------------------------------------------------------------- frozen bounds
DEFAULT_MAX_ROUND_TRIPS = int(os.environ.get("ADR0043_CHURN_MAX_ROUND_TRIPS", "12"))
DEFAULT_MAX_SETUP_NOTIONAL = D(os.environ.get("ADR0043_CHURN_MAX_SETUP_NOTIONAL", "25000"))
DEFAULT_MAX_OVERSHOOT = D(os.environ.get("ADR0043_CHURN_MAX_OVERSHOOT", "750"))
DEFAULT_MAX_WALL_CLOCK_S = float(os.environ.get("ADR0043_CHURN_MAX_WALL_CLOCK_S", "5400"))


@dataclass(frozen=True)
class ChurnBounds:
    """Frozen before the first order and never recomputed. Each field is a way the run could
    otherwise creep toward the breach instead of reaching it inside a budget."""

    target_loss: D                  # the account's OWN max_daily_loss — read, never chosen
    max_overshoot: D = DEFAULT_MAX_OVERSHOOT
    max_round_trips: int = DEFAULT_MAX_ROUND_TRIPS
    max_setup_notional: D = DEFAULT_MAX_SETUP_NOTIONAL
    max_wall_clock_s: float = DEFAULT_MAX_WALL_CLOCK_S

    def as_dict(self) -> dict[str, Any]:
        return {
            "target_loss": str(self.target_loss),
            "max_overshoot": str(self.max_overshoot),
            "max_round_trips": self.max_round_trips,
            "max_setup_notional": str(self.max_setup_notional),
            "max_wall_clock_s": self.max_wall_clock_s,
        }


@dataclass(frozen=True)
class FrozenPlan:
    """Everything the run is allowed to do, decided once. A plan that can be edited mid-run is not
    a bound; it is a suggestion."""

    symbols: tuple[str, ...]
    bounds: ChurnBounds
    limits_fp: str
    protected_qty: dict[str, str]
    started_at: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "symbols": list(self.symbols),
            "bounds": self.bounds.as_dict(),
            "limits_fingerprint": self.limits_fp,
            "protected_qty": dict(self.protected_qty),
            "started_at": self.started_at,
        }


@dataclass(frozen=True)
class Leg:
    index: int
    side: str          # "BUY" | "SELL"
    symbol: str
    qty: D

    @property
    def order_side(self) -> OrderSide:
        return OrderSide.BUY if self.side == "BUY" else OrderSide.SELL


# ---------------------------------------------------------------------------- checkpoint
@dataclass
class ChurnCheckpoint:
    """Leg-indexed and durable. A restart may never re-issue a leg that already happened, and may
    never claim a leg happened without the durable order to prove it."""

    run_id: str = ""
    plan: dict | None = None
    legs: dict[str, Any] = field(default_factory=dict)
    outcome: dict | None = None

    @classmethod
    def load(cls) -> ChurnCheckpoint:
        if CHECKPOINT.exists():
            return cls(**json.loads(CHECKPOINT.read_text(encoding="utf-8")))
        cp = cls(run_id=datetime.now(UTC).strftime("%Y%m%d%H%M%S"))
        cp.save()
        return cp

    def save(self) -> None:
        CHECKPOINT.parent.mkdir(parents=True, exist_ok=True)
        tmp = CHECKPOINT.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.__dict__, indent=2, default=str), encoding="utf-8")
        tmp.replace(CHECKPOINT)

    def client_id(self, index: int) -> str:
        return f"adr0043-churn-{self.run_id}-l{index}"

    def leg_done(self, index: int) -> bool:
        return bool(self.legs.get(f"L{index}", {}).get("done"))

    def leg_data(self, index: int) -> dict:
        return dict(self.legs.get(f"L{index}", {}))

    def record_leg_intent(self, leg: Leg, **data: Any) -> None:
        self.legs[f"L{leg.index}"] = {
            "index": leg.index, "side": leg.side, "symbol": leg.symbol, "qty": str(leg.qty),
            **data, "done": False, "intent_at": datetime.now(UTC).isoformat(),
        }
        self.save()

    def record_leg(self, index: int, /, **data: Any) -> None:
        # Positional-only ``index`` so a leg record may itself carry an "index" field.
        self.legs[f"L{index}"] = {**self.legs.get(f"L{index}", {}), **data, "done": True,
                                  "at": datetime.now(UTC).isoformat()}
        self.save()

    def next_index(self) -> int:
        return len(self.legs)


# ---------------------------------------------------------------------------- PURE gates
def assess_churn_leg(
    *, local_status: str | None, fill_count: int, booked_qty: D, ordered_qty: D,
    local_position: D, broker_position: D, held_reservations: int, open_broker_orders: int,
    loss_control_state: str | None, allowed_states: tuple[str, ...],
    breaker_tripped: bool, breaker_trip_allowed: bool,
    limits_fp: str, frozen_limits_fp: str,
    protected_now: dict[str, D], protected_frozen: dict[str, D],
) -> tuple[bool, list[str]]:
    """Every condition that must hold after a settled leg, evaluated as a LIST of violations rather
    than a single boolean — when the driver stops, the operator needs to know which invariant broke,
    not merely that one did.

    Pure, so the offline tests can prove each violation independently stops the run."""
    v: list[str] = []
    if str(local_status).lower() != "filled":
        v.append(f"previous order not terminally FILLED (status={local_status})")
    if fill_count < 1 or booked_qty != ordered_qty:
        # A partial that the broker then cancelled leaves booked < ordered. The driver must never
        # advance on it: the position it is about to reason about is not the position it asked for.
        v.append(f"leg not fully filled: booked {booked_qty} of {ordered_qty} in {fill_count} fill(s)")
    if local_position != broker_position:
        v.append(f"local position {local_position} != broker {broker_position}")
    if held_reservations:
        v.append(f"{held_reservations} HELD reservation(s) outstanding")
    if open_broker_orders:
        v.append(f"{open_broker_orders} unexpected open broker order(s)")
    if loss_control_state not in allowed_states:
        v.append(f"loss-control state {loss_control_state} not in {list(allowed_states)}")
    if breaker_tripped and not breaker_trip_allowed:
        # Before the daily-loss boundary is crossed the breaker must be CLEAR: a trip here is by
        # definition some other cause, and the driver has no business churning through it. After the
        # boundary a trip is tolerated because the same daily-loss event may legitimately set it —
        # tolerated, not required, since the ADR-0043 lock does not depend on the legacy breaker.
        v.append("circuit breaker tripped for a cause other than the daily-loss boundary")
    if limits_fp != frozen_limits_fp:
        v.append(f"effective limits changed mid-run ({frozen_limits_fp} -> {limits_fp})")
    for sym, frozen in protected_frozen.items():
        now = protected_now.get(sym, D(0))
        if now != frozen:
            v.append(f"protected {sym} moved {frozen} -> {now}")
    return (not v), v


def assess_phase0_ready(
    *, day_change: D, max_daily_loss: D, loss_control_state: str | None, trip_cause: str | None,
    protected_ok: bool, setup_positions: dict[str, D], open_orders: int, held_reservations: int,
) -> tuple[bool, str]:
    """Phase 0 is COMPLETE only on durable observation of the whole end state.

    "Enough churn was submitted" is not the success condition and never was — the canary needs a
    lock that actually exists, with the protected leg intact and nothing left in flight."""
    residual = {s: q for s, q in setup_positions.items() if q != 0}
    ok = (
        day_change <= -max_daily_loss
        and loss_control_state == STATE_REDUCTION_ONLY_DAILY_LOSS
        and (trip_cause or "").upper().find("DAILY_LOSS") >= 0
        and protected_ok
        and not residual
        and open_orders == 0
        and held_reservations == 0
    )
    return ok, (
        f"day_change={day_change} vs cap {max_daily_loss} state={loss_control_state} "
        f"trip_cause={trip_cause} protected_ok={protected_ok} residual_setup={residual or '{}'} "
        f"open_orders={open_orders} held_reservations={held_reservations}"
    )


def validate_symbols(symbols: tuple[str, ...]) -> tuple[str, ...]:
    """Enforce protected-symbol disjointness IN CODE, before anything is submitted."""
    upper = tuple(s.strip().upper() for s in symbols if s.strip())
    if not upper:
        raise CanaryRefused("no churn symbols configured; the driver has nothing safe to trade")
    overlap = sorted(set(upper) & NEVER_CHURN)
    if overlap:
        raise CanaryRefused(
            f"churn symbols {overlap} overlap protected/leg symbols {sorted(NEVER_CHURN)}. The "
            f"driver refuses to churn a position the canary's assertions depend on."
        )
    if len(set(upper)) != len(upper):
        raise CanaryRefused(f"duplicate churn symbols configured: {upper}")
    return upper


# ---------------------------------------------------------------------------- the driver
class ChurnDriver:
    """Single-order, synchronous, bounded, fail-closed. Collaborators are injected so the offline
    tests drive the real sequencing without a broker."""

    def __init__(self, *, sf, adapter, router, evidence: Evidence, checkpoint: ChurnCheckpoint,
                 consumer=None, settle=None, price_fn=None, bounds: ChurnBounds | None = None,
                 symbols: tuple[str, ...] | None = None):
        self.sf = sf
        self.ad = adapter
        self.router = router
        self.ev = evidence
        self.cp = checkpoint
        self.consumer = consumer
        # The SHARED seam, which pairs every submit with the SHARED barrier. No driver-local
        # reconciliation path exists — one implementation of "is this order settled?", repo-wide.
        self.sub = GovernedSubmitter(
            sf=sf, adapter=adapter, router=router, consumer=consumer, evidence=evidence,
            settle=settle)
        self._price_fn = price_fn
        self._bounds = bounds
        self._symbols = symbols
        self.plan: FrozenPlan | None = None
        self._t0 = time.monotonic()

    # ---- pricing (never synthetic) ------------------------------------------------------
    async def price_of(self, symbol: str) -> D | None:
        if self._price_fn is not None:
            return await self._price_fn(symbol)
        for p in self.ad.get_positions() or []:
            if str(p.get("symbol")).upper() == symbol.upper():
                qty, mv = D(str(p.get("qty") or 0)), D(str(p.get("market_value") or 0))
                if qty and mv:
                    return (mv / abs(qty)).quantize(D("0.01"))
        return None

    # ---- preflight: freeze the plan -----------------------------------------------------
    async def preflight(self) -> FrozenPlan:
        symbols = validate_symbols(self._symbols or CHURN_SYMBOLS)
        limits = await load_limits(self.sf)
        if limits.max_daily_loss is None or limits.max_daily_loss <= 0:
            raise CanaryRefused(
                "no positive max_daily_loss on the account; there is no boundary to establish")
        pre = await snapshot_state(self.sf, self.ad)
        if pre.loss_control_state not in (None, STATE_NORMAL):
            raise CanaryRefused(
                f"account is already in loss-control state {pre.loss_control_state}; Phase 0 "
                f"establishes a lock, it does not run inside one")
        if pre.open_orders:
            raise CanaryRefused(f"{pre.open_orders} open broker order(s) before the first leg")
        if await held_reservation_count(self.sf):
            raise CanaryRefused("HELD reservation(s) outstanding before the first leg")
        residual = {s: pre.positions.get(s, D(0)) for s in symbols if pre.positions.get(s, D(0))}
        if residual:
            raise CanaryRefused(
                f"setup symbols are not flat before the run: {residual}; a churn run must start "
                f"from zero temporary exposure or its arithmetic means nothing")

        plan = FrozenPlan(
            symbols=symbols,
            bounds=self._bounds or ChurnBounds(target_loss=limits.max_daily_loss),
            limits_fp=limits_fingerprint(limits),
            protected_qty={s: str(pre.positions.get(s, D(0))) for s in sorted(NEVER_CHURN)},
            started_at=datetime.now(UTC).isoformat(),
        )
        self.plan = plan
        self.cp.plan = plan.as_dict()
        self.cp.save()
        self.ev.doc["churn_plan"] = plan.as_dict()
        self.ev.doc["risk_limits"] = limits.as_dict()
        return plan

    # ---- one leg: submit -> settle -> verify ---------------------------------------------
    async def run_leg(self, leg: Leg, limits: Limits) -> dict:
        assert self.plan is not None
        cid = self.cp.client_id(leg.index)
        pre_local = await local_position_qty(self.sf, leg.symbol)
        pre_broker = broker_position_qty(self.ad, leg.symbol)

        existing = await find_order_by_client_id(self.sf, self.ad, cid)
        if existing is not None:
            # Re-entry. The leg already happened; rebind rather than repeat it. A checkpoint alone
            # is not proof — the ORDER is, which is why the lookup is by durable client id.
            if not order_identity_matches(existing, side=leg.side, symbol=leg.symbol, qty=leg.qty):
                raise CanaryStop(
                    "CHURN_LEG_IDENTITY_CONFLICT",
                    f"leg {leg.index} id {cid} exists with contradicting fields {existing}")
            if existing.get("local_id") is None:
                raise CanaryStop(
                    "CHURN_LEG_LOCAL_MISSING",
                    f"leg {leg.index} exists at the broker with no local order row")
            order_id = int(existing["local_id"])
            # Rebound rather than submitted, so the seam did not settle it — settle it here. Same
            # barrier, same evidence; only the submit is absent.
            settlement = await self.settle(leg, order_id=order_id)
        else:
            if self.cp.leg_done(leg.index):
                raise CanaryStop(
                    "CHURN_LEG_UNPROVEN",
                    f"checkpoint claims leg {leg.index} completed but no order carries {cid}; "
                    f"refusing to trust a checkpoint the ledger does not corroborate")
            self.cp.record_leg_intent(leg, client_order_id=cid, pre_local=str(pre_local),
                                      pre_broker=str(pre_broker))
            price = await self.price_of(leg.symbol)
            # Submit and settle are ONE decision: the seam cannot return an unsettled order that
            # reached the broker, so there is no state in which the driver advances without one.
            governed = await self.sub.submit_and_settle(
                step=f"CHURN.L{leg.index}",
                request={"symbol": leg.symbol, "side": leg.side, "qty": str(leg.qty),
                         "client_order_id": cid},
                order_req=OrderRequest(
                    user_id=USER, account_id=ACCT, symbol_ticker=leg.symbol, side=leg.order_side,
                    qty=leg.qty, type=OrderType.MARKET, tif=TimeInForce.DAY,
                    source_type=OrderSourceType.STRATEGY, client_order_id=cid,
                    reference_price=price,
                ),
                ticker=leg.symbol)
            order_id = governed.order_id
            if not governed.admitted or order_id is None:
                # A refused setup order is not a failure of the driver — but it IS the end of the
                # road, because the next decision would rest on an order that never happened.
                raise CanaryStop(
                    "CHURN_LEG_REJECTED",
                    f"leg {leg.index} {leg.side} {leg.qty} {leg.symbol} was refused "
                    f"(status={governed.status} "
                    f"reason={getattr(governed.order, 'rejection_reason', None)})")
            settlement = _Settled(governed.settlement, governed.elapsed_s or 0.0)

        booked = await order_fill_summary(self.sf, order_id)
        record = {
            "index": leg.index, "side": leg.side, "symbol": leg.symbol,
            "ordered_qty": str(leg.qty), "client_order_id": cid,
            "local_order_id": order_id, "broker_order_id": booked["broker_order_id"],
            "broker_status": settlement.broker_status, "local_status": booked["status"],
            "booked_qty": str(booked["filled_qty"]),
            "avg_price": str(booked["avg_price"]) if booked["avg_price"] is not None else None,
            "pre_local_position": str(pre_local), "pre_broker_position": str(pre_broker),
            "post_local_position": str(settlement.local_position),
            "post_broker_position": str(settlement.broker_position),
            "reservation_states": await self._reservations(order_id),
            "settlement_elapsed_s": settlement.elapsed_s,
            "polls": settlement.polls,
        }
        self.cp.record_leg(leg.index, **record)
        self.ev.doc.setdefault("legs", []).append(record)
        await self.verify_after(leg, booked, limits)
        return record

    async def _reservations(self, order_id: int) -> list[str]:
        from scripts.adr0043_canary_lib import reservation_states_for
        return await reservation_states_for(self.sf, order_id)

    async def settle(self, leg: Leg, *, order_id: int):
        """THE BARRIER for a leg this call did not just submit (the re-entry / rebind path). Legs
        the driver submits itself are settled inside the governed seam."""
        result, elapsed = await self.sub.settle_existing(
            step=f"CHURN.L{leg.index}", order_id=order_id, ticker=leg.symbol)
        return _Settled(result, elapsed)

    async def verify_after(self, leg: Leg, booked: dict, limits: Limits) -> None:
        """Every invariant, after every leg. A violation stops the run BEFORE the next submit."""
        assert self.plan is not None
        snap = await snapshot_state(self.sf, self.ad)
        # Before the boundary trips the account must stay NORMAL; after it trips, reduction-only is
        # the expected state and the breaker may legitimately be set by the same trip.
        breached = snap.day_change <= -self.plan.bounds.target_loss
        allowed = ((STATE_NORMAL, None) if not breached
                   else (STATE_NORMAL, STATE_REDUCTION_ONLY_DAILY_LOSS, None))
        ok, violations = assess_churn_leg(
            local_status=booked["status"], fill_count=booked["fill_count"],
            booked_qty=booked["filled_qty"], ordered_qty=leg.qty,
            local_position=await local_position_qty(self.sf, leg.symbol),
            broker_position=broker_position_qty(self.ad, leg.symbol),
            held_reservations=await held_reservation_count(self.sf),
            open_broker_orders=count_open_orders(self.ad),
            loss_control_state=snap.loss_control_state, allowed_states=allowed,
            breaker_tripped=bool(snap.breaker_tripped_at), breaker_trip_allowed=breached,
            limits_fp=limits_fingerprint(await load_limits(self.sf)),
            frozen_limits_fp=self.plan.limits_fp,
            protected_now={s: snap.positions.get(s, D(0)) for s in self.plan.protected_qty},
            protected_frozen={s: D(q) for s, q in self.plan.protected_qty.items()},
        )
        if not ok:
            raise CanaryStop(
                "CHURN_INVARIANT_VIOLATED",
                f"after leg {leg.index} ({leg.side} {leg.qty} {leg.symbol}): " + "; ".join(violations),
                {"leg": leg.index, "violations": violations})

    # ---- the run ------------------------------------------------------------------------
    async def run(self) -> dict:
        plan = await self.preflight()
        limits = await load_limits(self.sf)
        symbol = plan.symbols[0]
        round_trips = 0
        open_qty = D(0)

        while True:
            snap = await snapshot_state(self.sf, self.ad)
            if snap.day_change <= -plan.bounds.target_loss:
                break                                    # boundary reached — stop increasing risk
            if snap.day_change <= -(plan.bounds.target_loss + plan.bounds.max_overshoot):
                raise CanaryStop(
                    "CHURN_OVERSHOT",
                    f"day_change {snap.day_change} exceeded the frozen overshoot allowance "
                    f"({plan.bounds.target_loss} + {plan.bounds.max_overshoot})")
            if round_trips >= plan.bounds.max_round_trips:
                raise BreachUnreachable(
                    f"BREACH_UNREACHABLE: {round_trips} round trip(s) of {symbol} did not reach "
                    f"-{plan.bounds.target_loss} (day_change={snap.day_change}); the frozen bounds "
                    f"do not permit more. Do NOT relax a limit to close the gap.")
            if time.monotonic() - self._t0 >= plan.bounds.max_wall_clock_s:
                raise BreachUnreachable(
                    f"BREACH_UNREACHABLE: wall-clock budget {plan.bounds.max_wall_clock_s}s spent "
                    f"at day_change={snap.day_change}")

            price = await self.price_of(symbol)
            if price is None or price <= 0:
                raise CanaryRefused(
                    f"no live price for {symbol}; refusing to size an order against a synthetic "
                    f"price (the 2026-07-16 defect)")
            qty = admissible_shares(
                price=price, limits=limits, gross_used=D(0),
                buying_power=D(str((self.ad.get_account() or {}).get("buying_power") or 0)),
                ceiling=plan.bounds.max_setup_notional)
            if qty <= 0:
                raise BreachUnreachable(
                    f"BREACH_UNREACHABLE: the account's own limits admit 0 shares of {symbol} at "
                    f"{price}; sizing up is not an option")

            buy = Leg(self.cp.next_index(), "BUY", symbol, qty)
            await self.run_leg(buy, limits)
            open_qty = qty
            # The closing leg is RISK-REDUCING and runs immediately, whether or not the buy just
            # crossed the boundary — leaving setup exposure open to "check the state first" is how
            # a driver ends up holding an unplanned position through a lock.
            await self.flatten(symbol, open_qty, limits)
            open_qty = D(0)
            round_trips += 1

        return await self.finish(plan, symbol, open_qty, round_trips)

    async def flatten(self, symbol: str, qty: D, limits: Limits) -> None:
        """Close a setup position through the ORDINARY risk path.

        The engine must classify this as a verified reduction on its own merits; there is no churn
        bypass, because a bypass here would re-open the hole ADR 0042 closed. If the engine refuses,
        that is a reportable end state with the residual quantity attached — not something to retry
        around."""
        leg = Leg(self.cp.next_index(), "SELL", symbol, qty)
        try:
            await self.run_leg(leg, limits)
        except CanaryStop as stop:
            if stop.stop_reason == "SETTLEMENT_BARRIER_FAILED":
                raise                       # already the most specific description of the failure
            residual_local = await local_position_qty(self.sf, symbol)
            raise CanaryStop(
                "CHURN_RESIDUAL_POSITION",
                f"setup position {symbol} could not be flattened ({stop.stop_reason}: "
                f"{stop.detail}); {residual_local} share(s) remain open",
                {"symbol": symbol, "residual_local": str(residual_local),
                 "residual_broker": str(broker_position_qty(self.ad, symbol)),
                 "underlying": stop.stop_reason}) from stop

    async def finish(self, plan: FrozenPlan, symbol: str, open_qty: D, round_trips: int) -> dict:
        """The boundary tripped. Flatten any setup position through the ORDINARY risk path, then
        prove the whole Phase-0 end state — do not declare readiness from the loss figure alone."""
        if open_qty > 0:
            await self.flatten(symbol, open_qty, await load_limits(self.sf))

        snap = await snapshot_state(self.sf, self.ad)
        events = await control_events_for(self.sf)
        trips = [e for e in events if e.get("to_state") == STATE_REDUCTION_ONLY_DAILY_LOSS]
        trip_cause = str(trips[-1].get("trip_type") or trips[-1].get("trip_cause")) if trips else None
        limits = await load_limits(self.sf)
        protected_ok = all(
            snap.positions.get(s, D(0)) == D(q) for s, q in plan.protected_qty.items())
        ok, detail = assess_phase0_ready(
            day_change=snap.day_change,
            max_daily_loss=limits.max_daily_loss or plan.bounds.target_loss,
            loss_control_state=snap.loss_control_state, trip_cause=trip_cause,
            protected_ok=protected_ok,
            setup_positions={s: snap.positions.get(s, D(0)) for s in plan.symbols},
            open_orders=count_open_orders(self.ad),
            held_reservations=await held_reservation_count(self.sf))
        self.ev.assert_("PHASE0.lock_established", ok, detail)
        outcome = {
            "ready": ok, "detail": detail, "round_trips": round_trips,
            "trip_cause": trip_cause, "day_change": str(snap.day_change),
            "loss_control_state": snap.loss_control_state,
            "elapsed_s": round(time.monotonic() - self._t0, 3),
        }
        self.cp.outcome = outcome
        self.cp.save()
        self.ev.doc["outcome"] = outcome
        return outcome


@dataclass(frozen=True)
class _Settled:
    """The barrier's result plus the driver's own elapsed measurement."""

    result: Any
    elapsed_s: float

    @property
    def broker_status(self) -> str:
        return self.result.broker_status

    @property
    def local_position(self) -> D:
        return self.result.local_position

    @property
    def broker_position(self) -> D:
        return self.result.broker_position

    @property
    def polls(self) -> int:
        return self.result.polls


# ---------------------------------------------------------------------------- entrypoint
async def _run() -> int:
    from app.brokers.registry import BrokerRegistry
    from app.db.session import get_sessionmaker
    from app.events.bus import EventBus
    from app.orders.lifecycle import TradeUpdateConsumer
    from app.orders.positions import PositionRecomputer
    from app.orders.router import OrderRouter
    from app.risk import RiskEngine

    sf = get_sessionmaker()
    ev = Evidence(phase="PHASE0_CHURN")
    cp = ChurnCheckpoint.load()
    registry = BrokerRegistry(sf)
    await registry.load_all()
    ad = registry.get(USER)
    bus = EventBus()
    # NOT started — the driver drives the canonical handler synchronously through the barrier.
    consumer = TradeUpdateConsumer(sf, bus, PositionRecomputer(sf, bus))
    router = OrderRouter(
        ad, RiskEngine(sf, broker_registry=registry, bus=bus), sf, bus, broker_registry=registry)
    driver = ChurnDriver(sf=sf, adapter=ad, router=router, evidence=ev, checkpoint=cp,
                         consumer=consumer)
    try:
        outcome = await driver.run()
    except CanaryStop as stop:
        ev.record_stop(stop.stop_reason, stop.detail, stop.diagnostics)
        digest = ev.write(OUT)
        print(f"STOP [{stop.stop_reason}]: {stop.detail}\n  evidence {OUT} sha256={digest}",
              flush=True)
        return 3
    except BreachUnreachable as exc:
        ev.assert_("PHASE0.lock_established", False, str(exc))
        ev.record_stop("BREACH_UNREACHABLE", str(exc), {})
        digest = ev.write(OUT)
        print(f"{exc}\n  evidence {OUT} sha256={digest}", flush=True)
        return 4
    digest = ev.write(OUT)
    print(f"Phase 0 churn {'READY' if outcome['ready'] else 'NOT READY'} — "
          f"evidence {OUT} sha256={digest}", flush=True)
    return 0 if outcome["ready"] else 1


def main() -> int:
    try:
        with SingleInstance():
            return asyncio.run(_run())
    except CanaryRefused as exc:
        print(f"REFUSED: {exc}", flush=True)
        return 2


if __name__ == "__main__":
    sys.exit(main())
