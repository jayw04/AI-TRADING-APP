"""MR-002 Gate N1 — C4(b) canonical shuffle-invariance, measured at the right granularity.

Sealed authority: MR002_N1_ProspectiveRegistration_v1.0 §5.3 C4
identity 7f8a56e34e6d5d36a3914ecb825de015debdc83ebae2967887e5e37ca3d684af.

The first C4 pass collapsed two different events into one "differs" counter:

  (i)  the permuted problem FAILED TO CERTIFY under that generator
  (ii) it certified, but at a point deviating beyond the registered agreement slack

Only (ii) is a solution non-invariance. (i) says the generator did not qualify on a relabelled
instance — real, but under a TWO-GENERATOR method the cascade still resolves it, exactly as it
resolves the unpermuted instance where that generator fails.

So this measures three things separately:

  PER-GENERATOR   exact / bounded / deviates-beyond-slack / failed-to-certify
  METHOD-LEVEL    run the full A -> B cascade on the permuted problem and compare the ACCEPTED
                  point. This is what "the method is shuffle-invariant" actually means, and the
                  accepted point IS the economic solution.
  PERMUTATIONS    each instance is tested under several permutations, not one, so a pass is not an
                  artifact of a single lucky relabelling.

Deterministic: PCG64 seeded from the registration's frozen N2 seed so the permutations are
reproducible.

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
SLACK = 1e-10
SEED = 20260819
N_PERMS = int(os.environ.get("N1_PERMS", "3"))


def permuted(rec, perm):
    t, A_ub, b_ub, A_eq, b_eq, upper = rec
    return (t[perm], A_ub[:, perm], b_ub, A_eq[:, perm], b_eq, upper[perm])


def cascade_accept(rec, cand, solvers, certify):
    """The two-generator method's accepted point and disposition on one instance."""
    a = M.normalize(A_PROFILE, solvers[A_PROFILE], certify, rec)
    if a.outcome == M.SYSTEM_INTEGRITY_DEFECT:
        return M.INVALID_RUN, None
    if a.is_certified:
        return M.PRIMARY_CERTIFIED, a.z
    b = M.normalize(cand, solvers[cand], certify, rec)
    if b.outcome == M.SYSTEM_INTEGRITY_DEFECT:
        return M.INVALID_RUN, None
    if b.is_certified:
        return M.SECONDARY_CERTIFIED, b.z
    return M.UNRESOLVED_INSTANCE, None


def main() -> int:
    t0 = time.time()
    limit = int(os.environ.get("N1_LIMIT", "0"))
    from scripts.mr002_coverage_signed_gap import SOLVERS, canonical_qualify

    d = np.load(CORPUS_NPZ, allow_pickle=False)
    if str(d["corpus_hash"]) != REGISTERED_CORPUS_HASH:
        raise SystemExit("ABORT: corpus hash mismatch")
    n_inst = int(d["n_instances"])
    if limit:
        n_inst = min(n_inst, limit)
    print(f"[{time.time()-t0:7.1f}s] {n_inst} instances, {N_PERMS} permutations each", flush=True)

    gen = {p: {"exact": 0, "bounded": 0, "deviates_beyond_slack": 0,
               "permuted_failed_to_certify": 0, "base_not_certified": 0, "worst": 0.0,
               "deviating_rows": []}
           for p in (A_PROFILE, *B_CANDIDATES)}
    meth = {c: {"exact": 0, "bounded": 0, "deviates_beyond_slack": 0,
                "disposition_changed": 0, "unresolved_both": 0, "worst": 0.0,
                "deviating_rows": [],
                # Addendum §2 clause 5: where B is ACTUALLY DECISIVE (A produced no certified
                # candidate), permutation must not alter the disposition or the accepted allocation
                # beyond the bound. This is a SEPARATE condition from the aggregate, so it is
                # counted separately rather than inferred from it.
                "B_decisive_instances": 0,
                "B_decisive_permuted_checks": 0,
                "B_decisive_disposition_changed": 0,
                "B_decisive_allocation_beyond_bound": 0,
                "B_decisive_worst": 0.0,
                "B_decisive_rows": []}
            for c in B_CANDIDATES}

    rng = np.random.Generator(np.random.PCG64(SEED))

    for i in range(n_inst):
        rec = tuple(d[f"{i}_{k}"] for k in ("t", "A_ub", "b_ub", "A_eq", "b_eq", "upper"))
        n = len(rec[0])
        if n < 2:
            for p in gen:
                gen[p]["base_not_certified"] += 1
            continue
        perms = [rng.permutation(n) for _ in range(N_PERMS)]

        # ── per generator ───────────────────────────────────────────────────────────────────────
        for p in (A_PROFILE, *B_CANDIDATES):
            base = M.normalize(p, SOLVERS[p], canonical_qualify, rec)
            if not base.is_certified:
                gen[p]["base_not_certified"] += 1
                continue
            for perm in perms:
                inv = np.argsort(perm)
                o = M.normalize(p, SOLVERS[p], canonical_qualify, permuted(rec, perm))
                if not o.is_certified:
                    gen[p]["permuted_failed_to_certify"] += 1
                    continue
                back = np.asarray(o.z, float)[inv]
                if back.tobytes() == np.asarray(base.z, float).tobytes():
                    gen[p]["exact"] += 1
                    continue
                dev = float(np.linalg.norm(back - np.asarray(base.z, float)))
                gen[p]["worst"] = max(gen[p]["worst"], dev)
                if dev <= SLACK:
                    gen[p]["bounded"] += 1
                else:
                    gen[p]["deviates_beyond_slack"] += 1
                    if len(gen[p]["deviating_rows"]) < 25:
                        gen[p]["deviating_rows"].append({"i": i, "n": n, "deviation": dev})

        # ── method level: the accepted point of the two-generator cascade ───────────────────────
        for c in B_CANDIDATES:
            d0, z0 = cascade_accept(rec, c, SOLVERS, canonical_qualify)
            b_decisive = (d0 == M.SECONDARY_CERTIFIED)
            if b_decisive:
                meth[c]["B_decisive_instances"] += 1
            for perm in perms:
                inv = np.argsort(perm)
                d1, z1 = cascade_accept(permuted(rec, perm), c, SOLVERS, canonical_qualify)
                if b_decisive:
                    meth[c]["B_decisive_permuted_checks"] += 1
                if (z0 is None) != (z1 is None) or d0 != d1:
                    meth[c]["disposition_changed"] += 1
                    if b_decisive:
                        meth[c]["B_decisive_disposition_changed"] += 1
                        meth[c]["B_decisive_rows"].append(
                            {"i": i, "n": n, "base": d0, "permuted": d1, "why": "disposition changed"})
                    continue
                if z0 is None:
                    meth[c]["unresolved_both"] += 1
                    continue
                back = np.asarray(z1, float)[inv]
                same = back.tobytes() == np.asarray(z0, float).tobytes()
                dev = 0.0 if same else float(np.linalg.norm(back - np.asarray(z0, float)))
                if b_decisive:
                    meth[c]["B_decisive_worst"] = max(meth[c]["B_decisive_worst"], dev)
                    if dev > SLACK:
                        meth[c]["B_decisive_allocation_beyond_bound"] += 1
                        meth[c]["B_decisive_rows"].append(
                            {"i": i, "n": n, "deviation": dev, "why": "allocation beyond bound"})
                if same:
                    meth[c]["exact"] += 1
                    continue
                meth[c]["worst"] = max(meth[c]["worst"], dev)
                if dev <= SLACK:
                    meth[c]["bounded"] += 1
                else:
                    meth[c]["deviates_beyond_slack"] += 1
                    if len(meth[c]["deviating_rows"]) < 25:
                        meth[c]["deviating_rows"].append({"i": i, "n": n, "deviation": dev})

        if (i + 1) % 250 == 0:
            print(f"[{time.time()-t0:7.1f}s]   {i+1}/{n_inst}", flush=True)

    print("\nPER-GENERATOR shuffle behaviour")
    for p, r in gen.items():
        print(f"  {p:15s} exact={r['exact']} bounded={r['bounded']} "
              f"BEYOND_SLACK={r['deviates_beyond_slack']} "
              f"permuted_failed_to_certify={r['permuted_failed_to_certify']} "
              f"base_not_certified={r['base_not_certified']} worst={r['worst']:.3e}")
    print("\nMETHOD-LEVEL shuffle behaviour (the accepted point of the A->B cascade)")
    for c, r in meth.items():
        print(f"  {c:15s} exact={r['exact']} bounded={r['bounded']} "
              f"BEYOND_SLACK={r['deviates_beyond_slack']} "
              f"disposition_changed={r['disposition_changed']} "
              f"unresolved_both={r['unresolved_both']} worst={r['worst']:.3e}")
    print("\nADDENDUM 2 CLAUSE 5 - where B is ACTUALLY DECISIVE (both must be 0)")
    for c, r in meth.items():
        print(f"  {c:15s} B_decisive_instances={r['B_decisive_instances']} "
              f"checks={r['B_decisive_permuted_checks']} "
              f"DISPOSITION_CHANGED={r['B_decisive_disposition_changed']} "
              f"ALLOCATION_BEYOND_BOUND={r['B_decisive_allocation_beyond_bound']} "
              f"worst={r['B_decisive_worst']:.3e}")

    os.makedirs(OUT_DIR, exist_ok=True)
    suffix = f"_limit{limit}" if limit else ""
    with open(os.path.join(OUT_DIR, f"n1_shuffle{suffix}.json"), "w") as fh:
        json.dump({"corpus_hash": REGISTERED_CORPUS_HASH, "instances": n_inst,
                   "permutations_per_instance": N_PERMS, "seed": SEED,
                   "slack": SLACK, "per_generator": gen, "method_level": meth}, fh,
                  indent=1, sort_keys=True)
    print(f"\n[{time.time()-t0:7.1f}s] wrote shuffle report", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
