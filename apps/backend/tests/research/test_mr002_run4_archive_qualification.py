"""MR-002 Run-4 archive-qualification tool tests (laptop-side review, host phase deferred).

Static tests PIN the tool's composition: exact import set, forbidden capabilities absent (no
population, cascade resolution, checkpoint writing, resume, validation/OOS, or performance code),
and no write-mode file opens. Functional tests exercise the full flow against a SYNTHETIC
read-only archive with monkeypatched pins — the real archived Run-4 evidence is never touched
before the host phase (it lives on the stopped launch host).
"""

from __future__ import annotations

import ast
import inspect
import json
import os
import stat
import subprocess as _subprocess
import sys as _sys
from pathlib import Path

import numpy as np
import pytest

from app.research.mr002 import stage3_cascade as sc
from scripts import mr002_run4_archive_qualification as tool
from scripts import mr002_stage3_population_runner as run

TOOL_PATH = inspect.getsourcefile(tool)


# ═══════════════════════════ static composition (pinned by test) ════════════════════════════════
def _tool_ast():
    with open(TOOL_PATH, encoding="utf-8") as fh:
        return ast.parse(fh.read())


def test_composition_import_set_exact():
    tree = _tool_ast()
    plain, from_imports = set(), set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            plain.update(a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom):
            from_imports.update(f"{node.module}:{a.name}" for a in node.names)
    assert plain == {"argparse", "hashlib", "json", "os", "subprocess", "sys", "numpy"}
    assert from_imports == {
        "__future__:annotations",
        "app.research.mr002.stage3_cascade:EVIDENCE_SCHEMA_VERSION",
        "app.research.mr002.stage3_cascade:_exact_hex_list",
        "app.research.mr002.stage3_cascade:rec_content_hash",
        "scripts.mr002_stage3_population_runner:_decode_exact_hex",
        "scripts.mr002_stage3_population_runner:production_corpus_source",
        "scripts.mr002_stage3_population_runner:read_checkpoint",
        "scripts.mr002_stage3_population_runner:verify_numerical_evidence_record",
    }


def test_composition_forbidden_capabilities_absent():
    # identifiers that would mean population, cascade resolution, checkpoint writing, resume,
    # validation/OOS access, or performance computation — none may appear anywhere in the tool
    forbidden = {"run_population", "orchestrate", "run_clean_successor", "CheckpointSink",
                 "write_record", "mark_complete", "mark_failed", "resolve", "resolve_instance",
                 "normalize", "certify", "aggregate_verdict", "aggregate_verdict_defect",
                 "canonicalize", "FrozenDataset", "run_config", "resume", "is_resumable",
                 "validation", "oos", "sharpe", "returns", "pnl"}
    seen = set()
    for node in ast.walk(_tool_ast()):
        if isinstance(node, ast.Name):
            seen.add(node.id)
        elif isinstance(node, ast.Attribute):
            seen.add(node.attr)
    assert not (seen & forbidden), f"forbidden identifiers present: {sorted(seen & forbidden)}"


def test_composition_no_write_mode_opens():
    for node in ast.walk(_tool_ast()):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) \
                and node.func.id == "open":
            modes = [a.value for a in node.args[1:2] if isinstance(a, ast.Constant)]
            modes += [kw.value.value for kw in node.keywords
                      if kw.arg == "mode" and isinstance(kw.value, ast.Constant)]
            for m in modes:
                assert not any(c in str(m) for c in "wax+"), f"write-mode open: {m}"


def test_default_corpus_source_is_the_committed_one():
    sig = inspect.signature(tool.main)
    assert sig.parameters["corpus_source"].default is run.production_corpus_source


def test_pins_are_the_governing_identities():
    assert tool.PINNED_IMPLEMENTATION_COMMIT == "ecaa262480fb2b81fb0ba7d11b97721b617722bf"
    assert tool.PINNED_CHECKPOINT_SHA256.startswith("b9b0a948")
    assert tool.PINNED_MANIFEST_SHA256.startswith("1132d3b8")
    assert tool.PINNED_CORPUS_HASH.startswith("1d231930")
    assert tool.REQUIRED_SCHEMA_VERSION == "2.0" == sc.EVIDENCE_SCHEMA_VERSION
    assert (tool.EXPECTED_FORMERLY_FAILING, tool.EXPECTED_FORMERLY_CLEAN) == (3639, 256)


# ═══════════════════════════ synthetic archive fixture ══════════════════════════════════════════
def _rec(i, b_ub=None, a_ub=None):
    return (np.array([0.008 + i * 1e-4, 0.008]),
            np.array([[1.0, 1.0], [1.0, 0.0]]) if a_ub is None else a_ub,
            np.array([0.01, 0.01]) if b_ub is None else b_ub,
            np.zeros((0, 2)), np.zeros(0), np.array([0.02, 0.02]))


def _build_synthetic(tmp_path, monkeypatch):
    """3 rows: row0 formerly-failing (-0.0 in b_ub), row1 clean, row2 formerly-failing
    (-0.0 in A_ub AND b_ub) — two distinct placement patterns."""
    recs = [sc.canonicalize(_rec(0, b_ub=np.array([0.0, -0.0]))),
            sc.canonicalize(_rec(1)),
            sc.canonicalize(_rec(2, b_ub=np.array([-0.0, 0.01]),
                                 a_ub=np.array([[1.0, -0.0], [1.0, 0.0]])))]
    rows = [(i, recs[i]) for i in range(3)]
    archive = tmp_path / "archive"
    archive.mkdir()
    cp = archive / tool.CHECKPOINT_NAME
    lines = [json.dumps({"kind": "record", "row_id": i, "class": "qualified",
                         "input_content_hash": sc.rec_content_hash(recs[i])},
                        separators=(",", ":")) for i in range(3)]
    lines.append(json.dumps({"kind": "terminal", "status": "COMPLETE", "n_records": 3}))
    cp.write_text("\n".join(lines) + "\n", encoding="utf-8")
    mf = archive / tool.MANIFEST_NAME
    mf.write_text(json.dumps({"record_type": "SYNTHETIC_TEST_MANIFEST"}), encoding="utf-8")
    for p in (cp, mf):
        os.chmod(p, stat.S_IRUSR | stat.S_IRGRP | stat.S_IROTH)

    corpus_hash = run.derive_corpus_hash(recs)
    monkeypatch.setattr(tool, "EXPECTED_N_RECORDS", 3)
    monkeypatch.setattr(tool, "PINNED_CHECKPOINT_SHA256", tool._sha256_file(str(cp)))
    monkeypatch.setattr(tool, "PINNED_MANIFEST_SHA256", tool._sha256_file(str(mf)))
    monkeypatch.setattr(tool, "PINNED_CORPUS_HASH", corpus_hash)
    monkeypatch.setattr(tool, "EXPECTED_FORMERLY_FAILING", 2)
    monkeypatch.setattr(tool, "EXPECTED_FORMERLY_CLEAN", 1)
    monkeypatch.setattr(tool, "_head_commit",
                        lambda _w: tool.PINNED_IMPLEMENTATION_COMMIT)
    real_access = os.access
    monkeypatch.setattr(os, "access", lambda p, mode: (
        False if (mode == os.W_OK and str(p) == str(archive)) else real_access(p, mode)))

    def corpus_source():
        return rows, corpus_hash, None, None
    return archive, corpus_source, recs


def _run_tool(archive, corpus_source, capsys, extra=()):
    rc = tool.main(["--archive", str(archive), "--work-root", ".", *extra],
                   corpus_source=corpus_source)
    return rc, json.loads(capsys.readouterr().out)


# ═══════════════════════════ functional: full PASS flow ═════════════════════════════════════════
def test_full_pass_flow_with_patterns_and_bit_equality(tmp_path, monkeypatch, capsys):
    archive, source, recs = _build_synthetic(tmp_path, monkeypatch)
    rc, rep = _run_tool(archive, source, capsys)
    assert rc == 0 and rep["disposition"] == "PASS"
    assert rep["population"] == {"n_records": 3, "formerly_failing": 2, "formerly_clean": 1,
                                 "expected_failing": 2, "expected_clean": 1,
                                 "counts_match_run4_forensics": True}
    assert rep["negative_zero_patterns"] == [
        {"components": ["A_ub", "b_ub"], "representative_row_id": 2},
        {"components": ["b_ub"], "representative_row_id": 0}]
    assert rep["selected_row_ids"] == [0, 1, 2]     # both patterns + the lowest clean row
    for r in rep["records"]:
        assert r["pass"] is True
        assert r["schema2_replay_defect"] is None
        assert r["archived_content_hash_equal"] is True and r["content_hash_equal"] is True
        assert all(v is True for v in r["uint64_bit_equality"].values())
    r0 = rep["records"][0]
    assert r0["negative_zero"]["b_ub"] == {"count": 1, "locations": [1],
                                           "locations_truncated": False}
    r2 = rep["records"][2]
    assert r2["negative_zero"]["A_ub"]["locations"] == [1]
    assert r2["negative_zero"]["b_ub"]["locations"] == [0]


def test_explicit_rows_are_included(tmp_path, monkeypatch, capsys):
    archive, source, _ = _build_synthetic(tmp_path, monkeypatch)
    rc, rep = _run_tool(archive, source, capsys, extra=("--rows", "1,2"))
    assert rc == 0 and rep["selected_row_ids"] == [0, 1, 2]


def test_tool_writes_nothing(tmp_path, monkeypatch, capsys):
    archive, source, _ = _build_synthetic(tmp_path, monkeypatch)
    before = {p.name for p in tmp_path.rglob("*")}
    rc, _rep = _run_tool(archive, source, capsys)
    assert rc == 0
    assert {p.name for p in tmp_path.rglob("*")} == before


# ═══════════════════════════ refusal gates (fail-closed) ════════════════════════════════════════
def test_refuses_wrong_implementation_commit(tmp_path, monkeypatch, capsys):
    archive, source, _ = _build_synthetic(tmp_path, monkeypatch)
    monkeypatch.setattr(tool, "_head_commit", lambda _w: "f" * 40)
    rc, rep = _run_tool(archive, source, capsys)
    assert rc == 2 and rep["disposition"] == "REFUSED"
    assert rep["detail"].startswith("IMPLEMENTATION_COMMIT_MISMATCH")


def test_refuses_checkpoint_hash_mismatch(tmp_path, monkeypatch, capsys):
    archive, source, _ = _build_synthetic(tmp_path, monkeypatch)
    monkeypatch.setattr(tool, "PINNED_CHECKPOINT_SHA256", "0" * 64)
    rc, rep = _run_tool(archive, source, capsys)
    assert rc == 2 and rep["detail"].startswith("CHECKPOINT_HASH_MISMATCH")


def test_refuses_manifest_hash_mismatch(tmp_path, monkeypatch, capsys):
    archive, source, _ = _build_synthetic(tmp_path, monkeypatch)
    monkeypatch.setattr(tool, "PINNED_MANIFEST_SHA256", "0" * 64)
    rc, rep = _run_tool(archive, source, capsys)
    assert rc == 2 and rep["detail"].startswith("MANIFEST_HASH_MISMATCH")


def test_refuses_corpus_hash_mismatch(tmp_path, monkeypatch, capsys):
    archive, source, _ = _build_synthetic(tmp_path, monkeypatch)
    monkeypatch.setattr(tool, "PINNED_CORPUS_HASH", "0" * 64)
    rc, rep = _run_tool(archive, source, capsys)
    assert rc == 2 and rep["detail"].startswith("CORPUS_HASH_MISMATCH")


def test_refuses_writable_checkpoint(tmp_path, monkeypatch, capsys):
    archive, source, _ = _build_synthetic(tmp_path, monkeypatch)
    os.chmod(archive / tool.CHECKPOINT_NAME, stat.S_IRUSR | stat.S_IWUSR)
    rc, rep = _run_tool(archive, source, capsys)
    assert rc == 2 and rep["detail"].startswith("ARCHIVE_CHECKPOINT_WRITABLE")


def test_refuses_schema_version_drift(tmp_path, monkeypatch, capsys):
    archive, source, _ = _build_synthetic(tmp_path, monkeypatch)
    monkeypatch.setattr(tool, "EVIDENCE_SCHEMA_VERSION", "1.0")
    rc, rep = _run_tool(archive, source, capsys)
    assert rc == 2 and rep["detail"].startswith("SCHEMA_VERSION_MISMATCH")


def test_refuses_selection_over_bound(tmp_path, monkeypatch, capsys):
    archive, source, _ = _build_synthetic(tmp_path, monkeypatch)
    monkeypatch.setattr(tool, "MAX_SELECTED", 1)
    rc, rep = _run_tool(archive, source, capsys)
    assert rc == 2 and rep["detail"].startswith("SELECTION_EXCEEDS_BOUND")


def test_population_count_cross_check_fails_loudly(tmp_path, monkeypatch, capsys):
    # a forensic-count mismatch is NOT a refusal gate, but it must fail the disposition
    archive, source, _ = _build_synthetic(tmp_path, monkeypatch)
    monkeypatch.setattr(tool, "EXPECTED_FORMERLY_FAILING", 99)
    rc, rep = _run_tool(archive, source, capsys)
    assert rc == 1 and rep["disposition"] == "FAIL"
    assert rep["population"]["counts_match_run4_forensics"] is False


# ═══════════════════ v1.0a: containment, reconciliation, strict paths, /tools model ═════════════
def _rewrite_checkpoint(archive, lines):
    cp = archive / tool.CHECKPOINT_NAME
    os.chmod(cp, stat.S_IRUSR | stat.S_IWUSR)
    cp.write_text("\n".join(lines) + "\n", encoding="utf-8")
    os.chmod(cp, stat.S_IRUSR | stat.S_IRGRP | stat.S_IROTH)
    return tool._sha256_file(str(cp))


def _checkpoint_lines(recs, ids=None, terminal_n=None, terminal_status="COMPLETE",
                      with_terminal=True):
    ids = list(range(len(recs))) if ids is None else ids
    lines = [json.dumps({"kind": "record", "row_id": rid, "class": "qualified",
                         "input_content_hash": sc.rec_content_hash(recs[i])},
                        separators=(",", ":")) for i, rid in enumerate(ids)]
    if with_terminal:
        lines.append(json.dumps({"kind": "terminal", "status": terminal_status,
                                 "n_records": len(ids) if terminal_n is None else terminal_n}))
    return lines


def test_v10a_expected_records_pin_is_3895():
    # the fixture monkeypatches it; the COMMITTED pin must be the registered population size
    src = Path(TOOL_PATH).read_text(encoding="utf-8")
    assert "EXPECTED_N_RECORDS = 3895" in src


def test_v10a_runs_as_standalone_tools_file(tmp_path):
    # /tools execution model: the tool is invoked BY FILE PATH from outside the checkout, with
    # imports resolving via PYTHONPATH — and even with a bogus archive it emits exactly one
    # bounded JSON document, REFUSED, exit 2, nothing on a traceback
    backend = os.path.dirname(os.path.dirname(os.path.abspath(inspect.getsourcefile(run))))
    tools_dir = tmp_path / "tools"
    tools_dir.mkdir()
    copy = tools_dir / "mr002_run4_archive_qualification.py"
    copy.write_text(Path(TOOL_PATH).read_text(encoding="utf-8"), encoding="utf-8")
    env = {**os.environ, "PYTHONPATH": backend}
    proc = _subprocess.run([_sys.executable, str(copy),
                            "--archive", str(tmp_path / "missing")],
                           capture_output=True, text=True, timeout=300, env=env,
                           cwd=str(tmp_path))
    rep = json.loads(proc.stdout)
    assert proc.returncode == 2 and rep["disposition"] == "REFUSED"
    assert "Traceback" not in proc.stderr


def test_v10a_argparse_failure_contained(tmp_path, monkeypatch, capsys):
    archive, source, _ = _build_synthetic(tmp_path, monkeypatch)
    rc = tool.main(["--archive", str(archive), "--bogus-flag"], corpus_source=source)
    rep = json.loads(capsys.readouterr().out)
    assert rc == 2 and rep["disposition"] == "REFUSED"
    assert rep["detail"].startswith("ARGUMENT_PARSE")


def test_v10a_missing_required_argument_contained(capsys):
    rc = tool.main([], corpus_source=lambda: None)
    rep = json.loads(capsys.readouterr().out)
    assert rc == 2 and rep["detail"].startswith("ARGUMENT_PARSE")


def test_v10a_invalid_explicit_row_id_refuses(tmp_path, monkeypatch, capsys):
    archive, source, _ = _build_synthetic(tmp_path, monkeypatch)
    for bad in ("99", "abc"):
        rc, rep = _run_tool(archive, source, capsys, extra=("--rows", bad))
        assert rc == 2 and rep["detail"].startswith("INVALID_ROW_ID")


def test_v10a_duplicate_archived_row_ids_refuse(tmp_path, monkeypatch, capsys):
    archive, source, recs = _build_synthetic(tmp_path, monkeypatch)
    sha = _rewrite_checkpoint(archive, _checkpoint_lines(recs, ids=[0, 1, 1]))
    monkeypatch.setattr(tool, "PINNED_CHECKPOINT_SHA256", sha)
    rc, rep = _run_tool(archive, source, capsys)
    assert rc == 2 and rep["detail"].startswith("DUPLICATE_ARCHIVED_ROW_IDS:[1]")


def test_v10a_row_set_mismatch_refuses(tmp_path, monkeypatch, capsys):
    archive, source, recs = _build_synthetic(tmp_path, monkeypatch)
    sha = _rewrite_checkpoint(archive, _checkpoint_lines(recs, ids=[0, 1, 7]))
    monkeypatch.setattr(tool, "PINNED_CHECKPOINT_SHA256", sha)
    rc, rep = _run_tool(archive, source, capsys)
    assert rc == 2
    assert rep["detail"].startswith("ARCHIVE_CORPUS_ROW_SET_MISMATCH:missing=[2]:extra=[7]")


def test_v10a_non_integer_archived_row_id_refuses(tmp_path, monkeypatch, capsys):
    archive, source, recs = _build_synthetic(tmp_path, monkeypatch)
    sha = _rewrite_checkpoint(archive, _checkpoint_lines(recs, ids=[0, 1, "x"]))
    monkeypatch.setattr(tool, "PINNED_CHECKPOINT_SHA256", sha)
    rc, rep = _run_tool(archive, source, capsys)
    assert rc == 2 and rep["detail"].startswith("ARCHIVE_ROW_ID_INVALID")


def test_v10a_missing_terminal_refuses(tmp_path, monkeypatch, capsys):
    archive, source, recs = _build_synthetic(tmp_path, monkeypatch)
    sha = _rewrite_checkpoint(archive, _checkpoint_lines(recs, with_terminal=False))
    monkeypatch.setattr(tool, "PINNED_CHECKPOINT_SHA256", sha)
    rc, rep = _run_tool(archive, source, capsys)
    assert rc == 2 and rep["detail"].startswith("ARCHIVE_TERMINAL_NOT_COMPLETE")


def test_v10a_failed_terminal_refuses(tmp_path, monkeypatch, capsys):
    archive, source, recs = _build_synthetic(tmp_path, monkeypatch)
    sha = _rewrite_checkpoint(archive, _checkpoint_lines(recs, terminal_status="FAILED"))
    monkeypatch.setattr(tool, "PINNED_CHECKPOINT_SHA256", sha)
    rc, rep = _run_tool(archive, source, capsys)
    assert rc == 2 and rep["detail"].startswith("ARCHIVE_TERMINAL_NOT_COMPLETE:FAILED")


def test_v10a_wrong_terminal_count_refuses(tmp_path, monkeypatch, capsys):
    archive, source, recs = _build_synthetic(tmp_path, monkeypatch)
    sha = _rewrite_checkpoint(archive, _checkpoint_lines(recs, terminal_n=99))
    monkeypatch.setattr(tool, "PINNED_CHECKPOINT_SHA256", sha)
    rc, rep = _run_tool(archive, source, capsys)
    assert rc == 2 and rep["detail"].startswith("ARCHIVE_TERMINAL_COUNT_MISMATCH:99!=3")


def test_v10a_archive_not_a_directory_refuses(tmp_path, monkeypatch, capsys):
    archive, source, _ = _build_synthetic(tmp_path, monkeypatch)
    not_dir = tmp_path / "not_a_dir"
    not_dir.write_text("x", encoding="utf-8")
    os.chmod(not_dir, stat.S_IRUSR)
    rc = tool.main(["--archive", str(not_dir), "--work-root", "."], corpus_source=source)
    rep = json.loads(capsys.readouterr().out)
    assert rc == 2 and rep["detail"].startswith("ARCHIVE_DIR_NOT_A_DIRECTORY")


def test_v10a_checkpoint_is_a_directory_refuses(tmp_path, monkeypatch, capsys):
    archive, source, _ = _build_synthetic(tmp_path, monkeypatch)
    cp = archive / tool.CHECKPOINT_NAME
    os.chmod(cp, stat.S_IRUSR | stat.S_IWUSR)
    cp.unlink()
    cp.mkdir()
    real_access = os.access
    monkeypatch.setattr(os, "access", lambda p, m: (
        False if m == os.W_OK and str(p).startswith(str(archive)) else real_access(p, m)))
    rc, rep = _run_tool(archive, source, capsys)
    assert rc == 2 and rep["detail"].startswith("ARCHIVE_CHECKPOINT_NOT_A_REGULAR_FILE")


def test_v10a_symlink_checkpoint_refuses(tmp_path, monkeypatch, capsys):
    archive, source, _ = _build_synthetic(tmp_path, monkeypatch)
    cp = archive / tool.CHECKPOINT_NAME
    target = tmp_path / "real_target"
    os.chmod(cp, stat.S_IRUSR | stat.S_IWUSR)
    cp.rename(target)
    try:
        os.symlink(target, cp)
    except OSError:
        pytest.skip("symlink creation requires privilege on this platform")
    rc, rep = _run_tool(archive, source, capsys)
    assert rc == 2 and rep["detail"].startswith("ARCHIVE_CHECKPOINT_IS_SYMLINK")


def test_v10a_corpus_source_exception_contained(tmp_path, monkeypatch, capsys):
    archive, _source, _ = _build_synthetic(tmp_path, monkeypatch)

    def exploding():
        raise RuntimeError("corpus infrastructure fault")
    rc, rep = _run_tool(archive, exploding, capsys)
    assert rc == 2 and rep["disposition"] == "REFUSED"
    assert rep["detail"].startswith("UNHANDLED:RuntimeError")


def test_v10a_malformed_checkpoint_contained(tmp_path, monkeypatch, capsys):
    archive, source, recs = _build_synthetic(tmp_path, monkeypatch)
    lines = _checkpoint_lines(recs)
    lines.insert(1, "{GARBAGE")
    sha = _rewrite_checkpoint(archive, lines)
    monkeypatch.setattr(tool, "PINNED_CHECKPOINT_SHA256", sha)
    rc, rep = _run_tool(archive, source, capsys)
    assert rc == 2 and rep["detail"] == "ARCHIVE_CHECKPOINT_UNREADABLE"


def test_v10a_qualification_exception_contained(tmp_path, monkeypatch, capsys):
    archive, source, _ = _build_synthetic(tmp_path, monkeypatch)

    def exploding_qualify(rid, canon, archived):
        raise ValueError("qualification fault")
    monkeypatch.setattr(tool, "qualify_record", exploding_qualify)
    rc, rep = _run_tool(archive, source, capsys)
    assert rc == 1 and rep["disposition"] == "FAIL"
    for r in rep["records"]:
        assert r["pass"] is False and r["error"].startswith("ValueError:qualification fault")


def test_v10a_report_serialization_failure_contained(tmp_path, monkeypatch, capsys):
    archive, source, _ = _build_synthetic(tmp_path, monkeypatch)
    real_dumps = json.dumps
    calls = {"n": 0}

    def flaky_dumps(obj, **kw):
        calls["n"] += 1
        if calls["n"] == 1:
            raise TypeError("unserializable report")
        return real_dumps(obj, **kw)
    monkeypatch.setattr(tool.json, "dumps", flaky_dumps)
    rc = tool.main(["--archive", str(archive), "--work-root", "."], corpus_source=source)
    monkeypatch.setattr(tool.json, "dumps", real_dumps)
    rep = json.loads(capsys.readouterr().out)
    assert rc == 2 and rep["detail"] == "REPORT_SERIALIZATION_FAILED:TypeError"


def test_v10a_unexpected_exception_never_escapes(tmp_path, monkeypatch, capsys):
    # even a fault injected into the gate layer yields the single bounded JSON, exit 2
    archive, source, _ = _build_synthetic(tmp_path, monkeypatch)
    monkeypatch.setattr(tool, "run_gates", lambda *_a: (_ for _ in ()).throw(OSError("io")))
    rc, rep = _run_tool(archive, source, capsys)
    assert rc == 2 and rep["detail"].startswith("UNHANDLED:OSError")


@pytest.mark.skipif(os.environ.get("MR002_REAL_DOCKER_ARCHIVE_TEST") != "1",
                    reason="host-only: requires real Docker + Linux bind-mount semantics "
                           "(MR002_REAL_DOCKER_ARCHIVE_TEST=1, MR002_REAL_DOCKER_IMAGE, "
                           "MR002_REAL_DOCKER_WORK)")
def test_v10a_real_docker_mount_semantics(tmp_path):
    """HOST PHASE ONLY — proves in the actual Linux container that ro bind mounts pass the
    immutability gate, writable mounts refuse, symlinks refuse, and wrong path types refuse."""
    image = os.environ["MR002_REAL_DOCKER_IMAGE"]
    work = os.environ["MR002_REAL_DOCKER_WORK"]
    tools_dir = tmp_path / "tools"
    tools_dir.mkdir()
    (tools_dir / "t.py").write_text(Path(TOOL_PATH).read_text(encoding="utf-8"),
                                    encoding="utf-8")
    archive = tmp_path / "arch"
    archive.mkdir()
    (archive / tool.CHECKPOINT_NAME).write_text("{}\n", encoding="utf-8")
    (archive / tool.MANIFEST_NAME).write_text("{}\n", encoding="utf-8")
    probe = ("import sys; sys.path.insert(0, '/tools'); "
             "import importlib.util as u; "
             "s = u.spec_from_file_location('aq', '/tools/t.py'); m = u.module_from_spec(s); "
             "sys.modules['aq'] = m; s.loader.exec_module(m); "
             "import os; "
             "def probe(p, kind, expect):\n"
             "    try:\n"
             "        m._strict_path(p, kind, expect); print(kind + ':OK')\n"
             "    except m.ArchiveQualificationRefused as e: print(kind + ':' + str(e))\n"
             "probe('/archive', 'DIR', 'dir'); "
             "probe('/archive/" + tool.CHECKPOINT_NAME + "', 'CHECKPOINT', 'file'); "
             "probe('/archive/" + tool.MANIFEST_NAME + "', 'MANIFEST', 'file')")

    def run_probe(archive_mount_spec):
        return _subprocess.run(
            ["sudo", "docker", "run", "--rm", "--network=none",
             "--mount", f"type=bind,src={work},dst=/work,ro",
             "--mount", f"type=bind,src={tools_dir},dst=/tools,ro",
             "--mount", archive_mount_spec,
             "--env=PYTHONPATH=/work/apps/backend", image, "python", "-c", probe],
            capture_output=True, text=True, timeout=300)

    ro = run_probe(f"type=bind,src={archive},dst=/archive,ro")
    assert "DIR:OK" in ro.stdout and "CHECKPOINT:OK" in ro.stdout and "MANIFEST:OK" in ro.stdout
    rw = run_probe(f"type=bind,src={archive},dst=/archive,ro=false")
    assert "WRITABLE" in rw.stdout
    # symlink + wrong-type inside a ro mount
    (archive / tool.CHECKPOINT_NAME).unlink()
    os.symlink(archive / tool.MANIFEST_NAME, archive / tool.CHECKPOINT_NAME)
    ln = run_probe(f"type=bind,src={archive},dst=/archive,ro")
    assert "CHECKPOINT:ARCHIVE_CHECKPOINT_IS_SYMLINK" in ln.stdout
    os.unlink(archive / tool.CHECKPOINT_NAME)
    (archive / tool.CHECKPOINT_NAME).mkdir()
    wt = run_probe(f"type=bind,src={archive},dst=/archive,ro")
    assert "CHECKPOINT:ARCHIVE_CHECKPOINT_NOT_A_REGULAR_FILE" in wt.stdout
