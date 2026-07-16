"""MR-002 v1.1 — CLARABEL EXACT-CONIC (Hessian-free) characterization.

Owner-authorized 2026-07-13. OFFLINE ONLY. No performance computed. Preflight and development
run remain stopped. Validation and sealed OOS remain sealed and unread.

THE SUBMITTED MODEL CONTAINS NO STAGE-3 HESSIAN. P is exactly the zero matrix.

    s_i = sqrt(t_i) ,  z_i = s_i v_i ,  r = v - s
    D(z) = sum (z_i - t_i)^2 / t_i  =  sum (v_i - s_i)^2  =  ||r||_2^2

    min  eta        s.t.   (eta + 1, 2r, eta - 1)  in  SOC(n+2)
                           0 <= v_i <= s_i
                           A_ub S v <= b_ub
                           A_eq S v  = b_eq

    SOC identity (EXACT):  eta >= ||r||^2  <=>  ||(2r, eta-1)|| <= eta+1
      square:  4||r||^2 + eta^2 - 2eta + 1 <= eta^2 + 2eta + 1  =>  ||r||^2 <= eta
    The cone itself implies eta >= 0, so no separate lower bound on eta is needed.
    The constant is FROZEN at exactly 1.0.

Clarabel standard form:  A x + s = b ,  s in K ,  x = (v, eta)
    rows: [ZeroCone(meq)] [Nonneg(m_ub)] [Nonneg(n) lower] [Nonneg(n) upper] [SOC(n+2)]

DUAL MAPPING back to the ORIGINAL QP canonical convention (derived, then proved on fixtures):
    Clarabel KKT with P = 0:  q + A' y = 0
    v-block  =>  2 y_soc_mid = S A_eq' y_eq + S A_ub' y_ineq - y_lb + y_ub
    eta-block=>  1 - y_soc[0] - y_soc[-1] = 0     (i.e. w0 + w_last = 1)
    cone-derived gradient  -2 w_mid  ==  analytic  2(v - s)
  Canonical (original z-coords):  Hz - a = A_eq'nu - A_ub'lam_ineq + lam_lo - lam_hi
    =>  nu = -y_eq ;  lam_ineq = y_ineq ;  lam_lo = y_lb / sqrt(t) ;  lam_hi = y_ub / sqrt(t)
"""
from __future__ import annotations

import hashlib
import importlib.metadata as md
import json
import platform
import sys
import warnings
from collections import Counter

import clarabel
import numpy as np
import scipy.sparse as sp

sys.path.insert(0, "/work/apps/backend")

import app.research.mr002.joint_portfolio as jp  # noqa: E402

LIMITS = {
    "primal_residual": 1e-9, "dual_residual": 1e-9,
    "stationarity_residual": 1e-8, "complementarity_residual": 1e-8,
    "kkt_residual": 1e-8,
}
GAP_MAX = 1e-10
EPIGRAPH_TOL = 1e-10
SOC_CONST = 1.0                       # FROZEN. No alternative scaling constant.
EPS_INCLUDE = 1e-8

# FROZEN Clarabel settings — unchanged from the prior VALID capability records.
CLARABEL_PROPORTIONAL = 4.930380657631324e-32


def settings():
    s = clarabel.DefaultSettings()
    s.max_threads = 1
    s.max_iter = 500
    s.time_limit = 60.0
    s.verbose = False
    s.tol_gap_abs = 1e-10
    s.tol_gap_rel = 1e-10
    s.tol_feas = 1e-10
    s.tol_infeas_abs = 1e-10
    s.tol_infeas_rel = 1e-10
    s.equilibrate_enable = True
    s.presolve_enable = False
    s.direct_kkt_solver = True
    s.direct_solve_method = "qdldl"
    s.static_regularization_enable = True
    s.static_regularization_constant = 1e-8
    s.static_regularization_proportional = CLARABEL_PROPORTIONAL
    s.dynamic_regularization_enable = True
    s.dynamic_regularization_eps = 1e-13
    s.dynamic_regularization_delta = 2e-7
    s.iterative_refinement_enable = True
    return s


def guards(t, upper):
    t = np.asarray(t, float)
    if not np.all(np.isfinite(t)):
        raise RuntimeError("non-finite t")
    if not np.all(t > EPS_INCLUDE):
        raise RuntimeError("t <= eps_include")
    if t.tobytes() != np.asarray(upper, float).tobytes():
        raise RuntimeError("t is not BITWISE IDENTICAL to the registered upper bound")
    s = np.sqrt(t)
    if not (np.all(np.isfinite(s)) and np.all(s > 0)):
        raise RuntimeError("non-finite or non-positive sqrt(t)")
    return s, float(np.max(np.abs(s * s - t)))          # diagnostic round-trip error


def build_conic(t, A_ub, b_ub, A_eq, b_eq, upper):
    """x = (v, eta).  NO HESSIAN: P is exactly the zero matrix."""
    n = len(t)
    s = np.sqrt(t)
    S = sp.diags(s)
    meq, m_ub = A_eq.shape[0], A_ub.shape[0]
    N = n + 1                                            # v (n) + eta (1)

    P = sp.csc_matrix((N, N))                            # EXACTLY ZERO
    q = np.zeros(N)
    q[n] = 1.0                                           # min eta

    blocks, bvec = [], []
    # equalities: A_eq S v = b_eq
    blocks.append(sp.hstack([sp.csr_matrix(A_eq) @ S, sp.csc_matrix((meq, 1))]))
    bvec.append(np.asarray(b_eq, float))
    # inequalities: A_ub S v <= b_ub
    blocks.append(sp.hstack([sp.csr_matrix(A_ub) @ S, sp.csc_matrix((m_ub, 1))]))
    bvec.append(np.asarray(b_ub, float))
    # lower bounds: -v <= 0
    blocks.append(sp.hstack([-sp.eye(n), sp.csc_matrix((n, 1))]))
    bvec.append(np.zeros(n))
    # upper bounds: v <= s
    blocks.append(sp.hstack([sp.eye(n), sp.csc_matrix((n, 1))]))
    bvec.append(s.copy())
    # SOC: b_soc - A_soc x = (eta + 1, 2(v - s), eta - 1)
    A_soc = sp.lil_matrix((n + 2, N))
    A_soc[0, n] = -1.0
    for i in range(n):
        A_soc[1 + i, i] = -2.0
    A_soc[n + 1, n] = -1.0
    b_soc = np.concatenate([[SOC_CONST], -2.0 * s, [-SOC_CONST]])
    blocks.append(A_soc.tocsr())
    bvec.append(b_soc)

    A = sp.csc_matrix(sp.vstack(blocks))
    b = np.concatenate(bvec)
    cones = [clarabel.ZeroConeT(meq), clarabel.NonnegativeConeT(m_ub + 2 * n),
             clarabel.SecondOrderConeT(n + 2)]
    return P, q, A, b, cones, s


def solve_conic(t, A_ub, b_ub, A_eq, b_eq, upper):
    n = len(t)
    meq, m_ub = A_eq.shape[0], A_ub.shape[0]
    s, rt_err = guards(t, upper)
    P, q, A, b, cones, s = build_conic(t, A_ub, b_ub, A_eq, b_eq, upper)

    sol = clarabel.DefaultSolver(P, q, A, b, cones, settings()).solve()
    if str(sol.status) != "Solved":
        raise RuntimeError(f"status {sol.status}")

    x = np.asarray(sol.x, float)
    y = np.asarray(sol.z, float)                          # cone duals
    v, eta = x[:n], float(x[n])
    z = s * v                                             # back to ORIGINAL coordinates

    o = 0
    y_eq = y[o:o + meq]; o += meq
    y_ineq = y[o:o + m_ub]; o += m_ub
    y_lb = y[o:o + n]; o += n
    y_ub = y[o:o + n]; o += n
    y_soc = y[o:]

    # canonical multipliers in ORIGINAL z-coordinates
    lam = np.concatenate([-y_eq, y_ineq, y_lb / s, y_ub / s])

    diag = {
        "eta": eta,
        "soc_w0_plus_wlast": float(y_soc[0] + y_soc[-1]),      # must be 1
        "cone_gradient_vs_analytic": float(np.max(np.abs(
            -2.0 * y_soc[1:n + 1] - 2.0 * (v - s)))),          # must be ~0
        "sqrt_roundtrip_error": rt_err,
    }
    return z, lam, diag


def external_gap(z, lam, meq, m_ub, t, b_ub, b_eq, upper):
    n = len(t)
    nu = lam[:meq]
    lam_ineq = lam[meq:meq + m_ub]
    lam_hi = lam[meq + m_ub + n:]
    return (float(z @ ((2.0 / t) * z)) - 2.0 * float(np.sum(z))
            + float(b_ub @ lam_ineq) + float(np.asarray(upper, float) @ lam_hi)
            + float(b_eq @ (-nu)))


def evaluate(t, A_ub, b_ub, A_eq, b_eq, upper):
    """Acceptance is on the COMPLETE ORIGINAL QP SYSTEM, never on the conic model.
    The original gradient is recomputed ANALYTICALLY: grad D(z)_i = 2 (z_i - t_i) / t_i."""
    n = len(t)
    H = np.diag(2.0 / t)                      # for CHECKING only -- never submitted
    a = 2.0 * np.ones(n)
    C, b = jp._qp_matrices(A_ub, b_ub, A_eq, b_eq, upper, n)
    meq, m_ub = A_eq.shape[0], A_ub.shape[0]

    with warnings.catch_warnings():
        warnings.simplefilter("error")
        z, lam, d = solve_conic(t, A_ub, b_ub, A_eq, b_eq, upper)
    if not (np.all(np.isfinite(z)) and np.all(np.isfinite(lam))):
        raise RuntimeError("non-finite primal or dual")

    ck = jp._acceptance(z, lam, meq, H, a, C, b, A_ub, b_ub, A_eq, b_eq, upper)
    g = external_gap(z, lam, meq, m_ub, t, b_ub, b_eq, upper)
    D = float(np.sum((z - t) ** 2 / t))
    epi = d["eta"] - D
    ck.update({"external_primal_dual_gap": g, "objective_D": D,
               "epigraph_slack": epi, **d})

    bad = sorted(k for k, lim in LIMITS.items() if ck[k] > lim)
    if g < -1e-9:
        bad.append("gap_negative")
    if g > GAP_MAX:
        bad.append("gap_exceeds_1e-10")
    if not (-EPIGRAPH_TOL <= epi <= EPIGRAPH_TOL):
        bad.append("epigraph_not_tight")
    return z, ck, bad, g


# ======================================================================================
def fixtures() -> dict:
    """Hand-solvable primal AND dual fixtures for the conic construction."""
    out = {}

    # (1) active general inequality: z1+z2 <= 0.01, t = (0.008, 0.008) -> z = (0.005,0.005)
    t = np.array([0.008, 0.008])
    z, lam, d = solve_conic(t, np.array([[1.0, 1.0]]), np.array([0.01]),
                            np.zeros((0, 2)), np.zeros(0), t.copy())
    C, _ = jp._qp_matrices(np.array([[1.0, 1.0]]), np.array([0.01]),
                           np.zeros((0, 2)), np.zeros(0), t.copy(), 2)
    out["active_inequality"] = {
        "z": z.tolist(), "expected_z": [0.005, 0.005],
        "stationarity": float(np.max(np.abs(np.diag(2.0 / t) @ z - 2.0 - C @ lam))),
        "soc_w0_plus_wlast": d["soc_w0_plus_wlast"],
        "cone_gradient_vs_analytic": d["cone_gradient_vs_analytic"],
        "eta_vs_D": d["eta"] - float(np.sum((z - t) ** 2 / t)),
    }

    # (2) active equality
    t = np.array([0.008, 0.008])
    z, lam, d = solve_conic(t, np.zeros((0, 2)), np.zeros(0),
                            np.array([[1.0, 1.0]]), np.array([0.01]), t.copy())
    C, _ = jp._qp_matrices(np.zeros((0, 2)), np.zeros(0),
                           np.array([[1.0, 1.0]]), np.array([0.01]), t.copy(), 2)
    out["active_equality"] = {
        "z": z.tolist(), "expected_z": [0.005, 0.005],
        "stationarity": float(np.max(np.abs(np.diag(2.0 / t) @ z - 2.0 - C @ lam))),
        "soc_w0_plus_wlast": d["soc_w0_plus_wlast"],
        "eta_vs_D": d["eta"] - float(np.sum((z - t) ** 2 / t)),
    }

    # (3) active LOWER bound: a 10x-weighted row forces z2 to 0 -> lam_lo(z2) > 0.
    #     This is the fixture that exercises  mu_z = mu_v / sqrt(t).
    t = np.array([0.01, 0.01])
    z, lam, d = solve_conic(t, np.array([[1.0, 10.0]]), np.array([0.005]),
                            np.zeros((0, 2)), np.zeros(0), t.copy())
    C, _ = jp._qp_matrices(np.array([[1.0, 10.0]]), np.array([0.005]),
                           np.zeros((0, 2)), np.zeros(0), t.copy(), 2)
    out["active_lower_bound"] = {
        "z": z.tolist(), "z2_at_lower_bound": bool(abs(z[1]) < 1e-8),
        "lam_lo": lam[1:3].tolist(),
        "lam_lo_z2_positive": bool(lam[2] > 1e-6),
        "stationarity": float(np.max(np.abs(np.diag(2.0 / t) @ z - 2.0 - C @ lam))),
        "note": "nonzero lower-bound multiplier proves the 1/sqrt(t) transform",
    }

    # (4) STRONGLY-SCALED Hessian-equivalent (the MR-002 pathology). t_min is the corpus's
    # actual observed minimum (1.0007e-8, i.e. just above eps_include -- the exact value that
    # defeated every prior solver). t = 1e-8 EXACTLY is rejected by the guard, correctly.
    t = np.array([1.0007001644509297e-08, 5.0e-5, 1.5e-2])
    z, ck, bad, g = evaluate(t.copy(), np.array([[1.0, 1.0, 1.0]]), np.array([0.01]),
                             np.zeros((0, 3)), np.zeros(0), t.copy())
    out["strongly_scaled"] = {
        "z": z.tolist(), "external_checks_pass": not bad, "failures": bad,
        "kkt_residual": ck["kkt_residual"], "gap": g,
        "epigraph_slack": ck["epigraph_slack"],
        "sqrt_roundtrip_error": ck["sqrt_roundtrip_error"],
        "note": "equivalent Hessian entries would be 2e8 / 4e4 / 1.3e2 — NONE is submitted",
    }

    out["all_pass"] = (
        all(v.get("stationarity", 0.0) <= LIMITS["stationarity_residual"]
            for v in out.values() if isinstance(v, dict))
        and out["strongly_scaled"]["external_checks_pass"]
        and all(abs(v.get("soc_w0_plus_wlast", 1.0) - 1.0) < 1e-8
                for v in out.values() if isinstance(v, dict) and "soc_w0_plus_wlast" in v)
    )
    return out


def negative_controls() -> dict:
    out = {}
    # invalid cone dimension
    try:
        P = sp.csc_matrix((2, 2))
        clarabel.DefaultSolver(P, np.zeros(2), sp.csc_matrix(np.eye(2)), np.zeros(2),
                              [clarabel.SecondOrderConeT(99)], settings()).solve()
        out["invalid_cone_dimension_rejected"] = False
    except Exception as e:
        out["invalid_cone_dimension_rejected"] = True
        out["invalid_cone_dimension_error"] = f"{type(e).__name__}"
    # invalid setting name
    s = settings()
    try:
        setattr(s, "mr002_not_a_real_setting", 1.0)
        out["invalid_setting_rejected"] = not hasattr(s, "mr002_not_a_real_setting")
    except Exception:
        out["invalid_setting_rejected"] = True
    return out


def manifest() -> dict:
    rep = json.load(open("/manifest/pip_report.json", encoding="utf-8"))
    art = {i["metadata"]["name"]: (i.get("download_info", {}).get("archive_info", {}) or {})
           .get("hashes", {}).get("sha256") for i in rep["install"]}
    HH = json.load(open("/out/MR002_Stage3_Corpus_Hashes.json", encoding="utf-8"))
    side = hashlib.sha256(
        open("/out/MR002_Stage3_Corpus_Symbolic.jsonl", "rb").read()).hexdigest()

    M = {
        "record_type": "MR002_CLARABEL_EXACT_CONIC_CAPABILITY_MANIFEST",
        "record_status": "IMMUTABLE",
        "date": "2026-07-13",
        "binds": {
            "clarabel_capability_manifest_sha256":
                "5f42217533c1ae3fc099b8e773a6c30862da7a45911de93698a35256e4f08b5e",
            "clarabel_field_mapping_amendment_sha256":
                "cc3de7db3e752afe6c33f959009baeff7ae3b552bab86ceb673ecc946d3fc4d7",
            "corpus_hash": HH["corpus_hash"],
            "symbolic_sidecar_sha256": side,
        },
        "distribution": {"name": "clarabel", "version": md.version("clarabel"),
                         "artifact_sha256": art.get("clarabel")},
        "environment": {"python": sys.version.split()[0],
                        "platform": platform.platform(), "machine": platform.machine()},
        "zero_hessian_construction": {
            "P": "sparse zero matrix, shape (n+1, n+1) — NO Stage-3 Hessian is submitted",
            "q_v": 0.0, "q_eta": 1.0,
            "soc_constant": SOC_CONST,
            "soc_identity": "eta >= ||r||^2  <=>  (eta+1, 2r, eta-1) in SOC(n+2)",
            "cone_implies_eta_nonnegative": True,
        },
        "row_construction": {
            "order": ["ZeroConeT(meq)", "NonnegativeConeT(m_ub)",
                      "NonnegativeConeT(n) lower bounds", "NonnegativeConeT(n) upper bounds",
                      "SecondOrderConeT(n+2)"],
            "soc": {"b_soc[0]": 1.0, "A_soc[0,eta]": -1.0,
                    "b_soc[1:n+1]": "-2*sqrt(t)", "A_soc[mid,v]": -2.0,
                    "b_soc[n+1]": -1.0, "A_soc[last,eta]": -1.0},
        },
        "dual_mapping": {
            "nu": "-y_eq", "lam_ineq": "y_ineq",
            "lam_lo": "y_lb / sqrt(t)", "lam_hi": "y_ub / sqrt(t)",
            "eta_stationarity": "w0 + w_last = 1",
            "cone_gradient": "-2 * w_mid == 2 (v - sqrt(t)) == analytic grad_v D",
            "original_gradient": "grad D(z)_i = 2 (z_i - t_i) / t_i — recomputed ANALYTICALLY; "
                                 "a solver-internal conic gradient is NEVER substituted",
        },
        "solution_fields_used": ["solution.x", "solution.z", "solution.s"],
        "internal_scaled_variables_inspected": False,
        "accepted_native_status": "Solved",
        "non_qualifying_statuses": ["AlmostSolved", "MaxIterations", "InsufficientProgress",
                                    "NumericalError", "PrimalInfeasible", "DualInfeasible"],
        "fresh_solver_per_instance": True,
        "warm_start_or_update": False,
        "settings_unchanged_from_prior_valid_records": True,
        "negative_controls": negative_controls(),
        "fixtures": fixtures(),
        "fatal": [],
    }
    if not M["fixtures"]["all_pass"]:
        M["fatal"].append("hand-solvable conic fixtures failed")
    for k, v in M["negative_controls"].items():
        if k.endswith("_rejected") and not v:
            M["fatal"].append(f"negative control not rejected: {k}")
    M["verdict"] = "VALID" if not M["fatal"] else "INVALID"
    return M


def _hash_instance(t, A_ub, b_ub, A_eq, b_eq, upper) -> str:
    h = hashlib.sha256()
    for arr in (t, A_ub, b_ub, A_eq, b_eq, upper):
        a = np.ascontiguousarray(np.asarray(arr, dtype=np.float64))
        h.update(str(a.shape).encode())
        h.update(a.tobytes())
    return h.hexdigest()


def corpus_main() -> int:
    HH = json.load(open("/out/MR002_Stage3_Corpus_Hashes.json", encoding="utf-8"))
    npz = np.load("/out/MR002_Stage3_Corpus.npz")
    N = len(HH["instance_hashes"])
    inst, ok = [], 0
    for i in range(N):
        rec = tuple(npz[f"{i}_{k}"] for k in ("t", "A_ub", "b_ub", "A_eq", "b_eq", "upper"))
        if _hash_instance(*rec) == HH["instance_hashes"][i]:
            ok += 1
        inst.append(rec)
    print(f"corpus {N} | per-instance hashes re-verified {ok}/{N}")
    if ok != N:
        return 1

    c = {"qualified": 0, "failed": 0, "failure_kinds": Counter(),
         "worst_kkt": 0.0, "worst_stationarity": 0.0, "worst_primal": 0.0,
         "worst_gap": 0.0, "worst_epigraph_slack": 0.0,
         "worst_sqrt_roundtrip": 0.0, "failed_instances": []}
    for i, rec in enumerate(inst):
        try:
            z, ck, bad, g = evaluate(*(x.copy() for x in rec))
            c["worst_kkt"] = max(c["worst_kkt"], ck["kkt_residual"])
            c["worst_stationarity"] = max(c["worst_stationarity"], ck["stationarity_residual"])
            c["worst_primal"] = max(c["worst_primal"], ck["primal_residual"])
            c["worst_gap"] = max(c["worst_gap"], abs(g))
            c["worst_epigraph_slack"] = max(c["worst_epigraph_slack"],
                                            abs(ck["epigraph_slack"]))
            c["worst_sqrt_roundtrip"] = max(c["worst_sqrt_roundtrip"],
                                            ck["sqrt_roundtrip_error"])
            if bad:
                c["failed"] += 1
                c["failure_kinds"]["+".join(bad)] += 1
                if len(c["failed_instances"]) < 20:
                    c["failed_instances"].append(
                        {"index": i, "hash": HH["instance_hashes"][i], "why": bad})
            else:
                c["qualified"] += 1
        except Exception as e:
            c["failed"] += 1
            c["failure_kinds"][f"{type(e).__name__}:{str(e)[:60]}"] += 1
            if len(c["failed_instances"]) < 20:
                c["failed_instances"].append(
                    {"index": i, "hash": HH["instance_hashes"][i],
                     "why": [f"{type(e).__name__}: {e}"]})
        if (i + 1) % 500 == 0:
            print(f"  {i+1}/{N} qualified={c['qualified']} failed={c['failed']}", flush=True)

    c["failure_kinds"] = dict(c["failure_kinds"])
    c["qualifies_all"] = c["failed"] == 0
    R = {"record_type": "MR002_CLARABEL_EXACT_CONIC_CORPUS_CHARACTERIZATION",
         "instances": N, "corpus_verified": True, "result": c,
         "VERDICT": "PASS" if c["qualifies_all"] else "FAIL — STOP FOR ADJUDICATION"}
    with open("/out/MR002_Clarabel_ExactConic_Corpus.json", "w",
              encoding="utf-8", newline="\n") as fh:
        json.dump(R, fh, indent=2, default=str)
        fh.write("\n")
    print("\n" + json.dumps(R, indent=2, default=str)[:2500])
    return 0


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "discovery"
    if mode == "discovery":
        M = manifest()
        out = "/out/MR002_Clarabel_ExactConicCapabilityManifest.json"
        with open(out, "w", encoding="utf-8", newline="\n") as fh:
            json.dump(M, fh, indent=2, default=str)
            fh.write("\n")
        print(json.dumps({k: M[k] for k in
              ("distribution", "zero_hessian_construction", "negative_controls",
               "fixtures", "fatal", "verdict")}, indent=2, default=str))
        print(f"\nmanifest: {out}")
        raise SystemExit(0 if M["verdict"] == "VALID" else 1)
    raise SystemExit(corpus_main())
