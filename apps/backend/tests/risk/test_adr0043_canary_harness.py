"""ADR 0043 canary harness — the ways a harness could LIE, as regression tests.

Like the ADR 0042 harness tests, none of these is about the risk engine; every one is about the
harness not asserting a green it didn't earn. They run offline (no broker, no box).
"""

from __future__ import annotations

import importlib
from decimal import Decimal as D

import pytest


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
    # The reduction assertions SELL a protected leg; a leg that is not protected could be churned
    # away, producing a RED that has nothing to do with the engine.
    legs = {s for s, _ in lib.LEGS}
    assert legs and legs <= set(lib.PROTECTED), f"legs {legs - set(lib.PROTECTED)} not protected"


def test_churn_symbols_disjoint_from_legs(lib):
    assert not (set(lib.CHURN_SYMBOLS) & {s for s, _ in lib.LEGS})


# ---------------------------------------------------------------- the lock is MEASURED, not assumed


def test_reduction_only_reflects_the_durable_state_row(lib):
    # The lock is read from risk_loss_control_state, NOT inferred from day_change vs the cap — that
    # is the whole point of ADR 0043 (the machine is authoritative).
    assert _snap(lib).reduction_only is True
    assert _snap(lib, loss_control_state=lib.STATE_NORMAL).reduction_only is False
    assert _snap(lib, loss_control_state=lib.STATE_INTEGRITY_STOP).reduction_only is False
    # A missing state row is NOT a lock — it must not read as reduction-only.
    assert _snap(lib, loss_control_state=None).reduction_only is False


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
    # $50 price: qty cap (10) is tighter than every notional/gross/BP cap → 10, never enlarged.
    n = lib.admissible_shares(price=D("50"), limits=limits, gross_used=D("0"),
                              buying_power=D("1000000"), ceiling=D("1000000"))
    assert n == D("10")


def test_admissible_shares_zero_on_nonpositive_price(lib):
    limits = lib.Limits(None, None, None, None, None)
    assert lib.admissible_shares(price=D("0"), limits=limits, gross_used=D("0"),
                                 buying_power=D("1"), ceiling=D("1")) == D("0")


# ---------------------------------------------------------------- evidence cannot fake a PASS


def test_empty_assertions_is_not_a_pass(lib):
    # A run that asserted NOTHING must not report PASS (an early return could otherwise look green).
    ev = lib.Evidence(phase="ENFORCE")
    assert ev.passed() is False


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
    assert ev.passed() is True and len(digest) == 64
    import json
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
        pass  # a second concurrent harness must be refused
    # After the first releases, a new one may acquire.
    with lib.SingleInstance():
        pass


# ---------------------------------------------------------------- required mode


def test_required_mode_is_enforce(lib):
    # The canary asserts the AUTHORITATIVE path — it must require ENFORCE, never silently accept
    # OFF/SHADOW (under which the state machine contributes nothing).
    assert lib.REQUIRED_LOSS_CONTROL_MODE == "ENFORCE"


def test_loss_control_mode_reads_env(lib, monkeypatch):
    monkeypatch.setenv("WORKBENCH_LOSS_CONTROL_MODE", "shadow")
    import asyncio
    assert asyncio.run(lib.loss_control_mode(None)) == "SHADOW"


# ---------------------------------------------------------------- snapshot serialization


def test_snapshot_serializes_the_durable_state(lib):
    d = _snap(lib).as_dict()
    assert d["loss_control_state"] == lib.STATE_REDUCTION_ONLY_DAILY_LOSS
    assert d["reduction_only"] is True and d["loss_control_state_version"] == 3
    assert d["positions"] == {"F": "500", "MSFT": "20"}
