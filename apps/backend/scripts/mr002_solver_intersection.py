"""MR-002 v1.1 Stage-3 — CROSS-FAMILY SOLVER INTERSECTION.

THE ONE QUESTION THIS ANSWERS:

    Is there an instance in the immutable 3,895-corpus that NO solver family can certify?

Every characterization so far scored each solver ALONE. None reached the zero-failure gate:

    quadprog family (raw u sqrt u t-scaled)   2 failures
    quadprog + sqrt                           5
    Clarabel                                  9
    PIQP (P2)                                50
    HiGHS (qpasm)                           592

But nobody asked whether the failure SETS overlap. If they are disjoint, a deterministic
cross-family cascade reaches ZERO and Stage-3 qualifies WITHOUT MOSEK, without a licence, and
without redesign. If some instance defeats every family, the difficulty is STRUCTURAL, and
v1.1 is Numerically Unimplementable Before Validation on evidence rather than on a hunch.

GOVERNANCE
  * DIAGNOSTIC ONLY. No performance is computed, printed or persisted. Preflight and the
    development run remain STOPPED. Validation and sealed OOS remain sealed and UNREAD.
  * A solver does not change the optimisation problem -- same feasible set, same optimum. It
    changes only whether the optimum can be CERTIFIED. This is a defect fix, not a change to
    expected performance, and no solver is selected because it produces a preferred answer.
  * The acceptance predicate is byte-identical to the registered one (jp._acceptance + LIMITS).
    A different predicate would make the comparison meaningless.
  * The corpus is re-captured deterministically and verified against the REGISTERED
    corpus_hash 1d2319301a7b52dfe369819bc8029f7b6d64ad820d828f041eba15a91348390b. If the hash
    does not match, this script ABORTS -- we would otherwise be comparing solvers on a
    different problem set than every prior report.

Run inside the pinned research image:
    docker run --rm -v <repo>:/work -v <out>:/out mr002-research:v1.3 \
        python /work/apps/backend/scripts/mr002_solver_intersection.py
"""

from __future__ import annotations

import hashlib
import json
import sys
import warnings
from datetime import date

import numpy as np
import quadprog

sys.path.insert(0, "/work/apps/backend")

import app.research.mr002.joint_portfolio as jp  # noqa: E402

REGISTERED_CORPUS_HASH = (
    "1d2319301a7b52dfe369819bc8029f7b6d64ad820d828f041eba15a91348390b"
)

# The REGISTERED acceptance limits. Do not touch.
LIMITS = {
    "primal_residual": 1e-9,
    "dual_residual": 1e-9,
    "stationarity_residual": 1e-8,
    "complementarity_residual": 1e-8,
    "kkt_residual": 1e-8,
}

CORPUS: list[dict] = []


def _hash_instance(t, A_ub, b_ub, A_eq, b_eq, upper) -> str:
    h = hashlib.sha256()
    for arr in (t, A_ub, b_ub, A_eq, b_eq, upper):
        a = np.ascontiguousarray(np.asarray(arr, dtype=np.float64))
        h.update(str(a.shape).encode())
        h.update(a.tobytes())
    return h.hexdigest()


def failures(checks) -> list[str]:
    return sorted(k for k, lim in LIMITS.items() if checks[k] > lim)


# ======================================================================================
# The solve paths. Each returns (z, checks) in ORIGINAL coordinates, or raises.
# ======================================================================================
def _qp(H, a, C, b, meq):
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        return quadprog.solve_qp(H, a, C, b, meq)


def solve_raw(t, A_ub, b_ub, A_eq, b_eq, upper):
    n = len(t)
    H = np.diag(2.0 / t)
    a = 2.0 * np.ones(n)
    C, b = jp._qp_matrices(A_ub, b_ub, A_eq, b_eq, upper, n)
    meq = A_eq.shape[0]
    out = _qp(H, a, C, b, meq)
    z = np.asarray(out[0], float)
    lam = np.asarray(out[4], float)
    return z, jp._acceptance(z, lam, meq, H, a, C, b, A_ub, b_ub, A_eq, b_eq, upper)


def solve_sqrt(t, A_ub, b_ub, A_eq, b_eq, upper):
    """sqrt-equilibrated: H is EXACTLY 2I by construction."""
    n = len(t)
    H = np.diag(2.0 / t)
    a = 2.0 * np.ones(n)
    C, b = jp._qp_matrices(A_ub, b_ub, A_eq, b_eq, upper, n)
    meq = A_eq.shape[0]

    s = np.sqrt(t)
    S = np.diag(s)
    H_v = 2.0 * np.eye(n)
    a_v = 2.0 * s
    C_v, b_v = jp._qp_matrices(A_ub @ S, b_ub, A_eq @ S, b_eq, s, n)

    out = _qp(H_v, a_v, C_v, b_v, meq)
    v = np.asarray(out[0], float)
    lam_v = np.asarray(out[4], float)
    z = S @ v
    nr = meq + A_ub.shape[0]
    lam_z = lam_v.copy()
    lam_z[nr:nr + n] /= s
    lam_z[nr + n:] /= s
    return z, jp._acceptance(z, lam_z, meq, H, a, C, b, A_ub, b_ub, A_eq, b_eq, upper)


def solve_tscaled(t, A_ub, b_ub, A_eq, b_eq, upper):
    n = len(t)
    H = np.diag(2.0 / t)
    a = 2.0 * np.ones(n)
    C, b = jp._qp_matrices(A_ub, b_ub, A_eq, b_eq, upper, n)
    meq = A_eq.shape[0]

    T = np.diag(t)
    H_u = 2.0 * np.diag(t)
    a_u = 2.0 * t
    C_u, b_u = jp._qp_matrices(A_ub @ T, b_ub, A_eq @ T, b_eq, np.ones(n), n)

    out = _qp(H_u, a_u, C_u, b_u, meq)
    u = np.asarray(out[0], float)
    lam_u = np.asarray(out[4], float)
    z = T @ u
    nr = meq + A_ub.shape[0]
    lam_z = lam_u.copy()
    lam_z[nr:nr + n] /= t
    lam_z[nr + n:] /= t
    return z, jp._acceptance(z, lam_z, meq, H, a, C, b, A_ub, b_ub, A_eq, b_eq, upper)


# THE VALIDATED CLARABEL PATH — imported, NOT re-derived.
#
# I first hand-rolled this and it failed 3,895/3,895 while the registered report has Clarabel
# solving 3,886/3,895. A solver does not go from 9 failures to 3,895; the mapping was mine.
# Two things were wrong: the dual SIGN convention, and the entire regularization/refinement
# configuration (the registered path pins static_regularization_constant, qdldl, presolve off,
# iterative refinement — I used none of it, and there is an owner-approved field-mapping
# amendment on file for exactly this). Re-deriving a validated numeric path is how you
# manufacture a false verdict. So: import it.
from scripts.mr002_characterize_native_qp import solve_clarabel as _clarabel_raw  # noqa: E402


def solve_clarabel(t, A_ub, b_ub, A_eq, b_eq, upper):
    """Validated Clarabel; returns (z, checks) in the registered acceptance form."""
    n = len(t)
    H = np.diag(2.0 / t)
    a = 2.0 * np.ones(n)
    C, b = jp._qp_matrices(A_ub, b_ub, A_eq, b_eq, upper, n)
    meq = A_eq.shape[0]
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        z, lam = _clarabel_raw(t, A_ub, b_ub, A_eq, b_eq, upper)
    if not (np.all(np.isfinite(z)) and np.all(np.isfinite(lam))):
        raise RuntimeError("non-finite primal or dual")
    return z, jp._acceptance(z, lam, meq, H, a, C, b, A_ub, b_ub, A_eq, b_eq, upper)


def solve_highs(t, A_ub, b_ub, A_eq, b_eq, upper):
    """Validated HiGHS (qpasm); same registered acceptance form."""
    from scripts.mr002_characterize_native_qp import solve_highs as _highs_raw
    n = len(t)
    H = np.diag(2.0 / t)
    a = 2.0 * np.ones(n)
    C, b = jp._qp_matrices(A_ub, b_ub, A_eq, b_eq, upper, n)
    meq = A_eq.shape[0]
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        z, lam = _highs_raw(t, A_ub, b_ub, A_eq, b_eq, upper)
    if not (np.all(np.isfinite(z)) and np.all(np.isfinite(lam))):
        raise RuntimeError("non-finite primal or dual")
    return z, jp._acceptance(z, lam, meq, H, a, C, b, A_ub, b_ub, A_eq, b_eq, upper)


# PIQP — proximal INTERIOR-POINT. The only fallback candidate that is algorithmically
# independent of quadprog (Goldfarb-Idnani active-set). HiGHS qpasm is ALSO active-set, so a
# quadprog->HiGHS cascade pairs two solvers of the same family — and the mode that kills the
# square-root path (false infeasibility: "constraints are inconsistent") is the characteristic
# active-set breakdown, which HiGHS itself exhibits 25 times. Imported, never re-derived.
from scripts.mr002_piqp import solve_piqp as _piqp_raw  # noqa: E402


def _piqp(scale_cost):
    def solve(t, A_ub, b_ub, A_eq, b_eq, upper):
        n = len(t)
        H = np.diag(2.0 / t)
        a = 2.0 * np.ones(n)
        C, b = jp._qp_matrices(A_ub, b_ub, A_eq, b_eq, upper, n)
        meq = A_eq.shape[0]
        with warnings.catch_warnings():
            warnings.simplefilter("error")
            z, lam = _piqp_raw(scale_cost, t, A_ub, b_ub, A_eq, b_eq, upper)
        if not (np.all(np.isfinite(z)) and np.all(np.isfinite(lam))):
            raise RuntimeError("non-finite primal or dual")
        return z, jp._acceptance(z, lam, meq, H, a, C, b, A_ub, b_ub, A_eq, b_eq, upper)
    return solve


SOLVERS = (
    ("QUADPROG_RAW", solve_raw),
    ("QUADPROG_SQRT", solve_sqrt),
    ("QUADPROG_TSCALED", solve_tscaled),
    ("CLARABEL", solve_clarabel),
    ("HIGHS_QPASM", solve_highs),
    ("PIQP_P1", _piqp(False)),
    ("PIQP_P2", _piqp(True)),
)


# ======================================================================================
# PHASE 1 — re-capture the immutable corpus (identical device to the registered runs)
# ======================================================================================
def capture_solver(H_diag, targets, A_ub, b_ub, A_eq, b_eq, upper):
    t = np.asarray(targets, float)
    CORPUS.append({
        "t": t.copy(), "A_ub": A_ub.copy(), "b_ub": b_ub.copy(),
        "A_eq": A_eq.copy(), "b_eq": b_eq.copy(),
        "upper": np.asarray(upper, float).copy(),
        "hash": _hash_instance(t, A_ub, b_ub, A_eq, b_eq, upper),
    })
    for fn in (solve_raw, solve_sqrt, solve_tscaled):
        try:
            z, ck = fn(t, A_ub, b_ub, A_eq, b_eq, upper)
            if not failures(ck):
                return z, dict(ck, stage3_formulation="CAPTURE",
                               hessian_condition_number=1.0, qp_iterations=[0, 0])
        except ValueError:
            continue

    from scipy.optimize import linprog
    n = len(t)
    f = linprog(c=np.zeros(n), A_ub=A_ub, b_ub=b_ub, A_eq=A_eq, b_eq=b_eq,
                bounds=[(0.0, float(u)) for u in upper], method="highs-ds",
                options=jp.LP_OPTIONS)
    if not f.success:
        raise jp.InvalidRun("capture: no formulation solved and the region is infeasible")
    z = np.asarray(f.x, float)
    H = np.diag(2.0 / t)
    a = 2.0 * np.ones(n)
    C, b = jp._qp_matrices(A_ub, b_ub, A_eq, b_eq, upper, n)
    ck = jp._acceptance(z, np.zeros(C.shape[1]), A_eq.shape[0], H, a, C, b,
                        A_ub, b_ub, A_eq, b_eq, upper)
    return z, dict(ck, stage3_formulation="DIAGNOSTIC_FALLBACK",
                   hessian_condition_number=1.0, qp_iterations=[0, 0])


def main() -> int:
    jp._solve_qp = capture_solver

    from app.research.mr002.dataset import FrozenDataset
    from app.research.mr002.runner import CONFIGS
    from scripts.mr002_development_run import run_config

    ds = FrozenDataset("/work/apps/backend/data/mr002_research.duckdb")
    days = ds.day_inputs(date(2013, 1, 2), date(2019, 10, 2))
    print("PHASE 1 — re-capture the immutable corpus", flush=True)
    for name in ("A", "B", "C"):
        print(f"  config {name} ...", flush=True)
        run_config(days, CONFIGS[name])

    n_inst = len(CORPUS)
    corpus_hash = hashlib.sha256(
        "|".join(i["hash"] for i in CORPUS).encode()).hexdigest()
    print(f"  captured {n_inst} instances")
    print(f"  corpus hash   {corpus_hash}")
    print(f"  registered    {REGISTERED_CORPUS_HASH}")
    if corpus_hash != REGISTERED_CORPUS_HASH:
        print("\nABORT: corpus hash MISMATCH. Every prior solver report was scored on a "
              "different problem set; an intersection computed here would be meaningless.",
              file=sys.stderr)
        return 1
    print("  ✓ corpus reproduced EXACTLY — the comparison is sound", flush=True)

    # ==================================================================================
    # PHASE 2 — per-instance failure SETS, on immutable copies
    # ==================================================================================
    print("\nPHASE 2 — per-instance failure sets", flush=True)
    fail_sets: dict[str, set[int]] = {name: set() for name, _ in SOLVERS}
    reasons: dict[str, dict[int, str]] = {name: {} for name, _ in SOLVERS}

    for i, inst in enumerate(CORPUS):
        rec = (inst["t"], inst["A_ub"], inst["b_ub"],
               inst["A_eq"], inst["b_eq"], inst["upper"])
        for name, fn in SOLVERS:
            try:
                _z, ck = fn(*(x.copy() for x in rec))
                bad = failures(ck)
                if bad:
                    fail_sets[name].add(i)
                    reasons[name][i] = "+".join(bad)
            except Exception as e:  # noqa: BLE001 — a raise IS a failure
                fail_sets[name].add(i)
                reasons[name][i] = f"{type(e).__name__}: {str(e)[:70]}"
        if (i + 1) % 500 == 0:
            print(f"  {i+1}/{n_inst}", flush=True)

    for name, _ in SOLVERS:
        print(f"  {name:18} failures: {len(fail_sets[name]):4}")

    # ==================================================================================
    # PHASE 3 — THE ANSWER
    # ==================================================================================
    # ONE predicate for every solver: the REGISTERED production acceptance
    # (jp._acceptance + LIMITS). The two prior characterizers used DIFFERENT predicates — the
    # native-QP one adds an external primal-dual gap gate, the quadprog one does not — so their
    # headline counts are not directly comparable, and an intersection across mismatched
    # predicates would be meaningless. Scored uniformly here.
    quadprog_family = (
        fail_sets["QUADPROG_RAW"]
        & fail_sets["QUADPROG_SQRT"]
        & fail_sets["QUADPROG_TSCALED"]
    )
    all_families = (quadprog_family & fail_sets["CLARABEL"] & fail_sets["HIGHS_QPASM"]
                    & fail_sets["PIQP_P1"] & fail_sets["PIQP_P2"])

    print("\n" + "=" * 74)
    print(f"  quadprog family (raw ∩ sqrt ∩ t-scaled) unsolved : {len(quadprog_family)}")
    print(f"    -> instances: {sorted(quadprog_family)}")
    print(f"  Clarabel unsolved                                : "
          f"{len(fail_sets['CLARABEL'])}")
    print(f"  HiGHS unsolved                                   : "
          f"{len(fail_sets['HIGHS_QPASM'])}")
    print(f"  PIQP P1 unsolved                                 : {len(fail_sets['PIQP_P1'])}")
    print(f"  PIQP P2 unsolved                                 : {len(fail_sets['PIQP_P2'])}")
    print("")
    print("  --- 2-solver cascades from QUADPROG_SQRT (ZERO = qualifies) ---")
    for cand in ("HIGHS_QPASM", "CLARABEL", "PIQP_P1", "PIQP_P2"):
        left = fail_sets["QUADPROG_SQRT"] & fail_sets[cand]
        print(f"    SQRT -> {cand:12} unresolved: {len(left):3}   "
              f"(fallback own failure rate {len(fail_sets[cand])/n_inst*100:5.2f}%)")
    print(f"  UNSOLVED BY EVERY FAMILY                         : {len(all_families)}")
    print(f"    -> instances: {sorted(all_families)}")
    print("=" * 74)

    if not all_families:
        print("\n*** VERDICT: the union COVERS the corpus. ***")
        print("A deterministic cross-family cascade reaches ZERO Stage-3 failures.")
        print("Stage 3 is implementable WITHOUT MOSEK. Returning for adjudication:")
        print("the cascade order and tolerances must be REGISTERED before use.")
    else:
        print("\n*** VERDICT: at least one instance defeats EVERY solver family. ***")
        print("The difficulty is STRUCTURAL, not solver-specific. No further solver will")
        print("close it. v1.1 should close as Numerically Unimplementable Before")
        print("Validation, and Stage 3 be reformulated in a v1.2 design process.")

    out = {
        "instances": n_inst,
        "corpus_hash": corpus_hash,
        "corpus_verified": True,
        "acceptance_limits": LIMITS,
        "failures_per_solver": {k: sorted(v) for k, v in fail_sets.items()},
        "failure_reasons": {k: {str(i): r for i, r in v.items()}
                            for k, v in reasons.items()},
        "quadprog_family_unsolved": sorted(quadprog_family),
        "unsolved_by_every_family": sorted(all_families),
        "union_covers_corpus": not all_families,
        "no_performance_computed": True,
    }
    with open("/out/MR002_SolverIntersection.json", "w", encoding="utf-8") as fh:
        json.dump(out, fh, indent=2)
    print("\nwrote /out/MR002_SolverIntersection.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
