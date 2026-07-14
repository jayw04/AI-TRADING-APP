"""MR-002 v1.1 — the 15 REGISTERED CASCADE FIXTURES.

Implementation Erratum "Stage-3 Equivalent-Formulation Retry", countersigned 2026-07-12,
artifact sha256 9ce8f53a4367c5817881cab55d9550db058a171e8ee504f57ad6a7060fe378fb.

Suite total: 28 (existing) + 15 (here) = 43.

These run inside the frozen Linux/amd64 mr002-research image.
"""

from __future__ import annotations

import warnings

import numpy as np
import pytest
import quadprog

from app.research.mr002 import joint_portfolio as jp
from app.research.mr002.joint_portfolio import (
    FALSE_INCONSISTENCY,
    RAW,
    SCALED_RESCUE,
    InvalidRun,
    build_joint,
)

from .test_mr002_joint_solve import assert_constraints, diversified, hold

TOL = 1e-9


def stage3(res):
    return res.diagnostics["stage3"]


# --------------------------------------------------------------------------------------
# A small, well-conditioned Stage-3 instance used to drive the cascade deterministically.
# --------------------------------------------------------------------------------------
def base_book():
    hs = [hold(1, 1, 0.010, "XLK"), hold(2, -1, 0.008, "XLF"), hold(3, 1, 0.006, "XLV")]
    cs = diversified(6, start=300, offset=1)
    return hs, cs


class Boom(Exception):
    """Not a ValueError -- must never be treated as the rescue trigger."""


def force_raw(monkeypatch, exc):
    """Make ONLY the first (raw) quadprog call raise `exc`; let the retry through."""
    real = quadprog.solve_qp
    state = {"n": 0}

    def fake(H, a, C, b, meq):
        state["n"] += 1
        if state["n"] == 1:
            raise exc
        return real(H, a, C, b, meq)

    monkeypatch.setattr(jp.quadprog, "solve_qp", fake)
    return state


# ======================================================================================
# 1-2-3 · the happy path, the trigger, and the rescue
# ======================================================================================
def test_c01_raw_succeeds_and_the_scaled_path_is_never_invoked(monkeypatch):
    calls = {"probe": 0}
    real_lp = jp.linprog

    def spy_lp(*a, **k):
        # the Stage-3 feasibility probe is a ZERO objective; stages 1-2 are not
        if np.allclose(np.asarray(a[0] if a else k["c"], float), 0.0):
            calls["probe"] += 1
        return real_lp(*a, **k)

    monkeypatch.setattr(jp, "linprog", spy_lp)
    hs, cs = base_book()
    res = build_joint(hs, cs)
    assert stage3(res)["stage3_formulation"] == RAW
    assert stage3(res)["raw_exception_message"] is None
    assert calls["probe"] == 0, "the feasibility probe must not run when raw succeeds"


def test_c02_exact_false_inconsistency_triggers_the_highs_feasibility_probe(monkeypatch):
    probes = {"n": 0}
    real_lp = jp.linprog

    def spy_lp(*a, **k):
        c = np.asarray(a[0] if a else k["c"], float)
        if c.size and np.allclose(c, 0.0):
            probes["n"] += 1
        return real_lp(*a, **k)

    monkeypatch.setattr(jp, "linprog", spy_lp)
    force_raw(monkeypatch, ValueError(FALSE_INCONSISTENCY))
    hs, cs = base_book()
    res = build_joint(hs, cs)
    assert probes["n"] == 1, "the probe must run exactly once before the rescue"
    assert stage3(res)["feasibility_probe_status"] == 0


def test_c03_feasible_raw_region_is_rescued_by_the_scaled_formulation(monkeypatch):
    force_raw(monkeypatch, ValueError(FALSE_INCONSISTENCY))
    hs, cs = base_book()
    res = build_joint(hs, cs)
    s3 = stage3(res)
    assert s3["stage3_formulation"] == SCALED_RESCUE
    assert s3["raw_exception_class"] == "ValueError"
    assert s3["raw_exception_message"] == FALSE_INCONSISTENCY
    assert res.x, "the rescued solve must still produce orders"
    assert_constraints(res, hs, cs)


# ======================================================================================
# 4-5-6 · agreement, original-coordinate acceptance, multiplier transform
# ======================================================================================
def test_c04_raw_and_scaled_agree_within_tolerance_when_both_are_evaluated(monkeypatch):
    hs, cs = base_book()
    raw = build_joint(hs, cs)
    assert stage3(raw)["stage3_formulation"] == RAW

    force_raw(monkeypatch, ValueError(FALSE_INCONSISTENCY))
    resc = build_joint(hs, cs)
    assert stage3(resc)["stage3_formulation"] == SCALED_RESCUE

    for pt in set(raw.y) | set(resc.y):
        assert raw.y[pt] == pytest.approx(resc.y[pt], abs=1e-12)
    for pt in set(raw.x) | set(resc.x):
        assert raw.x[pt] == pytest.approx(resc.x[pt], abs=1e-12)
    assert stage3(raw)["raw_coordinate_objective"] == pytest.approx(
        stage3(resc)["raw_coordinate_objective"], rel=1e-9)


def test_c05_mapped_back_solution_passes_every_check_in_original_coordinates(monkeypatch):
    force_raw(monkeypatch, ValueError(FALSE_INCONSISTENCY))
    hs, cs = base_book()
    s3 = stage3(build_joint(hs, cs))
    assert s3["primal_residual"] <= jp.PRIMAL_RESIDUAL_MAX
    assert s3["dual_residual"] <= jp.DUAL_RESIDUAL_MAX
    assert s3["stationarity_residual"] <= jp.STATIONARITY_RESIDUAL_MAX
    assert s3["complementarity_residual"] <= jp.COMPLEMENTARITY_RESIDUAL_MAX
    assert s3["kkt_residual"] <= jp.KKT_RESIDUAL_MAX
    # scaled residuals are recorded, but are DIAGNOSTIC ONLY -- never the acceptance basis
    assert "scaled_coordinate_residuals_DIAGNOSTIC_ONLY" in s3


def test_c06_bound_multipliers_and_stationarity_transform_correctly():
    """mu_z,i = mu_u,i / t_i ; row multipliers keep their association.

    Verified directly on the algebra: with H_s = T H T, a_s = T a, u = T^-1 z, and the
    bound rows UNSCALED, stationarity in scaled coordinates implies
        H z - a = Aeq' l_eq - A' l_ineq + T^-1 (l_lo - l_hi).
    A rescue whose bound multipliers were NOT divided by t would blow the original-
    coordinate stationarity by a factor of ~1/t (up to 1e8 here).
    """
    # The objective's unconstrained optimum is z = t, i.e. ON the upper bound, where the
    # gradient VANISHES -- so upper-bound multipliers are always ~0 and the transform is
    # untestable there. A nonzero bound multiplier requires a variable driven hard onto its
    # LOWER bound. The row below charges variable 0 ten times the budget of the others,
    # which pushes its unconstrained optimum negative and clamps it at 0 with a nonzero
    # multiplier -- and t_0 = 1e-8 makes the 1/t amplification ~1e8.
    t = np.array([1.0e-8, 5.0e-3, 1.5e-2])
    n = 3
    A_ub = np.array([[10.0, 1.0, 1.0]])
    b_ub = np.array([0.01])
    A_eq = np.zeros((1, n))
    b_eq = np.zeros(1)
    upper = t.copy()

    H = np.diag(2.0 / t)
    a = 2.0 * np.ones(n)
    C, b = jp._qp_matrices(A_ub, b_ub, A_eq, b_eq, upper, n)

    T = np.diag(t)
    H_s, a_s = np.diag(2.0 * t), 2.0 * t
    C_s, b_s = jp._qp_matrices(A_ub @ T, b_ub, A_eq @ T, b_eq, upper / t, n)
    out = quadprog.solve_qp(H_s, a_s, C_s, b_s, 1)
    u, lam_u = np.asarray(out[0]), np.asarray(out[4])
    z = T @ u

    n_rows = 1 + A_ub.shape[0]
    lam_z = lam_u.copy()
    lam_z[n_rows:n_rows + n] /= t
    lam_z[n_rows + n:] /= t

    # The fixture is only meaningful if a bound multiplier is actually NONZERO.
    # Test it on the TRANSFORMED multiplier: in scaled coordinates mu_u = t * mu_z, so an
    # economically large mu_z (~8) appears as a tiny mu_u (~8e-8) precisely BECAUSE of the
    # scaling. Judging "is it active?" in scaled coordinates would be the same category
    # error the transform exists to correct.
    assert float(np.max(np.abs(lam_z[n_rows:]))) > 1.0, (
        "fixture is vacuous: no bound multiplier is active, so the 1/t transform is "
        "untestable here"
    )

    st_ok = float(np.max(np.abs(H @ z - a - C @ lam_z)))
    st_bad = float(np.max(np.abs(H @ z - a - C @ lam_u)))     # untransformed: WRONG
    assert st_ok <= jp.STATIONARITY_RESIDUAL_MAX, f"transformed stationarity {st_ok:.3e}"
    assert st_bad > jp.STATIONARITY_RESIDUAL_MAX, (
        f"the UNtransformed multipliers must FAIL stationarity, else the fixture proves "
        f"nothing: st_bad={st_bad:.3e}"
    )
    assert st_bad / max(st_ok, 1e-300) > 1e6, "the 1/t amplification is not being exercised"


# ======================================================================================
# 7-8-9-10-11 · everything that must stay FATAL
# ======================================================================================
def test_c07_non_positive_definite_exception_remains_immediately_fatal(monkeypatch):
    force_raw(monkeypatch, ValueError("matrix G is not positive definite"))
    hs, cs = base_book()
    with pytest.raises(InvalidRun, match="not the registered rescue trigger"):
        build_joint(hs, cs)


def test_c08_any_other_exception_message_remains_immediately_fatal(monkeypatch):
    force_raw(monkeypatch, ValueError("constraints are inconsistent"))   # near-miss!
    hs, cs = base_book()
    with pytest.raises(InvalidRun, match="not the registered rescue trigger"):
        build_joint(hs, cs)


def test_c08b_a_different_exception_type_remains_immediately_fatal(monkeypatch):
    force_raw(monkeypatch, Boom(FALSE_INCONSISTENCY))   # right message, wrong TYPE
    hs, cs = base_book()
    with pytest.raises(Boom):
        build_joint(hs, cs)


def test_c09_highs_probe_infeasible_or_non_optimal_remains_fatal(monkeypatch):
    force_raw(monkeypatch, ValueError(FALSE_INCONSISTENCY))
    real_lp = jp.linprog

    class Bad:
        success = False
        status = 2
        message = "infeasible"
        x = None
        fun = None

    def spy_lp(*a, **k):
        c = np.asarray(a[0] if a else k["c"], float)
        if c.size and np.allclose(c, 0.0):
            return Bad()
        return real_lp(*a, **k)

    monkeypatch.setattr(jp, "linprog", spy_lp)
    hs, cs = base_book()
    with pytest.raises(InvalidRun, match=r"probe.*not optimal"):
        build_joint(hs, cs)


def test_c10_scaled_quadprog_failure_remains_fatal(monkeypatch):
    def always_fail(H, a, C, b, meq):
        raise ValueError(FALSE_INCONSISTENCY)

    monkeypatch.setattr(jp.quadprog, "solve_qp", always_fail)
    hs, cs = base_book()
    with pytest.raises(InvalidRun, match="rescue.*quadprog failed"):
        build_joint(hs, cs)


def test_c11_scaled_residual_or_kkt_failure_remains_fatal(monkeypatch):
    force_raw(monkeypatch, ValueError(FALSE_INCONSISTENCY))
    monkeypatch.setattr(jp, "KKT_RESIDUAL_MAX", 1e-30)     # impossible to satisfy
    hs, cs = base_book()
    with pytest.raises(InvalidRun, match="rescue.*kkt_residual"):
        build_joint(hs, cs)


def test_c11b_a_warning_from_the_raw_solve_is_never_a_rescue_trigger(monkeypatch):
    """Under the fatal-warning policy a warning raises a Warning -- a DIFFERENT exception
    type from the registered ValueError -- so it must be immediately fatal."""
    real = quadprog.solve_qp
    state = {"n": 0}

    def warner(H, a, C, b, meq):
        state["n"] += 1
        if state["n"] == 1:
            warnings.warn("something numerical", RuntimeWarning, stacklevel=2)
        return real(H, a, C, b, meq)

    monkeypatch.setattr(jp.quadprog, "solve_qp", warner)
    hs, cs = base_book()
    with pytest.raises(InvalidRun, match="warning is fatal"):
        build_joint(hs, cs)


# ======================================================================================
# 12-13-14-15 · determinism, invariance, and the closed door
# ======================================================================================
def test_c12_repeated_rescue_produces_byte_identical_executable_decisions(monkeypatch):
    hs, cs = base_book()
    hashes = []
    for _ in range(3):
        force_raw(monkeypatch, ValueError(FALSE_INCONSISTENCY))
        r = build_joint(hs, cs)
        assert stage3(r)["stage3_formulation"] == SCALED_RESCUE
        hashes.append(r.diagnostics["determinism_hash"])
    assert len(set(hashes)) == 1


def test_c13_shuffles_produce_the_same_rescued_result(monkeypatch):
    hs, cs = base_book()
    force_raw(monkeypatch, ValueError(FALSE_INCONSISTENCY))
    base = build_joint(list(hs), list(cs))
    for seed in range(4):
        rng = np.random.default_rng(seed)
        h2, c2 = list(hs), list(cs)
        rng.shuffle(h2)
        rng.shuffle(c2)
        force_raw(monkeypatch, ValueError(FALSE_INCONSISTENCY))
        r = build_joint(h2, c2)
        assert stage3(r)["stage3_formulation"] == SCALED_RESCUE
        assert r.diagnostics["determinism_hash"] == base.diagnostics["determinism_hash"]
        assert r.y == base.y and r.x == base.x


def test_c14_the_retry_changes_no_lexicographic_optimum_objective_or_bound(monkeypatch):
    hs, cs = base_book()
    raw = build_joint(hs, cs)

    force_raw(monkeypatch, ValueError(FALSE_INCONSISTENCY))
    resc = build_joint(hs, cs)

    assert resc.diagnostics["R_star"] == pytest.approx(raw.diagnostics["R_star"], abs=1e-15)
    assert resc.diagnostics["Q_star"] == pytest.approx(raw.diagnostics["Q_star"], abs=1e-15)
    assert stage3(resc)["raw_coordinate_objective"] == pytest.approx(
        stage3(raw)["raw_coordinate_objective"], rel=1e-9)
    by_c = {h.permaticker: h.c for h in hs}
    by_w = {c.permaticker: c.w for c in cs}
    for pt, v in resc.y.items():
        assert v <= by_c[pt] + TOL, "a registered bound was violated by the rescue"
    for pt, v in resc.x.items():
        assert v <= by_w[pt] + TOL, "a registered bound was violated by the rescue"


def test_c15_no_third_attempt_and_no_alternate_solver_is_reachable(monkeypatch):
    """Exactly TWO quadprog calls at most: raw, then one rescue. Never a third."""
    real = quadprog.solve_qp
    calls = {"n": 0}

    def counted(H, a, C, b, meq):
        calls["n"] += 1
        if calls["n"] == 1:
            raise ValueError(FALSE_INCONSISTENCY)
        return real(H, a, C, b, meq)

    monkeypatch.setattr(jp.quadprog, "solve_qp", counted)
    hs, cs = base_book()
    res = build_joint(hs, cs)
    assert stage3(res)["stage3_formulation"] == SCALED_RESCUE
    assert calls["n"] == 2, f"expected exactly 2 quadprog calls, saw {calls['n']}"

    # and the module imports no other optimizer
    src = __import__("inspect").getsource(jp)
    for banned in ("osqp", "cvxpy", "trust-constr", "SLSQP", "minimize("):
        assert banned not in src, f"an alternate optimizer leaked in: {banned}"


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
