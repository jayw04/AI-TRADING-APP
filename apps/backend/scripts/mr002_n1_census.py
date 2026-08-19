"""MR-002 Gate N1 — the development census (C1/C2 stage).

Sealed authority: MR002_N1_ProspectiveRegistration_v1.0
identity 7f8a56e34e6d5d36a3914ecb825de015debdc83ebae2967887e5e37ca3d684af.

Scores each admissible Solver-B candidate as the pair (A = QUADPROG_SQRT, B) over the registered
3,895-instance development corpus under the certificate-driven v2 method, and reports the
lexicographic hard gates that do not require Reference Solver R:

    C1  zero SYSTEM_INTEGRITY_DEFECT over the corpus
    C2  100% certified resolution (PRIMARY_CERTIFIED or SECONDARY_CERTIFIED), zero
        UNRESOLVED_INSTANCE, zero INVALID_RUN

plus the advance conditions UNREGISTERED_TERMINATION_REASON == 0 and the raw material for the
SA-2 both-certified uniqueness test.

⛔ C3 (agreement with Reference Solver R) and the §4.4 equivalence gate are SEPARATE stages. A
candidate passing here has NOT passed N1.

A is evaluated ONCE per instance and reused across candidates: A's outcome cannot depend on which B
it is paired with, and recomputing it would invite a discrepancy that means nothing.

Development domain only. Opens no sealed reader, no validation store, no OOS.
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
#: §5.2 frozen admissible candidate set, in the registration's listed order.
B_CANDIDATES = ("PIQP_P1", "PIQP_P2", "CLARABEL")


def load_corpus() -> list[dict]:
    d = np.load(CORPUS_NPZ, allow_pickle=False)
    got = str(d["corpus_hash"])
    if got != REGISTERED_CORPUS_HASH:
        raise SystemExit(f"ABORT: corpus hash {got} != registered {REGISTERED_CORPUS_HASH}")
    n = int(d["n_instances"])
    return [{k: d[f"{i}_{k}"] for k in ("t", "A_ub", "b_ub", "A_eq", "b_eq", "upper")}
            | {"hash": str(d[f"{i}_hash"])} for i in range(n)]


def rec_of(inst: dict) -> tuple:
    return (inst["t"], inst["A_ub"], inst["b_ub"], inst["A_eq"], inst["b_eq"], inst["upper"])


def outcome_row(o: M.GenOutcome) -> dict:
    return {
        "outcome": o.outcome, "reason": o.reason, "detail": o.detail[:160],
        "provenance": o.provenance, "exception_class": o.exception_class,
        "owning_module": o.owning_module, "literal_outcome": o.literal_outcome,
    }


def main() -> int:
    t0 = time.time()
    limit = int(os.environ.get("N1_LIMIT", "0"))

    from scripts.mr002_coverage_signed_gap import SOLVERS, canonical_qualify

    corpus = load_corpus()
    if limit:
        corpus = corpus[:limit]
    print(f"[{time.time()-t0:7.1f}s] corpus verified, {len(corpus)} instances", flush=True)

    # ── Solver A, once ──────────────────────────────────────────────────────────────────────────
    a_out: list[M.GenOutcome] = []
    for i, inst in enumerate(corpus):
        a_out.append(M.normalize(A_PROFILE, SOLVERS[A_PROFILE], canonical_qualify, rec_of(inst)))
        if (i + 1) % 250 == 0:
            print(f"[{time.time()-t0:7.1f}s]   A {i+1}/{len(corpus)}", flush=True)
    a_cert = sum(1 for o in a_out if o.is_certified)
    print(f"[{time.time()-t0:7.1f}s] A={A_PROFILE}: certified {a_cert}/{len(corpus)}", flush=True)

    results: dict[str, dict] = {}
    census: dict[str, list[dict]] = {}

    for cand in B_CANDIDATES:
        tb = time.time()
        rows: list[dict] = []
        counts = {"disposition": {}, "b_outcome": {}, "b_reason": {},
                  "literal_divergence": 0, "unregistered": 0,
                  "both_certified": 0, "system_integrity_defect": 0}

        for i, inst in enumerate(corpus):
            a = a_out[i]
            rec = rec_of(inst)

            if a.outcome == M.SYSTEM_INTEGRITY_DEFECT:
                disp, b, acc = M.INVALID_RUN, None, None
            else:
                b = M.normalize(cand, SOLVERS[cand], canonical_qualify, rec)
                if b.outcome == M.SYSTEM_INTEGRITY_DEFECT:
                    disp, acc = M.INVALID_RUN, None
                elif a.is_certified:
                    disp, acc = M.PRIMARY_CERTIFIED, A_PROFILE
                elif b.is_certified:
                    disp, acc = M.SECONDARY_CERTIFIED, cand
                else:
                    disp, acc = M.UNRESOLVED_INSTANCE, None

            counts["disposition"][disp] = counts["disposition"].get(disp, 0) + 1
            if b is not None:
                counts["b_outcome"][b.outcome] = counts["b_outcome"].get(b.outcome, 0) + 1
                if b.reason:
                    counts["b_reason"][b.reason] = counts["b_reason"].get(b.reason, 0) + 1
                if b.outcome != b.literal_outcome:
                    counts["literal_divergence"] += 1
                if b.reason == M.UNREGISTERED_TERMINATION_REASON:
                    counts["unregistered"] += 1
                if b.outcome == M.SYSTEM_INTEGRITY_DEFECT:
                    counts["system_integrity_defect"] += 1
                if a.is_certified and b.is_certified:
                    counts["both_certified"] += 1

            rows.append({
                "i": i, "hash": inst["hash"], "n": int(len(inst["t"])),
                "disposition": disp, "accepted_by": acc,
                "A": outcome_row(a), "B": outcome_row(b) if b is not None else None,
            })
            if (i + 1) % 250 == 0:
                print(f"[{time.time()-t0:7.1f}s]   {cand} {i+1}/{len(corpus)}", flush=True)

        if a_out and a_out[0].outcome != a_out[0].literal_outcome:
            pass
        counts["A_literal_divergence"] = sum(
            1 for o in a_out if o.outcome != o.literal_outcome)
        counts["A_unregistered"] = sum(
            1 for o in a_out if o.reason == M.UNREGISTERED_TERMINATION_REASON)
        counts["A_system_integrity_defect"] = sum(
            1 for o in a_out if o.outcome == M.SYSTEM_INTEGRITY_DEFECT)

        resolved = sum(counts["disposition"].get(d, 0) for d in M.RESOLVED_DISPOSITIONS)
        sid = counts["system_integrity_defect"] + counts["A_system_integrity_defect"]
        unreg = counts["unregistered"] + counts["A_unregistered"]
        verdict = {
            "candidate": cand,
            "instances": len(corpus),
            "C1_zero_integrity_defects": sid == 0,
            "C1_system_integrity_defects": sid,
            "C2_full_resolution": resolved == len(corpus),
            "C2_resolved": resolved,
            "unresolved_instances": counts["disposition"].get(M.UNRESOLVED_INSTANCE, 0),
            "invalid_runs": counts["disposition"].get(M.INVALID_RUN, 0),
            "advance_unregistered_termination_reason": unreg,
            "both_certified_pairs_for_SA2": counts["both_certified"],
            "literal_rule_divergence": counts["literal_divergence"] + counts["A_literal_divergence"],
            "counts": counts,
            "seconds": round(time.time() - tb, 1),
        }
        results[cand] = verdict
        census[cand] = rows
        print(f"[{time.time()-t0:7.1f}s] {cand}: C1={'PASS' if sid==0 else f'FAIL({sid})'} "
              f"C2={'PASS' if resolved==len(corpus) else f'FAIL({resolved}/{len(corpus)})'} "
              f"unreg={unreg} both_certified={counts['both_certified']} "
              f"literal_divergence={verdict['literal_rule_divergence']} "
              f"({verdict['seconds']}s)", flush=True)

    os.makedirs(OUT_DIR, exist_ok=True)
    suffix = f"_limit{limit}" if limit else ""
    with open(os.path.join(OUT_DIR, f"n1_census_c1c2{suffix}.json"), "w") as fh:
        json.dump({"corpus_hash": REGISTERED_CORPUS_HASH, "instances": len(corpus),
                   "A_profile": A_PROFILE, "A_certified": a_cert,
                   "results": results}, fh, indent=1, sort_keys=True)
    with open(os.path.join(OUT_DIR, f"n1_census_rows{suffix}.json"), "w") as fh:
        json.dump(census, fh, indent=0, sort_keys=True)
    print(f"\n[{time.time()-t0:7.1f}s] wrote census to {OUT_DIR}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
