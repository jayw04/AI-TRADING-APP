"""Find an instance whose canonical OPTIMAL multipliers are nonzero in as many blocks as the
QP family actually admits (ruling §5).

FINDING (see the run output): a *strictly* active LOWER bound is structurally unreachable in this
family. With H = diag(2/t), q = -2, a total-budget equality sum(z) = S, and nonnegative-coefficient
`<=` rows, stationarity in row i reads

    (2/t_i) z_i - 2 = nu - mu . row_i + sigma_i - tau_i

At z_i = 0 (lower bound active, tau_i = 0):   sigma_i = -2 - nu + mu . row_i
Any variable j that is interior and outside every binding row gives nu = (2/t_j) z_j - 2 >= -2,
so sigma_i > 0 demands mu . row_i > 2 + nu >= 0. But then every OTHER member k of that row has
(2/t_k) z_k = 2 + nu - mu . row_k < 0, i.e. z_k < 0 — impossible — so k is at zero too, the row
becomes slack, and mu collapses to 0. Contradiction.

So the optimal duals cannot exercise the lower-bound sign path. The equivalence fixture therefore
drives the certificate with ARBITRARY dual-feasible multipliers that are nonzero in all four
blocks (which is a strictly harder test of the sign mapping than optimal duals, since at an
optimum many terms vanish), and uses this instance's true optimum only for the tightness and
weak-duality checks.
"""

from __future__ import annotations

import sys

import numpy as np
import quadprog

sys.path.insert(0, "/work/apps/backend")

from app.research.mr002.joint_portfolio import _qp_matrices  # noqa: E402

rng = np.random.default_rng(11)
TOL = 1e-6
best = None

for _ in range(20000):
    n = 4
    t = np.round(rng.uniform(0.05, 0.60, n), 3)
    upper = np.round(rng.uniform(0.02, 0.40, n), 3)
    row = np.zeros(n)
    row[rng.choice(n, 2, replace=False)] = 1.0
    A_ub = row.reshape(1, n)
    b_ub = np.array([round(float(rng.uniform(0.02, 0.20)), 3)])
    A_eq = np.ones((1, n))
    b_eq = np.array([round(float(rng.uniform(0.10, 0.50)), 3)])

    C, b = _qp_matrices(A_ub, b_ub, A_eq, b_eq, upper, n)
    meq = 1
    try:
        out = quadprog.solve_qp(np.diag(2.0 / t), 2.0 * np.ones(n), C, b, meq)
    except ValueError:
        continue
    z, lam = np.asarray(out[0], float), np.asarray(out[4], float)
    nr = meq + A_ub.shape[0]
    nu, mu = lam[:meq], lam[meq:nr]
    sig, tau = lam[nr:nr + n], lam[nr + n:]

    if abs(nu).max() > TOL and mu.max() > TOL and tau.max() > TOL and lam[meq:].min() > -1e-12:
        best = (t, upper, A_ub, b_ub, b_eq, z, nu, mu, sig, tau)
        break

if best is None:
    print("no instance found (eq + ineq + upper)")
else:
    t, upper, A_ub, b_ub, b_eq, z, nu, mu, sig, tau = best
    print("FOUND (equality + ordinary inequality + upper bound all strictly active)")
    print("t     =", t.tolist())
    print("upper =", upper.tolist())
    print("A_ub  =", A_ub.tolist())
    print("b_ub  =", b_ub.tolist())
    print("b_eq  =", b_eq.tolist())
    print("z     =", z.tolist())
    print("nu(eq)      =", nu)
    print("mu(ineq)    =", mu)
    print("sigma(lower)=", sig, "  <-- structurally zero, see the module docstring")
    print("tau(upper)  =", tau)
