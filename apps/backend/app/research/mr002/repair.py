"""MR-002 Stage-3 — EXACT-RATIONAL FEASIBLE-REPAIR CERTIFICATE, proposal profile R2.

The agreement radius cannot come from the signed Lagrangian gap. That gap is NEGATIVE at a point
feasible only to within rounding, and `sqrt(2*max(Gamma,0)/m)` would collapse the radius to zero —
the exact defect that invalidated the previous specification. A KKT-residual inflation term is also
forbidden: a residual norm is not objective suboptimality.

So the radius is rebuilt on a point that is EXACTLY feasible:

    z_s        the solver's accepted point (feasible only to within rounding)
    zhat_s     an EXACTLY feasible rational point, PROVED by exact verification
    delta_s    ||z_s - zhat_s||                       (outward-rounded upper bound)
    Ghat_s     f(zhat_s) - d_s   >= 0                 (weak duality + EXACT feasibility)

    ||zhat_s - z*|| <= sqrt(2*Ghat_s/m)               strong convexity, now legitimately applicable
    ||z_s   - z*|| <= delta_s + sqrt(2*Ghat_s/m) =: R_s          triangle inequality
    ||z_1 - z_2||  <= R_1 + R_2 + 1e-10

WHY PROPOSAL PROFILE R2 EXISTS
------------------------------
Profile R1 projected z_s onto the feasible set and handed the result to the exact constructor. It
failed on 46 of 50 overlaps. The constructor was right to fail: the projection lands ON the
boundary — active rows tight, coordinates pinned at 0 or u — so in exact rational arithmetic those
rows are VIOLATED by ~1e-17 roughly half the time. A one-coordinate absorber cannot repair a
violated row r when A_ub[r, k] == 0, and any nonzero correction to a coordinate already at a bound
leaves the box.

R2 gives the constructor INTERIOR proposals instead, by tightening the numerical proposal problem:

    min 1/2 ||w - z_s||^2
    s.t.  A_eq w  = b_eq                    (UNCHANGED — the equality is never tightened)
          A_ub,j w <= b_ub,j - eta          (nonzero rows only)
          eta <= w_i <= u_i - eta
          eta = 1e-12, frozen

⚠ THIS PROVES NOTHING BY ITSELF, AND THE RECORD MUST NOT SAY IT DOES.
Tightening supplies a predeclared interior numerical proposal. **Exact absorber enumeration and
exact verification against the ORIGINAL, UNTIGHTENED constraints remain the sole feasibility
authority.** The equality correction can still exceed the available slack, and when it does the
answer is REPAIR_CERTIFICATE_UNAVAILABLE — not a quiet retry.

There is NO untightened fallback. R1's `clip(z_s)` path is deliberately gone: leaving it reachable
would silently bypass the tightening that defines R2.

STRUCTURALLY EMPTY ROWS. A row whose coefficients are all exactly zero is NOT tightened — that
would turn `0 <= b_j` into the infeasible `0 <= -eta`. It is omitted from the numerical proposal
and RETAINED in the exact verification, where it passes only when `0 <= b_j`. A zero row with
`b_j < 0` is an invalid original model, not a repair failure.

STRUCTURAL PRECONDITION. meq == 1, asserted (`assert_structure`). A model with zero, two or more
equalities is NOT handled and must NOT be silently generalized.

ABSORBER ENUMERATION. Every eligible coordinate is tried and verified exactly; the closest
exact-feasible candidate wins. A single preselected absorber would confuse an unlucky coordinate
choice with the absence of a repair: a coordinate can have ample bound slack and still need an
enormous correction because its equality coefficient is tiny.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from fractions import Fraction

import numpy as np
from mpmath import iv

from app.research.mr002.certificate import (
    CertificateDefect,
    f_up,
    rational_iv,
    to_fraction,
)

AGREEMENT_SLACK = 1e-10
OBJECTIVE_SLACK = 1e-12

# ---- proposal profile R2-C1, FROZEN. One profile, one solver. No sweep, no adaptive eta, no
# ---- per-instance eta, no second tightening level, no alternate solver, no untightened fallback.
#
# The quadprog proposal path is RETIRED. It reported `constraints are inconsistent` on 50/50 of
# regression sample A while an independent LP found those same tightened sets FEASIBLE — a false
# infeasibility, the same Goldfarb-Idnani mode that defeats QUADPROG_SQRT on its five registered
# instances. The accepted Stage-3 point sits on a degenerate vertex (typically 16 of 18 nonzero
# rows carry slack below eta), and tightening every near-active row drives an active-set method
# into a rank-deficient working set.
#
# Clarabel is an INTERIOR-POINT method: the tightened problem is designed to have an interior, and
# finding one is what such a method is for. It is also algorithmically distinct from the failed
# path and independent of PIQP, which keeps the offline repair separate from the production
# fallback.
PROPOSAL_PROFILE = "EXACT_REPAIR_PROPOSAL_R2_CLARABEL_C1"
ETA = Fraction(1, 10**12)                 # the exact rational
ETA_FLOAT = 1e-12                         # the IEEE-754 value submitted to the proposal solver
ETA_HEX = ETA_FLOAT.hex()

# Derived from eta, never fitted to a result. The proposal's residual against the TIGHTENED
# constraints must be strictly smaller than the tightening itself, or the original-set slack it was
# supposed to buy is gone: original slack >= eta - eps. eps = eta/100 leaves ~1e-12 of margin.
# (A tolerance of 1e-10 would make eta - eps NEGATIVE and defeat the entire purpose.)
PROPOSAL_TOL = 1e-14
PROPOSAL_MAX_ITER = 500
PROPOSAL_TIME_LIMIT = 60.0

# Field names and regularization values are IMPORTED from the validated Clarabel path, not
# re-derived. Re-deriving them is exactly what produced a false "close v1.1" verdict: an inverted
# dual sign convention plus none of the pinned regularization config. The owner-approved amendment
# on file records that the Python binding's base static-regularization control is
# `static_regularization_constant` (documented as `static_regularization_eps`), pinned separately
# from `static_regularization_proportional`; neither is aliased.
CLARABEL_STATIC_REG = 1e-8
CLARABEL_PROPORTIONAL = 4.930380657631324e-32
CLARABEL_DYNAMIC_EPS = 1e-13
CLARABEL_DYNAMIC_DELTA = 2e-7
PROPOSAL_SOLVER = (
    "clarabel.DefaultSolver, P = I, q = -z_s, tightened constraints, single-threaded, "
    "fresh instance per proposal, no warm start, status 'Solved' only"
)


class RepairUnavailable(RuntimeError):
    """REPAIR_CERTIFICATE_UNAVAILABLE.

    A certificate-METHOD stop. It is NOT a Stage-3 solver invalidation, NOT evidence of economic
    infeasibility, NOT permission to use the old proposal, and NOT permission to introduce a
    multi-coordinate repair.

    Reason codes: TIGHTENED_BOX_EMPTY, TIGHTENED_PROPOSAL_NOT_OBTAINED,
                  TIGHTENED_PROPOSAL_INFEASIBLE, NO_EXACT_ABSORBER_CANDIDATE.
    """


@dataclass(frozen=True)
class RepairCertificate:
    zhat: tuple                   # the EXACTLY feasible rational point
    absorber: int                 # k*, the winning coordinate (a label; selection is by identity)
    n_candidates: int
    n_feasible_candidates: int
    delta_upper: float            # >= ||z_s - zhat_s||
    f_zhat_upper: float           # >= f(zhat_s)
    ghat_upper: float             # >= f(zhat_s) - d_s  >= 0
    radius_upper: float           # R_s = delta_U + upper(sqrt(2*Ghat_U/m))
    objective_bound_upper: float  # U_s = upper|f(z_s) - f(zhat_s)| + Ghat_U
    empty_rows: tuple = field(default=())   # (row index, exact rhs as a string) — recorded
    profile: str = PROPOSAL_PROFILE


# ======================================================================================
# Structural preconditions
# ======================================================================================
def assert_structure(A_eq, b_eq) -> None:
    """meq == 1, asserted rather than assumed."""
    A_eq = np.asarray(A_eq, dtype=np.float64)
    if A_eq.shape[0] != 1:
        raise CertificateDefect(
            f"exact-rational repair is authorized for meq == 1 only; this model has "
            f"{A_eq.shape[0]} equality rows. It must NOT silently generalize — stop."
        )
    if not (np.all(np.isfinite(A_eq[0])) and np.all(np.isfinite(np.asarray(b_eq, float)))):
        raise CertificateDefect("equality row is not finite")
    if not np.any(A_eq[0] != 0.0):
        raise CertificateDefect("equality row has no nonzero coefficient — no absorber exists")


def empty_rows_of(A_ub, b_ub):
    """§4 — a structurally empty row: every coefficient EXACTLY zero.

    Detected on the exact values, so the classification is invariant under row and variable
    shuffling. `0 <= b_j` is required exactly; `b_j < 0` on a zero row is an INVALID ORIGINAL
    MODEL, not a repair failure, and is raised as such.
    """
    A_ub = np.asarray(A_ub, dtype=np.float64)
    b = np.asarray(b_ub, dtype=np.float64).ravel()
    empties = []
    for r in range(A_ub.shape[0]):
        if np.all(A_ub[r] == 0.0):
            rhs = to_fraction(b[r])
            if rhs < 0:
                raise CertificateDefect(
                    f"INVALID ORIGINAL MODEL: inequality row {r} is structurally empty with "
                    f"b = {float(rhs)!r} < 0, i.e. 0 <= b is false. Unsatisfiable as written."
                )
            empties.append((r, str(rhs)))
    return tuple(empties)


def assert_tightened_box_nonempty(upper) -> None:
    """§5 — u_i > 2*eta for every variable, or the tightened box is empty.

    Do NOT reduce eta and do NOT revert to the untightened proposal.
    """
    U = [to_fraction(v) for v in np.asarray(upper, dtype=np.float64).ravel()]
    bad = [(i, str(u)) for i, u in enumerate(U) if not (u > 2 * ETA)]
    if bad:
        raise RepairUnavailable(
            f"TIGHTENED_BOX_EMPTY: {len(bad)} variable(s) have u_i <= 2*eta "
            f"(first: index {bad[0][0]}, u = {bad[0][1]}). eta is frozen; the box cannot be "
            f"opened by shrinking it."
        )


# ======================================================================================
# §8 — canonical variable identity: survives ROW and VARIABLE shuffling
# ======================================================================================
def canonical_key(k, t, upper, A_eq, A_ub, b_ub):
    """A variable's identity in terms of the MODEL, never its current column index.

    Row order is quotiented out by sorting the (coefficient, rhs) pairs of the inequality rows the
    variable appears in, so the key survives a row shuffle as well as a variable shuffle. Two
    variables sharing a key are genuinely interchangeable, so ordering by it resolves an exact tie
    deterministically.
    """
    rows = sorted(
        (to_fraction(A_ub[r, k]), to_fraction(b_ub[r]))
        for r in range(np.asarray(A_ub).shape[0])
        if A_ub[r, k] != 0.0
    )
    return (to_fraction(A_eq[0, k]), to_fraction(t[k]), to_fraction(upper[k]), tuple(rows))


# ======================================================================================
# §§3-7 — the R2 tightened proposal (NON-EVIDENTIARY)
# ======================================================================================
def build_tightened_problem(A_ub, b_ub, A_eq, b_eq, upper):
    """The tightened proposal in CLARABEL form: min 1/2 w'Pw + q'w  s.t.  A w + s = b, s in K.

        P = I,  q = -z_s (supplied by the caller — the constant 1/2 z_s'z_s is omitted, as it
                          does not move the minimizer and the proposal solver does not need it)

        A = [ A_eq   ]   b = [ b_eq        ]   cones = [ Zero(meq),
            [ A_ub_nz]       [ b_ub_nz - e ]             Nonneg(m_nz + 2n) ]
            [ -I     ]       [ -e          ]
            [  I     ]       [ u - e       ]

    Row orientation is the SAME as the validated Clarabel Stage-3 path; only the right-hand side is
    tightened. Exposed so a fixture can prove that every NONZERO inequality row receives exactly
    the frozen eta, that structurally empty rows receive NONE, and that the equality is unchanged.
    """
    A_ub = np.asarray(A_ub, dtype=np.float64)
    A_eq = np.asarray(A_eq, dtype=np.float64)
    b_ub = np.asarray(b_ub, dtype=np.float64).ravel()
    b_eq = np.asarray(b_eq, dtype=np.float64).ravel()
    u = np.asarray(upper, dtype=np.float64).ravel()
    n = A_eq.shape[1]

    keep = [r for r in range(A_ub.shape[0]) if np.any(A_ub[r] != 0.0)]   # empty rows: NOT tightened
    A_nz = A_ub[keep] if keep else np.zeros((0, n))
    b_nz = b_ub[keep] if keep else np.zeros(0)

    A = np.vstack([A_eq, A_nz, -np.eye(n), np.eye(n)])
    b = np.concatenate([
        b_eq,                          # A_eq w = b_eq            (UNCHANGED)
        b_nz - ETA_FLOAT,              # A_ub w <= b_ub - eta
        np.full(n, -ETA_FLOAT),        # -w <= -eta   i.e.  w >= eta
        u - ETA_FLOAT,                 # w <= u - eta
    ])
    return A, b, keep


def _settings(clarabel):
    """The frozen C1 settings, with every value READ BACK and verified.

    Field names and regularization values come from the validated Clarabel path (including the
    owner-approved `static_regularization_constant` amendment) and are NOT re-derived. Only the
    tolerances differ, and they are derived from eta.
    """
    s = clarabel.DefaultSettings()
    want = {
        "max_threads": 1,
        "max_iter": PROPOSAL_MAX_ITER,
        "time_limit": PROPOSAL_TIME_LIMIT,
        "verbose": False,
        "tol_gap_abs": PROPOSAL_TOL,
        "tol_gap_rel": PROPOSAL_TOL,
        "tol_feas": PROPOSAL_TOL,
        "tol_infeas_abs": PROPOSAL_TOL,
        "tol_infeas_rel": PROPOSAL_TOL,
        "equilibrate_enable": True,
        "presolve_enable": False,
        "direct_kkt_solver": True,
        "direct_solve_method": "qdldl",
        "static_regularization_enable": True,
        "static_regularization_constant": CLARABEL_STATIC_REG,
        "static_regularization_proportional": CLARABEL_PROPORTIONAL,
        "dynamic_regularization_enable": True,
        "dynamic_regularization_eps": CLARABEL_DYNAMIC_EPS,
        "dynamic_regularization_delta": CLARABEL_DYNAMIC_DELTA,
        "iterative_refinement_enable": True,
    }
    for k, v in want.items():
        try:
            setattr(s, k, v)
        except Exception as e:  # noqa: BLE001 — an UNSUPPORTED setting is an adjudication stop,
            raise CertificateDefect(  # ................. not a quiet substitution
                f"Clarabel rejected setting {k}={v!r} ({type(e).__name__}). The tolerance is "
                f"derived from eta and may not be silently substituted. STOP."
            ) from e
    return s, want


def _verify_readback(s, want):
    """A setting that does not read back is a setting that was not applied."""
    for k, v in want.items():
        got = getattr(s, k, None)
        ok = (got == v) if isinstance(v, (bool, str)) else (
            got is not None and float(got) == float(v))
        if not ok:
            raise RepairUnavailable(
                f"TIGHTENED_PROPOSAL_NOT_OBTAINED: settings read-back mismatch on {k}: "
                f"set {v!r}, read {got!r}"
            )


def canonical_order(z_s, A_ub, b_ub, A_eq, b_eq, upper):
    """The permutation that puts the proposal problem into a MODEL-DEFINED order.

    ⚠ WHY THIS EXISTS. Clarabel is an interior-point method and is NOT bitwise
    permutation-equivariant: equilibration and the KKT factorization depend on the order in which
    variables and rows are presented, so the same problem submitted under two different layouts
    returns primals that differ in the last bits. quadprog happened to be invariant; Clarabel is
    not. Because the exact repair is DERIVED from the proposal, the certificate would inherit that
    ordering dependence — and shuffle-invariance is a binding obligation, not a nicety.

    So the problem is submitted in an order defined by the MODEL and the solver point, never by the
    incoming matrix layout, and the result is mapped back. Invariance then holds by construction,
    with no change to the solver, its settings, eta, or the exact certificate.

    The variable key includes z_s: the proposal's objective is `-z_s`, so two variables that are
    identical in the model but carry different z_s are NOT interchangeable, and a key that ignored
    z_s would not define a unique order.
    """
    A_ub = np.asarray(A_ub, dtype=np.float64)
    A_eq = np.asarray(A_eq, dtype=np.float64)
    b_ub = np.asarray(b_ub, dtype=np.float64).ravel()
    n = A_eq.shape[1]

    def var_key(i):
        rows = sorted(
            (to_fraction(A_ub[r, i]), to_fraction(b_ub[r]))
            for r in range(A_ub.shape[0]) if A_ub[r, i] != 0.0
        )
        return (to_fraction(A_eq[0, i]), to_fraction(upper[i]), to_fraction(z_s[i]), tuple(rows))

    p = sorted(range(n), key=var_key)                       # variables -> canonical order

    keep = [r for r in range(A_ub.shape[0]) if np.any(A_ub[r] != 0.0)]
    # Rows keyed by their coefficients EXPRESSED IN CANONICAL VARIABLE ORDER, so the row order is
    # invariant under a variable shuffle as well as a row shuffle.
    q = sorted(keep, key=lambda r: (tuple(to_fraction(A_ub[r, i]) for i in p),
                                    to_fraction(b_ub[r])))
    return p, q


def propose_r2(z_s, A_ub, b_ub, A_eq, b_eq, upper):
    """The ONE frozen deterministic proposal path: Clarabel, status `Solved`, primal only.

    No fallback of any kind. Not quadprog, not HiGHS, not PIQP, not clipping, not another settings
    profile, not a different eta, not the untightened problem.

    ONLY the primal vector w is consumed. Clarabel's duals, reported objective, residuals, internal
    scaling and internal certificate carry NO evidentiary authority here — original-set feasibility
    is established solely by exact rational verification downstream.

    Submitted in canonical order (see `canonical_order`) and mapped back, so the proposal — and
    therefore the exact repair derived from it — is shuffle-invariant.
    """
    import warnings

    import clarabel
    import scipy.sparse as sp

    A_ub = np.asarray(A_ub, dtype=np.float64)
    A_eq = np.asarray(A_eq, dtype=np.float64)
    b_ub = np.asarray(b_ub, dtype=np.float64).ravel()
    b_eq = np.asarray(b_eq, dtype=np.float64).ravel()
    u = np.asarray(upper, dtype=np.float64).ravel()
    z_s = np.asarray(z_s, dtype=np.float64).ravel()
    n = len(z_s)
    meq = A_eq.shape[0]

    p, rows = canonical_order(z_s, A_ub, b_ub, A_eq, b_eq, u)
    A_can, b_can, _keep = build_tightened_problem(
        A_ub[np.ix_(rows, p)] if rows else np.zeros((0, n)),
        b_ub[rows] if rows else np.zeros(0),
        A_eq[:, p], b_eq, u[p],
    )
    m_nz = len(rows)

    P = sp.csc_matrix(np.eye(n))
    q = -z_s[p]                                      # min 1/2||w - z_s||^2, constant omitted
    cones = [clarabel.ZeroConeT(meq), clarabel.NonnegativeConeT(m_nz + 2 * n)]

    s, want = _settings(clarabel)                    # raises CertificateDefect if unsupported
    _verify_readback(s, want)

    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error")           # a warning is a failure, not a shrug
            sol = clarabel.DefaultSolver(P, q, sp.csc_matrix(A_can), b_can, cones, s).solve()
    except Exception as e:  # noqa: BLE001
        raise RepairUnavailable(
            f"TIGHTENED_PROPOSAL_NOT_OBTAINED: {type(e).__name__}: {str(e)[:90]}"
        ) from e

    status = str(sol.status)
    if status != "Solved":                           # AlmostSolved is NOT accepted
        raise RepairUnavailable(
            f"TIGHTENED_PROPOSAL_NOT_OBTAINED: Clarabel status {status!r} (only 'Solved' is "
            f"accepted; reduced-accuracy results are not)"
        )
    x = np.asarray(sol.x, dtype=np.float64)
    if x.shape != (n,) or not np.all(np.isfinite(x)):
        raise RepairUnavailable("TIGHTENED_PROPOSAL_NOT_OBTAINED: non-finite or misshaped primal")

    w = np.empty(n, dtype=np.float64)                # map back out of canonical order
    w[np.asarray(p)] = x
    return w


# ======================================================================================
# §9 — the exact constructor. UNCHANGED from R1, and the sole feasibility authority.
# ======================================================================================
def exact_repair_from_proposal(w_tilde, z_s, t, A_ub, b_ub, A_eq, b_eq, upper):
    """Clip exactly, enumerate every absorber, verify against the ORIGINAL constraints, select the
    closest exact-feasible candidate.

    ⚠ Verification is against the ORIGINAL, UNTIGHTENED feasible set. The certificate is membership
    in F, not in the tightened proposal's constraints. Nothing here "passes by construction".

    Kept separate from the proposal so the exact-verification REJECTION paths are reachable in
    fixtures — a proposal that is already interior would never exercise them.
    """
    assert_structure(A_eq, b_eq)
    n = len(t)
    A_ub = np.asarray(A_ub, dtype=np.float64)
    A_eq = np.asarray(A_eq, dtype=np.float64)
    empties = empty_rows_of(A_ub, b_ub)               # raises on an invalid original model

    # Exact clip into the ORIGINAL box. Bounds are exact rationals, so the clip is exact.
    U = [to_fraction(v) for v in np.asarray(upper, dtype=np.float64).ravel()]
    x = [min(max(to_fraction(w_tilde[i]), Fraction(0)), U[i]) for i in range(n)]

    a = [to_fraction(v) for v in A_eq[0]]
    beta = to_fraction(np.asarray(b_eq, dtype=np.float64).ravel()[0])
    Aub = [[to_fraction(A_ub[r, i]) for i in range(n)] for r in range(A_ub.shape[0])]
    Bub = [to_fraction(v) for v in np.asarray(b_ub, dtype=np.float64).ravel()]
    Zs = [to_fraction(v) for v in np.asarray(z_s, dtype=np.float64).ravel()]

    candidates = [k for k in range(n) if a[k] != 0]
    feasible = []
    for k in candidates:
        w = list(x)
        # The equality now holds IDENTICALLY, in rational arithmetic — not to 1e-16.
        w[k] = (beta - sum(a[i] * x[i] for i in range(n) if i != k)) / a[k]

        if not (Fraction(0) <= w[k] <= U[k]):         # ORIGINAL bounds
            continue
        ok = True
        for r in range(len(Bub)):
            # Structurally empty rows are evaluated here too: they pass only when 0 <= b_ub.
            if sum(Aub[r][i] * w[i] for i in range(n)) > Bub[r]:
                ok = False
                break
        if not ok:
            continue
        feasible.append((k, w, sum((w[i] - Zs[i]) ** 2 for i in range(n))))   # exact distance^2

    if not feasible:
        raise RepairUnavailable(
            f"NO_EXACT_ABSORBER_CANDIDATE: all {len(candidates)} absorbers failed exact "
            f"verification against the original constraints. This says nothing about the solver, "
            f"the feasible set, or economic feasibility."
        )

    # Exact minimum-distance selection; ties broken by CANONICAL VARIABLE IDENTITY, which survives
    # row and variable shuffles — never by matrix index, never by a float.
    best = min(feasible, key=lambda c: (c[2], canonical_key(c[0], t, upper, A_eq, A_ub, b_ub)))
    return tuple(best[1]), best[0], len(candidates), len(feasible), empties


def repair(z_s, t, A_ub, b_ub, A_eq, b_eq, upper):
    """Production entry point: R2 tightened proposal, then the exact certificate."""
    assert_structure(A_eq, b_eq)
    empty_rows_of(A_ub, b_ub)                        # invalid-model check runs FIRST
    assert_tightened_box_nonempty(upper)
    w_tilde = propose_r2(z_s, A_ub, b_ub, A_eq, b_eq, upper)
    return exact_repair_from_proposal(w_tilde, z_s, t, A_ub, b_ub, A_eq, b_eq, upper)


# ======================================================================================
# §§10-13 — repaired gap, radius, agreement
# ======================================================================================
def certify_repair(z_s, cert, t, A_ub, b_ub, A_eq, b_eq, upper) -> RepairCertificate:
    """Exact feasibility -> nonnegative repaired gap -> agreement radius.

    `cert` is the SignedGapCertificate for z_s; only its rigorous dual LOWER bound is used.
    """
    zhat, k, n_cand, n_feas, empties = repair(z_s, t, A_ub, b_ub, A_eq, b_eq, upper)
    n = len(t)
    T = [to_fraction(v) for v in np.asarray(t, dtype=np.float64).ravel()]
    Zs = [to_fraction(v) for v in np.asarray(z_s, dtype=np.float64).ravel()]

    # The ORIGINAL registered economic objective, exactly. Never a transformed solver objective.
    f_zhat = sum((zhat[i] - T[i]) ** 2 / T[i] for i in range(n))
    f_zhat_iv = rational_iv(f_zhat)

    # Exact feasibility + weak duality => nonnegative. A negative value is fatal.
    ghat_iv = f_zhat_iv - iv.mpf(cert.dual_lower)
    ghat_u = f_up(ghat_iv)                            # OUTWARD: a rounded-down bound is no bound
    if not np.isfinite(ghat_u):
        raise CertificateDefect("non-finite repaired gap")
    if ghat_u < 0.0:
        raise CertificateDefect(
            f"repaired gap {ghat_u:.6e} is negative at an EXACTLY feasible point. Weak duality "
            f"forbids this — a certificate or interval-direction defect. INVALID_RUN."
        )

    d2 = sum((zhat[i] - Zs[i]) ** 2 for i in range(n))                # exact rational
    delta_u = f_up(iv.sqrt(rational_iv(d2)))
    m_iv = iv.mpf(2) / iv.mpf(float(np.max(np.asarray(t, dtype=np.float64))))
    radius_u = delta_u + f_up(iv.sqrt(iv.mpf(2) * ghat_iv / m_iv))

    f_zs_iv = iv.mpf([cert.primal_lower, cert.primal_upper])
    b_u = f_up(abs(f_zs_iv - f_zhat_iv))
    return RepairCertificate(
        zhat=zhat, absorber=k, n_candidates=n_cand, n_feasible_candidates=n_feas,
        delta_upper=delta_u, f_zhat_upper=float(f_zhat_iv.b), ghat_upper=ghat_u,
        radius_upper=radius_u, objective_bound_upper=b_u + ghat_u, empty_rows=empties,
    )


def agreement(r1: RepairCertificate, r2: RepairCertificate, z1, z2):
    """||z1 - z2|| <= R1 + R2 + 1e-10, with the left side ALSO taken at an upper endpoint."""
    d1 = [to_fraction(v) for v in np.asarray(z1, dtype=np.float64).ravel()]
    d2 = [to_fraction(v) for v in np.asarray(z2, dtype=np.float64).ravel()]
    dz = f_up(iv.sqrt(rational_iv(sum((d1[i] - d2[i]) ** 2 for i in range(len(d1))))))
    bound = r1.radius_upper + r2.radius_upper + AGREEMENT_SLACK
    return (dz <= bound), dz, bound


def objective_agreement(r1: RepairCertificate, r2: RepairCertificate, c1, c2):
    """|f(z1) - f(z2)| <= U1 + U2 + 1e-12, from complete interval enclosures."""
    f1 = iv.mpf([c1.primal_lower, c1.primal_upper])
    f2 = iv.mpf([c2.primal_lower, c2.primal_upper])
    df = f_up(abs(f1 - f2))
    bound = r1.objective_bound_upper + r2.objective_bound_upper + OBJECTIVE_SLACK
    return (df <= bound), df, bound


def manifest() -> dict:
    """§4 — eta, the Clarabel settings and the proposal-path identity, for the evidence record."""
    import hashlib
    import inspect
    import platform
    import sys
    import sysconfig
    from importlib.metadata import version

    try:
        clarabel_version = version("clarabel")
    except Exception:  # noqa: BLE001
        clarabel_version = None

    src = hashlib.sha256()
    for fn in (build_tightened_problem, _settings, _verify_readback, propose_r2,
               exact_repair_from_proposal, repair, certify_repair):
        src.update(inspect.getsource(fn).encode())

    return {
        "profile": PROPOSAL_PROFILE,
        "eta_exact_rational": f"{ETA.numerator}/{ETA.denominator}",
        "eta_ieee754": ETA_FLOAT,
        "eta_ieee754_hex": ETA_HEX,
        "proposal_solver": PROPOSAL_SOLVER,
        "clarabel_version": clarabel_version,
        "clarabel_settings": {
            "max_threads": 1, "max_iter": PROPOSAL_MAX_ITER, "time_limit": PROPOSAL_TIME_LIMIT,
            "verbose": False,
            "tol_gap_abs": PROPOSAL_TOL, "tol_gap_rel": PROPOSAL_TOL, "tol_feas": PROPOSAL_TOL,
            "tol_infeas_abs": PROPOSAL_TOL, "tol_infeas_rel": PROPOSAL_TOL,
            "equilibrate_enable": True, "presolve_enable": False,
            "direct_kkt_solver": True, "direct_solve_method": "qdldl",
            "static_regularization_enable": True,
            "static_regularization_constant": CLARABEL_STATIC_REG,
            "static_regularization_proportional": CLARABEL_PROPORTIONAL,
            "dynamic_regularization_enable": True,
            "dynamic_regularization_eps": CLARABEL_DYNAMIC_EPS,
            "dynamic_regularization_delta": CLARABEL_DYNAMIC_DELTA,
            "iterative_refinement_enable": True,
        },
        "proposal_tol_derivation": "eps = eta / 100 = 1e-14 — derived from eta, never fitted",
        "objective": "P = I, q = -z_s (constant 1/2 z_s'z_s omitted; it does not move the minimizer)",
        "accepted_status": ["Solved"],
        "rejected_statuses": ["AlmostSolved", "MaxIterations", "InsufficientProgress",
                              "PrimalInfeasible", "DualInfeasible", "*any other*"],
        "fresh_instance_per_proposal": True,
        "warm_start": False,
        "cross_instance_state": False,
        "quadprog_proposal_path": "RETIRED — unreachable",
        "untightened_fallback_reachable": False,
        "proposal_output_consumed": "primal vector x ONLY (duals, objective, residuals discarded)",
        "python_abi": sysconfig.get_config_var("SOABI"),
        "python_version": sys.version.split()[0],
        "platform_machine": platform.machine(),
        "repair_module_source_sha256": src.hexdigest(),
        "feasibility_authority": (
            "exact rational verification against the ORIGINAL untightened constraints; the "
            "tightened proposal is non-evidentiary and proves nothing by itself"
        ),
    }
