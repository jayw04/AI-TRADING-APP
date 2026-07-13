"""MR-002 v1.1 — NATIVE HiGHS-QP and CLARABEL CHARACTERIZATION.

Authorized 2026-07-12 (quadprog retired). OFFLINE, IMMUTABLE-CORPUS CHARACTERIZATION ONLY.
No performance is computed. Preflight and development run remain stopped.

Canonical MR-002 Stage-3 problem, in ORIGINAL coordinates:

    minimize  D(z) = sum_i (z_i - t_i)^2 / t_i
                   = (1/2) z' P z + q' z + const ,   P = diag(2/t) ,  q = -2 * 1
    s.t.      A_ub z <= b_ub          (homogeneous coupling + lexicographic bands)
              A_eq z  = b_eq          (new-entry dollar neutrality)
              0 <= z <= upper

Canonical multiplier convention (the one the registered acceptance battery uses):

    grad D = P z + q = H z - a          (H = P, a = -q = 2*1)
    C = [A_eq ; -A_ub ; I ; -I]'   and   H z - a - C.lam = 0
    => lam = [ nu_eq ; lam_ineq >= 0 ; lam_lo >= 0 ; lam_hi >= 0 ]

Each candidate's native duals are mapped into that convention and then judged by the
UNCHANGED registered battery. No native dual certificate is ever reconstructed from another
solver.
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
import warnings
from collections import Counter

import numpy as np
import scipy.sparse as sp

sys.path.insert(0, "/work/apps/backend")

import app.research.mr002.joint_portfolio as jp  # noqa: E402

LIMITS = {
    "primal_residual": 1e-9, "dual_residual": 1e-9,
    "stationarity_residual": 1e-8, "complementarity_residual": 1e-8,
    "kkt_residual": 1e-8,
}
AGREE = 1e-8
TOL = 1e-10
TIME_LIMIT = 60.0

CORPUS_NPZ = "/out/MR002_Stage3_Corpus.npz"
CORPUS_HASHES = "/out/MR002_Stage3_Corpus_Hashes.json"
SIDECAR = "/out/MR002_Stage3_Corpus_Symbolic.jsonl"


def _hash_instance(t, A_ub, b_ub, A_eq, b_eq, upper) -> str:
    h = hashlib.sha256()
    for arr in (t, A_ub, b_ub, A_eq, b_eq, upper):
        a = np.ascontiguousarray(np.asarray(arr, dtype=np.float64))
        h.update(str(a.shape).encode())
        h.update(a.tobytes())
    return h.hexdigest()


# ======================================================================================
# CANDIDATE A — native HiGHS QP (qpasm)
# ======================================================================================
def solve_highs(t, A_ub, b_ub, A_eq, b_eq, upper):
    import highspy

    n = len(t)
    m_ub, meq = A_ub.shape[0], A_eq.shape[0]
    h = highspy.Highs()
    for k, v in (("output_flag", False), ("solver", "qpasm"), ("threads", 1),
                 ("parallel", "off"), ("presolve", "off")):
        h.setOptionValue(k, v)
    h.setOptionValue("random_seed", 0)
    for k in ("kkt_tolerance", "primal_feasibility_tolerance",
              "dual_feasibility_tolerance", "primal_residual_tolerance",
              "dual_residual_tolerance", "optimality_tolerance"):
        h.setOptionValue(k, TOL)
    h.setOptionValue("small_matrix_value", 1e-12)
    h.setOptionValue("time_limit", TIME_LIMIT)

    inf = highspy.kHighsInf
    A = np.vstack([A_eq, A_ub]) if m_ub else A_eq
    row_lo = np.concatenate([b_eq, np.full(m_ub, -inf)])
    row_hi = np.concatenate([b_eq, b_ub])

    lp = highspy.HighsLp()
    lp.num_col_ = n
    lp.num_row_ = A.shape[0]
    lp.col_cost_ = -2.0 * np.ones(n)                     # q
    lp.col_lower_ = np.zeros(n)
    lp.col_upper_ = np.asarray(upper, float)
    lp.row_lower_ = row_lo
    lp.row_upper_ = row_hi
    S = sp.csr_matrix(A)
    lp.a_matrix_.format_ = highspy.MatrixFormat.kRowwise
    lp.a_matrix_.start_ = S.indptr.tolist()
    lp.a_matrix_.index_ = S.indices.tolist()
    lp.a_matrix_.value_ = S.data.tolist()

    hess = highspy.HighsHessian()                        # P = diag(2/t), UPPER triangle
    hess.dim_ = n
    hess.format_ = highspy.HessianFormat.kTriangular
    hess.start_ = list(range(n + 1))
    hess.index_ = list(range(n))
    hess.value_ = (2.0 / t).tolist()

    model = highspy.HighsModel()
    model.lp_ = lp
    model.hessian_ = hess
    st = h.passModel(model)
    if str(st) != "HighsStatus.kOk":
        raise RuntimeError(f"passModel status {st}")
    st = h.run()
    if str(st) != "HighsStatus.kOk":
        raise RuntimeError(f"run status {st}")
    ms = h.getModelStatus()
    if "kOptimal" not in str(ms):
        raise RuntimeError(f"model status {ms}")

    sol = h.getSolution()
    z = np.asarray(sol.col_value, float)
    row_dual = np.asarray(sol.row_dual, float)
    col_dual = np.asarray(sol.col_dual, float)

    # ---- map native duals into the canonical convention ------------------------------
    # HiGHS (minimization): grad + A' y_row + y_col = 0, with y_col the reduced cost.
    #   => H z - a = -A' y_row - y_col
    # canonical: H z - a = A_eq' nu - A_ub' lam_ineq + lam_lo - lam_hi
    #   => nu = -y_row[:meq] ; lam_ineq = y_row[meq:]  (>=0 for an active <= row)
    #      lam_lo = max(-y_col, 0) ; lam_hi = max(y_col, 0)
    nu = -row_dual[:meq]
    lam_ineq = row_dual[meq:]
    lam_lo = np.maximum(-col_dual, 0.0)
    lam_hi = np.maximum(col_dual, 0.0)
    lam = np.concatenate([nu, lam_ineq, lam_lo, lam_hi])
    return z, lam


# ======================================================================================
# CANDIDATE B — native Clarabel
# ======================================================================================
def solve_clarabel(t, A_ub, b_ub, A_eq, b_eq, upper):
    import clarabel

    n = len(t)
    m_ub, meq = A_ub.shape[0], A_eq.shape[0]
    P = sp.csc_matrix(np.diag(2.0 / t))
    q = -2.0 * np.ones(n)
    A = sp.csc_matrix(np.vstack([A_eq, A_ub, -np.eye(n), np.eye(n)]))
    b = np.concatenate([b_eq, b_ub, np.zeros(n), np.asarray(upper, float)])
    cones = [clarabel.ZeroConeT(meq), clarabel.NonnegativeConeT(m_ub + 2 * n)]

    s = clarabel.DefaultSettings()
    s.max_threads = 1
    s.max_iter = 500
    s.time_limit = TIME_LIMIT
    s.verbose = False
    s.tol_gap_abs = TOL
    s.tol_gap_rel = TOL
    s.tol_feas = TOL
    s.tol_infeas_abs = TOL
    s.tol_infeas_rel = TOL
    s.equilibrate_enable = True
    s.presolve_enable = False
    s.direct_kkt_solver = True
    s.direct_solve_method = "qdldl"
    s.static_regularization_enable = True
    s.dynamic_regularization_enable = True
    s.iterative_refinement_enable = True

    sol = clarabel.DefaultSolver(P, q, A, b, cones, s).solve()
    if str(sol.status) != "Solved":
        raise RuntimeError(f"clarabel status {sol.status}")

    z = np.asarray(sol.x, float)
    y = np.asarray(sol.z, float)                          # cone duals
    # Clarabel: P x + q + A' y = 0  =>  H z - a = -A' y
    # canonical: H z - a = A_eq' nu - A_ub' lam_ineq + lam_lo - lam_hi
    #   A = [A_eq ; A_ub ; -I ; I]
    #   -A'y = -A_eq' y_eq - A_ub' y_ub + y_lo - y_hi
    #   => nu = -y_eq ; lam_ineq = y_ub ; lam_lo = y_lo ; lam_hi = y_hi
    nu = -y[:meq]
    lam_ineq = y[meq:meq + m_ub]
    lam_lo = y[meq + m_ub:meq + m_ub + n]
    lam_hi = y[meq + m_ub + n:]
    lam = np.concatenate([nu, lam_ineq, lam_lo, lam_hi])
    return z, lam


# ======================================================================================
def evaluate(name, fn, t, A_ub, b_ub, A_eq, b_eq, upper):
    n = len(t)
    H = np.diag(2.0 / t)
    a = 2.0 * np.ones(n)
    C, b = jp._qp_matrices(A_ub, b_ub, A_eq, b_eq, upper, n)
    meq = A_eq.shape[0]
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        z, lam = fn(t, A_ub, b_ub, A_eq, b_eq, upper)
    if not (np.all(np.isfinite(z)) and np.all(np.isfinite(lam))):
        raise RuntimeError("non-finite primal or dual")
    ck = jp._acceptance(z, lam, meq, H, a, C, b, A_ub, b_ub, A_eq, b_eq, upper)
    bad = sorted(k for k, lim in LIMITS.items() if ck[k] > lim)
    return z, ck, bad


def main() -> int:
    # ---- corpus verification (immutable; the code cannot mutate it) --------------------
    with open(CORPUS_HASHES, encoding="utf-8") as fh:
        H = json.load(fh)
    npz = np.load(CORPUS_NPZ)
    N = len(H["instance_hashes"])
    side = {}
    with open(SIDECAR, encoding="utf-8") as fh:
        for line in fh:
            r = json.loads(line)
            side[r["instance_hash"]] = r

    print(f"corpus: {N} instances")
    ok_hash, ok_link = 0, 0
    inst = []
    for i in range(N):
        t = npz[f"{i}_t"]
        A_ub, b_ub = npz[f"{i}_A_ub"], npz[f"{i}_b_ub"]
        A_eq, b_eq = npz[f"{i}_A_eq"], npz[f"{i}_b_eq"]
        upper = npz[f"{i}_upper"]
        hh = _hash_instance(t, A_ub, b_ub, A_eq, b_eq, upper)
        if hh == H["instance_hashes"][i]:
            ok_hash += 1
        if hh in side:
            ok_link += 1
        inst.append((t, A_ub, b_ub, A_eq, b_eq, upper))
    corpus_hash = hashlib.sha256(
        "|".join(H["instance_hashes"]).encode()).hexdigest()
    print(f"  global corpus hash matches : {corpus_hash == H['corpus_hash']}")
    print(f"  per-instance hashes match  : {ok_hash}/{N}")
    print(f"  symbolic sidecar linkage   : {ok_link}/{N}")
    if not (corpus_hash == H["corpus_hash"] and ok_hash == N == ok_link == N):
        print("CORPUS VERIFICATION FAILED", file=sys.stderr)
        return 1

    R = {"instances": N, "corpus_hash": corpus_hash,
         "corpus_verified": True, "candidates": {}}
    prim = {}

    for name, fn in (("HIGHS_QPASM", solve_highs), ("CLARABEL", solve_clarabel)):
        print(f"\n=== {name} ===", flush=True)
        c = {"solved": 0, "failed": 0, "failure_kinds": Counter(),
             "worst_kkt": 0.0, "worst_stationarity": 0.0, "worst_primal": 0.0}
        zs = {}
        for i, (t, A_ub, b_ub, A_eq, b_eq, upper) in enumerate(inst):
            try:
                z, ck, bad = evaluate(name, fn, t.copy(), A_ub.copy(), b_ub.copy(),
                                      A_eq.copy(), b_eq.copy(), upper.copy())
                if bad:
                    c["failed"] += 1
                    c["failure_kinds"]["+".join(bad)] += 1
                else:
                    c["solved"] += 1
                    zs[i] = z
                c["worst_kkt"] = max(c["worst_kkt"], ck["kkt_residual"])
                c["worst_stationarity"] = max(c["worst_stationarity"],
                                              ck["stationarity_residual"])
                c["worst_primal"] = max(c["worst_primal"], ck["primal_residual"])
            except Exception as e:
                c["failed"] += 1
                c["failure_kinds"][f"{type(e).__name__}:{str(e)[:70]}"] += 1
            if (i + 1) % 500 == 0:
                print(f"  {i+1}/{N}  solved={c['solved']} failed={c['failed']}", flush=True)
        c["failure_kinds"] = dict(c["failure_kinds"])
        R["candidates"][name] = c
        prim[name] = zs
        print(f"  SOLVED {c['solved']}/{N}   FAILED {c['failed']}")
        print(f"  worst KKT {c['worst_kkt']:.3e} | stationarity {c['worst_stationarity']:.3e}")

    # ---- candidate-to-candidate agreement ---------------------------------------------
    both = set(prim["HIGHS_QPASM"]) & set(prim["CLARABEL"])
    dz = max((float(np.max(np.abs(prim["HIGHS_QPASM"][i] - prim["CLARABEL"][i])))
              for i in both), default=0.0)
    dobj = 0.0
    for i in both:
        t = inst[i][0]
        o1 = float(np.sum((prim["HIGHS_QPASM"][i] - t) ** 2 / t))
        o2 = float(np.sum((prim["CLARABEL"][i] - t) ** 2 / t))
        dobj = max(dobj, abs(o1 - o2))
    R["candidate_agreement"] = {
        "instances_both_solved": len(both),
        "max_primal_disagreement": dz,
        "max_objective_disagreement": dobj,
        "within_1e-8": dz <= AGREE and dobj <= AGREE,
    }

    R["gates"] = {
        "highs_solves_all": R["candidates"]["HIGHS_QPASM"]["failed"] == 0,
        "clarabel_solves_all": R["candidates"]["CLARABEL"]["failed"] == 0,
        "candidates_agree_within_1e-8": R["candidate_agreement"]["within_1e-8"],
    }
    q = [k for k, v in (("HIGHS_QPASM", R["gates"]["highs_solves_all"]),
                        ("CLARABEL", R["gates"]["clarabel_solves_all"])) if v]
    R["qualified"] = q
    R["selection"] = ("HIGHS_QPASM (precedence: already the registered LP technology)"
                      if "HIGHS_QPASM" in q else
                      ("CLARABEL" if "CLARABEL" in q else "NEITHER — STOP FOR ADJUDICATION"))
    R["VERDICT"] = "PASS" if q else "FAIL"

    dst = "/out/MR002_NativeQP_Characterization.json"
    with open(dst, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(R, fh, indent=2, default=str)
        fh.write("\n")
    print("\n" + json.dumps({k: R[k] for k in
          ("candidates", "candidate_agreement", "gates", "qualified", "selection",
           "VERDICT")}, indent=2, default=str))
    print(f"\nreport: {dst}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
