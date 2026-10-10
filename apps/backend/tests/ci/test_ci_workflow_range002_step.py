"""Pin: the RANGE-002 Linux acceptance step must not be guarded by file-existence checks.

A `hashFiles(...)` term in the step's `if:` makes the step silently SKIP (job green) when the required
tests or manifest are deleted. The step must instead run and fail. Text-level parse only (stdlib, no
PyYAML), same approach as the other CI-script tests.
"""

from __future__ import annotations

import re
from pathlib import Path

CI_YML = Path(__file__).resolve().parents[4] / ".github" / "workflows" / "ci.yml"
STEP_NAME = "- name: RANGE-002 Linux acceptance"


def _step_block(text: str) -> str:
    start = text.index(STEP_NAME)
    indent = len(text[:start].rsplit("\n", 1)[-1])
    # The step ends at the next sibling "- name:" / "- uses:" at the same indent.
    sibling = re.compile(rf"^ {{{indent}}}- (?:name|uses):", re.MULTILINE)
    nxt = sibling.search(text, start + len(STEP_NAME))
    return text[start : nxt.start() if nxt else len(text)]


def _if_expression(block: str) -> str:
    lines = block.splitlines()
    i = next(n for n, ln in enumerate(lines) if ln.strip().startswith("if:"))
    out = [lines[i]]
    for ln in lines[i + 1 :]:
        if re.match(r"^\s+(?:working-directory|run|id|env|with):", ln):
            break
        out.append(ln)
    return "\n".join(out)


def test_range002_step_present_and_gated_by_filter_or_dispatch() -> None:
    expr = _if_expression(_step_block(CI_YML.read_text(encoding="utf-8")))
    assert "needs.changes.outputs.range002 == 'true'" in expr
    assert "workflow_dispatch" in expr


def test_range002_step_if_has_no_hashfiles_guard() -> None:
    expr = _if_expression(_step_block(CI_YML.read_text(encoding="utf-8")))
    assert "hashFiles" not in expr, (
        "RANGE-002 step `if:` must not use hashFiles: a missing test/manifest must FAIL the step, "
        "not skip it silently"
    )


def _run_script(block: str) -> str:
    lines = block.splitlines()
    i = next(n for n, ln in enumerate(lines) if re.match(r"^\s+run: \|", ln))
    return "\n".join(lines[i + 1 :])


def _verifier_command(script: str) -> list[str]:
    joined = script.replace("\\\n", " ")
    line = next(ln for ln in joined.splitlines() if "ci_verify_required_tests.py" in ln)
    return line.split()


def test_range002_step_script_has_no_allow_pending() -> None:
    # Fully fail-closed: PENDING must be a failure on pull_request as well as on dispatch.
    script = _run_script(_step_block(CI_YML.read_text(encoding="utf-8")))
    assert "--allow-pending" not in script
    assert "allow=" not in script and "$allow" not in script


def test_range002_step_verifier_flags_are_exactly_the_strict_set() -> None:
    cmd = _verifier_command(_run_script(_step_block(CI_YML.read_text(encoding="utf-8"))))
    assert {t for t in cmd if t.startswith("--")} == {
        "--junit",
        "--manifest",
        "--root",
        "--table-out",
    }


def test_range002_step_has_no_skip_or_continue_escape_hatches() -> None:
    block = _step_block(CI_YML.read_text(encoding="utf-8"))
    script = _run_script(block)
    assert "continue-on-error" not in block
    assert "|| true" not in script
    assert "hashFiles" not in block.split("run: |", 1)[0]
    assert "--allow-pending" not in script


def test_range002_step_fails_when_pytest_or_verifier_fails() -> None:
    script = _run_script(_step_block(CI_YML.read_text(encoding="utf-8")))
    assert '[ "$pytest_rc" -ne 0 ] || [ "$verify_rc" -ne 0 ]' in script
    assert "exit 1" in script
