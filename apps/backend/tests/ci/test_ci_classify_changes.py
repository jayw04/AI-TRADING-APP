"""Tests for the CI change classifier (single source of truth for which Python projects run FULL on a PR).

Pins the owner-authorized policy (2026-07-23): a change to any testable path for a Python project forces
that project's FULL suite on the PR; a GLOBAL change (ci.yml, root manifests) forces ALL projects; a test
file is CODE; docs-only and unrelated frontend-only changes stay LIGHT; PR-controlled filenames are DATA
(never executed); and the classifier FAILS CLOSED on malformed input.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from scripts.ci_classify_changes import PROJECTS, classify, main, requires_full

CLASSIFIER = Path(__file__).resolve().parents[2] / "scripts" / "ci_classify_changes.py"


def _only(project: str) -> dict[str, bool]:
    return {p: (p == project) for p in PROJECTS}


def _all() -> dict[str, bool]:
    return dict.fromkeys(PROJECTS, True)


def _none() -> dict[str, bool]:
    return dict.fromkeys(PROJECTS, False)


# ---- per-project attribution --------------------------------------------------------------------

@pytest.mark.parametrize("path,project", [
    ("apps/backend/app/validation/first_session.py", "backend"),
    ("apps/backend/tests/validation/test_first_session_atomic_open.py", "backend"),  # a TEST is code
    ("apps/backend/pyproject.toml", "backend"),          # nested manifest ⇒ its own project only
    ("apps/backend/alembic.ini", "backend"),
    ("deploy/aws/provision-adr0043-validation.sh", "backend"),   # exercised by backend suite
    ("scripts/range_postrun_verify.py", "backend"),
    ("tests/smoke/test_x.py", "backend"),
    ("apps/mcp-server/src/server.py", "mcp_server"),
    ("apps/mcp-server/pyproject.toml", "mcp_server"),
    ("apps/mcp-workbench/src/app.py", "mcp_workbench"),
    ("apps/agent/src/agent.py", "agent"),
])
def test_path_attributes_to_exactly_one_project(path, project):
    assert classify([path]) == _only(project)


# ---- GLOBAL paths force ALL projects ------------------------------------------------------------

@pytest.mark.parametrize("path", [
    ".github/workflows/ci.yml",   # a workflow change re-verifies everything
    "pyproject.toml",             # ROOT manifest
    "requirements-dev.txt",
    "poetry.lock",
    "uv.lock",
])
def test_global_paths_flag_all_projects(path):
    assert classify([path]) == _all()


# ---- non-code paths flag NOTHING ----------------------------------------------------------------

@pytest.mark.parametrize("path", [
    "docs/design/whatever.md",
    "Docs/Cost Control.md",
    "README.md",
    "apps/frontend/src/pages/Home.tsx",     # frontend-only
    "apps/frontend/package.json",
    ".github/workflows/other-workflow.yml",  # a DIFFERENT workflow, not ci.yml
])
def test_non_code_paths_flag_nothing(path):
    assert classify([path]) == _none()
    assert requires_full([path]) is False


# ---- combinations -------------------------------------------------------------------------------

def test_multiple_projects_flagged_independently():
    assert classify(["apps/mcp-server/src/x.py",
                     "apps/agent/src/y.py"]) == {"backend": False, "mcp_server": True,
                                                 "mcp_workbench": False, "agent": True}


def test_any_code_in_a_mixed_set_flags_that_project():
    got = classify(["docs/x.md", "apps/frontend/y.tsx", "apps/backend/app/z.py"])
    assert got == _only("backend")
    assert requires_full(["docs/x.md", "apps/backend/app/z.py"]) is True


def test_pure_docs_and_frontend_set_is_light():
    assert classify(["docs/x.md", "README.md", "apps/frontend/y.tsx"]) == _none()


def test_empty_changeset_is_light():
    assert classify([]) == _none()
    assert requires_full([]) is False


def test_leading_dot_slash_is_normalized():
    assert classify(["./apps/backend/app/z.py"]) == _only("backend")


# ---- untrusted filenames are DATA, never executed (blocker #1) ----------------------------------

@pytest.mark.parametrize("evil", [
    "apps/backend/app/$(rm -rf ~).py",           # command-substitution characters
    "apps/backend/app/`whoami`.py",              # backticks
    "apps/backend/app/a';rm -rf /;'.py",         # single quote + shell syntax
    "apps/backend/app/with spaces .py",          # spaces
    "apps/backend/app/dollar$HOME.py",           # dollar sign
    "apps/backend/app/tab\tname.py",             # tab
    "apps/backend/app/new\nline.py",             # newline
])
def test_adversarial_filenames_are_classified_as_data(evil):
    # A hostile filename under apps/backend/** is still just a backend code path — classified, not run.
    assert classify([evil]) == _only("backend")


def test_adversarial_filenames_survive_the_json_cli_roundtrip(tmp_path, capsys):
    # The exact transport the workflow uses: JSON array on disk → classifier. No shell involved.
    evil = ["apps/backend/app/a';echo pwned;'.py", "apps/mcp-server/src/$(id).py"]
    f = tmp_path / "changed.json"
    f.write_text(json.dumps(evil), encoding="utf-8")
    assert main(["ci_classify_changes.py", str(f)]) == 0
    out = capsys.readouterr().out
    assert "backend_code=true" in out and "mcp_server_code=true" in out
    assert "pwned" not in out and "mcp_workbench_code=false" in out and "agent_code=false" in out


def test_adversarial_filename_does_not_execute_in_subprocess(tmp_path):
    """End-to-end through a real process: a filename with shell metacharacters must not run anything."""
    marker = tmp_path / "SHOULD_NOT_EXIST"
    evil = [f"apps/backend/app/x$(touch {marker}).py", "apps/agent/`touch " + str(marker) + "`.py"]
    f = tmp_path / "changed.json"
    f.write_text(json.dumps(evil), encoding="utf-8")
    proc = subprocess.run([sys.executable, str(CLASSIFIER), str(f)], capture_output=True, text=True)
    assert proc.returncode == 0
    assert not marker.exists()                    # no command substitution ever executed
    assert "backend_code=true" in proc.stdout and "agent_code=true" in proc.stdout


# ---- CLI contract: one `<project>_code=<bool>` line per project ---------------------------------

def test_cli_emits_a_line_per_project(tmp_path, capsys):
    f = tmp_path / "changed.json"
    f.write_text(json.dumps(["apps/backend/app/z.py"]), encoding="utf-8")
    assert main(["ci_classify_changes.py", str(f)]) == 0
    lines = capsys.readouterr().out.strip().splitlines()
    assert lines == ["backend_code=true", "mcp_server_code=false",
                     "mcp_workbench_code=false", "agent_code=false"]


def test_cli_docs_only_all_false(tmp_path, capsys):
    f = tmp_path / "changed.json"
    f.write_text(json.dumps(["docs/x.md"]), encoding="utf-8")
    assert main(["ci_classify_changes.py", str(f)]) == 0
    assert capsys.readouterr().out.strip().splitlines() == [
        "backend_code=false", "mcp_server_code=false",
        "mcp_workbench_code=false", "agent_code=false"]


# ---- FAIL CLOSED on malformed input -------------------------------------------------------------

def test_cli_fails_closed_on_malformed_json(tmp_path, capsys):
    f = tmp_path / "bad.json"
    f.write_text("{not json", encoding="utf-8")
    assert main(["ci_classify_changes.py", str(f)]) == 2
    assert capsys.readouterr().out.strip() == ""      # no output emitted on failure


def test_cli_fails_closed_on_non_array_json(tmp_path):
    f = tmp_path / "obj.json"
    f.write_text('{"a": 1}', encoding="utf-8")
    assert main(["ci_classify_changes.py", str(f)]) == 2


def test_cli_fails_closed_on_missing_file(tmp_path):
    assert main(["ci_classify_changes.py", str(tmp_path / "nope.json")]) == 2


def test_subprocess_exit_code_is_nonzero_on_bad_input(tmp_path):
    f = tmp_path / "bad.json"
    f.write_text("not json at all", encoding="utf-8")
    proc = subprocess.run([sys.executable, str(CLASSIFIER), str(f)], capture_output=True, text=True)
    assert proc.returncode != 0 and proc.stdout.strip() == ""
