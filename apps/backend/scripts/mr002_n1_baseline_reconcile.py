"""MR-002 Gate N1 — reconcile the v1 baseline: governed 3891/4 vs regenerated 3890/5.

Owner ruling 2026-08-19: the authoritative Condition-8 referent is the GOVERNED v1 DEVELOPMENT
QUALIFICATION (3891 PRIMARY_QUALIFIED / 4 FALLBACK_QUALIFIED), not the earlier fallback-selection
bakeoff — because §4.4 asks what the v1 METHOD ACCEPTED, and the bakeoff was a candidate-selection
artifact.

⛔ The prohibited move is "both records exist; pick the one N1 currently reproduces." So this does
not adjust anything. It re-runs the governed qualification's own experiment and reports what comes
back.

WHY THE TWO NUMBERS CAN BOTH BE HONEST. They are not measurements of the same thing:

  bakeoff corpus      instances captured by the SELECTION capture device (raw -> sqrt -> tscaled,
                      then an LP diagnostic), whose accepted point feeds forward into the next
                      session's state
  governed replay     instances produced by the v1 CASCADE itself (QUADPROG_SQRT -> PIQP_P2), whose
                      accepted point feeds forward instead

Where the two devices accept different points, every LATER instance in that config can differ. So a
one-instance disposition difference between them is not by itself evidence that either record is
wrong. This run settles it by reproducing the governed experiment directly.

Localisation already established: config B (3 fallbacks) and config C (0) agree exactly; the whole
discrepancy is ONE instance in config A, between corpus rows 800 and 1328.

Development domain only. No sealed reader, no validation store, no OOS.
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
import time
from datetime import date

import numpy as np

sys.path.insert(0, "/work/apps/backend")

import app.research.mr002.joint_portfolio as jp  # noqa: E402
from app.research.mr002 import stage3_route as sr  # noqa: E402

OUT_DIR = "/work/.mr002out/n1"
WINDOW = (date(2013, 1, 2), date(2019, 10, 2))
COUNTERSIGNATURE = "MR002_Stage3ExecutionCountersignature_v1.0"

#: What the governed development qualification recorded, per config.
GOVERNED = {
    "A": {"PRIMARY_QUALIFIED": 1426, "FALLBACK_QUALIFIED": 1, "invocations": 1427},
    "B": {"PRIMARY_QUALIFIED": 1532, "FALLBACK_QUALIFIED": 3, "invocations": 1535},
    "C": {"PRIMARY_QUALIFIED": 933, "FALLBACK_QUALIFIED": 0, "invocations": 933},
}


def _hash_instance(t, A_ub, b_ub, A_eq, b_eq, upper) -> str:
    """The registered per-instance content hash — same construction as the bakeoff corpus."""
    h = hashlib.sha256()
    for arr in (t, A_ub, b_ub, A_eq, b_eq, upper):
        a = np.ascontiguousarray(np.asarray(arr, dtype=np.float64))
        h.update(str(a.shape).encode())
        h.update(a.tobytes())
    return h.hexdigest()


def main() -> int:
    t0 = time.time()
    from app.research.mr002.dataset import FrozenDataset
    from app.research.mr002.runner import CONFIGS
    from scripts.mr002_development_run import run_config

    ds = FrozenDataset("/work/apps/backend/data/mr002_research.duckdb")
    days = ds.day_inputs(*WINDOW)
    print(f"[{time.time()-t0:7.1f}s] loaded {len(days)} development sessions", flush=True)

    # corpus row hashes, so a fallback invocation here can be matched to a bakeoff corpus row
    corpus_hashes: dict[str, int] = {}
    npz = os.path.join(OUT_DIR, "corpus.npz")
    if os.path.exists(npz):
        d = np.load(npz, allow_pickle=False)
        for i in range(int(d["n_instances"])):
            corpus_hashes[str(d[f"{i}_hash"])] = i
        print(f"[{time.time()-t0:7.1f}s] loaded {len(corpus_hashes)} bakeoff corpus row hashes",
              flush=True)

    report: dict = {"per_config": {}, "governed_recorded": GOVERNED}
    total: dict[str, int] = {}

    for name in ("A", "B", "C"):
        census: list = []
        hashes: list[str] = []

        # Use the countersigned seam itself and ADD OBSERVATION ONLY — the seam is not re-derived.
        with sr.routed(census, countersignature=COUNTERSIGNATURE):
            inner = jp._solve_qp

            def observing(H_diag, targets, A_ub, b_ub, A_eq, b_eq, upper,
                          _inner=inner, _hashes=hashes):
                _hashes.append(_hash_instance(targets, A_ub, b_ub, A_eq, b_eq, upper))
                return _inner(H_diag, targets, A_ub, b_ub, A_eq, b_eq, upper)

            jp._solve_qp = observing
            try:
                run_config(days, CONFIGS[name])
            finally:
                jp._solve_qp = inner

        summary = sr.census_summary(census)
        by = summary["by_disposition"]
        fb_rows = []
        for k, row in enumerate(census):
            if row.get("fallback_invoked"):
                h = hashes[k] if k < len(hashes) else None
                fb_rows.append({"invocation_index": k, "instance_hash": h,
                                "bakeoff_corpus_row": corpus_hashes.get(h),
                                "disposition": row["disposition"],
                                "accepted_by": row.get("accepted_by")})

        # every instance this config solved, matched back to the bakeoff corpus
        matched = [corpus_hashes.get(h) for h in hashes]
        unmatched = sum(1 for m in matched if m is None)

        rec = {
            "invocations": summary["invocations"],
            "by_disposition": by,
            "by_accepted_by": summary["by_accepted_by"],
            "fallback_invoked": summary["fallback_invoked"],
            "stop_dispositions": summary["stop_dispositions"],
            "unrecognized_outcomes": summary["unrecognized_outcomes"],
            "governed_recorded": GOVERNED[name],
            "matches_governed": (
                by.get("PRIMARY_QUALIFIED", 0) == GOVERNED[name]["PRIMARY_QUALIFIED"]
                and by.get("FALLBACK_QUALIFIED", 0) == GOVERNED[name]["FALLBACK_QUALIFIED"]
                and summary["invocations"] == GOVERNED[name]["invocations"]),
            "fallback_instances": fb_rows,
            "instances_not_present_in_bakeoff_corpus": unmatched,
        }
        report["per_config"][name] = rec
        for k, v in by.items():
            total[k] = total.get(k, 0) + v

        print(f"[{time.time()-t0:7.1f}s] config {name}: inv={rec['invocations']} {by} "
              f"-> governed {GOVERNED[name]} : "
              f"{'MATCH' if rec['matches_governed'] else '*** DIFFERS ***'}  "
              f"(instances not in bakeoff corpus: {unmatched})", flush=True)
        for r in fb_rows:
            print(f"      fallback at invocation {r['invocation_index']} "
                  f"bakeoff_row={r['bakeoff_corpus_row']}", flush=True)

    report["total"] = total
    report["governed_total"] = {"PRIMARY_QUALIFIED": 3891, "FALLBACK_QUALIFIED": 4}
    report["reproduces_governed_total"] = (
        total.get("PRIMARY_QUALIFIED") == 3891 and total.get("FALLBACK_QUALIFIED") == 4)

    print(f"\nTOTAL          {total}")
    print(f"GOVERNED       {report['governed_total']}")
    print(f"REPRODUCES     {report['reproduces_governed_total']}")

    os.makedirs(OUT_DIR, exist_ok=True)
    with open(os.path.join(OUT_DIR, "n1_baseline_reconcile.json"), "w") as fh:
        json.dump(report, fh, indent=1, sort_keys=True)
    print(f"\n[{time.time()-t0:7.1f}s] wrote baseline reconciliation", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
