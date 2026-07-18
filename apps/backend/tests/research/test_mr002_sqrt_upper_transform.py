"""Focused tests for the authorized QUADPROG_SQRT upper-transform fix (delta review 2026-07-18).

The defect: with the substitution z = S v (S = diag(sqrt(t))), the transformed upper bound must
be upper / sqrt(t); the historical form passed sqrt(t) itself, which coincides with the correct
bound only when upper == t elementwise. These tests pin the corrected transform, the historical
masking condition, dual reconstruction, and the realism fixture regression.

Solver-stack tests skip when quadprog/mpmath/piqp are unavailable (they run in the pinned
environment and in-image, where zero skips are required) — the same pattern as the
production-binding test. The pure transformation-identity tests run everywhere.
"""

import numpy as np
import pytest


def _solver_stack():
    pytest.importorskip("mpmath")
    pytest.importorskip("piqp")
    import app.research.mr002.joint_portfolio as jp
    from scripts.mr002_coverage_signed_gap import PRIMARY, SOLVERS, canonical_qualify
    from scripts.mr002_solver_intersection import LIMITS
    return jp, SOLVERS[PRIMARY], canonical_qualify, LIMITS


def _rec(t, A_ub, b_ub, A_eq, b_eq, upper):
    return (np.asarray(t, float), np.asarray(A_ub, float), np.asarray(b_ub, float),
            np.asarray(A_eq, float), np.asarray(b_eq, float), np.asarray(upper, float))


def _bounds_only(t, upper):
    n = len(t)
    return _rec(t, np.zeros((0, n)), np.zeros(0), np.zeros((0, n)), np.zeros(0), upper)


# ── 1) one-dimensional active upper bound ────────────────────────────────────────────────────────
def test_one_dim_active_upper_bound_primary_qualified():
    jp, primary, qualify, LIMITS = _solver_stack()
    rec = _bounds_only([0.02], [0.01])
    z, lam = primary(*rec)
    assert z.shape == (1,)
    assert abs(z[0] - 0.01) < 1e-12                       # expected z = 0.01
    assert z[0] <= 0.01 + 1e-15                           # upper bound respected
    assert (0.01 - z[0]) < 1e-12                          # and ACTIVE (no slack)
    ok, bad, cert = qualify(z, lam, *rec)
    assert ok, bad                                        # primary qualifies


# ── 2) historical masking case: upper == t ───────────────────────────────────────────────────────
def test_masking_case_upper_equals_t_mathematically_equivalent_and_stays_qualified():
    """upper == t implies the old (s) and corrected (upper/s) transformed bounds represent the
    SAME mathematical constraint — but NOT general bitwise equality: the corpus audit measured
    bitwise coincidence on only 156 of 3,895 registered rows, with a 1-ulp difference on the
    remaining 3,739 (see the fixed 1-ulp regression below). Equivalence is therefore asserted
    through the reconstructed original-coordinate bounds at an explicit ulp-scale tolerance."""
    t = np.asarray([0.008, 0.02, 0.25], float)
    upper = t.copy()
    s = np.sqrt(t)
    old_original_upper = s * s                            # bound the frozen form imposed on z
    new_original_upper = s * (upper / s)                  # bound the corrected form imposes on z
    assert np.all(np.abs(old_original_upper - upper) <= np.spacing(upper))
    assert np.all(np.abs(new_original_upper - upper) <= np.spacing(upper))
    jp, primary, qualify, LIMITS = _solver_stack()
    rec = _bounds_only(t, upper)
    z, lam = primary(*rec)
    assert np.all(z <= upper + 1e-15)
    ok, bad, cert = qualify(z, lam, *rec)
    assert ok, bad                                        # behavior remains qualified


def test_masking_one_ulp_bitwise_nuance_fixed_example():
    """Deterministic no-RNG regression for the accepted corpus-audit finding: upper == t exactly,
    yet fl(t/sqrt(t)) != fl(sqrt(t)) bitwise — the difference is at most one ulp of sqrt(t) and
    both forms represent the same mathematical bound in original coordinates. Pure numpy."""
    t = np.asarray([0.001, 0.01, 0.021], float)           # fixed values with the 1-ulp property
    upper = t.copy()
    s = np.sqrt(t)
    corrected = upper / s
    assert not np.array_equal(corrected, s)               # bitwise DIFFERENT on these values
    assert np.all(np.abs(corrected - s) <= np.spacing(s))  # by at most 1 ulp of sqrt(t)
    # same mathematical bound once mapped back to original coordinates (explicit ulp scale)
    assert np.all(np.abs(s * corrected - upper) <= np.spacing(upper))
    assert np.all(np.abs(s * s - upper) <= np.spacing(upper))


# ── 3) inactive upper bound: upper > t ───────────────────────────────────────────────────────────
def test_inactive_upper_bound_returns_unconstrained_optimum():
    jp, primary, qualify, LIMITS = _solver_stack()
    t = np.asarray([0.02, 0.008], float)
    upper = np.asarray([0.05, 0.03], float)               # upper > t everywhere
    rec = _bounds_only(t, upper)
    z, lam = primary(*rec)
    assert np.allclose(z, t, rtol=0, atol=1e-12)          # unconstrained optimum z = t, feasible
    assert np.all(z <= upper)
    ok, bad, cert = qualify(z, lam, *rec)
    assert ok, bad


# ── 4) heterogeneous multidimensional bounds ─────────────────────────────────────────────────────
def test_heterogeneous_bounds_elementwise_transform_and_feasibility(monkeypatch):
    jp, primary, qualify, LIMITS = _solver_stack()
    t = np.asarray([0.02, 0.008, 0.01], float)
    upper = np.asarray([0.01, 0.008, 0.02], float)        # upper < t, == t, > t
    rec = _bounds_only(t, upper)

    calls = []
    real_qp_matrices = jp._qp_matrices

    def recorder(A_ub, b_ub, A_eq, b_eq, up, n):
        calls.append(np.asarray(up, float).copy())
        return real_qp_matrices(A_ub, b_ub, A_eq, b_eq, up, n)

    monkeypatch.setattr(jp, "_qp_matrices", recorder)
    z, lam = primary(*rec)
    monkeypatch.undo()

    # call 1 = original coordinates, call 2 = transformed: bound must equal upper/sqrt(t) BITWISE
    assert len(calls) == 2
    assert np.array_equal(calls[0], upper)
    assert np.array_equal(calls[1], upper / np.sqrt(t))

    assert np.all(z <= upper + 1e-15)                     # every upper bound respected
    expected = np.minimum(t, upper)                       # separable bounds-only optimum
    assert np.allclose(z, expected, rtol=0, atol=1e-12)
    ok, bad, cert = qualify(z, lam, *rec)
    assert ok, bad


# ── 5) transformation identity (pure numpy — runs everywhere) ────────────────────────────────────
def test_transformation_identity_bounds_equivalence_exact_dyadic():
    # dyadic values make every product/quotient exact: sqrt(0.25)=0.5, 0.125/0.5=0.25, 0.5*0.25=0.125
    t = np.asarray([0.25, 0.0625], float)
    upper = np.asarray([0.125, 0.25], float)
    s = np.sqrt(t)
    v_bound = upper / s
    assert np.array_equal(s * v_bound, upper)             # exact round-trip at the boundary
    for v in (np.zeros(2), v_bound, 0.5 * v_bound, v_bound + np.asarray([0.25, 0.0]),
              np.asarray([-0.25, 0.125])):
        z = s * v
        z_feasible = bool(np.all(z >= 0.0) and np.all(z <= upper))
        v_feasible = bool(np.all(v >= 0.0) and np.all(v <= v_bound))
        assert z_feasible == v_feasible                   # 0<=z<=upper  ⇔  0<=v<=upper/sqrt(t)


def test_transformation_identity_representative_vectors_with_margin():
    t = np.asarray([0.02, 0.008, 0.013, 3.7], float)
    s = np.sqrt(t)
    upper = np.asarray([0.01, 0.008, 0.05, 1.9], float)
    v_bound = upper / s
    for scale, expect in ((0.5, True), (0.999, True), (1.001, False), (2.0, False)):
        v = scale * v_bound
        z = s * v
        assert bool(np.all(z <= upper)) is expect         # strict-margin cases agree in both spaces
        assert bool(np.all(v <= v_bound)) is expect


# ── 6) dual reconstruction regression ────────────────────────────────────────────────────────────
def test_dual_reconstruction_unscaling_regression():
    jp, primary, qualify, LIMITS = _solver_stack()
    t = np.asarray([0.02], float)
    upper = np.asarray([0.01], float)
    rec = _bounds_only(t, upper)
    z, lam = primary(*rec)
    # registered multiplier layout with meq=0, no A_ub rows: [n lower | n upper]
    assert lam.shape == (2,)
    lower_mu, upper_mu = lam[0], lam[1]
    assert abs(lower_mu) < 1e-12                          # lower bound slack → zero multiplier
    # stationarity in ORIGINAL coordinates: H z - a + mu_upper - mu_lower = 0
    # H = 2/t = 100, a = 2 → 100*0.01 - 2 + mu_upper = 0 → mu_upper = 1 (proves /= s unscaling)
    assert abs(upper_mu - 1.0) < 1e-9
    H = np.diag(2.0 / t)
    stationarity = H @ z - 2.0 * np.ones(1) + upper_mu - lower_mu
    assert abs(stationarity[0]) < 1e-9


# ── 7) realism regression: the exact fixture case, unchanged input and expectation ───────────────
def test_realism_fixture_case_becomes_primary_qualified():
    pytest.importorskip("mpmath")
    pytest.importorskip("piqp")
    from app.research.mr002 import stage3_cascade as sc
    from scripts.mr002_stage3_cascade_fixtures import _rec_hash, hand_solvable_problems

    cases = dict(hand_solvable_problems())
    rec = cases["active_upper_bound"]                     # the UNCHANGED fixture input
    assert _rec_hash(rec) == ("4bbaa6d1701fb2e0efff77d36dea4f27c6b8d112"
                              "947739366567ca5092c6d210")
    o = sc.resolve_instance(rec)
    assert o.disposition == sc.PRIMARY_QUALIFIED          # the UNCHANGED expectation
    assert o.accepted_by == sc.PRIMARY_SOLVER_ID
    assert o.fallback_invoked is False
