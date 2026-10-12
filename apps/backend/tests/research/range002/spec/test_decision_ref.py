"""Meeting-decision reference (the migration that replaced role / signature fields).

Synthetic fixtures only. The decision block is pure data held outside the spec hash; these tests
pin its shape, the minutes-file check, and that no legacy role / signature identifier survives.
"""

from __future__ import annotations

import copy
import re
from pathlib import Path
from typing import Any

import pytest

from app.research.range002.spec import decision as decision_module
from app.research.range002.spec.decision import (
    MinutesMismatchError,
    MinutesMissingError,
    check_minutes_file,
)
from app.research.range002.spec.loader import SpecSchemaError, parse_draft
from app.research.range002.spec.schema import DecisionRef, draft_skeleton

from ._fixtures import (
    MINUTES_BYTES,
    MINUTES_RELPATH,
    MINUTES_SHA256,
    complete_payload,
    decision_block,
    make_symlink,
    set_path,
)

BACKEND = Path(__file__).resolve().parents[4]


def _problems(payload: dict[str, Any]) -> str:
    with pytest.raises(SpecSchemaError) as ei:
        parse_draft(payload)
    return " ".join(ei.value.problems)


# --- shape ----------------------------------------------------------------------------------


def test_valid_block_parses_and_is_frozen() -> None:
    ref = parse_draft(complete_payload()).decision
    assert isinstance(ref, DecisionRef)
    assert ref.decision == "approved" and ref.scope == ("build", "run")
    assert ref.spec_sha256 is None  # only the freeze tool fills it
    with pytest.raises(Exception):  # noqa: B017 - pydantic frozen-instance error
        ref.decision = "stop"  # type: ignore[misc]


def test_skeleton_has_a_null_decision_and_no_role_or_thesis_fields() -> None:
    sk = draft_skeleton()
    assert sk["decision"] is None
    assert "signoff" not in sk
    assert set(sk["governance"]) == {"exposure_signed", "registry_genesis_id"}
    assert parse_draft(sk).decision is None


def test_a_draft_may_carry_no_decision_but_the_key_is_required() -> None:
    payload = complete_payload(decided=False)
    assert parse_draft(payload).decision is None
    del payload["decision"]
    assert "decision" in _problems(payload)


@pytest.mark.parametrize(
    "key",
    [
        "decision_date",
        "record_kind",
        "minutes_path",
        "minutes_sha256",
        "decision",
        "scope",
        "partitions",
        "strategy_version",
        "baseline_id",
        "spec_sha256",
    ],
)
def test_every_field_is_a_required_key_with_no_default(key: str) -> None:
    payload = complete_payload()
    del payload["decision"][key]
    assert f"decision.{key}" in _problems(payload)


def test_unknown_keys_refused() -> None:
    payload = complete_payload()
    payload["decision"]["signed_by"] = "someone"
    assert "decision.signed_by" in _problems(payload)


@pytest.mark.parametrize(
    ("key", "bad"),
    [
        ("decision_date", "2000-1-1x"),
        ("decision_date", 20000101),
        ("record_kind", "owner"),
        ("record_kind", "MEETING_MINUTES"),
        ("record_kind", ""),
        ("record_kind", None),
        ("minutes_path", ""),
        ("minutes_path", "   "),
        ("minutes_path", " minutes/x.md"),
        ("minutes_path", "/abs/minutes.md"),
        ("minutes_path", "C:/minutes.md"),
        ("minutes_path", "..\\minutes.md"),
        ("minutes_path", "minutes\\x.md"),
        ("minutes_path", "../minutes.md"),
        ("minutes_path", "a/../../minutes.md"),
        ("minutes_path", "a//b.md"),
        ("minutes_path", "./a.md"),
        ("minutes_sha256", "abc"),
        ("minutes_sha256", "A" * 64),
        ("minutes_sha256", None),
        ("decision", "approve"),
        ("decision", "APPROVED"),
        ("decision", ""),
        ("decision", None),
        ("scope", []),
        ("scope", ["review"]),
        ("scope", ["run", "run"]),
        ("scope", "run"),
        ("partitions", ["holdout"]),
        ("partitions", ["HOLDOUT", "HOLDOUT"]),
        ("partitions", [""]),
        ("strategy_version", ""),
        ("strategy_version", "  "),
        ("strategy_version", " V1"),
        ("baseline_id", ""),
        ("baseline_id", None),
        ("spec_sha256", "xyz"),
        ("spec_sha256", "A" * 64),
    ],
)
def test_field_validation(key: str, bad: Any) -> None:
    payload = complete_payload()
    payload["decision"][key] = bad
    assert f"decision.{key}" in _problems(payload)


def test_run_scope_must_name_partitions_and_build_only_must_not() -> None:
    payload = complete_payload()
    payload["decision"]["partitions"] = []
    assert "partitions" in _problems(payload)
    payload = complete_payload()
    payload["decision"]["scope"] = ["build"]  # partitions still listed
    assert "partitions" in _problems(payload)
    payload["decision"]["partitions"] = []
    assert parse_draft(payload).decision.scope == ("build",)  # type: ignore[union-attr]


def test_decision_values_other_than_approved_parse_but_are_data_only() -> None:
    for outcome in ("revise", "defer", "stop"):
        payload = complete_payload()
        payload["decision"]["decision"] = outcome
        assert parse_draft(payload).decision.decision == outcome  # type: ignore[union-attr]


# --- minutes file ---------------------------------------------------------------------------


def test_minutes_file_accepted_when_present_and_hash_matches() -> None:
    check_minutes_file(MINUTES_RELPATH, MINUTES_SHA256)


def test_minutes_file_missing() -> None:
    with pytest.raises(MinutesMissingError):
        check_minutes_file("minutes/none.md", MINUTES_SHA256)


def test_minutes_file_hash_mismatch() -> None:
    with pytest.raises(MinutesMismatchError):
        check_minutes_file(MINUTES_RELPATH, "0" * 64)


@pytest.mark.parametrize(
    "path",
    ["", "/etc/passwd", "../x.md", "a/../x.md", "a//x.md", ".", "C:/x.md", "x\\y.md", "./x.md"],
)
def test_minutes_path_forms_that_could_leave_the_root_are_refused(path: str) -> None:
    with pytest.raises(MinutesMissingError):
        check_minutes_file(path, MINUTES_SHA256)


def test_minutes_symlink_out_of_the_root_refused(tmp_path: Path) -> None:
    outside = tmp_path / "outside.md"
    outside.write_bytes(MINUTES_BYTES)
    root = tmp_path / "root"
    (root / "minutes").mkdir(parents=True)
    make_symlink(root / "minutes" / "link.md", outside)
    decision_module._MINUTES_ROOT = root
    with pytest.raises(MinutesMissingError, match="outside"):
        check_minutes_file("minutes/link.md", MINUTES_SHA256)


def test_minutes_directory_is_not_a_minutes_file(tmp_path: Path) -> None:
    (tmp_path / "minutes" / "d.md").mkdir(parents=True)
    decision_module._MINUTES_ROOT = tmp_path
    with pytest.raises(MinutesMissingError):
        check_minutes_file("minutes/d.md", MINUTES_SHA256)


def test_default_root_is_the_repository_and_any_committed_file_will_do() -> None:
    decision_module._MINUTES_ROOT = None
    root = decision_module._REPO_ROOT
    assert (root / "apps" / "backend" / "app" / "research" / "range002").is_dir()
    target = Path("apps/backend/app/research/range002/__init__.py")
    from app.research.range002.spec.hashing import file_sha256

    check_minutes_file(target.as_posix(), file_sha256(root / target))
    with pytest.raises(MinutesMismatchError):
        check_minutes_file(target.as_posix(), "0" * 64)


def test_minutes_edit_after_the_fact_is_detected(tmp_path: Path) -> None:
    (tmp_path / "minutes").mkdir()
    f = tmp_path / MINUTES_RELPATH
    f.write_bytes(MINUTES_BYTES)
    decision_module._MINUTES_ROOT = tmp_path
    check_minutes_file(MINUTES_RELPATH, MINUTES_SHA256)
    f.write_bytes(MINUTES_BYTES + b"x")
    with pytest.raises(MinutesMismatchError):
        check_minutes_file(MINUTES_RELPATH, MINUTES_SHA256)


# --- nothing invented, nothing legacy ----------------------------------------------------------

_LEGACY = (
    "independent_validator",
    "trading_expert",
    "signoff",
    "economic_thesis",
    "meeting_date",  # renamed decision_date (2026-10-12 owner-instruction record)
)


def test_no_legacy_role_or_signature_identifier_in_the_research_package() -> None:
    root = BACKEND / "app" / "research" / "range002"
    hits = []
    for path in [
        *root.rglob("*.py"),
        BACKEND / "scripts" / "research" / "range002" / "freeze_spec.py",
    ]:
        text = path.read_text(encoding="utf-8").lower()
        hits += [f"{path.name}: {word}" for word in _LEGACY if word in text]
    assert hits == []


def test_no_placeholder_signer_in_the_synthetic_decision_block() -> None:
    block = decision_block()
    assert set(block) == {
        "decision_date",
        "record_kind",
        "minutes_path",
        "minutes_sha256",
        "decision",
        "scope",
        "partitions",
        "strategy_version",
        "baseline_id",
        "spec_sha256",
    }
    text = " ".join(str(v) for v in block.values()).lower()
    assert not re.search(r"owner|expert|validator|signer|signed", text)


def test_governance_block_has_only_the_technical_fields() -> None:
    payload = complete_payload()
    assert set(payload["governance"]) == {"exposure_signed", "registry_genesis_id"}
    for removed in ("roles", "economic_thesis_sha"):
        bad = copy.deepcopy(payload)
        set_path(bad, f"governance.{removed}", None)
        assert f"governance.{removed}" in _problems(bad)
