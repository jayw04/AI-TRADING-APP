"""MR-002 Stage-3 — the CANONICAL signed-gap certificate module (owner rulings §2, §3).

THE ONE implementation of:

  * canonical C/b construction              (re-exported from the registered builder)
  * canonical folded multiplier vector
  * dual-sign validation
  * dual-feasible projection
  * certified dual lower bound              (high-precision interval)
  * the CERTIFIED SIGNED LAGRANGIAN GAP     (two-sided, interval containment)
  * the exact-identity integrity check

No characterizer, fixture, wrapper or runtime path may reimplement any of these. That rule is not
decorative: a hand-rolled Clarabel dual mapping produced a false "close v1.1" verdict, and a
KKT-inflated radius was proposed and rejected because a residual norm is not an objective gap.

The AGREEMENT RADIUS is NOT here. It cannot be derived from this gap (see below) and lives in
`app.research.mr002.repair`, built on a certified exactly-feasible repair.

TWO SPECIFICATIONS DIED TO GET HERE
-----------------------------------
1. The SIGNED-gap radius `sqrt(2*max(g,0)/m)`. When g came out negative, `max(.,0)` assigned ZERO
   uncertainty and the radius COLLAPSED to a bare 1e-10 — demanding that an active-set and an
   interior-point method agree below double-precision reproducibility.

2. The NONNEGATIVE certified-gap gate. It disqualified 2,054 of 3,895 square-root solves that pass
   every registered KKT gate, worst value -6.9e-14. The reason is an identity, not a bug:

       Gamma = f(z) - d(lam_bar) = lam_bar'(C'z - b) + 1/2 e' H^-1 e,   e = Hz + q - C lam_bar

   The second term is nonnegative and vanishes at exact stationarity, so Gamma is essentially the
   SIGNED complementarity sum. Requiring it to be >= 0 demands EXACT primal feasibility on active
   constraints, which no double-precision solver delivers, and which the registered system never
   asked for — `primal_residual` already governs feasibility, at a compatible exactness level.

   So Gamma is NOT a "nonnegative certified duality gap" for a point that is not exactly feasible.
   It is a SIGNED primal-dual residual, and the gate is two-sided.

WHAT REMAINS RIGOROUS
---------------------
Registered canonical form (`joint_portfolio._qp_matrices`):

    minimise    f(z) = 1/2 z'Hz + q'z + c      H = diag(2/t), q = -a = -2*1, c = sum(t)
    subject to  C'z >= b                       C = [A_eq; -A_ub; I; -I]',  b = [b_eq; -b_ub; 0; -u]
                the first `meq` rows are equalities; the rest carry lambda >= 0.

    h        = q - C lam_bar
    d(lam)   = c + b'lam_bar - 1/2 h' H^-1 h        H^-1 = diag(t/2), EXACT

For ANY lam_bar with lam_bar[meq:] >= 0, weak duality gives d <= p* REGARDLESS of stationarity.
The dual value is still a rigorous lower bound on the optimum. Only the SIGN of f(z) - d is not
guaranteed, and only because z is not exactly feasible.

ARITHMETIC. Every frozen IEEE-754 input enters through its exact binary rational
(`as_integer_ratio`), never through `str()`. Everything is carried as outward-rounded intervals at
>= 100 decimal digits, and the two-sided gate tests CONTAINMENT OF THE WHOLE INTERVAL — never a
midpoint, a rounded scalar, or one endpoint.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from fractions import Fraction

import numpy as np
from mpmath import iv

from app.research.mr002.directed import to_binary64_dn, to_binary64_up
from app.research.mr002.joint_portfolio import _qp_matrices

# >= 100 decimal digits of working precision.
IV_DPS = 100
iv.dps = IV_DPS

# The binding two-sided gate: the WHOLE interval must sit inside [-1e-10, 1e-10].
SIGNED_GAP_MAX = 1e-10

# Interval widths must be negligible against the gate, or the arithmetic itself is not
# trustworthy and the certificate means nothing.
MAX_INTERVAL_WIDTH = 1e-30


class CertificateDefect(RuntimeError):
    """INVALID_RUN / CERTIFICATE_LAGRANGIAN_IDENTITY_VIOLATION.

    The certificate construction is broken. STOP — do not clamp, do not continue.
    """


@dataclass(frozen=True)
class SignedGapCertificate:
    gamma_lower: float            # f_L - d_U
    gamma_upper: float            # f_U - d_L
    primal_lower: float
    primal_upper: float
    dual_lower: float             # the rigorous lower bound on p*
    dual_upper: float
    lagrangian_slack: float       # lower(lam_bar'(C'z - b))
    stationarity_energy: float    # lower(1/2 e'H^-1 e) >= 0
    primal_interval_width: float
    dual_interval_width: float
    max_multiplier_clip: float
    n_multipliers_clipped: int
    clipped: tuple = field(default=())    # (index, original IEEE-754 hex)
    qualifies: bool = False       # whole interval within +/- 1e-10 AND widths acceptable


# ======================================================================================
# Exact conversion. Never through str() or a shortened decimal.
# ======================================================================================
def exact_iv(x) -> iv.mpf:
    """One IEEE-754 double, through its exact binary rational.

    `as_integer_ratio()` has a power-of-two denominator, so the quotient is exactly representable
    and the interval has ZERO width. Asserted: a nonzero width would mean the conversion silently
    rounded, which is the failure this is here to prevent.
    """
    num, den = float(x).as_integer_ratio()
    v = iv.mpf(num) / iv.mpf(den)
    if v.delta != 0:
        raise CertificateDefect(f"exact conversion of {x!r} rounded — width {v.delta}")
    return v


def rational_iv(fr: Fraction) -> iv.mpf:
    """A general exact rational, as an outward-rounded ENCLOSURE.

    Unlike a double, an arbitrary rational is not binary-representable, so this cannot be
    zero-width — and must not pretend to be. The enclosure is what keeps it rigorous.
    """
    return iv.mpf(int(fr.numerator)) / iv.mpf(int(fr.denominator))


def to_fraction(x) -> Fraction:
    """A frozen double as an exact rational. The only sanctioned entry point."""
    num, den = float(x).as_integer_ratio()
    return Fraction(num, den)


def _vec(a) -> list:
    return [exact_iv(v) for v in np.asarray(a, dtype=np.float64).ravel()]


def _width(x) -> float:
    """The interval's width, rounded UP.

    This is a serialized bound like any other, and it GATES (`fw <= MAX_INTERVAL_WIDTH`). Rounded to
    nearest it could come out below the true width and admit an interval wider than the limit allows
    — the same defect as on the gap endpoints, in a quantity that is easy to overlook because it
    looks like a diagnostic rather than a bound.
    """
    return to_binary64_up(x.delta)


def f_up(x) -> float:
    """An interval's upper endpoint as a double, CORRECTLY ROUNDED toward +infinity.

    Delegated to `app.research.mr002.directed` — the ONE serializer. See that module for why
    `float(x)` (nearest) and `nextafter(float(x), inf)` (rigorous but loose, and it turns an exact
    zero into a spurious subnormal) are both wrong, and what "correctly rounded" costs.
    """
    return to_binary64_up(x)


def f_dn(x) -> float:
    """An interval's lower endpoint as a double, CORRECTLY ROUNDED toward -infinity."""
    return to_binary64_dn(x)


# ======================================================================================
# Canonical construction, sign gate, projection
# ======================================================================================
def canonical_matrices(A_ub, b_ub, A_eq, b_eq, upper, n):
    """THE canonical (C, b). Re-exported so nothing downstream rebuilds it."""
    return _qp_matrices(A_ub, b_ub, A_eq, b_eq, upper, n)


def verify_canonical_hessian(H, t) -> None:
    """The certificate must use the registered economic objective derived from t, never a
    solver-internal transformed Hessian. The sqrt and t-scaled formulations both carry one, and a
    wrapper that forgot to map back would otherwise certify a DIFFERENT problem."""
    expected = np.diag(2.0 / np.asarray(t, dtype=np.float64))
    if not np.array_equal(np.asarray(H, dtype=np.float64), expected):
        raise CertificateDefect(
            "Hessian was not produced by the frozen canonical 2/t construction — the certificate "
            "would be evaluated against a different problem than the registered one"
        )


def dual_sign_violation(lam, meq: int) -> float:
    """Largest magnitude by which an inequality/bound multiplier is negative. The ordinary
    dual-sign gate runs FIRST and stays hard; projection does not repair a multiplier that fails
    it."""
    ineq = np.asarray(lam, dtype=np.float64)[meq:]
    return float(np.max(np.maximum(-ineq, 0.0))) if ineq.size else 0.0


def project_dual(lam, meq: int):
    """Make the multipliers EXACTLY dual-feasible: equalities free, the rest clipped at zero.

    CERTIFICATE CONSTRUCTION ONLY. Everything clipped is RECORDED — index and original IEEE-754
    hex — so a solver quietly leaning on the projection is visible rather than laundered.
    """
    lam = np.asarray(lam, dtype=np.float64).copy()
    idx = [j for j in range(meq, lam.size) if lam[j] < 0.0]
    clipped = tuple((int(j), lam[j].hex()) for j in idx)
    worst = float(max((-lam[j] for j in idx), default=0.0))
    if idx:
        lam[idx] = 0.0
    return lam, worst, clipped


# ======================================================================================
# The signed gap
# ======================================================================================
def gap_intervals(z, lam_bar, t, A_ub, b_ub, A_eq, b_eq, upper):
    """(f, d, S_lag, energy) as outward-rounded intervals. THE folded-convention implementation.

    `lam_bar` must already be dual-feasible. Exposed at full interval precision because the
    equivalence fixture has to compare the folded convention against the expanded A/E/l/u
    derivation far below what a rounded double can express.
    """
    n = len(t)
    C, b = canonical_matrices(A_ub, b_ub, A_eq, b_eq, upper, n)
    C_np = np.asarray(C, dtype=np.float64)
    b_np = np.asarray(b, dtype=np.float64).ravel()
    lam_np = np.asarray(lam_bar, dtype=np.float64).ravel()

    Z, T = _vec(z), _vec(t)
    two = iv.mpf(2)
    quarter = iv.mpf(1) / iv.mpf(4)

    # f(z) = sum(z_i^2/t_i) - 2*sum(z_i) + sum(t_i)      [ = 1/2 z'Hz + q'z + c, q = -2 ]
    c_iv = sum(T, iv.mpf(0))
    f_iv = iv.mpf(0)
    for i in range(n):
        f_iv += (Z[i] * Z[i]) / T[i]
    f_iv -= two * sum(Z, iv.mpf(0))
    f_iv += c_iv

    # h = q - C lam,  b'lam,  and  S_lag = lam'(C'z - b),  all in one sparse sweep.
    #
    # Both skips below are read off the ORIGINAL doubles: a zero multiplier and a zero C entry
    # contribute exactly zero, so dropping them is an identity, not a tolerance. (Never decide
    # this by comparing intervals for equality — interval comparison is not the predicate it looks
    # like. And never densify C: it is (n x 2n+m_ub+meq) with diagonal bound blocks, so converting
    # it entry-by-entry would cost hours across the corpus and buy nothing.)
    h = [-two for _ in range(n)]
    bl = iv.mpf(0)
    slag_iv = iv.mpf(0)
    for j in np.nonzero(lam_np)[0]:
        Lj = exact_iv(lam_np[j])
        Bj = exact_iv(b_np[j])
        bl += Bj * Lj
        col = C_np[:, j]
        cz = iv.mpf(0)
        for i in np.nonzero(col)[0]:
            Cij = exact_iv(col[i])
            h[i] -= Cij * Lj
            cz += Cij * Z[i]
        slag_iv += Lj * (cz - Bj)

    # d = c + b'lam - (1/2) h'H^-1 h,   H^-1 = diag(t/2)  =>  (1/2) h'H^-1 h = (1/4) sum t_i h_i^2
    #
    # This is the line where a slip becomes a FAKE CERTIFICATE, so it is written once, as one
    # expression, and not spread across accumulating statements.
    quad = iv.mpf(0)
    for i in range(n):
        quad += T[i] * h[i] * h[i]
    d_iv = c_iv + bl - quarter * quad

    # e = Hz + q - C lam = Hz + h,  H = diag(2/t)  =>  e_i = (2/t_i) z_i + h_i
    #   1/2 e'H^-1 e = (1/4) sum_i t_i e_i^2      >= 0
    energy_iv = iv.mpf(0)
    for i in range(n):
        e_i = (two * Z[i]) / T[i] + h[i]
        energy_iv += T[i] * e_i * e_i
    energy_iv *= quarter

    return f_iv, d_iv, slag_iv, energy_iv


def certify(z, lam, t, A_ub, b_ub, A_eq, b_eq, upper) -> SignedGapCertificate:
    """The two-sided certified SIGNED Lagrangian gap, from interval endpoints at >= 100 digits."""
    meq = np.asarray(A_eq).shape[0]
    lam_bar, worst_clip, clipped = project_dual(lam, meq)

    f_iv, d_iv, slag_iv, energy_iv = gap_intervals(
        z, lam_bar, t, A_ub, b_ub, A_eq, b_eq, upper)

    fw, dw = _width(f_iv), _width(d_iv)
    if not (np.isfinite(fw) and np.isfinite(dw)):
        raise CertificateDefect("non-finite interval in the certificate")

    gamma_iv = f_iv - d_iv                  # = [f_L - d_U, f_U - d_L], both endpoints

    # ---- INTEGRITY: the exact identity  Gamma == S_lag + 1/2 e'H^-1 e --------------------
    # Evaluated as two INDEPENDENT interval expressions; their difference must contain zero. This
    # is an EQUALITY check and supersedes the weaker one-sided floor: it catches a defect that
    # preserves the inequality while corrupting the magnitude. No empirical tolerance is added —
    # the interval widths are the only slack, and they are separately bounded.
    diff = gamma_iv - (slag_iv + energy_iv)
    if not (diff.a <= 0 <= diff.b):
        raise CertificateDefect(
            f"CERTIFICATE_LAGRANGIAN_IDENTITY_VIOLATION: Gamma - (S_lag + energy) encloses "
            f"[{diff.a}, {diff.b}], which excludes zero. The identity is exact, so this is a "
            f"sign, conversion or formula defect. INVALID_RUN."
        )

    g_lo, g_hi = f_dn(gamma_iv), f_up(gamma_iv)      # OUTWARD, or they stop being bounds
    qualifies = (
        max(abs(g_lo), abs(g_hi)) <= SIGNED_GAP_MAX      # WHOLE interval inside the band
        and fw <= MAX_INTERVAL_WIDTH
        and dw <= MAX_INTERVAL_WIDTH
    )

    return SignedGapCertificate(
        gamma_lower=g_lo,
        gamma_upper=g_hi,
        primal_lower=f_dn(f_iv),
        primal_upper=f_up(f_iv),
        dual_lower=f_dn(d_iv),                       # the rigorous LOWER bound on p*
        dual_upper=f_up(d_iv),
        lagrangian_slack=f_dn(slag_iv),
        stationarity_energy=f_dn(energy_iv),
        primal_interval_width=fw,
        dual_interval_width=dw,
        max_multiplier_clip=worst_clip,
        n_multipliers_clipped=len(clipped),
        clipped=clipped,
        qualifies=qualifies,
    )


def classify(cert: SignedGapCertificate) -> str:
    """The registered disposition string for a signed-gap outcome."""
    if cert.qualifies:
        return "PASS"
    if max(cert.primal_interval_width, cert.dual_interval_width) > MAX_INTERVAL_WIDTH:
        return "INTERVAL_WIDTH_EXCEEDED"
    return "SIGNED_LAGRANGIAN_GAP_LIMIT_EXCEEDED"
