"""How often does the RAW Stage-3 formulation fail a REGISTERED CHECK (not just raise),
and does the registered SCALED formulation fix every one?

DIAGNOSTIC ONLY. No performance computed.
"""
from __future__ import annotations
import json, sys, warnings
from collections import Counter
from datetime import date
import numpy as np, quadprog
sys.path.insert(0, "/work/apps/backend")
import app.research.mr002.joint_portfolio as jp
from app.research.mr002.joint_portfolio import InvalidRun

R = {"solves": 0, "raw_clean": 0, "raw_raised": 0, "raw_check_failed": 0,
     "raw_failure_kinds": Counter(), "scaled_failure_kinds": Counter(),
     "diagnostic_slsqp_ok": 0, "diagnostic_slsqp_failed": 0, "rescued_by_scaled": 0, "scaled_also_failed": 0,
     "max_primal_disagreement_raw_vs_scaled": 0.0, "worst_raw_stationarity": 0.0,
     "worst_scaled_stationarity": 0.0, "min_target_on_failure": 1.0}

def qp(H,a,C,b,meq):
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        return quadprog.solve_qp(H,a,C,b,meq)

def solve(H_diag, targets, A_ub, b_ub, A_eq, b_eq, upper):
    n=len(targets); t=np.asarray(targets,float); R["solves"]+=1
    H=np.diag(2.0/t); a=2.0*np.ones(n); meq=A_eq.shape[0]
    C,b = jp._qp_matrices(A_ub,b_ub,A_eq,b_eq,upper,n)
    z_raw=None; kind=None
    try:
        o=qp(H,a,C,b,meq); z=np.asarray(o[0],float); lam=np.asarray(o[4],float)
        ck=jp._acceptance(z,lam,meq,H,a,C,b,A_ub,b_ub,A_eq,b_eq,upper)
        R["worst_raw_stationarity"]=max(R["worst_raw_stationarity"],ck["stationarity_residual"])
        bad=[k for k,v in ck.items() if v > {"primal_residual":1e-9,"dual_residual":1e-9,
             "stationarity_residual":1e-8,"complementarity_residual":1e-8,"kkt_residual":1e-8}[k]]
        if not bad:
            R["raw_clean"]+=1; return z, dict(ck, stage3_formulation="RAW",
                hessian_condition_number=1.0, qp_iterations=[0,0])
        R["raw_check_failed"]+=1; kind="+".join(sorted(bad)); z_raw=z
    except ValueError as e:
        R["raw_raised"]+=1; kind=f"RAISED:{e}"
    R["raw_failure_kinds"][kind]+=1
    R["min_target_on_failure"]=min(R["min_target_on_failure"], float(t.min()))

    T=np.diag(t)
    C_s,b_s = jp._qp_matrices(A_ub@T,b_ub,A_eq@T,b_eq,upper/t,n)
    try:
        o=qp(np.diag(2.0*t),2.0*t,C_s,b_s,meq)
    except ValueError as e:
        R["scaled_also_failed"]+=1
        R["scaled_failure_kinds"][f"RAISED:{e}"]+=1
        # DIAGNOSTIC continuation only: an independent solver so the census completes
        from scipy.optimize import minimize
        r=minimize(lambda x: float(np.sum((x-t)**2/t)), x0=np.clip(t,0,upper),
                   jac=lambda x: 2*(x-t)/t, bounds=[(0.0,float(v)) for v in upper],
                   constraints=[{"type":"ineq","fun":lambda x: b_ub-A_ub@x},
                                {"type":"eq","fun":lambda x:(A_eq@x-b_eq).ravel()}],
                   method="SLSQP", options={"maxiter":800,"ftol":1e-16})
        R["diagnostic_slsqp_ok" if r.success else "diagnostic_slsqp_failed"]+=1
        z=np.asarray(r.x,float) if r.success else np.clip(t,0,upper)
        return z, dict(jp._acceptance(z,np.zeros(C.shape[1]),meq,H,a,C,b,A_ub,b_ub,A_eq,b_eq,upper),
                       stage3_formulation="DIAGNOSTIC_FALLBACK",
                       hessian_condition_number=1.0, qp_iterations=[0,0])
    u=np.asarray(o[0],float); lam_u=np.asarray(o[4],float); z=T@u
    nr=meq+A_ub.shape[0]; lam_z=lam_u.copy(); lam_z[nr:nr+n]/=t; lam_z[nr+n:]/=t
    ck=jp._acceptance(z,lam_z,meq,H,a,C,b,A_ub,b_ub,A_eq,b_eq,upper)
    R["worst_scaled_stationarity"]=max(R["worst_scaled_stationarity"],ck["stationarity_residual"])
    bad=[k for k,v in ck.items() if v > {"primal_residual":1e-9,"dual_residual":1e-9,
         "stationarity_residual":1e-8,"complementarity_residual":1e-8,"kkt_residual":1e-8}[k]]
    if bad:
        R["scaled_also_failed"]+=1
        R["scaled_failure_kinds"]["+".join(sorted(bad))]+=1
    else:
        R["rescued_by_scaled"]+=1
    if z_raw is not None:
        R["max_primal_disagreement_raw_vs_scaled"]=max(
            R["max_primal_disagreement_raw_vs_scaled"], float(np.max(np.abs(z_raw-z))))
    return z, dict(ck, stage3_formulation="SCALED_RESCUE",
                   hessian_condition_number=1.0, qp_iterations=[0,0])

jp._solve_qp = solve
from app.research.mr002.dataset import FrozenDataset
from app.research.mr002.runner import CONFIGS
from scripts.mr002_development_run import run_config
ds=FrozenDataset("/work/apps/backend/data/mr002_research.duckdb")
days=ds.day_inputs(date(2013,1,2), date(2019,10,2))
for nm in ("A","B","C"):
    print(f"config {nm} ...", flush=True); run_config(days, CONFIGS[nm])
R["raw_failure_kinds"]=dict(R["raw_failure_kinds"])
R["scaled_failure_kinds"]=dict(R["scaled_failure_kinds"])
print(json.dumps(R, indent=2))
