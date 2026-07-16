"""MR-002 — the EXACT MINIMUM-L-INFINITY REPAIR LP (owner ruling §10, full fixture suite).

The existing 58 certificate fixtures cover the signed-gap certificate and the RETIRED R1/R2/R2-C1
proposal family. This suite covers the layer that replaced them: the exact repair LP itself, its
canonical standard form, and the agreement certificate built on top of it.

WHAT A REPAIR FIXTURE HAS TO PROVE. That the returned point is exactly feasible is necessary but far
from sufficient — `w = 0` is exactly feasible for many of these models. The load-bearing claims are:

  * rho* is the exact MINIMUM. Verified independently of the simplex's own dual certificate, by
    re-solving with rho PINNED below rho* and requiring exact Phase-I infeasibility. If the solver
    silently returned a suboptimal vertex, the dual test inside solve_lp and this test would have to
    be wrong in the same direction to agree.
  * the envelope BINDS: some coordinate sits exactly at rho*, else rho could have been smaller.
  * the canonical order is MODEL-defined, not layout-defined — under variable AND row relabelling.
  * feasibility is re-derived from the ORIGINAL float arrays, not from the standard form we built.

FINDINGS. One real defect, and one thing I initially called a defect and was wrong about. Both are
recorded, because the second is the more instructive:

  B (REAL). `canonical_order` keyed variables on equality row 0 ALONE. With a second equality row,
     variables identical in row 0 tie, and Python's stable sort then orders them by INCOMING
     POSITION — so relabelling the variables moves the "canonical" order. Verified against the
     pre-fix code: it failed. Canonical shuffle invariance was holding only because meq = 1 on every
     corpus instance. An accident of the data, not a property of the code. Fixed; the key now reads
     every equality row, and `exact_repair` likewise verifies every equality row against the ORIGINAL
     model rather than only row 0.

  A (NOT A DEFECT). I claimed `certify_repair` would crash on `iv.sqrt` of a gap enclosure that
     straddles zero. The fixture I wrote for it PASSED against the unfixed code — which is how the
     over-claim surfaced. Measurement: the enclosure is ~1e-133 wide (f(zhat) is enclosed from an
     EXACT rational) while `dual_lower` is a float64 with ~1e-48 granularity there. A straddle would
     need the float to land inside the 1e-100-relative window. It cannot. The interval is always
     wholly non-negative, or wholly negative and already caught by the weak-duality guard.
     What remained was an unguarded sqrt DOMAIN resting on an unstated premise, so the premise is now
     pinned by a fixture and asserted in the code — stop with a reason code, never an mpmath
     traceback. No clamp: widening an interval to make sqrt succeed would manufacture a bound rather
     than prove one.
"""

from __future__ import annotations

from fractions import Fraction

import numpy as np
import pytest
from mpmath import iv

from app.research.mr002.certificate import (
    CertificateDefect,
    certify,
    rational_iv,
    to_fraction,
)
from app.research.mr002.exact_repair import (
    RepairUnavailable,
    agreement,
    build_standard_form,
    canonical_order,
    certify_repair,
    empty_rows_of,
    exact_repair,
    lp_content_hash,
    manifest,
    objective_agreement,
)
from app.research.mr002.exact_simplex import SimplexUnavailable, solve_lp

ZERO = Fraction(0)


# =====================================================================================
# Model builders
# =====================================================================================
def simplex_model(n=4, budget=1.0, upper=None):
    """sum(w) = budget, 0 <= w <= u. The MR-002 shape: one equality, box bounds."""
    return dict(
        A_ub=np.zeros((0, n)), b_ub=np.zeros(0),
        A_eq=np.ones((1, n)), b_eq=np.array([budget]),
        upper=np.ones(n) if upper is None else np.asarray(upper, dtype=float),
    )


def capped_model(n=4, budget=1.0, cap=0.4):
    """Adds a per-name cap as an inequality row, so the repair must satisfy A_ub too."""
    m = simplex_model(n, budget)
    m["A_ub"] = np.eye(n)
    m["b_ub"] = np.full(n, cap)
    return m


def args_of(m):
    return (m["A_ub"], m["b_ub"], m["A_eq"], m["b_eq"], m["upper"])


def is_feasible_exactly(w, m, tol_free=True):
    """Exact rational feasibility against the ORIGINAL model. No tolerance anywhere."""
    n = len(w)
    A_eq, b_eq = m["A_eq"], m["b_eq"]
    for e in range(A_eq.shape[0]):
        if sum(to_fraction(A_eq[e, i]) * w[i] for i in range(n)) != to_fraction(b_eq[e]):
            return False
    for r in range(m["A_ub"].shape[0]):
        if sum(to_fraction(m["A_ub"][r, i]) * w[i] for i in range(n)) > to_fraction(m["b_ub"][r]):
            return False
    return all(ZERO <= w[i] <= to_fraction(m["upper"][i]) for i in range(n))


# =====================================================================================
# rho* is the exact MINIMUM — proven without trusting the simplex's dual certificate
# =====================================================================================
def pin_rho_and_solve(z, m, rho: Fraction):
    """Re-solve the repair LP with rho PINNED to a constant instead of minimized.

    If rho* is truly minimal, pinning rho BELOW it must make the LP exactly infeasible — Phase I
    terminates with a positive exact optimum. That is an independent optimality test: it never
    consults the dual vector the solver produced, so a solver that returned a suboptimal vertex would
    have to be wrong here in exactly the same direction to escape detection.
    """
    M, h, c, n, mm, perm, _rows = build_standard_form(z, *args_of(m))
    N = len(c)
    RHO = 4 * n + mm
    # x_rho = rho  ->  add the row  e_rho . x = rho
    row = [ZERO] * N
    row[RHO] = Fraction(1)
    M2 = [list(r) for r in M] + [row]
    h2 = list(h) + [rho]
    c2 = [ZERO] * N                       # pure feasibility: Phase I decides it
    return solve_lp(M2, h2, c2)


@pytest.mark.parametrize("n", [3, 4, 6])
def test_rho_star_is_exactly_minimal_pinning_below_it_is_infeasible(n):
    m = simplex_model(n, budget=1.0)
    z = np.full(n, 1.0 / n - 0.01)                       # sums short of the budget -> repair needed
    r = exact_repair(z, *args_of(m))
    rho = r["rho_star"]
    assert rho > 0

    pin_rho_and_solve(z, m, rho)                         # AT rho*: feasible

    for below in (rho / 2, rho * Fraction(999, 1000)):   # BELOW rho*: must be exactly infeasible
        with pytest.raises(SimplexUnavailable, match="EXACT_PHASE_I_POSITIVE"):
            pin_rho_and_solve(z, m, below)


def test_the_rho_envelope_BINDS_at_the_optimum():
    """If no coordinate sat exactly at rho*, rho could have been reduced — so rho* would not be the
    minimum. A slack envelope is a silent suboptimality."""
    m = capped_model(5, budget=1.0, cap=0.35)
    z = np.array([0.5, 0.3, 0.1, 0.05, 0.0])
    r = exact_repair(z, *args_of(m))
    rho, zhat = r["rho_star"], r["zhat"]
    Z = [to_fraction(v) for v in z]
    assert rho > 0
    assert any(abs(zhat[i] - Z[i]) == rho for i in range(len(z))), (
        "no coordinate attains rho* — the envelope is slack, so rho* is not minimal")


def test_an_already_feasible_point_repairs_to_itself_with_rho_zero():
    """rho* = 0 is PERMISSIBLE and must not be treated as a failure: it means the submitted point was
    exactly feasible to begin with. It must then be returned UNCHANGED."""
    m = simplex_model(4, budget=1.0)
    z = np.array([0.25, 0.25, 0.25, 0.25])              # exact binary; sums to exactly 1.0
    r = exact_repair(z, *args_of(m))
    assert r["rho_star"] == 0
    assert r["n_changed"] == 0
    assert list(r["zhat"]) == [to_fraction(v) for v in z]


# =====================================================================================
# The repaired point lands EXACTLY in the ORIGINAL set
# =====================================================================================
@pytest.mark.parametrize(
    ("desc", "z", "model"),
    [
        ("short of budget", np.array([0.2, 0.2, 0.2, 0.2]), simplex_model(4)),
        ("over budget", np.array([0.3, 0.3, 0.3, 0.3]), simplex_model(4)),
        ("above an upper bound", np.array([0.9, 0.05, 0.05, 0.0]), capped_model(4, cap=0.4)),
        ("below zero", np.array([-0.05, 0.4, 0.4, 0.25]), simplex_model(4)),
        ("violates a cap row", np.array([0.7, 0.1, 0.1, 0.1]), capped_model(4, cap=0.35)),
        ("every coordinate wrong", np.array([0.9, 0.9, 0.9, 0.9]), capped_model(4, cap=0.4)),
    ],
)
def test_the_repaired_point_is_exactly_feasible_in_the_original_model(desc, z, model):
    r = exact_repair(z, *args_of(model))
    assert is_feasible_exactly(r["zhat"], model), f"{desc}: repaired point is not exactly feasible"
    Z = [to_fraction(v) for v in z]
    for i in range(len(z)):                              # and inside the envelope it claims
        assert abs(r["zhat"][i] - Z[i]) <= r["rho_star"]


def test_a_bound_violating_z_is_pulled_INSIDE_not_merely_close():
    m = simplex_model(3, budget=1.0, upper=[0.5, 0.5, 0.5])
    z = np.array([0.8, 0.1, 0.1])                        # z0 exceeds its upper bound
    r = exact_repair(z, *args_of(m))
    assert r["zhat"][0] <= to_fraction(0.5)
    assert all(v >= 0 for v in r["zhat"])
    assert is_feasible_exactly(r["zhat"], m)


def test_an_exactly_infeasible_model_reports_PHASE_I_POSITIVE_not_a_crash():
    """The box cannot hold the budget. That is a mathematical result about the MODEL, and it must
    surface as one — not as a numerical failure and not as a silently wrong answer."""
    m = simplex_model(2, budget=5.0, upper=[0.1, 0.1])
    with pytest.raises(SimplexUnavailable, match="EXACT_PHASE_I_POSITIVE"):
        exact_repair(np.array([0.05, 0.05]), *args_of(m))


def test_RepairUnavailable_is_the_SAME_reason_code_family():
    assert RepairUnavailable is SimplexUnavailable


# =====================================================================================
# Canonical identity — MODEL-defined, not layout-defined
# =====================================================================================
def test_the_repair_is_invariant_under_variable_and_row_relabelling():
    m = capped_model(5, budget=1.0, cap=0.4)
    m["A_ub"] = np.vstack([m["A_ub"], np.array([[1.0, 1.0, 0.0, 0.0, 0.0]])])
    m["b_ub"] = np.concatenate([m["b_ub"], [0.6]])
    z = np.array([0.45, 0.3, 0.15, 0.07, 0.03])

    base = exact_repair(z, *args_of(m))
    vp = np.array([3, 0, 4, 1, 2])                       # relabel variables
    rp = np.array([2, 0, 4, 1, 3, 5])                    # and rows
    shuf = exact_repair(
        z[vp], m["A_ub"][np.ix_(rp, vp)], m["b_ub"][rp],
        m["A_eq"][:, vp], m["b_eq"], m["upper"][vp],
    )
    assert shuf["rho_star"] == base["rho_star"]
    for k in range(len(z)):
        assert shuf["zhat"][k] == base["zhat"][vp[k]]


def test_canonical_order_uses_EVERY_equality_row_not_just_the_first():
    """DEFECT B. With two equality rows, variables 0/1/2 are identical in row 0, in `upper`, in `z_s`
    and in the (absent) inequality rows — they differ ONLY in row 1. A key that read row 0 alone
    would tie them, and Python's stable sort would then order them by INCOMING POSITION. Relabel the
    variables and the "canonical" order moves. Canonical shuffle invariance would then be holding
    only because meq = 1 in this corpus, which is an accident of the data, not a property of the
    code."""
    A_eq = np.array([[1.0, 1.0, 1.0], [1.0, 2.0, 3.0]])
    z, up = np.array([0.2, 0.2, 0.2]), np.ones(3)
    A_ub, b_ub, b_eq = np.zeros((0, 3)), np.zeros(0), np.array([0.6, 1.2])

    p, _ = canonical_order(z, A_ub, b_ub, A_eq, b_eq, up)
    for perm in ([2, 0, 1], [1, 2, 0], [2, 1, 0]):
        p2, _ = canonical_order(z[perm], A_ub, b_ub, A_eq[:, perm], b_eq, up[perm])
        assert [perm[i] for i in p2] == p, (
            f"relabelling by {perm} changed the canonical order — it is layout-defined")


def test_the_repair_verifies_EVERY_equality_row_against_the_original_model():
    """The independent verification block re-derives feasibility from the ORIGINAL float arrays. If
    it checked only row 0, a second equality would be enforced by the standard form but never
    independently confirmed — which is the one thing that block exists to do."""
    A_eq = np.array([[1.0, 1.0, 1.0, 1.0], [1.0, -1.0, 0.0, 0.0]])
    b_eq = np.array([1.0, 0.0])                          # w0 == w1, and the budget
    m = dict(A_ub=np.zeros((0, 4)), b_ub=np.zeros(0), A_eq=A_eq, b_eq=b_eq, upper=np.ones(4))
    z = np.array([0.4, 0.1, 0.25, 0.25])
    r = exact_repair(z, *args_of(m))
    assert r["zhat"][0] == r["zhat"][1], "the SECOND equality row was not enforced"
    assert is_feasible_exactly(r["zhat"], m)


def test_the_lp_content_hash_is_a_property_of_the_MODEL():
    m = capped_model(4, budget=1.0, cap=0.4)
    z = np.array([0.5, 0.2, 0.2, 0.1])
    h1 = lp_content_hash(*build_standard_form(z, *args_of(m))[:3])
    vp = np.array([2, 0, 3, 1])
    h2 = lp_content_hash(*build_standard_form(
        z[vp], m["A_ub"][:, vp], m["b_ub"], m["A_eq"][:, vp], m["b_eq"], m["upper"][vp])[:3])
    assert h1 == h2, "the same model presented differently produced a different LP hash"

    m2 = capped_model(4, budget=1.0, cap=0.41)           # a genuinely DIFFERENT model
    h3 = lp_content_hash(*build_standard_form(z, *args_of(m2))[:3])
    assert h3 != h1, "a different model hashed identically — the hash is not discriminating"


# =====================================================================================
# The standard form encodes what it claims
# =====================================================================================
def test_the_standard_form_reproduces_the_original_constraints_exactly():
    """Every solution of (Mx = h, x >= 0) must map back to a w that satisfies the ORIGINAL model and
    the rho envelope. If the form drifted from the model, the certificate would be about a different
    problem than the one registered."""
    m = capped_model(4, budget=1.0, cap=0.45)
    z = np.array([0.6, 0.2, 0.15, 0.05])
    M, h, c, n, mm, perm, _rows = build_standard_form(z, *args_of(m))
    res = solve_lp(M, h, c)

    RHO = 4 * n + mm
    rho = res.x[RHO]
    w = [ZERO] * n
    for k, i in enumerate(perm):
        w[i] = res.x[k]

    assert rho == res.objective
    assert is_feasible_exactly(w, m)
    Z = [to_fraction(v) for v in z]
    for i in range(n):
        assert abs(w[i] - Z[i]) <= rho


def test_a_structurally_empty_inequality_row_is_validated_and_omitted():
    m = simplex_model(3, budget=1.0)
    m["A_ub"] = np.array([[0.0, 0.0, 0.0], [1.0, 0.0, 0.0]])
    m["b_ub"] = np.array([0.5, 0.4])                     # row 0 is empty, 0 <= 0.5 holds
    empties = empty_rows_of(m["A_ub"], m["b_ub"])
    assert len(empties) == 1 and empties[0][0] == 0
    _M, _h, _c, _n, mm, _p, _rows = build_standard_form(np.array([0.5, 0.3, 0.2]), *args_of(m))
    assert mm == 1, "the structurally empty row was not omitted from the LP"


def test_an_empty_row_with_a_NEGATIVE_rhs_is_an_INVALID_MODEL_not_a_repair_failure():
    """0 <= b is false. The model is unsatisfiable as written — that must not be laundered into an
    unavailable certificate, which would read as 'the solver could not cope'."""
    with pytest.raises(CertificateDefect, match="INVALID ORIGINAL MODEL"):
        empty_rows_of(np.array([[0.0, 0.0]]), np.array([-1e-9]))


# =====================================================================================
# Determinism
# =====================================================================================
def test_the_repair_is_bitwise_deterministic_across_repeats():
    m = capped_model(6, budget=1.0, cap=0.3)
    z = np.array([0.4, 0.25, 0.15, 0.1, 0.07, 0.03])
    a = exact_repair(z, *args_of(m))
    b = exact_repair(z, *args_of(m))
    assert a["zhat"] == b["zhat"]
    assert a["rho_star"] == b["rho_star"]
    assert a["result"].basis == b["result"].basis
    assert a["result"].pivots_phase_i == b["result"].pivots_phase_i
    assert a["result"].pivots_phase_ii == b["result"].pivots_phase_ii


# =====================================================================================
# certify_repair — the agreement certificate on top of the repair
# =====================================================================================
def qp_instance(n=4):
    """A small MR-002-shaped QP:  min sum (z_i - t_i)^2 / t_i  s.t.  sum z = 1, 0 <= z <= u."""
    t = np.array([0.4, 0.3, 0.2, 0.1])[:n]
    t = t / t.sum()
    m = simplex_model(n, budget=1.0)
    return t, m


def test_the_repaired_gap_enclosure_is_ONE_SIDED_so_sqrt_has_a_domain():
    """`iv.sqrt` raises mpmath's ComplexResult on an interval that straddles zero, and certify_repair
    feeds it `2 * ghat_iv / m`. So the certificate's finiteness rests on ghat_iv never straddling.

    It never does, and the reason is a WIDTH argument, not an appeal to weak duality alone:

      * f_zhat_iv is `rational_iv` of an EXACT rational -> width ~1e-100 relative (measured: 1e-133
        absolute at these magnitudes);
      * cert.dual_lower is a float64 POINT, granularity ~1e-16 relative.

    A straddle needs dual_lower to land inside that 1e-100-wide window around f(zhat). No float can.
    So the interval is wholly non-negative, or wholly negative and rejected by the weak-duality guard.

    This fixture PINS that premise. It is the thing the domain assertion in certify_repair depends
    on, and if a future change to IV_DPS or to the dual representation breaks it, this fails here
    rather than as an mpmath traceback in the middle of Sample A.
    """
    t, m = qp_instance(4)
    for z in (np.array(t, dtype=float),
              t + np.array([1e-16, -1e-16, 0.0, 0.0]),
              t + np.array([1e-12, -1e-12, 0.0, 0.0])):
        cert = certify(z, np.zeros(0), t, m["A_ub"], m["b_ub"], m["A_eq"], m["b_eq"], m["upper"])
        f_z = sum((to_fraction(z[i]) - to_fraction(t[i])) ** 2 / to_fraction(t[i])
                  for i in range(len(t)))
        ghat = rational_iv(f_z) - iv.mpf(cert.dual_lower)
        assert not (ghat.a < 0 <= ghat.b), (
            f"the repaired-gap enclosure [{float(ghat.a):.3e}, {float(ghat.b):.3e}] straddles zero — "
            f"sqrt has no real value on it and certify_repair would die with ComplexResult")

        r = certify_repair(z, cert, t, *args_of(m))
        assert r.ghat_upper >= 0.0
        assert np.isfinite(r.radius_upper)
        assert r.radius_upper >= r.delta_upper >= 0.0


def test_a_straddling_gap_enclosure_STOPS_with_a_reason_code_not_an_mpmath_traceback(monkeypatch):
    """The straddle cannot be produced from real inputs — a float cannot land inside a 1e-100-wide
    window — so it cannot be provoked by choosing a bad `dual_lower`. Attempting that is how the
    over-claim was caught.

    What CAN change is the premise: if `f(zhat)` ever stops being enclosed from an exact rational and
    starts arriving as a wide interval, the straddle becomes reachable. So break exactly that premise
    — widen the enclosure — and require a reason code rather than an mpmath ComplexResult escaping
    from inside a library. This is the assertion earning its place, tested against the only scenario
    in which it can ever fire.
    """
    import app.research.mr002.exact_repair as er

    t, m = qp_instance(4)
    z = np.array(t, dtype=float)
    cert = certify(z, np.zeros(0), t, m["A_ub"], m["b_ub"], m["A_eq"], m["b_eq"], m["upper"])

    real = er.rational_iv
    monkeypatch.setattr(er, "rational_iv",
                        lambda fr: real(fr) + iv.mpf([-1e-18, 1e-18]))   # a WIDE enclosure

    with pytest.raises(CertificateDefect, match="straddles zero"):
        certify_repair(z, cert, t, *args_of(m))


def test_a_genuinely_negative_repaired_gap_is_STILL_rejected():
    """The straddle fix must not weaken the real guard. A dual lower bound that EXCEEDS f(zhat) is a
    weak-duality violation and must still be an INVALID_RUN."""
    t, m = qp_instance(4)
    z = np.array(t, dtype=float)
    lam = np.zeros(0)
    cert = certify(z, lam, t, m["A_ub"], m["b_ub"], m["A_eq"], m["b_eq"], m["upper"])
    forged = cert.__class__(**{**cert.__dict__, "dual_lower": cert.primal_upper + 1.0})
    with pytest.raises(CertificateDefect, match="negative"):
        certify_repair(z, forged, t, *args_of(m))


def test_the_agreement_radius_actually_bounds_the_distance_between_two_solver_points():
    """The claim the whole certificate exists to support: two solvers' points lie within R1 + R2."""
    t, m = qp_instance(4)
    z1 = np.array(t, dtype=float)
    z2 = z1 + np.array([1e-12, -1e-12, 5e-13, -5e-13])
    z2 = z2 / z2.sum()
    lam = np.zeros(0)
    c1 = certify(z1, lam, t, m["A_ub"], m["b_ub"], m["A_eq"], m["b_eq"], m["upper"])
    c2 = certify(z2, lam, t, m["A_ub"], m["b_ub"], m["A_eq"], m["b_eq"], m["upper"])
    r1 = certify_repair(z1, c1, t, *args_of(m))
    r2 = certify_repair(z2, c2, t, *args_of(m))

    ok, dz, bound = agreement(r1, r2, z1, z2)
    assert ok and dz <= bound

    ok_o, df, bound_o = objective_agreement(r1, r2, c1, c2)
    assert ok_o and df <= bound_o


def test_the_agreement_bound_REFUSES_two_genuinely_distant_points():
    """A negative control. If `agreement` accepted anything, the fixture above would be worthless."""
    t, m = qp_instance(4)
    z1 = np.array(t, dtype=float)
    lam = np.zeros(0)
    c1 = certify(z1, lam, t, m["A_ub"], m["b_ub"], m["A_eq"], m["b_eq"], m["upper"])
    r1 = certify_repair(z1, c1, t, *args_of(m))
    far = np.array([0.7, 0.1, 0.1, 0.1])                 # far away, and still on the simplex
    ok, dz, bound = agreement(r1, r1, z1, far)
    assert not ok and dz > bound


def test_the_delta_and_radius_endpoints_are_OUTWARD_rounded():
    """delta_upper must be >= the true ||z - zhat||, not the nearest float to it. Rounding to nearest
    can land BELOW a bound and quietly stop being one."""
    t, m = qp_instance(4)
    z = np.array([0.45, 0.28, 0.19, 0.08])
    z = z / z.sum()
    lam = np.zeros(0)
    cert = certify(z, lam, t, m["A_ub"], m["b_ub"], m["A_eq"], m["b_eq"], m["upper"])
    r = certify_repair(z, cert, t, *args_of(m))

    Z = [to_fraction(v) for v in z]
    d2 = sum((r.zhat[i] - Z[i]) ** 2 for i in range(len(z)))          # exact rational
    assert iv.mpf(r.delta_upper) >= iv.sqrt(iv.mpf([float(d2), float(d2)])).a
    assert r.f_zhat_upper >= float(sum(
        (r.zhat[i] - to_fraction(t[i])) ** 2 / to_fraction(t[i]) for i in range(len(z))))


def test_the_manifest_records_that_no_float_is_in_the_evidentiary_path():
    mf = manifest()
    assert mf["floating_point_in_evidentiary_path"] is False
    assert "HiGHS basis oracle" in " ".join(mf["retired"])
    assert mf["resource_ceilings"]["max_seconds_per_repair"] == 600.0
