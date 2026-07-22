"""MR-002 Increment 4 (operational increment / prerequisite P3) — qualification tests.

Qualifies the four operational capabilities: numeric-runtime identity, code identity + refusal,
access boundary + opened-object ledger, and the no-overwrite publication wrapper.

Synthetic ONLY. Reads no real dataset, opens no validation or OOS partition, computes no performance.
Every "sealed" object in these tests is a fabricated identifier that names nothing.
Run: apps/backend/.venv/Scripts/python.exe -m pytest test_increment4.py -v
"""

from __future__ import annotations

import json
import os
import stat
import tempfile

import pytest

import mr002_valoos_access_boundary as AB
import mr002_valoos_code_identity as CI
import mr002_valoos_publication as PUB
import mr002_valoos_runtime as RT

HERE = os.path.abspath(os.path.dirname(__file__))
PUBLISHED_AT = "2026-07-22T00:00:00Z"


def _state(*, authorized=False, rev=0, identities=None):
    return {"record_type": "MR002_Phase3BC_ValidationAuthorizationState",
            "validation_authorization": authorized, "_rev": rev,
            "bound_identities": identities if identities is not None else {"prerequisite_digest": "d"}}


def _registered():
    return {AB.SYNTHETIC: {"synthetic/fixture_a"},
            AB.VALIDATION: {"validation/registered_object"},
            AB.OOS: {"oos/registered_object"}}


def _boundary(**kw):
    return AB.AccessBoundary(authorization_state=kw.pop("state", _state()),
                             registered_objects=_registered(), **kw)


# =====================================================================================
# T4-01..T4-09 — numeric-runtime identity
# =====================================================================================
def test_T4_01_capture_reports_the_frozen_solver_settings_and_seed():
    obs = RT.capture_runtime()
    assert obs["solver"] == "numpy.linalg.lstsq"
    assert obs["lapack_driver"] == "gelsd/SVD"
    assert obs["dtype"] == "float64" and obs["rcond"] == 1e-10
    assert obs["rng"] == "numpy_PCG64" and obs["bootstrap_seed"] == 20260711
    assert obs["numpy"] and obs["python"]
    assert set(obs["thread_env"]) == set(RT.THREAD_VARS)


def test_T4_02_capture_never_fabricates_lockfile_or_container():
    obs = RT.capture_runtime()
    assert "dependency_lockfile_sha256" not in obs
    assert "container_image_digest" not in obs


def test_T4_03_capture_binds_a_supplied_lockfile_by_content():
    with tempfile.TemporaryDirectory() as d:
        lock = os.path.join(d, "requirements.lock")
        with open(lock, "wb") as fh:
            fh.write(b"numpy==2.2.6\n")
        obs = RT.capture_runtime(lockfile_path=lock, container_image_digest="sha256:abc")
        assert obs["dependency_lockfile_sha256"] == RT._sha_path(lock)
        assert obs["container_image_digest"] == "sha256:abc"


def test_T4_04_specification_template_is_not_a_runtime_instance():
    obs = RT.capture_runtime()
    template = dict(obs)  # no lockfile, no container digest -> a template, not an instance
    c = RT.manifest_completeness(template)
    assert c["is_runtime_instance"] is False
    assert "dependency_lockfile_sha256" in c["missing"]
    assert "container_image_digest" in c["missing"]


@pytest.mark.parametrize("placeholder", ["", "TBD", "PENDING", None, "pending"])
def test_T4_05_placeholder_completion_is_rejected(placeholder):
    obs = RT.capture_runtime(lockfile_path=None, container_image_digest="sha256:abc")
    manifest = dict(obs)
    manifest["dependency_lockfile_sha256"] = placeholder
    assert RT.manifest_completeness(manifest)["is_runtime_instance"] is False
    with pytest.raises(RT.RuntimeIdentityStop) as exc:
        RT.require_runtime(obs, manifest)
    assert RT.RUNTIME_INCOMPLETE in str(exc.value)


def test_T4_06_matching_runtime_instance_passes():
    with tempfile.TemporaryDirectory() as d:
        lock = os.path.join(d, "lock")
        with open(lock, "wb") as fh:
            fh.write(b"x")
        obs = RT.capture_runtime(lockfile_path=lock, container_image_digest="sha256:abc")
        manifest = {k: v for k, v in obs.items() if k in RT.REQUIRED_FIELDS}
        report = RT.require_runtime(obs, manifest)
        assert report["matches"] is True and report["mismatches"] == []


def test_T4_07_any_bound_field_mismatch_fail_stops():
    with tempfile.TemporaryDirectory() as d:
        lock = os.path.join(d, "lock")
        with open(lock, "wb") as fh:
            fh.write(b"x")
        obs = RT.capture_runtime(lockfile_path=lock, container_image_digest="sha256:abc")
        manifest = {k: v for k, v in obs.items() if k in RT.REQUIRED_FIELDS}
        manifest["numpy"] = "0.0.0"
        with pytest.raises(RT.RuntimeIdentityStop) as exc:
            RT.require_runtime(obs, manifest)
        assert RT.RUNTIME_STOP in str(exc.value) and "numpy" in str(exc.value)


def test_T4_08_thread_env_change_is_a_mismatch():
    with tempfile.TemporaryDirectory() as d:
        lock = os.path.join(d, "lock")
        with open(lock, "wb") as fh:
            fh.write(b"x")
        obs = RT.capture_runtime(lockfile_path=lock, container_image_digest="sha256:abc")
        manifest = {k: v for k, v in obs.items() if k in RT.REQUIRED_FIELDS}
        manifest["thread_env"] = {v: "99" for v in RT.THREAD_VARS}
        with pytest.raises(RT.RuntimeIdentityStop):
            RT.require_runtime(obs, manifest)


def test_T4_09_runtime_identity_digest_is_stable_and_sensitive():
    obs = RT.capture_runtime()
    assert RT.runtime_identity_sha256(obs) == RT.runtime_identity_sha256(dict(obs))
    other = dict(obs, numpy="0.0.0")
    assert RT.runtime_identity_sha256(other) != RT.runtime_identity_sha256(obs)


# =====================================================================================
# T4-10..T4-17 — code identity + refusal
# =====================================================================================
def _fake_pkg(tmp, files):
    for name, body in files.items():
        with open(os.path.join(tmp, name), "wb") as fh:
            fh.write(body)


def test_T4_10_module_digests_exclude_tests_and_generators():
    with tempfile.TemporaryDirectory() as d:
        _fake_pkg(d, {"mod_a.py": b"a", "test_x.py": b"t", "_gen_y.py": b"g", "notes.txt": b"n"})
        assert set(CI.module_digests(d)) == {"mod_a.py"}


def test_T4_11_binding_refuses_unresolved_fields():
    with tempfile.TemporaryDirectory() as d:
        _fake_pkg(d, {"mod_a.py": b"a"})
        for bad in ("", "PENDING_EVALUATOR_BIND", "TBD"):
            with pytest.raises(CI.RefusedCodeIdentity) as exc:
                CI.bind_from_directory(d, commit=bad, tree="t", container_image_digest="sha256:i")
            assert CI.REFUSED in str(exc.value)


def test_T4_12_matching_binding_passes():
    with tempfile.TemporaryDirectory() as d:
        _fake_pkg(d, {"mod_a.py": b"a", "mod_b.py": b"b"})
        b = CI.bind_from_directory(d, commit="c1", tree="t1", container_image_digest="sha256:i")
        rep = CI.require_code_identity(d, b, observed_commit="c1", observed_tree="t1",
                                       observed_container_image_digest="sha256:i")
        assert rep["matches"] is True and rep["bound_module_count"] == 2


def test_T4_13_module_drift_refuses():
    with tempfile.TemporaryDirectory() as d:
        _fake_pkg(d, {"mod_a.py": b"a"})
        b = CI.bind_from_directory(d, commit="c1", tree="t1", container_image_digest="sha256:i")
        _fake_pkg(d, {"mod_a.py": b"a-modified"})
        with pytest.raises(CI.RefusedCodeIdentity) as exc:
            CI.require_code_identity(d, b)
        assert "module_drift" in str(exc.value)


def test_T4_14_unbound_module_refuses():
    """Code added to the evaluator after the binding was accepted must not run silently."""
    with tempfile.TemporaryDirectory() as d:
        _fake_pkg(d, {"mod_a.py": b"a"})
        b = CI.bind_from_directory(d, commit="c1", tree="t1", container_image_digest="sha256:i")
        _fake_pkg(d, {"mod_new.py": b"new"})
        with pytest.raises(CI.RefusedCodeIdentity) as exc:
            CI.require_code_identity(d, b)
        assert "module_unbound" in str(exc.value)


def test_T4_15_missing_module_refuses():
    with tempfile.TemporaryDirectory() as d:
        _fake_pkg(d, {"mod_a.py": b"a", "mod_b.py": b"b"})
        b = CI.bind_from_directory(d, commit="c1", tree="t1", container_image_digest="sha256:i")
        os.remove(os.path.join(d, "mod_b.py"))
        with pytest.raises(CI.RefusedCodeIdentity) as exc:
            CI.require_code_identity(d, b)
        assert "module_missing" in str(exc.value)


@pytest.mark.parametrize("field,value", [("observed_commit", "other"), ("observed_tree", "other"),
                                         ("observed_container_image_digest", "sha256:other")])
def test_T4_16_commit_tree_container_mismatch_refuses(field, value):
    with tempfile.TemporaryDirectory() as d:
        _fake_pkg(d, {"mod_a.py": b"a"})
        b = CI.bind_from_directory(d, commit="c1", tree="t1", container_image_digest="sha256:i")
        with pytest.raises(CI.RefusedCodeIdentity) as exc:
            CI.require_code_identity(d, b, **{field: value})
        assert "identity_mismatch" in str(exc.value)


def test_T4_17_absent_binding_refuses_and_is_never_inferred():
    with tempfile.TemporaryDirectory() as d:
        _fake_pkg(d, {"mod_a.py": b"a"})
        with pytest.raises(CI.RefusedCodeIdentity) as exc:
            CI.require_code_identity(d, None)
        assert "binding_absent" in str(exc.value)
        with pytest.raises(CI.RefusedCodeIdentity):
            CI.require_code_identity(d, {"commit": "c", "tree": "t",
                                         "container_image_digest": "sha256:i"})  # no modules


# =====================================================================================
# T4-18..T4-29 — access boundary
# =====================================================================================
def test_T4_18_validation_blocked_when_authorization_false():
    b = _boundary()
    with pytest.raises(AB.AccessBoundaryViolation) as exc:
        b.open_object(AB.VALIDATION, "validation/registered_object")
    assert "validation_authorization_false" in str(exc.value)
    assert b.counts()["validation_reads"] == 0


def test_T4_19_oos_blocked_even_when_validation_authorized():
    b = _boundary(state=_state(authorized=True))
    with pytest.raises(AB.AccessBoundaryViolation) as exc:
        b.open_object(AB.OOS, "oos/registered_object")
    assert "oos_denied_requires_separate_authorization" in str(exc.value)
    assert b.counts()["oos_reads"] == 0


def test_T4_20_validation_permitted_only_with_matching_rev_and_identities():
    ids = {"prerequisite_digest": "abc", "authorization_request_sha256": "def"}
    b = AB.AccessBoundary(authorization_state=_state(authorized=True, rev=1, identities=ids),
                          registered_objects=_registered(), expected_identities=ids, expected_rev=1)
    rec = b.open_object(AB.VALIDATION, "validation/registered_object")
    assert rec["permitted"] is True
    assert b.counts()["validation_reads"] == 1


def test_T4_21_stale_prerequisite_digest_blocks_validation():
    """The brittle CAS digest must actually bite at the access boundary."""
    ids = {"prerequisite_digest": "abc"}
    b = AB.AccessBoundary(authorization_state=_state(authorized=True, rev=1, identities=ids),
                          registered_objects=_registered(),
                          expected_identities={"prerequisite_digest": "CHANGED"}, expected_rev=1)
    with pytest.raises(AB.AccessBoundaryViolation) as exc:
        b.open_object(AB.VALIDATION, "validation/registered_object")
    assert "bound_identity_mismatch:prerequisite_digest" in str(exc.value)


def test_T4_22_rev_mismatch_blocks_validation():
    b = AB.AccessBoundary(authorization_state=_state(authorized=True, rev=2),
                          registered_objects=_registered(), expected_rev=0)
    with pytest.raises(AB.AccessBoundaryViolation) as exc:
        b.open_object(AB.VALIDATION, "validation/registered_object")
    assert "authorization_rev_mismatch" in str(exc.value)


def test_T4_23_unregistered_object_blocked_on_every_partition():
    b = _boundary(state=_state(authorized=True), expected_rev=0)
    for partition in (AB.SYNTHETIC, AB.VALIDATION):
        with pytest.raises(AB.AccessBoundaryViolation) as exc:
            b.open_object(partition, "not/registered")
        assert "unregistered_object" in str(exc.value)


def test_T4_24_unsealed_partitions_remain_usable():
    b = _boundary()
    rec = b.open_object(AB.SYNTHETIC, "synthetic/fixture_a")
    assert rec["permitted"] is True
    assert b.counts()["sealed_reads"] == 0


def test_T4_25_every_attempt_is_ledgered_including_refusals():
    b = _boundary()
    for partition, obj in ((AB.VALIDATION, "validation/registered_object"),
                           (AB.OOS, "oos/registered_object"),
                           (AB.SYNTHETIC, "not/registered")):
        with pytest.raises(AB.AccessBoundaryViolation):
            b.open_object(partition, obj)
    b.open_object(AB.SYNTHETIC, "synthetic/fixture_a")
    c = b.counts()
    assert c["attempts"] == 4 and c["blocked"] == 3 and c["permitted"] == 1
    assert set(c["blocked_by_reason"]) == {"validation_authorization_false",
                                           "oos_denied_requires_separate_authorization",
                                           "unregistered_object"}


def test_T4_26_ledger_is_hash_chained_and_tamper_evident():
    b = _boundary()
    b.open_object(AB.SYNTHETIC, "synthetic/fixture_a")
    with pytest.raises(AB.AccessBoundaryViolation):
        b.open_object(AB.VALIDATION, "validation/registered_object")
    assert b.chain_verifies() is True
    b._ledger[0]["object_id"] = "synthetic/tampered"
    assert b.chain_verifies() is False


@pytest.mark.parametrize("bad", [
    None, [], {"record_type": "WRONG", "validation_authorization": False, "_rev": 0,
               "bound_identities": {}},
    {"validation_authorization": False, "_rev": 0, "bound_identities": {}},
    {"record_type": "MR002_Phase3BC_ValidationAuthorizationState",
     "validation_authorization": "true", "_rev": 0, "bound_identities": {}},
    {"record_type": "MR002_Phase3BC_ValidationAuthorizationState",
     "validation_authorization": True, "_rev": True, "bound_identities": {}},
])
def test_T4_27_malformed_authorization_state_blocks(bad):
    with pytest.raises(AB.AuthorizationStateInvalid):
        AB.load_authorization_state(None, raw=bad) if bad is not None else \
            AB.load_authorization_state(None)


def test_T4_28_absent_state_file_blocks_rather_than_defaulting_open():
    with tempfile.TemporaryDirectory() as d:
        with pytest.raises(AB.AuthorizationStateInvalid) as exc:
            AB.load_authorization_state(os.path.join(d, "missing.json"))
        assert "state_absent" in str(exc.value)
        bad = os.path.join(d, "bad.json")
        with open(bad, "wb") as fh:
            fh.write(b"{not json")
        with pytest.raises(AB.AuthorizationStateInvalid) as exc:
            AB.load_authorization_state(bad)
        assert "state_unreadable" in str(exc.value)


def test_T4_29_governing_state_on_disk_loads_and_denies_validation():
    """The real adjudicated state record must load and must deny — it says false at _rev 0."""
    path = os.path.abspath(os.path.join(
        HERE, "..", "phase3bc", "MR002_Phase3BC_ValidationAuthorizationState_v1.0.json"))
    if not os.path.exists(path):  # pragma: no cover - package not yet landed
        pytest.skip("authorization state record absent")
    state = AB.load_authorization_state(path)
    assert state["validation_authorization"] is False and state["_rev"] == 0
    b = AB.AccessBoundary(authorization_state=state, registered_objects=_registered())
    with pytest.raises(AB.AccessBoundaryViolation):
        b.open_object(AB.VALIDATION, "validation/registered_object")
    rep = b.boundary_report()
    assert rep["sealed_reads_zero"] is True and rep["chain_verifies"] is True


# =====================================================================================
# T4-30..T4-38 — publication wrapper
# =====================================================================================
def _identities():
    return {"code_identity": "c" * 64, "runtime_identity": "r" * 64, "governing_identity": "g" * 64}


def _paths(d):
    return {"report_path": os.path.join(d, "report.json"),
            "publication_path": os.path.join(d, "publication.json"),
            "stderr_path": os.path.join(d, "stderr.log")}


def test_T4_30_publishes_once_and_locks_read_only():
    with tempfile.TemporaryDirectory() as d:
        p = _paths(d)
        rec = PUB.publish({"disposition": "PASS", "x": 1}, disposition="PASS", exit_code=0,
                          identities=_identities(), published_at=PUBLISHED_AT, **p)
        assert rec["exit_disposition_agreement"] is True
        v = PUB.verify_published(p["publication_path"], p["report_path"])
        assert v["report_sha256_matches"] is True and v["locked_readonly"] is True
        for path in p.values():
            assert not os.stat(path).st_mode & stat.S_IWUSR


def test_T4_31_occupied_destination_refuses_and_does_not_overwrite():
    with tempfile.TemporaryDirectory() as d:
        p = _paths(d)
        with open(p["report_path"], "wb") as fh:
            fh.write(b"PRIOR RUN")
        with pytest.raises(PUB.PublicationRefused) as exc:
            PUB.publish({"disposition": "PASS"}, disposition="PASS", exit_code=0,
                        identities=_identities(), published_at=PUBLISHED_AT, **p)
        assert "destination_occupied" in str(exc.value)
        with open(p["report_path"], "rb") as fh:
            assert fh.read() == b"PRIOR RUN"
        assert not os.path.exists(p["publication_path"])


@pytest.mark.parametrize("disposition,exit_code", [("PASS", 1), ("FAIL", 0), ("REFUSED", 0),
                                                   ("INTEGRITY_STOP", 0), ("PASS", 3)])
def test_T4_32_exit_disposition_disagreement_refuses(disposition, exit_code):
    with tempfile.TemporaryDirectory() as d:
        with pytest.raises(PUB.PublicationRefused) as exc:
            PUB.publish({"disposition": disposition}, disposition=disposition, exit_code=exit_code,
                        identities=_identities(), published_at=PUBLISHED_AT, **_paths(d))
        assert "exit_disposition_disagreement" in str(exc.value)


@pytest.mark.parametrize("disposition", list(PUB.DISPOSITIONS))
def test_T4_33_every_disposition_publishes_verbatim_at_its_exit_code(disposition):
    with tempfile.TemporaryDirectory() as d:
        p = _paths(d)
        rec = PUB.publish({"disposition": disposition}, disposition=disposition,
                          exit_code=PUB.EXIT_BY_DISPOSITION[disposition],
                          identities=_identities(), published_at=PUBLISHED_AT, **p)
        assert rec["disposition"] == disposition
        with open(p["report_path"], "rb") as fh:
            assert json.loads(fh.read())["disposition"] == disposition


def test_T4_34_report_disposition_conflict_refuses():
    with tempfile.TemporaryDirectory() as d:
        with pytest.raises(PUB.PublicationRefused) as exc:
            PUB.publish({"disposition": "FAIL"}, disposition="PASS", exit_code=0,
                        identities=_identities(), published_at=PUBLISHED_AT, **_paths(d))
        assert "report_disposition_conflict" in str(exc.value)


@pytest.mark.parametrize("missing", ["code_identity", "runtime_identity", "governing_identity"])
def test_T4_35_missing_identity_refuses_publication(missing):
    with tempfile.TemporaryDirectory() as d:
        ids = _identities()
        ids[missing] = ""
        with pytest.raises(PUB.PublicationRefused) as exc:
            PUB.publish({"disposition": "PASS"}, disposition="PASS", exit_code=0,
                        identities=ids, published_at=PUBLISHED_AT, **_paths(d))
        assert f"identity_absent:{missing}" in str(exc.value)


def test_T4_36_unknown_disposition_refuses():
    with pytest.raises(PUB.PublicationRefused) as exc:
        PUB.verify_exit_agreement("MOSTLY_PASS", 0)
    assert "unknown_disposition" in str(exc.value)


def test_T4_37_second_publication_to_the_same_paths_refuses():
    with tempfile.TemporaryDirectory() as d:
        p = _paths(d)
        PUB.publish({"disposition": "PASS"}, disposition="PASS", exit_code=0,
                    identities=_identities(), published_at=PUBLISHED_AT, **p)
        with pytest.raises(PUB.PublicationRefused):
            PUB.publish({"disposition": "PASS"}, disposition="PASS", exit_code=0,
                        identities=_identities(), published_at=PUBLISHED_AT, **p)


def test_T4_38_publication_is_deterministic_for_identical_inputs():
    shas = []
    for _ in range(2):
        with tempfile.TemporaryDirectory() as d:
            p = _paths(d)
            rec = PUB.publish({"disposition": "PASS", "x": 1}, disposition="PASS", exit_code=0,
                              identities=_identities(), published_at=PUBLISHED_AT, **p)
            shas.append((rec["report_sha256"], rec["publication_sha256"]))
    assert shas[0] == shas[1]


# =====================================================================================
# T4-39..T4-41 — boundary assertions for the whole increment
# =====================================================================================
def test_T4_39_no_module_imports_a_dataset_or_partition_path():
    """The operational modules must contain no real data path or partition literal."""
    for mod in ("mr002_valoos_runtime.py", "mr002_valoos_code_identity.py",
                "mr002_valoos_access_boundary.py", "mr002_valoos_publication.py"):
        with open(os.path.join(HERE, mod), encoding="utf-8") as fh:
            src = fh.read().lower()
        for token in ("duckdb", "parquet", ".csv", "s3://", "sharadar", "alpaca"):
            assert token not in src, f"{mod} references {token}"


def test_T4_40_access_boundary_has_no_bypass_for_sealed_partitions():
    b = _boundary(state=_state(authorized=True), expected_rev=0)
    permitted, reason = b.partition_permitted(AB.OOS)
    assert permitted is False and "separate_authorization" in reason
    for partition in AB.SEALED_PARTITIONS:
        assert partition in (AB.VALIDATION, AB.OOS)


def test_T4_41_boundary_report_shape_is_evidence_grade():
    b = _boundary()
    with pytest.raises(AB.AccessBoundaryViolation):
        b.open_object(AB.VALIDATION, "validation/registered_object")
    rep = b.boundary_report()
    assert rep["record_type"] == "MR002_Increment4_AccessBoundaryReport"
    assert rep["validation_authorization"] is False
    assert rep["counts"]["blocked"] == 1 and rep["sealed_reads_zero"] is True
    assert rep["opened_object_ledger"][0]["permitted"] is False
