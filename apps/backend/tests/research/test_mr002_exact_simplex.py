"""MR-002 — the shared exact basis decomposition (owner ruling §6).

The decomposition is an ACCELERATION, so these fixtures are not about whether the simplex is right —
the certificates inside `solve_lp` settle that. They are about whether reusing ONE decomposition for
three solves computes the same thing three times, and in particular whether the TRANSPOSE solve —
which no longer discovers any structure of its own, but inherits B's — lands on the same exact dual
the old independent factorization did.

The reference here is deliberately naive: plain Fraction Gaussian elimination, no singletons, no
fraction-free trick, no reuse. If the decomposition and the naive solve ever disagree, the
decomposition is wrong, because the naive one has nothing in it to be clever about.
"""

from __future__ import annotations

import random
from fractions import Fraction

import pytest

from app.research.mr002.exact_simplex import (
    ONE,
    ZERO,
    BasisDecomposition,
    SimplexUnavailable,
    _bareiss_factor,
    decompose,
    solve_lp,
)


# ---------------------------------------------------------------- an independent reference
def gauss(B, rhs):
    """Plain exact Gaussian elimination. Nothing shared with the code under test."""
    n = len(rhs)
    A = [[B[r][c] for c in range(n)] + [rhs[r]] for r in range(n)]
    for k in range(n):
        p = next((i for i in range(k, n) if A[i][k] != 0), None)
        if p is None:
            raise SimplexUnavailable("singular")
        A[k], A[p] = A[p], A[k]
        for i in range(k + 1, n):
            if A[i][k]:
                f = A[i][k] / A[k][k]
                for j in range(k, n + 1):
                    A[i][j] -= f * A[k][j]
    x = [ZERO] * n
    for i in range(n - 1, -1, -1):
        x[i] = (A[i][n] - sum(A[i][j] * x[j] for j in range(i + 1, n))) / A[i][i]
    return x


def make_basis(n, n_singleton, rng):
    """A basis with `n_singleton` structurally-singleton columns — the shape the repair LP's slack,
    bound and proximity variables actually give it (s, v, p, q each appear in exactly one row)."""
    B = [[ZERO] * n for _ in range(n)]
    rows = list(range(n))
    rng.shuffle(rows)
    for j in range(n_singleton):
        B[rows[j]][j] = Fraction(rng.choice([-1, 1]))
    for j in range(n_singleton, n):
        for r in range(n):
            if rng.random() < 0.45:
                B[r][j] = Fraction(rng.randint(-8, 8), rng.choice([1, 2, 4, 8]))
    return B


def cols_of(B, n):
    return [[B[r][j] for r in range(n)] for j in range(n)]


def nonsingular(n, ns, seed):
    rng = random.Random(seed)
    for _ in range(80):
        B = make_basis(n, ns, rng)
        try:
            gauss(B, [ONE] * n)
        except SimplexUnavailable:
            continue
        return B, rng
    pytest.skip("no nonsingular draw")
    return None


# ---------------------------------------------------------------- the factorization identity
@pytest.mark.parametrize(("n", "ns"), [(8, 4), (16, 10), (24, 16), (40, 30)])
def test_factorization_identity_T_A_equals_U(n, ns):
    """T @ A_int == U, exactly, and U really is upper triangular. This is the property the transpose
    solve leans on: without it, U' is not lower triangular and the reverse substitution is nonsense.
    """
    B, _ = nonsingular(n, ns, seed=n)
    cols = cols_of(B, n)
    dec = decompose(cols, n)
    k = len(dec.core_pos)
    if k == 0:
        pytest.skip("fully triangular basis — no core to factor")

    A_int = [[(cols[j][r] * dec.scale[a]).numerator for j in dec.core_pos]
             for a, r in enumerate(dec.core_rows)]
    t_a = [[sum(dec.T[i][t] * A_int[t][j] for t in range(k)) for j in range(k)] for i in range(k)]
    assert t_a == [list(row) for row in dec.U]
    for i in range(k):
        for j in range(i):
            assert dec.U[i][j] == 0


def test_bareiss_stays_integral():
    """Every intermediate is a minor determinant, hence an integer. A rational leaking in would mean
    the determinant bound no longer holds and the bit growth is unbounded."""
    A = [[2, -1, 0], [-1, 2, -1], [0, -1, 2]]
    U, T = _bareiss_factor(A)
    assert all(isinstance(v, int) for row in U + T for v in row)
    TA = [[sum(T[i][t] * A[t][j] for t in range(3)) for j in range(3)] for i in range(3)]
    assert TA == U


# ---------------------------------------------------------------- one decomposition, three solves
@pytest.mark.parametrize(("n", "ns"), [(8, 4), (16, 10), (24, 16), (40, 30), (55, 40)])
def test_one_decomposition_serves_all_three_solves(n, ns):
    """B x = h, B d = a_enter and B' y = c_B, from a SINGLE decomposition, all exactly equal to the
    independent Gaussian reference. The dual is the one that matters: it never sees B'."""
    B, rng = nonsingular(n, ns, seed=100 + n)
    cols = cols_of(B, n)
    dec = decompose(cols, n)

    h = [Fraction(rng.randint(-9, 9), rng.choice([1, 2, 4])) for _ in range(n)]
    a_enter = [Fraction(rng.randint(-9, 9), rng.choice([1, 2, 8])) for _ in range(n)]
    c_B = [Fraction(rng.randint(-9, 9), rng.choice([1, 2, 4])) for _ in range(n)]

    assert dec.solve(h) == gauss(B, h)
    assert dec.solve(a_enter) == gauss(B, a_enter)

    Bt = [[B[r][c] for r in range(n)] for c in range(n)]
    assert dec.solve_transpose(c_B) == gauss(Bt, c_B)


@pytest.mark.parametrize(("n", "ns"), [(16, 10), (30, 22)])
def test_decomposition_is_rhs_independent(n, ns):
    """The same object, reused for many right-hand sides, must give what a fresh decomposition gives.
    If it carried RHS state, reuse across pivots would silently corrupt the direction solve."""
    B, rng = nonsingular(n, ns, seed=200 + n)
    cols = cols_of(B, n)
    dec = decompose(cols, n)
    for _ in range(6):
        rhs = [Fraction(rng.randint(-9, 9), rng.choice([1, 2, 4])) for _ in range(n)]
        assert dec.solve(rhs) == decompose(cols, n).solve(rhs) == gauss(B, rhs)


def test_singleton_structure_is_block_triangular():
    """The claim the transpose reuse rests on: when column j_q is eliminated at step q, it has NO
    nonzero in any core row, and none in any row eliminated later."""
    B, _ = nonsingular(40, 30, seed=7)
    cols = cols_of(B, 40)
    dec = decompose(cols, 40)
    elim_rows = [r for _, r in dec.order]
    for q, (pos, _r_q) in enumerate(dec.order):
        for r in dec.core_rows:
            assert cols[pos][r] == 0, "a singleton column has a nonzero in a core row"
        for p in range(q + 1, len(dec.order)):
            assert cols[pos][elim_rows[p]] == 0, "a singleton column reaches a later-eliminated row"


# ---------------------------------------------------------------- refusal, not a wrong answer
def test_singular_basis_is_refused():
    B = [[ONE, ONE], [ONE, ONE]]
    with pytest.raises(SimplexUnavailable, match="EXACT_SIMPLEX_SINGULAR"):
        decompose(cols_of(B, 2), 2).solve([ONE, ONE])


def test_verification_catches_a_corrupted_decomposition():
    """The full unreduced system — not the reduced core — is the authority. Corrupt the factors and
    the solve must STOP, not return the wrong vector. This is what keeps a defect in the acceleration
    from ever reaching a certificate."""
    B, _ = nonsingular(16, 10, seed=11)
    cols = cols_of(B, 16)
    dec = decompose(cols, 16)
    if not dec.core_pos:
        pytest.skip("no core")
    bad_U = [list(r) for r in dec.U]
    bad_U[0][0] = bad_U[0][0] + 1                        # a single corrupted pivot
    corrupt = BasisDecomposition(
        nrows=dec.nrows, cols=dec.cols, order=dec.order, core_pos=dec.core_pos,
        core_rows=dec.core_rows, scale=dec.scale,
        U=tuple(tuple(r) for r in bad_U), T=dec.T,
    )
    with pytest.raises(SimplexUnavailable, match="unreduced"):
        corrupt.solve([ONE] * 16)


# ---------------------------------------------------------------- end to end, through solve_lp
def test_solve_lp_exact_optimum_and_certificates():
    """min rho s.t. w0 + w1 = 5/8, 0 <= w <= 1, |w_i - 1/4| <= rho  ->  rho* = 1/16 exactly."""
    z = [Fraction(1, 4), Fraction(1, 4)]
    n, N = 2, 4 * 2 + 0 + 1
    W, V, P, Q, RHO = 0, 2, 4, 6, 8
    M, h = [], []
    row = [ZERO] * N
    row[W], row[W + 1] = ONE, ONE
    M.append(row)
    h.append(Fraction(5, 8))
    for i in range(n):
        r = [ZERO] * N
        r[W + i], r[V + i] = ONE, ONE
        M.append(r)
        h.append(ONE)
    for i in range(n):
        r = [ZERO] * N
        r[W + i], r[P + i], r[RHO] = ONE, ONE, Fraction(-1)
        M.append(r)
        h.append(z[i])
    for i in range(n):
        r = [ZERO] * N
        r[W + i], r[Q + i], r[RHO] = Fraction(-1), ONE, Fraction(-1)
        M.append(r)
        h.append(-z[i])
    c = [ZERO] * N
    c[RHO] = ONE

    res = solve_lp(M, h, c)
    assert res.objective == Fraction(1, 16)
    assert res.x[RHO] == Fraction(1, 16)
    assert res.n_decompositions > 0                      # the shared path really was used
