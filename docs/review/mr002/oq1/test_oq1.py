"""MR-002 OQ-1 operational qualification tests (in-process cases; container cases run via docker).

Maps to the OQ-1 qualification matrix (OQ1-01..35). Environment-identity, sealed-access boundary,
refusal contract, determinism projection, and publication are exercised here; the container-runtime
cases (image digest, altered-file refusal, non-root, network-disabled, rebuild equivalence, full suite
in container) are proven by the docker runs recorded in the OQ-1 evidence bundle.
Run: apps/backend/.venv/Scripts/python.exe -m pytest test_oq1.py -v
"""

from __future__ import annotations

import os
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.abspath(os.path.join(HERE, "..", "evaluator")))

import oq1_determinism as DET     # noqa: E402
import oq1_environment as ENV     # noqa: E402
import oq1_exit_codes as EC       # noqa: E402
import oq1_publish as PUB         # noqa: E402
import oq1_sealed_access as SA    # noqa: E402

MANIFEST = os.path.join(HERE, "wheelhouse-manifest.json")
EVAL = os.path.abspath(os.path.join(HERE, "..", "evaluator"))


# ── environment identity (OQ1-01..06) ─────────────────────────────────────────────────────────────
def _installed_ok():
    m = ENV.load_lock(MANIFEST)
    return {w["name"]: w["version"] for w in m["wheels"]}


def test_oq1_01_clean_locked_environment_passes():
    got = ENV.verify_environment(MANIFEST, installed=_installed_ok(), python_version="3.13")
    assert got["python"] == "3.13" and "numpy" in got["locked_packages"]


def test_oq1_02_version_mismatch_refuses():
    bad = {**_installed_ok(), "numpy": "2.2.5"}
    with pytest.raises(ENV.EnvironmentRefused, match="VERSION_MISMATCH:numpy"):
        ENV.verify_environment(MANIFEST, installed=bad, python_version="3.13")


def test_oq1_03_missing_package_refuses():
    bad = {k: v for k, v in _installed_ok().items() if k != "scipy"}
    with pytest.raises(ENV.EnvironmentRefused, match="MISSING_PACKAGE:scipy"):
        ENV.verify_environment(MANIFEST, installed=bad, python_version="3.13")


def test_oq1_05_wrong_python_refuses():
    with pytest.raises(ENV.EnvironmentRefused, match="PYTHON_MISMATCH"):
        ENV.verify_environment(MANIFEST, installed=_installed_ok(), python_version="3.12")


def test_oq1_03b_wheel_hashes_pinned_no_floating():
    m = ENV.load_lock(MANIFEST)
    assert m["no_floating_ranges"] and m["no_unverified_downloads"]
    assert all(len(w["sha256"]) == 64 for w in m["wheels"]) and len(m["wheels"]) == 9


# ── sealed-access boundary (OQ1-13..20) ───────────────────────────────────────────────────────────
def test_oq1_13_no_credentials_present_passes():
    SA.assert_no_credentials(environ={})                       # clean env -> ok


def test_oq1_14_credential_discovery_refuses():
    with pytest.raises(SA.SealedAccessRefused, match="CREDENTIAL_PRESENT"):
        SA.assert_no_credentials(environ={"AWS_SECRET_ACCESS_KEY": "x"})


def test_oq1_15_direct_sealed_path_refuses():
    with pytest.raises(SA.SealedAccessRefused, match="SEALED_PATTERN"):
        SA.guarded_open(os.path.join(EVAL, "..", "validation_data.duckdb"), EVAL)


def test_oq1_16_path_traversal_refuses():
    with pytest.raises(SA.SealedAccessRefused, match="OUTSIDE_ALLOWLIST|SEALED_PATTERN"):
        SA.guarded_open(os.path.join(EVAL, "..", "..", "..", "etc", "passwd"), EVAL)


def test_oq1_17_symlink_escape_refuses(tmp_path):
    target = tmp_path / "secret_validation.txt"
    target.write_text("x")
    link = tmp_path / "link.py"
    try:
        os.symlink(target, link)
    except (OSError, NotImplementedError):
        pytest.skip("symlink not permitted on this host")
    with pytest.raises(SA.SealedAccessRefused):
        SA.guarded_open(str(link), str(tmp_path))


def test_oq1_18_20_forbidden_adapter_and_subprocess_refuse():
    with pytest.raises(SA.SealedAccessRefused, match="FORBIDDEN_IMPORT:boto3"):
        SA.assert_no_forbidden_imports({"boto3", "os"})
    with pytest.raises(SA.SealedAccessRefused, match="FORBIDDEN_IMPORT:.*subprocess"):
        SA.assert_no_forbidden_imports({"subprocess"})
    with pytest.raises(SA.SealedAccessRefused, match="FORBIDDEN_IMPORT:requests"):
        SA.assert_no_forbidden_imports({"requests"})


def test_oq1_15b_write_to_input_refused(tmp_path):
    f = tmp_path / "ok.py"
    f.write_text("x")
    with pytest.raises(SA.SealedAccessRefused, match="WRITE_TO_INPUT_FORBIDDEN"):
        SA.guarded_open(str(f), str(tmp_path), mode="w")


# ── refusal / exit-code contract (OQ1-21..24) ─────────────────────────────────────────────────────
def test_oq1_21_refusal_families_map_to_frozen_exit_codes():
    assert EC.exit_code_for("REFUSED_CODE_OR_DATA_IDENTITY:X") == 10
    assert EC.exit_code_for("REFUSED_ENVIRONMENT_IDENTITY:X") == 11
    assert EC.exit_code_for("REFUSED_SEALED_ACCESS:X") == 12
    assert EC.exit_code_for("INTEGRITY_STOP:X") == 13
    assert EC.exit_code_for("DETERMINISM_MISMATCH") == 14
    assert EC.exit_code_for("REFUSED_PUBLICATION:X") == 15
    assert EC.exit_code_for("UNSUPPORTED_INVOCATION") == 16


def test_oq1_22_refusal_report_canonical_deterministic():
    kw = dict(reason_code="REFUSED_SEALED_ACCESS:NETWORK_REACHABLE", stage="preflight",
              expected="disabled", observed="reachable", code_commit="abc", container_digest="sha256:d",
              dependency_lock_hash="e", timestamp="FIXED")
    r1, r2 = EC.refusal_record(**kw), EC.refusal_record(**kw)
    assert r1 == r2 and r1["record_hash"] == r2["record_hash"] and r1["exit_code"] == 12


def test_oq1_23_refusal_report_contains_no_secrets():
    r = EC.refusal_record(reason_code="REFUSED_SEALED_ACCESS:X", stage="s",
                          expected="C:/Users/jay/.aws/credentials", observed="/home/oq1/.aws/credentials",
                          code_commit="c", container_digest="d", dependency_lock_hash="h", timestamp="T")
    # only basenames survive; no directory / secret material echoed
    assert r["expected_identity"] == "credentials" and "/" not in r["observed_identity"]


# ── determinism (OQ1-25, 27, 29) ──────────────────────────────────────────────────────────────────
def test_oq1_25_27_determinism_and_accepted_hash():
    a, b = DET.run_replay_report(), DET.run_replay_report()
    v = DET.compare(a, b, accepted_output_hash="42c5cee0fc121f1fabf9ff1916a02cc8bd922ce69b8f80d85be7852dc5fde907")
    assert v["verdict"] == "DETERMINISTIC" and v["accepted_hash_reproduced"] and v["economic_payload_match"]


def test_oq1_29_signed_zero_exact_float_preserved():
    import mr002_valoos_report as R
    assert R.encode_float(-0.0)["exact_hex"] == "-0x0.0p+0"
    with pytest.raises(R.CanonicalizationError):
        R.canonical_bytes({"x": float("nan")})


# ── publication (OQ1-31..35) ──────────────────────────────────────────────────────────────────────
def _arts(tmp_path):
    p = tmp_path / "MR002_OQ1_Qualification.json"
    p.write_text('{"ok":true}')
    return [{"path": str(p), "content_type": "application/json", "producer": "oq1", "governing_role": "qualification"}]


def test_oq1_31_32_manifest_covers_and_hashes_verify(tmp_path):
    m = PUB.build_manifest(_arts(tmp_path))
    assert m["artifact_count"] == 1 and len(m["artifacts"][0]["sha256"]) == 64 and m["manifest_self_hash"]


def test_oq1_33_overwrite_refuses(tmp_path):
    dest = tmp_path / "bundle"
    dest.mkdir()
    arts = _arts(tmp_path)
    PUB.publish_local(str(dest), arts)
    with pytest.raises(PUB.PublicationRefused, match="OVERWRITE_FORBIDDEN"):
        PUB.publish_local(str(dest), arts)


def test_oq1_34_partial_missing_artifact_fails_closed(tmp_path):
    dest = tmp_path / "b2"
    dest.mkdir()
    with pytest.raises(PUB.PublicationRefused, match="MISSING_ARTIFACT"):
        PUB.publish_local(str(dest), [{"path": str(tmp_path / "nope.json"), "content_type": "x",
                                       "producer": "p", "governing_role": "r"}])


def test_oq1_35_s3_dryrun_immutability_and_run5_forbidden(tmp_path):
    arts = _arts(tmp_path)
    ok = PUB.s3_publish_dryrun(bucket="mr002-oq1-evidence", prefix="oq1/v1", artifacts=arts,
                               versioning=True, object_lock=True, sse=True)
    assert ok["mode"] == "DRY_RUN" and ok["run5_archive_untouched"] and ok["planned_objects"][0]["sha256"]
    with pytest.raises(PUB.PublicationRefused, match="IMMUTABILITY_PRECONDITION:VERSIONING"):
        PUB.s3_publish_dryrun(bucket="b", prefix="p", artifacts=arts, versioning=False, object_lock=True, sse=True)
    with pytest.raises(PUB.PublicationRefused, match="RUN5_ARCHIVE_DESTINATION_FORBIDDEN"):
        PUB.s3_publish_dryrun(bucket="workbench-backups-219024422756", prefix="mr002/run5", artifacts=arts,
                              versioning=True, object_lock=True, sse=True)


# ── OQ-1 v1.1: base-image immutability + offline-build-input bundle ────────────────────────────────
def test_oq1_v11_dockerfile_base_digest_pinned():
    df = open(os.path.join(HERE, "Dockerfile.oq1"), encoding="utf-8").read()
    assert "FROM python:3.13-slim@sha256:6771159cd4fa5d9bba1258caf0b82e6b73458c694d178ad97c5e925c2d0e1a91" in df
    assert "@sha256:" in df.splitlines()[1]                 # mutable tag alone is not permitted


def test_oq1_v12_build_identity_binds_v11_commit_and_images():
    import json
    b = json.load(open(os.path.join(HERE, "container-build-identity.json")))
    assert b["base_image"]["index_digest"] == "sha256:6771159cd4fa5d9bba1258caf0b82e6b73458c694d178ad97c5e925c2d0e1a91"
    assert b["base_image"]["amd64_digest"] == "sha256:afe189875f1d2f9b45e287834fb9f2c273a5d59d354ae4050ab9affbf0a6ba06"
    # v1.2 provenance correction: binds the v1.1 build commit/tree (not the parent), both image digests
    bc = b["build_context_identity"]
    assert bc["source_commit"] == "1e3db0a00903f2ca692644caa6199164e4836f5f"
    assert bc["source_tree"] == "66c86234876d101168414b02b74504dd200b32f9"
    assert bc["dockerfile_sha256"] and bc["governance_input_aggregate_sha256"] and bc["evaluator_code_aggregate_sha256"]
    assert "resulting_image_digest" not in b                     # the misleading single "n/a" field is removed
    assert {i["build_id"] for i in b["resulting_images"]} == {"A", "B"}
    assert all(i["runtime_preflight_verified"] for i in b["resulting_images"])
    # governing installed-distribution fingerprint is SHA-256, not MD5
    cid = b["canonical_rebuild_equivalence_identity"]
    assert len(cid["installed_distributions_sha256"]) == 64
    assert cid["accepted_evaluator_output_hash"] == "42c5cee0fc121f1fabf9ff1916a02cc8bd922ce69b8f80d85be7852dc5fde907"


def test_oq1_v11_wheelhouse_bundle_manifest_bound_to_release():
    import json
    m = json.load(open(os.path.join(HERE, "wheelhouse-bundle-manifest.json")))
    assert m["wheel_count"] == 9 and len(m["archive_sha256"]) == 64 and m["archive_byte_count"] == 64235470
    p = m["publication"]
    assert p["mechanism"] == "GitHub release asset" and p["asset_id"] == "483744510"
    assert p["release_url"].endswith("mr002-oq1-wheelhouse-v1")
    assert all(len(w["sha256"]) == 64 and w["platform_tag"] for w in m["wheels"])
