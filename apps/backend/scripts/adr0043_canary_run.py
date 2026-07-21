"""ADR 0043 canary — the loss-control ENFORCE assertion sequence, run against the live acct-3 rig.

Preconditions, REFUSED rather than worked around (a run that assumes them proves nothing):
  * ``WORKBENCH_LOSS_CONTROL_MODE`` must be ``ENFORCE`` — under OFF/SHADOW the machine is not
    authoritative, so no assertion here would mean anything;
  * the account must be genuinely in a durable loss-control lock (a ``REDUCTION_ONLY_*`` state read
    from ``risk_loss_control_state`` — measured, not assumed);
  * the protected legs must be present — a locked account cannot buy, so if the legs are gone the
    reduction assertion cannot run and any RED would say nothing about the engine.

The assertions (each records a PRE-ORDER SNAPSHOT of the durable state, so none rests on an
assumption about the lock, and every refusal is verified to have left an immutable event/ledger
record):
  A1 state_authoritative        — the durable state row is REDUCTION_ONLY_* (the machine, not just
                                   the breaker column, governs the account).
  A2 verified_reduction_allowed — a SELL of a protected leg (a verified risk-reducing order) is
                                   SUBMITTED under the lock (ALLOW_REDUCTION_ONLY; ADR 0042 preserved).
  A3 new_risk_refused           — a BUY (new risk) is REJECTED with LOSS_CONTROL_STOP and leaves a
                                   durable trail.
  A4 recovery_path_reachable    — the sanctioned recovery preflight can be REQUESTED and commits a
                                   real RECOVERY_REQUEST event (durable path out — never an ad-hoc
                                   force to NORMAL).
  A5 evaluator_does_not_prematurely_rearm — if the account reaches RECOVERY_COOLDOWN, the cooldown
                                   evaluator HOLDs (the §D6 dwell is not satisfied within the run);
                                   the harness NEVER fakes elapsed time to force a NORMAL.

⚠ RUNTIME IS AWS — this runs on the box, never against the laptop's local stack.
"""

from __future__ import annotations

import asyncio
import sys
from decimal import Decimal as D
from pathlib import Path

from app.brokers.registry import BrokerRegistry
from app.db.enums import OrderSide, OrderSourceType, OrderType, TimeInForce
from app.db.session import get_sessionmaker
from app.events.bus import EventBus
from app.orders.router import OrderRouter
from app.risk import OrderRequest, RiskEngine
from app.risk.loss_control.cooldown import CooldownEvaluator
from app.risk.loss_control.recovery import RecoveryPreflightService
from scripts.adr0043_canary_lib import (
    ACCT,
    LEGS,
    REDUCTION_ONLY_STATES,
    REQUIRED_LOSS_CONTROL_MODE,
    STATE_RECOVERY_COOLDOWN,
    USER,
    CanaryRefused,
    Checkpoint,
    Evidence,
    SingleInstance,
    control_events_for,
    ledger_rows_for,
    load_limits,
    loss_control_mode,
    max_control_event_id,
    max_ledger_id,
    snapshot_state,
)

OUT = Path("/app/data/adr0043_evidence_enforce.json")
LEG = LEGS[0][0]  # the reduction target


def mk(sym, side, qty, src=OrderSourceType.STRATEGY, **kw) -> OrderRequest:
    return OrderRequest(
        user_id=USER, account_id=ACCT, symbol_ticker=sym, side=side, qty=qty,
        type=kw.pop("type", OrderType.MARKET), tif=TimeInForce.DAY, source_type=src, **kw,
    )


def _submitted(o) -> bool:
    return str(getattr(o, "status", "")).endswith("submitted")


def _rejected(o) -> bool:
    return str(getattr(o, "status", "")).endswith("rejected")


def _reason(o) -> str:
    return str(getattr(o, "rejection_reason", "") or "")


async def _submit(router, ev, sf, ad, step, request, order_req):
    pre = await snapshot_state(sf, ad)
    o = await router.submit(order_req)
    ev.record_order(step=step, snapshot=pre, request=request, response=o)
    return o, pre


async def _refusal_is_auditable(sf, since_ledger, since_events, ev, step) -> None:
    """A refusal must be traceable — a loss-control control event and/or the decision ledger."""
    ledger = await ledger_rows_for(sf, since_id=since_ledger)
    events = await control_events_for(sf, since_id=since_events)
    lc_reject_ledger = [r for r in ledger if r["reason_codes"]]
    ok = bool(lc_reject_ledger) or bool(events)
    where = "decision_ledger" if lc_reject_ledger else "control_events" if events else "NOWHERE"
    ev.assert_(
        f"{step}.refusal_is_auditable", ok,
        f"recorded in {where}: "
        + ", ".join(f"#{r['id']} {r['decision']} {r['reason_codes']}" for r in lc_reject_ledger[:3]),
    )


async def run() -> int:
    sf = get_sessionmaker()
    ev = Evidence(phase="ENFORCE")
    cp = Checkpoint.load()

    # --- precondition 1: the right mode ---
    mode = await loss_control_mode(sf)
    if mode != REQUIRED_LOSS_CONTROL_MODE:
        raise CanaryRefused(
            f"WORKBENCH_LOSS_CONTROL_MODE is {mode!r}, not {REQUIRED_LOSS_CONTROL_MODE!r}. Under "
            f"OFF/SHADOW the state machine is not authoritative, so the canary would assert nothing."
        )

    registry = BrokerRegistry(sf)
    await registry.load_all()
    ad = registry.get(USER)
    ev.doc["risk_limits"] = (await load_limits(sf)).as_dict()

    # --- precondition 2: a genuine, MEASURED lock ---
    pre = await snapshot_state(sf, ad)
    ev.doc["precondition_snapshot"] = pre.as_dict()
    if not pre.reduction_only:
        raise CanaryRefused(
            f"account {ACCT} is not in a reduction-only loss-control state "
            f"(loss_control_state={pre.loss_control_state!r}). The canary asserts behaviour UNDER a "
            f"lock; it does not manufacture one by editing state."
        )
    # --- precondition 3: the legs the reduction assertion needs ---
    missing = [s for s, _ in LEGS if pre.positions.get(s, D(0)) <= 0]
    if missing:
        raise CanaryRefused(f"protected legs absent: {missing}; cannot run the reduction assertion")
    cp.lock_reached = True
    cp.save()

    bus = EventBus()
    router = OrderRouter(
        ad, RiskEngine(sf, broker_registry=registry, bus=bus), sf, bus, broker_registry=registry
    )

    # A1 — the durable state row is authoritative (not merely the breaker column).
    ev.assert_(
        "A1.state_authoritative",
        pre.loss_control_state in REDUCTION_ONLY_STATES and pre.loss_control_state_version is not None,
        f"loss_control_state={pre.loss_control_state} v{pre.loss_control_state_version}",
    )

    # A2 — a verified reduction (SELL a protected leg) is ALLOWED under the lock.
    o, _ = await _submit(
        router, ev, sf, ad, "A2.reduce",
        {"symbol": LEG, "side": "sell", "qty": "1", "kind": "verified_reduction"},
        mk(LEG, OrderSide.SELL, D("1")),
    )
    ev.assert_("A2.verified_reduction_allowed", _submitted(o),
               f"SELL 1 {LEG} status={getattr(o, 'status', o)} reason={_reason(o)}")

    # A3 — new risk (BUY) is REFUSED, with a durable trail.
    since_l, since_e = await max_ledger_id(sf), await max_control_event_id(sf)
    o, _ = await _submit(
        router, ev, sf, ad, "A3.new_risk",
        {"symbol": LEG, "side": "buy", "qty": "1", "kind": "new_risk"},
        mk(LEG, OrderSide.BUY, D("1")),
    )
    reason = _reason(o)
    ev.assert_("A3.new_risk_refused", _rejected(o) and "LOSS_CONTROL_STOP" in reason,
               f"BUY 1 {LEG} status={getattr(o, 'status', o)} reason={reason}")
    await _refusal_is_auditable(sf, since_l, since_e, ev, "A3")

    # A4 — the sanctioned recovery path is reachable (commits a real RECOVERY_REQUEST event).
    since_e = await max_control_event_id(sf)
    svc = RecoveryPreflightService(sf)
    outcome = await svc.request_recovery(
        account_id=ACCT, account_owner_id=USER, idempotency_key=f"canary-{cp.started_at}",
        requester_user_id=USER, adapter=ad,
    )
    ev.doc["recovery_outcome"] = {
        "accepted": outcome.accepted, "status": outcome.status,
        "aggregate_verdict": outcome.aggregate_verdict, "reason": outcome.reason,
        "resulting_state": outcome.resulting_state,
    }
    post_req = await snapshot_state(sf, ad)
    events = await control_events_for(sf, since_id=since_e)
    entered_preflight_or_beyond = any(
        e["to_state"] in {"RECOVERY_PREFLIGHT", STATE_RECOVERY_COOLDOWN} for e in events
    )
    ev.assert_(
        "A4.recovery_path_reachable",
        outcome.accepted and entered_preflight_or_beyond,
        f"request status={outcome.status}; state now {post_req.loss_control_state}; "
        f"events={[e['to_state'] for e in events]}",
    )

    # A5 — if the account reached RECOVERY_COOLDOWN, the evaluator HOLDs (dwell not satisfied within
    # the run). The harness NEVER fakes elapsed time to force a NORMAL.
    if post_req.loss_control_state == STATE_RECOVERY_COOLDOWN:
        result = await CooldownEvaluator(sf).evaluate(
            ACCT, adapter=ad, velocity=None,  # no injected velocity → velocity trips fail closed
        )
        post_eval = await snapshot_state(sf, ad)
        ev.assert_(
            "A5.evaluator_does_not_prematurely_rearm",
            result.transitioned_to != "NORMAL" and post_eval.loss_control_state != "NORMAL",
            f"evaluator verdict={result.verdict} transitioned_to={result.transitioned_to}; "
            f"state still {post_eval.loss_control_state}",
        )
    else:
        ev.assert_(
            "A5.evaluator_does_not_prematurely_rearm", True,
            f"account did not reach RECOVERY_COOLDOWN (state {post_req.loss_control_state}); "
            f"no premature re-arm possible",
        )

    digest = ev.write(OUT)
    cp.phase = "DONE"
    cp.note("complete", gate=ev.doc["gate"], digest=digest)
    print(f"\nADR 0043 canary {ev.doc['gate']} — evidence {OUT} sha256={digest}", flush=True)
    return 0 if ev.passed() else 1


def main() -> int:
    try:
        with SingleInstance():
            return asyncio.run(run())
    except CanaryRefused as exc:
        print(f"REFUSED: {exc}", flush=True)
        return 2


if __name__ == "__main__":
    sys.exit(main())
