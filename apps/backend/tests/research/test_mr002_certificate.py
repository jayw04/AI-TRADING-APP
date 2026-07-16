"""MR-002 — signed-gap certificate + exact-rational feasible repair (owner ruling §14).

Two specifications died before this one, and both deaths are encoded here as tests:

  * the signed-gap RADIUS `sqrt(2*max(g,0)/m)`, which collapsed to zero exactly when the gap went
    negative — i.e. exactly when uncertainty was real;
  * the NONNEGATIVE gap gate, which demanded exact primal feasibility on active constraints and
    disqualified 2,054 of 3,895 square-root solves that pass every registered KKT gate.

The load-bearing fixtures are:

  * `test_the_exact_identity_holds`            — Gamma == S_lag + 1/2 e'H^-1 e, the integrity check
  * `test_folded_and_expanded_dual_bounds_agree` — the folded convention really is the expanded one
  * `test_a_falsified_dual_mapping_cannot_pass` — a wrong dual cannot manufacture a small gap
  * `test_enumeration_finds_a_repair_where_the_largest_slack_absorber_FAILS` — why enumeration
  * `test_a_merely_tolerance_feasible_point_is_not_a_certified_repair`
"""

from __future__ import annotations

from fractions import Fraction

import numpy as np
import pytest
from mpmath import iv, mp, mpf

from app.research.mr002.certificate import (
    MAX_INTERVAL_WIDTH,
    SIGNED_GAP_MAX,
    CertificateDefect,
    canonical_matrices,
    certify,
    classify,
    dual_sign_violation,
    exact_iv,
    gap_intervals,
    project_dual,
    rational_iv,
    to_fraction,
    verify_canonical_hessian,
)
from app.research.mr002.repair import (
    ETA,
    ETA_FLOAT,
    ETA_HEX,
    PROPOSAL_PROFILE,
    RepairUnavailable,
    agreement,
    assert_structure,
    assert_tightened_box_nonempty,
    build_tightened_problem,
    canonical_key,
    certify_repair,
    empty_rows_of,
    exact_repair_from_proposal,
    manifest,
    objective_agreement,
    repair,
)

mp.dps = 120


# ---------------------------------------------------------------------------------
# INSTANCE 1 — analytic: min sum((z-t)^2/t) s.t. a'z = S, 0 <= z <= u.
# With the equality active and bounds slack the optimum is z* = t*(S/sum(t)) for a = 1.
# S = 0.6*sum(t) keeps the equality multiplier NONZERO; S = sum(t) would zero every multiplier
# and quietly turn the falsification fixture into a no-op. `test_..._NONZERO_multipliers` guards.
# ---------------------------------------------------------------------------------
def _analytic():
    t = np.array([0.10, 0.20, 0.30, 0.40])
    u = np.ones(4)
    S = 0.6 * float(t.sum())
    return t, np.zeros((0, 4)), np.zeros(0), np.ones((1, 4)), np.array([S]), u, S


def _solve_analytic(t, S):
    return t * (S / t.sum())


def _duals_for(z, t, A_ub, b_ub, A_eq, b_eq, upper):
    n = len(t)
    meq = A_eq.shape[0]
    C, _b = canonical_matrices(A_ub, b_ub, A_eq, b_eq, upper, n)
    grad = (2.0 / t) * z - 2.0 * np.ones(n)               # Hz - a
    lam = np.zeros(C.shape[1])
    lam[:meq] = np.linalg.lstsq(C[:, :meq], grad, rcond=None)[0]
    return lam


def _certify_args():
    t, A_ub, b_ub, A_eq, b_eq, u, S = _analytic()
    z = _solve_analytic(t, S)
    return z, _duals_for(z, t, A_ub, b_ub, A_eq, b_eq, u), t, A_ub, b_ub, A_eq, b_eq, u


# ---------------------------------------------------------------------------------
# INSTANCE 2 — the equivalence fixture. Real inequality row, real upper bounds; equality,
# inequality and upper-bound multipliers all strictly active (found by search, see
# `scripts/mr002_find_equivalence_fixture.py`).
#
# A strictly active LOWER bound is unreachable in this family: it would force its own row-mates to
# zero, which makes the `<=` row slack and collapses that row's multiplier — a contradiction. So
# the lower-bound sign path is exercised with ARBITRARY dual-feasible multipliers nonzero in all
# four blocks, which is strictly harder than optimal duals (at an optimum many terms vanish and a
# sign slip can hide). The separate native-wrapper fixture below covers a genuinely nonzero
# OPTIMAL lower-bound multiplier, outside this objective family.
# ---------------------------------------------------------------------------------
def _rich():
    return (np.array([0.237, 0.059, 0.138, 0.598]),
            np.array([[1.0, 0.0, 0.0, 1.0]]), np.array([0.076]),
            np.ones((1, 4)), np.array([0.227]),
            np.array([0.195, 0.283, 0.041, 0.033]))


def _rich_optimum():
    import quadprog
    t, A_ub, b_ub, A_eq, b_eq, upper = _rich()
    C, b = canonical_matrices(A_ub, b_ub, A_eq, b_eq, upper, 4)
    out = quadprog.solve_qp(np.diag(2.0 / t), 2.0 * np.ones(4), C, b, 1)
    return np.asarray(out[0], float), np.asarray(out[4], float)


def _expanded_dual_bound(z, lam, t, A_ub, b_ub, A_eq, b_eq, upper):
    """The EXPANDED derivation with four SEPARATE multiplier vectors, written independently of the
    module under test — that independence is the whole value of this fixture.

        nu: A_eq z = b_eq (free)     mu: A_ub z <= b_ub (>=0)
        sig: z >= 0 (>=0)            tau: z <= u (>=0)

        h = q - A_eq'nu + A_ub'mu - sig + tau
        d = c + b_eq'nu - b_ub'mu - u'tau - (1/4) sum_i t_i h_i^2
    """
    n = len(t)
    meq, mub = A_eq.shape[0], A_ub.shape[0]
    nu = [mpf(float(v)) for v in lam[:meq]]
    mu = [mpf(float(v)) for v in lam[meq:meq + mub]]
    sig = [mpf(float(v)) for v in lam[meq + mub:meq + mub + n]]
    tau = [mpf(float(v)) for v in lam[meq + mub + n:]]
    T = [mpf(float(v)) for v in t]
    U = [mpf(float(v)) for v in upper]

    h = []
    for i in range(n):
        acc = mpf(-2)
        for e in range(meq):
            acc -= mpf(float(A_eq[e, i])) * nu[e]
        for r in range(mub):
            acc += mpf(float(A_ub[r, i])) * mu[r]
        h.append(acc - sig[i] + tau[i])

    d = sum(T)
    d += sum(mpf(float(b_eq[e])) * nu[e] for e in range(meq))
    d -= sum(mpf(float(b_ub[r])) * mu[r] for r in range(mub))
    d -= sum(U[i] * tau[i] for i in range(n))
    d -= mpf(1) / mpf(4) * sum(T[i] * h[i] * h[i] for i in range(n))
    return d


# ================================================================ signed gap: endpoints + identity


def test_both_signed_gap_interval_endpoints_are_computed():
    """Gamma_L = f_L - d_U and Gamma_U = f_U - d_L. Not a midpoint, not one endpoint.

    The reported endpoints are each rounded OUTWARD independently, so `gamma_lower` and
    `primal_lower - dual_upper` agree only to a few ulps of the objective magnitude (~1e-17 here),
    not exactly. Demanding exact equality would be testing the float rounding, not the gap. What
    must hold is that the reported interval is no NARROWER than the endpoint difference — i.e. the
    rounding is conservative in both directions.
    """
    z, lam, t, A_ub, b_ub, A_eq, b_eq, u = _certify_args()
    c = certify(z, lam, t, A_ub, b_ub, A_eq, b_eq, u)
    ulps = 8 * np.spacing(max(abs(c.primal_upper), 1e-300))

    assert c.gamma_lower <= c.gamma_upper
    assert c.gamma_lower <= (c.primal_lower - c.dual_upper) + ulps
    assert c.gamma_upper >= (c.primal_upper - c.dual_lower) - ulps
    assert c.dual_lower <= c.dual_upper and c.primal_lower <= c.primal_upper


def test_the_exact_identity_holds():
    """§14.3 — Gamma == S_lag + (1/2) e'H^-1 e, evaluated as two INDEPENDENT interval expressions.

    This is the integrity check, and it is an EQUALITY: it supersedes the one-sided floor because
    it catches a defect that preserves `Gamma >= S_lag` while corrupting the magnitude. Driven with
    arbitrary (non-optimal) duals, where the stationarity-energy term is large and a sign slip
    cannot hide behind a vanishing residual.
    """
    t, A_ub, b_ub, A_eq, b_eq, upper = _rich()
    z, _ = _rich_optimum()
    rng = np.random.default_rng(17)

    for _ in range(40):
        lam = np.concatenate([rng.normal(scale=2.0, size=1), rng.uniform(0.0, 3.0, size=9)])
        f_iv, d_iv, slag, energy = gap_intervals(z, lam, t, A_ub, b_ub, A_eq, b_eq, upper)
        diff = (f_iv - d_iv) - (slag + energy)
        assert diff.a <= 0 <= diff.b, "the exact identity failed to enclose zero"
        assert energy.a >= 0, "the stationarity energy must be nonnegative"


def test_the_identity_check_rejects_a_corrupted_dual_bound():
    """The identity check must actually FIRE. A dual bound shifted off its correct value is the one
    defect weak duality alone cannot see (a too-LOW bound still looks like a valid lower bound)."""
    import app.research.mr002.certificate as cert

    real = cert.gap_intervals

    def sabotaged(z_, lam_, *rest):
        f_iv, d_iv, slag, energy = real(z_, lam_, *rest)
        return f_iv, d_iv + iv.mpf(1), slag, energy      # d displaced by 1.0

    cert.gap_intervals = sabotaged
    try:
        with pytest.raises(CertificateDefect, match="LAGRANGIAN_IDENTITY_VIOLATION"):
            cert.certify(*_certify_args())
    finally:
        cert.gap_intervals = real


# ================================================================ the two-sided gate


def test_interval_CONTAINMENT_controls_the_decision_not_a_midpoint():
    """§14.2 — an interval straddling the band edge must FAIL even when its midpoint is inside."""
    from app.research.mr002.certificate import SignedGapCertificate

    def q(lo, hi):
        return SignedGapCertificate(
            gamma_lower=lo, gamma_upper=hi, primal_lower=0.0, primal_upper=0.0,
            dual_lower=0.0, dual_upper=0.0, lagrangian_slack=0.0, stationarity_energy=0.0,
            primal_interval_width=0.0, dual_interval_width=0.0,
            max_multiplier_clip=0.0, n_multipliers_clipped=0,
            qualifies=max(abs(lo), abs(hi)) <= SIGNED_GAP_MAX,
        )

    assert q(-1e-11, 1e-11).qualifies
    assert not q(-1e-9, 1e-11).qualifies        # midpoint inside, interval is NOT
    assert not q(-1e-11, 1e-9).qualifies


def test_a_NEGATIVE_signed_gap_within_tolerance_can_qualify():
    """§14.4 — THE correction. A point feasible only to within rounding has Gamma < 0, and that is
    not a defect: 2,054 square-root solves were disqualified by the withdrawn nonnegative rule.

    Direction matters, and it is not arbitrary: Gamma ~ S_lag = lam'(C'z - b), so the sign of the
    excursion is the sign of the multiplier-weighted violation. On this instance the equality
    multiplier is POSITIVE (nu = +1.73) while the active inequality and upper-bound multipliers
    push the other way, and nudging z UP is what nets out negative. Nudging it down makes Gamma
    POSITIVE — which is precisely the trap the first draft of this fixture fell into.
    """
    t, A_ub, b_ub, A_eq, b_eq, upper = _rich()
    z, lam = _rich_optimum()
    c = certify(z + 1e-13, lam, t, A_ub, b_ub, A_eq, b_eq, upper)

    assert c.gamma_upper < 0.0, "the fixture failed to produce a negative gap"
    assert abs(c.gamma_lower) <= SIGNED_GAP_MAX
    assert c.qualifies, "a negative gap inside the two-sided band must still qualify"
    assert classify(c) == "PASS"


def test_signed_gaps_beyond_the_band_fail_on_BOTH_sides():
    """§14.5."""
    z, lam, t, A_ub, b_ub, A_eq, b_eq, u = _certify_args()

    far = certify(z, -lam, t, A_ub, b_ub, A_eq, b_eq, u)         # inverted duals: Gamma >> 1e-10
    assert not far.qualifies
    assert far.gamma_lower > SIGNED_GAP_MAX
    assert classify(far) == "SIGNED_LAGRANGIAN_GAP_LIMIT_EXCEEDED"

    # The analytic instance's equality multiplier is NEGATIVE (nu = -0.8), so a POSITIVE violation
    # is what drives Gamma below the band. (z - 1e-3 would push it to +3.2e-3.)
    neg = certify(z + 1e-3, lam, t, A_ub, b_ub, A_eq, b_eq, u)
    assert not neg.qualifies
    assert neg.gamma_upper < -SIGNED_GAP_MAX
    assert classify(neg) == "SIGNED_LAGRANGIAN_GAP_LIMIT_EXCEEDED"


# ================================================================ folded == expanded


def test_folded_and_expanded_dual_bounds_agree():
    """§14 — the folded C/b/lambda convention removes four sign-mapping paths ONLY IF it is exactly
    equivalent to the expanded one. Arbitrary dual-feasible multipliers, nonzero in EVERY block."""
    t, A_ub, b_ub, A_eq, b_eq, upper = _rich()
    z, _ = _rich_optimum()
    rng = np.random.default_rng(3)

    for _ in range(40):
        lam = np.concatenate([rng.normal(scale=2.0, size=1), rng.uniform(0.05, 3.0, size=9)])
        assert lam[1:].min() > 0.0                              # all four blocks nonzero

        _f, d_iv, _s, _e = gap_intervals(z, lam, t, A_ub, b_ub, A_eq, b_eq, upper)
        d_expanded = _expanded_dual_bound(z, lam, t, A_ub, b_ub, A_eq, b_eq, upper)

        assert d_iv.a <= d_expanded <= d_iv.b, (
            "the folded interval does not enclose the expanded value — the two conventions "
            "disagree, which is the exact sign error the folding was meant to eliminate"
        )
        assert float(d_iv.delta) <= MAX_INTERVAL_WIDTH


def test_weak_duality_holds_for_arbitrary_dual_feasible_multipliers():
    """d(lam) <= p* for ANY dual-feasible lam. This survives the correction untouched: it is the
    DUAL bound that stays rigorous — only the SIGN of f(z) - d was ever in question."""
    t, A_ub, b_ub, A_eq, b_eq, upper = _rich()
    z_star, _ = _rich_optimum()
    p_star = float(np.sum((z_star - t) ** 2 / t))
    rng = np.random.default_rng(5)

    for _ in range(60):
        lam = np.concatenate([rng.normal(scale=4.0, size=1), rng.uniform(0.0, 5.0, size=9)])
        c = certify(z_star, lam, t, A_ub, b_ub, A_eq, b_eq, upper)
        assert c.dual_lower <= p_star + 1e-12, "the lower bound exceeded the optimum — sign error"


def test_a_falsified_dual_mapping_cannot_pass():
    """Everything else can be right and the gate still worthless if a WRONG dual can manufacture a
    small gap. Inverting the sign convention is the classic error — and the exact bug that produced
    a false 'close v1.1' verdict earlier in this program."""
    z, lam, t, A_ub, b_ub, A_eq, b_eq, u = _certify_args()
    assert certify(z, lam, t, A_ub, b_ub, A_eq, b_eq, u).qualifies
    assert not certify(z, -lam, t, A_ub, b_ub, A_eq, b_eq, u).qualifies


def test_a_falsified_dual_cannot_pass_on_the_RICH_instance_either():
    """The analytic instance has no inequality rows, so a sign error confined to the inequality or
    bound blocks would survive it. This one has both."""
    t, A_ub, b_ub, A_eq, b_eq, upper = _rich()
    z, lam = _rich_optimum()
    assert certify(z, lam, t, A_ub, b_ub, A_eq, b_eq, upper).qualifies

    flipped = lam.copy()
    flipped[1] = -flipped[1]                          # invert ONLY the inequality multiplier
    assert not certify(z, flipped, t, A_ub, b_ub, A_eq, b_eq, upper).qualifies


# ================================================================ conversion / projection / sign


def test_ieee754_values_convert_through_their_exact_binary_rational():
    """Never through str() or a shortened decimal. 0.1 is not 1/10, and a certificate that pretends
    otherwise has already lost the digits it claims to protect."""
    v = exact_iv(0.1)
    num, den = (0.1).as_integer_ratio()
    assert float(v.delta) == 0.0
    assert v.a == mpf(num) / mpf(den)
    assert v.a != mpf("0.1")

    r = rational_iv(Fraction(1, 3))                   # a general rational cannot be zero-width...
    assert r.a <= mpf(1) / mpf(3) <= r.b              # ...but it MUST enclose


def test_negative_multipliers_are_clipped_and_RECORDED_with_their_hex_values():
    t, A_ub, b_ub, A_eq, b_eq, upper = _rich()
    z, lam = _rich_optimum()
    lam = lam.copy()
    lam[3] = -1e-12

    projected, worst, clipped = project_dual(lam, 1)
    assert projected[3] == 0.0
    assert worst == pytest.approx(1e-12)
    assert projected[:1] == pytest.approx(lam[:1])           # equalities remain UNRESTRICTED
    assert clipped == ((3, (-1e-12).hex()),)                 # index + IEEE-754 hex, recorded

    c = certify(z, lam, t, A_ub, b_ub, A_eq, b_eq, upper)
    assert c.n_multipliers_clipped == 1
    assert c.clipped == ((3, (-1e-12).hex()),)               # surfaced, not laundered


def test_a_multiplier_beyond_the_dual_sign_limit_is_still_a_HARD_failure():
    """Projection constructs a certificate; it does NOT excuse a wrong-signed solver multiplier."""
    from app.research.mr002.joint_portfolio import _acceptance

    t, A_ub, b_ub, A_eq, b_eq, upper = _rich()
    z, lam = _rich_optimum()
    lam = lam.copy()
    lam[3] = -1e-3

    assert dual_sign_violation(lam, 1) == pytest.approx(1e-3)
    C, b = canonical_matrices(A_ub, b_ub, A_eq, b_eq, upper, 4)
    ck = _acceptance(z, lam, 1, np.diag(2.0 / t), 2.0 * np.ones(4), C, b,
                     A_ub, b_ub, A_eq, b_eq, upper)
    assert ck["dual_residual"] > 1e-9, "the registered dual gate must still reject this"


def test_a_non_canonical_hessian_is_rejected():
    """The certificate must be evaluated against the registered 2/t objective, never a
    solver-internal transformed Hessian — the sqrt and t-scaled formulations both carry one."""
    t = np.array([0.1, 0.2, 0.3, 0.4])
    verify_canonical_hessian(np.diag(2.0 / t), t)
    with pytest.raises(CertificateDefect):
        verify_canonical_hessian(2.0 * np.eye(4), t)          # the sqrt formulation's Hessian


# ================================================================ EXACT-RATIONAL REPAIR


def test_the_structural_precondition_is_asserted_not_assumed():
    """§14 — meq == 1 is a PRECONDITION of the one-coordinate construction. A model with 0 or 2+
    equalities must stop, never silently generalize."""
    assert_structure(np.ones((1, 3)), np.array([1.0]))
    with pytest.raises(CertificateDefect, match="meq == 1"):
        assert_structure(np.ones((2, 3)), np.array([1.0, 1.0]))
    with pytest.raises(CertificateDefect, match="meq == 1"):
        assert_structure(np.zeros((0, 3)), np.zeros(0))
    with pytest.raises(CertificateDefect, match="no nonzero coefficient"):
        assert_structure(np.zeros((1, 3)), np.array([0.0]))


def test_the_clipped_proposal_is_represented_EXACTLY():
    """§14.6 — the clip happens in rational arithmetic against exact rational bounds."""
    x = min(max(to_fraction(1.5), Fraction(0)), to_fraction(0.3))
    assert isinstance(x, Fraction)
    assert x == to_fraction(0.3)                              # exactly the bound, not 0.3 rounded


def test_every_absorber_candidate_satisfies_the_equality_IDENTICALLY():
    """§14.7 — 'identically' means in exact rational arithmetic, not to 1e-16."""
    t, A_ub, b_ub, A_eq, b_eq, upper = _rich()
    z, _ = _rich_optimum()
    zhat, k, n_cand, n_feas, _src = repair(z, t, A_ub, b_ub, A_eq, b_eq, upper)

    a = [to_fraction(v) for v in A_eq[0]]
    beta = to_fraction(b_eq[0])
    assert sum(a[i] * zhat[i] for i in range(4)) == beta      # EXACT equality, Fraction == Fraction
    assert n_cand == 4 and n_feas >= 1
    assert 0 <= k < 4


def test_the_selected_repair_is_EXACTLY_feasible():
    """§14.13 — every constraint verified in rational arithmetic. No numerical tolerance."""
    t, A_ub, b_ub, A_eq, b_eq, upper = _rich()
    z, _ = _rich_optimum()
    zhat, _k, _nc, _nf, _s = repair(z, t, A_ub, b_ub, A_eq, b_eq, upper)

    U = [to_fraction(v) for v in upper]
    assert all(Fraction(0) <= zhat[i] <= U[i] for i in range(4))
    for r in range(A_ub.shape[0]):
        lhs = sum(to_fraction(A_ub[r, i]) * zhat[i] for i in range(4))
        assert lhs <= to_fraction(b_ub[r])


def test_exact_verification_rejects_a_bound_violating_absorber():
    """§14.8 — an absorber whose correction pushes it outside [0, u] must be discarded.

    Driven through `exact_repair_from_proposal` with a DELIBERATELY far-off proposal. Going through
    `repair()` would prove nothing: the projection already lands on the equality, so every
    absorber's correction is ~1e-17 and all of them pass. The rejection path is only reachable
    when the proposal is genuinely off — which is exactly why the exact constructor is separable
    from the numerical proposal.
    """
    t = np.array([0.25, 0.25, 0.25, 0.25])
    upper = np.array([1e-6, 1.0, 1.0, 1.0])                   # coord 0 has almost no room
    A_ub, b_ub = np.zeros((0, 4)), np.zeros(0)
    A_eq, b_eq = np.ones((1, 4)), np.array([0.5])
    z = np.array([0.0, 0.2, 0.2, 0.2])
    proposal = np.array([0.0, 0.2, 0.2, 0.2])                 # sums to 0.6: absorb -0.1

    zhat, k, n_cand, n_feas, _e = exact_repair_from_proposal(
        proposal, z, t, A_ub, b_ub, A_eq, b_eq, upper)

    assert k != 0, "absorber 0 would need w_0 = -0.1 and must have been rejected"
    assert n_cand == 4 and n_feas == 3
    assert sum(to_fraction(A_eq[0, i]) * zhat[i] for i in range(4)) == to_fraction(0.5)


def test_exact_verification_rejects_an_INEQUALITY_violating_absorber():
    """§14.9 — and a structurally EMPTY inequality row is still evaluated exactly: it passes only
    when 0 <= b_ub."""
    t = np.array([0.25, 0.25, 0.25, 0.25])
    upper = np.ones(4)
    A_ub = np.array([[1.0, 0.0, 0.0, 0.0],                    # z0 <= 0.05
                     [0.0, 0.0, 0.0, 0.0]])                   # a structurally EMPTY row
    b_ub = np.array([0.05, 0.0])
    A_eq, b_eq = np.ones((1, 4)), np.array([0.8])
    z = np.array([0.05, 0.2, 0.2, 0.2])
    proposal = np.array([0.05, 0.2, 0.2, 0.2])                # sums to 0.65: absorb +0.15

    zhat, k, _nc, n_feas, _e = exact_repair_from_proposal(
        proposal, z, t, A_ub, b_ub, A_eq, b_eq, upper)

    assert k != 0, "absorbing into z0 would give z0 = 0.2 > 0.05 and must have been rejected"
    assert n_feas == 3
    assert sum(to_fraction(A_ub[0, i]) * zhat[i] for i in range(4)) <= to_fraction(0.05)


def test_an_empty_inequality_row_with_a_NEGATIVE_rhs_is_an_INVALID_MODEL():
    """`0 <= b_ub` is a real check, not a formality — and a zero row with b_ub < 0 is an invalid
    ORIGINAL MODEL, not a repair failure. Classifying it as REPAIR_CERTIFICATE_UNAVAILABLE would
    launder a broken model into a certificate-method stop."""
    t = np.array([0.25, 0.25])
    upper = np.ones(2)
    A_ub = np.zeros((1, 2))                                   # structurally empty...
    b_ub = np.array([-1.0])                                   # ...with an impossible rhs
    A_eq, b_eq = np.ones((1, 2)), np.array([0.5])
    z = np.array([0.25, 0.25])

    with pytest.raises(CertificateDefect, match="INVALID ORIGINAL MODEL"):
        exact_repair_from_proposal(z, z, t, A_ub, b_ub, A_eq, b_eq, upper)


def test_enumeration_finds_a_repair_where_the_largest_slack_absorber_FAILS():
    """§14.10 — THE reason enumeration replaced a heuristic pick.

    Coordinate 1 has by far the most bound slack, but a near-zero equality coefficient (1e-6), so
    absorbing the residual there demands a correction of ~3e5 and blows through its bound. A
    largest-slack heuristic would pick it, fail, and report REPAIR_CERTIFICATE_UNAVAILABLE — a
    false statement about the constructor dressed up as a statement about the problem.
    """
    t = np.array([0.25, 0.25, 0.25, 0.25])
    upper = np.array([1.0, 10.0, 1.0, 1.0])                   # coord 1: the most slack by far
    A_ub, b_ub = np.zeros((0, 4)), np.zeros(0)
    A_eq = np.array([[1.0, 1e-6, 1.0, 1.0]])                  # coord 1: a near-zero coefficient
    b_eq = np.array([0.9])
    z = np.array([0.2, 0.2, 0.2, 0.2])                        # a'z = 0.6000002 -> absorb ~0.3

    zhat, k, n_cand, n_feas, _e = exact_repair_from_proposal(
        z, z, t, A_ub, b_ub, A_eq, b_eq, upper)

    assert n_cand == 4
    assert k != 1, "the largest-slack coordinate must NOT win: its correction is ~3e5"
    assert n_feas == 3, "exactly the three well-conditioned absorbers should verify"
    a = [to_fraction(v) for v in A_eq[0]]
    assert sum(a[i] * zhat[i] for i in range(4)) == to_fraction(0.9)


def test_no_candidate_yields_REPAIR_CERTIFICATE_UNAVAILABLE_not_solver_invalidation():
    """§14.19 — the constructor failing says nothing about the solver or the feasible set."""
    t = np.array([0.25, 0.25])
    upper = np.array([0.1, 0.1])
    A_eq = np.ones((1, 2))
    b_eq = np.array([5.0])                                    # unreachable inside the box
    z = np.array([0.05, 0.05])

    with pytest.raises(RepairUnavailable, match="NO_EXACT_ABSORBER_CANDIDATE"):
        exact_repair_from_proposal(z, z, t, np.zeros((0, 2)), np.zeros(0), A_eq, b_eq, upper)


def test_a_merely_tolerance_feasible_point_is_not_a_certified_repair():
    """§14 — 'residual below TAU_PRIMAL' is exactly the standard that failed. The repaired point
    must satisfy the equality as an exact rational identity, and a 1e-16-off point does not."""
    t, A_ub, b_ub, A_eq, b_eq, upper = _rich()
    z, _ = _rich_optimum()

    a = [to_fraction(v) for v in A_eq[0]]
    beta = to_fraction(b_eq[0])
    # The raw solver point passes any sane numerical tolerance...
    assert abs(float((A_eq @ z - b_eq)[0])) < 1e-12
    # ...and is NOT exactly feasible. That distinction is the whole point of the repair.
    assert sum(a[i] * to_fraction(z[i]) for i in range(4)) != beta

    zhat, *_ = repair(z, t, A_ub, b_ub, A_eq, b_eq, upper)
    assert sum(a[i] * zhat[i] for i in range(4)) == beta      # the repair IS exactly feasible


def test_exact_minimum_distance_selection_is_shuffle_invariant():
    """§14.11 — permute the variables and the rows; the SAME repaired point must come back."""
    t, A_ub, b_ub, A_eq, b_eq, upper = _rich()
    z, _ = _rich_optimum()
    zhat, _k, _nc, _nf, _s = repair(z, t, A_ub, b_ub, A_eq, b_eq, upper)

    p = np.array([2, 0, 3, 1])
    zhat_p, _k2, _nc2, _nf2, _s2 = repair(
        z[p], t[p], A_ub[:, p], b_ub, A_eq[:, p], b_eq, upper[p])

    for i in range(4):
        assert zhat_p[i] == zhat[p[i]], "the repair is not shuffle-invariant"


def test_the_canonical_identity_resolves_a_true_exact_tie():
    """§14.12 — with two genuinely interchangeable coordinates the tie is broken by MODEL identity,
    not by matrix index and not by a float. Interchangeable coordinates give the same repair
    either way, which is what makes the choice safe."""
    t = np.array([0.25, 0.25])
    upper = np.array([1.0, 1.0])
    A_eq = np.ones((1, 2))
    b_eq = np.array([0.5])
    A_ub, b_ub = np.zeros((0, 2)), np.zeros(0)
    z = np.array([0.2, 0.2])                                  # perfectly symmetric

    k1 = canonical_key(0, t, upper, A_eq, A_ub, b_ub)
    k2 = canonical_key(1, t, upper, A_eq, A_ub, b_ub)
    assert k1 == k2, "the fixture is not actually a tie"

    zhat_a, _k, _nc, _nf, _s = repair(z, t, A_ub, b_ub, A_eq, b_eq, upper)
    zhat_b, _k, _nc, _nf, _s = repair(z[::-1], t[::-1], A_ub[:, ::-1], b_ub,
                                      A_eq[:, ::-1], b_eq, upper[::-1])
    assert set(zhat_a) == set(zhat_b)


# ================================================================ repaired gap / radius / agreement


def test_the_repaired_objective_and_gap_are_exact_and_NONNEGATIVE():
    """§§14.14-14.15 — exact feasibility + weak duality force Ghat >= 0. This is what the negative
    signed gap could never give us, and it is why the radius had to be rebuilt on it."""
    t, A_ub, b_ub, A_eq, b_eq, upper = _rich()
    z, lam = _rich_optimum()
    c = certify(z, lam, t, A_ub, b_ub, A_eq, b_eq, upper)
    r = certify_repair(z, c, t, A_ub, b_ub, A_eq, b_eq, upper)

    assert r.ghat_upper >= 0.0
    assert r.delta_upper >= 0.0
    assert r.radius_upper >= r.delta_upper
    assert r.f_zhat_upper >= c.dual_lower                     # f(zhat) >= d: weak duality


def test_the_repair_distance_interval_contains_the_true_distance():
    """The reported delta must be a rigorous UPPER bound on the exact distance.

    Compared EXACTLY: delta_upper^2 >= ||z - zhat||^2 as rationals. An earlier version of this
    fixture computed the "true" distance with a float sqrt and compared that — but a float sqrt
    carries its own rounding and can exceed a rigorous upper bound by an ulp, so the test would
    fail on a correct bound. The bound is exact; the yardstick has to be too."""
    t, A_ub, b_ub, A_eq, b_eq, upper = _rich()
    z, lam = _rich_optimum()
    c = certify(z, lam, t, A_ub, b_ub, A_eq, b_eq, upper)
    r = certify_repair(z, c, t, A_ub, b_ub, A_eq, b_eq, upper)

    d2 = sum((r.zhat[i] - to_fraction(z[i])) ** 2 for i in range(4))     # exact rational
    assert to_fraction(r.delta_upper) ** 2 >= d2, "delta_upper is not an upper bound"
    assert r.delta_upper > 0


def test_the_pairwise_radius_bound_holds_on_an_analytic_example():
    """§14.17 — and it must hold on the case the OLD gate could not: two points straddling the
    optimum, where the signed gap is negative and its radius would have collapsed to zero."""
    t, A_ub, b_ub, A_eq, b_eq, upper = _rich()
    z_star, lam = _rich_optimum()
    d = np.array([1.0, -1.0, 1.0, -1.0]) * 1e-7               # null-space of the all-ones equality
    z1, z2 = z_star + d, z_star - 3 * d

    c1 = certify(z1, lam, t, A_ub, b_ub, A_eq, b_eq, upper)
    c2 = certify(z2, lam, t, A_ub, b_ub, A_eq, b_eq, upper)
    r1 = certify_repair(z1, c1, t, A_ub, b_ub, A_eq, b_eq, upper)
    r2 = certify_repair(z2, c2, t, A_ub, b_ub, A_eq, b_eq, upper)

    ok, dz, bound = agreement(r1, r2, z1, z2)
    assert ok, f"radius-sum bound violated: {dz:.3e} > {bound:.3e}"

    ok_o, df, ob = objective_agreement(r1, r2, c1, c2)
    assert ok_o, f"objective-agreement bound violated: {df:.3e} > {ob:.3e}"


def test_the_objective_agreement_bound_holds_on_an_analytic_example():
    """§14.18 — |f(z_s) - f(z*)| <= |f(z_s) - f(zhat_s)| + Ghat_s, checked against the KNOWN
    optimum rather than against itself."""
    t, A_ub, b_ub, A_eq, b_eq, upper = _rich()
    z_star, lam = _rich_optimum()
    f_star = float(np.sum((z_star - t) ** 2 / t))
    z = z_star + 1e-8 * np.array([1.0, -1.0, 1.0, -1.0])

    c = certify(z, lam, t, A_ub, b_ub, A_eq, b_eq, upper)
    r = certify_repair(z, c, t, A_ub, b_ub, A_eq, b_eq, upper)

    f_z = float(np.sum((z - t) ** 2 / t))
    assert abs(f_z - f_star) <= r.objective_bound_upper + 1e-30


# ================================================================ the still-owed native fixture


def test_native_wrapper_maps_a_genuinely_nonzero_optimal_LOWER_bound_multiplier():
    """§14.21 — the fixture owed from the previous ruling.

    The MR-002 objective family CANNOT produce a strictly active lower bound at an optimum (proved
    in `scripts/mr002_find_equivalence_fixture.py`), so the canonical lower-bound sign path is
    never exercised by optimal duals there. This fixture leaves that family: a generic QP whose
    optimum genuinely pins a variable at zero with a strictly positive multiplier, solved by the
    NATIVE wrapper, checking that the canonical C/b mapping reproduces stationarity exactly.

        min 1/2 w'w - a'w,   a = [-1, 2],   0 <= w <= 3
        optimum w* = [0, 2];  lower-bound multiplier on w_0 is 1 > 0.
    """
    import quadprog

    n = 2
    a = np.array([-1.0, 2.0])
    upper = np.array([3.0, 3.0])
    A_ub, b_ub = np.zeros((0, n)), np.zeros(0)
    A_eq, b_eq = np.zeros((0, n)), np.zeros(0)

    C, b = canonical_matrices(A_ub, b_ub, A_eq, b_eq, upper, n)
    out = quadprog.solve_qp(np.eye(n), a, C, b, 0)
    w = np.asarray(out[0], float)
    lam = np.asarray(out[4], float)

    assert w == pytest.approx([0.0, 2.0], abs=1e-12)
    lower_block = lam[:n]                                     # the I block: z >= 0
    assert lower_block[0] > 1e-9, "the optimal LOWER-bound multiplier is not strictly positive"
    assert np.all(lam >= -1e-12), "a bound multiplier came back negative — sign mapping is wrong"

    # stationarity in the canonical convention: Hw - a = C lam
    assert np.allclose(np.eye(n) @ w - a, C @ lam, atol=1e-12), (
        "the canonical C/b mapping does not reproduce stationarity for an active LOWER bound"
    )


def test_the_fixture_instance_has_NONZERO_multipliers():
    """Guards the guard. If the analytic instance drifts back to S = sum(t), every multiplier is
    zero, negating the duals is a no-op, and the falsification fixture silently stops testing
    anything. That is how a gate rots."""
    z, lam, t, *_ = _certify_args()
    assert float(np.max(np.abs(lam))) > 1e-3
    assert float(np.sum((z - t) ** 2 / t)) > 1e-3


# ================================================================ R2 TIGHTENED PROPOSAL (§12)
#
# R1 handed the exact constructor a point sitting ON the boundary of the feasible set. In exact
# rational arithmetic the active rows were violated by ~1e-17, leaving the one-coordinate absorber
# no slack to work with, and 46 of 50 overlaps produced no certificate. R2 tightens the NUMERICAL
# PROPOSAL so the constructor is handed interior points instead.
#
# The proposal is NOT evidence. Exact verification against the ORIGINAL untightened constraints
# remains the sole feasibility authority, and these fixtures exist to keep that true.


def test_a_zero_inequality_row_with_b_equals_zero_is_NOT_tightened():
    """§7 — tightening it would turn `0 <= 0` into the infeasible `0 <= -eta`, manufacturing a
    failure out of a row that is trivially satisfied."""
    A_ub = np.array([[1.0, 1.0], [0.0, 0.0]])          # row 1 is structurally empty
    b_ub = np.array([0.5, 0.0])
    A_eq, b_eq = np.ones((1, 2)), np.array([0.4])
    upper = np.ones(2)

    A, b, keep = build_tightened_problem(A_ub, b_ub, A_eq, b_eq, upper)

    assert keep == [0], "the empty row must be omitted from the tightened numerical proposal"
    assert A.shape[0] == 1 + 1 + 2 + 2                 # eq + one nonzero ineq + lower + upper
    assert empty_rows_of(A_ub, b_ub) == ((1, "0"),)    # retained for EXACT verification


def test_a_zero_inequality_row_with_NEGATIVE_b_invalidates_the_original_model():
    """§12 — `0 <= b` is false. That is a broken model, not a repair failure, and must not be
    laundered into REPAIR_CERTIFICATE_UNAVAILABLE."""
    with pytest.raises(CertificateDefect, match="INVALID ORIGINAL MODEL"):
        empty_rows_of(np.zeros((1, 2)), np.array([-1.0]))


def test_every_NONZERO_inequality_row_receives_exactly_the_frozen_eta_tightening():
    """§9 — and the EQUALITY is submitted UNCHANGED, in Clarabel row form."""
    A_ub = np.array([[1.0, 0.0], [0.0, 1.0]])
    b_ub = np.array([0.5, 0.25])
    A_eq, b_eq = np.array([[2.0, 3.0]]), np.array([0.4])
    upper = np.array([0.8, 0.9])

    A, b, _keep = build_tightened_problem(A_ub, b_ub, A_eq, b_eq, upper)

    assert np.array_equal(A[0], A_eq[0]), "the equality row was altered"
    assert b[0] == b_eq[0], "the equality rhs was tightened — it must NOT be"

    assert b[1] == 0.5 - ETA_FLOAT                     # A_ub w <= b_ub - eta
    assert b[2] == 0.25 - ETA_FLOAT
    assert b[3] == -ETA_FLOAT and b[4] == -ETA_FLOAT   # -w <= -eta   i.e.  w >= eta
    assert b[5] == 0.8 - ETA_FLOAT                     # w <= u - eta
    assert b[6] == 0.9 - ETA_FLOAT
    assert np.array_equal(A[3:5], -np.eye(2))
    assert np.array_equal(A[5:7], np.eye(2))


def test_the_tightened_box_is_rejected_when_u_is_not_greater_than_2_eta():
    """§12 — TIGHTENED_BOX_EMPTY. Do not shrink eta; do not revert to the untightened proposal."""
    assert_tightened_box_nonempty(np.array([1.0, 1e-6]))        # both comfortably > 2*eta
    with pytest.raises(RepairUnavailable, match="TIGHTENED_BOX_EMPTY"):
        assert_tightened_box_nonempty(np.array([1.0, 1e-13]))   # 1e-13 <= 2e-12


def test_the_quadprog_and_clip_proposal_paths_are_UNREACHABLE():
    """§8 — both retired proposal paths are GONE from the module, not merely unused.

    R1's clip(z_s) would bypass the tightening that defines R2. quadprog reported a FALSE
    infeasibility on 50/50 of sample A (an independent LP found those same tightened sets
    feasible), so it is disqualified as the proposal solver. Leaving either reachable would let a
    silent fallback re-enter."""
    import inspect

    import app.research.mr002.repair as rp

    assert not hasattr(rp, "_propose"), "the R1 clip proposal is still present"
    m = rp.manifest()
    assert m["untightened_fallback_reachable"] is False
    assert m["quadprog_proposal_path"].startswith("RETIRED")

    src = inspect.getsource(rp)
    assert "import quadprog" not in src, "quadprog is still importable from the repair module"
    assert "highspy" not in src and "import piqp" not in src


def test_an_R2_proposal_with_margin_yields_an_exact_feasible_absorber():
    """§12 — the mechanism R2 exists to restore, on the instance family that defeated R1."""
    t, A_ub, b_ub, A_eq, b_eq, upper = _rich()
    z, _ = _rich_optimum()

    zhat, k, n_cand, n_feas, empties = repair(z, t, A_ub, b_ub, A_eq, b_eq, upper)

    assert n_feas >= 1, "R2 failed to give the constructor a usable interior proposal"
    assert n_cand == 4
    assert empties == ()
    a = [to_fraction(v) for v in A_eq[0]]
    assert sum(a[i] * zhat[i] for i in range(4)) == to_fraction(b_eq[0])   # EXACT equality
    assert 0 <= k < 4


def test_an_equality_correction_that_violates_an_ORIGINAL_constraint_is_still_rejected():
    """§12 — tightening supplies margin; it does not suspend verification. A correction larger than
    the available slack must still fail. This is why the record may NOT say the repair "passes by
    construction"."""
    t = np.array([0.25, 0.25, 0.25, 0.25])
    upper = np.array([1e-6, 1.0, 1.0, 1.0])
    A_ub, b_ub = np.zeros((0, 4)), np.zeros(0)
    A_eq, b_eq = np.ones((1, 4)), np.array([0.5])
    z = np.array([0.0, 0.2, 0.2, 0.2])
    proposal = np.array([0.0, 0.2, 0.2, 0.2])                  # absorbing -0.1 into coord 0 fails

    _zhat, k, _nc, n_feas, _e = exact_repair_from_proposal(
        proposal, z, t, A_ub, b_ub, A_eq, b_eq, upper)
    assert k != 0 and n_feas == 3


def test_exact_verification_uses_the_ORIGINAL_constraints_not_the_tightened_ones():
    """§12 — THE property that keeps the certificate meaningful. A point sitting exactly ON an
    original bound IS feasible and must be accepted, even though the tightened proposal would never
    have produced it. Verifying against the tightened set would reject a legitimately feasible point
    and quietly narrow the certified set."""
    t = np.array([0.25, 0.25])
    upper = np.array([0.5, 0.5])
    A_ub, b_ub = np.zeros((0, 2)), np.zeros(0)
    A_eq, b_eq = np.ones((1, 2)), np.array([0.75])
    z = np.array([0.25, 0.5])
    proposal = np.array([0.25, 0.5])                            # coord 1 sits ON its upper bound

    zhat, _k, _nc, n_feas, _e = exact_repair_from_proposal(
        proposal, z, t, A_ub, b_ub, A_eq, b_eq, upper)

    assert n_feas >= 1, "a point exactly ON an original bound was rejected as infeasible"
    assert zhat[1] == to_fraction(0.5)                          # accepted AT the bound
    assert sum(zhat) == to_fraction(0.75)


def test_a_tightened_proposal_can_still_be_certificate_unavailable():
    """§12 — R2 is not a guarantee. When no absorber verifies, the answer is a certificate-METHOD
    stop; it never invalidates the solver."""
    t = np.array([0.25, 0.25])
    upper = np.array([0.1, 0.1])
    A_eq, b_eq = np.ones((1, 2)), np.array([5.0])               # unreachable inside the box
    z = np.array([0.05, 0.05])

    with pytest.raises(RepairUnavailable):
        repair(z, t, np.zeros((0, 2)), np.zeros(0), A_eq, b_eq, upper)


def test_structurally_empty_row_detection_is_shuffle_invariant():
    """§12 — detection is on exact values, so permuting rows or variables cannot change WHICH rows
    are empty (only their labels)."""
    A_ub = np.array([[1.0, 2.0], [0.0, 0.0], [3.0, 0.0]])
    b_ub = np.array([0.5, 0.0, 0.25])

    base = {rhs for _r, rhs in empty_rows_of(A_ub, b_ub)}
    rows = np.array([2, 0, 1])
    cols = np.array([1, 0])
    shuffled = {rhs for _r, rhs in empty_rows_of(A_ub[np.ix_(rows, cols)], b_ub[rows])}

    assert base == shuffled == {"0"}
    assert len(empty_rows_of(A_ub, b_ub)) == 1


def test_the_manifest_binds_eta_the_solver_path_and_the_profile():
    """§12 — eta as an exact rational, as an IEEE-754 value, and as hex; plus the solver path."""
    m = manifest()
    assert m["profile"] == PROPOSAL_PROFILE == "EXACT_REPAIR_PROPOSAL_R2_CLARABEL_C1"
    assert m["eta_exact_rational"] == "1/1000000000000"
    assert Fraction(1, 10**12) == ETA
    assert m["eta_ieee754"] == ETA_FLOAT == 1e-12
    assert m["eta_ieee754_hex"] == ETA_HEX == (1e-12).hex()
    assert "clarabel" in m["proposal_solver"]
    assert "ORIGINAL" in m["feasibility_authority"]


def test_the_R2_repair_is_shuffle_invariant_end_to_end():
    """The R1 shuffle-invariance obligation carries over to the tightened proposal path."""
    t, A_ub, b_ub, A_eq, b_eq, upper = _rich()
    z, _ = _rich_optimum()
    zhat, *_ = repair(z, t, A_ub, b_ub, A_eq, b_eq, upper)

    p = np.array([2, 0, 3, 1])
    zhat_p, *_ = repair(z[p], t[p], A_ub[:, p], b_ub, A_eq[:, p], b_eq, upper[p])

    for i in range(4):
        assert zhat_p[i] == zhat[p[i]], "the R2 repair is not shuffle-invariant"


# ================================================================ R2-C1 CLARABEL PROPOSAL (§9)
#
# quadprog reported `constraints are inconsistent` on 50/50 of regression sample A, while an
# independent LP found those same tightened sets FEASIBLE — a false infeasibility, the same
# Goldfarb-Idnani mode that defeats QUADPROG_SQRT on its five registered instances. The accepted
# Stage-3 point sits on a degenerate vertex (typically 16 of 18 nonzero rows carry slack below
# eta), and tightening every near-active row drives an active-set method into a rank-deficient
# working set.
#
# Clarabel is an interior-point method. The tightened problem is DESIGNED to have an interior, and
# finding one is what such a method is for.
#
# The proposal still carries NO evidentiary authority. Only its primal vector is consumed, and
# exact verification against the ORIGINAL untightened constraints remains the sole authority.


def _clarabel_settings():
    import clarabel

    import app.research.mr002.repair as rp
    return rp._settings(clarabel)


def test_the_clarabel_objective_is_exactly_identity_P_and_minus_z():
    """§9 — P = I, q = -z_s. The omitted constant does not move the minimizer."""
    m = manifest()
    assert m["objective"].startswith("P = I, q = -z_s")

    import inspect

    import app.research.mr002.repair as rp
    src = inspect.getsource(rp.propose_r2)
    assert "sp.csc_matrix(np.eye(n))" in src
    assert "q = -z_s[p]" in src


def test_the_configured_1e_14_tolerances_are_SET_AND_READ_BACK():
    """§9 — a setting that does not read back is a setting that was not applied. And the tolerance
    is DERIVED from eta (eps = eta/100): at 1e-10 the original-set slack `eta - eps` would go
    NEGATIVE and the tightening would buy nothing."""
    import app.research.mr002.repair as rp

    s, want = _clarabel_settings()
    rp._verify_readback(s, want)                       # raises on mismatch

    assert want["tol_feas"] == want["tol_gap_abs"] == 1e-14 == rp.PROPOSAL_TOL
    assert rp.PROPOSAL_TOL == rp.ETA_FLOAT / 100
    assert float(s.tol_feas) == 1e-14
    assert int(s.max_iter) == 500
    assert int(s.max_threads) == 1


def test_the_validated_clarabel_field_mapping_is_IMPORTED_not_rederived():
    """§4 — re-deriving the Clarabel binding is exactly what produced a false 'close v1.1' verdict:
    an inverted dual sign convention plus none of the pinned regularization config. The
    owner-approved amendment pins `static_regularization_constant` (documented as
    `static_regularization_eps`), separate from `static_regularization_proportional`."""
    import app.research.mr002.repair as rp
    from scripts.mr002_characterize_native_qp import CLARABEL_PROPORTIONAL as VALIDATED

    s, want = _clarabel_settings()
    assert want["static_regularization_constant"] == 1e-8
    assert want["static_regularization_proportional"] == VALIDATED == rp.CLARABEL_PROPORTIONAL
    assert want["direct_solve_method"] == "qdldl"
    assert float(s.static_regularization_constant) == 1e-8


def test_a_readback_mismatch_is_TIGHTENED_PROPOSAL_NOT_OBTAINED():
    """§5 — not a shrug, and not a silent substitution."""
    import app.research.mr002.repair as rp

    s, want = _clarabel_settings()
    bad = dict(want)
    bad["tol_feas"] = 1e-30                            # never actually set on `s`
    with pytest.raises(RepairUnavailable, match="TIGHTENED_PROPOSAL_NOT_OBTAINED"):
        rp._verify_readback(s, bad)


def test_only_Solved_is_accepted_and_AlmostSolved_is_REJECTED():
    """§5 — reduced-accuracy status is not accepted. A near-miss proposal is exactly the thing that
    would silently reintroduce the ~1e-17 boundary violations R2 exists to remove."""
    import app.research.mr002.repair as rp

    m = manifest()
    assert m["accepted_status"] == ["Solved"]
    assert "AlmostSolved" in m["rejected_statuses"]

    import inspect
    src = inspect.getsource(rp.propose_r2)
    assert 'status != "Solved"' in src
    assert "AlmostSolved is NOT accepted" in src


def test_a_clarabel_failure_is_REPAIR_CERTIFICATE_UNAVAILABLE_not_stage3_invalidation():
    """§9 — the constructor failing to obtain a proposal says nothing about the Stage-3 solver."""
    t = np.array([0.25, 0.25])
    upper = np.array([0.1, 0.1])
    A_eq, b_eq = np.ones((1, 2)), np.array([5.0])      # genuinely unreachable inside the box
    z = np.array([0.05, 0.05])

    with pytest.raises(RepairUnavailable):
        repair(z, t, np.zeros((0, 2)), np.zeros(0), A_eq, b_eq, upper)


def test_no_clarabel_dual_or_reported_objective_enters_the_certificate():
    """§6 — ONLY the primal vector is consumed. Clarabel's duals, objective, residuals, internal
    scaling and internal certificate have no evidentiary authority here."""
    import inspect

    import app.research.mr002.repair as rp

    src = inspect.getsource(rp.propose_r2)
    assert "sol.x" in src
    assert "sol.z" not in src, "a Clarabel DUAL is being read"
    assert "sol.obj" not in src, "a Clarabel objective is being read"
    assert manifest()["proposal_output_consumed"].startswith("primal vector x ONLY")


def test_the_primal_proposal_is_converted_through_as_integer_ratio():
    """§6 — the proposal enters the exact world through exact binary rationals, nothing else."""
    import inspect

    import app.research.mr002.repair as rp

    src = inspect.getsource(rp.exact_repair_from_proposal)
    assert "to_fraction(w_tilde[i])" in src
    assert "as_integer_ratio" in inspect.getsource(rp.to_fraction)


def test_a_DEGENERATE_tightened_projection_is_solved_and_reaches_the_exact_constructor():
    """§9 — THE fixture that reproduces the failure mode.

    A vertex pinned by many simultaneously-active rows: exactly the geometry on which quadprog
    answered `constraints are inconsistent`. Clarabel must solve it AND the exact constructor must
    then certify membership in the ORIGINAL set.
    """
    n = 6
    t = np.full(n, 0.2)
    upper = np.full(n, 0.5)
    # FOUR rows simultaneously tight at z, plus a structurally empty one. This is the geometry on
    # which the active-set proposal reported a false infeasibility. (Chosen by probing rather than
    # by guessing: Clarabel's AlmostSolved outcomes at 1e-14 do NOT track rank-deficiency -- an
    # exactly duplicated row solves, while some full-rank overlapping-cap sets do not. See
    # `scripts/mr002_probe_degenerate.py` and `test_an_ALMOST_SOLVED_proposal_is_refused`.)
    A_ub = np.array([
        [1.0, 1.0, 0.0, 0.0, 0.0, 0.0],
        [0.0, 0.0, 1.0, 1.0, 0.0, 0.0],
        [0.0, 1.0, 1.0, 0.0, 0.0, 0.0],
        [0.0, 0.0, 0.0, 0.0, 1.0, 1.0],
        [0.0, 0.0, 0.0, 0.0, 0.0, 0.0],      # structurally empty
    ])
    b_ub = np.array([0.30, 0.30, 0.30, 0.50, 0.0])
    A_eq, b_eq = np.ones((1, n)), np.array([0.90])
    z = np.array([0.15, 0.15, 0.15, 0.15, 0.15, 0.15])   # sits ON rows 0,1,2

    zhat, k, n_cand, n_feas, empties = repair(z, t, A_ub, b_ub, A_eq, b_eq, upper)

    assert n_feas >= 1, "Clarabel failed to give the constructor a usable interior proposal"
    assert n_cand == n
    assert empties == ((4, "0"),)                        # empty row detected and retained

    # ORIGINAL-set membership, in exact rational arithmetic.
    U = [to_fraction(v) for v in upper]
    assert all(Fraction(0) <= zhat[i] <= U[i] for i in range(n))
    assert sum(zhat) == to_fraction(0.90)                # the equality holds IDENTICALLY
    for r in range(A_ub.shape[0]):
        lhs = sum(to_fraction(A_ub[r, i]) * zhat[i] for i in range(n))
        assert lhs <= to_fraction(b_ub[r]), f"original inequality row {r} violated"
    assert 0 <= k < n


def test_the_exact_constructor_still_verifies_the_ORIGINAL_untightened_set_under_C1():
    """§6, §9 — the proposal is interior, but the certificate must cover the FULL original feasible
    set. A point exactly ON an original bound is feasible and must be accepted."""
    t = np.array([0.25, 0.25])
    upper = np.array([0.5, 0.5])
    A_eq, b_eq = np.ones((1, 2)), np.array([0.75])
    z = np.array([0.25, 0.5])
    proposal = np.array([0.25, 0.5])                     # coord 1 sits ON its upper bound

    zhat, _k, _nc, n_feas, _e = exact_repair_from_proposal(
        proposal, z, t, np.zeros((0, 2)), np.zeros(0), A_eq, b_eq, upper)

    assert n_feas >= 1, "a point exactly ON an original bound was rejected as infeasible"
    assert zhat[1] == to_fraction(0.5)


def test_row_and_variable_shuffling_preserve_the_C1_proposal_and_the_selected_repair():
    """§9 — the whole path, proposal included, must be shuffle-invariant."""
    t, A_ub, b_ub, A_eq, b_eq, upper = _rich()
    z, _ = _rich_optimum()
    zhat, *_ = repair(z, t, A_ub, b_ub, A_eq, b_eq, upper)

    p = np.array([2, 0, 3, 1])
    zhat_p, *_ = repair(z[p], t[p], A_ub[:, p], b_ub, A_eq[:, p], b_eq, upper[p])

    for i in range(4):
        assert zhat_p[i] == zhat[p[i]], "the R2-C1 repair is not shuffle-invariant"


def test_the_C1_manifest_binds_the_proposal_path():
    """§4 — profile, solver, settings, eta in three forms, ABI, and the module source hash."""
    m = manifest()
    assert m["profile"] == "EXACT_REPAIR_PROPOSAL_R2_CLARABEL_C1"
    assert "clarabel" in m["proposal_solver"]
    assert m["clarabel_version"]
    assert m["clarabel_settings"]["tol_feas"] == 1e-14
    assert m["clarabel_settings"]["max_iter"] == 500
    assert m["fresh_instance_per_proposal"] is True
    assert m["warm_start"] is False
    assert m["cross_instance_state"] is False
    assert m["eta_exact_rational"] == "1/1000000000000"
    assert m["eta_ieee754_hex"] == (1e-12).hex()
    assert len(m["repair_module_source_sha256"]) == 64
    assert m["python_abi"]


def test_an_ALMOST_SOLVED_proposal_is_refused_rather_than_used():
    """§5 — reduced accuracy is not accepted, and the refusal is a certificate-METHOD stop.

    On a rank-deficient tightened problem (an exactly duplicated inequality row) Clarabel returns
    `AlmostSolved` at the derived 1e-14 tolerance. Using that point would silently reintroduce the
    boundary violations R2 exists to remove, so it must be refused — and refusing it says nothing
    about the Stage-3 solver."""
    n = 6
    t = np.full(n, 0.2)
    upper = np.full(n, 0.5)
    A_ub = np.array([
        [1.0, 1.0, 0.0, 0.0, 0.0, 0.0],
        [0.0, 0.0, 1.0, 1.0, 0.0, 0.0],
        [0.0, 1.0, 1.0, 0.0, 0.0, 0.0],
    ])
    b_ub = np.array([0.30, 0.30, 0.30])
    A_eq, b_eq = np.ones((1, n)), np.array([0.90])
    z = np.full(n, 0.15)

    with pytest.raises(RepairUnavailable, match="TIGHTENED_PROPOSAL_NOT_OBTAINED"):
        repair(z, t, A_ub, b_ub, A_eq, b_eq, upper)


def test_the_canonical_proposal_order_is_MODEL_defined_not_layout_defined():
    """The fix for Clarabel's ordering dependence. The permutation must be derived from the model
    and z_s, so the SAME problem presented under any layout submits identical matrices.

    z_s belongs in the key: the proposal objective is -z_s, so two variables identical in the model
    but carrying different z_s are NOT interchangeable, and a key that ignored z_s would fail to
    define a unique order."""
    import app.research.mr002.repair as rp

    t, A_ub, b_ub, A_eq, b_eq, upper = _rich()
    z, _ = _rich_optimum()

    p0, r0 = rp.canonical_order(z, A_ub, b_ub, A_eq, b_eq, upper)
    perm = np.array([2, 0, 3, 1])
    p1, r1 = rp.canonical_order(z[perm], A_ub[:, perm], b_ub, A_eq[:, perm], b_eq, upper[perm])

    # the same variables, in the same canonical sequence, regardless of the incoming layout
    assert [int(perm[i]) for i in p1] == list(p0)
    assert len(r0) == len(r1)
