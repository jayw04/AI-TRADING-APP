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
     + reduction_settled          — and SETTLED: the per-order REST barrier confirms the broker
                                  order FILLED, the local order terminal, exactly one booked fill of
                                  the reduced quantity, local == broker position at the expected
                                  figure, and no lingering HELD reservation. An ALLOW that never
                                  reached the account is NOT a passing A2.
     + admitted_as_verified_reduction / state_remains_reduction_only — the ledger records the
                                  admission AS a verified reduction, and the lock still holds after.
  A3 new_risk_refused           — a new-risk BUY is REJECTED with ``LOSS_CONTROL_STOP``, reaches NO
                                  broker (no broker order id, no reservation), and leaves the
                                  settled position from A2 unchanged. Recorded once; re-derived on
                                  resume. If a broker submission somehow occurred, the run
                                  reconciles it through the canonical settlement path and STOPS.

  A4 reached_recovery_cooldown  — the recovery drove the account ALL THE WAY into
                                  ``RECOVERY_COOLDOWN`` with a full PASS (aggregate PASS, a committed
                                  ``PREFLIGHT_PASS`` event, parent ``PASSED``, 12 PASS checks). A
                                  preflight FAIL/INCOMPLETE — or merely entering ``RECOVERY_PREFLIGHT``
                                  — is a RED canary, NOT a vacuous pass.
  A5 evaluator_holds            — the cooldown evaluator is ACTUALLY invoked and returns exactly
                                  ``HOLD`` (no transition, still in cooldown); NORMAL / COOLDOWN_COMPLETE
                                  at NO point in the run. The harness never fakes elapsed time to force
                                  a re-arm.

Ordering is load-bearing: A2 submit → A2 SETTLE → verify → A3 → verify. Attempt 2 failed because a
wall-clock sleep stood where the settlement barrier now stands, so A3 acted on a ledger that had not
caught up. The barrier is inside A2 itself — it is not deferred to the churn driver. Every order
goes through ``GovernedSubmitter``, which pairs the submit with the barrier in one call;
``check_settlement_barrier.py`` proves at CI time that no harness can bypass it.

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
from app.orders.lifecycle import TradeUpdateConsumer
from app.orders.positions import PositionRecomputer
from app.orders.router import OrderRouter
from app.risk import OrderRequest, RiskEngine
from app.risk.loss_control.cooldown import CooldownEvaluator
from app.risk.loss_control.recovery import RecoveryPreflightService
from scripts.adr0043_canary_lib import (
    ACCT,
    LEGS,
    REDUCE_QTY,
    REDUCTION_ONLY_STATES,
    REQUIRED_LOSS_CONTROL_MODE,
    STATE_NORMAL,
    STATE_RECOVERY_COOLDOWN,
    USER,
    CanaryRefused,
    CanaryStop,
    Checkpoint,
    Evidence,
    GovernedSubmitter,
    SingleInstance,
    assess_a2_settlement,
    assess_a3_no_submission,
    assess_a4,
    assess_a5,
    broker_position_qty,
    control_events_for,
    current_loss_control_state,
    event_row,
    find_order_by_client_id,
    ledger_rows_for,
    load_limits,
    local_position_qty,
    loss_control_mode,
    max_ledger_id,
    order_fill_summary,
    order_identity_matches,
    order_row,
    preflight_pass_check_count,
    preflight_row,
    reservation_states_for,
    saw_state_since,
    snapshot_state,
)

OUT = Path("/app/data/adr0043_evidence_enforce.json")
LEG = LEGS[0][0]  # the reduction target


def mk(sym, side, qty, *, client_order_id, src=OrderSourceType.STRATEGY) -> OrderRequest:
    # A DETERMINISTIC client_order_id: the router forwards it to the broker (router.py L623), so a
    # re-submit after a lost checkpoint cannot create a second broker order.
    return OrderRequest(
        user_id=USER, account_id=ACCT, symbol_ticker=sym, side=side, qty=qty,
        type=OrderType.MARKET, tif=TimeInForce.DAY, source_type=src, client_order_id=client_order_id,
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

    def __init__(self, *, sf, adapter, router, recovery, evaluator, evidence, checkpoint,
                 consumer=None, settle=None):
        self.sf = sf
        self.ad = adapter
        self.router = router
        self.recovery: RecoveryPreflightService = recovery
        self.evaluator: CooldownEvaluator = evaluator
        self.ev: Evidence = evidence
        self.cp: Checkpoint = checkpoint
        self.consumer = consumer
        # EVERY order this harness places goes through the one governed seam, which pairs the
        # submit with the barrier so they cannot drift apart. ``settle`` is injected only so the
        # offline honesty tests can drive the sequencing without a broker; the production default
        # is the real barrier and there is no configuration that removes it.
        self.sub = GovernedSubmitter(
            sf=sf, adapter=adapter, router=router, consumer=consumer, evidence=evidence,
            checkpoint=checkpoint, settle=settle)

    async def settle(self, step: str, *, order_id: int, ticker: str):
        """THE BARRIER, for an order this step did not just submit (a rebind). Returns only when the
        order is settled against broker truth; otherwise raises :class:`SettlementBarrierFailed`
        with a full, credential-free diagnostic record."""
        result, _elapsed = await self.sub.settle_existing(step=step, order_id=order_id,
                                                          ticker=ticker)
        return result

    # ---- A1 -------------------------------------------------------------------------------
    async def step_a1(self, pre) -> None:
        self.ev.assert_(
            "A1.state_authoritative",
            pre.loss_control_state in REDUCTION_ONLY_STATES
            and pre.loss_control_state_version is not None,
            f"loss_control_state={pre.loss_control_state} v{pre.loss_control_state_version}",
        )
        self.cp.record_step("A1", state=pre.loss_control_state)

    # ---- A2: a verified reduction is admitted AND SETTLED ---------------------------------
    # Two distinct claims, and the second is the one attempt 2 skipped. "The router returned ALLOW"
    # is a statement about the decision; it is NOT a statement about the account. A2 is formal
    # evidence in its own right, so it settles here — NOT later inside the churn driver, and NOT
    # after A3 has already acted on a ledger nobody verified.
    async def step_a2(self) -> None:
        cid = self.cp.client_id("A2")
        existing = await find_order_by_client_id(self.sf, self.ad, cid)
        if existing is not None:
            # An order already carries this identity (checkpoint present OR the post-submit crash
            # window). Rebind to it; never submit a second protected-leg SELL.
            if not order_identity_matches(existing, side="sell", symbol=LEG, qty=REDUCE_QTY):
                raise CanaryRefused(
                    f"A2 deterministic id {cid} exists with contradicting fields {existing}; "
                    f"refusing — investigate rather than restart")
            intent = self.cp.intent("A2")
            if not intent.get("expected_position"):
                raise CanaryRefused(
                    f"A2 order {cid} exists but no pre-submit intent was recorded; the expected "
                    f"post-settlement position cannot be derived. A resumed run that cannot verify "
                    f"its own arithmetic must refuse, not assume.")
            if existing.get("local_id") is None:
                raise CanaryRefused(
                    f"A2 order {cid} exists at the BROKER with no local order row; settlement "
                    f"cannot be verified against a ledger that never recorded the order.")
            order_id = int(existing["local_id"])
            self.cp.record_step("A2", order_id=order_id, client_order_id=cid, rebound=True)
            self.ev.assert_("A2.verified_reduction_allowed", _admitted(existing["status"]),
                            f"rebound to {existing['source']} order {cid} "
                            f"status={existing['status']} (no re-submit)")
            await self._verify_a2(
                order_id=order_id, expected=D(str(intent["expected_position"])),
                ledger_since=int(intent.get("ledger_since") or 0))
            return

        pre = await snapshot_state(self.sf, self.ad)
        held = pre.positions.get(LEG, D(0))
        if held < REDUCE_QTY:
            raise CanaryRefused(
                f"A2 cannot reduce {LEG}: broker holds {held}, need at least {REDUCE_QTY}")
        expected = held - REDUCE_QTY
        ledger_since = await max_ledger_id(self.sf)
        # Durable BEFORE the side effect: a crash after submit still knows what to verify.
        self.cp.record_intent("A2", pre_position=str(held), expected_position=str(expected),
                              ledger_since=ledger_since, client_order_id=cid)
        # Submit and settle are ONE decision here — the seam will not return an unsettled order
        # that reached the broker.
        governed = await self.sub.submit_and_settle(
            step="A2.reduce",
            request={"symbol": LEG, "side": "sell", "qty": str(REDUCE_QTY),
                     "client_order_id": cid},
            order_req=mk(LEG, OrderSide.SELL, REDUCE_QTY, client_order_id=cid),
            ticker=LEG, pre=pre)
        self.cp.record_step("A2", order_id=governed.order_id, client_order_id=cid,
                            broker_order_id=governed.broker_order_id)
        self.ev.assert_("A2.verified_reduction_allowed", governed.admitted,
                        f"SELL {REDUCE_QTY} {LEG} status={governed.status} "
                        f"reason={getattr(governed.order, 'rejection_reason', None)}")
        if governed.order_id is None:
            raise CanaryStop(
                "A2_NO_LOCAL_ORDER",
                f"the router returned no local order id for {cid}; settlement cannot be verified")
        if governed.settlement is None:
            raise CanaryStop(
                "A2_REDUCTION_REFUSED",
                f"the verified reduction was refused before the broker (status={governed.status}); "
                f"there is no settled reduction to assert on")
        await self._verify_a2(order_id=int(governed.order_id), expected=expected,
                              ledger_since=ledger_since, result=governed.settlement)

    async def _verify_a2(self, *, order_id: int, expected: D, ledger_since: int,
                         result=None) -> None:
        """Read every claim back from the durable record — never from the router's response."""
        if result is None:                       # rebind path: settle the order we rebound to
            result = await self.settle("A2", order_id=order_id, ticker=LEG)

        booked = await order_fill_summary(self.sf, order_id)
        ok, detail = assess_a2_settlement(
            broker_status=result.broker_status, local_status=booked["status"],
            fill_count=booked["fill_count"], booked_qty=booked["filled_qty"],
            local_position=await local_position_qty(self.sf, LEG),
            broker_position=broker_position_qty(self.ad, LEG),
            expected_position=expected,
            reservation_states=await reservation_states_for(self.sf, order_id))
        self.ev.assert_("A2.reduction_settled", ok, detail)

        # The admission must be visible in the append-only decision ledger AS a verified reduction —
        # an ALLOW with some other rationale would mean the gate let it through for the wrong reason.
        ledger = await ledger_rows_for(self.sf, since_id=ledger_since)
        verified = [
            r for r in ledger
            if "ALLOW" in str(r.get("decision") or "").upper()
            and "VERIFIED_REDUCTION" in str(r.get("reason_codes") or "")
        ]
        self.ev.assert_(
            "A2.admitted_as_verified_reduction", bool(verified),
            f"{len(verified)} ALLOW/VERIFIED_REDUCTION ledger row(s) of {len(ledger)} since "
            f"id={ledger_since}")

        # Settling a reduction must not have moved the account out of the lock — the whole point is
        # that a reduction is permitted WHILE reduction-only remains in force.
        state = await current_loss_control_state(self.sf)
        self.ev.assert_("A2.state_remains_reduction_only", state in REDUCTION_ONLY_STATES,
                        f"loss_control_state={state} after the settled reduction")

    # ---- A3: new risk is refused, and reaches NO broker -----------------------------------
    # Runs only after A2 has SETTLED, so "MSFT is unchanged" is a claim about a known position
    # rather than about one that may still be in flight.
    async def step_a3(self) -> None:
        cid = self.cp.client_id("A3")
        expected = self.cp.intent("A2").get("expected_position")
        if expected is None:
            raise CanaryRefused(
                "A3 cannot assert an unchanged position: no settled A2 intent is recorded")
        expected_pos = D(str(expected))

        existing = await find_order_by_client_id(self.sf, self.ad, cid)
        if existing is not None:
            if not order_identity_matches(existing, side="buy", symbol=LEG, qty=REDUCE_QTY):
                raise CanaryRefused(
                    f"A3 deterministic id {cid} exists with contradicting fields {existing}; "
                    f"refusing — investigate rather than restart")
            row = await order_row(self.sf, existing["local_id"]) if existing.get("local_id") else None
            reason = str((row or {}).get("rejection_reason") or "")
            self.cp.record_step("A3", order_id=existing.get("local_id"), client_order_id=cid,
                                rebound=True)
            await self._assert_a3(
                rejected=_rejected(existing["status"]), reason=reason,
                broker_order_id=(await order_fill_summary(
                    self.sf, existing["local_id"]))["broker_order_id"]
                if existing.get("local_id") else None,
                local_status=existing["status"], expected=expected_pos,
                order_id=existing.get("local_id"), note=f"rebound to order {cid} (no re-submit)")
            return

        since_l = await max_ledger_id(self.sf)
        # The seam proves no broker order exists. If one does, it reconciles that order through the
        # canonical barrier and raises A3_UNEXPECTED_BROKER_SUBMISSION — the canary does not
        # continue on an account carrying an unplanned live order.
        governed = await self.sub.submit_expecting_refusal(
            step="A3.new_risk",
            request={"symbol": LEG, "side": "buy", "qty": str(REDUCE_QTY),
                     "client_order_id": cid},
            order_req=mk(LEG, OrderSide.BUY, REDUCE_QTY, client_order_id=cid), ticker=LEG)
        reason = str(getattr(governed.order, "rejection_reason", "") or "")
        self.cp.record_step("A3", order_id=governed.order_id, client_order_id=cid,
                            broker_order_id=governed.broker_order_id)

        await self._assert_a3(
            rejected=_rejected(governed.status), reason=reason, broker_order_id=None,
            local_status=governed.status, expected=expected_pos, order_id=governed.order_id,
            note=f"BUY {REDUCE_QTY} {LEG}")
        ledger = await ledger_rows_for(self.sf, since_id=since_l)
        self.ev.assert_("A3.refusal_is_auditable", bool(ledger),
                        f"{len(ledger)} ledger row(s) for the refusal")

    async def _assert_a3(self, *, rejected, reason, broker_order_id, local_status, expected,
                         order_id, note) -> None:
        reservations = await reservation_states_for(self.sf, order_id) if order_id else []
        self.ev.assert_("A3.no_broker_submission", not broker_order_id,
                        f"broker_order_id={broker_order_id or 'none'}")
        ok, detail = assess_a3_no_submission(
            rejected=rejected, reason=reason, broker_order_id=broker_order_id,
            local_status=local_status,
            local_position=await local_position_qty(self.sf, LEG),
            broker_position=broker_position_qty(self.ad, LEG),
            expected_position=expected, reservation_count=len(reservations))
        self.ev.assert_("A3.new_risk_refused", ok, f"{note} — {detail}")

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


async def _completed_or_none(sf, adapter, cp: Checkpoint, out_path: Path) -> int | None:
    """If the checkpoint reports every step done, VERIFY the durable evidence and return the prior
    gate WITHOUT any side effect — never trade, request recovery, run the evaluator, or rewrite the
    evidence again. Called BEFORE the mutable reduction-only / legs preconditions (after a full run
    the account is in RECOVERY_COOLDOWN, not reduction-only, so those preconditions would otherwise
    wrongly refuse a completed run). A completed checkpoint that contradicts durable evidence is
    REFUSED, not trusted."""
    if not cp.all_done():
        return None
    for step, side in (("A2", "sell"), ("A3", "buy")):
        cid = cp.client_id(step)
        found = await find_order_by_client_id(sf, adapter, cid)
        if found is None or not order_identity_matches(found, side=side, symbol=LEG, qty=REDUCE_QTY):
            raise CanaryRefused(
                f"completed-run {step} order {cid} missing or contradicts durable evidence: {found}")
    pf_id = cp.step_data("A4").get("preflight_id")
    pf = await preflight_row(sf, pf_id) if pf_id else None
    if not pf or pf.get("status") != "PASSED" or await preflight_pass_check_count(sf, pf_id) != 12:
        raise CanaryRefused("completed-run preflight evidence missing or not a full 12/12 PASS")
    if cp.step_data("A5").get("verdict") != "HOLD":
        raise CanaryRefused("completed-run A5 verdict is not HOLD")
    if not out_path.exists():
        raise CanaryRefused("completed-run evidence file is missing")
    import hashlib
    digest = hashlib.sha256(out_path.read_bytes()).hexdigest()
    if cp.completed_digest and digest != cp.completed_digest:
        raise CanaryRefused("completed-run evidence file digest does not match the checkpoint")
    run_start = int(cp.steps.get("run_start_event_id", 0))
    if await saw_state_since(sf, STATE_NORMAL, run_start):
        raise CanaryRefused("a NORMAL transition occurred after the recorded run — evidence is stale")
    gate = cp.completed_gate or "FAIL"
    print(f"ADR 0043 canary already complete — gate {gate}; no orders/recovery/evaluator re-issued",
          flush=True)
    return 0 if gate == "PASS" else 1


async def run() -> int:
    sf = get_sessionmaker()
    ev = Evidence(phase="ENFORCE")
    cp = Checkpoint.load()

    # A completed run resumes cleanly BEFORE the mutable preconditions: verify durable evidence and
    # return the prior result with zero side effects (local-order evidence only — no registry/broker).
    completed = await _completed_or_none(sf, None, cp, OUT)
    if completed is not None:
        return completed

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
    # The consumer is NOT started: the harness drives its canonical ``_handle`` synchronously via
    # the settlement barrier. Subscribing here would re-arm a second consumer against the same
    # trade-update stream — the dual-arm condition that lost attempt 2's fills in the first place.
    consumer = TradeUpdateConsumer(sf, bus, PositionRecomputer(sf, bus))
    run_obj = CanaryRun(
        sf=sf, adapter=ad, router=router, recovery=RecoveryPreflightService(sf),
        evaluator=CooldownEvaluator(sf), evidence=ev, checkpoint=cp, consumer=consumer)
    try:
        rc = await run_obj.execute(pre=pre, run_start_event_id=run_start)
    except CanaryStop as stop:
        # A stop is EVIDENCE, not an absence of it. Write the package before propagating so the
        # failure is diagnosable without re-running anything against the live account.
        ev.record_stop(stop.stop_reason, stop.detail, stop.diagnostics)
        digest = ev.write(OUT)
        # Deliberately NOT recording completed_gate/digest: a stopped run is not a completed run,
        # and must never resume down the "already complete" path.
        cp.phase = f"STOPPED:{stop.stop_reason}"
        cp.save()
        cp.note("stopped", stop_reason=stop.stop_reason, detail=stop.detail, digest=digest)
        raise

    digest = ev.write(OUT)
    cp.completed_gate = ev.doc["gate"]
    cp.completed_digest = digest
    cp.phase = "DONE"
    cp.save()
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
    except CanaryStop as exc:
        # Distinct exit code: a STOP means the run began and then hit a named unsafe condition —
        # operationally very different from a refusal, and the runbook treats it differently.
        print(f"STOP [{exc.stop_reason}]: {exc.detail}", flush=True)
        print(f"  diagnostics: {exc.diagnostics}", flush=True)
        return 3


if __name__ == "__main__":
    sys.exit(main())
