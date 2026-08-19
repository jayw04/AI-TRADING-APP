"""MR-002 Gate N1 — the difference-vs-v1 report (§7 output 7).

Sealed authority: MR002_N1_ProspectiveRegistration_v1.0
identity 7f8a56e34e6d5d36a3914ecb825de015debdc83ebae2967887e5e37ca3d684af.

"Every instance where the v2 method's accepted point or disposition differs from the v1 method's,
with the economic consequence stated."

The economic consequence is stated in the units the strategy actually acts in, not as an abstract
norm: the registered Stage-3 objective f(z) = sum (z_i - t_i)^2 / t_i evaluated at both points, the
largest single-coordinate allocation change, and the total absolute allocation change. A difference
that is real but economically inert should be visible AS inert rather than hidden behind a pass.

Development domain only.
"""
from __future__ import annotations

import json
import os
import sys
import time

import numpy as np

sys.path.insert(0, "/work/apps/backend")

from app.research.mr002.n1 import method as M  # noqa: E402

CORPUS_NPZ = "/work/.mr002out/n1/corpus.npz"
OUT_DIR = "/work/.mr002out/n1"
REGISTERED_CORPUS_HASH = "1d2319301a7b52dfe369819bc8029f7b6d64ad820d828f041eba15a91348390b"

A_PROFILE = "QUADPROG_SQRT"
B_CANDIDATES = ("PIQP_P1", "PIQP_P2")


def objective(z, t) -> float:
    z = np.asarray(z, float)
    t = np.asarray(t, float)
    return float(np.sum((z - t) ** 2 / t))


def main() -> int:
    t0 = time.time()
    limit = int(os.environ.get("N1_LIMIT", "0"))
    from app.research.mr002 import stage3_cascade as SC
    from scripts.mr002_coverage_signed_gap import SOLVERS, canonical_qualify

    d = np.load(CORPUS_NPZ, allow_pickle=False)
    if str(d["corpus_hash"]) != REGISTERED_CORPUS_HASH:
        raise SystemExit("ABORT: corpus hash mismatch")
    n_inst = int(d["n_instances"])
    if limit:
        n_inst = min(n_inst, limit)
    print(f"[{time.time()-t0:7.1f}s] corpus verified, {n_inst} instances", flush=True)

    report = {"corpus_hash": REGISTERED_CORPUS_HASH, "instances": n_inst, "candidates": {}}
    for c in B_CANDIDATES:
        report["candidates"][c] = {"disposition_differs": [], "point_differs": [],
                                   "counts": {"identical": 0, "point_differs": 0,
                                              "disposition_differs": 0}}

    for i in range(n_inst):
        rec = tuple(d[f"{i}_{k}"] for k in ("t", "A_ub", "b_ub", "A_eq", "b_eq", "upper"))
        t = rec[0]

        try:
            o1 = SC.resolve_instance(rec)
            z1 = None if o1.accepted_z is None else np.asarray(o1.accepted_z, float)
            d1, by1 = o1.disposition, o1.accepted_by
        except Exception as exc:  # noqa: BLE001
            z1, d1, by1 = None, f"RAISED:{type(exc).__name__}", None

        a = M.normalize(A_PROFILE, SOLVERS[A_PROFILE], canonical_qualify, rec)
        for c in B_CANDIDATES:
            b = M.normalize(c, SOLVERS[c], canonical_qualify, rec)
            if a.outcome == M.SYSTEM_INTEGRITY_DEFECT or b.outcome == M.SYSTEM_INTEGRITY_DEFECT:
                d2, z2, by2 = M.INVALID_RUN, None, None
            elif a.is_certified:
                d2, z2, by2 = M.PRIMARY_CERTIFIED, a.z, A_PROFILE
            elif b.is_certified:
                d2, z2, by2 = M.SECONDARY_CERTIFIED, b.z, c
            else:
                d2, z2, by2 = M.UNRESOLVED_INSTANCE, None, None

            R = report["candidates"][c]
            same_point = (z1 is not None and z2 is not None
                          and np.asarray(z1).tobytes() == np.asarray(z2).tobytes())

            # v1 and v2 name dispositions differently by design; compare what they MEAN.
            v1_resolved = z1 is not None
            v2_resolved = z2 is not None
            if v1_resolved != v2_resolved:
                R["counts"]["disposition_differs"] += 1
                R["disposition_differs"].append({
                    "i": i, "v1": d1, "v2": d2, "v1_accepted_by": by1, "v2_accepted_by": by2})
                continue

            if same_point:
                R["counts"]["identical"] += 1
                continue

            if z1 is None:
                R["counts"]["identical"] += 1
                continue

            f1, f2 = objective(z1, t), objective(z2, t)
            dz = np.asarray(z2, float) - np.asarray(z1, float)
            R["counts"]["point_differs"] += 1
            R["point_differs"].append({
                "i": i, "n": int(len(t)),
                "v1_accepted_by": by1, "v2_accepted_by": by2,
                "v1_disposition": d1, "v2_disposition": d2,
                "objective_v1": f1, "objective_v2": f2,
                "objective_delta": f2 - f1,
                "objective_relative_delta": (f2 - f1) / f1 if f1 else None,
                "max_abs_coordinate_change": float(np.max(np.abs(dz))),
                "total_abs_allocation_change": float(np.sum(np.abs(dz))),
                "l2_change": float(np.linalg.norm(dz)),
            })

        if (i + 1) % 500 == 0:
            print(f"[{time.time()-t0:7.1f}s]   {i+1}/{n_inst}", flush=True)

    for c in B_CANDIDATES:
        R = report["candidates"][c]
        pts = R["point_differs"]
        R["summary"] = {
            "instances_with_identical_accepted_point": R["counts"]["identical"],
            "instances_with_differing_accepted_point": R["counts"]["point_differs"],
            "instances_with_differing_resolution": R["counts"]["disposition_differs"],
            "max_objective_relative_delta": max((abs(p["objective_relative_delta"] or 0.0)
                                                 for p in pts), default=0.0),
            "max_total_abs_allocation_change": max((p["total_abs_allocation_change"] for p in pts),
                                                   default=0.0),
        }
        print(f"\n{c}: {R['summary']}", flush=True)
        for p in pts[:10]:
            print(f"   i={p['i']:5d} v1={p['v1_accepted_by']} -> v2={p['v2_accepted_by']}  "
                  f"dObj={p['objective_delta']:+.3e} ({p['objective_relative_delta']:+.2e} rel)  "
                  f"max|dz|={p['max_abs_coordinate_change']:.3e}  "
                  f"sum|dz|={p['total_abs_allocation_change']:.3e}", flush=True)

    os.makedirs(OUT_DIR, exist_ok=True)
    suffix = f"_limit{limit}" if limit else ""
    with open(os.path.join(OUT_DIR, f"n1_diff_v1{suffix}.json"), "w") as fh:
        json.dump(report, fh, indent=1, sort_keys=True)
    print(f"\n[{time.time()-t0:7.1f}s] wrote difference-vs-v1 report", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
