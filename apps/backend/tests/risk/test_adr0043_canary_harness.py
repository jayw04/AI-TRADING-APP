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


class _FakeRouter:
    def __init__(self):
        self.submits = 0

    async def submit(self, req):
        self.submits += 1
        return SimpleNamespace(id=999, status="submitted", rejection_reason=None)


class _FakeRecovery:
    def __init__(self):
        self.requests = 0

    async def request_recovery(self, **kw):
        self.requests += 1
        return SimpleNamespace(preflight_id=1, status="PASSED")


class _FakeEvaluator:
    def __init__(self):
        self.calls = 0

    async def evaluate(self, account_id, **kw):
        self.calls += 1
        return SimpleNamespace(verdict="HOLD", transitioned_to=None, account_id=account_id)


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


async def _seed_order(session_factory, *, oid, side, status, reason=None):
    async with session_factory() as s:
        s.add(Order(id=oid, user_id=3, account_id=3, symbol_id=1, client_order_id=f"c{oid}",
                    side=side, qty=D("1"), type=OrderType.MARKET, tif=TimeInForce.DAY,
                    status=status, source_type=OrderSourceType.STRATEGY, rejection_reason=reason,
                    created_at=datetime.now(UTC), updated_at=datetime.now(UTC)))
        await s.commit()


def _run(canary_env, session_factory, cp, **collab):
    from scripts.adr0043_canary_run import CanaryRun
    return CanaryRun(
        sf=session_factory, adapter=None,
        router=collab.get("router", _FakeRouter()),
        recovery=collab.get("recovery", _FakeRecovery()),
        evaluator=collab.get("evaluator", _FakeEvaluator()),
        evidence=canary_env.Evidence(phase="TEST"), checkpoint=cp)


async def test_resume_after_a2_does_not_resubmit(canary_env, session_factory):
    await _seed_account(session_factory)
    await _seed_order(session_factory, oid=1, side=OrderSide.SELL, status=OrderStatus.SUBMITTED)
    cp = canary_env.Checkpoint()
    cp.record_step("A2", order_id=1)
    router = _FakeRouter()
    run = _run(canary_env, session_factory, cp, router=router)
    await run.step_a2()
    assert router.submits == 0                        # no second protected-leg SELL
    assert run.ev.doc["assertions"][-1]["result"] == "PASS"


async def test_resume_after_a3_does_not_resubmit(canary_env, session_factory):
    await _seed_account(session_factory)
    await _seed_order(session_factory, oid=2, side=OrderSide.BUY, status=OrderStatus.REJECTED,
                      reason="LOSS_CONTROL_STOP")
    cp = canary_env.Checkpoint()
    cp.record_step("A3", order_id=2)
    router = _FakeRouter()
    run = _run(canary_env, session_factory, cp, router=router)
    await run.step_a3()
    assert router.submits == 0                        # no second new-risk BUY
    assert run.ev.doc["assertions"][-1]["result"] == "PASS"


async def test_a2_checkpoint_contradicting_durable_evidence_refuses(canary_env, session_factory):
    await _seed_account(session_factory)
    # Checkpoint says A2 sold order 1, but order 1 is a BUY — a contradiction → refuse, not restart.
    await _seed_order(session_factory, oid=1, side=OrderSide.BUY, status=OrderStatus.SUBMITTED)
    cp = canary_env.Checkpoint()
    cp.record_step("A2", order_id=1)
    run = _run(canary_env, session_factory, cp)
    with pytest.raises(canary_env.CanaryRefused):
        await run.step_a2()


async def test_a3_missing_durable_order_refuses(canary_env, session_factory):
    await _seed_account(session_factory)  # no order 5 exists
    cp = canary_env.Checkpoint()
    cp.record_step("A3", order_id=5)
    run = _run(canary_env, session_factory, cp)
    with pytest.raises(canary_env.CanaryRefused):
        await run.step_a3()


async def test_resume_during_a4_reuses_the_preflight_not_a_new_request(canary_env, session_factory):
    await _seed_account(session_factory)
    cp = canary_env.Checkpoint()
    cp.record_step("A4", preflight_id=1)
    recovery = _FakeRecovery()
    run = _run(canary_env, session_factory, cp, recovery=recovery)
    await run.step_a4()
    assert recovery.requests == 0                     # reused the recorded preflight, no new request


async def test_run_after_all_done_issues_no_side_effects(canary_env, session_factory):
    await _seed_account(session_factory)
    cp = canary_env.Checkpoint()
    for step in ("A1", "A2", "A3", "A4", "A5"):
        cp.record_step(step)
    router, recovery, evaluator = _FakeRouter(), _FakeRecovery(), _FakeEvaluator()
    run = _run(canary_env, session_factory, cp, router=router, recovery=recovery, evaluator=evaluator)
    rc = await run.execute(pre=None, run_start_event_id=0)
    assert rc == 0
    assert router.submits == 0 and recovery.requests == 0 and evaluator.calls == 0


def test_a4_idempotency_key_is_stable_across_reload(canary_env):
    cp = canary_env.Checkpoint.load()
    key = cp.idempotency_key
    assert key and canary_env.Checkpoint.load().idempotency_key == key  # a retry reuses the key
