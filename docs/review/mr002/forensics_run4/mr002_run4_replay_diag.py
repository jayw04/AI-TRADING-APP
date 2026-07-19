"""MR-002 run-4 STOP forensics — stage 2: numerical replay of every checkpoint record.

READ-ONLY. Runs inside the pinned Stage-3 image with /work and /out mounted ro.
Imports the bound runner module and calls verify_numerical_evidence_record on each
durable record, reporting every defect (record index, row_id, defect string).
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

state = runner.read_checkpoint(CHECKPOINT)
records = state["records"]
print(f"n_records={len(records)} corruption={state['corruption'][:3]} "
      f"trailing_partial={state['trailing_partial']} "
      f"terminal_status={state['terminal'].get('status') if state['terminal'] else None}",
      flush=True)

defects = []
for idx, rec in enumerate(records):
    d = runner.verify_numerical_evidence_record(rec)
    if d is not None:
        defects.append({"index": idx, "row_id": rec.get("row_id"), "defect": d})
        if len(defects) <= 3:
            print(f"DEFECT index={idx} row_id={rec.get('row_id')} defect={d}", flush=True)
    if idx % 500 == 0:
        print(f"...progress {idx}/{len(records)} defects_so_far={len(defects)}", flush=True)

print(json.dumps({"n_records": len(records), "n_defects": len(defects),
                  "defects_first_20": defects[:20]}, indent=1))
if not defects:
    print("ALL NUMERICAL REPLAYS CLEAN — failure must be the row-manifest comparison "
          "(row_id / input_content_hash order vs rebuilt corpus manifest).")
sys.exit(0)
