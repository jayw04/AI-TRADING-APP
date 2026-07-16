"""MR-002 — CANONICAL EXACT RATIONAL SIMPLEX (Phase I + Phase II).

This is the repair-LP OPTIMIZER, not a postprocessor. It replaces the HiGHS basis oracle, which is
RETIRED from the evidentiary path.

WHY THE ORACLE HAD TO GO
------------------------
HiGHS returned `kOptimal` with `rho = 0` on every corpus instance, at every tolerance it accepts.
The rho = 0 vertex does not exist in exact arithmetic — z_s is NOT exactly feasible, which is the
entire reason a repair is needed — so `h` fell outside the column space of the returned basis and no
exact reconstruction was possible. Tightening the tolerance shrank the inconsistency (1e-8 -> 1e-18)
without ever removing it. The exact optimum rho* lives at ~1e-17; the oracle's resolution floor is
~1e-12. It was being asked to see something beneath its epsilon.

Exact rational simplex has NO tolerance. Every comparison, ratio test, zero test and pivot is an
exact rational operation, so the pivots that only matter at 1e-17 are not merely accurate — they are
DECIDABLE.

    min c'x   s.t.   Mx = h,   x >= 0            (the canonical nonnegative standard form)

PHASE I builds its own feasible basis from artificials — it does not warm-start from a
floating-point solver. That was considered and rejected: repairing an exactly-infeasible basis needs
essentially all of this machinery anyway, and it would leave a float dependency in the proof path.

DETERMINISM. Bland's rule over CANONICAL identities. The standard form is constructed in canonical
model order, so a column's index IS its canonical identity. No floating magnitude, no approximate
tie, no hash iteration order and no solver-supplied priority may influence a pivot. Bland's rule is
binding even where another policy would be faster: it is what makes the pivot sequence reproducible
and free of cycling.

COST. Each basis is decomposed ONCE and the decomposition serves all three of its solves. See
`decompose` for why the transpose is the reason that matters. The decomposition is an ACCELERATION
and carries no authority: every solve it produces is verified against the FULL UNREDUCED system
before it is used.
"""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass, field
from fractions import Fraction
from math import lcm

# ======================================================================================
# FROZEN RESOURCE CEILINGS. Operational stop limits — NOT mathematical tolerances.
# They may not be raised after observing a stopped instance without a new adjudication.
# ======================================================================================
MAX_PIVOTS_PHASE_I = 4000
MAX_PIVOTS_PHASE_II = 4000
MAX_NUMERATOR_BITS = 200_000
MAX_DENOMINATOR_BITS = 200_000
MAX_SECONDS_PER_REPAIR = 600.0
MAX_PEAK_MEMORY_MB = 4096

ZERO = Fraction(0)
ONE = Fraction(1)


# ======================================================================================
# EQUIVALENCE TRACE. Pure recording. It observes the pivot sequence; it never influences it.
#
# The acceleration is only accepted if it reproduces the reference pivot-for-pivot and value-for-
# value, so the comparison needs a record with no room to hide in: the entering and leaving
# identities at every pivot, the basis content after every pivot, and every exact output. Anything
# summarised (a pivot COUNT, a float) could agree while the underlying computation diverged.
# ======================================================================================
def basis_hash(basis) -> str:
    """The basis CONTENT, positionally. Position is carried by the algorithm (it indexes x_B and the
    ratio test's tie-break), so hashing the ordered tuple is strictly stronger than hashing the set:
    it detects a divergence that permuted the basis without changing its membership."""
    d = hashlib.sha256(b"MR002|simplex-basis|v1")
    for j in basis:
        d.update(f"|{j}".encode())
    return d.hexdigest()


def _fr(v: Fraction) -> str:
    return f"{v.numerator}/{v.denominator}"


def _frs(vs) -> list[str]:
    return [_fr(v) for v in vs]


class SimplexUnavailable(RuntimeError):
    """REPAIR_CERTIFICATE_UNAVAILABLE from the exact solver.

    Reason codes: EXACT_PHASE_I_POSITIVE, ARTIFICIAL_BASIS_CLEANUP_FAILED,
                  EXACT_SIMPLEX_SINGULAR, EXACT_SIMPLEX_UNBOUNDED,
                  EXACT_SIMPLEX_RESOURCE_LIMIT.
    """


@dataclass(frozen=True)
class SimplexResult:
    x: tuple                      # exact primal, full standard-form vector
    y: tuple                      # exact dual
    basis: tuple                  # canonical column identities of the final basis
    objective: Fraction
    pivots_phase_i: int
    pivots_phase_ii: int
    redundant_rows: tuple = field(default=())
    full_basis_dim: int = 0
    core_dim_max: int = 0
    singletons_max: int = 0
    max_num_bits: int = 0
    max_den_bits: int = 0
    solve_seconds: float = 0.0
    core_seconds: float = 0.0
    certificate_seconds: float = 0.0
    # ---- §8 resource characterization -------------------------------------------------------
    decomposition_seconds: float = 0.0     # singleton discovery + integerising, per basis
    core_factor_seconds: float = 0.0       # the fraction-free core factorization
    primal_solve_seconds: float = 0.0      # B x_B = h
    direction_solve_seconds: float = 0.0   # B d  = a_enter
    dual_solve_seconds: float = 0.0        # B' y = c_B
    verify_seconds: float = 0.0            # exact verification against the unreduced systems
    n_decompositions: int = 0


# ======================================================================================
# ONE DETERMINISTIC EXACT DECOMPOSITION PER BASIS  (owner ruling §6)
#
# The previous implementation solved each of the three systems at a basis by rediscovering the
# structure from scratch:
#
#     B x_B = h          singleton-first + fraction-free core        (cheap: the core is small)
#     B d   = a_enter    singleton-first + fraction-free core        (cheap: same structure)
#     B' y  = c_B        singleton-first + fraction-free core   <--- THE BOTTLENECK
#
# The transpose was the defect. Singleton discovery run INDEPENDENTLY on B' looks for columns of B'
# with exactly one nonzero — but the columns of B' are the ROWS of B, which carry 2-3 nonzeros each.
# So no singleton is ever found, the reduction eliminates nothing, and the solve falls through to a
# dense Bareiss elimination on the FULL basis with several-hundred-bit integers. Measured: a core of
# 115 in a 116-row basis. The structure was there. The transpose solve simply could not see it,
# because it was looking for it in the wrong matrix.
#
# The fix is not a better search. It is to stop searching twice. The singleton eliminations of B ARE
# a permutation of B to block-triangular form, and that form transposes for free:
#
#     rows [core | r_1 ... r_s]                      B_perm = [ A_core   0  ]
#     cols [core | j_1 ... j_s]                               [   X      U  ]
#
#   * when column j_q is eliminated, its only nonzero among the LIVE rows is at r_q. Core rows are
#     live throughout, so B[r][j_q] = 0 for every core row r. And r_p for p > q was still live at
#     step q, so B[r_p][j_q] = 0 there too. Hence U is upper triangular with the pivots B[r_q][j_q]
#     on its diagonal, and the block above it is exactly zero.
#
# Transposing:  B_perm' = [ A_core'   X' ]   — block upper triangular, with U' LOWER triangular.
#                         [   0       U' ]
#
# So the dual solve reuses the SAME eliminations, walked in the opposite direction:
#
#     primal   core solve, then the singletons by BACK substitution     (reverse elimination order)
#     dual     the singletons by FORWARD substitution (elimination order), then the core on A'
#
# No second singleton discovery. No second factorization. The core is factored once per basis and
# its factors are used transposed. This is a reuse of structure, not a new method: every value the
# decomposition produces is still checked against the full unreduced system before it is used, so a
# defect in the reuse cannot reach a certificate — it can only stop the run.
# ======================================================================================
def _bareiss_factor(A):
    """Fraction-free elimination of the AUGMENTED [A | I], yielding (U, T) with  T @ A = U  exactly,
    U upper triangular. A must be INTEGER.

    Augmenting with the identity is what makes the factorization reusable: T accumulates the row
    operations, so a later right-hand side is transformed by a matrix-vector product instead of a
    re-elimination — and T' serves the transpose solve without any new pivoting.

    Every intermediate stays an integer (each is a minor determinant of the augmented matrix), so
    numerators remain determinant-bounded instead of letting rational denominators compound at every
    step. The exactness of the one-step division is NOT assumed: it is checked. A nonzero remainder
    would mean the fraction-free invariant had been broken — a defect, not a rounding.

    Pivoting: the first EXACTLY nonzero entry in canonical row order — never a magnitude, which does
    not exist here. The Bareiss-reduced entries are nonzero-scalar multiples of the Gaussian ones, so
    this selects exactly the pivots the unaugmented reduction would.
    """
    k = len(A)
    W = [list(A[i]) + [1 if j == i else 0 for j in range(k)] for i in range(k)]
    prev = 1
    for p in range(k):
        piv = next((i for i in range(p, k) if W[i][p] != 0), None)
        if piv is None:
            raise SimplexUnavailable("EXACT_SIMPLEX_SINGULAR: exactly singular core")
        if piv != p:
            W[p], W[piv] = W[piv], W[p]
        Wp = W[p]
        pk = Wp[p]
        for i in range(p + 1, k):
            Wi = W[i]
            mi = Wi[p]
            for j in range(p + 1, 2 * k):
                q, rem = divmod(Wi[j] * pk - mi * Wp[j], prev)
                if rem:
                    raise SimplexUnavailable(
                        "EXACT_SIMPLEX_SINGULAR: fraction-free division left a remainder — the "
                        "Bareiss integrality invariant is broken")
                Wi[j] = q
            Wi[p] = 0
        prev = pk
    return [row[:k] for row in W], [row[k:] for row in W]


@dataclass(frozen=True)
class BasisDecomposition:
    """The single exact decomposition of one simplex basis B, reused for all three of its solves.

    `cols[i]` is the column of B for basis POSITION i, indexed by row: B[r][i] = cols[i][r].
    """

    nrows: int
    cols: tuple                 # the unreduced basis — the certificate authority
    order: tuple                # ((basis_pos, row), ...) singleton eliminations, ELIMINATION order
    core_pos: tuple             # basis positions surviving into the core
    core_rows: tuple
    scale: tuple                # per-core-row multiplier that integerises the core
    U: tuple                    # k x k integer, upper triangular:  T @ A_int = U
    T: tuple                    # k x k integer, the accumulated row operations

    # ---- primal:  B x = rhs  (also serves  B d = a_enter — same factors, another RHS) ---------
    def solve(self, rhs, stats=None, bucket="primal_solve_seconds"):
        t0 = time.perf_counter()
        k = len(self.core_pos)
        x: list = [None] * self.nrows

        if k:
            #  A_core x_core = rhs_core, via  U x_core = T (diag(scale) rhs_core)
            b = [rhs[self.core_rows[a]] * self.scale[a] for a in range(k)]
            w = [sum(self.T[i][j] * b[j] for j in range(k)) for i in range(k)]
            xc = [ZERO] * k
            for i in range(k - 1, -1, -1):                # back substitution through U
                acc = w[i]
                Ui = self.U[i]
                for j in range(i + 1, k):
                    if Ui[j]:
                        acc -= Ui[j] * xc[j]
                xc[i] = acc / Ui[i]
            for b_i, pos in enumerate(self.core_pos):
                x[pos] = xc[b_i]

        for pos, r in reversed(self.order):              # singletons, REVERSE elimination order
            acc = rhs[r]
            col_r = [self.cols[j][r] for j in range(self.nrows)]
            for j in range(self.nrows):
                if j != pos and x[j] is not None and col_r[j] != 0:
                    acc -= col_r[j] * x[j]
            x[pos] = acc / self.cols[pos][r]

        if any(v is None for v in x):
            raise SimplexUnavailable("EXACT_SIMPLEX_SINGULAR: reconstruction incomplete")
        if stats is not None:
            stats[bucket] = stats.get(bucket, 0.0) + (time.perf_counter() - t0)
        self._verify(rhs, x, stats)
        return x

    # ---- dual:  B' y = c_B, through the TRANSPOSED factors, reverse substitution order --------
    def solve_transpose(self, c_B, stats=None):
        t0 = time.perf_counter()
        k = len(self.core_pos)
        y: list = [None] * self.nrows

        # U' is LOWER triangular, so the singleton rows resolve by FORWARD substitution — in the
        # SAME order they were eliminated, the mirror of the primal's reverse walk. Column j_q has
        # nonzeros only at rows r_1..r_q, so its equation never references a y that is not yet known.
        for pos, r_q in self.order:
            acc = c_B[pos]
            col = self.cols[pos]
            for r in range(self.nrows):
                if r == r_q or col[r] == 0:
                    continue
                if y[r] is None:
                    raise SimplexUnavailable(
                        f"EXACT_SIMPLEX_SINGULAR: basis column {pos} has a nonzero at row {r}, "
                        f"which the singleton elimination order requires to be zero — the "
                        f"block-triangular structure the decomposition rests on does not hold")
                acc -= col[r] * y[r]
            y[r_q] = acc / col[r_q]

        if k:
            # A_core' y_core = c_core - X' y_sing, then the SAME factors, transposed:
            #   A_int = T^-1 U   =>   A_int' = U' T^-'   =>   U' w = d,  y' = T' w
            d = []
            for pos in self.core_pos:
                acc = c_B[pos]
                col = self.cols[pos]
                for _p, r in self.order:
                    if col[r] != 0:
                        acc -= col[r] * y[r]
                d.append(acc)
            w = [ZERO] * k
            for i in range(k):                           # forward substitution through U' (lower)
                acc = d[i]
                for j in range(i):
                    if self.U[j][i]:
                        acc -= self.U[j][i] * w[j]
                w[i] = acc / self.U[i][i]
            for a in range(k):                           # y' = T' w, then undo the row integerising
                y[self.core_rows[a]] = sum(
                    self.T[j][a] * w[j] for j in range(k)) * self.scale[a]

        if any(v is None for v in y):
            raise SimplexUnavailable("EXACT_SIMPLEX_SINGULAR: dual reconstruction incomplete")
        if stats is not None:
            stats["dual_solve_seconds"] = stats.get("dual_solve_seconds", 0.0) + (
                time.perf_counter() - t0)
        self._verify_transpose(c_B, y, stats)
        return y

    # ---- the FULL UNREDUCED system is the authority, for EVERY solve -------------------------
    def _verify(self, rhs, x, stats=None):
        t0 = time.perf_counter()
        for r in range(self.nrows):
            acc = ZERO
            for j in range(self.nrows):
                v = self.cols[j][r]
                if v != 0:
                    acc += v * x[j]
            if acc != rhs[r]:
                raise SimplexUnavailable(
                    f"EXACT_SIMPLEX_SINGULAR: unreduced equation {r} not satisfied exactly")
        if stats is not None:
            stats["verify_seconds"] = stats.get("verify_seconds", 0.0) + (
                time.perf_counter() - t0)

    def _verify_transpose(self, c_B, y, stats=None):
        t0 = time.perf_counter()
        for i in range(self.nrows):
            acc = ZERO
            col = self.cols[i]
            for r in range(self.nrows):
                if col[r] != 0:
                    acc += col[r] * y[r]
            if acc != c_B[i]:
                raise SimplexUnavailable(
                    f"EXACT_SIMPLEX_SINGULAR: unreduced transposed equation {i} not satisfied "
                    f"exactly")
        if stats is not None:
            stats["verify_seconds"] = stats.get("verify_seconds", 0.0) + (
                time.perf_counter() - t0)


def decompose(cols, nrows, stats=None) -> BasisDecomposition:
    """The ONE decomposition of basis B. It is built from B alone — it holds no right-hand side,
    which is precisely why the same object serves the primal RHS, the pivot direction and the dual.

    Singleton-column elimination: a column with exactly one nonzero among the live rows lives in only
    that row, so that row DEFINES its variable and constrains nothing else. Remove both, repeat to a
    fixed point. Canonical order throughout — ascending basis position, then ascending row — never
    incoming indices or hash iteration order.
    """
    t0 = time.perf_counter()
    live = {j: {r for r in range(nrows) if cols[j][r] != 0} for j in range(nrows)}
    live_rows = set(range(nrows))

    order = []
    while True:
        pick = next((j for j in sorted(live) if len(live[j]) == 1), None)
        if pick is None:
            break
        r = next(iter(live[pick]))
        order.append((pick, r))
        del live[pick]
        live_rows.discard(r)
        for j in live:
            live[j].discard(r)

    core_pos = tuple(sorted(live))
    core_rows = tuple(sorted(live_rows))
    k = len(core_pos)

    # Integerise each core ROW. Bareiss's determinant bound is an INTEGER-matrix property; handing it
    # rationals would let denominators compound exactly where the bound was supposed to stop them.
    scale: list[int] = []
    A_int: list[list[int]] = []
    for r in core_rows:
        mult = 1
        for j in core_pos:
            mult = lcm(mult, cols[j][r].denominator)
        row = []
        for j in core_pos:
            v = cols[j][r] * mult
            if v.denominator != 1:
                raise SimplexUnavailable("EXACT_SIMPLEX_SINGULAR: integerising the core failed")
            row.append(v.numerator)
        scale.append(mult)
        A_int.append(row)
    t1 = time.perf_counter()

    U, T = _bareiss_factor(A_int) if k else ([], [])
    t2 = time.perf_counter()

    if stats is not None:
        stats["decomposition_seconds"] = stats.get("decomposition_seconds", 0.0) + (t1 - t0)
        stats["core_factor_seconds"] = stats.get("core_factor_seconds", 0.0) + (t2 - t1)
        stats["core_seconds"] = stats.get("core_seconds", 0.0) + (t2 - t0)
        stats["n_decompositions"] = stats.get("n_decompositions", 0) + 1
        stats["core_dim_max"] = max(stats.get("core_dim_max", 0), k)
        stats["singletons_max"] = max(stats.get("singletons_max", 0), len(order))

    return BasisDecomposition(
        nrows=nrows, cols=tuple(cols), order=tuple(order), core_pos=core_pos,
        core_rows=core_rows, scale=tuple(scale),
        U=tuple(tuple(r) for r in U), T=tuple(tuple(r) for r in T),
    )


# ======================================================================================
def _bits(vals):
    num = den = 0
    for v in vals:
        if v:
            num = max(num, v.numerator.bit_length())
            den = max(den, v.denominator.bit_length())
    return num, den


def _check_limits(t0, stats):
    if time.perf_counter() - t0 > MAX_SECONDS_PER_REPAIR:
        raise SimplexUnavailable(
            f"EXACT_SIMPLEX_RESOURCE_LIMIT: exceeded {MAX_SECONDS_PER_REPAIR}s")
    if stats["max_num_bits"] > MAX_NUMERATOR_BITS or stats["max_den_bits"] > MAX_DENOMINATOR_BITS:
        raise SimplexUnavailable(
            f"EXACT_SIMPLEX_RESOURCE_LIMIT: integer growth "
            f"{stats['max_num_bits']}/{stats['max_den_bits']} bits")


def _new_stats():
    return {"max_num_bits": 0, "max_den_bits": 0, "core_seconds": 0.0,
            "core_dim_max": 0, "singletons_max": 0, "decomposition_seconds": 0.0,
            "core_factor_seconds": 0.0, "primal_solve_seconds": 0.0,
            "direction_solve_seconds": 0.0, "dual_solve_seconds": 0.0,
            "verify_seconds": 0.0, "n_decompositions": 0}


def _iterate(M, h, c, basis, nrows, ncols, allowed, max_pivots, t0, stats, phase, trace=None):
    """Exact revised simplex from a feasible `basis`. Returns (basis, x, y, pivots).

    `allowed` restricts the entering columns (Phase II excludes artificials — they are gone by
    then, but the guard is explicit).

    `trace`, when supplied, RECORDS the pivot sequence. It is appended to after each decision has
    already been made, so it cannot influence one.
    """
    pivots = 0
    while True:
        cols = [[M[r][j] for r in range(nrows)] for j in basis]
        dec = decompose(cols, nrows, stats)          # ONE decomposition; three solves below

        x_B = dec.solve(list(h), stats)
        if any(v < 0 for v in x_B):
            raise SimplexUnavailable(
                f"EXACT_SIMPLEX_SINGULAR: phase {phase} basis is not primal feasible")

        c_B = [c[j] for j in basis]
        y = dec.solve_transpose(c_B, stats)          # the SAME factors, transposed

        nb, nd = _bits(x_B + y)
        stats["max_num_bits"] = max(stats["max_num_bits"], nb)
        stats["max_den_bits"] = max(stats["max_den_bits"], nd)
        _check_limits(t0, stats)

        # BLAND'S RULE: entering = the SMALLEST canonical column identity with a negative exact
        # reduced cost. The standard form is built in canonical model order, so the column index IS
        # the canonical identity. This is what removes cycling and makes the pivot sequence
        # reproducible; it is binding even where another rule would be faster.
        in_basis = set(basis)
        entering = None
        for j in sorted(allowed):
            if j in in_basis:
                continue
            acc = ZERO
            for r in range(nrows):
                if M[r][j] != 0:
                    acc += M[r][j] * y[r]
            if c[j] - acc < 0:
                entering = j
                break
        if entering is None:
            return basis, x_B, y, pivots                 # exactly optimal: all reduced costs >= 0

        d = dec.solve([M[r][entering] for r in range(nrows)], stats, "direction_solve_seconds")
        pos = [i for i in range(nrows) if d[i] > 0]
        if not pos:
            raise SimplexUnavailable(f"EXACT_SIMPLEX_UNBOUNDED: phase {phase}")

        # Minimum exact ratio; ties broken by the SMALLEST canonical basic-variable identity.
        best = None
        for i in pos:
            ratio = x_B[i] / d[i]
            key = (ratio, basis[i])
            if best is None or key < best[0]:
                best = (key, i)
        leaving = best[1]
        basis = list(basis)
        leaving_id = basis[leaving]
        basis[leaving] = entering
        pivots += 1
        if trace is not None:
            trace.append({
                "phase": phase, "pivot": pivots,
                "entering": entering, "leaving_pos": leaving, "leaving": leaving_id,
                "ratio": _fr(best[0][0]), "basis_sha256": basis_hash(basis),
            })
        if pivots > max_pivots:
            raise SimplexUnavailable(
                f"EXACT_SIMPLEX_RESOURCE_LIMIT: phase {phase} exceeded {max_pivots} pivots")


def solve_lp(M, h, c, trace=None):
    """Exact Phase-I / Phase-II simplex on  min c'x  s.t.  Mx = h,  x >= 0.

    `trace`, when a dict is supplied, is filled with the complete equivalence record: the Phase-I and
    Phase-II pivot sequences, the basis content after every pivot, and every exact output.
    """
    t0 = time.perf_counter()
    nrows, ncols = len(M), len(c)
    stats = _new_stats()
    pivots_i: list = []
    pivots_ii: list = []

    # ---- PHASE I: canonical artificial basis. No floating-point warm start. -----------------
    # Normalize each row so its exact right-hand side is nonnegative, then give it one artificial
    # with coefficient +1. The artificials form an immediately feasible basis with x_B = h >= 0.
    Mi = [list(M[r]) for r in range(nrows)]
    hi = list(h)
    for r in range(nrows):
        if hi[r] < 0:
            Mi[r] = [-v for v in Mi[r]]
            hi[r] = -hi[r]
    for r in range(nrows):
        for rr in range(nrows):
            Mi[rr].append(ONE if rr == r else ZERO)
    c_I = [ZERO] * ncols + [ONE] * nrows
    basis = [ncols + r for r in range(nrows)]

    basis, x_B, _y, piv1 = _iterate(
        Mi, hi, c_I, basis, nrows, ncols + nrows, range(ncols + nrows),
        MAX_PIVOTS_PHASE_I, t0, stats, "I", pivots_i if trace is not None else None)

    phase1_obj = sum(x_B[i] for i in range(nrows) if basis[i] >= ncols)
    if trace is not None:
        trace["phase_i_pivots"] = pivots_i
        trace["phase_i_optimum"] = _fr(phase1_obj)
        trace["phase_i_basis"] = list(basis)
        trace["phase_i_basis_sha256"] = basis_hash(basis)
    if phase1_obj != 0:
        raise SimplexUnavailable(
            f"EXACT_PHASE_I_POSITIVE: exact Phase-I optimum is {float(phase1_obj):.3e} != 0, so "
            f"the canonical repair LP is EXACTLY INFEASIBLE. This is a mathematical result, not a "
            f"numerical failure — stop for adjudication.")

    # ---- Artificial cleanup: no artificial may enter Phase II. -------------------------------
    # ONE decomposition per basis, reused across every candidate entering column. The previous
    # version re-factorized for each candidate j, which is the same defect as the transpose: the
    # basis did not change between candidates, so neither did its decomposition.
    redundant = []
    for i in range(nrows):
        if basis[i] < ncols:
            continue
        cols = [[Mi[r][j] for r in range(nrows)] for j in basis]
        dec = decompose(cols, nrows, stats)
        swapped = False
        for j in range(ncols):                              # canonical entering order
            if j in basis:
                continue
            d = dec.solve([Mi[r][j] for r in range(nrows)], stats, "direction_solve_seconds")
            if d[i] != 0:                                   # exact nonzero pivot element
                basis[i] = j
                swapped = True
                break
        if not swapped:
            # No original column can replace this zero artificial => row i is EXACTLY redundant:
            # every original column has a zero pivot element in it, i.e. the row is a linear
            # combination of the others. That is a rank statement, recorded as such.
            redundant.append(i)
    if any(basis[i] >= ncols and i not in redundant for i in range(nrows)):
        raise SimplexUnavailable("ARTIFICIAL_BASIS_CLEANUP_FAILED")

    # ---- PHASE II on the ORIGINAL columns only -----------------------------------------------
    keep = [r for r in range(nrows) if r not in set(redundant)]
    M2 = [[M[r][j] for j in range(ncols)] for r in keep]
    h2 = [h[r] for r in keep]
    basis2 = [basis[i] for i in range(nrows) if i not in set(redundant)]
    if any(j >= ncols for j in basis2):
        raise SimplexUnavailable("ARTIFICIAL_BASIS_CLEANUP_FAILED: artificial survived into II")

    if trace is not None:
        trace["cleanup_basis"] = list(basis)
        trace["cleanup_basis_sha256"] = basis_hash(basis)
        trace["redundant_rows"] = list(redundant)

    basis2, x_B2, y2, piv2 = _iterate(
        M2, h2, c, basis2, len(keep), ncols, range(ncols),
        MAX_PIVOTS_PHASE_II, t0, stats, "II", pivots_ii if trace is not None else None)
    if trace is not None:
        trace["phase_ii_pivots"] = pivots_ii

    x = [ZERO] * ncols
    for i, j in enumerate(basis2):
        x[j] = x_B2[i]
    y = [ZERO] * nrows
    for i, r in enumerate(keep):
        y[r] = y2[i]

    nb, nd = _bits(list(x) + list(y))
    stats["max_num_bits"] = max(stats["max_num_bits"], nb)
    stats["max_den_bits"] = max(stats["max_den_bits"], nd)

    # ---- THE CERTIFICATE ----------------------------------------------------------------------
    tc = time.perf_counter()
    for r in range(nrows):                                  # exact primal feasibility
        acc = ZERO
        for j in range(ncols):
            if M[r][j] != 0:
                acc += M[r][j] * x[j]
        if acc != h[r]:
            raise SimplexUnavailable(f"EXACT_SIMPLEX_SINGULAR: Mx = h fails exactly at row {r}")
    if any(v < 0 for v in x):
        raise SimplexUnavailable("EXACT_SIMPLEX_SINGULAR: negative standard-form variable")

    reduced = []
    for j in range(ncols):                                  # M'y <= c: THE optimality proof
        acc = ZERO
        for r in range(nrows):
            if M[r][j] != 0:
                acc += M[r][j] * y[r]
        rc = c[j] - acc
        reduced.append(rc)
        if rc < 0:
            raise SimplexUnavailable(
                f"EXACT_SIMPLEX_SINGULAR: reduced cost of column {j} is negative at termination")

    primal = sum(c[j] * x[j] for j in range(ncols))
    dual = sum(h[r] * y[r] for r in range(nrows))
    if primal != dual:                                      # identity — consistency check only
        raise SimplexUnavailable("EXACT_SIMPLEX_SINGULAR: exact objectives disagree")
    cert_seconds = time.perf_counter() - tc

    if trace is not None:
        trace["final_basis"] = list(basis2)
        trace["final_basis_sha256"] = basis_hash(basis2)
        trace["x"] = _frs(x)
        trace["y"] = _frs(y)
        trace["reduced_costs"] = _frs(reduced)
        trace["objective_primal"] = _fr(primal)
        trace["objective_dual"] = _fr(dual)
        trace["objective_identity"] = primal == dual

    return SimplexResult(
        x=tuple(x), y=tuple(y), basis=tuple(basis2), objective=primal,
        pivots_phase_i=piv1, pivots_phase_ii=piv2, redundant_rows=tuple(redundant),
        full_basis_dim=len(keep), core_dim_max=stats["core_dim_max"],
        singletons_max=stats["singletons_max"],
        max_num_bits=stats["max_num_bits"], max_den_bits=stats["max_den_bits"],
        solve_seconds=time.perf_counter() - t0, core_seconds=stats["core_seconds"],
        certificate_seconds=cert_seconds,
        decomposition_seconds=stats["decomposition_seconds"],
        core_factor_seconds=stats["core_factor_seconds"],
        primal_solve_seconds=stats["primal_solve_seconds"],
        direction_solve_seconds=stats["direction_solve_seconds"],
        dual_solve_seconds=stats["dual_solve_seconds"],
        verify_seconds=stats["verify_seconds"],
        n_decompositions=stats["n_decompositions"],
    )


def ceilings() -> dict:
    """The frozen operational stop limits. NOT mathematical tolerances."""
    return {
        "max_pivots_phase_i": MAX_PIVOTS_PHASE_I,
        "max_pivots_phase_ii": MAX_PIVOTS_PHASE_II,
        "max_numerator_bits": MAX_NUMERATOR_BITS,
        "max_denominator_bits": MAX_DENOMINATOR_BITS,
        "max_seconds_per_repair": MAX_SECONDS_PER_REPAIR,
        "max_peak_memory_mb": MAX_PEAK_MEMORY_MB,
        "note": ("operational stop limits, not tolerances; they may not be raised after observing "
                 "a stopped instance without a new adjudication"),
    }
