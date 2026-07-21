"""ADR 0043 canary harness — the ways a harness could LIE, as regression tests.

Like the ADR 0042 harness tests, none of these is about the risk engine; every one is about the
harness not asserting a green it didn't earn. They run offline (no broker, no box). The blocker-2
tests prove that a GREEN canary REQUIRES actually reaching RECOVERY_COOLDOWN and holding there; the
blocker-1 tests prove the run is truly step-level resumable and idempotent (a retry never re-issues a
completed side effect).
"""

from __future__ import annotations

import importlib
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
        evidence=canary_env.Evidence(phase="TEST"), checkpoint=cp)


# ---- the post-submit / pre-checkpoint crash window ----


async def test_a2_rebinds_to_existing_order_when_checkpoint_absent(canary_env, session_factory):
    # The order was submitted (durably) but the checkpoint write was lost. A retry must REBIND to the
    # existing deterministic identity, not submit a second protected-leg SELL.
    await _seed_account(session_factory)
    cp = canary_env.Checkpoint.load()
    await _seed_order(session_factory, oid=1, side=OrderSide.SELL, status=OrderStatus.SUBMITTED,
                      client_order_id=cp.client_id("A2"))  # checkpoint has NO A2 recorded
    router = _DbRouter(session_factory)
    run = _canary(canary_env, session_factory, cp, router=router)
    await run.step_a2()
    assert router.submits == 0                                   # no second SELL
    assert run.ev.doc["assertions"][-1]["result"] == "PASS"
    assert cp.step_done("A2")


async def test_a3_rebinds_to_existing_rejected_order_when_checkpoint_absent(canary_env,
                                                                            session_factory):
    await _seed_account(session_factory)
    cp = canary_env.Checkpoint.load()
    await _seed_order(session_factory, oid=2, side=OrderSide.BUY, status=OrderStatus.REJECTED,
                      client_order_id=cp.client_id("A3"), reason="LOSS_CONTROL_STOP")
    router = _DbRouter(session_factory)
    run = _canary(canary_env, session_factory, cp, router=router)
    await run.step_a3()
    assert router.submits == 0                                   # no second BUY
    assert run.ev.doc["assertions"][-1]["result"] == "PASS"


async def test_repeated_a2_retries_produce_exactly_one_order(canary_env, session_factory):
    # Two runs sharing the SAME run id (a retry) submit the protected-leg SELL exactly once — the
    # second finds the first's order by its deterministic client id.
    await _seed_account(session_factory)
    cp1 = canary_env.Checkpoint.load()
    router = _DbRouter(session_factory)
    run1 = _canary(canary_env, session_factory, cp1, router=router)
    await run1.step_a2()
    assert router.submits == 1
    cp2 = canary_env.Checkpoint(run_id=cp1.run_id)                # retry: same identity, lost steps
    run2 = _canary(canary_env, session_factory, cp2, router=router)
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
    run = _canary(canary_env, session_factory, cp, router=router)
    await run.step_a2()
    assert router.submits == 1 and run.ev.doc["assertions"][-1]["result"] == "PASS"


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
