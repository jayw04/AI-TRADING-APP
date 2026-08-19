"""MR-002 Gate N1 — C4 (deterministic reproducibility) and C5 (runtime).

Sealed authority: MR002_N1_ProspectiveRegistration_v1.0 §5.3
identity 7f8a56e34e6d5d36a3914ecb825de015debdc83ebae2967887e5e37ca3d684af.

C4 has two registered parts:
  (a) two independent runs in the pinned image produce BYTE-IDENTICAL accepted z and identical
      dispositions;
  (b) canonical shuffle-invariance.

For (b), the instance's coordinates are permuted, the generator is run on the permuted problem, and
the result is mapped back. A shuffle-invariant generator returns the inverse-permuted solution
BYTE-IDENTICALLY. This is a real property, not a formality: a solver whose pivoting depends on
column order can return a different point for the same mathematical program, and the accepted point
IS the economic solution.

⚠ Shuffle-invariance is reported at two strengths, because they are different claims:
  EXACT   — byte-identical after inverse permutation
  BOUNDED — differs, but within the §4 agreement slack floor (1e-10), so the two points are provably
            the same minimiser to the registered resolution
Only EXACT satisfies "byte-identical". BOUNDED is reported so a near-miss is visible rather than
hidden inside a pass.

C5 measures wall-clock over repeats. A difference inside run-to-run noise is NOT a C5 decision —
it is reported as a tie, and per §5.3 a tie surviving C6 is an owner adjudication item, never a
coin flip.

Development domain only.
"""
from __future__ import annotations

import json
import os
import statistics
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
REPEATS = int(os.environ.get("N1_REPEATS", "3"))
SLACK = 1e-10


def load_corpus() -> list[dict]:
    d = np.load(CORPUS_NPZ, allow_pickle=False)
    if str(d["corpus_hash"]) != REGISTERED_CORPUS_HASH:
        raise SystemExit("ABORT: corpus hash mismatch")
    n = int(d["n_instances"])
    return [{k: d[f"{i}_{k}"] for k in ("t", "A_ub", "b_ub", "A_eq", "b_eq", "upper")}
            for i in range(n)]


def rec_of(inst: dict) -> tuple:
    return (inst["t"], inst["A_ub"], inst["b_ub"], inst["A_eq"], inst["b_eq"], inst["upper"])


def permuted(rec: tuple, perm: np.ndarray) -> tuple:
    t, A_ub, b_ub, A_eq, b_eq, upper = rec
    return (t[perm], A_ub[:, perm], b_ub, A_eq[:, perm], b_eq, upper[perm])


def main() -> int:
    t0 = time.time()
    limit = int(os.environ.get("N1_LIMIT", "0"))
    from scripts.mr002_coverage_signed_gap import SOLVERS, canonical_qualify

    corpus = load_corpus()
    if limit:
        corpus = corpus[:limit]
    print(f"[{time.time()-t0:7.1f}s] corpus verified, {len(corpus)} instances, "
          f"{REPEATS} repeats", flush=True)

    report: dict[str, dict] = {}

    for profile in (A_PROFILE, *B_CANDIDATES):
        runs: list[list[tuple]] = []
        times: list[float] = []
        for r in range(REPEATS):
            tr = time.time()
            sig = []
            for inst in corpus:
                o = M.normalize(profile, SOLVERS[profile], canonical_qualify, rec_of(inst))
                sig.append((o.outcome, o.reason,
                            None if o.z is None else np.asarray(o.z, float).tobytes()))
            times.append(time.time() - tr)
            runs.append(sig)
            print(f"[{time.time()-t0:7.1f}s]   {profile} run {r+1}/{REPEATS}: "
                  f"{times[-1]:.1f}s", flush=True)

        identical = all(runs[0] == runs[k] for k in range(1, REPEATS))
        mismatches = [i for i in range(len(corpus)) if any(runs[0][i] != runs[k][i]
                                                           for k in range(1, REPEATS))]

        # ── shuffle invariance ──────────────────────────────────────────────────────────────────
        rng = np.random.Generator(np.random.PCG64(20260819))
        exact = bounded = differs = skipped = 0
        worst = 0.0
        for inst in corpus:
            rec = rec_of(inst)
            n = len(rec[0])
            if n < 2:
                skipped += 1
                continue
            base = M.normalize(profile, SOLVERS[profile], canonical_qualify, rec)
            if not base.is_certified:
                skipped += 1
                continue
            perm = rng.permutation(n)
            inv = np.argsort(perm)
            o = M.normalize(profile, SOLVERS[profile], canonical_qualify, permuted(rec, perm))
            if not o.is_certified:
                differs += 1
                continue
            back = np.asarray(o.z, float)[inv]
            if back.tobytes() == np.asarray(base.z, float).tobytes():
                exact += 1
            else:
                d = float(np.linalg.norm(back - np.asarray(base.z, float)))
                worst = max(worst, d)
                if d <= SLACK:
                    bounded += 1
                else:
                    differs += 1

        report[profile] = {
            "C4a_runs_identical": identical,
            "C4a_mismatched_instances": mismatches[:20],
            "C4b_shuffle_exact": exact,
            "C4b_shuffle_bounded_not_exact": bounded,
            "C4b_shuffle_differs_beyond_slack": differs,
            "C4b_skipped": skipped,
            "C4b_worst_deviation": worst,
            "C4_pass": identical and differs == 0,
            "C4_pass_strict_byte_identical": identical and differs == 0 and bounded == 0,
            "C5_times_seconds": [round(x, 2) for x in times],
            "C5_median_seconds": round(statistics.median(times), 2),
            "C5_min_seconds": round(min(times), 2),
        }
        r = report[profile]
        print(f"[{time.time()-t0:7.1f}s] {profile}: C4a identical={identical} "
              f"shuffle exact={exact} bounded={bounded} differs={differs} skipped={skipped} "
              f"worst={worst:.2e} | C5 median={r['C5_median_seconds']}s", flush=True)

    # ── C5 comparison between the C2 survivors ──────────────────────────────────────────────────
    meds = {c: report[c]["C5_median_seconds"] for c in B_CANDIDATES}
    spread = {c: max(report[c]["C5_times_seconds"]) - min(report[c]["C5_times_seconds"])
              for c in B_CANDIDATES}
    fastest = min(meds, key=meds.get)
    gap = abs(meds[B_CANDIDATES[0]] - meds[B_CANDIDATES[1]])
    noise = max(spread.values())
    report["_C5_comparison"] = {
        "medians": meds,
        "within_candidate_spread": spread,
        "median_gap": round(gap, 2),
        "gap_exceeds_noise": gap > noise,
        "fastest": fastest,
        "verdict": (f"{fastest} is faster" if gap > noise
                    else "TIE — the median gap does not exceed run-to-run spread; "
                         "not a C5 decision"),
    }
    print(f"\nC5: medians={meds} spread={spread} gap={gap:.2f} noise={noise:.2f}")
    print(f"C5 verdict: {report['_C5_comparison']['verdict']}")

    os.makedirs(OUT_DIR, exist_ok=True)
    suffix = f"_limit{limit}" if limit else ""
    with open(os.path.join(OUT_DIR, f"n1_c4c5{suffix}.json"), "w") as fh:
        json.dump(report, fh, indent=1, sort_keys=True)
    print(f"\n[{time.time()-t0:7.1f}s] wrote C4/C5 report", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
