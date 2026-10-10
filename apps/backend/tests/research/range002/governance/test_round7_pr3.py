"""Round 7 (PR 3): one shared attempt-limit constant, and a recursion-bomb first line cannot
crash or bypass enrolment. Level 1 only (accidental misuse, casual bypass)."""

from __future__ import annotations

import inspect
from pathlib import Path

import pytest

from app.research.range002.governance import errors, model, results_guard, run_registry
from app.research.range002.governance.run_registry import RunRegistry
from app.research.range002.spec import limits


def test_attempt_limit_has_one_source_of_truth() -> None:
    assert model.MAX_ATTEMPT_LIMIT is limits.MAX_ATTEMPT_LIMIT
    assert model.MAX_ATTEMPT_LIMIT == 10_000
    assert results_guard.MAX_ATTEMPT_LIMIT is limits.MAX_ATTEMPT_LIMIT
    assert run_registry.MAX_ATTEMPT_LIMIT is limits.MAX_ATTEMPT_LIMIT
    assert "MAX_ATTEMPT_LIMIT" in inspect.getsource(RunRegistry.mark_capability_issued)
    assert "MAX_ATTEMPT_LIMIT" in inspect.getsource(results_guard)
    # model.py imports the constant; it does not define a literal of its own
    assert "10_000" not in inspect.getsource(model)


def test_recursion_bomb_first_line_fails_closed_with_the_named_error(tmp_path: Path) -> None:
    """Reviewer PoC: a first line of 300000 '[' makes json.loads raise RecursionError, which the
    old ``except ValueError`` did not catch, so enrolment crashed with a bare RecursionError."""
    (tmp_path / "bomb.log").write_bytes(b"[" * 300_000 + b"\n")
    with pytest.raises(errors.RegistryEnrollmentError, match="already contains"):
        RunRegistry.enroll_new(tmp_path / "reg.jsonl", enrolled_by="owner")
    assert not (tmp_path / "reg.jsonl").exists()
