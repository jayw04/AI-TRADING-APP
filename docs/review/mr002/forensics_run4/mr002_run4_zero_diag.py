"""MR-002 run-4 STOP forensics — stage 3: test the negative-zero hypothesis.

READ-ONLY. Hypothesis: (-0.0).as_integer_ratio() == (0, 1) loses the sign bit;
replay rebuilds +0.0; rec_content_hash covers raw float64 bytes, so any record
whose canonical input contained -0.0 fails INPUT_RATIOS_DO_NOT_MATCH_CONTENT_HASH.
Prediction: defect status correlates EXACTLY with presence of a [0, 1] ratio
(a zero) in the input — modulo records whose zeros were all +0.0.
Sharper test: for one failing record, brute-force the hash over sign choices is
infeasible; instead we check correlation + demonstrate the mechanism.
"""
import importlib.util
import json
import sys

CHECKPOINT = "/out/cleanrun/MR002_Stage3_CleanRun_checkpoint.jsonl"
RUNNER = "/work/apps/backend/scripts/mr002_stage3_population_runner.py"

spec = importlib.util.spec_from_file_location("runner", RUNNER)
runner = importlib.util.module_from_spec(spec)
sys.modules["runner"] = runner
spec.loader.exec_module(runner)

import numpy as np  # noqa: E402

print("mechanism check: (-0.0).as_integer_ratio() =", (-0.0).as_integer_ratio())
a = np.array([-0.0]); b = np.array([0.0])
print("tobytes equal for -0.0 vs 0.0:", a.tobytes() == b.tobytes())

state = runner.read_checkpoint(CHECKPOINT)
records = state["records"]

both = {"defect_and_zero": 0, "defect_no_zero": 0, "clean_and_zero": 0, "clean_no_zero": 0}
examples = []
for idx, rec in enumerate(records):
    d = runner.verify_numerical_evidence_record(rec)
    has_zero = any(n == 0 for k in ("t", "A_ub", "b_ub", "A_eq", "b_eq", "upper")
                   for n, _dd in rec["input"][k]["exact_ratio"])
    key = (("defect" if d else "clean") + ("_and_zero" if has_zero else "_no_zero"))
    both[key] += 1
    if d and len(examples) < 2:
        zero_counts = {k: sum(1 for n, _dd in rec["input"][k]["exact_ratio"] if n == 0)
                       for k in ("t", "A_ub", "b_ub", "A_eq", "b_eq", "upper")}
        examples.append({"index": idx, "row_id": rec.get("row_id"),
                         "defect": d, "zero_counts_by_component": zero_counts})
    if idx % 1000 == 0:
        print(f"...{idx}/{len(records)}", flush=True)

print(json.dumps({"correlation": both, "examples": examples}, indent=1))
