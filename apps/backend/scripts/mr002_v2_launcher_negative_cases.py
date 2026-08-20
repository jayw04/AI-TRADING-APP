"""Negative-case tests for the amended launcher. NO AWS, NO reader, NO sealed access.

Each case must fail with a specific IntegrityFailure code BEFORE reader acquisition, so a
forbidden configuration fails on the SAFE SIDE of the credential boundary.
"""
import json
import os
import subprocess
import sys
import tempfile

_REG = ("/work/apps/backend/app/research/mr002/phase3c/manifests/"
        "validation2_object_registry.json")
with open(_REG, encoding="utf-8") as _fh:
    BASE = json.load(_fh)
RUN = "/work/apps/backend/scripts/mr002_phase3c_validation_run.py"
CODES = ("CONSUMED_PARTITION_ACCESS_ATTEMPT", "CONSUMED_PARTITION_IN_REGISTRY",
         "UNREGISTERED_VALIDATION2_OBJECT_IN_REGISTRY", "UNREGISTERED_VALIDATION2_OBJECT",
         "VERSION_ID_MISMATCH", "SHA256_CONTRACT_MISMATCH", "UNPINNED_OBJECT",
         "WINDOW_MISUSE")


def run(reg, reader="fixture", window="development"):
    d = tempfile.mkdtemp()
    p = os.path.join(d, "reg.json")
    with open(p, "w") as fh:
        json.dump(reg, fh)
    r = subprocess.run(
        [sys.executable, RUN, "--reader", reader, "--window", window, "--manifest", p,
         "--materialized", os.path.join(d, "m.duckdb"), "--out", os.path.join(d, "o.json"),
         "--fixture-root", d],
        capture_output=True, text=True)
    return r.stdout + r.stderr


def clone():
    return json.loads(json.dumps(BASE))


cases = {}

reg = clone()
reg["sealed_validation2_objects"].append(
    {"table": "x", "key": "validation/prices.parquet",
     "version_id": "eC8XZGBPXa6vPDW_WKPvwV8HtF05_tty", "sha256": "00" * 32})
cases["1_consumed_validation_key"] = run(reg)

reg = clone()
reg["sealed_validation2_objects"].append(
    {"table": "y", "key": "oos/somethingelse.parquet", "version_id": "ZZZ",
     "sha256": "11" * 32})
cases["2_unregistered_seventh_oos"] = run(reg)

reg = clone()
reg["sealed_validation2_objects"][3]["version_id"] = "WRONGVERSIONID0000000000000000"
cases["3_registered_key_wrong_version"] = run(reg)

reg = clone()
reg["sealed_validation2_objects"][3]["sha256"] = "de" * 32
cases["4_registry_vs_contract_sha"] = run(reg)

cases["5_s3_reader_with_dev_window"] = run(clone(), reader="s3", window="development")

print()
for k, v in cases.items():
    hit = [c for c in CODES if c in v]
    unsafe = ("AssumeRole" in v) or ("mr002-validation-reader" in v)
    print(f"  {k:32s} codes={hit or ['NONE']}  reader_acquisition_attempted={unsafe}")
