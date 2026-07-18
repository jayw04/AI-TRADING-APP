"""MR-002 Stage-3 — clean successor runner + orchestration tests (review cycle 3).

Synthetic rows, REAL row-identity manifests (64-hex hashes via the runner's own derivation), real
temp-file checkpoints, and outcomes built through the REAL cascade (`stage3_cascade.resolve` with stub
solvers). Proves the cycle-3 enforcement guarantees: independent corpus hashing, strict self-verifying
checkpoints, sidecar preservation, authorization semantics + cross-validation, and fail-closed
orchestration — all without the solver stack.
"""

from __future__ import annotations

import json
from types import SimpleNamespace

import numpy as np
import pytest

from app.research.mr002 import stage3_cascade as sc
from scripts import mr002_stage3_population_runner as run


# ── distinct valid tiny problems ─────────────────────────────────────────────────────────────────
def rec(i: int):
    return (np.array([0.008 + i * 1e-4, 0.008]), np.array([[1.0, 1.0]]), np.array([0.01]),
            np.zeros((0, 2)), np.zeros(0), np.array([0.02, 0.02]))


Z = np.array([0.005, 0.005])
LAM = np.zeros(5)


def good_cert(qualifies=True):
    vals = {f: 0.0 for f in sc.REQUIRED_CERT_FIELDS}
    vals["qualifies"] = qualifies
    vals["n_multipliers_clipped"] = 0          # must be a real int (cycle-4 finding 18)
    return SimpleNamespace(**vals)


def qualified_outcome():
    return sc.resolve(rec(0), primary=lambda *_a: (Z, LAM), fallback=lambda *_a: (Z, LAM),
                      certify_fn=lambda *_a: (True, [], good_cert()))


def stop_outcome(disp=sc.INVALID_RUN):
    return sc.Outcome(disp, primary=sc.Attempt(sc.PRIMARY_SOLVER_ID, sc.INTEGRITY_DEFECT, "x"))


class ScriptedResolver:
    def __init__(self, outcomes):
        self._outcomes = list(outcomes)
        self.calls = 0

    def __call__(self, _rec):
        o = self._outcomes[self.calls]
        self.calls += 1
        return o


def rows_and_manifest(n):
    recs = [sc.canonicalize(rec(i)) for i in range(n)]
    rows = [(i, recs[i]) for i in range(n)]
    manifest = run.RowIdentityManifest(
        corpus_hash=run.derive_corpus_hash(recs),
        rows=tuple({"row_id": i, "content_hash": sc.rec_content_hash(recs[i])} for i in range(n)))
    return rows, manifest


def ckpt(tmp_path):
    return str(tmp_path / "clean_run.jsonl")


def _run(rows, outcomes, cp, m, **kw):
    return run.run_population(rows, ScriptedResolver(outcomes), cp,
                             preflight_passed=True, row_manifest=m, **kw)


# ══════════════════════════════════════════════ gates ══════════════════════════════════════════
def test_preflight_fail_refuses_and_resolves_nothing(tmp_path):
    rows, m = rows_and_manifest(3)
    r = ScriptedResolver([qualified_outcome()] * 3)
    res = run.run_population(rows, r, ckpt(tmp_path), preflight_passed=False, row_manifest=m)
    assert res.refused and res.refusal_reason == "PREFLIGHT_NOT_PASSED" and r.calls == 0


def test_validation_window_is_refused(tmp_path):
    rows, m = rows_and_manifest(1)
    with pytest.raises(run.WindowAccessError):
        _run(rows, [qualified_outcome()], ckpt(tmp_path), m, windows=("validation",))


# ══════════════════════════════ row-manifest schema (finding 14) ═══════════════════════════════
def test_short_corpus_hash_refused(tmp_path):
    _, m0 = rows_and_manifest(1)
    m = run.RowIdentityManifest(corpus_hash="deadbeef", rows=m0.rows)   # not 64-hex
    res = _run([(0, rec(0))], [qualified_outcome()], ckpt(tmp_path), m)
    assert res.refused and "CORPUS_HASH_NOT_64HEX" in res.refusal_reason


def test_malformed_row_entry_refused(tmp_path):
    _, m0 = rows_and_manifest(1)
    m = run.RowIdentityManifest(corpus_hash=m0.corpus_hash,
                                rows=({"row_id": 0, "content_hash": "abc", "extra": 1},))
    res = _run([(0, rec(0))], [qualified_outcome()], ckpt(tmp_path), m)
    assert res.refused and "ROW_ENTRY_MALFORMED" in res.refusal_reason


def test_short_content_hash_refused(tmp_path):
    _, m0 = rows_and_manifest(1)
    m = run.RowIdentityManifest(corpus_hash=m0.corpus_hash,
                                rows=({"row_id": 0, "content_hash": "ff"},))
    res = _run([(0, rec(0))], [qualified_outcome()], ckpt(tmp_path), m)
    assert res.refused and "CONTENT_HASH_NOT_64HEX" in res.refusal_reason


def test_duplicate_row_ids_refused(tmp_path):
    _, m0 = rows_and_manifest(2)
    m = run.RowIdentityManifest(corpus_hash=m0.corpus_hash,
                                rows=(m0.rows[0], {**m0.rows[1], "row_id": 0}))
    res = _run([(0, rec(0)), (0, rec(1))], [], ckpt(tmp_path), m)
    assert res.refused and "DUPLICATE_ROW_IDS" in res.refusal_reason


# ═══════════════════ happy path: full evidence incl. complete input (finding 8) ═════════════════
def test_all_qualified_passes_and_preserves_full_evidence(tmp_path):
    cp = ckpt(tmp_path)
    rows, m = rows_and_manifest(3)
    res = _run(rows, [qualified_outcome() for _ in range(3)], cp, m)
    assert res.passed is True and res.n_qualified == 3 and res.evidence_persisted is True
    state = run.read_checkpoint(cp)
    assert not state["corruption"]
    rec0 = state["records"][0]
    assert rec0["input_content_hash"] == m.rows[0]["content_hash"]
    assert set(rec0["input"].keys()) == {"t", "A_ub", "b_ub", "A_eq", "b_eq", "upper"}
    assert rec0["input"]["t"]["exact_ratio"]                  # complete input preserved
    assert rec0["accepted"]["certificate"]["qualifies"] is True
    assert rec0["record_sha256"] == run._record_hash(rec0)


# ═════════════════════════ STOP + malformed-outcome (findings 7, 30) ════════════════════════════
def test_stop_halts_immediately_no_later_row(tmp_path):
    cp = ckpt(tmp_path)
    rows, m = rows_and_manifest(5)
    r = ScriptedResolver([qualified_outcome(), qualified_outcome(), stop_outcome(),
                          qualified_outcome(), qualified_outcome()])
    res = run.run_population(rows, r, cp, preflight_passed=True, row_manifest=m)
    assert res.stopped and res.stop_row == 2 and r.calls == 3
    assert res.passed is False and res.resumable is False
    assert run.read_checkpoint(cp)["terminal"]["status"] == run.TERMINAL_FAILED


def test_malformed_qualified_outcome_is_rejected(tmp_path):
    malformed = sc.Outcome(sc.PRIMARY_QUALIFIED,
                           primary=sc.Attempt(sc.PRIMARY_SOLVER_ID, sc.QUALIFIED, "PASS"),
                           accepted_by=sc.PRIMARY_SOLVER_ID)     # no evidence
    rows, m = rows_and_manifest(2)
    res = _run(rows, [malformed, qualified_outcome()], ckpt(tmp_path), m)
    assert res.stopped and "QUALIFIED_MISSING_NUMERICAL_EVIDENCE" in res.stop_reason


def test_wrong_solver_id_outcome_is_rejected(tmp_path):
    bad = sc.Outcome(sc.PRIMARY_QUALIFIED,
                     primary=sc.Attempt("NOT_A_SOLVER", sc.QUALIFIED, "PASS"),
                     accepted_by=sc.PRIMARY_SOLVER_ID)
    rows, m = rows_and_manifest(1)
    res = _run(rows, [bad], ckpt(tmp_path), m)
    assert res.stopped and "PRIMARY_SOLVER_ID_MISMATCH" in res.stop_reason


def test_certificate_not_qualifying_outcome_is_rejected(tmp_path):
    o = sc.resolve(rec(0), primary=lambda *_a: (Z, LAM), fallback=lambda *_a: (Z, LAM),
                   certify_fn=lambda *_a: (True, [], good_cert(qualifies=False)))
    rows, m = rows_and_manifest(1)
    res = _run(rows, [o], ckpt(tmp_path), m)
    assert res.stopped and "CERTIFICATE_QUALIFIES_NOT_TRUE" in res.stop_reason


# ═══════════════ exceptions + sidecar preservation (findings 8, 10, 11) ═════════════════════════
def test_resolver_exception_preserved_as_failed_terminal(tmp_path):
    cp = ckpt(tmp_path)
    rows, m = rows_and_manifest(3)

    def boom(_rec):
        raise RuntimeError("solver process died")

    res = run.run_population(rows, boom, cp, preflight_passed=True, row_manifest=m)
    assert res.stopped and res.stop_reason == "RESOLVER_ERROR"
    term = run.read_checkpoint(cp)["terminal"]
    assert term["exception_class"] == "RuntimeError" and term["traceback_sha256"]


def test_row_iterator_creation_failure_preserved(tmp_path):
    class BadRows:
        def __iter__(self):
            raise OSError("cannot enumerate")
    rows, m = rows_and_manifest(2)
    res = run.run_population(BadRows(), ScriptedResolver([]), ckpt(tmp_path),
                             preflight_passed=True, row_manifest=m)
    assert res.stopped and res.stop_reason == "ROW_ITERATOR_ERROR"


def test_drain_iterator_failure_preserved(tmp_path):
    rows, m = rows_and_manifest(1)

    def gen():
        yield rows[0]
        raise OSError("post-population fault")
    res = run.run_population(gen(), ScriptedResolver([qualified_outcome()]), ckpt(tmp_path),
                             preflight_passed=True, row_manifest=m)
    assert res.stopped and res.stop_reason == "ROW_ITERATOR_ERROR"


def test_terminal_write_failure_writes_sidecar(tmp_path, monkeypatch):
    cp = ckpt(tmp_path)
    rows, m = rows_and_manifest(2)

    def failing_mark(self, reason, row_id, extra=None):
        raise OSError("disk full")
    monkeypatch.setattr(run.CheckpointSink, "mark_failed", failing_mark)
    res = _run([rows[0], (1, rec(9))], [qualified_outcome()], cp, m)   # row-1 hash mismatch → stop
    assert res.stopped and res.evidence_persisted is True              # sidecar succeeded
    with open(cp + ".emergency.1.json", encoding="utf-8") as fh:
        sidecar = json.load(fh)
    assert sidecar["status"] == run.TERMINAL_FAILED


# ══════════════ strict checkpoint + self-verifying aggregate (findings 12, 13) ══════════════════
def test_midfile_malformed_line_is_corruption(tmp_path):
    cp = ckpt(tmp_path)
    with open(cp, "w", encoding="utf-8") as fh:
        fh.write('{"kind":"record","row_id":0}\nGARBAGE\n{"kind":"record","row_id":1}\n')
    state = run.read_checkpoint(cp)
    assert any("MALFORMED_LINE" in c for c in state["corruption"])
    assert run.precheck_checkpoint(cp).startswith("CHECKPOINT_CORRUPT")


def test_unknown_event_kind_is_corruption(tmp_path):
    cp = ckpt(tmp_path)
    with open(cp, "w", encoding="utf-8") as fh:
        fh.write('{"kind":"mystery"}\n{"kind":"record","row_id":0}\n')
    assert any("UNKNOWN_EVENT" in c for c in run.read_checkpoint(cp)["corruption"])


def test_record_after_terminal_is_corruption(tmp_path):
    cp = ckpt(tmp_path)
    with open(cp, "w", encoding="utf-8") as fh:
        fh.write('{"kind":"terminal","status":"COMPLETE","n_records":0}\n'
                 '{"kind":"record","row_id":0}\n')
    assert any("EVENT_AFTER_TERMINAL" in c for c in run.read_checkpoint(cp)["corruption"])


def _edit_line(cp, index, mutate):
    with open(cp, encoding="utf-8") as fh:
        lines = fh.read().splitlines()
    obj = json.loads(lines[index])
    mutate(obj)
    lines[index] = json.dumps(obj, separators=(",", ":"))
    with open(cp, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")


def test_tampered_record_hash_fails_aggregate(tmp_path):
    cp = ckpt(tmp_path)
    rows, m = rows_and_manifest(2)
    res = _run(rows, [qualified_outcome(), qualified_outcome()], cp, m)
    assert res.passed is True
    # tamper: alter a record's evidence without updating record_sha256
    _edit_line(cp, 0, lambda o: o["accepted"].__setitem__("z_sha256", "0" * 64))
    assert run.aggregate_verdict(run.read_checkpoint(cp), m) is False


def test_terminal_count_mismatch_fails_aggregate(tmp_path):
    cp = ckpt(tmp_path)
    rows, m = rows_and_manifest(1)
    _run(rows, [qualified_outcome()], cp, m)
    _edit_line(cp, -1, lambda o: o.__setitem__("n_records", 99))
    assert run.aggregate_verdict(run.read_checkpoint(cp), m) is False


# ═══════════════════ row identity + count enforcement (findings 11, 12) ═════════════════════════
def test_row_order_mismatch_stops(tmp_path):
    rows, m = rows_and_manifest(3)
    res = _run([rows[0], rows[2], rows[1]], [qualified_outcome()] * 3, ckpt(tmp_path), m)
    assert res.stopped and res.stop_reason == "ROW_ID_ORDER_MISMATCH"


def test_row_content_hash_mismatch_stops(tmp_path):
    rows, m = rows_and_manifest(2)
    res = _run([(0, rec(9)), rows[1]], [qualified_outcome()] * 2, ckpt(tmp_path), m)
    assert res.stopped and res.stop_reason == "ROW_CONTENT_HASH_MISMATCH"


def test_population_shorter_than_manifest_stops(tmp_path):
    rows, m = rows_and_manifest(3)
    res = _run(rows[:2], [qualified_outcome()] * 3, ckpt(tmp_path), m)
    assert res.stopped and res.stop_reason == "POPULATION_SHORTER_THAN_MANIFEST"


def test_population_longer_than_manifest_stops(tmp_path):
    rows, m = rows_and_manifest(2)
    res = _run([*rows, (2, rec(2))], [qualified_outcome()] * 3, ckpt(tmp_path), m)
    assert res.stopped and res.stop_reason == "POPULATION_LONGER_THAN_MANIFEST"


# ═══════════════════════════ checkpoint refusal (findings 9, 10) ════════════════════════════════
def test_refuses_preexisting_failed_checkpoint(tmp_path):
    cp = ckpt(tmp_path)
    rows, m = rows_and_manifest(2)
    _run([rows[0], (1, rec(9))], [qualified_outcome()], cp, m)
    with pytest.raises(run.CheckpointRefused):
        _run(rows, [qualified_outcome()] * 2, cp, m)


def test_refuses_preexisting_complete_checkpoint(tmp_path):
    cp = ckpt(tmp_path)
    rows, m = rows_and_manifest(2)
    _run(rows, [qualified_outcome()] * 2, cp, m)
    with pytest.raises(run.CheckpointRefused):
        _run(rows, [qualified_outcome()] * 2, cp, m)


def test_refuses_trailing_partial_checkpoint(tmp_path):
    cp = ckpt(tmp_path)
    with open(cp, "w", encoding="utf-8") as fh:
        fh.write('{"kind":"record","row_id":0}\n{"kind":"record","row_id":1')
    assert run.precheck_checkpoint(cp) == "CHECKPOINT_TRAILING_PARTIAL"


# ═══════════ orchestration: independent corpus hashing + fail-closed (findings 2, 17, 18) ═══════
PROV = {"database": {"path": "db", "sha256": "0" * 64, "byte_length": 1},
        "days": {"n_days": 2, "first": "2013-01-02", "last": "2013-01-03",
                 "sequence_sha256": "1" * 64}}


def _source(rows, m, claimed=None, prov=PROV):
    def src():
        return list(rows), claimed if claimed is not None else m.corpus_hash, m, prov
    return src


def _cfg(tmp_path, rows, m, **kw):
    defaults = dict(corpus_source=_source(rows, m), resolve_fn=lambda _r: qualified_outcome(),
                    checkpoint_path=ckpt(tmp_path), out_dir=str(tmp_path),
                    preflight_passed=True, expected_corpus_hash=m.corpus_hash,
                    provenance={"authorization_sha256": "x" * 64})
    defaults.update(kw)
    return run.OrchestrationConfig(**defaults)


def test_orchestration_dry_run_pass_binds_checkpoint_and_provenance(tmp_path):
    rows, m = rows_and_manifest(3)
    result = run.orchestrate(_cfg(tmp_path, rows, m))
    assert result.disposition == "PASS" and result.corpus_hash == m.corpus_hash
    with open(result.run_manifest_path, encoding="utf-8") as fh:
        doc = json.load(fh)
    assert doc["corpus_hash_derived_by_runner"] == m.corpus_hash
    assert doc["checkpoint_sha256"] == run._sha256_file(ckpt(tmp_path))   # finding 16
    assert doc["row_manifest_sha256"] == m.canonical_hash()
    assert doc["execution_provenance"]["authorization_sha256"] == "x" * 64  # finding 15


def test_orchestration_derives_hash_itself_lying_source_caught(tmp_path):
    # the source returns DIFFERENT rows but claims the expected hash — the runner derives from the
    # actual bytes and STOPs (finding 2)
    rows, m = rows_and_manifest(2)
    altered = [(0, sc.canonicalize(rec(7))), rows[1]]
    result = run.orchestrate(_cfg(tmp_path, altered, m, corpus_source=_source(altered, m)))
    assert result.disposition == "STOP" and result.detail.startswith("CORPUS_HASH_MISMATCH")


def test_orchestration_source_claimed_hash_inconsistency_caught(tmp_path):
    rows, m = rows_and_manifest(2)
    result = run.orchestrate(_cfg(tmp_path, rows, m,
                                  corpus_source=_source(rows, m, claimed="f" * 64)))
    assert result.disposition == "STOP" and result.detail == "CORPUS_SOURCE_CLAIMED_HASH_INCONSISTENT"


def test_orchestration_fails_closed_on_source_exception(tmp_path):
    rows, m = rows_and_manifest(1)

    def exploding_source():
        raise RuntimeError("dataset unavailable")
    result = run.orchestrate(_cfg(tmp_path, rows, m, corpus_source=exploding_source))
    assert result.disposition == "STOP" and result.detail.startswith("ORCHESTRATION_ERROR")


def test_orchestration_refuses_nonempty_out_dir(tmp_path):
    rows, m = rows_and_manifest(1)
    (tmp_path / "leftover.txt").write_text("old")
    result = run.orchestrate(_cfg(tmp_path, rows, m))
    assert result.disposition == "REFUSED" and "OUT_DIR_NOT_EMPTY" in result.detail


def test_orchestration_refuses_checkpoint_outside_root(tmp_path):
    rows, m = rows_and_manifest(1)
    outside = str(tmp_path.parent / "outside.jsonl")
    result = run.orchestrate(_cfg(tmp_path, rows, m, checkpoint_path=outside))
    assert result.disposition == "REFUSED" and "CHECKPOINT_OUTSIDE_OUTPUT_ROOT" in result.detail


def test_orchestration_refuses_without_preflight(tmp_path):
    rows, m = rows_and_manifest(1)
    assert run.orchestrate(_cfg(tmp_path, rows, m, preflight_passed=False)).disposition == "REFUSED"


# ═══════════ authorization semantics + cross-validation (findings 3, 4) ═════════════════════════
GOOD_AUTH = {
    "record_type": run.AUTHORIZATION_RECORD_TYPE, "version": run.AUTHORIZATION_VERSION,
    "record_status": "IMMUTABLE", "decision": "AUTHORIZED", "authorized_date": "2026-07-18",
    "execution_authorized": True, "countersigned_by": run.AUTHORIZED_COUNTERSIGNER,
    "repository": "jayw04/AI-TRADING-APP",
    "bound_commit": "c" * 40, "bound_tree": "t" * 40,
    "image_digest": "sha256:" + "a" * 64, "oci_config_digest": "sha256:" + "b" * 64,
    "source_manifest_sha256": "1" * 64, "expected_pins_sha256": "2" * 64,
    "row_manifest_protocol": run.ROW_MANIFEST_PROTOCOL,
    "execution_package_sha256": "3" * 64,
    "execution_package_version": run.SUPPORTED_EXECUTION_PACKAGE_VERSION,
}


def _write(tmp_path, name, obj):
    p = str(tmp_path / name)
    with open(p, "w", encoding="utf-8") as fh:
        json.dump(obj, fh)
    return p


def test_authorization_semantic_fields_enforced(tmp_path):
    for field_name, bad in [("record_type", "WRONG"), ("decision", "PENDING"),
                            ("execution_authorized", False), ("countersigned_by", ""),
                            ("repository", "other/repo"), ("version", "")]:
        art = {**GOOD_AUTH, field_name: bad}
        p = _write(tmp_path, f"auth_{field_name}.json", art)
        with pytest.raises(run.Stage3RunRefused):
            run.load_authorization(p, run._sha256_file(p))


def test_authorization_good_artifact_loads(tmp_path):
    p = _write(tmp_path, "auth.json", GOOD_AUTH)
    auth = run.load_authorization(p, run._sha256_file(p))
    assert auth["bound_commit"] == "c" * 40


def test_authorization_cross_validation_against_pins(tmp_path):
    from scripts.mr002_stage3_preflight import ExpectedPins
    pins = ExpectedPins(git_commit="c" * 40, git_tree="t" * 40,
                        image_digest="sha256:" + "a" * 64, oci_config_digest="sha256:" + "b" * 64)
    run.cross_validate_authorization(GOOD_AUTH, pins)      # consistent → no raise
    bad_pins = ExpectedPins(git_commit="d" * 40, git_tree="t" * 40,
                            image_digest="sha256:" + "a" * 64,
                            oci_config_digest="sha256:" + "b" * 64)
    with pytest.raises(run.Stage3RunRefused):
        run.cross_validate_authorization(GOOD_AUTH, bad_pins)


def test_load_expected_pins_requires_all_pins(tmp_path):
    p = _write(tmp_path, "pins.json", {"git_commit": "c", "git_tree": "t"})
    with pytest.raises(run.Stage3RunRefused):
        run.load_expected_pins(p, run._sha256_file(p))


def test_load_static_manifest_hash_mismatch_refused(tmp_path):
    p = _write(tmp_path, "man.json", {"files": {}})
    with pytest.raises(run.Stage3RunRefused):
        run.load_static_manifest(p, "notthehash")


def test_real_entry_refuses_without_authorization(monkeypatch):
    monkeypatch.delenv("MR002_EXECUTION_COUNTERSIGN", raising=False)
    monkeypatch.delenv("MR002_EXECUTION_COUNTERSIGN_SHA256", raising=False)
    assert run.run_clean_successor() == 2


# ═══════════════════════════ derivation scheme sanity ═══════════════════════════════════════════
def test_derive_corpus_hash_matches_registered_scheme():
    # independent local re-computation of the documented scheme
    import hashlib
    recs = [sc.canonicalize(rec(i)) for i in range(3)]
    per = []
    for r in recs:
        h = hashlib.sha256()
        for arr in r:
            a = np.ascontiguousarray(np.asarray(arr, dtype=np.float64))
            h.update(str(a.shape).encode())
            h.update(a.tobytes())
        per.append(h.hexdigest())
    assert run.derive_corpus_hash(recs) == hashlib.sha256("|".join(per).encode()).hexdigest()


# ═══════════════════════════════ cycle-4 additions ═══════════════════════════════════════════════
def test_invalid_run_with_qualified_primary_is_rejected():
    # cycle-4 finding 2 — INVALID_RUN paired with each inadmissible primary enum
    for enum in (sc.QUALIFIED, sc.NUMERICAL_STATUS_NONQUALIFICATION,
                 sc.CERTIFICATE_NONQUALIFICATION):
        o = sc.Outcome(sc.INVALID_RUN, primary=sc.Attempt(sc.PRIMARY_SOLVER_ID, enum, "x"))
        assert sc.validate_outcome(o) == "INVALID_RUN_INCONSISTENT_STATE", enum


def test_authorization_exact_schema_extras(tmp_path):
    # cycle-4 findings 6, 7 — wrong protocol/version/status/countersigner/pkg-version refused
    for field_name, bad in [("row_manifest_protocol", "anything"), ("version", "9.9"),
                            ("record_status", "DRAFT"), ("countersigned_by", "someone else"),
                            ("execution_package_version", "0.1"), ("authorized_date", "")]:
        art = {**GOOD_AUTH, field_name: bad}
        pth = _write(tmp_path, f"a_{field_name}.json", art)
        with pytest.raises(run.Stage3RunRefused):
            run.load_authorization(pth, run._sha256_file(pth))


def test_execution_package_bytes_verified(tmp_path):
    # cycle-4 finding 5
    pkg = {"record_type": "MR002_STAGE3_EXECUTION_PACKAGE",
           "version": run.SUPPORTED_EXECUTION_PACKAGE_VERSION}
    pth = _write(tmp_path, "pkg.json", pkg)
    auth = {**GOOD_AUTH, "execution_package_sha256": run._sha256_file(pth)}
    assert run.verify_execution_package(pth, auth)["version"] == run.SUPPORTED_EXECUTION_PACKAGE_VERSION
    with pytest.raises(run.Stage3RunRefused):
        run.verify_execution_package(pth, {**GOOD_AUTH, "execution_package_sha256": "0" * 64})
    bad = _write(tmp_path, "pkg_bad.json", {**pkg, "version": "0.0"})
    with pytest.raises(run.Stage3RunRefused):
        run.verify_execution_package(bad, {**GOOD_AUTH,
                                           "execution_package_sha256": run._sha256_file(bad)})


def test_pins_corpus_hash_mandatory(tmp_path):
    # cycle-4 finding 8
    pins = {"record_type": run.PINS_RECORD_TYPE, "version": run.PINS_VERSION,
            "record_status": "IMMUTABLE", "repository": "jayw04/AI-TRADING-APP",
            "git_commit": "c" * 40, "git_tree": "t" * 40,
            "image_digest": "sha256:" + "a" * 64, "oci_config_digest": "sha256:" + "b" * 64,
            "python_version": "3.12.5", "python_abi": "abi",
            "package_versions": {"numpy": "2"}, "material_config": {"x": 1},
            "fingerprints": {"resolve": "f"}}
    pth = _write(tmp_path, "pins_nocorpus.json", pins)
    with pytest.raises(run.Stage3RunRefused):
        run.load_expected_pins(pth, run._sha256_file(pth))


def test_evidence_replay_catches_tampered_ratios(tmp_path):
    # cycle-4 finding 9 — the attacker recomputes record_sha256 after tampering the ratios; the
    # outer checksum verifies but the semantic replay catches the input/content-hash mismatch
    cp = ckpt(tmp_path)
    rows, m = rows_and_manifest(1)
    _run(rows, [qualified_outcome()], cp, m)

    def tamper(o):
        o["input"]["t"]["exact_ratio"][0] = [1, 2]
        o["record_sha256"] = run._record_hash(o)
    _edit_line(cp, 0, tamper)
    state = run.read_checkpoint(cp)
    assert run.verify_numerical_evidence_record(state["records"][0]) is not None
    assert run.aggregate_verdict(state, m) is False


def test_close_failure_cannot_pass(tmp_path, monkeypatch):
    # cycle-4 finding 11
    cp = ckpt(tmp_path)
    rows, m = rows_and_manifest(1)

    def failing_close(self):
        raise OSError("close failed")
    monkeypatch.setattr(run.CheckpointSink, "close", failing_close)
    res = _run(rows, [qualified_outcome()], cp, m)
    assert res.passed is False and res.stopped is True and res.evidence_persisted is False
    import os as _os
    assert _os.path.exists(cp + ".emergency.1.json")


def test_record_write_failure_sets_evidence_not_persisted(tmp_path, monkeypatch):
    # cycle-4 finding 12
    cp = ckpt(tmp_path)
    rows, m = rows_and_manifest(1)

    def bad_write(self, rec_):
        self._fh.write("{PARTIAL")
        raise OSError("disk error mid-record")
    monkeypatch.setattr(run.CheckpointSink, "write_record", bad_write)
    res = _run(rows, [qualified_outcome()], cp, m)
    assert res.stopped and res.stop_reason == "RECORD_WRITE_ERROR"
    assert res.evidence_persisted is False and res.passed is False
    import os as _os
    assert _os.path.exists(cp + ".emergency.1.json")


def test_orchestration_rows_are_read_only_after_canonicalization(tmp_path):
    # cycle-4 finding 3 — the resolver sees immutable canonical copies
    rows, m = rows_and_manifest(1)
    seen = {}

    def spy_resolver(r):
        seen["writeable"] = any(a.flags.writeable for a in r)
        return qualified_outcome()
    result = run.orchestrate(_cfg(tmp_path, rows, m, resolve_fn=spy_resolver))
    assert result.disposition == "PASS" and seen["writeable"] is False


def test_window_violation_is_governed_refused(tmp_path):
    # cycle-4 finding 14
    rows, m = rows_and_manifest(1)
    result = run.orchestrate(_cfg(tmp_path, rows, m, windows=("validation",)))
    assert result.disposition == "REFUSED" and "WINDOW_ACCESS" in result.detail


def test_run_manifest_sha256_exposed(tmp_path):
    # cycle-4 finding 15
    rows, m = rows_and_manifest(1)
    result = run.orchestrate(_cfg(tmp_path, rows, m))
    assert result.run_manifest_sha256 == run._sha256_file(result.run_manifest_path)


def test_expected_corpus_instances_pinned():
    # cycle-4 finding 17 — the registered count is a pinned configuration value
    assert run.EXPECTED_CORPUS_INSTANCES == 3895


# ═══════════════════════════════ cycle-5 additions ═══════════════════════════════════════════════
def _passing_checkpoint(tmp_path):
    cp = ckpt(tmp_path)
    rows, m = rows_and_manifest(1)
    _run(rows, [qualified_outcome()], cp, m)
    return cp, m


def test_replay_rejects_malformed_certificate(tmp_path):
    # cycle-5 finding 7 — reversed interval + recomputed checksum still fails replay
    cp, m = _passing_checkpoint(tmp_path)

    def tamper(o):
        o["accepted"]["certificate"]["gamma_lower"] = 1.0
        o["accepted"]["certificate"]["gamma_upper"] = -1.0
        o["record_sha256"] = run._record_hash(o)
    _edit_line(cp, 0, tamper)
    state = run.read_checkpoint(cp)
    assert run.verify_numerical_evidence_record(state["records"][0]) == "CERTIFICATE_INTERVAL_REVERSED"
    assert run.aggregate_verdict(state, m) is False


def test_replay_runs_model_input_validation(tmp_path):
    # cycle-5 finding 8 — a structurally invalid rebuilt input fails replay even with consistent hashes
    cp, m = _passing_checkpoint(tmp_path)

    def tamper(o):
        # make t contain a zero (violates T_POSITIVE) and recompute BOTH hashes consistently
        o["input"]["t"]["exact_ratio"][0] = [0, 1]
        import numpy as _np
        comps = {k: _np.array([n / d for n, d in v["exact_ratio"]],
                              dtype=_np.float64).reshape(v["shape"])
                 for k, v in o["input"].items()}
        rebuilt = tuple(comps[k] for k in ("t", "A_ub", "b_ub", "A_eq", "b_eq", "upper"))
        o["input_content_hash"] = sc.rec_content_hash(rebuilt)
        o["record_sha256"] = run._record_hash(o)
    _edit_line(cp, 0, tamper)
    state = run.read_checkpoint(cp)
    assert str(run.verify_numerical_evidence_record(state["records"][0])).startswith(
        "REPLAY_MODEL_INPUT_DEFECT")


def test_replay_checks_disposition_relationships(tmp_path):
    # cycle-5 finding 9 — fallback_invoked flipped on a PRIMARY_QUALIFIED record fails replay
    cp, m = _passing_checkpoint(tmp_path)

    def tamper(o):
        o["fallback_invoked"] = True
        o["record_sha256"] = run._record_hash(o)
    _edit_line(cp, 0, tamper)
    state = run.read_checkpoint(cp)
    assert run.verify_numerical_evidence_record(
        state["records"][0]) == "REPLAY_FALLBACK_ON_PRIMARY_QUALIFICATION"


def test_sidecar_is_sequenced_and_never_overwrites(tmp_path):
    # cycle-5 finding 10
    cp = str(tmp_path / "x.jsonl")
    assert run._emergency_preserve(cp, {"reason": "first"}) is True
    assert run._emergency_preserve(cp, {"reason": "second"}) is True
    with open(cp + ".emergency.1.json", encoding="utf-8") as fh:
        s1 = json.load(fh)
    with open(cp + ".emergency.2.json", encoding="utf-8") as fh:
        s2 = json.load(fh)
    assert s1["reason"] == "first" and s2["reason"] == "second"
    assert s1["record_type"] == "MR002_STAGE3_EMERGENCY_SIDECAR" and s1["failure_sequence"] == 1


def test_stop_persistence_boundary_catches_any_exception(tmp_path, monkeypatch):
    # cycle-5 finding 11 — a ValueError (not OSError) in mark_failed still yields a sidecar
    cp = ckpt(tmp_path)
    rows, m = rows_and_manifest(2)

    def failing_mark(self, reason, row_id, extra=None):
        raise ValueError("closed file")
    monkeypatch.setattr(run.CheckpointSink, "mark_failed", failing_mark)
    res = _run([rows[0], (1, rec(9))], [qualified_outcome()], cp, m)   # hash mismatch → stop
    assert res.stopped
    import os as _os
    assert _os.path.exists(cp + ".emergency.1.json")


def test_atomic_write_is_byte_exact(tmp_path):
    # cycle-5 finding 12
    pth = str(tmp_path / "doc.json")
    expected = run._atomic_write_json(pth, {"b": 2, "a": 1})
    assert run._sha256_file(pth) == expected


def test_authorization_date_must_be_iso(tmp_path):
    # cycle-5 finding 15
    art = {**GOOD_AUTH, "authorized_date": "July 18, 2026"}
    pth = _write(tmp_path, "auth_baddate.json", art)
    with pytest.raises(run.Stage3RunRefused):
        run.load_authorization(pth, run._sha256_file(pth))


def _good_binding():
    b = {"record_type": run.BINDING_RECORD_TYPE, "version": "1.0", "record_status": "IMMUTABLE",
         "countersigned_by": run.AUTHORIZED_COUNTERSIGNER, "countersigned_date": "2026-07-18",
         "repository": "jayw04/AI-TRADING-APP",
         "decision": "EXECUTION_PACKAGE_COUNTERSIGNED", "execution_authorized": True,
         "scope": "MR002_STAGE3_CLEAN_SUCCESSOR_ONLY",
         **{k: "a" * 64 for k in run.BINDING_REQUIRED_FIELDS}}
    b["bound_commit"] = "c" * 40
    b["bound_tree"] = "t" * 40
    # git object names are hex — use valid hex
    b["bound_commit"] = "c1" * 20
    b["bound_tree"] = "d2" * 20
    b["image_digest"] = "sha256:" + "e" * 64
    b["oci_config_digest"] = "sha256:" + "f" * 64
    return b


def test_execution_binding_and_attestation_schemas(tmp_path):
    # cycle-5 findings 2, 3, 14 + cycle-6 findings 4, 5, 14
    binding = _good_binding()
    pth = _write(tmp_path, "binding.json", binding)
    assert run.load_execution_binding(pth, run._sha256_file(pth))["record_type"] == run.BINDING_RECORD_TYPE
    # malformed/short hash refused (cycle-6 finding 14)
    p2 = _write(tmp_path, "binding_short.json", {**binding, "realism_pass_sha256": "abc123"})
    with pytest.raises(run.Stage3RunRefused):
        run.load_execution_binding(p2, run._sha256_file(p2))
    # missing field refused
    incomplete = {**binding}
    del incomplete["realism_pass_sha256"]
    p3 = _write(tmp_path, "binding_missing.json", incomplete)
    with pytest.raises(run.Stage3RunRefused):
        run.load_execution_binding(p3, run._sha256_file(p3))
    # wrong status / countersigner / invalid calendar date refused (cycle-6 findings 4, 15)
    for f, bad in [("record_status", "DRAFT"), ("countersigned_by", "someone"),
                   ("countersigned_date", "2026-02-31")]:
        pb = _write(tmp_path, f"binding_{f}.json", {**binding, f: bad})
        with pytest.raises(run.Stage3RunRefused):
            run.load_execution_binding(pb, run._sha256_file(pb))

    att = {"record_type": run.ATTESTATION_RECORD_TYPE, "version": "1.0",
           "record_status": "IMMUTABLE",
           **{k: "a" * 64 for k in run.ATTESTATION_REQUIRED_FIELDS}}
    att.update({"bound_commit": "c1" * 20, "bound_tree": "d2" * 20,
                "image_digest": "sha256:" + "e" * 64, "oci_config_digest": "sha256:" + "f" * 64,
                "launcher_identity": "launcher", "exact_command": "cmd",
                "output_mount_identity": "mount", "run_nonce": "n1", "signature": "sig",
                "signature_algorithm": "ed25519", "signing_key_id": "key-1",
                "verification_tool": "verify-tool"})
    import hashlib as _h
    unsigned = {k: v for k, v in att.items()
                if k not in ("signature", "canonical_signed_payload_sha256")}
    att["canonical_signed_payload_sha256"] = _h.sha256(
        json.dumps(unsigned, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    p4 = _write(tmp_path, "att.json", att)
    assert run.load_launch_attestation(p4, run._sha256_file(p4))["signature"] == "sig"
    # cycle-7 finding 4: payload-hash mismatch refused
    p4b = _write(tmp_path, "att_payload.json",
                 {**att, "canonical_signed_payload_sha256": "9" * 64})
    with pytest.raises(run.Stage3RunRefused):
        run.load_launch_attestation(p4b, run._sha256_file(p4b))
    # a missing signature-envelope member refused (cycle-6 finding 5)
    p5 = _write(tmp_path, "att_bad.json", {**att, "signing_key_id": ""})
    with pytest.raises(run.Stage3RunRefused):
        run.load_launch_attestation(p5, run._sha256_file(p5))


def test_cross_validate_binding_catches_artifact_mismatch(tmp_path):
    # cycle-6 findings 1, 3
    binding = _good_binding()
    kw = dict(authorization_sha=binding["authorization_sha256"],
              pins_sha=binding["expected_pins_sha256"],
              manifest_sha=binding["implementation_manifest_sha256"],
              attestation_sha=binding["launch_attestation_sha256"],
              package_sha=binding["execution_package_sha256"],
              auth={k: binding[k] for k in ("bound_commit", "bound_tree",
                                            "image_digest", "oci_config_digest")},
              realism_sha=binding["realism_pass_sha256"],
              final_report_sha=binding["final_test_report_sha256"])
    run.cross_validate_binding(binding, **kw)          # consistent → no raise
    with pytest.raises(run.Stage3RunRefused):
        run.cross_validate_binding(binding, **{**kw, "realism_sha": "0" * 64})


# ═══════════════════════════════ cycle-7 additions ═══════════════════════════════════════════════
def test_binding_rejects_unexpected_keys_and_missing_decision(tmp_path):
    # cycle-7 findings 6, 8
    b = _good_binding()
    p1 = _write(tmp_path, "b_extra.json", {**b, "surprise": 1})
    with pytest.raises(run.Stage3RunRefused):
        run.load_execution_binding(p1, run._sha256_file(p1))
    p2 = _write(tmp_path, "b_dec.json", {**b, "decision": "PENDING"})
    with pytest.raises(run.Stage3RunRefused):
        run.load_execution_binding(p2, run._sha256_file(p2))


def test_realism_semantic_qualification(tmp_path):
    # cycle-7 finding 2 — FAIL / unpersisted / preflight-failed all refused
    good = _good_realism()
    pg = _write(tmp_path, "r_ok.json", good)
    assert run.load_realism_pass(pg, run._sha256_file(pg))["verdict"] == "PASS"
    for f, bad in [("verdict", "FAIL"), ("preflight_passed", False), ("cases_pass", False),
                   ("evidence_persisted", False)]:
        pb = _write(tmp_path, f"r_{f}.json", {**good, f: bad})
        with pytest.raises(run.Stage3RunRefused):
            run.load_realism_pass(pb, run._sha256_file(pb))


def test_final_report_semantic_qualification(tmp_path):
    # cycle-7 finding 2 — nonzero exit / skips / dirty tree / non-admissible refused
    good = _good_report()
    pg = _write(tmp_path, "t_ok.json", good)
    assert run.load_final_test_report(pg, run._sha256_file(pg))["exit_code"] == 0
    for f, bad in [("exit_code", 1), ("collected_skipped", 1), ("working_tree_dirty", True),
                   ("admissible_as_final", False)]:
        pb = _write(tmp_path, f"t_{f}.json", {**good, f: bad})
        with pytest.raises(run.Stage3RunRefused):
            run.load_final_test_report(pb, run._sha256_file(pb))


def test_verification_receipt_required_semantics(tmp_path):
    # cycle-7 finding 3
    good = {"record_type": run.RECEIPT_RECORD_TYPE, "version": "1.0",
            "record_status": "IMMUTABLE", "verification_exit_status": 0,
            "verification_tool_sha256": "a" * 64, "signing_key_id": "key-1",
            "signature_algorithm": "ed25519", "canonical_signed_payload_sha256": "d" * 64,
            "attestation_sha256": "b" * 64, "run_nonce": "n1", "verified_at": "2026-07-18"}
    pg = _write(tmp_path, "rc_ok.json", good)
    assert run.load_verification_receipt(pg, run._sha256_file(pg), "b" * 64)
    pb = _write(tmp_path, "rc_bad.json", {**good, "verification_exit_status": 1})
    with pytest.raises(run.Stage3RunRefused):
        run.load_verification_receipt(pb, run._sha256_file(pb), "b" * 64)
    with pytest.raises(run.Stage3RunRefused):        # bound to a DIFFERENT attestation
        run.load_verification_receipt(pg, run._sha256_file(pg), "c" * 64)


def test_corpus_provenance_reaches_run_manifest(tmp_path):
    # cycle-7 findings 1, 10 — the ACTUAL provenance is in the persisted manifest, and a missing
    # provenance is refused BEFORE any manifest exists
    rows, m = rows_and_manifest(1)
    result = run.orchestrate(_cfg(tmp_path, rows, m))
    with open(result.run_manifest_path, encoding="utf-8") as fh:
        doc = json.load(fh)
    assert doc["corpus_source_provenance"] == PROV
    rows2, m2 = rows_and_manifest(2)
    d2 = tmp_path / "empty2"
    d2.mkdir()
    r2 = run.orchestrate(_cfg(d2, rows2, m2, corpus_source=_source(rows2, m2, prov=None)))
    assert r2.disposition == "REFUSED" and "CORPUS_PROVENANCE_INCOMPLETE" in r2.detail
    assert not (d2 / "MR002_Stage3_CleanRun_Manifest.json").exists()


# ═══════════════════════ cycle-8 fixtures + one test per review issue ════════════════════════════
def _case_fields(group):
    if group == "primary_qualified":
        return {"disposition": "PRIMARY_QUALIFIED", "primary_solver": "QUADPROG_SQRT",
                "primary_enum": "QUALIFIED", "fallback_invoked": False,
                "accepted_by": "QUADPROG_SQRT", "stop": False}
    if group == "fallback_qualified":
        return {"disposition": "FALLBACK_QUALIFIED",
                "primary_enum": "NUMERICAL_STATUS_NONQUALIFICATION",
                "fallback_solver": "PIQP_P2", "fallback_enum": "QUALIFIED",
                "fallback_invoked": True, "accepted_by": "PIQP_P2", "stop": False}
    return {"expected_primary_enum": "CERTIFICATE_NONQUALIFICATION",
            "primary_enum": "CERTIFICATE_NONQUALIFICATION"}


def _good_realism():
    def case(group, i):
        return {"case": f"{group}/p{i}", "pass": True, "rec_sha256": "a" * 64,
                "outcome_sha256": "b" * 64, **_case_fields(group)}
    return {"record_type": run.REALISM_RECORD_TYPE, "verdict": "PASS", "preflight_passed": True,
            "cases_pass": True, "evidence_persisted": True,
            "binds_real": {"primary": "QUADPROG_SQRT", "fallback": "PIQP_P2",
                           "certifier": "canonical_qualify (registered)"},
            "cases": [case(g, i) for g in run.REALISM_REQUIRED_CASE_GROUPS for i in range(3)]}


def _good_report(binding=None):
    ids = [f"{m}::test_{i}" for m in run.FINAL_REPORT_REQUIRED_MODULES for i in range(30)]
    ids.append(run.PRODUCTION_BINDING_TEST_ID)
    doc = {"record_type": run.TEST_REPORT_RECORD_TYPE, "exit_code": 0, "collected_skipped": 0,
           "working_tree_dirty": False, "admissible_as_final": True,
           "collected_test_ids": ids, "collected_passed": len(ids),
           "test_results": [{"test_id": i, "outcome": "passed"} for i in ids],
           "production_binding_outcome": "passed"}
    if binding is not None:
        doc.update({"bound_commit": binding["bound_commit"], "bound_tree": binding["bound_tree"],
                    "image_digest": binding["image_digest"],
                    "oci_config_digest": binding["oci_config_digest"],
                    "source_manifest_sha256": binding["implementation_manifest_sha256"],
                    "expected_pins_sha256": binding["expected_pins_sha256"],
                    "execution_package_sha256": binding["execution_package_sha256"]})
    return doc


def test_cycle8_issue1_missing_evidence_persisted_refused(tmp_path):
    # issue 1: the default-True defect — a MISSING evidence_persisted field must refuse
    art = _good_realism()
    del art["evidence_persisted"]
    pth = _write(tmp_path, "r_noev.json", art)
    with pytest.raises(run.Stage3RunRefused, match="REALISM_EVIDENCE_NOT_PERSISTED"):
        run.load_realism_pass(pth, run._sha256_file(pth))


def test_cycle8_issue2_cases_derived_not_trusted(tmp_path):
    # issue 2: an empty cases array with cases_pass true must NOT qualify; each defect class refuses
    base = _good_realism()
    for name, mut in [
        ("empty", lambda a: a.update(cases=[])),
        ("group_missing", lambda a: a.update(
            cases=[c for c in a["cases"] if not c["case"].startswith("certifier_classification/")])),
        ("case_failed", lambda a: a["cases"][0].update({"pass": False})),
        ("dup_names", lambda a: a["cases"].__setitem__(1, dict(a["cases"][0]))),
        ("bad_hash", lambda a: a["cases"][0].update({"rec_sha256": "zz"})),
        ("no_binds_real", lambda a: a.pop("binds_real")),
    ]:
        art = json.loads(json.dumps(_good_realism()))
        mut(art)
        pth = _write(tmp_path, f"r2_{name}.json", art)
        with pytest.raises(run.Stage3RunRefused):
            run.load_realism_pass(pth, run._sha256_file(pth))
    pg = _write(tmp_path, "r2_ok.json", base)
    assert run.load_realism_pass(pg, run._sha256_file(pg))["verdict"] == "PASS"


def test_cycle8_issue3_production_binding_must_have_run(tmp_path):
    # issue 3: zero skips alone cannot qualify — the collected-test manifest must prove the
    # production-binding test was collected AND passed
    good = _good_report()
    for name, mut in [
        ("no_ids", lambda a: a.pop("collected_test_ids")),
        ("binding_absent", lambda a: a.update(
            collected_test_ids=[i for i in a["collected_test_ids"]
                                if i != run.PRODUCTION_BINDING_TEST_ID])),
        ("binding_not_passed", lambda a: a.update(production_binding_outcome="skipped")),
        ("module_missing", lambda a: a.update(
            collected_test_ids=[i for i in a["collected_test_ids"]
                                if not i.startswith("tests/research/test_mr002_stage3_preflight.py")]
            + [run.PRODUCTION_BINDING_TEST_ID] * 40)),
    ]:
        art = json.loads(json.dumps(good))
        mut(art)
        if name == "module_missing":
            art["collected_test_ids"] = list(dict.fromkeys(art["collected_test_ids"]))
            art["collected_test_ids"] += [f"tests/research/test_mr002_stage3_cascade_dispA.py::x{i}"
                                          for i in range(120)]
        pth = _write(tmp_path, f"t3_{name}.json", art)
        with pytest.raises(run.Stage3RunRefused):
            run.load_final_test_report(pth, run._sha256_file(pth))
    pg = _write(tmp_path, "t3_ok.json", good)
    assert run.load_final_test_report(pg, run._sha256_file(pg))["production_binding_outcome"] == "passed"


def test_cycle8_issue4_receipt_must_match_attestation_key_and_payload(tmp_path):
    # issue 4: a receipt claiming verification under a DIFFERENT key/algorithm/payload is refused
    att = {"signing_key_id": "key-1", "signature_algorithm": "ed25519",
           "canonical_signed_payload_sha256": "d" * 64, "run_nonce": "n1",
           "verification_tool_sha256": "a" * 64}
    good = {"record_type": run.RECEIPT_RECORD_TYPE, "version": "1.0",
            "record_status": "IMMUTABLE", "verification_exit_status": 0,
            "verification_tool_sha256": "a" * 64, "signing_key_id": "key-1",
            "signature_algorithm": "ed25519", "canonical_signed_payload_sha256": "d" * 64,
            "attestation_sha256": "b" * 64, "run_nonce": "n1", "verified_at": "2026-07-18"}
    pg = _write(tmp_path, "rc4_ok.json", good)
    assert run.load_verification_receipt(pg, run._sha256_file(pg), "b" * 64, attestation=att)
    for f, bad in [("signing_key_id", "other-key"), ("signature_algorithm", "rsa"),
                   ("canonical_signed_payload_sha256", "e" * 64)]:
        pb = _write(tmp_path, f"rc4_{f}.json", {**good, f: bad})
        with pytest.raises(run.Stage3RunRefused, match="RECEIPT_ATTESTATION_FIELD_MISMATCH"):
            run.load_verification_receipt(pb, run._sha256_file(pb), "b" * 64, attestation=att)
    # invalid tool hash + unexpected key also refuse (closed schema)
    pb2 = _write(tmp_path, "rc4_tool.json", {**good, "verification_tool_sha256": "short"})
    with pytest.raises(run.Stage3RunRefused, match="RECEIPT_TOOL_HASH_INVALID"):
        run.load_verification_receipt(pb2, run._sha256_file(pb2), "b" * 64, attestation=att)
    pb3 = _write(tmp_path, "rc4_extra.json", {**good, "surprise": 1})
    with pytest.raises(run.Stage3RunRefused, match="RECEIPT_UNEXPECTED_KEYS"):
        run.load_verification_receipt(pb3, run._sha256_file(pb3), "b" * 64, attestation=att)


def test_cycle8_issue5_entry_retains_attestation_for_receipt():
    # issue 5: the entry signature passes the PARSED attestation into the receipt loader
    import inspect
    src_entry = inspect.getsource(run.run_clean_successor)
    assert "attestation=attestation" in src_entry


def test_cycle8_issue6_invalid_calendar_authorization_date_refused(tmp_path):
    # issue 6: 2026-02-31 passes the regex shape but is not a real date — must refuse
    for bad in ("2026-02-31", "2026-99-99"):
        art = {**GOOD_AUTH, "authorized_date": bad}
        pth = _write(tmp_path, f"a6_{bad}.json", art)
        with pytest.raises(run.Stage3RunRefused, match="AUTHORIZATION_DATE_INVALID"):
            run.load_authorization(pth, run._sha256_file(pth))


def test_cycle8_issue7_attestation_closed_schema(tmp_path):
    # issue 7: unexpected keys / missing version / non-immutable status refused
    att = {"record_type": run.ATTESTATION_RECORD_TYPE, "version": "1.0",
           "record_status": "IMMUTABLE",
           **{k: "a" * 64 for k in run.ATTESTATION_REQUIRED_FIELDS}}
    att.update({"bound_commit": "c1" * 20, "bound_tree": "d2" * 20,
                "image_digest": "sha256:" + "e" * 64, "oci_config_digest": "sha256:" + "f" * 64,
                "launcher_identity": "launcher", "exact_command": "cmd",
                "output_mount_identity": "mount", "run_nonce": "n1", "signature": "sig",
                "signature_algorithm": "ed25519", "signing_key_id": "key-1",
                "verification_tool": "verify-tool"})
    import hashlib as _h
    unsigned = {k: v for k, v in att.items()
                if k not in ("signature", "canonical_signed_payload_sha256")}
    att["canonical_signed_payload_sha256"] = _h.sha256(
        json.dumps(unsigned, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    pg = _write(tmp_path, "att7_ok.json", att)
    assert run.load_launch_attestation(pg, run._sha256_file(pg))
    for name, mut in [("extra", {"surprise": 1}), ("version", {"version": "2.0"}),
                      ("status", {"record_status": "DRAFT"})]:
        bad = {**att, **mut}
        if name == "extra":
            unsigned = {k: v for k, v in bad.items()
                        if k not in ("signature", "canonical_signed_payload_sha256")}
            bad["canonical_signed_payload_sha256"] = _h.sha256(
                json.dumps(unsigned, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        pb = _write(tmp_path, f"att7_{name}.json", bad)
        with pytest.raises(run.Stage3RunRefused):
            run.load_launch_attestation(pb, run._sha256_file(pb))


# ═══════════════════ cycle-9 fixtures + one test per review blocker ══════════════════════════════
def test_cycle9_blocker1_binds_real_identities_enforced(tmp_path):
    # blocker 1: FAKE solver identities in binds_real must refuse; truthiness is not enough
    art = _good_realism()
    art["binds_real"] = {"primary": "FAKE_SOLVER", "fallback": "FAKE_FALLBACK",
                         "certifier": "canonical_qualify"}
    pth = _write(tmp_path, "b1_fake.json", art)
    with pytest.raises(run.Stage3RunRefused, match="REALISM_BINDS_REAL_INVALID"):
        run.load_realism_pass(pth, run._sha256_file(pth))
    art2 = _good_realism()
    art2["binds_real"]["certifier"] = "my_own_certifier"
    p2 = _write(tmp_path, "b1_cert.json", art2)
    with pytest.raises(run.Stage3RunRefused, match="REALISM_BINDS_REAL_INVALID"):
        run.load_realism_pass(p2, run._sha256_file(p2))


def test_cycle9_blocker2_case_semantics_derived_per_group(tmp_path):
    # blocker 2: a case named primary_qualified/x with pass true but an unrelated disposition refuses
    art = json.loads(json.dumps(_good_realism()))
    art["cases"][0]["disposition"] = "FALLBACK_QUALIFIED"      # wrong for its group
    pth = _write(tmp_path, "b2_wrongdisp.json", art)
    with pytest.raises(run.Stage3RunRefused, match="REALISM_CASE_SEMANTICS"):
        run.load_realism_pass(pth, run._sha256_file(pth))
    art2 = json.loads(json.dumps(_good_realism()))
    fb = next(c for c in art2["cases"] if c["case"].startswith("fallback_qualified/"))
    fb["fallback_solver"] = "CLARABEL"                          # wrong fallback identity
    p2 = _write(tmp_path, "b2_wrongfb.json", art2)
    with pytest.raises(run.Stage3RunRefused, match="REALISM_CASE_SEMANTICS"):
        run.load_realism_pass(p2, run._sha256_file(p2))
    pg = _write(tmp_path, "b2_ok.json", _good_realism())
    assert run.load_realism_pass(pg, run._sha256_file(pg))["verdict"] == "PASS"


def test_cycle9_blocker3_per_test_results_required_and_derived(tmp_path):
    # blocker 3: names alone cannot qualify — a per-test result map is required and counts derived
    art = _good_report()
    del art["test_results"]
    pth = _write(tmp_path, "b3_nores.json", art)
    with pytest.raises(run.Stage3RunRefused, match="TEST_REPORT_RESULTS_MISSING"):
        run.load_final_test_report(pth, run._sha256_file(pth))
    art2 = _good_report()
    art2["test_results"][5]["outcome"] = "failed"
    p2 = _write(tmp_path, "b3_fail.json", art2)
    with pytest.raises(run.Stage3RunRefused, match="TEST_REPORT_NOT_ALL_PASSED"):
        run.load_final_test_report(p2, run._sha256_file(p2))
    art3 = _good_report()
    art3["test_results"] = art3["test_results"][:-1]            # production-binding record missing
    art3["collected_passed"] = len(art3["test_results"])
    p3 = _write(tmp_path, "b3_missing.json", art3)
    with pytest.raises(run.Stage3RunRefused, match="RESULTS_IDS_MISMATCH"):
        run.load_final_test_report(p3, run._sha256_file(p3))
    art4 = _good_report()
    art4["collected_passed"] = 9999                             # trusted scalar disagrees → refuse
    p4 = _write(tmp_path, "b3_count.json", art4)
    with pytest.raises(run.Stage3RunRefused, match="PASSED_COUNT_DISAGREES"):
        run.load_final_test_report(p4, run._sha256_file(p4))


def test_cycle9_blocker4_report_identity_must_match_phase_b(tmp_path):
    # blocker 4: the report must STATE commit/tree/image/OCI/manifest/pins/package and match Phase B
    binding = _good_binding()
    good = _good_report(binding)
    pg = _write(tmp_path, "b4_ok.json", good)
    assert run.load_final_test_report(pg, run._sha256_file(pg), binding=binding)
    bad = dict(good)
    bad["image_digest"] = "sha256:" + "0" * 64
    pb = _write(tmp_path, "b4_img.json", bad)
    with pytest.raises(run.Stage3RunRefused, match="TEST_REPORT_IDENTITY_MISMATCH:image_digest"):
        run.load_final_test_report(pb, run._sha256_file(pb), binding=binding)
    bad2 = dict(good)
    del bad2["bound_commit"]                                    # identity absent → mismatch → refuse
    p2 = _write(tmp_path, "b4_nocommit.json", bad2)
    with pytest.raises(run.Stage3RunRefused, match="TEST_REPORT_IDENTITY_MISMATCH:bound_commit"):
        run.load_final_test_report(p2, run._sha256_file(p2), binding=binding)


def test_cycle9_blocker5_receipt_nonce_mandatory_and_matched(tmp_path):
    # blocker 5: run_nonce mandatory + must equal the attestation nonce; verified_at mandatory
    att = {"signing_key_id": "key-1", "signature_algorithm": "ed25519",
           "canonical_signed_payload_sha256": "d" * 64, "run_nonce": "n1",
           "verification_tool_sha256": "a" * 64}
    good = {"record_type": run.RECEIPT_RECORD_TYPE, "version": "1.0",
            "record_status": "IMMUTABLE", "verification_exit_status": 0,
            "verification_tool_sha256": "a" * 64, "signing_key_id": "key-1",
            "signature_algorithm": "ed25519", "canonical_signed_payload_sha256": "d" * 64,
            "attestation_sha256": "b" * 64, "run_nonce": "n1", "verified_at": "2026-07-18"}
    pg = _write(tmp_path, "b5_ok.json", good)
    assert run.load_verification_receipt(pg, run._sha256_file(pg), "b" * 64, attestation=att)
    nn = {k: v for k, v in good.items() if k != "run_nonce"}
    p1 = _write(tmp_path, "b5_nononce.json", nn)
    with pytest.raises(run.Stage3RunRefused, match="RECEIPT_MISSING:run_nonce"):
        run.load_verification_receipt(p1, run._sha256_file(p1), "b" * 64, attestation=att)
    p2 = _write(tmp_path, "b5_wrongnonce.json", {**good, "run_nonce": "OTHER"})
    with pytest.raises(run.Stage3RunRefused, match="RECEIPT_ATTESTATION_FIELD_MISMATCH:run_nonce"):
        run.load_verification_receipt(p2, run._sha256_file(p2), "b" * 64, attestation=att)


def test_cycle9_blocker6_receipt_version_and_status_enforced(tmp_path):
    # blocker 6: missing/unsupported version and non-immutable status refuse
    att = {"signing_key_id": "key-1", "signature_algorithm": "ed25519",
           "canonical_signed_payload_sha256": "d" * 64, "run_nonce": "n1",
           "verification_tool_sha256": "a" * 64}
    base = {"record_type": run.RECEIPT_RECORD_TYPE, "version": "1.0",
            "record_status": "IMMUTABLE", "verification_exit_status": 0,
            "verification_tool_sha256": "a" * 64, "signing_key_id": "key-1",
            "signature_algorithm": "ed25519", "canonical_signed_payload_sha256": "d" * 64,
            "attestation_sha256": "b" * 64, "run_nonce": "n1", "verified_at": "2026-07-18"}
    for f, bad, msg in [("version", None, "RECEIPT_UNSUPPORTED_VERSION"),
                        ("version", "2.0", "RECEIPT_UNSUPPORTED_VERSION"),
                        ("record_status", "DRAFT", "RECEIPT_NOT_IMMUTABLE")]:
        d = {k: v for k, v in base.items() if not (k == f and bad is None)}
        if bad is not None:
            d[f] = bad
        pb = _write(tmp_path, f"b6_{f}_{bad}.json", d)
        with pytest.raises(run.Stage3RunRefused, match=msg):
            run.load_verification_receipt(pb, run._sha256_file(pb), "b" * 64, attestation=att)


def test_cycle9_blocker7_verification_tool_bound_to_attestation(tmp_path):
    # blocker 7: the receipt's tool hash must equal the attestation's verification_tool_sha256
    att = {"signing_key_id": "key-1", "signature_algorithm": "ed25519",
           "canonical_signed_payload_sha256": "d" * 64, "run_nonce": "n1",
           "verification_tool_sha256": "a" * 64}
    good = {"record_type": run.RECEIPT_RECORD_TYPE, "version": "1.0",
            "record_status": "IMMUTABLE", "verification_exit_status": 0,
            "verification_tool_sha256": "c" * 64, "signing_key_id": "key-1",
            "signature_algorithm": "ed25519", "canonical_signed_payload_sha256": "d" * 64,
            "attestation_sha256": "b" * 64, "run_nonce": "n1", "verified_at": "2026-07-18"}
    pb = _write(tmp_path, "b7_tool.json", good)
    with pytest.raises(run.Stage3RunRefused,
                       match="RECEIPT_ATTESTATION_FIELD_MISMATCH:verification_tool_sha256"):
        run.load_verification_receipt(pb, run._sha256_file(pb), "b" * 64, attestation=att)
    # attestation itself now REQUIRES a 64-hex verification_tool_sha256
    assert "verification_tool_sha256" in run.ATTESTATION_REQUIRED_FIELDS
