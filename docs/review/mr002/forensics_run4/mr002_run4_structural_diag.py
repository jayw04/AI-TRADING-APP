"""MR-002 run-4 STOP forensics — stage 1: structural replay of aggregate_verdict.

READ-ONLY. Replays read_checkpoint + the structural (non-numerical, non-manifest)
PASS conditions from scripts/mr002_stage3_population_runner.py against the durable
checkpoint, and reports the FIRST failing condition with enough context to write
the stop report. No numpy required.
"""
import hashlib
import json
import sys

CHECKPOINT = "/home/ec2-user/mr002/out/cleanrun/MR002_Stage3_CleanRun_checkpoint.jsonl"
MANIFEST = "/home/ec2-user/mr002/out/cleanrun/MR002_Stage3_CleanRun_Manifest.json"

_RECORD_ENVELOPE_KEYS = ("kind", "record_sha256")


def _record_hash(rec):
    body = {k: v for k, v in rec.items() if k not in _RECORD_ENVELOPE_KEYS}
    return hashlib.sha256(json.dumps(body, sort_keys=True, separators=(",", ":"),
                                     default=str).encode()).hexdigest()


def main():
    with open(CHECKPOINT, encoding="utf-8") as fh:
        lines = [ln.strip() for ln in fh.readlines()]
    nonempty = [(i, ln) for i, ln in enumerate(lines) if ln]
    print(f"lines_total={len(lines)} nonempty={len(nonempty)}")

    records, terminal, trailing_partial, corruption = [], None, False, []
    for pos, (i, line) in enumerate(nonempty):
        is_last = pos == len(nonempty) - 1
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            if is_last:
                trailing_partial = True
            else:
                corruption.append(f"MALFORMED_LINE:{i}")
            continue
        if not isinstance(obj, dict) or obj.get("kind") not in ("record", "terminal"):
            corruption.append(f"UNKNOWN_EVENT:{i}")
            continue
        if terminal is not None:
            corruption.append(f"EVENT_AFTER_TERMINAL:{i}")
            continue
        if obj["kind"] == "terminal":
            terminal = obj
        else:
            records.append(obj)

    print(f"corruption={corruption[:5]} (n={len(corruption)})")
    print(f"trailing_partial={trailing_partial}")
    print(f"terminal={json.dumps(terminal)[:400] if terminal else None}")
    print(f"n_records={len(records)}")

    fails = []
    if corruption or trailing_partial:
        fails.append("CORRUPTION_OR_TRAILING_PARTIAL")
    if terminal is None or terminal.get("status") != "COMPLETE":
        fails.append(f"TERMINAL_STATUS={terminal.get('status') if terminal else None}")
    if terminal is not None and terminal.get("n_records") != len(records):
        fails.append(f"TERMINAL_COUNT_MISMATCH:{terminal.get('n_records')}!={len(records)}")
    bad_class = [(idx, r.get("class")) for idx, r in enumerate(records)
                 if r.get("class") != "qualified"]
    if bad_class:
        fails.append(f"NON_QUALIFIED_RECORDS:{bad_class[:5]}")
    if len(records) != 3895:
        fails.append(f"N_RECORDS!={3895}: {len(records)}")

    bad_hash = []
    for idx, r in enumerate(records):
        if r.get("record_sha256") != _record_hash(r):
            bad_hash.append(idx)
            if len(bad_hash) >= 5:
                break
    if bad_hash:
        fails.append(f"RECORD_SHA256_MISMATCH at record indexes {bad_hash} ...")
        idx = bad_hash[0]
        r = records[idx]
        print(f"first bad record: index={idx} row_id={r.get('row_id')} "
              f"claimed={r.get('record_sha256')} recomputed={_record_hash(r)}")

    dup = len(records) - len({r.get("row_id") for r in records})
    print(f"duplicate_row_ids={dup}")

    with open(MANIFEST, encoding="utf-8") as fh:
        m = json.load(fh)
    print(f"manifest disposition={m.get('disposition')} n_expected={m.get('n_expected')}")

    if fails:
        print("STRUCTURAL FAILURES (first failing aggregate_verdict conditions):")
        for f in fails:
            print("  -", f)
    else:
        print("STRUCTURAL CHECKS ALL PASS — verdict failure must be in "
              "row-manifest comparison (row_id/content-hash order) or numerical replay.")


if __name__ == "__main__":
    sys.exit(main())
