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
"""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass, field
from fractions import Fraction

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


# ======================================================================================
# Structure-aware exact solve: singleton-first, then a fraction-free core.
# The reduction is an ACCELERATION. The full unreduced system is the certificate authority.
# ======================================================================================
def _bareiss(A, b):
    """Fraction-free (Bareiss) elimination. Deterministic pivoting: the first EXACTLY nonzero
    entry in canonical row order — never a floating magnitude, which does not exist here.

    Fraction-free keeps intermediate integers determinant-bounded instead of letting rational
    numerators and denominators compound at every elimination step.
    """
    rows = len(A)
    ncols = len(A[0]) if rows else 0
    Ab = [list(A[i]) + [b[i]] for i in range(rows)]
    prev = ONE
    for k in range(ncols):
        cand = next((i for i in range(k, rows) if Ab[i][k] != 0), None)
        if cand is None:
            raise SimplexUnavailable("EXACT_SIMPLEX_SINGULAR: exactly singular core")
        if cand != k:
            Ab[k], Ab[cand] = Ab[cand], Ab[k]
        for i in range(k + 1, rows):
            for j in range(k + 1, ncols + 1):
                Ab[i][j] = (Ab[i][j] * Ab[k][k] - Ab[i][k] * Ab[k][j]) / prev
            Ab[i][k] = ZERO
        prev = Ab[k][k]

    x = [ZERO] * ncols
    for i in range(ncols - 1, -1, -1):
        acc = Ab[i][ncols]
        for j in range(i + 1, ncols):
            acc -= Ab[i][j] * x[j]
        x[i] = acc / Ab[i][i]
    return x


def solve_exact(cols, rhs, stats=None):
    """Solve A x = rhs exactly; `cols` are A's columns. A may have more rows than columns.

    Singleton-column elimination first: a column with exactly one nonzero among the live rows lives
    in only that row, so that row DEFINES its variable and constrains nothing else. Remove both,
    repeat to a fixed point. Canonical order throughout: ascending column identity, then ascending
    row identity — never incoming indices or hash iteration order.
    """
    t0 = time.perf_counter()
    nrows, ncols = len(rhs), len(cols)
    if ncols > nrows:
        raise SimplexUnavailable(f"EXACT_SIMPLEX_SINGULAR: {ncols} columns for {nrows} rows")

    live_rows, live_cols = set(range(nrows)), set(range(ncols))
    order = []
    changed = True
    while changed:
        changed = False
        for j in sorted(live_cols):
            nz = [r for r in sorted(live_rows) if cols[j][r] != 0]
            if len(nz) == 1:
                order.append((j, nz[0]))
                live_cols.discard(j)
                live_rows.discard(nz[0])
                changed = True
                break

    core_cols, core_rows = sorted(live_cols), sorted(live_rows)
    x = [None] * ncols
    if core_cols:
        A = [[cols[j][r] for j in core_cols] for r in core_rows]
        for j, val in zip(core_cols, _bareiss(A, [rhs[r] for r in core_rows]), strict=True):
            x[j] = val

    for j, r in reversed(order):
        acc = rhs[r]
        for k in range(ncols):
            if k != j and x[k] is not None and cols[k][r] != 0:
                acc -= cols[k][r] * x[k]
        x[j] = acc / cols[j][r]

    if any(v is None for v in x):
        raise SimplexUnavailable("EXACT_SIMPLEX_SINGULAR: reconstruction incomplete")

    for r in range(nrows):                       # the ORIGINAL unreduced system IS the authority
        acc = ZERO
        for j in range(ncols):
            if cols[j][r] != 0:
                acc += cols[j][r] * x[j]
        if acc != rhs[r]:
            raise SimplexUnavailable(
                f"EXACT_SIMPLEX_SINGULAR: unreduced equation {r} not satisfied exactly")

    if stats is not None:
        stats["core_seconds"] = stats.get("core_seconds", 0.0) + (time.perf_counter() - t0)
        stats["core_dim_max"] = max(stats.get("core_dim_max", 0), len(core_cols))
        stats["singletons_max"] = max(stats.get("singletons_max", 0), len(order))
    return x


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
        x_B = solve_exact(cols, list(h), stats)
        if any(v < 0 for v in x_B):
            raise SimplexUnavailable(
                f"EXACT_SIMPLEX_SINGULAR: phase {phase} basis is not primal feasible")

        c_B = [c[j] for j in basis]
        # B' y = c_B — the same structure-aware exact solve, applied to the transpose.
        tcols = [[cols[i][r] for i in range(nrows)] for r in range(nrows)]
        y = solve_exact(tcols, c_B, stats)

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

        d = solve_exact(cols, [M[r][entering] for r in range(nrows)], stats)
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
    stats = {"max_num_bits": 0, "max_den_bits": 0, "core_seconds": 0.0,
             "core_dim_max": 0, "singletons_max": 0}
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
    redundant = []
    for i in range(nrows):
        if basis[i] < ncols:
            continue
        cols = [[Mi[r][j] for r in range(nrows)] for j in basis]
        swapped = False
        for j in range(ncols):                              # canonical entering order
            if j in basis:
                continue
            d = solve_exact(cols, [Mi[r][j] for r in range(nrows)], stats)
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
