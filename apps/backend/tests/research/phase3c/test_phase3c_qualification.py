"""Phase 3C qualification — NON-SEALED fixtures only.

Required by owner ruling R5A before any sealed-opening request. Nothing here reads the validation
or OOS partitions; every input is synthetic or development-window.

The build_joint-dependent tests need the frozen research image, because joint_portfolio refuses to
run unless /manifest/pip_report.json pins quadprog to the registered artifact. That refusal is a
control, not an obstacle, so the tests skip rather than weaken it:

    docker run --rm --network=none -v "$PWD:/work" -w /work/apps/backend \\
        mr002-research:v1.4 python -m pytest tests/research/phase3c -q
"""

from __future__ import annotations

import os
from datetime import date, timedelta

import numpy as np
import pytest

from app.research.mr002.execution import EXIT_Z, MAX_HOLD_SESSIONS, exit_reason
from app.research.mr002.phase3c import NAV0, IntegrityFailure, adopted, folds, gates
from app.research.mr002.phase3c.exits import RETIRED_TRIGGER, exit_reason_validation

FROZEN_RUNTIME = os.path.exists("/manifest/pip_report.json")
needs_frozen_runtime = pytest.mark.skipif(
    not FROZEN_RUNTIME,
    reason="joint_portfolio requires the frozen research image (/manifest/pip_report.json)",
)


# ----------------------------------------------------------------- adoption binding (ruling R5A)

def test_adoption_binding_verifies():
    info = adopted.verify_binding()
    assert info["runner_sha256"] == adopted.ADOPTED_RUNNER_SHA256
    assert info["mechanics_block_sha256"] == adopted.MECHANICS_BLOCK_SHA256


def test_adoption_binding_is_fail_closed(tmp_path, monkeypatch):
    """A drifted adopted file must be fatal, not silently tolerated."""
    tampered = tmp_path / "mr002_development_run.py"
    tampered.write_bytes(adopted.runner_path().read_bytes() + b"\n# tampered\n")
    monkeypatch.setattr(adopted, "runner_path", lambda: tampered)
    with pytest.raises(adopted.AdoptionBindingViolation):
        adopted.verify_binding()


# ----------------------------------------------------------------- ruling 1: retired exit trigger

def test_retired_trigger_is_absent_from_the_signature():
    import inspect

    params = list(inspect.signature(exit_reason_validation).parameters)
    assert "confirm" not in params, "the retired trigger's input must not survive"
    assert RETIRED_TRIGGER == "exit_hypothesis_failure"


@pytest.mark.parametrize("z_now", [-5.0, -3.6, -3.5, -1.0, -0.35, 0.0, 0.35, 3.5, 4.2, np.nan])
@pytest.mark.parametrize("held", [1, 4, 5, 6])
@pytest.mark.parametrize("blackout", [False, True])
@pytest.mark.parametrize("action", [False, True])
def test_validation_ladder_equals_frozen_ladder_with_confirm_false(z_now, held, blackout, action):
    """Retiring the trigger is behaviour-preserving relative to what actually ran.

    `confirm` was never populated in the accepted runner, so the frozen ladder always saw
    confirm=False. The validation ladder must agree with it on every input.
    """
    assert exit_reason_validation(z_now, held, blackout, action) == exit_reason(
        z_now, held, blackout, action, False)


def test_ladder_ordering_preserved():
    # blackout outranks corporate action outranks z-revert outranks time stop
    assert exit_reason_validation(0.0, 99, True, True) == "exit_earnings_blackout"
    assert exit_reason_validation(0.0, 99, False, True) == "exit_corporate_action"
    assert exit_reason_validation(0.0, 99, False, False) == "exit_z_reverted"
    assert exit_reason_validation(9.9, MAX_HOLD_SESSIONS, False, False) == "exit_time_stop"
    assert exit_reason_validation(9.9, MAX_HOLD_SESSIONS - 1, False, False) is None
    # a |z| beyond 3.5 no longer produces an exit of its own
    assert exit_reason_validation(4.0, 1, False, False) is None
    assert abs(EXIT_Z - 0.35) < 1e-12


# ----------------------------------------------------------------- folds

def _sessions_for_frozen_folds() -> list[date]:
    """Build a session list that reproduces the frozen 155-per-fold structure exactly."""
    out: list[date] = []
    for f in folds.FROZEN_FOLDS:
        d, made = f.first, 0
        while made < f.sessions:
            if d.weekday() < 5:
                out.append(d)
                made += 1
            d += timedelta(days=1)
    return out


def test_fold_boundaries_are_the_frozen_literals():
    assert [(f.index, str(f.first), str(f.last)) for f in folds.FROZEN_FOLDS] == [
        (1, "2020-01-13", "2020-08-21"),
        (2, "2020-08-24", "2021-04-06"),
        (3, "2021-04-07", "2021-11-12"),
        (4, "2021-11-15", "2022-06-28"),
        (5, "2022-06-29", "2023-02-08"),
    ]
    assert sum(f.sessions for f in folds.FROZEN_FOLDS) == folds.EXPECTED_ELIGIBLE_SESSIONS == 775


def test_fold_assignment_is_contiguous_and_total():
    sessions = _sessions_for_frozen_folds()
    report = folds.verify_assignment(sessions)
    assert report["eligible_sessions_observed"] == 775
    assert all(f["observed_sessions"] == 155 for f in report["folds"])


def test_short_fold_is_an_integrity_failure():
    sessions = _sessions_for_frozen_folds()
    del sessions[0]                                     # one session short in fold 1
    with pytest.raises(IntegrityFailure) as exc:
        folds.verify_assignment(sessions)
    assert exc.value.code == "FOLD_ASSIGNMENT_MISMATCH"


def test_sessions_outside_the_scoring_span_are_not_assigned():
    assert folds.fold_of(date(2019, 10, 3)) is None      # formation lead-in
    assert folds.fold_of(date(2023, 2, 16)) is None      # past the scoring-eligible last
    assert folds.fold_of(date(2020, 1, 13)) == 1


# ----------------------------------------------------------------- gates

def _curve(returns: list[float]) -> list[float]:
    nav, out = NAV0, []
    for r in returns:
        nav *= 1.0 + r
        out.append(nav)
    return out


def test_fold_returns_use_the_nav_ratio():
    sessions = _sessions_for_frozen_folds()
    rets = [0.001] * len(sessions)
    per = gates.fold_net_returns(sessions, _curve(rets))
    assert all(v["sessions"] == 155 for v in per.values())
    assert all(v["net_positive"] for v in per.values())
    # compounding 155 sessions of +0.1% must reproduce the fold ratio
    assert per[1]["net_return"] == pytest.approx(1.001 ** 155 - 1.0, rel=1e-12)


def test_three_of_five_gate_boundary():
    sessions = _sessions_for_frozen_folds()
    # folds 1,2,3 positive; 4,5 negative
    rets = []
    for s in sessions:
        f = folds.fold_of(s)
        rets.append(0.001 if f in (1, 2, 3) else -0.001)
    per_config = {
        "A": {"sessions": sessions, "nav_curve": _curve([0.001] * len(sessions)),
              "daily_ret": [0.001] * len(sessions)},
        "B": {"sessions": sessions, "nav_curve": _curve(rets), "daily_ret": rets},
        "C": {"sessions": sessions, "nav_curve": _curve([0.001] * len(sessions)),
              "daily_ret": [0.001] * len(sessions)},
    }
    out = gates.evaluate(per_config, integrity_ok=True)
    assert out["gate_validation_positive_folds_ge_3_of_5"]["observed_positive_folds"] == 3
    assert out["verdict"] == "VALIDATION_ADVANCE_REQUEST"


def test_two_of_five_fails_the_fold_gate():
    sessions = _sessions_for_frozen_folds()
    rets = [0.001 if folds.fold_of(s) in (1, 2) else -0.001 for s in sessions]
    flat = [0.001] * len(sessions)
    per_config = {
        "A": {"sessions": sessions, "nav_curve": _curve(flat), "daily_ret": flat},
        "B": {"sessions": sessions, "nav_curve": _curve(rets), "daily_ret": rets},
        "C": {"sessions": sessions, "nav_curve": _curve(flat), "daily_ret": flat},
    }
    out = gates.evaluate(per_config, integrity_ok=True)
    assert out["gate_validation_positive_folds_ge_3_of_5"]["observed_positive_folds"] == 2
    assert out["verdict"] == "VALIDATION_DO_NOT_ADVANCE"


def test_parameter_stability_is_strictly_greater_than_zero():
    """A flat, never-trading config must FAIL the gate. Inactivity is not a pass."""
    sessions = _sessions_for_frozen_folds()
    good = [0.001] * len(sessions)
    flat = [0.0] * len(sessions)
    per_config = {
        "A": {"sessions": sessions, "nav_curve": _curve(good), "daily_ret": good},
        "B": {"sessions": sessions, "nav_curve": _curve(good), "daily_ret": good},
        "C": {"sessions": sessions, "nav_curve": _curve(flat), "daily_ret": flat},
    }
    out = gates.evaluate(per_config, integrity_ok=True)
    stab = out["gate_parameter_stability_A_and_C_net_profitable"]
    assert stab["per_config"]["C"]["cumulative_net_return"] == 0.0
    assert stab["per_config"]["C"]["net_profitable"] is False
    assert out["verdict"] == "VALIDATION_DO_NOT_ADVANCE"


def test_integrity_stop_is_not_an_economic_verdict():
    out = gates.evaluate({}, integrity_ok=False, integrity_detail="drift quantity undefined")
    assert out["verdict"] == "INTEGRITY_FAILURE"
    assert out["verdict"] != "VALIDATION_DO_NOT_ADVANCE"
    assert out["gates_evaluated"] is False


def test_oos_gates_are_never_evaluated():
    sessions = _sessions_for_frozen_folds()
    flat = [0.001] * len(sessions)
    cfg = {"sessions": sessions, "nav_curve": _curve(flat), "daily_ret": flat}
    out = gates.evaluate({"A": cfg, "B": cfg, "C": cfg}, integrity_ok=True)
    blob = repr(out)
    for forbidden in ("sharpe_point_estimate", "bootstrap_lower_bound", "dsr_significance"):
        assert forbidden not in blob or forbidden in repr(out["oos_gates_not_evaluated"])
    assert "net_oos_sharpe_ge_0.70" in out["oos_gates_not_evaluated"]


def test_annualized_sharpe_matches_the_frozen_estimator():
    r = [0.001, -0.002, 0.003, 0.0005, -0.001] * 20
    arr = np.array(r, dtype=float)
    expected = float(arr.mean() / arr.std(ddof=1) * np.sqrt(252.0))
    assert gates.annualized_net_sharpe(r) == pytest.approx(expected, rel=1e-12)
