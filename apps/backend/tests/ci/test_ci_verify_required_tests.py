"""Tests for the RANGE-002 required-test verifier (scripts/ci_verify_required_tests.py).

The verifier is what turns a green Linux pytest run into *evidence*: a required test that was skipped,
not collected, errored or failed must fail the step, and a test whose file does not exist yet (PR 3)
must be reported PENDING - never PASSED.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from scripts.ci_verify_required_tests import (
    EXIT_FAIL,
    EXIT_OK,
    EXIT_PENDING,
    EXIT_USAGE,
    VerifierError,
    load_manifest,
    main,
    node_id_to_junit_key,
)

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "ci_verify_required_tests.py"
REAL_MANIFEST = Path(__file__).resolve().parents[2] / "ci" / "range002_required_linux_tests.json"

A = "tests/r/spec/test_a.py::test_one"
B = "tests/r/spec/test_a.py::test_two"
P = "tests/r/gov/test_p.py::test_param[x]"
C = "tests/r/gov/test_c.py::TestCls::test_in_class"


def _case(node_id: str, outcome: str = "pass") -> str:
    classname, name = node_id_to_junit_key(node_id)
    name = name.replace("&", "&amp;").replace("<", "&lt;")
    body = {
        "pass": "",
        "skip": '<skipped type="pytest.skip" message="reason: no symlink">skipped</skipped>',
        "xfail": '<skipped type="pytest.xfail" message="xfail">x</skipped>',
        "fail": '<failure message="assert 1 == 2">trace</failure>',
        "error": '<error message="fixture blew up">trace</error>',
    }[outcome]
    return f'<testcase classname="{classname}" name="{name}" time="0.01">{body}</testcase>'


def _xml(*cases: str) -> str:
    return f'<?xml version="1.0"?><testsuites><testsuite name="pytest">{"".join(cases)}</testsuite></testsuites>'


def _manifest(*entries: dict) -> str:
    return json.dumps({"schema": 1, "tests": list(entries)})


def _run(tmp_path: Path, xml: str, manifest: str, *extra: str, files: tuple[str, ...] = ()) -> int:
    for rel in files:
        f = tmp_path / rel
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text("", encoding="utf-8")
    (tmp_path / "j.xml").write_text(xml, encoding="utf-8")
    (tmp_path / "m.json").write_text(manifest, encoding="utf-8")
    return main(
        [
            "--junit", str(tmp_path / "j.xml"),
            "--manifest", str(tmp_path / "m.json"),
            "--root", str(tmp_path),
            *extra,
        ]
    )  # fmt: skip


def _e(node_id: str, phase: str = "pr2", **kw: str) -> dict:
    return {"id": node_id, "phase": phase, **kw}


def test_node_id_mapping_matches_pytest_xunit2_shape() -> None:
    assert node_id_to_junit_key(A) == ("tests.r.spec.test_a", "test_one")
    assert node_id_to_junit_key(P) == ("tests.r.gov.test_p", "test_param[x]")
    assert node_id_to_junit_key(C) == ("tests.r.gov.test_c.TestCls", "test_in_class")
    # `::` or `/` inside a parametrize id stays in the name
    assert node_id_to_junit_key("t/a.py::test_x[a::b/c]") == ("t.a", "test_x[a::b/c]")
    for bad in ("nonsense", "t/a.py", "t/a.txt::x", "::x"):
        with pytest.raises(VerifierError):
            node_id_to_junit_key(bad)


def test_all_pass(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    rc = _run(
        tmp_path,
        _xml(_case(A), _case(B), _case(P), _case(C)),
        _manifest(_e(A), _e(B), _e(P), _e(C)),
    )
    assert rc == EXIT_OK
    out = capsys.readouterr().out
    assert out.count("PASSED") == 4 and "required=4 collected=4 passed=4" in out


def test_skipped_test_fails(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    rc = _run(tmp_path, _xml(_case(A), _case(B, "skip")), _manifest(_e(A), _e(B)))
    assert rc == EXIT_FAIL
    out = capsys.readouterr().out
    assert "SKIPPED" in out and "reason: no symlink" in out and "skipped=1" in out


def test_xfail_is_not_a_pass(tmp_path: Path) -> None:
    assert _run(tmp_path, _xml(_case(A, "xfail")), _manifest(_e(A))) == EXIT_FAIL


def test_missing_test_fails(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    rc = _run(tmp_path, _xml(_case(A)), _manifest(_e(A), _e(B)), files=("tests/r/spec/test_a.py",))
    assert rc == EXIT_FAIL
    out = capsys.readouterr().out
    assert "MISSING" in out and "not in JUnit XML" in out


def test_absent_file_without_pending_marker_is_missing_not_ignored(tmp_path: Path) -> None:
    rc = _run(tmp_path, _xml(_case(A)), _manifest(_e(A), _e(P, "pr3")), "--allow-pending", files=())
    assert rc == EXIT_FAIL  # --allow-pending does NOT excuse an unmarked entry


def test_failed_test_fails(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    rc = _run(tmp_path, _xml(_case(A), _case(B, "fail")), _manifest(_e(A), _e(B)))
    assert rc == EXIT_FAIL
    assert "FAILED" in capsys.readouterr().out


def test_errored_test_fails(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    rc = _run(tmp_path, _xml(_case(A, "error")), _manifest(_e(A)))
    assert rc == EXIT_FAIL
    assert "ERROR" in capsys.readouterr().out


def test_duplicate_ids_in_xml_fail_closed(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    # e.g. a pass followed by a teardown error pytest records as a second <testcase> with the same id
    rc = _run(tmp_path, _xml(_case(A), _case(A, "error")), _manifest(_e(A)))
    assert rc == EXIT_FAIL
    assert "DUPLICATE" in capsys.readouterr().out
    assert _run(tmp_path, _xml(_case(A), _case(A)), _manifest(_e(A))) == EXIT_FAIL


def test_duplicate_ids_in_manifest_are_rejected(tmp_path: Path) -> None:
    assert _run(tmp_path, _xml(_case(A)), _manifest(_e(A), _e(A))) == EXIT_USAGE


def test_malformed_xml_is_a_usage_error_not_a_pass(tmp_path: Path) -> None:
    assert _run(tmp_path, "<testsuites><testsuite>", _manifest(_e(A))) == EXIT_USAGE
    assert _run(tmp_path, "not xml at all", _manifest(_e(A))) == EXIT_USAGE


def test_empty_xml_is_a_usage_error_not_a_pass(tmp_path: Path) -> None:
    assert _run(tmp_path, "", _manifest(_e(A))) == EXIT_USAGE
    assert _run(tmp_path, _xml(), _manifest(_e(A))) == EXIT_USAGE  # valid XML, zero testcases
    assert _run(tmp_path, "<html/>", _manifest(_e(A))) == EXIT_USAGE  # not JUnit


def test_missing_xml_file_is_a_usage_error(tmp_path: Path) -> None:
    (tmp_path / "m.json").write_text(_manifest(_e(A)), encoding="utf-8")
    rc = main(["--junit", str(tmp_path / "nope.xml"), "--manifest", str(tmp_path / "m.json")])
    assert rc == EXIT_USAGE


@pytest.mark.parametrize(
    "manifest",
    [
        "not json",
        "[]",
        json.dumps({"tests": []}),
        json.dumps({"tests": [{"id": A, "phase": "pr9"}]}),
        json.dumps({"tests": [{"id": "garbage", "phase": "pr2"}]}),
        json.dumps({"tests": [{"id": A, "phase": "pr2", "pending_pr": ""}]}),
        json.dumps({"tests": ["x"]}),
    ],
)
def test_invalid_manifest_is_a_usage_error(tmp_path: Path, manifest: str) -> None:
    assert _run(tmp_path, _xml(_case(A)), manifest) == EXIT_USAGE


def test_pending_is_reported_not_passed_and_distinct_exit_in_acceptance_mode(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    xml, man = _xml(_case(A)), _manifest(_e(A), _e(P, "pr3", pending_pr="3"))
    files = ("tests/r/spec/test_a.py",)
    assert _run(tmp_path, xml, man, files=files) == EXIT_PENDING
    out = capsys.readouterr().out
    assert "PENDING" in out and "pending=1" in out and "passed=1" in out
    assert "INCOMPLETE" in out


def test_pending_allowed_gate_mode_exits_zero_but_still_says_pending(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    xml, man = _xml(_case(A)), _manifest(_e(A), _e(P, "pr3", pending_pr="3"))
    assert _run(tmp_path, xml, man, "--allow-pending", files=("tests/r/spec/test_a.py",)) == EXIT_OK
    out = capsys.readouterr().out
    assert "PENDING" in out and "pending=1" in out


def test_allow_pending_does_not_mask_a_real_failure(tmp_path: Path) -> None:
    xml, man = _xml(_case(A, "skip")), _manifest(_e(A), _e(P, "pr3", pending_pr="3"))
    assert (
        _run(tmp_path, xml, man, "--allow-pending", files=("tests/r/spec/test_a.py",)) == EXIT_FAIL
    )


def test_pending_marker_ignored_once_the_file_exists(tmp_path: Path) -> None:
    # PR 3 landed: file present => the entry is required like any other (here: not collected => MISSING)
    xml, man = _xml(_case(A)), _manifest(_e(A), _e(P, "pr3", pending_pr="3"))
    files = ("tests/r/spec/test_a.py", "tests/r/gov/test_p.py")
    assert _run(tmp_path, xml, man, "--allow-pending", files=files) == EXIT_FAIL
    xml_ok = _xml(_case(A), _case(P))
    assert _run(tmp_path, xml_ok, man, files=files) == EXIT_OK


def test_phases_flag_selects_enabled_set(tmp_path: Path) -> None:
    xml, man = _xml(_case(A)), _manifest(_e(A), _e(P, "pr3"))
    assert _run(tmp_path, xml, man, "--phases", "pr2") == EXIT_OK
    assert _run(tmp_path, xml, man, "--phases", "pr2,pr3") == EXIT_FAIL
    assert _run(tmp_path, xml, man, "--phases", "pr9") == EXIT_USAGE


def test_there_is_no_ignore_if_absent_flag(tmp_path: Path) -> None:
    with pytest.raises(SystemExit) as ei:
        _run(tmp_path, _xml(_case(A)), _manifest(_e(A)), "--require-present-only-if-exists")
    assert ei.value.code == 2


def test_table_out_written_with_lf(tmp_path: Path) -> None:
    out = tmp_path / "t.txt"
    _run(tmp_path, _xml(_case(A)), _manifest(_e(A)), "--table-out", str(out))
    raw = out.read_bytes()
    assert b"required=1" in raw and b"\r" not in raw


def test_cli_exit_code_is_the_process_exit_code(tmp_path: Path) -> None:
    (tmp_path / "j.xml").write_text(_xml(_case(A, "skip")), encoding="utf-8")
    (tmp_path / "m.json").write_text(_manifest(_e(A)), encoding="utf-8")
    proc = subprocess.run(
        [sys.executable, str(SCRIPT), "--junit", str(tmp_path / "j.xml"),
         "--manifest", str(tmp_path / "m.json"), "--root", str(tmp_path)],
        capture_output=True, text=True, check=False,
    )  # fmt: skip
    assert proc.returncode == EXIT_FAIL and "SKIPPED" in proc.stdout


def test_committed_manifest_is_valid_and_covers_the_named_tests() -> None:
    """The committed manifest lists ONLY tests that exist in the PR that carries it: PR 2's four
    spec tests plus PR 3's governance tests (this PR extends the manifest in its own diff)."""
    reqs = load_manifest(REAL_MANIFEST)
    ids = {r.node_id.split("::", 1)[1] for r in reqs}
    pr2 = {
        "test_symlink_target_refused_and_nothing_written_through_it",
        "test_dangling_symlink_target_refused",
        "test_symlinked_manifest_refused",
        "test_canary_symlinks_work_on_linux",
    }
    pr3 = {
        "test_f9_symlink_alias_shares_the_lock",
        "test_f9_hardlink_alias_shares_the_lock",
        "test_f9_readers_are_not_blocked_by_the_writer_lock",
        "test_canary_lock_backend_matches_the_platform",
        "test_the_real_backend_excludes_a_second_holder",
        "test_fcntl_branch_runs_on_any_platform[False]",
        "test_fcntl_branch_runs_on_any_platform[True]",
        "test_four_processes_append_concurrently_through_the_real_backend",
        "test_namespace_lock_is_exclusive_through_the_real_backend",
        "test_threads_with_stale_views_never_fork_the_chain",
        "test_processes_serialize_appends_without_forking",
        "test_second_writer_with_same_stale_view_serialises_after_the_first",
        "test_lock_is_exclusive_and_fails_closed_on_timeout",
        "test_append_blocked_by_a_held_lock_is_refused_not_forked",
        "test_exactly_one_enrollment_wins_each_round[different]",
        "test_exactly_one_enrollment_wins_each_round[same]",
    }
    assert ids == pr2 | pr3
    assert len(reqs) == len(pr2) + len(pr3)
    assert {r.phase for r in reqs if r.node_id.split("::", 1)[1] in pr2} == {"pr2"}
    assert {r.phase for r in reqs if r.node_id.split("::", 1)[1] in pr3} == {"pr3"}
    assert all(r.pending_pr is None for r in reqs)
    backend = REAL_MANIFEST.parents[1]
    for r in reqs:
        test_file = backend / r.node_id.split("::", 1)[0]
        assert test_file.is_file(), (
            f"manifest lists a test file absent from this checkout: {r.node_id}"
        )
        assert f"def {r.node_id.split('::', 1)[1].split('[')[0]}" in test_file.read_text(
            encoding="utf-8"
        )
