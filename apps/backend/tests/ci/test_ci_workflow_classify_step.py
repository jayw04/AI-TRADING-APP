"""Regression pins for the `Classify changes` step in ci.yml (nightly defect A).

On `schedule` / `workflow_dispatch` there is no `before` in the event payload, so `dorny/paths-filter`
reports EVERY tracked file; as compact JSON that exceeded the Linux per-env-string limit
(MAX_ARG_STRLEN = 131,072 bytes) and the runner failed with `Argument list too long` before the step
script started (nightlies red since 2026-08-30). The list is only read on `pull_request`, so it must
only be exported on `pull_request`. Text-level parse of ci.yml (stdlib only, same approach as the other
CI-script tests); the real `run:` script is executed under bash.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[4]
CI_YML = REPO_ROOT / ".github" / "workflows" / "ci.yml"
CLASSIFIER = Path(__file__).resolve().parents[2] / "scripts" / "ci_classify_changes.py"
STEP_NAME = "- name: Classify changes (per-project FULL?)"
MAX_ARG_STRLEN = 131_072
ALL_FULL = {
    "backend_code=true",
    "mcp_server_code=true",
    "mcp_workbench_code=true",
    "agent_code=true",
    "adr0043_gate=true",
}


def _have_bash_and_python3() -> bool:
    py3 = shutil.which("python3")
    if shutil.which("bash") is None or py3 is None:
        return False
    # A Windows Store shim can be on PATH without being usable.
    probe = subprocess.run([py3, "-c", "pass"], capture_output=True, check=False)
    return probe.returncode == 0


# The CI runner (ubuntu-latest) always has both, so these never skip there.
needs_bash = pytest.mark.skipif(
    not _have_bash_and_python3(),
    reason="runs the real step script (needs bash and a working python3 on PATH)",
)


def _step_block() -> str:
    text = CI_YML.read_text(encoding="utf-8")
    start = text.index(STEP_NAME)
    indent = len(text[:start].rsplit("\n", 1)[-1])
    sibling = re.compile(rf"^ {{{indent}}}- (?:name|uses):", re.MULTILINE)
    nxt = sibling.search(text, start + len(STEP_NAME))
    return text[start : nxt.start() if nxt else len(text)]


def _env_expression() -> str:
    m = re.search(r"^\s+CHANGED_FILES_JSON:\s*(.+)$", _step_block(), re.MULTILINE)
    assert m, "CHANGED_FILES_JSON env entry not found in the Classify step"
    return m.group(1).strip()


def _run_script() -> str:
    lines = _step_block().splitlines()
    i = next(n for n, ln in enumerate(lines) if re.match(r"^\s+run: \|", ln))
    body = lines[i + 1 :]
    pad = len(body[0]) - len(body[0].lstrip())
    script: list[str] = []
    for ln in body:
        # The block scalar ends at the first non-blank line indented less than the script body
        # (this is where the next step's leading comment starts).
        if ln.strip() and len(ln) - len(ln.lstrip()) < pad:
            break
        script.append(ln[pad:])
    return "\n".join(script)


def _run_step(
    tmp_path: Path, event: str, files_json: str
) -> tuple[subprocess.CompletedProcess, str]:
    out = tmp_path / f"gh_output_{event}"
    out.write_text("", encoding="utf-8")
    env = {
        **os.environ,
        "GITHUB_EVENT_NAME": event,
        "GITHUB_OUTPUT": out.as_posix(),
        "RUNNER_TEMP": tmp_path.as_posix(),
        "CHANGED_FILES_JSON": files_json,
    }
    proc = subprocess.run(
        ["bash", "-c", _run_script()],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    return proc, out.read_text(encoding="utf-8")


def test_changed_files_env_is_only_exported_on_pull_request() -> None:
    expr = _env_expression()
    assert "github.event_name == 'pull_request'" in expr
    assert "steps.filter.outputs.all_files" in expr
    # Anything else (schedule, dispatch, push) must receive a tiny constant, never the whole-tree list.
    assert expr.endswith("|| '[]' }}")


def test_step_script_reads_the_list_only_on_pull_request() -> None:
    script = _run_script()
    assert 'if [ "$GITHUB_EVENT_NAME" = "pull_request" ]; then' in script
    head, _, tail = script.partition("else")
    assert "CHANGED_FILES_JSON" in head
    assert "CHANGED_FILES_JSON" not in tail


@needs_bash
@pytest.mark.parametrize("event", ["schedule", "workflow_dispatch", "push"])
def test_non_pr_events_resolve_to_all_projects_full(tmp_path: Path, event: str) -> None:
    # '[]' is what the gated expression yields on a non-PR event.
    proc, out = _run_step(tmp_path, event, "[]")
    assert proc.returncode == 0, proc.stderr
    assert set(out.split()) == ALL_FULL


@needs_bash
@pytest.mark.parametrize(
    ("files", "backend"),
    [(["docs/x.md"], "false"), (["apps/backend/app/x.py"], "true")],
)
def test_pull_request_event_still_uses_the_classifier(
    tmp_path: Path, files: list[str], backend: str
) -> None:
    proc, out = _run_step(tmp_path, "pull_request", json.dumps(files))
    assert proc.returncode == 0, proc.stderr
    assert f"backend_code={backend}" in out.split()


@needs_bash
def test_pull_request_event_with_malformed_list_fails_closed(tmp_path: Path) -> None:
    proc, _ = _run_step(tmp_path, "pull_request", "not json")
    assert proc.returncode != 0


def test_classifier_cli_accepts_a_list_larger_than_the_env_limit(tmp_path: Path) -> None:
    # Same entry point the workflow uses (argv file path): the classifier itself has no size limit;
    # the limit was only ever the environment variable.
    payload = json.dumps([f"apps/frontend/src/generated/file_{i:05d}.ts" for i in range(4000)])
    assert len(payload.encode()) > MAX_ARG_STRLEN
    big = tmp_path / "big.json"
    big.write_text(payload, encoding="utf-8")
    proc = subprocess.run(
        [sys.executable, str(CLASSIFIER), str(big)], capture_output=True, text=True, check=False
    )
    assert proc.returncode == 0, proc.stderr
    assert "backend_code=false" in proc.stdout.split()


@pytest.mark.skipif(not sys.platform.startswith("linux"), reason="MAX_ARG_STRLEN is a Linux limit")
def test_premise_a_single_env_string_over_the_limit_cannot_exec() -> None:
    # Pins WHY the env var is gated, so nobody simplifies the expression back.
    with pytest.raises(OSError):
        subprocess.run(["true"], env={"X": "a" * (MAX_ARG_STRLEN + 8_000)}, check=False)
