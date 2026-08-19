"""MR-002 Gate N1 — Reference Solver R: exact-rational active-set QP.

Sealed authority: MR002_N1_ProspectiveRegistration_v1.0 §6
identity 7f8a56e34e6d5d36a3914ecb825de015debdc83ebae2967887e5e37ca3d684af.

ROLE. R establishes numerical truth on development and stress instances. R is NEVER a production
generator, NEVER a third voter in the cascade, and NEVER consulted on any validation instance. The
prohibition is enforced by `_assert_development_domain()` at every entry point, not by convention.

METHOD. Exact-rational primal active-set on the registered canonical form

    minimise    f(z) = 1/2 z'Hz + q'z + c      H = diag(2/t), q = -2*1, c = sum(t)
    subject to  C'z >= b                        first meq rows equalities, remainder lambda >= 0

All arithmetic in `fractions.Fraction`. Every frozen IEEE-754 input enters through its exact binary
rational (`as_integer_ratio`), never through `str()` — the convention `certificate.py` and
`repair.py` already establish. There is no tolerance anywhere in R.

WHY AN ACTIVE-SET HINT IS NOT A TRUST RELATIONSHIP. R uses a numerical point only to GUESS which
constraints are active. It then solves the equality-constrained KKT system for that working set
exactly and PROVES optimality from scratch: exact primal feasibility, exact dual feasibility, exact
complementarity, exact stationarity. For a strictly convex QP those four conditions are jointly
sufficient, so a point that satisfies them exactly IS the unique minimiser — regardless of where the
hint came from. A wrong hint cannot produce a false R_EXACT; it can only fail to converge, which is
reported as R_UNAVAILABLE. R is therefore an independent verifier, not a solver that trusts input.

CEILINGS are operational stop limits, NOT mathematical tolerances (§6). They may not be raised after
observing a stopped instance without a new adjudication.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from fractions import Fraction

import numpy as np

# ── frozen resource ceilings (§6) ────────────────────────────────────────────────────────────────
MAX_ACTIVE_SET_ITERATIONS = 200
MAX_RATIONAL_BITS = 200_000

R_EXACT = "R_EXACT"
R_UNAVAILABLE = "R_UNAVAILABLE"


class ReferenceDomainViolation(RuntimeError):
    """R was invoked outside the development/stress domain."""


def _assert_development_domain() -> None:
    """R may never touch a validation instance. Enforced in code, not by convention (§6).

    The environment must not be carrying a validation/OOS context. This is a guard against the
    class of accident that consumes an opening, not a security boundary.
    """
    for var in ("MR002_VALIDATION_CONTEXT", "MR002_OOS_CONTEXT", "MR002_SEALED_CONTEXT"):
        if os.environ.get(var):
            raise ReferenceDomainViolation(
                f"Reference Solver R invoked with {var} set. R is development/stress only and is "
                "never consulted on a validation instance."
            )


def to_fraction(v) -> Fraction:
    """EXACT binary rational of an IEEE-754 double. Never `str()`, never a decimal approximation."""
    num, den = float(v).as_integer_ratio()
    return Fraction(num, den)


def _bits(x: Fraction) -> int:
    return max(x.numerator.bit_length(), x.denominator.bit_length())


@dataclass(frozen=True)
class ReferenceResult:
    status: str
    z: tuple[Fraction, ...] | None = None
    lam: dict[int, Fraction] | None = None
    active_set: tuple[int, ...] = ()
    iterations: int = 0
    detail: str = ""

    @property
    def is_exact(self) -> bool:
        return self.status == R_EXACT

    def z_float(self) -> np.ndarray | None:
        if self.z is None:
            return None
        return np.array([float(v) for v in self.z], dtype=float)


def _solve_exact(mat: list[list[Fraction]], rhs: list[Fraction]) -> list[Fraction] | None:
    """Exact Gaussian elimination with partial pivoting on rationals. None if singular."""
    m = len(mat)
    if m == 0:
        return []
    aug = [row[:] + [rhs[i]] for i, row in enumerate(mat)]
    for col in range(m):
        piv = None
        for r in range(col, m):
            if aug[r][col] != 0:
                piv = r
                break
        if piv is None:
            return None
        aug[col], aug[piv] = aug[piv], aug[col]
        pv = aug[col][col]
        aug[col] = [v / pv for v in aug[col]]
        for r in range(m):
            if r != col and aug[r][col] != 0:
                f = aug[r][col]
                aug[r] = [a - f * bcol for a, bcol in zip(aug[r], aug[col], strict=True)]
        if any(_bits(v) > MAX_RATIONAL_BITS for v in aug[col]):
            raise OverflowError("rational bit ceiling exceeded")
    return [aug[i][m] for i in range(m)]


def _independent_subset(rows: list[list[Fraction]], keep_first: int) -> list[int]:
    """Indices of a maximal linearly independent subset of `rows`, exactly, preferring early rows.

    A degenerate optimum has MORE tight constraints than dimensions, so the working-set KKT matrix
    C_W' H^-1 C_W is singular by construction whenever |W| > n. That is geometry, not a numerical
    problem, and it must not be reported as R_UNAVAILABLE. The dependent rows are redundant AT the
    solution; dropping them changes nothing, and the solution is afterwards verified against ALL of
    them, dropped ones included, so redundancy is proved rather than assumed.

    `keep_first` rows (the equalities) are offered first so they are never the ones dropped.
    """
    if not rows:
        return []
    ncols = len(rows[0])
    order = list(range(keep_first)) + list(range(keep_first, len(rows)))
    basis: list[list[Fraction]] = []
    pivots: list[int] = []
    chosen: list[int] = []
    for idx in order:
        v = rows[idx][:]
        for brow, pc in zip(basis, pivots, strict=True):
            if v[pc] != 0:
                f = v[pc]
                v = [a - f * bb for a, bb in zip(v, brow, strict=True)]
        pc = next((c for c in range(ncols) if v[c] != 0), None)
        if pc is None:
            continue                              # linearly dependent on what we already have
        v = [a / v[pc] for a in v]
        basis.append(v)
        pivots.append(pc)
        chosen.append(idx)
        if len(chosen) == ncols:
            break
    return sorted(chosen)


def solve_reference(rec: tuple, hint_z: np.ndarray | None = None) -> ReferenceResult:
    """Exact minimiser of the registered instance, or R_UNAVAILABLE under a frozen ceiling."""
    _assert_development_domain()

    from app.research.mr002.joint_portfolio import _qp_matrices

    t_np, A_ub, b_ub, A_eq, b_eq, upper = rec
    n = len(t_np)
    meq = A_eq.shape[0]
    C_np, b_np = _qp_matrices(A_ub, b_ub, A_eq, b_eq, upper, n)

    # Exact rational model. C is (n x nrows): row j of the constraint system is C[:, j]' z >= b[j].
    T = [to_fraction(v) for v in np.asarray(t_np, dtype=float).ravel()]
    Hd = [Fraction(2) / ti for ti in T]                       # diag(H)
    a = [Fraction(2)] * n                                     # a = 2*1, so q = -a
    nrows = C_np.shape[1]
    Ccol = [[to_fraction(C_np[i, j]) for i in range(n)] for j in range(nrows)]
    bvec = [to_fraction(v) for v in np.asarray(b_np, dtype=float).ravel()]

    def slack(z: list[Fraction], j: int) -> Fraction:
        col = Ccol[j]
        return sum((col[i] * z[i] for i in range(n)), Fraction(0)) - bvec[j]

    # ── working-set hint ────────────────────────────────────────────────────────────────────────
    # Equalities are always active. Inequalities are guessed from the numerical hint; the guess is
    # only a starting point — every result below is proved exactly.
    W: list[int] = list(range(meq))
    if hint_z is not None:
        zh = np.asarray(hint_z, dtype=float)
        sl = C_np.T @ zh - b_np
        scale = max(1.0, float(np.max(np.abs(b_np))) if b_np.size else 1.0)
        for j in range(meq, nrows):
            if sl[j] <= 1e-9 * scale:
                W.append(j)

    iterations = 0
    try:
        while iterations < MAX_ACTIVE_SET_ITERATIONS:
            iterations += 1

            # Equality-constrained KKT for the working set, solved exactly.
            #   H z - a - sum_{j in W} lam_j C_j = 0      and      C_j' z = b_j  (j in W)
            # Eliminating z = H^-1 (a + sum lam_j C_j) gives the dense |W| x |W| system
            #   (C_W' H^-1 C_W) lam = b_W - C_W' H^-1 a
            # Degeneracy: |W| may exceed n, making the KKT matrix singular by construction. Solve on
            # a maximal independent subset; every dropped row is verified exactly below.
            W = sorted(set(W))
            eq_in_W = [j for j in W if j < meq]
            W_ordered = eq_in_W + [j for j in W if j >= meq]
            sub = _independent_subset([Ccol[j] for j in W_ordered], len(eq_in_W))
            W_solve = [W_ordered[s] for s in sub]

            Hinv = [Fraction(1) / h for h in Hd]
            mat: list[list[Fraction]] = []
            rhs: list[Fraction] = []
            for jr in W_solve:
                cr = Ccol[jr]
                mat.append([sum((cr[i] * Hinv[i] * Ccol[jc][i] for i in range(n)), Fraction(0))
                            for jc in W_solve])
                rhs.append(bvec[jr] - sum((cr[i] * Hinv[i] * a[i] for i in range(n)), Fraction(0)))

            sol = _solve_exact(mat, rhs) if W_solve else []
            if sol is None:
                return ReferenceResult(R_UNAVAILABLE, iterations=iterations,
                                       detail="singular KKT system after independence reduction")
            lam = {jr: sol[r] for r, jr in enumerate(W_solve)}

            z = []
            for i in range(n):
                s = a[i] + sum((lam[jr] * Ccol[jr][i] for jr in W_solve), Fraction(0))
                z.append(s * Hinv[i])

            # ── dropped-but-active rows must still be EXACTLY tight ────────────────────────────
            # A row dropped for linear dependence is redundant only if the working set is
            # consistent. That is verified, never assumed; an inconsistent guess loses the row.
            bad_drop = next((j for j in W if j not in lam and slack(z, j) != 0), None)
            if bad_drop is not None:
                if bad_drop < meq:
                    return ReferenceResult(R_UNAVAILABLE, iterations=iterations,
                                           detail="equality row inconsistent under exact arithmetic")
                W.remove(bad_drop)
                continue

            # ── exact primal feasibility ────────────────────────────────────────────────────────
            worst_j, worst_v = None, Fraction(0)
            for j in range(nrows):
                if j in W:
                    continue
                s = slack(z, j)
                if s < worst_v:
                    worst_v, worst_j = s, j
            if worst_j is not None:
                W.append(worst_j)          # add the most-violated constraint and re-solve
                continue

            # ── exact dual feasibility (inequality multipliers only) ────────────────────────────
            neg_j, neg_v = None, Fraction(0)
            for j in W_solve:
                if j < meq:
                    continue
                if lam[j] < neg_v:
                    neg_v, neg_j = lam[j], j
            if neg_j is not None:
                W.remove(neg_j)            # drop the most-negative multiplier and re-solve
                continue

            # ── exact stationarity and complementarity, verified rather than assumed ────────────
            for i in range(n):
                lhs = Hd[i] * z[i] - a[i] - sum((lam[jr] * Ccol[jr][i] for jr in W_solve), Fraction(0))
                if lhs != 0:
                    return ReferenceResult(R_UNAVAILABLE, iterations=iterations,
                                           detail="exact stationarity residual is nonzero")
            for j in W_solve:
                if j >= meq and slack(z, j) != 0:
                    return ReferenceResult(R_UNAVAILABLE, iterations=iterations,
                                           detail="active constraint not exactly tight")

            return ReferenceResult(R_EXACT, z=tuple(z), lam=lam,
                                   active_set=tuple(sorted(W_solve)), iterations=iterations)

        return ReferenceResult(R_UNAVAILABLE, iterations=iterations,
                               detail=f"active-set iteration ceiling {MAX_ACTIVE_SET_ITERATIONS}")
    except OverflowError as exc:
        return ReferenceResult(R_UNAVAILABLE, iterations=iterations, detail=str(exc))


def exact_distance(z_float: np.ndarray, z_exact: tuple[Fraction, ...]) -> Fraction:
    """Exact squared distance ||z - z*||^2 between a double vector and the exact minimiser."""
    zf = [to_fraction(v) for v in np.asarray(z_float, dtype=float).ravel()]
    return sum(((zf[i] - z_exact[i]) ** 2 for i in range(len(z_exact))), Fraction(0))
