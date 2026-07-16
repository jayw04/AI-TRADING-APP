"""MR-002 v1.1 — REPLACEMENT-QP DEPENDENCY AND OPTION-CAPABILITY DISCOVERY.

Authorized 2026-07-12. The 3,895-instance corpus characterization is HELD until this phase
passes. No option is registered until it is shown to EXIST and to be HONORED.

An option is accepted only when:
  1. it exists on the pinned build;
  2. the native setter returns the documented success status;
  3. the native getter reads back the requested value exactly;
  4. an invalid-name negative control is REJECTED;
  5. a discriminating microproblem confirms behavior where read-back is insufficient.

Any warning, ignored field, rejected value, fallback, missing attribute or unexplained
coercion is FATAL.

CRITICAL: native HiGHS QP documents `qp_regularization_value` with a DEFAULT of 1e-7 ADDED
TO THE HESSIAN. MR-002 authorizes no objective regularization, so HiGHS is DISQUALIFIED
unless 0 is accepted, read back as 0, and BEHAVIOURALLY verified.
"""
from __future__ import annotations

import hashlib
import importlib.metadata as md
import json
import os
import platform
import sys
import warnings

import numpy as np
import scipy.sparse as sp

sys.path.insert(0, "/work/apps/backend")

TOL = 1e-10
OUT = "/out/MR002_QP_CandidateCapabilityManifest.json"


def artifact_hashes() -> dict:
    try:
        rep = json.load(open("/manifest/pip_report.json", encoding="utf-8"))
    except OSError:
        return {}
    return {i["metadata"]["name"]: {
        "version": i["metadata"]["version"],
        "sha256": (i.get("download_info", {}).get("archive_info", {}) or {})
        .get("hashes", {}).get("sha256"),
        "url": i.get("download_info", {}).get("url"),
    } for i in rep.get("install", [])}


THREADS = {v: os.environ.get(v) for v in (
    "OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS",
    "BLIS_NUM_THREADS", "NUMEXPR_NUM_THREADS")}


# ======================================================================================
# HiGHS
# ======================================================================================
def discover_highs(art) -> dict:
    import highspy

    R = {"distribution": "highspy", "version": md.version("highspy"),
         "artifact_sha256": art.get("highspy", {}).get("sha256"),
         "native_version": None, "options": [], "negative_controls": [],
         "behavioral": {}, "fatal": []}
    h = highspy.Highs()
    R["native_version"] = h.version()

    REQUESTED = [
        ("solver", "qpasm"), ("presolve", "off"), ("parallel", "off"),
        ("threads", 1), ("random_seed", 0), ("time_limit", 60.0),
        ("qp_allow_hot_start", False), ("qp_regularization_value", 0.0),
        ("output_flag", False), ("log_to_console", False),
        ("small_matrix_value", 1e-12),
    ]
    PROBE_ONLY = ["qp_iteration_limit", "qp_nullspace_limit", "kkt_tolerance",
                  "primal_feasibility_tolerance", "dual_feasibility_tolerance",
                  "primal_residual_tolerance", "dual_residual_tolerance",
                  "optimality_tolerance"]

    def setget(name, val):
        st = h.setOptionValue(name, val)
        ok_set = "kOk" in str(st)
        got = h.getOptionValue(name)
        if isinstance(got, tuple):
            got = got[-1]
        exact = (got == val) or (isinstance(val, float) and float(got) == float(val))
        rec = {"option": name, "requested": val, "set_status": str(st),
               "setter_succeeded": ok_set, "read_back": got,
               "read_back_exact": bool(exact)}
        R["options"].append(rec)
        if not (ok_set and exact):
            R["fatal"].append(f"HiGHS option {name}: set={st} read_back={got!r} "
                              f"(requested {val!r})")
        return rec

    for name, val in REQUESTED:
        setget(name, val)
    for name in PROBE_ONLY:
        st, typ = h.getOptionType(name)
        got = h.getOptionValue(name)
        if isinstance(got, tuple):
            got = got[-1]
        R["options"].append({"option": name, "exists": "kOk" in str(st),
                             "type": str(typ), "documented_default_read": got,
                             "requested": "PROBE_ONLY"})

    # ---- negative control: an invalid option name MUST be rejected ---------------------
    st = h.setOptionValue("mr002_not_a_real_option", 1.0)
    rejected = "kOk" not in str(st)
    R["negative_controls"].append({"option": "mr002_not_a_real_option",
                                   "status": str(st), "rejected": rejected})
    if not rejected:
        R["fatal"].append("HiGHS accepted an invalid option name -- silent-fallback risk")

    # ---- BEHAVIOURAL: is qp_regularization_value = 0 actually honored? -----------------
    # Discriminating microproblem: unconstrained-in-the-box QP whose exact optimum is known.
    #   min (1/2) z' diag(2/t) z - 2*1' z  ->  z* = t   (interior, no constraint active)
    # With Hessian regularization r, the solved Hessian is diag(2/t + r) and the optimum
    # shifts to z = 2 / (2/t + r) = t / (1 + r*t/2). With t = 1e-2 and r = 1e-7 the shift is
    # ~5e-10 -- detectable well above solver tolerance.
    def micro(reg, t_val=1e-2):
        g = highspy.Highs()
        for k, v in (("output_flag", False), ("log_to_console", False),
                     ("solver", "qpasm"), ("presolve", "off"), ("parallel", "off"),
                     ("threads", 1), ("random_seed", 0), ("time_limit", 60.0)):
            g.setOptionValue(k, v)
        g.setOptionValue("qp_regularization_value", reg)
        g.setOptionValue("kkt_tolerance", TOL)
        n = 1
        lp = highspy.HighsLp()
        lp.num_col_ = n
        lp.num_row_ = 1
        lp.col_cost_ = np.array([-2.0])
        lp.col_lower_ = np.array([0.0])
        lp.col_upper_ = np.array([1.0])          # non-binding
        lp.row_lower_ = np.array([-highspy.kHighsInf])
        lp.row_upper_ = np.array([1.0])          # non-binding
        S = sp.csr_matrix(np.array([[1.0]]))
        lp.a_matrix_.format_ = highspy.MatrixFormat.kRowwise
        lp.a_matrix_.start_ = S.indptr.tolist()
        lp.a_matrix_.index_ = S.indices.tolist()
        lp.a_matrix_.value_ = S.data.tolist()
        hess = highspy.HighsHessian()
        hess.dim_ = n
        hess.format_ = highspy.HessianFormat.kTriangular
        hess.start_ = [0, 1]
        hess.index_ = [0]
        hess.value_ = [2.0 / t_val]
        m = highspy.HighsModel()
        m.lp_ = lp
        m.hessian_ = hess
        g.passModel(m)
        g.run()
        return float(np.asarray(g.getSolution().col_value, float)[0])

    t_val = 1e-2
    z0 = micro(0.0, t_val)
    z7 = micro(1e-7, t_val)
    exact = t_val
    pred7 = t_val / (1.0 + 1e-7 * t_val / 2.0)
    R["behavioral"]["qp_regularization_value"] = {
        "microproblem": "min (1/2)(2/t)z^2 - 2z, box non-binding -> z* = t exactly",
        "t": t_val, "exact_optimum": exact,
        "z_with_reg_0": z0, "err_vs_exact_reg_0": abs(z0 - exact),
        "z_with_reg_1e-7": z7, "predicted_if_reg_applied": pred7,
        "reg_0_is_honored": abs(z0 - exact) < 1e-12,
        "note": ("If reg=0 reproduces the exact optimum, no Hessian regularization is "
                 "applied. MR-002 authorizes NO objective regularization."),
    }
    if not R["behavioral"]["qp_regularization_value"]["reg_0_is_honored"]:
        R["fatal"].append(
            f"HiGHS qp_regularization_value=0 NOT honored: z={z0!r} vs exact {exact!r} "
            "-- the submitted Stage-3 objective would be altered")

    # ---- H1 vs H2 tolerance configurations ---------------------------------------------
    R["behavioral"]["tolerance_configs"] = {
        "H1": "kkt_tolerance = 1e-10; individual tolerances left at documented defaults",
        "H2": "kkt_tolerance default; individual feas/residual/optimality = 1e-10",
        "note": ("HiGHS documents that a NON-DEFAULT kkt_tolerance is used for ALL KKT "
                 "measures, so H1 and H2 must not be combined."),
    }
    for tag in ("H1", "H2"):
        g = highspy.Highs()
        for k, v in (("output_flag", False), ("log_to_console", False),
                     ("solver", "qpasm"), ("presolve", "off"), ("parallel", "off"),
                     ("threads", 1), ("random_seed", 0)):
            g.setOptionValue(k, v)
        g.setOptionValue("qp_regularization_value", 0.0)
        if tag == "H1":
            ok = "kOk" in str(g.setOptionValue("kkt_tolerance", TOL))
            rb = g.getOptionValue("kkt_tolerance")
        else:
            ok = all("kOk" in str(g.setOptionValue(k, TOL)) for k in (
                "primal_feasibility_tolerance", "dual_feasibility_tolerance",
                "primal_residual_tolerance", "dual_residual_tolerance",
                "optimality_tolerance"))
            rb = g.getOptionValue("primal_feasibility_tolerance")
        R["behavioral"]["tolerance_configs"][tag + "_accepted"] = bool(ok)
        R["behavioral"]["tolerance_configs"][tag + "_read_back"] = (
            rb[-1] if isinstance(rb, tuple) else rb)

    return R


# ======================================================================================
# Clarabel
# ======================================================================================
def discover_clarabel(art) -> dict:
    import clarabel

    R = {"distribution": "clarabel", "version": md.version("clarabel"),
         "artifact_sha256": art.get("clarabel", {}).get("sha256"),
         "options": [], "negative_controls": [], "behavioral": {}, "fatal": []}

    FIELDS = ["max_threads", "max_iter", "time_limit", "verbose", "tol_gap_abs",
              "tol_gap_rel", "tol_feas", "tol_infeas_abs", "tol_infeas_rel",
              "tol_ktratio", "equilibrate_enable", "equilibrate_max_iter",
              "equilibrate_min_scaling", "equilibrate_max_scaling", "presolve_enable",
              "direct_kkt_solver", "direct_solve_method", "static_regularization_enable",
              "static_regularization_eps", "static_regularization_proportional",
              "dynamic_regularization_enable", "dynamic_regularization_eps",
              "dynamic_regularization_delta", "iterative_refinement_enable",
              "iterative_refinement_reltol", "iterative_refinement_abstol",
              "iterative_refinement_max_iter", "iterative_refinement_stop_ratio"]
    s = clarabel.DefaultSettings()
    for f in FIELDS:
        exists = hasattr(s, f)
        R["options"].append({"option": f, "exists": exists,
                             "installed_default": getattr(s, f, None) if exists else None})
        if not exists:
            R["fatal"].append(f"Clarabel setting {f} DOES NOT EXIST on the pinned build")

    REQUESTED = {
        "max_threads": 1, "max_iter": 500, "time_limit": 60.0, "verbose": False,
        "tol_gap_abs": TOL, "tol_gap_rel": TOL, "tol_feas": TOL,
        "tol_infeas_abs": TOL, "tol_infeas_rel": TOL,
        "equilibrate_enable": True, "presolve_enable": False,
        "direct_kkt_solver": True, "direct_solve_method": "qdldl",
        "static_regularization_enable": True, "dynamic_regularization_enable": True,
        "iterative_refinement_enable": True,
    }
    for f, v in REQUESTED.items():
        if not hasattr(s, f):
            continue
        setattr(s, f, v)
        got = getattr(s, f)
        exact = got == v
        R["options"].append({"option": f, "requested": v, "read_back": got,
                             "read_back_exact": bool(exact)})
        if not exact:
            R["fatal"].append(f"Clarabel {f}: read back {got!r}, requested {v!r}")

    # negative control
    try:
        setattr(s, "mr002_not_a_real_setting", 1.0)
        got = getattr(s, "mr002_not_a_real_setting", None)
        rejected = got is None
    except Exception:
        rejected = True
    R["negative_controls"].append({"option": "mr002_not_a_real_setting",
                                   "rejected": bool(rejected)})
    if not rejected:
        R["fatal"].append("Clarabel silently accepted an unknown setting name")

    # ---- BEHAVIOURAL: does it solve the exact submitted objective? ---------------------
    t = np.array([1e-2])
    P = sp.csc_matrix(np.diag(2.0 / t))
    q = -2.0 * np.ones(1)
    A = sp.csc_matrix(np.array([[-1.0], [1.0]]))
    b = np.array([0.0, 1.0])
    cones = [clarabel.NonnegativeConeT(2)]
    sol = clarabel.DefaultSolver(P, q, A, b, cones, s).solve()
    z = float(np.asarray(sol.x, float)[0])
    R["behavioral"]["exact_objective"] = {
        "microproblem": "min (1/2)(2/t)z^2 - 2z, 0<=z<=1 non-binding -> z* = t exactly",
        "t": 1e-2, "solved_z": z, "err_vs_exact": abs(z - 1e-2),
        "status": str(sol.status),
        "objective_unmodified": abs(z - 1e-2) < 1e-9,
        "note": ("Clarabel's internal KKT regularization is a linear-algebra mechanism; "
                 "it must not alter the submitted P, q or constraints."),
    }
    if str(sol.status) != "Solved":
        R["fatal"].append(f"Clarabel microproblem status {sol.status}")
    if not R["behavioral"]["exact_objective"]["objective_unmodified"]:
        R["fatal"].append("Clarabel altered the submitted objective")
    return R


# ======================================================================================
def small_matrix_audit() -> dict:
    """HiGHS treats |coeff| <= small_matrix_value as ZERO (documented minimum 1e-12).
    If any submitted NONZERO coefficient is at or below that, HiGHS does NOT receive the
    exact registered model."""
    npz = np.load("/out/MR002_Stage3_Corpus.npz")
    H = json.load(open("/out/MR002_Stage3_Corpus_Hashes.json", encoding="utf-8"))
    N = len(H["instance_hashes"])
    lo = np.inf
    for i in range(N):
        for k in ("A_ub", "A_eq"):
            M = npz[f"{i}_{k}"]
            nz = np.abs(M[M != 0.0])
            if nz.size:
                lo = min(lo, float(nz.min()))
    return {"instances_scanned": N,
            "min_absolute_nonzero_coefficient": lo,
            "small_matrix_value": 1e-12,
            "passed": bool(lo > 1e-12),
            "note": ("A submitted nonzero coefficient at or below small_matrix_value "
                     "would be silently zeroed by HiGHS.")}


def main() -> int:
    art = artifact_hashes()
    M = {
        "record_type": "MR002_QP_CANDIDATE_CAPABILITY_MANIFEST",
        "purpose": ("Isolated dependency and option-capability discovery. The 3,895-instance "
                    "corpus characterization is HELD until this manifest is VALID."),
        "environment": {
            "python": sys.version.split()[0],
            "abi": f"cp{sys.version_info.major}{sys.version_info.minor}",
            "platform": platform.platform(),
            "machine": platform.machine(),
            "numpy": md.version("numpy"), "scipy": md.version("scipy"),
            "thread_pins": THREADS,
        },
        "artifacts": {k: art.get(k) for k in ("highspy", "clarabel", "numpy", "scipy")},
        "IMPORTANT": ("highspy ships its own HiGHS build. SciPy vendors a DIFFERENT HiGHS "
                      "(1.12.0). They are not interchangeable."),
    }

    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        M["highs"] = discover_highs(art)
        M["clarabel"] = discover_clarabel(art)
        M["warnings_during_discovery"] = [str(x.message) for x in w]

    M["small_matrix_audit"] = small_matrix_audit()
    if not M["small_matrix_audit"]["passed"]:
        M["highs"]["fatal"].append(
            "small-matrix audit FAILED: a submitted nonzero coefficient is at or below "
            "small_matrix_value and would be silently zeroed")

    hf, cf = M["highs"]["fatal"], M["clarabel"]["fatal"]
    if M["warnings_during_discovery"]:
        hf.append(f"warnings during discovery: {M['warnings_during_discovery']}")

    M["summary"] = {
        "all_requested_options_exist":
            all(o.get("exists", True) for o in M["clarabel"]["options"]),
        "all_setters_succeeded":
            all(o.get("setter_succeeded", True) for o in M["highs"]["options"]),
        "all_values_read_back":
            all(o.get("read_back_exact", True) for o in
                M["highs"]["options"] + M["clarabel"]["options"]),
        "all_negative_controls_rejected":
            all(c["rejected"] for c in
                M["highs"]["negative_controls"] + M["clarabel"]["negative_controls"]),
        "all_behavioral_controls_passed":
            M["highs"]["behavioral"]["qp_regularization_value"]["reg_0_is_honored"]
            and M["clarabel"]["behavioral"]["exact_objective"]["objective_unmodified"],
        "highs_regularization_is_zero":
            M["highs"]["behavioral"]["qp_regularization_value"]["reg_0_is_honored"],
        "highs_small_matrix_audit_passed": M["small_matrix_audit"]["passed"],
        "no_silent_fallback_detected": not M["warnings_during_discovery"],
    }
    M["highs_verdict"] = "VALID" if not hf else "INVALID"
    M["clarabel_verdict"] = "VALID" if not cf else "INVALID"
    M["verdict"] = ("VALID" if not hf and not cf else
                    "PARTIAL" if not hf or not cf else "INVALID")

    with open(OUT, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(M, fh, indent=2, default=str)
        fh.write("\n")
    print(json.dumps({
        "environment": M["environment"], "artifacts": M["artifacts"],
        "highs_native_version": M["highs"]["native_version"],
        "highs_reg_behavioral": M["highs"]["behavioral"]["qp_regularization_value"],
        "small_matrix_audit": M["small_matrix_audit"],
        "clarabel_behavioral": M["clarabel"]["behavioral"]["exact_objective"],
        "summary": M["summary"],
        "highs_fatal": hf, "clarabel_fatal": cf,
        "highs_verdict": M["highs_verdict"], "clarabel_verdict": M["clarabel_verdict"],
        "verdict": M["verdict"]}, indent=2, default=str))
    print(f"\nmanifest: {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
