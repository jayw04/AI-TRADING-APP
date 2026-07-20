"""SPQ-1 Phase 2B-0 run-spec generator: portability + complete-identity binding.

Skips if the registered development DBs are absent (local-only). Verifies the generator produces
byte-identical artifacts regardless of working directory, and that every SHA-256 identity in the
committed artifacts is a full 64-char hex value (no ellipsis / truncation / placeholder).
"""
from __future__ import annotations

import importlib.util
import json
import os
import re
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[5]
GEN = REPO / "docs" / "review" / "mr002" / "spq1" / "phase2b" / "_gen_phase2b_0_runspec.py"
RESEARCH = REPO / "apps" / "backend" / "data" / "mr002_research.duckdb"
PROV = REPO / "apps" / "backend" / "data" / "mr002_provenance.duckdb"
P2B = REPO / "docs" / "review" / "mr002" / "spq1" / "phase2b"
_SHA = re.compile(r"^[0-9a-f]{64}$")

pytestmark = pytest.mark.skipif(
    not (RESEARCH.exists() and PROV.exists()),
    reason="registered development DBs not present (local-only)")


def _load_gen():
    spec = importlib.util.spec_from_file_location("_p2b0_gen", GEN)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _artifact(*parts):
    return P2B.joinpath(*parts)


def test_generator_is_cwd_independent(tmp_path):
    gen = _load_gen()
    art = _artifact("run_spec", "MR002_SPQ1_Phase2B_RunSpecification_v1.0.json")
    cwd0 = os.getcwd()
    try:
        os.chdir(tmp_path)
        h1 = gen.run()
        b1 = art.read_bytes()
        os.chdir(REPO)
        h2 = gen.run()
        b2 = art.read_bytes()
    finally:
        os.chdir(cwd0)
    assert h1 == h2                       # returned identities identical across CWDs
    assert b1 == b2                       # written artifact bytes identical
    assert _SHA.match(h1["run_spec_body"])


def _walk_sha_fields(obj, path=""):
    if isinstance(obj, dict):
        for k, v in obj.items():
            if isinstance(v, str) and (k.endswith("sha256") or k.endswith("_sha256")):
                yield f"{path}.{k}", v
            yield from _walk_sha_fields(v, f"{path}.{k}")
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            yield from _walk_sha_fields(v, f"{path}[{i}]")


def test_all_sha256_fields_are_full_64_hex():
    _load_gen().run()  # ensure fresh
    for name in ("run_spec/MR002_SPQ1_Phase2B_RunSpecification_v1.0.json",
                 "manifests/MR002_SPQ1_Phase2B_DevelopmentRunManifest_v1.0.json",
                 "manifests/MR002_SPQ1_Phase2B_InputIdentityManifest_v1.0.json",
                 "evidence/MR002_SPQ1_Phase2B_2B0_OpenedObjectLedger_v1.0.json"):
        doc = json.loads(_artifact(*name.split("/")).read_text(encoding="utf-8"))
        for field, val in _walk_sha_fields(doc):
            assert _SHA.match(val), f"{name}{field} is not full 64-hex: {val!r}"
        assert "..." not in json.dumps(doc), f"{name} contains an ellipsis/truncated value"


def test_2b0_ledger_records_guarded_completed_reads():
    _load_gen().run()
    led = json.loads(_artifact(
        "evidence", "MR002_SPQ1_Phase2B_2B0_OpenedObjectLedger_v1.0.json").read_text(encoding="utf-8"))
    assert led["count"] == 2 and led["all_completed"]
    assert led["no_actual_key_beyond_dev_end"] and led["validation_or_oos_objects_opened"] == 0
    for e in led["entries"]:
        assert e["status"] == "COMPLETED" and e["result_row_count"] > 0
        assert _SHA.match(str(e["result_set_sha256"])) and _SHA.match(str(e["object_sha256"]))
