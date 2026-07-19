"""MR-002 run-4 STOP forensics — stage 5: element-level diff, true corpus vs replay.

READ-ONLY. Rebuilds the corpus from the DuckDB via the runner's own
production_corpus_source (same code path the run used), then for failing records
compares the canonical arrays byte-for-byte against arrays rebuilt from the
serialized exact ratios. Reports every differing element: component, flat index,
canonical value/signbit/bits vs replay value/signbit/bits.
"""
import importlib.util
import json
import struct
import sys

CHECKPOINT = "/out/cleanrun/MR002_Stage3_CleanRun_checkpoint.jsonl"
RUNNER = "/work/apps/backend/scripts/mr002_stage3_population_runner.py"

spec = importlib.util.spec_from_file_location("runner", RUNNER)
runner = importlib.util.module_from_spec(spec)
sys.modules["runner"] = runner
spec.loader.exec_module(runner)

import numpy as np  # noqa: E402

KEYS = ("t", "A_ub", "b_ub", "A_eq", "b_eq", "upper")

def bits(x):
    return struct.pack("<d", float(x)).hex()

print("rebuilding corpus from DB (same code path as the run)...", flush=True)
rows, corpus_hash, row_manifest, prov = runner.production_corpus_source()
print(f"corpus rebuilt: n_rows={len(rows)} corpus_hash={corpus_hash}", flush=True)

state = runner.read_checkpoint(CHECKPOINT)
records = state["records"]
print(f"manifest_match_vs_run: corpus_hash_equal="
      f"{corpus_hash == '1d2319301a7b52dfe369819bc8029f7b6d64ad820d828f041eba15a91348390b'}",
      flush=True)

reported = 0
diff_summary = {}
for idx, rec in enumerate(records):
    if runner.verify_numerical_evidence_record(rec) is None:
        continue
    row_id, canon = rows[idx]
    assert row_id == rec.get("row_id"), (row_id, rec.get("row_id"))
    diffs = []
    for k, arr in zip(KEYS, canon, strict=True):
        e = rec["input"][k]
        replay = np.array([n / d for n, d in e["exact_ratio"]],
                          dtype=np.float64).reshape(e["shape"])
        a = np.ascontiguousarray(np.asarray(arr, dtype=np.float64))
        if a.tobytes() != replay.tobytes():
            fa, fr = a.ravel(), replay.ravel()
            for j in range(fa.size):
                if bits(fa[j]) != bits(fr[j]):
                    diffs.append({"component": k, "flat_index": j,
                                  "canonical": repr(float(fa[j])), "canonical_bits": bits(fa[j]),
                                  "replay": repr(float(fr[j])), "replay_bits": bits(fr[j])})
    kinds = {(d["canonical"], d["replay"]) for d in diffs}
    diff_summary[idx] = {"n_diffs": len(diffs), "kinds": sorted(map(list, kinds))}
    if reported < 3:
        print(json.dumps({"index": idx, "row_id": row_id,
                          "n_diffs": len(diffs), "first_5": diffs[:5]}, indent=1), flush=True)
    reported += 1
    if reported >= 40:
        break

all_kinds = {}
for v in diff_summary.values():
    for kk in map(tuple, v["kinds"]):
        all_kinds[kk] = all_kinds.get(kk, 0) + 1
print("DIFF KINDS ACROSS SAMPLED FAILING RECORDS (canonical -> replay : n_records):")
for kk, n in sorted(all_kinds.items(), key=lambda t: -t[1]):
    print(f"  {kk[0]} -> {kk[1]} : {n}")
