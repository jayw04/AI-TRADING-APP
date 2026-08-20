"""Negative-case tests for the amended launcher. NO AWS, NO reader, NO sealed access.

Cases 1-4 exercise PRODUCTION registry-content refusals, so they must run in the production
state (s3 + validation + validation2) where those checks are active. They still fail during
OBJECT-SET CONSTRUCTION, which precedes the reader block entirely, so no credential is ever
attempted. Running them in a fixture state would have them masked by UNPERMITTED_EXECUTION_STATE
and would silently stop testing what they were written to test.

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
         "WINDOW_MISUSE", "UNPERMITTED_EXECUTION_STATE", "REGISTRY_ROLE_MISMATCH")
REHEARSAL = ("/work/apps/backend/app/research/mr002/phase3c/manifests/"
             "validation2_rehearsal_registry.json")


def run(reg, reader="fixture", window="development", contract="validation2"):
    d = tempfile.mkdtemp()
    p = os.path.join(d, "reg.json")
    with open(p, "w") as fh:
        json.dump(reg, fh)
    r = subprocess.run(
        [sys.executable, RUN, "--reader", reader, "--window", window,
         "--contract", contract, "--manifest", p,
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
cases["1_consumed_validation_key"] = run(reg, reader="s3", window="validation")

reg = clone()
reg["sealed_validation2_objects"].append(
    {"table": "y", "key": "oos/somethingelse.parquet", "version_id": "ZZZ",
     "sha256": "11" * 32})
cases["2_unregistered_seventh_oos"] = run(reg, reader="s3", window="validation")

reg = clone()
reg["sealed_validation2_objects"][3]["version_id"] = "WRONGVERSIONID0000000000000000"
cases["3_registered_key_wrong_version"] = run(reg, reader="s3", window="validation")

reg = clone()
reg["sealed_validation2_objects"][3]["sha256"] = "de" * 32
cases["4_registry_vs_contract_sha"] = run(reg, reader="s3", window="validation")

cases["5_s3_reader_with_dev_window"] = run(clone(), reader="s3", window="development")

with open(REHEARSAL, encoding="utf-8") as _rh:
    REH = json.load(_rh)
cases["6_s3_with_rehearsal_contract"] = run(clone(), reader="s3", window="validation",
                                            contract="rehearsal")
cases["7_fixture_with_validation_window"] = run(clone(), reader="fixture", window="validation",
                                                contract="rehearsal")
cases["8_production_registry_declared_rehearsal"] = run(clone(), reader="fixture",
                                                        window="development",
                                                        contract="rehearsal")
reg = json.loads(json.dumps(REH))
reg["registry_role"] = "VALIDATION2_PRODUCTION"
cases["9_rehearsal_registry_mislabelled_production"] = run(reg, reader="fixture",
                                                           window="development",
                                                           contract="rehearsal")
reg = clone()
reg["registry_role"] = "SOMETHING_ELSE"
cases["10_unrecognised_registry_role"] = run(reg, reader="s3", window="validation",
                                             contract="validation2")

print()
for k, v in cases.items():
    hit = [c for c in CODES if c in v]
    unsafe = ("AssumeRole" in v) or ("mr002-validation-reader" in v)
    print(f"  {k:32s} codes={hit or ['NONE']}  reader_acquisition_attempted={unsafe}")
