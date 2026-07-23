"""Tests for the CI change classifier (the single source of truth for LIGHT vs FULL on a PR).

Pins the owner-authorized policy (2026-07-23): a change to any testable backend/deployment path forces
the FULL suite on the PR; docs-only and genuinely unrelated frontend-only changes stay LIGHT; a test
file is CODE; and the classifier FAILS CLOSED on malformed input rather than waving a PR through.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from scripts.ci_classify_changes import main, requires_full

CLASSIFIER = Path(__file__).resolve().parents[2] / "scripts" / "ci_classify_changes.py"


# ---- paths that MUST trigger FULL ---------------------------------------------------------------

@pytest.mark.parametrize("path", [
    "apps/backend/app/validation/first_session.py",       # backend source
    "apps/backend/app/risk/loss_control.py",
    "apps/backend/tests/validation/test_first_session_atomic_open.py",  # a TEST is code
    "apps/backend/pyproject.toml",                         # backend build config
    "apps/backend/alembic.ini",
    "deploy/aws/provision-adr0043-validation.sh",          # deploy script (exercised by the suite)
    "deploy/aws/tests/test_provision_adr0043_validation.sh",
    "scripts/range_postrun_verify.py",                     # repo-root operational script
    "tests/smoke/test_x.py",                               # repo-root tests
    "pyproject.toml",                                      # root build config
    "requirements-dev.txt",
    "poetry.lock",
    "uv.lock",
    "alembic.ini",
    ".github/workflows/ci.yml",                            # a workflow change re-verifies everything
])
def test_code_paths_trigger_full(path):
    assert requires_full([path]) is True


# ---- paths that must NOT trigger FULL -----------------------------------------------------------

@pytest.mark.parametrize("path", [
    "docs/design/whatever.md",                             # docs-only
    "Docs/Cost Control.md",
    "README.md",
    "docs/adr/0009-stateless-agent-invocation.md",
    "apps/frontend/src/pages/Home.tsx",                    # frontend-only
    "apps/frontend/package.json",
    "apps/frontend/pnpm-lock.yaml",
    ".github/ISSUE_TEMPLATE/bug.md",
    ".github/workflows/other-workflow.yml",                # a DIFFERENT workflow, not ci.yml
])
def test_non_code_paths_do_not_trigger_full(path):
    assert requires_full([path]) is False


# ---- combinations ------------------------------------------------------------------------------

def test_any_code_path_in_a_mixed_set_triggers_full():
    assert requires_full(["docs/x.md", "apps/frontend/y.tsx",
                          "apps/backend/app/z.py"]) is True


def test_pure_docs_and_frontend_set_stays_light():
    assert requires_full(["docs/x.md", "README.md", "apps/frontend/y.tsx"]) is False


def test_empty_changeset_is_light():
    assert requires_full([]) is False


def test_leading_dot_slash_is_normalized():
    assert requires_full(["./apps/backend/app/z.py"]) is True


# ---- CLI contract: prints exactly true/false, exit 0 --------------------------------------------

def test_cli_prints_true_for_code(tmp_path, capsys):
    f = tmp_path / "changed.json"
    f.write_text(json.dumps(["apps/backend/app/z.py"]), encoding="utf-8")
    rc = main(["ci_classify_changes.py", str(f)])
    assert rc == 0 and capsys.readouterr().out.strip() == "true"


def test_cli_prints_false_for_docs(tmp_path, capsys):
    f = tmp_path / "changed.json"
    f.write_text(json.dumps(["docs/x.md"]), encoding="utf-8")
    rc = main(["ci_classify_changes.py", str(f)])
    assert rc == 0 and capsys.readouterr().out.strip() == "false"


# ---- FAIL CLOSED on malformed input -------------------------------------------------------------

def test_cli_fails_closed_on_malformed_json(tmp_path, capsys):
    f = tmp_path / "bad.json"
    f.write_text("{not json", encoding="utf-8")
    rc = main(["ci_classify_changes.py", str(f)])
    assert rc == 2 and capsys.readouterr().out.strip() == ""      # no "false" emitted


def test_cli_fails_closed_on_non_array_json(tmp_path):
    f = tmp_path / "obj.json"
    f.write_text('{"a": 1}', encoding="utf-8")
    assert main(["ci_classify_changes.py", str(f)]) == 2


def test_cli_fails_closed_on_missing_file(tmp_path):
    assert main(["ci_classify_changes.py", str(tmp_path / "nope.json")]) == 2


def test_subprocess_exit_code_is_nonzero_on_bad_input(tmp_path):
    """End-to-end: a real process must exit non-zero so the workflow step fails closed."""
    f = tmp_path / "bad.json"
    f.write_text("not json at all", encoding="utf-8")
    proc = subprocess.run([sys.executable, str(CLASSIFIER), str(f)],
                          capture_output=True, text=True)
    assert proc.returncode != 0 and proc.stdout.strip() == ""
