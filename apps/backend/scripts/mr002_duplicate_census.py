"""MR-002 — CANONICAL CONTENT-HASH DUPLICATE CENSUS (owner ruling 2026-07-14 §5).

Reading (a) is adjudicated: canonical CONTENT-HASH disjointness is required between Sample A and
Sample B. Index identity is not problem identity — indices 7 and 1434 are byte-identical canonical
problems at different corpus positions. Before a corrected Sample B (B-C1) may be constructed, a
COMPLETE census over all 3,895 positions is required, because fixing only the first discovered
collision could leave another hidden A-to-B overlap or an internal Sample-B duplicate.

This is SELECTION-ONLY evidence. No repair is run, no certificate is produced, no performance is
computed. The corpus is NOT deduplicated, renumbered, or altered — both indices of every duplicate
class are preserved and recorded as belonging to the same canonical-problem equivalence class (§4).

Reports (§5):
  total corpus rows / unique canonical hashes / duplicate classes / rows in duplicate classes /
  max multiplicity; every within-A duplicate; every within-original-B duplicate; every A-to-B hash
  overlap. For each duplicate class: the canonical content hash, all corpus indices, byte-identical
  array verification, and the canonical serialization version. The index 7 / index 1434 pair must
  reproduce exactly.
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
from collections import defaultdict
from datetime import date

import numpy as np

sys.path.insert(0, "/work/apps/backend")

import app.research.mr002.joint_portfolio as jp  # noqa: E402
from scripts.mr002_coverage_signed_gap import (  # noqa: E402
    CORPUS,
    FALLBACK,
    PRIMARY,
    PROSPECTIVE_N,
    REGRESSION_N,
    capture,
    fixture_hash,
    try_solve,
)
from scripts.mr002_solver_intersection import REGISTERED_CORPUS_HASH  # noqa: E402

CANONICAL_SERIALIZATION_VERSION = "MR002|stage3|canonical-original-problem|v1"
ARRAY_KEYS = ("t", "A_ub", "b_ub", "A_eq", "b_eq", "upper")


def arrays_identical(i: int, j: int) -> bool:
    """Byte-identical across every canonical array — the strict test the ruling requires (§5)."""
    return all(
        np.array_equal(np.ascontiguousarray(np.asarray(CORPUS[i][k], np.float64)),
                       np.ascontiguousarray(np.asarray(CORPUS[j][k], np.float64)))
        for k in ARRAY_KEYS
    )


def main() -> int:  # noqa: PLR0915
    out_dir = os.environ.get("MR002_OUT", "/out")
    jp._solve_qp = capture
    from app.research.mr002.dataset import FrozenDataset
    from app.research.mr002.runner import CONFIGS
    from scripts.mr002_development_run import run_config

    ds = FrozenDataset("/work/apps/backend/data/mr002_research.duckdb")
    days = ds.day_inputs(date(2013, 1, 2), date(2019, 10, 2))
    for cfg in ("A", "B", "C"):
        run_config(days, CONFIGS[cfg])

    ch = hashlib.sha256("|".join(i["hash"] for i in CORPUS).encode()).hexdigest()
    print(f"corpus {len(CORPUS)}  hash {ch}")
    if ch != REGISTERED_CORPUS_HASH:
        print("ABORT: corpus hash mismatch", file=sys.stderr)
        return 1
    print("[ok] corpus reproduced EXACTLY\n")

    # ---- census over ALL 3,895 positions --------------------------------------------------------
    by_hash: dict[str, list[int]] = defaultdict(list)
    for i in range(len(CORPUS)):
        by_hash[fixture_hash(CORPUS[i])].append(i)

    dup_classes = {h: idxs for h, idxs in by_hash.items() if len(idxs) > 1}
    rows_in_dups = sum(len(v) for v in dup_classes.values())
    max_mult = max((len(v) for v in by_hash.values()), default=0)

    print("=== census ===")
    print(f"  total corpus rows            {len(CORPUS)}")
    print(f"  unique canonical hashes      {len(by_hash)}")
    print(f"  duplicate equivalence classes {len(dup_classes)}")
    print(f"  rows in duplicate classes    {rows_in_dups}")
    print(f"  maximum multiplicity         {max_mult}")

    # ---- reproduce the frozen A / original-B split (the SELECTION, not repairs) -----------------
    print("\nresolving the cascade to reproduce the A / B split ...")
    qual: list[int] = []
    for i, inst in enumerate(CORPUS):
        rec = (inst["t"], inst["A_ub"], inst["b_ub"], inst["A_eq"], inst["b_eq"], inst["upper"])
        if try_solve(PRIMARY, rec)[0] and try_solve(FALLBACK, rec)[0]:
            qual.append(i)
    sample_a = qual[:REGRESSION_N]
    rest = [i for i in qual if i not in set(sample_a)]
    orig_b = sorted(rest, key=lambda i: fixture_hash(CORPUS[i]))[:PROSPECTIVE_N]

    a_hashes = {fixture_hash(CORPUS[i]): i for i in sample_a}
    b_hashes: dict[str, list[int]] = defaultdict(list)
    for i in orig_b:
        b_hashes[fixture_hash(CORPUS[i])].append(i)

    within_a = {h: idxs for h, idxs in
                ((h, [i for i in sample_a if fixture_hash(CORPUS[i]) == h])
                 for h in {fixture_hash(CORPUS[i]) for i in sample_a}) if len(idxs) > 1}
    within_b = {h: idxs for h, idxs in b_hashes.items() if len(idxs) > 1}
    a_to_b = {h: {"A_index": a_hashes[h], "B_indices": b_hashes[h]}
              for h in set(a_hashes) & set(b_hashes)}

    print(f"\n  qualifying overlaps          {len(qual)}")
    print(f"  Sample A size                {len(sample_a)}")
    print(f"  original Sample B size       {len(orig_b)}   (preregistration PROSPECTIVE_N="
          f"{PROSPECTIVE_N})")
    print(f"  within-A duplicate classes   {len(within_a)}")
    print(f"  within-original-B duplicates {len(within_b)}")
    print(f"  A-to-original-B hash overlaps {len(a_to_b)}")
    for h, rec in a_to_b.items():
        for bi in rec["B_indices"]:
            ident = arrays_identical(rec["A_index"], bi)
            print(f"    hash {h[:20]} : A idx {rec['A_index']} <-> B idx {bi}  "
                  f"arrays_identical={ident}")

    # the ruling's required reproduction check
    pair_ok = (fixture_hash(CORPUS[7]) == fixture_hash(CORPUS[1434]) and arrays_identical(7, 1434))
    print(f"\n  index 7 / index 1434 reproduce as the same problem: {pair_ok}")

    # ---- full duplicate-class detail (every class, both indices preserved) ----------------------
    class_detail = []
    for h, idxs in sorted(dup_classes.items()):
        pairwise = all(arrays_identical(idxs[0], j) for j in idxs[1:])
        class_detail.append({
            "canonical_content_hash": h, "corpus_indices": idxs,
            "multiplicity": len(idxs), "byte_identical": pairwise,
            "canonical_serialization_version": CANONICAL_SERIALIZATION_VERSION,
            "in_sample_a": [i for i in idxs if i in set(sample_a)],
            "in_original_sample_b": [i for i in idxs if i in set(orig_b)],
        })

    ok = pair_ok
    print("\n" + "=" * 74)
    print("  DUPLICATE CENSUS: " + ("COMPLETE" if ok else "REPRODUCTION FAILED"))
    print("=" * 74)

    doc = {
        "schema": "MR002_DuplicateCensus/v1",
        "authorization": "owner ruling 2026-07-14 §5 (reading (a): content-hash disjointness)",
        "selection_only": True, "no_repair_executed": True, "no_performance_computed": True,
        "corpus_immutable": ("corpus NOT deduplicated/renumbered; both indices of every duplicate "
                             "class are preserved and recorded as one canonical-problem class (§4)"),
        "corpus_hash": ch,
        "canonical_serialization_version": CANONICAL_SERIALIZATION_VERSION,
        "totals": {
            "total_corpus_rows": len(CORPUS),
            "unique_canonical_hashes": len(by_hash),
            "duplicate_equivalence_classes": len(dup_classes),
            "rows_in_duplicate_classes": rows_in_dups,
            "maximum_multiplicity": max_mult,
        },
        "selection": {
            "qualifying_overlaps": len(qual),
            "sample_a_size": len(sample_a),
            "original_sample_b_size": len(orig_b),
            "preregistration_prospective_n": PROSPECTIVE_N,
            "preregistration_regression_n": REGRESSION_N,
        },
        "within_sample_a_duplicates": within_a,
        "within_original_sample_b_duplicates": within_b,
        "a_to_original_b_overlaps": a_to_b,
        "index_7_1434_pair_reproduced": pair_ok,
        "duplicate_classes": class_detail,
        "sample_a": sample_a,
        "original_sample_b": orig_b,
        "cardinality_note": (
            f"the ruling §6/§8 specifies Sample B-C1 cardinality = 50, but the preregistration set "
            f"PROSPECTIVE_N = {PROSPECTIVE_N}, so the original Sample B was {len(orig_b)}. This "
            f"discrepancy is SURFACED, not resolved here — B-C1 construction awaits the owner's "
            f"target cardinality."),
    }
    blob = json.dumps(doc, indent=2, default=str)
    with open(f"{out_dir}/MR002_DuplicateCensus.json", "w", encoding="utf-8") as fh:
        fh.write(blob)
    print(f"\ncensus sha256 {hashlib.sha256(blob.encode()).hexdigest()}")
    print(f"wrote {out_dir}/MR002_DuplicateCensus.json")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
