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

from scripts.ci_classify_changes import (
    PROJECTS,
    classify,
    main,
    requires_adr0043_by_backend_attribution,
    requires_full,
)

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


# ---- CLI contract: one `<project>_code=<bool>` line per project, then `adr0043_gate` ------------

def test_cli_emits_a_line_per_project(tmp_path, capsys):
    f = tmp_path / "changed.json"
    f.write_text(json.dumps(["apps/backend/app/z.py"]), encoding="utf-8")
    assert main(["ci_classify_changes.py", str(f)]) == 0
    lines = capsys.readouterr().out.strip().splitlines()
    assert lines == ["backend_code=true", "mcp_server_code=false",
                     "mcp_workbench_code=false", "agent_code=false",
                     "adr0043_gate=true"]


def test_cli_docs_only_all_false(tmp_path, capsys):
    f = tmp_path / "changed.json"
    f.write_text(json.dumps(["docs/x.md"]), encoding="utf-8")
    assert main(["ci_classify_changes.py", str(f)]) == 0
    assert capsys.readouterr().out.strip().splitlines() == [
        "backend_code=false", "mcp_server_code=false",
        "mcp_workbench_code=false", "agent_code=false",
        "adr0043_gate=false"]


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


# ---- ADR 0043 loss-control gate selection (PR 1: path gating) -----------------------------------
#
# The gate runs `pytest tests/risk` with scoped branch coverage on app.risk.loss_control. Only a
# backend-project change (or a GLOBAL path) can move its outcome. These tests pin BOTH directions:
# it must fire for anything that can affect loss control, and must NOT fire for work that cannot.

@pytest.mark.parametrize(
    "path",
    [
        "apps/backend/app/risk/loss_control/gate.py",       # the modules under the coverage floor
        "apps/backend/app/risk/loss_control/state_machine.py",
        "apps/backend/app/risk/engine.py",                  # risk engine
        "apps/backend/app/services/order_router.py",        # order path
        "apps/backend/app/db/models/risk_limits.py",        # account-state controls
        "apps/backend/alembic/versions/abc_add_column.py",  # migrations
        "apps/backend/app/services/some_shared_service.py", # transitively shared services
        "apps/backend/tests/risk/test_loss_control.py",     # the tests implementing the gate
        "apps/backend/scripts/check_adr0043_coverage.py",   # the gate's own checker
        "apps/backend/pyproject.toml",                      # backend dependency surface
    ],
)
def test_adr0043_gate_runs_for_paths_that_can_affect_loss_control(path):
    assert requires_adr0043_by_backend_attribution([path]) is True


@pytest.mark.parametrize(
    "path",
    [
        "apps/frontend/src/components/Chart.tsx",           # unrelated frontend work
        "apps/frontend/package.json",
        "docs/adr/0043-loss-control.md",                    # documentation, even about ADR 0043
        "docs/review/mr002/evidence.json",
        "README.md",
        "apps/mcp-server/src/tools.py",                     # isolated auxiliary projects
        "apps/mcp-workbench/src/server.py",
        "apps/agent/src/runtime.py",
        "manifests/s3/objects/repo-docs-adr.v1.json",
        "reports/daily.md",
    ],
)
def test_adr0043_gate_skipped_for_paths_that_cannot(path):
    assert requires_adr0043_by_backend_attribution([path]) is False


def test_adr0043_gate_runs_for_global_paths():
    # A workflow or root-manifest change re-verifies everything, including this gate.
    assert requires_adr0043_by_backend_attribution([".github/workflows/ci.yml"]) is True
    assert requires_adr0043_by_backend_attribution(["uv.lock"]) is True


def test_adr0043_gate_defaults_UP_on_an_empty_changeset():
    # Deliberately DIFFERENT from FULL selection: for FULL, "nothing changed" means LIGHT; here an
    # empty list means the changed-file list could not be determined, so ambiguity defaults upward.
    assert requires_adr0043_by_backend_attribution([]) is True
    assert classify([])["backend"] is False          # the documented divergence


def test_adr0043_gate_runs_when_a_mixed_changeset_touches_backend():
    # One backend file among many irrelevant ones must still arm the gate.
    assert requires_adr0043_by_backend_attribution(
        ["apps/frontend/src/App.tsx", "docs/x.md", "apps/backend/app/risk/engine.py"]
    ) is True


def test_adr0043_gate_never_selects_lower_than_backend_full():
    # The core safety property: the gate must fire whenever backend FULL fires. If a future
    # narrowing breaks this, a loss-control regression could reach main under a green result.
    samples = [
        ["apps/backend/app/risk/loss_control/service.py"],
        ["apps/backend/tests/risk/test_gate.py"],
        ["deploy/aws/stack.yaml"],
        ["scripts/some_root_script.py"],
        [".github/workflows/ci.yml"],
        ["apps/frontend/src/App.tsx"],
        ["docs/note.md"],
        [],
    ]
    for paths in samples:
        if classify(paths)["backend"]:
            assert requires_adr0043_by_backend_attribution(paths) is True, paths


def test_cli_emits_the_adr0043_gate_line(tmp_path, capsys):
    f = tmp_path / "c.json"
    f.write_text(json.dumps(["apps/backend/app/risk/engine.py"]), encoding="utf-8")
    assert main(["ci_classify_changes.py", str(f)]) == 0
    assert "adr0043_gate=true" in capsys.readouterr().out.splitlines()


def test_cli_emits_gate_false_for_a_frontend_only_change(tmp_path, capsys):
    f = tmp_path / "c.json"
    f.write_text(json.dumps(["apps/frontend/src/App.tsx"]), encoding="utf-8")
    assert main(["ci_classify_changes.py", str(f)]) == 0
    assert "adr0043_gate=false" in capsys.readouterr().out.splitlines()


def test_adr0043_gate_handles_renames():
    """A rename surfaces as changed path(s). Whichever side is backend must arm the gate.

    dorny/paths-filter reports renamed files; depending on config the OLD path, the NEW path,
    or both appear. All three shapes must be safe, so a file moving OUT of the backend still
    arms the gate (its removal can change what tests/risk imports).
    """
    # backend -> backend
    assert requires_adr0043_by_backend_attribution(
        ["apps/backend/app/risk/old_name.py", "apps/backend/app/risk/new_name.py"]) is True
    # backend -> frontend, both sides listed
    assert requires_adr0043_by_backend_attribution(
        ["apps/backend/app/helper.py", "apps/frontend/src/helper.ts"]) is True
    # backend -> frontend, only the OLD (backend) path listed
    assert requires_adr0043_by_backend_attribution(["apps/backend/app/helper.py"]) is True
    # frontend -> frontend: nothing backend on either side
    assert requires_adr0043_by_backend_attribution(
        ["apps/frontend/src/a.tsx", "apps/frontend/src/b.tsx"]) is False


def test_adr0043_gate_mixed_path_matrix():
    """Mixed changesets: one backend path anywhere in the set must arm the gate."""
    irrelevant = ["docs/x.md", "apps/frontend/src/App.tsx", "apps/agent/src/r.py", "reports/d.md"]
    assert requires_adr0043_by_backend_attribution(irrelevant) is False
    for backend_path in (
        "apps/backend/app/risk/loss_control/gate.py",
        "apps/backend/tests/risk/test_x.py",
        "apps/backend/alembic/versions/x.py",
        "deploy/aws/stack.yaml",
        ".github/workflows/ci.yml",
    ):
        assert requires_adr0043_by_backend_attribution(irrelevant + [backend_path]) is True, backend_path


# ---- deterministic dependency resolution: constraints are GLOBAL --------------------------
#
# A change to a committed resolution alters the exact third-party graph EVERY project installs,
# so it must re-verify all of them — never just the project whose file changed. Same for the
# generator and the drift gate, since either can change or stop validating what lands there.

@pytest.mark.parametrize(
    "path",
    [
        "constraints/backend-py312.txt",
        "constraints/agent-py312.txt",
        "constraints/mcp-server-py312.txt",
        "constraints/mcp-workbench-py312.txt",
        "scripts/regenerate_dependency_locks.py",
        "scripts/check_dependency_locks.py",
    ],
)
def test_dependency_resolution_paths_flag_every_project(path):
    assert classify([path]) == dict.fromkeys(PROJECTS, True)


@pytest.mark.parametrize(
    "path",
    [
        "constraints/backend-py312.txt",
        "scripts/regenerate_dependency_locks.py",
    ],
)
def test_dependency_resolution_paths_also_arm_the_adr0043_gate(path):
    # A changed dependency graph can move loss-control behaviour or its coverage, so the
    # ADR-0043 gate must fire too. It does, via backend attribution.
    assert requires_adr0043_by_backend_attribution([path]) is True
