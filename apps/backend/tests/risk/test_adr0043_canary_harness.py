"""ADR 0043 canary harness — the ways a harness could LIE, as regression tests.

Like the ADR 0042 harness tests, none of these is about the risk engine; every one is about the
harness not asserting a green it didn't earn. They run offline (no broker, no box). The blocker-2
tests prove that a GREEN canary REQUIRES actually reaching RECOVERY_COOLDOWN and holding there; the
blocker-1 tests prove the run is truly step-level resumable and idempotent (a retry never re-issues a
completed side effect).
"""

from __future__ import annotations

import importlib
import json
from datetime import UTC, datetime
from decimal import Decimal as D
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from app.db.enums import OrderSide, OrderSourceType, OrderStatus, OrderType, TimeInForce
from app.db.models.account import Account, AccountMode
from app.db.models.order import Order
from app.db.models.symbol import Symbol
from app.db.models.user import User


@pytest.fixture
def lib(tmp_path, monkeypatch):
    monkeypatch.setenv("ADR0043_CHECKPOINT", str(tmp_path / "state.json"))
    monkeypatch.setenv("ADR0043_LOCKFILE", str(tmp_path / "canary.lock"))
    import scripts.adr0043_canary_lib as m

    return importlib.reload(m)


def _snap(m, **over):
    base = dict(
        at="2026-07-20T18:00:00+00:00", day_change=D("-6000"), equity=D("94000"),
        last_equity=D("100000"), max_daily_loss=D("5000"), breaker_tripped_at=None,
        loss_control_state=m.STATE_REDUCTION_ONLY_DAILY_LOSS, loss_control_state_version=3,
        last_sequence_no=3, positions={"F": D("500"), "MSFT": D("20")}, open_orders=0,
    )
    base.update(over)
    return m.StateSnapshot(**base)


# ---------------------------------------------------------------- legs / protected discipline


def test_every_leg_is_protected(lib):
    legs = {s for s, _ in lib.LEGS}
    assert legs and legs <= set(lib.PROTECTED), f"legs {legs - set(lib.PROTECTED)} not protected"


def test_churn_symbols_disjoint_from_legs(lib):
    assert not (set(lib.CHURN_SYMBOLS) & {s for s, _ in lib.LEGS})


# ---------------------------------------------------------------- the lock is MEASURED, not assumed


def test_reduction_only_reflects_the_durable_state_row(lib):
    assert _snap(lib).reduction_only is True
    assert _snap(lib, loss_control_state=lib.STATE_NORMAL).reduction_only is False
    assert _snap(lib, loss_control_state=lib.STATE_INTEGRITY_STOP).reduction_only is False
    assert _snap(lib, loss_control_state=None).reduction_only is False  # missing row is NOT a lock


def test_integrity_stop_is_locked_but_not_reduction_only(lib):
    s = _snap(lib, loss_control_state=lib.STATE_INTEGRITY_STOP)
    assert s.locked is True and s.reduction_only is False


def test_normal_is_not_locked(lib):
    assert _snap(lib, loss_control_state=lib.STATE_NORMAL).locked is False


# ---------------------------------------------------------------- limits are never relaxed


def test_admissible_shares_is_bounded_by_the_tightest_cap(lib):
    limits = lib.Limits(max_position_qty=D("10"), max_position_notional=D("100000"),
                        max_gross_exposure=D("50000"), max_daily_loss=D("5000"),
                        max_orders_per_day=100)
    n = lib.admissible_shares(price=D("50"), limits=limits, gross_used=D("0"),
                              buying_power=D("1000000"), ceiling=D("1000000"))
    assert n == D("10")


def test_admissible_shares_zero_on_nonpositive_price(lib):
    limits = lib.Limits(None, None, None, None, None)
    assert lib.admissible_shares(price=D("0"), limits=limits, gross_used=D("0"),
                                 buying_power=D("1"), ceiling=D("1")) == D("0")


# ---------------------------------------------------------------- evidence cannot fake a PASS


def test_empty_assertions_is_not_a_pass(lib):
    assert lib.Evidence(phase="ENFORCE").passed() is False


def test_one_failed_assertion_fails_the_gate(lib):
    ev = lib.Evidence(phase="ENFORCE")
    ev.assert_("ok", True, "")
    ev.assert_("bad", False, "")
    assert ev.passed() is False


def test_all_pass_is_a_pass_and_writes_gate(lib, tmp_path):
    ev = lib.Evidence(phase="ENFORCE")
    ev.assert_("a", True, "")
    ev.assert_("b", True, "")
    out = tmp_path / "ev.json"
    digest = ev.write(out)
    import json
    assert ev.passed() is True and len(digest) == 64
    assert json.loads(out.read_text())["gate"] == "PASS"


# ---------------------------------------------------------------- checkpoint + single instance


def test_checkpoint_is_resumable(lib):
    cp = lib.Checkpoint.load()
    cp.phase = "MIDWAY"
    cp.lock_reached = True
    cp.save()
    again = lib.Checkpoint.load()
    assert again.phase == "MIDWAY" and again.lock_reached is True


def test_single_instance_refuses_a_second_process(lib):
    with lib.SingleInstance(), pytest.raises(lib.CanaryRefused), lib.SingleInstance():
        pass
    with lib.SingleInstance():  # after release a new one may acquire
        pass


# ---------------------------------------------------------------- required mode


def test_required_mode_is_enforce(lib):
    assert lib.REQUIRED_LOSS_CONTROL_MODE == "ENFORCE"


def test_loss_control_mode_reads_env(lib, monkeypatch):
    monkeypatch.setenv("WORKBENCH_LOSS_CONTROL_MODE", "shadow")
    import asyncio
    assert asyncio.run(lib.loss_control_mode(None)) == "SHADOW"


def test_snapshot_serializes_the_durable_state(lib):
    d = _snap(lib).as_dict()
    assert d["loss_control_state"] == lib.STATE_REDUCTION_ONLY_DAILY_LOSS
    assert d["reduction_only"] is True and d["loss_control_state_version"] == 3
    assert d["positions"] == {"F": "500", "MSFT": "20"}


# ================================================================ blocker 2: GREEN requires cooldown


def test_assess_a4_green_only_on_full_cooldown_pass(lib):
    ok, _ = lib.assess_a4(accepted=True, aggregate_verdict="PASS",
                          resulting_state=lib.STATE_RECOVERY_COOLDOWN, has_preflight_pass_event=True,
                          parent_status="PASSED", pass_check_count=12)
    assert ok is True


@pytest.mark.parametrize("over", [
    {"accepted": False},
    {"aggregate_verdict": "INCOMPLETE"},
    {"aggregate_verdict": "FAIL"},
    {"aggregate_verdict": None},
    {"resulting_state": "RECOVERY_PREFLIGHT"},          # entered preflight but NOT cooldown
    {"resulting_state": "REDUCTION_ONLY_DAILY_LOSS"},   # returned to the lock
    {"has_preflight_pass_event": False},
    {"parent_status": "AUTHORIZATION_REQUIRED"},
    {"parent_status": "FAILED"},
    {"pass_check_count": 11},                           # not all 12 checks passed
])
def test_assess_a4_is_red_when_cooldown_not_fully_reached(lib, over):
    base = dict(accepted=True, aggregate_verdict="PASS",
                resulting_state=lib.STATE_RECOVERY_COOLDOWN, has_preflight_pass_event=True,
                parent_status="PASSED", pass_check_count=12)
    base.update(over)
    ok, _ = lib.assess_a4(**base)
    assert ok is False, f"A4 must be RED for {over}"


def test_assess_a5_green_only_on_true_hold(lib):
    ok, _ = lib.assess_a5(evaluator_called=True, verdict="HOLD", transitioned_to=None,
                          current_state=lib.STATE_RECOVERY_COOLDOWN, saw_normal=False,
                          saw_cooldown_complete=False)
    assert ok is True


@pytest.mark.parametrize("over", [
    {"evaluator_called": False},                           # evaluator never invoked
    {"verdict": "NO_OP"},                                  # not actually evaluated
    {"verdict": "COMPLETE", "transitioned_to": "NORMAL"},  # re-armed
    {"verdict": "REGRESSED", "transitioned_to": "INTEGRITY_STOP"},  # regressed
    {"transitioned_to": "NORMAL"},
    {"current_state": "NORMAL"},
    {"saw_normal": True},                                  # NORMAL at some point in the run
    {"saw_cooldown_complete": True},                       # a COOLDOWN_COMPLETE fired
])
def test_assess_a5_is_red_on_any_non_hold(lib, over):
    base = dict(evaluator_called=True, verdict="HOLD", transitioned_to=None,
                current_state=lib.STATE_RECOVERY_COOLDOWN, saw_normal=False,
                saw_cooldown_complete=False)
    base.update(over)
    ok, _ = lib.assess_a5(**base)
    assert ok is False, f"A5 must be RED for {over}"




# ================================================================ blocker 1: resumable + idempotent
# A DB-PERSISTING fake router: a re-submit shows up as a second durable order, so the harness must
# instead rebind to the existing deterministic client_order_id and submit exactly once.

import hashlib  # noqa: E402

from app.db.models.risk_loss_control_state import RiskLossControlState  # noqa: E402
from app.db.models.risk_recovery_preflight import RiskRecoveryPreflight  # noqa: E402
from app.db.models.risk_recovery_preflight_check import RiskRecoveryPreflightCheck  # noqa: E402


class _DbRouter:
    def __init__(self, sf):
        self.sf = sf
        self.submits = 0

    async def submit(self, req):
        self.submits += 1
        rejected = req.side == OrderSide.BUY
        async with self.sf() as s:
            o = Order(user_id=3, account_id=3, symbol_id=1, client_order_id=req.client_order_id,
                      side=req.side, qty=req.qty, type=OrderType.MARKET, tif=TimeInForce.DAY,
                      status=(OrderStatus.REJECTED if rejected else OrderStatus.SUBMITTED),
                      source_type=OrderSourceType.STRATEGY,
                      rejection_reason=("LOSS_CONTROL_STOP" if rejected else None),
                      created_at=datetime.now(UTC), updated_at=datetime.now(UTC))
            s.add(o)
            await s.commit()
            oid = o.id
        return SimpleNamespace(id=oid, status=("rejected" if rejected else "submitted"),
                               rejection_reason=("LOSS_CONTROL_STOP" if rejected else None))


class _FakeRecovery:
    def __init__(self):
        self.requests = 0
        self.keys = []

    async def request_recovery(self, **kw):
        self.requests += 1
        self.keys.append(kw.get("idempotency_key"))
        return SimpleNamespace(preflight_id=1, status="PASSED")


class _FakeEvaluator:
    def __init__(self):
        self.calls = 0

    async def evaluate(self, account_id, **kw):
        self.calls += 1
        return SimpleNamespace(verdict="HOLD", transitioned_to=None, account_id=account_id)


def _adapter():
    a = MagicMock()
    a.get_positions.return_value = []
    a.list_orders.return_value = []
    return a


@pytest.fixture
def canary_env(tmp_path, monkeypatch):
    import scripts.adr0043_canary_lib as m
    monkeypatch.setattr(m, "CHECKPOINT", tmp_path / "state.json")
    monkeypatch.setattr(m, "LOCKFILE", tmp_path / "canary.lock")
    return m


async def _seed_account(session_factory):
    async with session_factory() as s:
        s.add(User(id=3, email="c@t"))
        s.add(Account(id=3, user_id=3, broker="alpaca", mode=AccountMode.paper, label="C"))
        s.add(Symbol(id=1, ticker="F", exchange="X", asset_class="us_equity", name="Ford",
                     active=True))
        await s.commit()


async def _seed_order(session_factory, *, oid, side, status, client_order_id, reason=None):
    async with session_factory() as s:
        s.add(Order(id=oid, user_id=3, account_id=3, symbol_id=1, client_order_id=client_order_id,
                    side=side, qty=D("1"), type=OrderType.MARKET, tif=TimeInForce.DAY,
                    status=status, source_type=OrderSourceType.STRATEGY, rejection_reason=reason,
                    created_at=datetime.now(UTC), updated_at=datetime.now(UTC)))
        await s.commit()


def _canary(canary_env, session_factory, cp, **collab):
    from scripts.adr0043_canary_run import CanaryRun
    return CanaryRun(
        sf=session_factory, adapter=collab.get("adapter", _adapter()),
        router=collab.get("router", _DbRouter(session_factory)),
        recovery=collab.get("recovery", _FakeRecovery()),
        evaluator=collab.get("evaluator", _FakeEvaluator()),
        evidence=canary_env.Evidence(phase="TEST"), checkpoint=cp,
        consumer=collab.get("consumer", MagicMock()),
        # Default to a settle that always succeeds; tests that care inject a spy. There is no
        # production path that omits it — see CanaryRun.__init__.
        settle=collab.get("settle", _SettleSpy()))


# ---- the post-submit / pre-checkpoint crash window ----


def _named(run) -> dict[str, str]:
    return {a["name"]: a["result"] for a in run.ev.doc["assertions"]}


async def test_a2_rebinds_to_existing_order_when_checkpoint_absent(canary_env, session_factory):
    # The order was submitted (durably) but the completed-step write was lost. A retry must REBIND to
    # the existing deterministic identity, not submit a second protected-leg SELL. The pre-submit
    # INTENT survives that window, which is what lets the rebound run still verify settlement.
    await _seed_account(session_factory)
    cp = canary_env.Checkpoint.load()
    cp.record_intent("A2", pre_position="19", expected_position="18", ledger_since=0)
    await _seed_order(session_factory, oid=1, side=OrderSide.SELL, status=OrderStatus.SUBMITTED,
                      client_order_id=cp.client_id("A2"))  # checkpoint has NO A2 step recorded
    router = _DbRouter(session_factory)
    run = _canary(canary_env, session_factory, cp, router=router,
                  adapter=_positioned_adapter("18"))
    await run.step_a2()
    assert router.submits == 0                                   # no second SELL
    assert _named(run)["A2.verified_reduction_allowed"] == "PASS"
    assert cp.step_done("A2")


async def test_a3_rebinds_to_existing_rejected_order_when_checkpoint_absent(canary_env,
                                                                            session_factory):
    await _seed_account(session_factory)
    await _seed_settled_position(session_factory, "18")
    cp = canary_env.Checkpoint.load()
    cp.record_intent("A2", pre_position="19", expected_position="18", ledger_since=0)
    await _seed_order(session_factory, oid=2, side=OrderSide.BUY, status=OrderStatus.REJECTED,
                      client_order_id=cp.client_id("A3"), reason="LOSS_CONTROL_STOP")
    router = _DbRouter(session_factory)
    run = _canary(canary_env, session_factory, cp, router=router,
                  adapter=_positioned_adapter("18"))
    await run.step_a3()
    assert router.submits == 0                                   # no second BUY
    assert _named(run)["A3.new_risk_refused"] == "PASS"


async def test_repeated_a2_retries_produce_exactly_one_order(canary_env, session_factory):
    # Two runs sharing the SAME run id (a retry) submit the protected-leg SELL exactly once — the
    # second finds the first's order by its deterministic client id.
    await _seed_account(session_factory)
    cp1 = canary_env.Checkpoint.load()
    router = _DbRouter(session_factory)
    run1 = _canary(canary_env, session_factory, cp1, router=router,
                   adapter=_positioned_adapter("19"))
    await run1.step_a2()
    assert router.submits == 1
    # Retry: same identity, completed-step record lost, pre-submit intent survived.
    cp2 = canary_env.Checkpoint(run_id=cp1.run_id, steps={"A2_intent": cp1.intent("A2")})
    run2 = _canary(canary_env, session_factory, cp2, router=router,
                   adapter=_positioned_adapter("18"))
    await run2.step_a2()
    assert router.submits == 1                                   # still exactly one order
    async with session_factory() as s:
        from sqlalchemy import func, select
        n = await s.scalar(select(func.count()).select_from(Order).where(
            Order.client_order_id == cp1.client_id("A2")))
    assert n == 1


async def test_a2_deterministic_id_wrong_fields_refuses(canary_env, session_factory):
    # An order carrying the A2 identity but with the WRONG side is a contradiction → refuse.
    await _seed_account(session_factory)
    cp = canary_env.Checkpoint.load()
    await _seed_order(session_factory, oid=1, side=OrderSide.BUY, status=OrderStatus.SUBMITTED,
                      client_order_id=cp.client_id("A2"))
    run = _canary(canary_env, session_factory, cp)
    with pytest.raises(canary_env.CanaryRefused):
        await run.step_a2()


async def test_fresh_a2_submits_exactly_once(canary_env, session_factory):
    await _seed_account(session_factory)
    cp = canary_env.Checkpoint.load()
    router = _DbRouter(session_factory)
    run = _canary(canary_env, session_factory, cp, router=router,
                  adapter=_positioned_adapter("19"))
    await run.step_a2()
    assert router.submits == 1 and _named(run)["A2.verified_reduction_allowed"] == "PASS"


async def test_a2_refuses_when_the_leg_is_not_actually_held(canary_env, session_factory):
    """No position, no reduction to verify — refuse rather than submit a sell that would OPEN a
    short, which is the opposite of what A2 is supposed to prove."""
    await _seed_account(session_factory)
    router = _DbRouter(session_factory)
    run = _canary(canary_env, session_factory, canary_env.Checkpoint.load(), router=router,
                  adapter=_positioned_adapter("0"))
    with pytest.raises(canary_env.CanaryRefused):
        await run.step_a2()
    assert router.submits == 0


async def test_a4_passes_the_stable_idempotency_key(canary_env, session_factory):
    await _seed_account(session_factory)
    cp = canary_env.Checkpoint.load()
    recovery = _FakeRecovery()
    run = _canary(canary_env, session_factory, cp, recovery=recovery)
    await run.step_a4()
    assert recovery.requests == 1 and recovery.keys == [cp.idempotency_key]


async def test_resume_during_a4_reuses_the_preflight_not_a_new_request(canary_env, session_factory):
    await _seed_account(session_factory)
    cp = canary_env.Checkpoint.load()
    cp.record_step("A4", preflight_id=1)
    recovery = _FakeRecovery()
    run = _canary(canary_env, session_factory, cp, recovery=recovery)
    await run.step_a4()
    assert recovery.requests == 0                                # reused the recorded preflight


# ---- the completed run resumes cleanly (before mutable preconditions), no side effects ----


async def _seed_completed(session_factory, canary_env, cp, out_path):
    from datetime import UTC as _UTC
    from datetime import datetime as _dt
    now = _dt.now(_UTC)
    await _seed_account(session_factory)
    await _seed_order(session_factory, oid=1, side=OrderSide.SELL, status=OrderStatus.SUBMITTED,
                      client_order_id=cp.client_id("A2"))
    await _seed_order(session_factory, oid=2, side=OrderSide.BUY, status=OrderStatus.REJECTED,
                      client_order_id=cp.client_id("A3"), reason="LOSS_CONTROL_STOP")
    async with session_factory() as s:
        s.add(RiskLossControlState(account_id=3, state="RECOVERY_COOLDOWN", state_version=5,
                                   last_sequence_no=4, control_version=1, updated_at=now))
        s.add(RiskRecoveryPreflight(
            account_id=3, idempotency_key="k", requested_transition="RECOVERY_REQUEST",
            expected_state_version=4, requested_by_actor_type="OWNER", requested_by_actor_id="3",
            requested_at=now, origin_state="REDUCTION_ONLY_DAILY_LOSS", origin_state_version=4,
            trip_cause="REALIZED_AND_MARK_TO_MARKET_LOSS",
            authority_class="OWNER_OR_OPERATOR", status="PASSED", result="PASSED",
            aggregate_verdict="PASS", initiator_type="OWNER", initiator_id="3", control_version=1,
            evidence_version=1, created_at=now))
        for i in range(12):
            s.add(RiskRecoveryPreflightCheck(preflight_id=1, check_name=f"c{i}", status="PASS",
                                             created_at=now))
        await s.commit()
    out_path.write_text('{"gate": "PASS"}', encoding="utf-8")
    cp.steps["run_start_event_id"] = 0
    for step in ("A1", "A2", "A3"):
        cp.record_step(step)
    cp.record_step("A4", preflight_id=1)
    cp.record_step("A5", verdict="HOLD", transitioned_to=None)
    cp.completed_gate = "PASS"
    cp.completed_digest = hashlib.sha256(out_path.read_bytes()).hexdigest()
    cp.save()


async def test_completed_run_returns_gate_with_no_side_effects(canary_env, session_factory,
                                                               tmp_path):
    from scripts.adr0043_canary_run import _completed_or_none
    out = tmp_path / "ev.json"
    cp = canary_env.Checkpoint.load()
    await _seed_completed(session_factory, canary_env, cp, out)
    rc = await _completed_or_none(session_factory, None, cp, out)
    assert rc == 0                                               # PASS gate, returned without trading


async def test_completed_run_missing_order_refuses(canary_env, session_factory, tmp_path):
    from scripts.adr0043_canary_run import _completed_or_none
    out = tmp_path / "ev.json"
    cp = canary_env.Checkpoint.load()
    await _seed_completed(session_factory, canary_env, cp, out)
    async with session_factory() as s:  # delete the A2 order → durable contradiction
        from sqlalchemy import delete
        await s.execute(delete(Order).where(Order.client_order_id == cp.client_id("A2")))
        await s.commit()
    with pytest.raises(canary_env.CanaryRefused):
        await _completed_or_none(session_factory, None, cp, out)


async def test_completed_run_digest_mismatch_refuses(canary_env, session_factory, tmp_path):
    from scripts.adr0043_canary_run import _completed_or_none
    out = tmp_path / "ev.json"
    cp = canary_env.Checkpoint.load()
    await _seed_completed(session_factory, canary_env, cp, out)
    out.write_text('{"gate": "PASS", "tampered": true}', encoding="utf-8")  # digest now mismatches
    with pytest.raises(canary_env.CanaryRefused):
        await _completed_or_none(session_factory, None, cp, out)


async def test_completed_run_a5_not_hold_refuses(canary_env, session_factory, tmp_path):
    from scripts.adr0043_canary_run import _completed_or_none
    out = tmp_path / "ev.json"
    cp = canary_env.Checkpoint.load()
    await _seed_completed(session_factory, canary_env, cp, out)
    cp.record_step("A5", verdict="COMPLETE", transitioned_to="NORMAL")  # contradicts HOLD
    cp.completed_gate = "PASS"
    cp.save()
    with pytest.raises(canary_env.CanaryRefused):
        await _completed_or_none(session_factory, None, cp, out)


async def test_not_all_done_returns_none(canary_env, session_factory, tmp_path):
    from scripts.adr0043_canary_run import _completed_or_none
    cp = canary_env.Checkpoint.load()
    cp.record_step("A1")  # not all steps done
    rc = await _completed_or_none(session_factory, None, cp, tmp_path / "ev.json")
    assert rc is None


async def test_run_after_all_done_issues_no_side_effects(canary_env, session_factory):
    await _seed_account(session_factory)
    cp = canary_env.Checkpoint.load()
    for step in ("A1", "A2", "A3", "A4", "A5"):
        cp.record_step(step)
    router, recovery, evaluator = _DbRouter(session_factory), _FakeRecovery(), _FakeEvaluator()
    run = _canary(canary_env, session_factory, cp, router=router, recovery=recovery,
                  evaluator=evaluator)
    rc = await run.execute(pre=None, run_start_event_id=0)
    assert rc == 0
    assert router.submits == 0 and recovery.requests == 0 and evaluator.calls == 0


def test_client_id_is_stable_and_step_specific(canary_env):
    cp = canary_env.Checkpoint.load()
    assert cp.client_id("A2") == canary_env.Checkpoint.load().client_id("A2")  # stable
    assert cp.client_id("A2") != cp.client_id("A3")                            # step-specific
    assert cp.client_id("A2").startswith("adr0043-")


# ================================================================ step 2: the settlement barrier
# A2 is formal evidence in its own right: an ALLOW that never reached the account is not a passing
# A2. These prove the harness cannot record a green reduction it did not settle, that A3 never runs
# on an unsettled ledger, and that a refusal which somehow reached the broker stops the run.


def test_assess_a2_green_only_on_a_fully_settled_reduction(canary_env):
    ok, _ = canary_env.assess_a2_settlement(
        broker_status="filled", local_status="filled", fill_count=1, booked_qty=D("1"),
        local_position=D("18"), broker_position=D("18"), expected_position=D("18"),
        reservation_states=["CONSUMED"])
    assert ok is True


@pytest.mark.parametrize("over", [
    {"broker_status": "new"},                      # broker never reached terminal
    {"broker_status": "canceled"},                 # terminal, but the reduction did not happen
    {"local_status": "submitted"},                 # broker filled, local ledger behind — attempt 2
    {"local_status": "partially_filled"},
    {"fill_count": 0},                             # nothing booked locally
    {"fill_count": 2},                             # not a single clean fill delta
    {"booked_qty": D("0")},
    {"local_position": D("19")},                   # local position never moved
    {"broker_position": D("19")},                  # broker position never moved
    {"local_position": D("18"), "broker_position": D("17")},   # the two ledgers disagree
    {"reservation_states": ["HELD"]},              # capacity still held by a finished order
    {"reservation_states": ["CONSUMED", "HELD"]},  # a second reservation leaked
])
def test_assess_a2_is_red_when_the_reduction_is_not_settled(canary_env, over):
    base = dict(broker_status="filled", local_status="filled", fill_count=1, booked_qty=D("1"),
                local_position=D("18"), broker_position=D("18"), expected_position=D("18"),
                reservation_states=["CONSUMED"])
    base.update(over)
    ok, _ = canary_env.assess_a2_settlement(**base)
    assert ok is False, f"A2 must be RED for {over}"


def test_assess_a3_green_only_when_nothing_reached_the_broker(canary_env):
    ok, _ = canary_env.assess_a3_no_submission(
        rejected=True, reason="LOSS_CONTROL_STOP", broker_order_id=None, local_status="rejected",
        local_position=D("18"), broker_position=D("18"), expected_position=D("18"),
        reservation_count=0)
    assert ok is True


@pytest.mark.parametrize("over", [
    {"rejected": False},                                  # admitted when it should be refused
    {"reason": "CIRCUIT_BREAKER"},                        # refused, but for the wrong reason
    {"reason": ""},
    {"broker_order_id": "b-999"},                         # a refusal that still reached the broker
    {"local_status": "submitted"},                        # a live local order was created
    {"local_position": D("19")},                          # the position moved
    {"broker_position": D("17")},
    {"reservation_count": 1},                             # capacity reserved for a refused order
])
def test_assess_a3_is_red_on_any_submission_evidence(canary_env, over):
    base = dict(rejected=True, reason="LOSS_CONTROL_STOP", broker_order_id=None,
                local_status="rejected", local_position=D("18"), broker_position=D("18"),
                expected_position=D("18"), reservation_count=0)
    base.update(over)
    ok, _ = canary_env.assess_a3_no_submission(**base)
    assert ok is False, f"A3 must be RED for {over}"


# ---- the A2 → settle → A3 sequencing ----


class _SettleSpy:
    """Records the order in which the barrier was invoked, and can be made to fail."""

    def __init__(self, *, fail=False, result=None):
        self.calls: list[int] = []
        self.fail = fail
        self.result = result or SimpleNamespace(
            broker_status="filled", local_status="filled", filled_qty=D("1"),
            local_position=D("18"), broker_position=D("18"), polls=1)

    async def __call__(self, sf, adapter, consumer, *, order_id, ticker, timeout_s=None):
        self.calls.append(order_id)
        if self.fail:
            from app.orders.settlement import SettlementError
            raise SettlementError(f"order {order_id}: still non-terminal at broker (new) after 45s")
        return self.result


def _positioned_adapter(qty="18"):
    a = MagicMock()
    a.get_positions.return_value = [{"symbol": "F", "qty": qty}]
    a.list_orders.return_value = []
    a.get_order.return_value = {"status": "new", "filled_qty": "0"}
    return a


async def _seed_settled_position(session_factory, qty="18"):
    """The local position row A2's verification reads back."""
    from app.db.models.position import Position
    async with session_factory() as s:
        s.add(Position(user_id=3, account_id=3, symbol_id=1, qty=D(qty),
                       avg_entry_price=D("10"), side="long", market_value=D("0"),
                       cost_basis=D("10"), unrealized_pl=D("0"), unrealized_plpc=D("0"),
                       updated_at=datetime.now(UTC)))
        await s.commit()


async def _seed_fill(session_factory, order_id, qty="1"):
    from app.db.models.fill import Fill
    async with session_factory() as s:
        s.add(Fill(order_id=order_id, broker_fill_id=f"x-{order_id}", qty=D(qty), price=D("10"),
                   commission=D("0"), filled_at=datetime.now(UTC)))
        await s.commit()


async def test_a2_settles_before_it_reports_a_green_reduction(canary_env, session_factory,
                                                              monkeypatch):
    """The happy path, end to end through the harness: submit → settle → verify against the
    durable record. The barrier must have been called with A2's own order id."""
    await _seed_account(session_factory)
    adapter = _positioned_adapter("19")          # pre-order broker position
    cp = canary_env.Checkpoint.load()
    settle = _SettleSpy()
    run = _canary(canary_env, session_factory, cp, adapter=adapter, settle=settle)

    # After the submit the broker (and the local ledger) reflect the settled reduction.
    router = run.router
    real_submit = router.submit

    async def _submit_then_settle(req):
        o = await real_submit(req)
        adapter.get_positions.return_value = [{"symbol": "F", "qty": "18"}]
        await _seed_fill(session_factory, o.id)
        await _seed_settled_position(session_factory, "18")
        async with session_factory() as s:
            from sqlalchemy import update
            await s.execute(update(Order).where(Order.id == o.id).values(
                status=OrderStatus.FILLED, terminal_at=datetime.now(UTC)))
            await s.commit()
        return o

    monkeypatch.setattr(router, "submit", _submit_then_settle)
    await run.step_a2()

    assert settle.calls == [cp.step_data("A2")["order_id"]]     # barrier ran on A2's order
    names = {a["name"]: a["result"] for a in run.ev.doc["assertions"]}
    assert names["A2.verified_reduction_allowed"] == "PASS"
    assert names["A2.reduction_settled"] == "PASS"
    assert run.ev.doc["settlements"][0]["outcome"] == "SETTLED"


async def test_a2_records_its_intent_before_submitting(canary_env, session_factory):
    """The pre-submit intent closes the crash window: a resumed run must be able to say what the
    position SHOULD settle to without re-deriving it from a ledger that has since moved."""
    await _seed_account(session_factory)
    adapter = _positioned_adapter("19")
    cp = canary_env.Checkpoint.load()

    class _Boom:
        submits = 0

        async def submit(self, req):
            raise RuntimeError("crashed at submit")

    run = _canary(canary_env, session_factory, cp, adapter=adapter, router=_Boom())
    with pytest.raises(RuntimeError):
        await run.step_a2()

    intent = canary_env.Checkpoint.load().intent("A2")
    assert intent["pre_position"] == "19" and intent["expected_position"] == "18"


async def test_a2_rebind_without_recorded_intent_refuses(canary_env, session_factory):
    """A rebound order whose expected position was never recorded cannot be verified. Refuse —
    do not assume the arithmetic."""
    await _seed_account(session_factory)
    cp = canary_env.Checkpoint.load()
    await _seed_order(session_factory, oid=1, side=OrderSide.SELL, status=OrderStatus.SUBMITTED,
                      client_order_id=cp.client_id("A2"))
    run = _canary(canary_env, session_factory, cp, adapter=_positioned_adapter("18"))
    with pytest.raises(canary_env.CanaryRefused):
        await run.step_a2()


async def test_a2_barrier_failure_stops_the_run_before_a3(canary_env, session_factory):
    """THE regression test for the Phase-0 failure: when the barrier cannot settle A2, the run
    raises SETTLEMENT_BARRIER_FAILED and A3 is never attempted."""
    await _seed_account(session_factory)
    adapter = _positioned_adapter("19")
    cp = canary_env.Checkpoint.load()
    router = _DbRouter(session_factory)
    run = _canary(canary_env, session_factory, cp, adapter=adapter, router=router,
                  settle=_SettleSpy(fail=True))

    with pytest.raises(canary_env.SettlementBarrierFailed) as exc:
        await run.execute(pre=_snap(canary_env, positions={"F": D("19")}), run_start_event_id=0)

    assert exc.value.stop_reason == "SETTLEMENT_BARRIER_FAILED"
    assert router.submits == 1, "only A2 was submitted — A3 must never have run"
    assert not cp.step_done("A3")


async def test_barrier_failure_records_credential_free_diagnostics(canary_env, session_factory):
    """A failed barrier must leave enough to diagnose it without re-running anything — and must
    not carry a credential into the evidence file."""
    await _seed_account(session_factory)
    adapter = _positioned_adapter("19")
    cp = canary_env.Checkpoint.load()
    await _seed_order(session_factory, oid=1, side=OrderSide.SELL, status=OrderStatus.SUBMITTED,
                      client_order_id=cp.client_id("A2"))
    run = _canary(canary_env, session_factory, cp, adapter=adapter, settle=_SettleSpy(fail=True))

    with pytest.raises(canary_env.SettlementBarrierFailed) as exc:
        await run.settle("A2", order_id=1, ticker="F")

    diag = exc.value.diagnostics
    for field in ("local_order_id", "broker_order_id", "broker_status", "broker_filled_qty",
                  "local_filled_qty", "local_order_status", "local_position", "broker_position",
                  "reservation_states", "elapsed_s", "exception_category", "stop_reason"):
        assert field in diag, f"diagnostics missing {field}"
    assert diag["stop_reason"] == "SETTLEMENT_BARRIER_FAILED"
    assert diag["exception_category"] == "SettlementError"
    blob = json.dumps(diag).lower()
    assert "secret" not in blob and "api_key" not in blob and "password" not in blob


async def test_diagnostics_survive_an_unreachable_broker(canary_env, session_factory):
    """The most likely cause of a barrier failure is a broker we cannot reach — so the collector
    must not itself fail on the same broker."""
    await _seed_account(session_factory)
    await _seed_order(session_factory, oid=1, side=OrderSide.SELL, status=OrderStatus.SUBMITTED,
                      client_order_id="x")
    adapter = MagicMock()
    adapter.get_positions.side_effect = ConnectionError("reset")
    adapter.get_order.side_effect = ConnectionError("reset")

    diag = await canary_env.settlement_diagnostics(
        session_factory, adapter, step="A2", order_id=1, ticker="F",
        exception_category="SettlementError", detail="unreachable")

    assert diag["broker_position"].startswith("UNAVAILABLE:")
    # The local half is still recorded — that is the point of collecting both independently.
    assert str(diag["local_order_status"]).lower() == "submitted"


async def test_a3_stops_the_run_if_a_broker_order_somehow_exists(canary_env, session_factory):
    """A refusal that reached the broker is not a refusal. The run reconciles the unplanned order
    through the canonical settlement path and STOPS rather than continuing to A4."""
    await _seed_account(session_factory)
    cp = canary_env.Checkpoint.load()
    cp.record_intent("A2", pre_position="19", expected_position="18", ledger_since=0)

    class _LeakyRouter(_DbRouter):
        async def submit(self, req):
            o = await super().submit(req)
            return SimpleNamespace(id=o.id, status="rejected",
                                   rejection_reason="LOSS_CONTROL_STOP",
                                   broker_order_id="b-leaked")

    settle = _SettleSpy()
    run = _canary(canary_env, session_factory, cp, adapter=_positioned_adapter("18"),
                  router=_LeakyRouter(session_factory), settle=settle)

    with pytest.raises(canary_env.CanaryStop) as exc:
        await run.step_a3()

    assert exc.value.stop_reason == "A3_UNEXPECTED_BROKER_SUBMISSION"
    assert settle.calls, "the unplanned order must be reconciled through the canonical barrier"
    names = {a["name"]: a["result"] for a in run.ev.doc["assertions"]}
    assert names["A3.no_broker_submission"] == "FAIL"


async def test_a3_refuses_without_a_settled_a2_intent(canary_env, session_factory):
    """A3's "MSFT is unchanged" claim is meaningless without the settled figure it compares to."""
    await _seed_account(session_factory)
    cp = canary_env.Checkpoint.load()          # no A2 intent recorded
    run = _canary(canary_env, session_factory, cp, adapter=_positioned_adapter("18"))
    with pytest.raises(canary_env.CanaryRefused):
        await run.step_a3()


async def test_a3_green_path_asserts_no_submission(canary_env, session_factory):
    await _seed_account(session_factory)
    await _seed_settled_position(session_factory, "18")
    cp = canary_env.Checkpoint.load()
    cp.record_intent("A2", pre_position="19", expected_position="18", ledger_since=0)
    run = _canary(canary_env, session_factory, cp, adapter=_positioned_adapter("18"),
                  router=_DbRouter(session_factory))

    await run.step_a3()

    names = {a["name"]: a["result"] for a in run.ev.doc["assertions"]}
    assert names["A3.no_broker_submission"] == "PASS"
    assert names["A3.new_risk_refused"] == "PASS"


def test_settlement_timeout_is_bounded_and_positive(canary_env):
    """A barrier that waits forever hangs the run past its budget; one that gives up instantly
    manufactures false stops."""
    assert 5 <= canary_env.SETTLEMENT_TIMEOUT_S <= 300
