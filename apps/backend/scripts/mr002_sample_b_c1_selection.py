"""MR-002 — corrected Sample B-C1 SELECTION amendment (owner ruling §6/§7/§8; cardinality = 100).

Reading (a) is adjudicated: canonical content-hash disjointness is required. The original frozen
Sample B is selection-defective (its index 1434 is the content-hash twin of Sample A's index 7) but
NOT mathematically failed; it is preserved unchanged as the historical selection. B-C1 is a
separately named, prospectively constructed corrected selection.

CARDINALITY = 100. The preregistered PROSPECTIVE_N = 100 controls; the earlier "50" references are
withdrawn (they carried Sample A's cardinality forward in error).

CONSTRUCTION (frozen, applied WITHOUT inspecting any repair outcome):
  1. Traverse the original Sample B candidates in their frozen order.
  2. Reject a candidate iff its canonical content hash appears in Sample A, or has already been
     accepted into B-C1.
  3. Preserve every other original candidate (it keeps its slot).
  4. Replace each rejected candidate with the next eligible candidate from the RESERVE ORDER, which
     is the deterministic continuation of the frozen selection generator: sorted(rest, key=content
     hash) beyond the original 100. Apply the same content-hash exclusions to every replacement.
  5. Continue until B-C1 holds exactly 100 unique hashes, all absent from Sample A.

§7 — the reserve order is derived ONLY from corpus identity and the original selection mechanism (the
content-hash sort), never from solver outcomes, dimensions, runtime, agreement margins or economic
data. It is frozen here, committed and hashed, and must be countersigned before any B-C1 repair runs.

§8 — the artifact proves cardinality 100, 100 unique hashes, 0 overlap with A, 0 internal duplicates,
0 unexplained changes from the original B, and replacement_count == rejected_count, with a row-by-row
mapping.

SELECTION ONLY. No repair is run, no certificate is produced, no performance is computed. Per §12,
after this is committed and sealed, STOP and present it for countersign before executing B-C1.
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
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

ARRAY_KEYS = ("t", "A_ub", "b_ub", "A_eq", "b_eq", "upper")


def arrays_identical(i: int, j: int) -> bool:
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

    # ---- reproduce the frozen selection procedure ----------------------------------------------
    print("reproducing the frozen selection (cascade qualification) ...")
    qual: list[int] = []
    for i, inst in enumerate(CORPUS):
        rec = (inst["t"], inst["A_ub"], inst["b_ub"], inst["A_eq"], inst["b_eq"], inst["upper"])
        if try_solve(PRIMARY, rec)[0] and try_solve(FALLBACK, rec)[0]:
            qual.append(i)
    sample_a = qual[:REGRESSION_N]
    rest = [i for i in qual if i not in set(sample_a)]
    # THE FROZEN GENERATOR: sorted(rest, key=content_hash). The original B is [:100]; the reserve is
    # the deterministic CONTINUATION [100:].
    generator = sorted(rest, key=lambda i: fixture_hash(CORPUS[i]))
    original_b = generator[:PROSPECTIVE_N]
    reserve = generator[PROSPECTIVE_N:]

    a_hashes = {fixture_hash(CORPUS[i]) for i in sample_a}
    print(f"  qualifying {len(qual)}  A {len(sample_a)}  original B {len(original_b)}  "
          f"reserve {len(reserve)}")

    # ---- construct B-C1 ------------------------------------------------------------------------
    bc1: list[int] = []
    accepted_hashes: set[str] = set()
    mapping: list[dict] = []
    reserve_ptr = 0

    def next_reserve() -> tuple[int, str] | None:
        nonlocal reserve_ptr
        while reserve_ptr < len(reserve):
            cand = reserve[reserve_ptr]
            reserve_ptr += 1
            h = fixture_hash(CORPUS[cand])
            if h in a_hashes or h in accepted_hashes:
                continue                       # same exclusions apply to replacements
            return cand, h
        return None

    n_rejected = 0
    for orig_pos, idx in enumerate(original_b):
        h = fixture_hash(CORPUS[idx])
        if h in a_hashes or h in accepted_hashes:
            reason = "content_hash_in_sample_a" if h in a_hashes else "duplicate_within_bc1"
            n_rejected += 1
            repl = next_reserve()
            if repl is None:
                print("STOP: reserve exhausted before 100 unique disjoint hashes — reporting the "
                      "shortfall, NOT relaxing eligibility (§6).", file=sys.stderr)
                return 1
            r_idx, r_h = repl
            bc1.append(r_idx)
            accepted_hashes.add(r_h)
            mapping.append({
                "original_b_position": orig_pos, "original_corpus_index": idx,
                "original_content_hash": h, "status": "rejected-duplicate", "reason": reason,
                "replacement_corpus_index": r_idx, "replacement_content_hash": r_h,
                "replacement_absent_from_A": r_h not in a_hashes,
                "replacement_absent_from_accepted": True,
            })
        else:
            bc1.append(idx)
            accepted_hashes.add(h)
            mapping.append({
                "original_b_position": orig_pos, "original_corpus_index": idx,
                "original_content_hash": h, "status": "retained",
                "replacement_corpus_index": None, "replacement_content_hash": None,
                "reason": "unique_and_absent_from_A",
            })

    # ---- §8 selection proof --------------------------------------------------------------------
    bc1_hashes = [fixture_hash(CORPUS[i]) for i in bc1]
    n_replacements = sum(1 for m in mapping if m["status"] == "rejected-duplicate")
    proof = {
        "cardinality": len(bc1),
        "unique_content_hashes": len(set(bc1_hashes)),
        "overlap_with_sample_a": len(set(bc1_hashes) & a_hashes),
        "internal_duplicate_hashes": len(bc1_hashes) - len(set(bc1_hashes)),
        "unexplained_changes_from_original_b": sum(
            1 for m in mapping if m["status"] == "retained"
            and m["original_corpus_index"] not in set(original_b)),
        "rejected_duplicate_count": n_rejected,
        "replacement_count": n_replacements,
    }
    ok = (proof["cardinality"] == PROSPECTIVE_N
          and proof["unique_content_hashes"] == PROSPECTIVE_N
          and proof["overlap_with_sample_a"] == 0
          and proof["internal_duplicate_hashes"] == 0
          and proof["unexplained_changes_from_original_b"] == 0
          and proof["replacement_count"] == proof["rejected_duplicate_count"])

    print("\n=== §8 selection proof ===")
    for k, v in proof.items():
        print(f"  {k:36} {v}")
    print("\n=== changes from original B (row-by-row, non-retained) ===")
    for m in mapping:
        if m["status"] != "retained":
            print(f"  pos {m['original_b_position']:3}: idx {m['original_corpus_index']} "
                  f"({m['original_content_hash'][:16]}) {m['status']} [{m['reason']}] -> "
                  f"idx {m['replacement_corpus_index']} ({m['replacement_content_hash'][:16]})")

    print("\n" + "=" * 74)
    print("  B-C1 SELECTION: " + ("VALID — ready for countersign" if ok else "INVALID — STOP"))
    print("=" * 74)

    doc = {
        "schema": "MR002_SampleBC1_Selection/v1",
        "authorization": "owner ruling 2026-07-14 §6/§7/§8 + cardinality correction (B-C1 = 100)",
        "selection_only": True, "no_repair_executed": True, "no_performance_computed": True,
        "cardinality_binding": {
            "target": PROSPECTIVE_N,
            "note": "PROSPECTIVE_N = 100 controls; the prior '50' references are withdrawn.",
        },
        "reserve_order_amendment": {
            "reserve_candidate_ordering": ("the deterministic continuation of the frozen selection "
                                           "generator: sorted(rest, key=canonical_content_hash) "
                                           "beyond the original 100"),
            "derived_only_from": "corpus identity (content hashes) + the original selection mechanism",
            "NOT_derived_from": ["solver outcomes", "problem dimensions", "runtime", "agreement "
                                 "margins", "economic data"],
            "duplicate_exclusion_rule": ("reject a candidate iff its content hash appears in Sample "
                                         "A or has already been accepted into B-C1; apply the same "
                                         "exclusions to every replacement"),
            "reserve_indices_consumed": reserve[:reserve_ptr],
        },
        "corpus_hash": ch,
        "sample_a": sample_a,
        "original_sample_b_preserved_unchanged": original_b,
        "sample_b_c1": bc1,
        "sample_b_c1_content_hashes": bc1_hashes,
        "row_by_row_mapping": mapping,
        "selection_proof": proof,
        "selection_valid": ok,
        "replacement_detail": [
            {**m,
             "replacement_arrays_differ_from_original": not arrays_identical(
                 m["original_corpus_index"], m["replacement_corpus_index"])}
            for m in mapping if m["status"] == "rejected-duplicate"
        ],
        "next_step": ("STOP for countersign. B-C1 repairs are NOT authorized until this selection "
                      "amendment is countersigned (§12)."),
        "validation_and_sealed_oos": "SEALED AND UNREAD",
    }
    blob = json.dumps(doc, indent=2, default=str)
    with open(f"{out_dir}/MR002_SampleBC1_Selection.json", "w", encoding="utf-8") as fh:
        fh.write(blob)
    print(f"\nselection sha256 {hashlib.sha256(blob.encode()).hexdigest()}")
    print(f"wrote {out_dir}/MR002_SampleBC1_Selection.json")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
