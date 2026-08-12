"""Tests for WP-F — the closed grant-readiness verification.

A grant-readiness verifier is the most dangerous kind of check to get wrong,
because its output is an input to opening sealed data. The failure that matters
is not a false FAIL, it is a false PASS. So almost every test here breaks one
condition and asserts the verifier NOTICES.

Two properties get special attention:

  * **K4 is enforced against the verifier's own source.** The adjudication that
    let P7 survive also forbade the method that endangered it: never prove DENY
    with a live sealed-object read. A verifier that could issue one would
    reintroduce the exact defect it exists to certify against.
  * **The stale anchor is rejected by name.** Binding to the 2026-07-22 digest
    would let a materially changed program inherit an old approval.

No network and no AWS: the resolver is injected.
"""

from __future__ import annotations

import copy
import importlib.util
import json
import sys
from pathlib import Path

import pytest

MODULE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(MODULE_DIR))


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, MODULE_DIR / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


W = _load("wp_f_grant_readiness")


class StubResolver:
    """Stands in for the WP-B resolver. Touches ECR only in reality; nothing here."""

    class ImageResolutionRefused(RuntimeError):
        def __init__(self, reason, detail=""):
            super().__init__(reason)
            self.reason = reason
            self.detail = detail

    SUPERSEDED_DIGESTS = {
        "sha256:60b15568aa5960ee04cf10b8c9b006d2ee702aa815a17384beffc979ed4554c9": "historical",
        "sha256:4d1945a64c114c078db2be1938c40f64faa24191d12c7355174b3ddbeef7969b": "not an index",
    }

    def __init__(self, *, digest=W.BOUND_INDEX, req7=True, refuse_superseded=True):
        self._digest, self._req7, self._refuse = digest, req7, refuse_superseded

    def resolve_bound_image(self, *, expected_digest=None, client=None):
        if expected_digest in self.SUPERSEDED_DIGESTS:
            if self._refuse:
                raise self.ImageResolutionRefused("superseded_digest")
            return {"image_digest": expected_digest, "satisfies_requirement_7": True,
                    "manifest_count": 1}
        return {"image_digest": self._digest, "satisfies_requirement_7": self._req7,
                "manifest_count": 1}


def status_of(report, cid):
    return next(f["status"] for f in report["findings"] if f["condition"] == cid)


# ---------------------------------------------------------------------------
# The real, current state
# ---------------------------------------------------------------------------


def test_the_current_program_state_passes_every_condition():
    report = W.run(StubResolver())
    failures = [f for f in report["findings"] if f["status"] != "PASS"]
    assert not failures, json.dumps(failures, indent=1)
    assert report["verdict"] == "PASS"
    assert report["conditions_evaluated"] == 12


def test_the_run_grants_nothing():
    report = W.run(StubResolver())
    assert "NOTHING" in report["authorizes"]


# ---------------------------------------------------------------------------
# The anchor
# ---------------------------------------------------------------------------


def test_anchor_is_recomputed_and_differs_from_the_stale_digest():
    reg = W._load(W.REGISTER)
    a = W.compute_anchor(reg)
    assert a["prerequisite_anchor_sha256"] != W.STALE_ANCHOR
    assert a["stale_anchor_rejected"] == W.STALE_ANCHOR
    assert a["anchor_differs_from_stale"] is True
    assert a["computed_from"] == W.REGISTER.name


def test_anchor_changes_when_any_prerequisite_status_changes():
    """The anchor must be sensitive to the thing it anchors."""
    reg = W._load(W.REGISTER)
    before = W.compute_anchor(reg)["prerequisite_anchor_sha256"]
    mutated = copy.deepcopy(reg)
    for p in mutated["prerequisites"]:
        if p["id"] == "P10":
            p["status"] = "NOT_PRODUCED"
    assert W.compute_anchor(mutated)["prerequisite_anchor_sha256"] != before


def test_recomputing_the_stale_anchor_is_a_hard_stop():
    reg = W._load(W.REGISTER)
    mutated = copy.deepcopy(reg)
    mutated["prerequisites"] = [{"id": "X", "status": "Y"}]
    W.STALE_ANCHOR_BACKUP = W.STALE_ANCHOR
    try:
        W.STALE_ANCHOR = W.compute_anchor(mutated)["prerequisite_anchor_sha256"]
        with pytest.raises(SystemExit):
            W.compute_anchor(mutated)
    finally:
        W.STALE_ANCHOR = W.STALE_ANCHOR_BACKUP


# ---------------------------------------------------------------------------
# C1 / C10 — the two that bound the grant itself
# ---------------------------------------------------------------------------


def test_c1_fails_if_any_blocking_prerequisite_is_unsatisfied():
    reg = copy.deepcopy(W._load(W.REGISTER))
    for p in reg["prerequisites"]:
        if p["id"] == "P10":
            p["status"] = "NOT_PRODUCED"
    assert W.check_c1(reg)["status"] == "FAIL"


def test_c1_excludes_p12_because_it_is_the_authorization_event():
    reg = W._load(W.REGISTER)
    f = W.check_c1(reg)
    assert f["status"] == "PASS"
    assert "P12" in f["detail"]


def test_c1_fails_if_p12_has_somehow_been_executed():
    reg = copy.deepcopy(W._load(W.REGISTER))
    for p in reg["prerequisites"]:
        if p["id"] == "P12":
            p["status"] = "SATISFIED"
    assert W.check_c1(reg)["status"] == "FAIL"


def test_c10_fails_if_authorization_were_true(tmp_path, monkeypatch):
    st = copy.deepcopy(W._load(W.AUTH_STATE))
    st["validation_authorization"] = True
    p = tmp_path / "state.json"
    p.write_text(json.dumps(st), encoding="utf-8")
    monkeypatch.setattr(W, "AUTH_STATE", p)
    assert W.check_c10()["status"] == "FAIL"


def test_c10_fails_if_rev_moved(tmp_path, monkeypatch):
    st = copy.deepcopy(W._load(W.AUTH_STATE))
    st["_rev"] = 1
    p = tmp_path / "state.json"
    p.write_text(json.dumps(st), encoding="utf-8")
    monkeypatch.setattr(W, "AUTH_STATE", p)
    assert W.check_c10()["status"] == "FAIL"


# ---------------------------------------------------------------------------
# C-R7 and K4 — the two conditions born from real defects
# ---------------------------------------------------------------------------


def test_cr7_fails_if_a_superseded_root_resolves():
    """The exact defect found on the first rebind: the predecessor is a well-formed
    index whose bytes rehash correctly, so it resolved until refused by name."""
    r = StubResolver(refuse_superseded=False)
    f = W.check_cr7(r, r.resolve_bound_image())
    assert f["status"] == "FAIL"
    assert "RESOLVED" in f["detail"]


def test_cr7_fails_if_the_resolver_returns_the_wrong_digest():
    r = StubResolver(digest="sha256:" + "ab" * 32)
    assert W.check_cr7(r, r.resolve_bound_image())["status"] == "FAIL"


def test_cr7_fails_if_requirement_7_flag_is_absent():
    r = StubResolver(req7=False)
    assert W.check_cr7(r, r.resolve_bound_image())["status"] == "FAIL"


def test_k4_passes_and_is_asserted_against_the_real_source():
    assert W.check_k4()["status"] == "PASS"


def test_k4_would_fail_if_a_sealed_read_call_existed(monkeypatch, tmp_path):
    """Proves K4 is a real check, not a constant. A verifier able to probe sealed
    objects would reintroduce the defect it exists to certify against."""
    fake = tmp_path / "wp_f_grant_readiness.py"
    fake.write_text('"""doc"""\ns3.get_object(Bucket="x", Key="y")\n', encoding="utf-8")
    monkeypatch.setattr(W, "__file__", str(fake))
    assert W.check_k4()["status"] == "FAIL"


def test_the_verifier_source_contains_no_sealed_object_read():
    source = (MODULE_DIR / "wp_f_grant_readiness.py").read_text(encoding="utf-8")
    body = source.split('"""', 2)[-1]
    for forbidden in ("get_object(", "head_object(", "download_file(",
                      "select_object_content("):
        assert forbidden not in body


# ---------------------------------------------------------------------------
# C7 — the access-event condition, under the ratified classification
# ---------------------------------------------------------------------------


def test_c7_passes_with_denied_attempts_present_but_zero_successful_reads():
    f = W.check_c7()
    assert f["status"] == "PASS"
    assert "denied ATTEMPTS recorded=2" in f["detail"]


def test_c7_fails_on_a_successful_sealed_read(tmp_path, monkeypatch):
    """The distinction the adjudication drew: attempts are recorded, ACCESSES are fatal."""
    p7 = copy.deepcopy(W._load(W.P7))
    p7["observed_gate_values"]["validation_access_events_before_authorization"] = 1
    p = tmp_path / "p7.json"
    p.write_text(json.dumps(p7), encoding="utf-8")
    monkeypatch.setattr(W, "P7", p)
    assert W.check_c7()["status"] == "FAIL"


def test_c7_fails_if_the_adjudication_is_not_ratified(tmp_path, monkeypatch):
    adj = copy.deepcopy(W._load(W.ADJUDICATION))
    adj["status"] = "AWAITING_OWNER_RATIFICATION"
    p = tmp_path / "adj.json"
    p.write_text(json.dumps(adj), encoding="utf-8")
    monkeypatch.setattr(W, "ADJUDICATION", p)
    assert W.check_c7()["status"] == "FAIL"


def test_c7_fails_if_the_hash_chain_is_broken(tmp_path, monkeypatch):
    p7 = copy.deepcopy(W._load(W.P7))
    p7["hash_chain"]["verifies"] = False
    p = tmp_path / "p7.json"
    p.write_text(json.dumps(p7), encoding="utf-8")
    monkeypatch.setattr(W, "P7", p)
    assert W.check_c7()["status"] == "FAIL"


# ---------------------------------------------------------------------------
# C6 / C9 — runtime and evaluator identity
# ---------------------------------------------------------------------------


def test_c6_fails_if_p10_binds_a_different_image(tmp_path, monkeypatch):
    p10 = copy.deepcopy(W._load(W.P10))
    p10["bindings"]["container_image_digest"]["digest"] = "sha256:" + "cd" * 32
    p = tmp_path / "p10.json"
    p.write_text(json.dumps(p10), encoding="utf-8")
    monkeypatch.setattr(W, "P10", p)
    r = StubResolver()
    assert W.check_c6(r.resolve_bound_image())["status"] == "FAIL"


def test_c6_fails_if_the_runtime_drifted_from_the_frozen_host(tmp_path, monkeypatch):
    p10 = copy.deepcopy(W._load(W.P10))
    p10["bindings"]["numpy_version"] = "9.9.9"
    p = tmp_path / "p10.json"
    p.write_text(json.dumps(p10), encoding="utf-8")
    monkeypatch.setattr(W, "P10", p)
    r = StubResolver()
    f = W.check_c6(r.resolve_bound_image())
    assert f["status"] == "FAIL"
    assert "numpy_version" in f["detail"]


def test_c6_records_that_it_does_not_recapture_p10():
    r = StubResolver()
    f = W.check_c6(r.resolve_bound_image())
    assert "not authorized" in f["limitation"]


def test_c9_detects_evaluator_drift(tmp_path, monkeypatch):
    manifest = copy.deepcopy(W._load(W.IMAGE_MANIFEST))
    key = next(iter(manifest["module_digests_in_image"]))
    manifest["module_digests_in_image"][key] = "0" * 64
    p = tmp_path / "im.json"
    p.write_text(json.dumps(manifest), encoding="utf-8")
    monkeypatch.setattr(W, "IMAGE_MANIFEST", p)
    f = W.check_c9()
    assert f["status"] == "FAIL"


def test_c5_declares_that_it_does_not_reread_the_corpus():
    """A condition that silently redefines itself to pass is worse than one that
    reports its limit."""
    f = W.check_c5()
    assert f["status"] == "PASS"
    assert "NOT AUTHORIZED TO PERFORM" in f["limitation"]


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))


# ---------------------------------------------------------------------------
# C8 vacuity — the defect that made the first execution void
# ---------------------------------------------------------------------------


def test_c8_actually_rehashes_a_meaningful_sample():
    """The first build of C8 looked for a 'sha256' key that the lineage record does
    not use, matched nothing, and reported PASS on an empty sample."""
    f = W.check_c8()
    assert f["status"] == "PASS"
    assert "sample_is_meaningful=True" in f["detail"]
    assert "0 bound artifacts" not in f["detail"]


def test_c8_fails_on_an_empty_sample(tmp_path, monkeypatch):
    """A check that can pass while examining nothing is not a check."""
    lineage = {"phase3a_artifacts": {"artifacts": {}, "manifest_bound_artifact_count": 25}}
    p = tmp_path / "lineage.json"
    p.write_text(json.dumps(lineage), encoding="utf-8")
    monkeypatch.setattr(W, "LINEAGE", p)
    f = W.check_c8()
    assert f["status"] == "FAIL"
    assert "sample_is_meaningful=False" in f["detail"]


def test_c8_fails_on_a_short_sample(tmp_path, monkeypatch):
    """Fewer artifacts re-hashed than the manifest binds means silent under-coverage."""
    real = W._load(W.LINEAGE)
    arts = dict(list(real["phase3a_artifacts"]["artifacts"].items())[:2])
    lineage = {"phase3a_artifacts": {"artifacts": arts,
                                     "manifest_bound_artifact_count": 25}}
    p = tmp_path / "lineage.json"
    p.write_text(json.dumps(lineage), encoding="utf-8")
    monkeypatch.setattr(W, "LINEAGE", p)
    assert W.check_c8()["status"] == "FAIL"


def test_c8_detects_real_drift(tmp_path, monkeypatch):
    real = copy.deepcopy(W._load(W.LINEAGE))
    name = next(iter(real["phase3a_artifacts"]["artifacts"]))
    real["phase3a_artifacts"]["artifacts"][name]["bound_sha256"] = "0" * 64
    p = tmp_path / "lineage.json"
    p.write_text(json.dumps(real), encoding="utf-8")
    monkeypatch.setattr(W, "LINEAGE", p)
    f = W.check_c8()
    assert f["status"] == "FAIL"
    assert name in f["detail"]
