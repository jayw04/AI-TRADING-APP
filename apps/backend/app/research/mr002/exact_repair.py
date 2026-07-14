"""MR-002 Stage-3 — EXACT MINIMUM-L-INFINITY REPAIR CERTIFICATE.

Supersedes the R1/R2/R2-C1 family, which is RETIRED. Those all required a floating-point solver to
return a point whose interior margin EXCEEDED its own numerical feasibility error. On the measured
geometry — an accepted Stage-3 point sitting on a degenerate vertex against many simultaneously
active rows — that condition was not attainable:

    quadprog  false `constraints are inconsistent` at eta = 1e-12        (LP oracle: feasible)
    Clarabel  converges only for eta <= 1e-11, where its OWN inequality residual (2.9e-12) exceeds
              eta, so the tightening buys nothing; false `PrimalInfeasible` at eta >= 1e-10
                                                                          (LP oracle: feasible)

THE REPLACEMENT removes the premise rather than tuning it. No interior point. No eta. No absorber
coordinate. Instead, the smallest L-infinity correction that lands EXACTLY in the original set:

    min  rho
    s.t. A_eq w  = b_eq
         A_ub w <= b_ub
         0 <= w <= u
         -rho <= w_i - z_s,i <= rho,   rho >= 0

It adjusts as many coordinates as it must, corrects the equality, the violated rows and the bounds
JOINTLY, and keeps every coordinate correction bounded by the smallest achievable rho. Because the
Stage-3 point is only ~1e-17..1e-12 outside the set, rho* is that small too — so the repair stays
close and the agreement radius stays tight and informative.

WHERE THE AUTHORITY LIVES
-------------------------
HiGHS proposes a BASIS. That is all. Its floating-point primal, duals and objective carry NO
evidentiary weight. From the basis we reconstruct, in exact rational arithmetic:

    x_B = B^-1 h        primal      -> exact feasibility + exact nonnegativity
    y   = B^-T c_B      dual        -> exact DUAL FEASIBILITY (M'y <= c)

Exact primal/dual objective equality follows ALGEBRAICALLY from those two solves
(c'x = c_B'B^-1 h = h'y), so it is a reconstruction CONSISTENCY check and proves nothing about
optimality. **The load-bearing optimality certificate is dual feasibility / reduced-cost signs.**
A feasible-but-suboptimal basis satisfies the identity and fails the reduced-cost test; the fixture
suite contains exactly that case.

ROW-VARIABLE SEMANTICS. HiGHS's basis is over [M, -I]: structural columns AND row (logical)
variables. A basic row variable contributes the column -e_r to B, and a NONBASIC row variable sits
at its bound h_r. Inferring a pure structural-column basis would be wrong, and would silently
produce a different linear system.
"""

from __future__ import annotations

import hashlib
import time
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
from app.research.mr002.exact_simplex import (
    SimplexUnavailable,
    ceilings,
    solve_lp,
)

RepairUnavailable = SimplexUnavailable          # one reason-code family

AGREEMENT_SLACK = 1e-10
OBJECTIVE_SLACK = 1e-12

REPAIR_METHOD = "EXACT_MIN_LINF_REPAIR_LP"
BASIS_ORACLE = "RETIRED — the exact rational simplex IS the repair optimizer"

# The frozen basis-oracle profile. One profile, one oracle. There is no second basis oracle.
HIGHS_OPTIONS = (
    ("output_flag", False),
    ("log_to_console", False),
    ("solver", "simplex"),
    ("simplex_strategy", 1),          # dual simplex, frozen
    ("presolve", "off"),
    ("parallel", "off"),
    ("threads", 1),
    ("random_seed", 0),
    ("time_limit", 60.0),
    # ⚠ NOT `small_matrix_value`. That option makes HiGHS DROP matrix entries below the threshold,
    # so it would silently solve a DIFFERENT matrix than the exact rational M the certificate is
    # built on — and a basis optimal for a different matrix cannot reconstruct exactly. It was
    # copied here from the validated QP profile, where it was harmless; here it is a defect.
    # ⚠ HiGHS's DEFAULT primal feasibility tolerance is 1e-7. At that setting it returns bases
    # whose EXACT basic solution violates the equalities by ~1e-8 and carries negative structural
    # variables — measured on the corpus, not supposed. Such a basis is not exactly feasible and
    # cannot be certified, however small the float residual looks. The oracle must be asked for a
    # basis that is feasible at a scale the exact reconstruction can actually stand on.
    ("primal_feasibility_tolerance", 1e-10),
    ("dual_feasibility_tolerance", 1e-10),
)


@dataclass(frozen=True)
class ExactRepair:
    zhat: tuple                   # the EXACTLY feasible rational repaired point
    rho_star: Fraction            # the exact minimum L-infinity repair envelope
    n_coords_changed: int
    delta_upper: float            # >= ||z_s - zhat||_2, outward-rounded
    f_zhat_upper: float
    ghat_upper: float             # >= f(zhat) - d_s  >= 0
    radius_upper: float           # R = delta_U + upper(sqrt(2*Ghat_U/m))
    objective_bound_upper: float
    basis_dim: int
    singletons_eliminated: int
    core_dim: int
    max_num_bits: int
    max_den_bits: int
    solve_seconds: float
    pivots_phase_i: int = 0
    pivots_phase_ii: int = 0
    certificate_seconds: float = 0.0
    core_seconds: float = 0.0
    empty_rows: tuple = field(default=())
    method: str = REPAIR_METHOD


# ======================================================================================
# Structural preconditions and canonical identities
# ======================================================================================
def empty_rows_of(A_ub, b_ub):
    """A structurally empty row: every coefficient EXACTLY zero. It is validated exactly and
    OMITTED from the repair LP; `0 <= b_j` is required. `b_j < 0` is an INVALID ORIGINAL MODEL —
    a broken model, not a repair failure, and it must not be laundered into an unavailable
    certificate."""
    A_ub = np.asarray(A_ub, dtype=np.float64)
    b = np.asarray(b_ub, dtype=np.float64).ravel()
    out = []
    for r in range(A_ub.shape[0]):
        if np.all(A_ub[r] == 0.0):
            rhs = to_fraction(b[r])
            if rhs < 0:
                raise CertificateDefect(
                    f"INVALID ORIGINAL MODEL: inequality row {r} is structurally empty with "
                    f"b = {float(rhs)!r} < 0. `0 <= b` is false; the model is unsatisfiable."
                )
            out.append((r, str(rhs)))
    return tuple(out)


def canonical_order(z_s, A_ub, b_ub, A_eq, b_eq, upper):
    """Model-defined identities for variables and rows. Incoming positions are NOT identities.

    z_s is part of the variable key because it appears in the repair objective's proximity rows:
    two variables identical in the model but carrying different z_s are NOT interchangeable, and a
    key that ignored z_s would fail to define a unique order.

    ⚠ EVERY equality row is in the key. An earlier version read only `A_eq[0, i]`, which made the
    "canonical" order LAYOUT-defined the moment a model carried a second equality: two variables
    identical in row 0, in `upper`, in `z_s` and in the inequality rows but differing in row 1 would
    tie, and the tie would then be broken by Python's stable sort on the INCOMING POSITION. Relabel
    the variables and the order changes — so canonical shuffle invariance held only because `meq = 1`
    on every instance in the corpus, not because the key was canonical. That is an accident, not a
    property, and it is exactly the kind of unstated assumption that survives until the model grows
    a second constraint. `meq = 1` remains true; the key no longer depends on it.
    """
    A_ub = np.asarray(A_ub, dtype=np.float64)
    A_eq = np.asarray(A_eq, dtype=np.float64)
    b_ub = np.asarray(b_ub, dtype=np.float64).ravel()
    n = A_eq.shape[1]
    meq = A_eq.shape[0]

    def var_key(i):
        rows = sorted(
            (to_fraction(A_ub[r, i]), to_fraction(b_ub[r]))
            for r in range(A_ub.shape[0]) if A_ub[r, i] != 0.0
        )
        eq = tuple(to_fraction(A_eq[e, i]) for e in range(meq))
        return (eq, to_fraction(upper[i]), to_fraction(z_s[i]), tuple(rows))

    p = sorted(range(n), key=var_key)
    keep = [r for r in range(A_ub.shape[0]) if np.any(A_ub[r] != 0.0)]
    rows = sorted(keep, key=lambda r: (tuple(to_fraction(A_ub[r, i]) for i in p),
                                       to_fraction(b_ub[r])))
    return p, rows


# ======================================================================================
# The canonical exact standard form:  min c'x  s.t.  Mx = h,  x >= 0
#
#   x = [ w(n) | s(m) | v(n) | p(n) | q(n) | rho(1) ]
#
#   R1  A_eq w                        = b_eq       (meq rows)
#   R2  A_ub w + s                    = b_ub       (m rows, structurally-empty rows omitted)
#   R3  w + v                         = u          (n rows)   -> w <= u
#   R4  w - rho*1 + p                 = z_s        (n rows)   -> w_i - z_i <= rho
#   R5  -w - rho*1 + q                = -z_s       (n rows)   -> z_i - w_i <= rho
#
#   c = e_rho                                                  -> min rho
# ======================================================================================
def build_standard_form(z_s, A_ub, b_ub, A_eq, b_eq, upper):
    """(M, h, c, n, m) as EXACT rationals, in canonical order. Nothing here is approximate."""
    A_ub = np.asarray(A_ub, dtype=np.float64)
    A_eq = np.asarray(A_eq, dtype=np.float64)
    b_ub = np.asarray(b_ub, dtype=np.float64).ravel()
    b_eq = np.asarray(b_eq, dtype=np.float64).ravel()
    z_s = np.asarray(z_s, dtype=np.float64).ravel()
    upper = np.asarray(upper, dtype=np.float64).ravel()

    empty_rows_of(A_ub, b_ub)                       # raises on an invalid original model
    p, rows = canonical_order(z_s, A_ub, b_ub, A_eq, b_eq, upper)
    n, m, meq = len(p), len(rows), A_eq.shape[0]

    Aeq = [[to_fraction(A_eq[e, i]) for i in p] for e in range(meq)]
    Beq = [to_fraction(v) for v in b_eq]
    Aub = [[to_fraction(A_ub[r, i]) for i in p] for r in rows]
    Bub = [to_fraction(b_ub[r]) for r in rows]
    U = [to_fraction(upper[i]) for i in p]
    Z = [to_fraction(z_s[i]) for i in p]

    N = 4 * n + m + 1                                # w, s, v, p, q, rho
    W, S, V, P, Q, RHO = 0, n, n + m, 2 * n + m, 3 * n + m, 4 * n + m
    M_rows, h = [], []
    zero = Fraction(0)
    one, neg = Fraction(1), Fraction(-1)

    for e in range(meq):                             # R1
        row = [zero] * N
        for i in range(n):
            row[W + i] = Aeq[e][i]
        M_rows.append(row)
        h.append(Beq[e])
    for r in range(m):                               # R2
        row = [zero] * N
        for i in range(n):
            row[W + i] = Aub[r][i]
        row[S + r] = one
        M_rows.append(row)
        h.append(Bub[r])
    for i in range(n):                               # R3
        row = [zero] * N
        row[W + i], row[V + i] = one, one
        M_rows.append(row)
        h.append(U[i])
    for i in range(n):                               # R4
        row = [zero] * N
        row[W + i], row[P + i], row[RHO] = one, one, neg
        M_rows.append(row)
        h.append(Z[i])
    for i in range(n):                               # R5
        row = [zero] * N
        row[W + i], row[Q + i], row[RHO] = neg, one, neg
        M_rows.append(row)
        h.append(-Z[i])

    c = [zero] * N
    c[RHO] = one
    return M_rows, h, c, n, m, p, rows


def lp_content_hash(M, h, c) -> str:
    """The canonical LP's identity. Two presentations of the same model MUST hash identically —
    that is what makes shuffle-invariance a property of the submitted problem rather than a hope
    about the solver."""
    d = hashlib.sha256()
    d.update(b"MR002|exact-min-linf-repair-lp|v1")
    for row in M:
        d.update(b"|r|")
        for v in row:
            d.update(f"{v.numerator}/{v.denominator};".encode())
    for v in h:
        d.update(f"|h|{v.numerator}/{v.denominator}".encode())
    for v in c:
        d.update(f"|c|{v.numerator}/{v.denominator}".encode())
    return d.hexdigest()


# ======================================================================================
# The certificate. The exact simplex IS the optimizer; HiGHS is retired from this path.
# ======================================================================================
def exact_repair(z_s, A_ub, b_ub, A_eq, b_eq, upper, trace=None):
    """The exactly certified minimum-L-infinity repair. Raises on any failure.

    `trace`, when a dict is supplied, is filled with the full equivalence record (pivot sequences,
    per-pivot basis hashes, every exact output). Recording only — it changes no decision.
    """
    t0 = time.perf_counter()
    empties = empty_rows_of(A_ub, b_ub)
    M, h, c, n, m, perm, _rows = build_standard_form(z_s, A_ub, b_ub, A_eq, b_eq, upper)

    res = solve_lp(M, h, c, trace)   # exact Phase I + Phase II; certificates verified inside

    rho = res.objective
    zhat = [Fraction(0)] * n
    for k, i in enumerate(perm):     # back to ORIGINAL variable order
        zhat[i] = res.x[k]

    # Independent verification against the ORIGINAL Stage-3 constraints — not the standard form.
    # ⚠ EVERY equality row, not just row 0. The standard form does encode them all, so a point that
    # passes `Mx = h` inside solve_lp already satisfies them; but the whole purpose of this block is
    # to re-derive feasibility from the ORIGINAL float arrays rather than trust the form we built.
    # Checking only row 0 left that independent check blind to any further equality.
    A_ubf = np.asarray(A_ub, dtype=np.float64)
    A_eqf = np.asarray(A_eq, dtype=np.float64)
    B_eqf = np.asarray(b_eq, dtype=np.float64).ravel()
    Z = [to_fraction(v) for v in np.asarray(z_s, dtype=np.float64).ravel()]
    U = [to_fraction(v) for v in np.asarray(upper, dtype=np.float64).ravel()]
    for e in range(A_eqf.shape[0]):
        if sum(to_fraction(A_eqf[e, i]) * zhat[i] for i in range(n)) != to_fraction(B_eqf[e]):
            raise SimplexUnavailable(f"EXACT_REPAIR_ORIGINAL_EQUALITY_FAILED row {e}")
    for r in range(A_ubf.shape[0]):
        lhs = sum(to_fraction(A_ubf[r, i]) * zhat[i] for i in range(n))
        if lhs > to_fraction(np.asarray(b_ub, dtype=np.float64).ravel()[r]):
            raise SimplexUnavailable(f"EXACT_REPAIR_ORIGINAL_INEQUALITY_FAILED row {r}")
    for i in range(n):
        if not (Fraction(0) <= zhat[i] <= U[i]):
            raise SimplexUnavailable(f"EXACT_REPAIR_ORIGINAL_BOUND_FAILED coord {i}")
        if abs(zhat[i] - Z[i]) > rho:
            raise SimplexUnavailable(f"EXACT_REPAIR_RHO_ENVELOPE_FAILED coord {i}")

    return {
        "zhat": tuple(zhat), "rho_star": rho, "empties": empties,
        "n_changed": sum(1 for i in range(n) if zhat[i] != Z[i]),
        "result": res,
        "seconds": time.perf_counter() - t0,
    }


def certify_repair(z_s, cert, t, A_ub, b_ub, A_eq, b_eq, upper) -> ExactRepair:
    """Exact repair -> nonnegative repaired gap -> agreement radius.

    `cert` is the SignedGapCertificate for z_s; only its rigorous dual LOWER bound is used.
    """
    r = exact_repair(z_s, A_ub, b_ub, A_eq, b_eq, upper)
    zhat = r["zhat"]
    res = r["result"]
    n = len(t)
    T = [to_fraction(v) for v in np.asarray(t, dtype=np.float64).ravel()]
    Z = [to_fraction(v) for v in np.asarray(z_s, dtype=np.float64).ravel()]

    # The ORIGINAL registered economic objective, exactly. Never a transformed solver objective.
    f_zhat = sum((zhat[i] - T[i]) ** 2 / T[i] for i in range(n))
    f_zhat_iv = rational_iv(f_zhat)

    ghat_iv = f_zhat_iv - iv.mpf(cert.dual_lower)
    ghat_u = f_up(ghat_iv)
    if ghat_u < 0.0:
        raise CertificateDefect(
            f"repaired gap {ghat_u:.6e} is negative at an EXACTLY feasible point. Weak duality "
            f"forbids this — a certificate or interval-direction defect. INVALID_RUN.")

    # `iv.sqrt` below has a DOMAIN, and nothing here had been checking it. An interval that straddles
    # zero raises mpmath's ComplexResult — an uncaught traceback, not a reason code.
    #
    # It cannot straddle, and the reason is worth writing down rather than rediscovering:
    #
    #   * f_zhat_iv is `rational_iv` of an EXACT rational, so its width is ~1e-100 relative;
    #   * cert.dual_lower is a float64, a POINT, whose granularity at these magnitudes is ~1e-16
    #     relative — eighty-odd orders of magnitude coarser than that width.
    #
    # So ghat_iv lands wholly on one side of zero: non-negative (fine), or wholly negative (the guard
    # above rejects it as a weak-duality violation). A straddle would require dual_lower to fall
    # inside a 1e-100-wide window around f(zhat), which no float can do.
    #
    # That argument depends on IV_DPS and on dual_lower being a float. Both are true today; neither is
    # guaranteed forever. So assert the domain instead of assuming it — if the premise ever changes,
    # this stops with a reason code rather than an mpmath traceback. It is NOT a clamp: silently
    # widening the interval to make sqrt succeed would be manufacturing a bound rather than proving
    # one.
    if ghat_iv.a < 0 <= ghat_iv.b:
        raise CertificateDefect(
            f"the repaired-gap enclosure [{float(ghat_iv.a):.3e}, {float(ghat_iv.b):.3e}] straddles "
            f"zero, so sqrt has no real value on it. This is unreachable while f(zhat) is enclosed "
            f"exactly and dual_lower is a float — if it fired, that premise changed. INVALID_RUN.")

    d2 = sum((zhat[i] - Z[i]) ** 2 for i in range(n))       # exact rational
    if d2 > n * r["rho_star"] ** 2:                         # L-inf -> L-2 consistency (diagnostic)
        raise CertificateDefect("delta^2 > n*rho^2 — the L-inf/L-2 relation is violated")
    delta_u = f_up(iv.sqrt(rational_iv(d2)))
    m_iv = iv.mpf(2) / iv.mpf(float(np.max(np.asarray(t, dtype=np.float64))))
    radius_u = delta_u + f_up(iv.sqrt(iv.mpf(2) * ghat_iv / m_iv))

    f_zs_iv = iv.mpf([cert.primal_lower, cert.primal_upper])
    b_u = f_up(abs(f_zs_iv - f_zhat_iv))
    return ExactRepair(
        zhat=zhat, rho_star=r["rho_star"], n_coords_changed=r["n_changed"],
        delta_upper=delta_u, f_zhat_upper=f_up(f_zhat_iv), ghat_upper=ghat_u,
        radius_upper=radius_u, objective_bound_upper=b_u + ghat_u,
        basis_dim=res.full_basis_dim, singletons_eliminated=res.singletons_max,
        core_dim=res.core_dim_max, max_num_bits=res.max_num_bits,
        max_den_bits=res.max_den_bits, solve_seconds=r["seconds"], empty_rows=r["empties"],
        pivots_phase_i=res.pivots_phase_i, pivots_phase_ii=res.pivots_phase_ii,
        certificate_seconds=res.certificate_seconds, core_seconds=res.core_seconds,
    )


def agreement(r1: ExactRepair, r2: ExactRepair, z1, z2):
    """||z1 - z2|| <= R1 + R2 + 1e-10, the left side ALSO at an outward-rounded upper endpoint."""
    d1 = [to_fraction(v) for v in np.asarray(z1, dtype=np.float64).ravel()]
    d2 = [to_fraction(v) for v in np.asarray(z2, dtype=np.float64).ravel()]
    dz = f_up(iv.sqrt(rational_iv(sum((d1[i] - d2[i]) ** 2 for i in range(len(d1))))))
    bound = r1.radius_upper + r2.radius_upper + AGREEMENT_SLACK
    return (dz <= bound), dz, bound


def objective_agreement(r1: ExactRepair, r2: ExactRepair, c1, c2):
    """|f(z1) - f(z2)| <= U1 + U2 + 1e-12, from complete interval enclosures."""
    f1 = iv.mpf([c1.primal_lower, c1.primal_upper])
    f2 = iv.mpf([c2.primal_lower, c2.primal_upper])
    df = f_up(abs(f1 - f2))
    bound = r1.objective_bound_upper + r2.objective_bound_upper + OBJECTIVE_SLACK
    return (df <= bound), df, bound


def manifest() -> dict:
    """The frozen repair/basis-oracle record."""
    import inspect
    import platform
    import sys
    import sysconfig

    src = hashlib.sha256()
    for fn in (build_standard_form, canonical_order, lp_content_hash, exact_repair,
               certify_repair, agreement, objective_agreement):
        src.update(inspect.getsource(fn).encode())
    return {
        "method": REPAIR_METHOD,
        "objective": "min rho  s.t.  original feasible set  AND  |w_i - z_s,i| <= rho",
        "basis_oracle": BASIS_ORACLE,
        "exact_solver": "canonical exact rational Phase-I/Phase-II simplex, Bland's rule",
        "resource_ceilings": ceilings(),
        "floating_point_in_evidentiary_path": False,
        "optimality_authority": (
            "EXACT dual feasibility (M'y <= c, reduced costs >= 0). Exact primal/dual objective "
            "equality follows algebraically from the two basis solves and is a RECONSTRUCTION "
            "CONSISTENCY check only — it cannot detect a feasible-but-suboptimal basis."
        ),
        "feasibility_authority": (
            "EXACT rational verification of Mx = h, x >= 0 against the unreduced system, and of "
            "the ORIGINAL Stage-3 constraints at the mapped-back point."
        ),
        "retired": ["EXACT_REPAIR_PROPOSAL_R1", "EXACT_REPAIR_PROPOSAL_R2",
                    "EXACT_REPAIR_PROPOSAL_R2_CLARABEL_C1", "eta tightening",
                    "one-coordinate absorber", "interior-anchor blend",
                    "HiGHS basis oracle (returned an exactly infeasible rho=0 basis)",
                    "HiGHS warm start (repairing an infeasible basis needs the whole exact "
                    "solver anyway, and would keep a float dependency in the proof path)"],
        "python_abi": sysconfig.get_config_var("SOABI"),
        "python_version": sys.version.split()[0],
        "platform_machine": platform.machine(),
        "repair_module_source_sha256": src.hexdigest(),
    }
