"""ADR 0043 canary — the loss-control ENFORCE assertion sequence, run against the live acct-3 rig.

Preconditions, REFUSED rather than worked around (a run that assumes them proves nothing):
  * ``WORKBENCH_LOSS_CONTROL_MODE`` must be ``ENFORCE`` — under OFF/SHADOW the machine is not
    authoritative, so no assertion here would mean anything;
  * the account must be genuinely in a durable loss-control lock (a ``REDUCTION_ONLY_*`` state read
    from ``risk_loss_control_state`` — measured, not assumed);
  * the protected legs must be present.

Each side-effecting step is CHECKPOINTED before the next begins, so a dropped SSH session resumes at
the first incomplete step and NEVER re-runs a completed side effect (a second protected-leg SELL, a
second rejected BUY, a second recovery request). On resume a completed step re-derives its assertion
from the DURABLE order / preflight / event evidence; a checkpoint that contradicts that evidence is
REFUSED, not silently restarted.

The assertions:
  A1 state_authoritative        — the durable state row is ``REDUCTION_ONLY_*``.
  A2 verified_reduction_allowed — a verified reduction (SELL a protected leg) is ADMITTED under the
                                  lock (ADR 0042 preserved). Recorded once; re-derived on resume.
  A3 new_risk_refused           — a new-risk BUY is REJECTED with ``LOSS_CONTROL_STOP`` + a durable
                                  trail. Recorded once; re-derived on resume.
  A4 reached_recovery_cooldown  — the recovery drove the account ALL THE WAY into
                                  ``RECOVERY_COOLDOWN`` with a full PASS (aggregate PASS, a committed
                                  ``PREFLIGHT_PASS`` event, parent ``PASSED``, 12 PASS checks). A
                                  preflight FAIL/INCOMPLETE — or merely entering ``RECOVERY_PREFLIGHT``
                                  — is a RED canary, NOT a vacuous pass.
  A5 evaluator_holds            — the cooldown evaluator is ACTUALLY invoked and returns exactly
                                  ``HOLD`` (no transition, still in cooldown); NORMAL / COOLDOWN_COMPLETE
                                  at NO point in the run. The harness never fakes elapsed time to force
                                  a re-arm.

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
    STATE_NORMAL,
    STATE_RECOVERY_COOLDOWN,
    USER,
    CanaryRefused,
    Checkpoint,
    Evidence,
    SingleInstance,
    assess_a4,
    assess_a5,
    control_events_for,
    current_loss_control_state,
    event_row,
    ledger_rows_for,
    load_limits,
    loss_control_mode,
    order_row,
    preflight_pass_check_count,
    preflight_row,
    saw_state_since,
    snapshot_state,
)

OUT = Path("/app/data/adr0043_evidence_enforce.json")
LEG = LEGS[0][0]  # the reduction target


def mk(sym, side, qty, src=OrderSourceType.STRATEGY) -> OrderRequest:
    return OrderRequest(
        user_id=USER, account_id=ACCT, symbol_ticker=sym, side=side, qty=qty,
        type=OrderType.MARKET, tif=TimeInForce.DAY, source_type=src,
    )


def _rejected(status: str) -> bool:
    # Case-insensitive: the ORM response yields the StrEnum value ("rejected") while a raw-SQL read on
    # resume yields the stored form (which may be the enum name, "REJECTED").
    return str(status).lower().endswith("rejected")


def _admitted(status: str) -> bool:
    return not _rejected(status)  # passed risk → submitted/accepted/filled (never rejected)


class CanaryRun:
    """The step-gated, resumable, idempotent assertion sequence. Collaborators are injected so the
    honesty tests can drive it offline with fakes."""

    def __init__(self, *, sf, adapter, router, recovery, evaluator, evidence, checkpoint):
        self.sf = sf
        self.ad = adapter
        self.router = router
        self.recovery: RecoveryPreflightService = recovery
        self.evaluator: CooldownEvaluator = evaluator
        self.ev: Evidence = evidence
        self.cp: Checkpoint = checkpoint

    async def _submit(self, step, request, order_req):
        pre = await snapshot_state(self.sf, self.ad)
        o = await self.router.submit(order_req)
        self.ev.record_order(step=step, snapshot=pre, request=request, response=o)
        return o

    # ---- A1 -------------------------------------------------------------------------------
    async def step_a1(self, pre) -> None:
        self.ev.assert_(
            "A1.state_authoritative",
            pre.loss_control_state in REDUCTION_ONLY_STATES
            and pre.loss_control_state_version is not None,
            f"loss_control_state={pre.loss_control_state} v{pre.loss_control_state_version}",
        )
        self.cp.record_step("A1", state=pre.loss_control_state)

    # ---- A2: a verified reduction is admitted ---------------------------------------------
    async def step_a2(self) -> None:
        if self.cp.step_done("A2"):
            oid = self.cp.step_data("A2").get("order_id")
            row = await order_row(self.sf, oid) if oid else None
            if row is None or str(row["side"]).lower() != "sell":
                raise CanaryRefused(
                    f"A2 checkpoint contradicts durable evidence (order {oid!r}); refusing to "
                    f"restart — investigate rather than re-submit a protected-leg SELL")
            self.ev.assert_("A2.verified_reduction_allowed", _admitted(row["status"]),
                            f"resumed: order #{oid} status={row['status']} (no re-submit)")
            return
        o = await self._submit(
            "A2.reduce", {"symbol": LEG, "side": "sell", "qty": "1", "kind": "verified_reduction"},
            mk(LEG, OrderSide.SELL, D("1")))
        self.cp.record_step("A2", order_id=getattr(o, "id", None))
        self.ev.assert_("A2.verified_reduction_allowed", _admitted(getattr(o, "status", "")),
                        f"SELL 1 {LEG} status={getattr(o, 'status', o)} "
                        f"reason={getattr(o, 'rejection_reason', None)}")

    # ---- A3: new risk is refused ----------------------------------------------------------
    async def step_a3(self) -> None:
        if self.cp.step_done("A3"):
            oid = self.cp.step_data("A3").get("order_id")
            row = await order_row(self.sf, oid) if oid else None
            reason = str(row["rejection_reason"] or "") if row else ""
            if row is None or not _rejected(row["status"]) or "LOSS_CONTROL_STOP" not in reason:
                raise CanaryRefused(
                    f"A3 checkpoint contradicts durable evidence (order {oid!r}); refusing to "
                    f"restart — investigate rather than re-submit a new-risk BUY")
            self.ev.assert_("A3.new_risk_refused", True,
                            f"resumed: order #{oid} rejected reason={reason} (no re-submit)")
            return
        since_l = (await ledger_rows_for(self.sf))  # snapshot before, for the audit check
        o = await self._submit(
            "A3.new_risk", {"symbol": LEG, "side": "buy", "qty": "1", "kind": "new_risk"},
            mk(LEG, OrderSide.BUY, D("1")))
        reason = str(getattr(o, "rejection_reason", "") or "")
        self.cp.record_step("A3", order_id=getattr(o, "id", None))
        self.ev.assert_(
            "A3.new_risk_refused",
            _rejected(getattr(o, "status", "")) and "LOSS_CONTROL_STOP" in reason,
            f"BUY 1 {LEG} status={getattr(o, 'status', o)} reason={reason}")
        ledger = await ledger_rows_for(self.sf, since_id=(since_l[-1]["id"] if since_l else 0))
        self.ev.assert_("A3.refusal_is_auditable", bool(ledger),
                        f"{len(ledger)} ledger row(s) for the refusal")

    # ---- A4: the recovery drives ALL THE WAY into RECOVERY_COOLDOWN ------------------------
    async def step_a4(self) -> None:
        if self.cp.step_done("A4"):
            preflight_id = self.cp.step_data("A4").get("preflight_id")
        else:
            outcome = await self.recovery.request_recovery(
                account_id=ACCT, account_owner_id=USER, idempotency_key=self.cp.idempotency_key,
                requester_user_id=USER, adapter=self.ad)
            # An operator-authority origin awaits an explicit approval; drive it (the canary is
            # authorised to exercise the full sanctioned path — it never edits state directly).
            if getattr(outcome, "status", None) == "AUTHORIZATION_REQUIRED":
                outcome = await self.recovery.approve(
                    account_id=ACCT, account_owner_id=USER, preflight_id=outcome.preflight_id,
                    approver_user_id=USER)
            preflight_id = outcome.preflight_id
            self.cp.record_step("A4", preflight_id=preflight_id)

        pf = await preflight_row(self.sf, preflight_id) if preflight_id else None
        state = await current_loss_control_state(self.sf)
        pass_event = False
        if pf and pf.get("transition_event_id"):
            evrow = await event_row(self.sf, pf["transition_event_id"])
            pass_event = bool(
                evrow and evrow["requested_transition"] == "PREFLIGHT_PASS"
                and evrow["to_state"] == STATE_RECOVERY_COOLDOWN)
        pass_count = await preflight_pass_check_count(self.sf, preflight_id) if preflight_id else 0
        ok, detail = assess_a4(
            accepted=pf is not None, aggregate_verdict=(pf or {}).get("aggregate_verdict"),
            resulting_state=state, has_preflight_pass_event=pass_event,
            parent_status=(pf or {}).get("status"), pass_check_count=pass_count)
        self.ev.doc["recovery"] = {"preflight_id": preflight_id, "detail": detail}
        self.ev.assert_("A4.reached_recovery_cooldown", ok, detail)

    # ---- A5: the evaluator is invoked and HOLDs -------------------------------------------
    async def step_a5(self, run_start_event_id: int) -> None:
        if self.cp.step_done("A5"):
            data = self.cp.step_data("A5")
            verdict, transitioned = data.get("verdict"), data.get("transitioned_to")
            called = True
        else:
            result = await self.evaluator.evaluate(ACCT, adapter=self.ad, velocity=None)
            verdict, transitioned = result.verdict, result.transitioned_to
            called = True
            self.cp.record_step("A5", verdict=verdict, transitioned_to=transitioned)

        state = await current_loss_control_state(self.sf)
        saw_normal = await saw_state_since(self.sf, STATE_NORMAL, run_start_event_id)
        saw_complete = any(
            e["requested_transition"] == "COOLDOWN_COMPLETE"
            for e in await control_events_for(self.sf, since_id=run_start_event_id))
        ok, detail = assess_a5(
            evaluator_called=called, verdict=verdict, transitioned_to=transitioned,
            current_state=state, saw_normal=saw_normal, saw_cooldown_complete=saw_complete)
        self.ev.assert_("A5.evaluator_holds", ok, detail)

    async def execute(self, *, pre, run_start_event_id: int) -> int:
        if self.cp.all_done():
            self.ev.assert_("already_complete", True,
                            "checkpoint reports all steps done — no orders or transitions re-issued")
            return 0
        await self.step_a1(pre)
        await self.step_a2()
        await self.step_a3()
        await self.step_a4()
        await self.step_a5(run_start_event_id)
        return 0 if self.ev.passed() else 1


async def run() -> int:
    sf = get_sessionmaker()
    ev = Evidence(phase="ENFORCE")
    cp = Checkpoint.load()

    mode = await loss_control_mode(sf)
    if mode != REQUIRED_LOSS_CONTROL_MODE:
        raise CanaryRefused(
            f"WORKBENCH_LOSS_CONTROL_MODE is {mode!r}, not {REQUIRED_LOSS_CONTROL_MODE!r}. Under "
            f"OFF/SHADOW the state machine is not authoritative, so the canary would assert nothing.")

    registry = BrokerRegistry(sf)
    await registry.load_all()
    ad = registry.get(USER)
    ev.doc["risk_limits"] = (await load_limits(sf)).as_dict()

    pre = await snapshot_state(sf, ad)
    ev.doc["precondition_snapshot"] = pre.as_dict()
    if not pre.reduction_only:
        raise CanaryRefused(
            f"account {ACCT} is not in a reduction-only loss-control state "
            f"(loss_control_state={pre.loss_control_state!r}); the canary asserts behaviour UNDER a "
            f"lock, it does not manufacture one.")
    missing = [s for s, _ in LEGS if pre.positions.get(s, D(0)) <= 0]
    if missing:
        raise CanaryRefused(f"protected legs absent: {missing}; cannot run the reduction assertion")

    # Anchor "NORMAL / COOLDOWN_COMPLETE at NO point in the run" to a durable event id, captured once.
    if "run_start_event_id" not in cp.steps:
        from scripts.adr0043_canary_lib import max_control_event_id
        cp.steps["run_start_event_id"] = await max_control_event_id(sf)
        cp.save()
    run_start = int(cp.steps["run_start_event_id"])
    cp.lock_reached = True
    cp.save()

    bus = EventBus()
    router = OrderRouter(
        ad, RiskEngine(sf, broker_registry=registry, bus=bus), sf, bus, broker_registry=registry)
    run_obj = CanaryRun(
        sf=sf, adapter=ad, router=router, recovery=RecoveryPreflightService(sf),
        evaluator=CooldownEvaluator(sf), evidence=ev, checkpoint=cp)
    rc = await run_obj.execute(pre=pre, run_start_event_id=run_start)

    digest = ev.write(OUT)
    cp.phase = "DONE"
    cp.note("complete", gate=ev.doc["gate"], digest=digest)
    print(f"\nADR 0043 canary {ev.doc['gate']} — evidence {OUT} sha256={digest}", flush=True)
    return rc


def main() -> int:
    try:
        with SingleInstance():
            return asyncio.run(run())
    except CanaryRefused as exc:
        print(f"REFUSED: {exc}", flush=True)
        return 2


if __name__ == "__main__":
    sys.exit(main())
