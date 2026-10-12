"""Relayed-decision checker on SYNTHETIC records and files. No real person's decision is used."""

from __future__ import annotations

import hashlib
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[4] / "scripts" / "research" / "range002"
sys.path.insert(0, str(SCRIPTS))
import relayed_decision_check as rdc  # noqa: E402

MESSAGE = "已阅读该文件。我的结论：有条件同意。条件：先补充试验账本条目。"
ARTIFACT = b"worksheet v0.1 synthetic bytes\n"


def sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


@pytest.fixture
def root(tmp_path: Path) -> Path:
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "worksheet.md").write_bytes(ARTIFACT)
    (tmp_path / "docs" / "msg.txt").write_text(MESSAGE, encoding="utf-8")
    return tmp_path


def record(**over: object) -> dict:  # type: ignore[type-arg]
    r = {
        "record_type": rdc.RECORD_TYPE,
        "person": "synthetic-reviewer",
        "role": "validator",
        "decision": "CONDITIONAL",
        "conditions": ["先补充试验账本条目"],
        "artifact_path": "docs/worksheet.md",
        "artifact_sha256": sha(ARTIFACT),
        "evidence_path": "docs/msg.txt",
        "evidence_sha256": sha(MESSAGE.encode("utf-8")),
        "evidence_kind": "original_message_export",
        "verbatim_text": "我的结论：有条件同意。",
        "translation": {
            "label": "owner translation",
            "text": "My conclusion: conditional approval.",
        },
        "date_received": "2000-01-01",
        "channel": "email",
        "relayed_by": "owner",
    }
    r.update(over)
    return r


def ev(root: Path, rec: dict, merged: bool = True) -> rdc.Result:  # type: ignore[type-arg]
    return rdc.evaluate(rec, repo_root=root, pr740_merged=merged)


def test_a_complete_record_is_genuine_only_after_740_is_merged(root: Path) -> None:
    ok = ev(root, record(), merged=True)
    assert ok.status == rdc.GENUINE and ok.counts_as_genuine and not ok.hard_fail
    waiting = ev(root, record(), merged=False)
    assert waiting.status == rdc.VERIFIED_PENDING_740 and not waiting.counts_as_genuine


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("同意", {"APPROVE"}),
        ("不同意", {"REJECT"}),  # must not also read as plain 同意
        ("有条件同意", {"CONDITIONAL"}),
        ("我同意，但是不同意第三条", {"APPROVE", "REJECT"}),
        ("I approve with conditions", {"CONDITIONAL"}),
        ("I do not approve", {"REJECT"}),
        ("I approve", {"APPROVE"}),
        ("看过了", set()),
    ],
)
def test_conclusion_detection_never_reads_a_longer_form_as_a_shorter_one(
    text: str, expected: set
) -> None:  # type: ignore[type-arg]
    assert rdc.detect_conclusions(text) == expected


def test_missing_or_tampered_evidence_is_invalid_and_a_hard_fail_for_the_validator(
    root: Path,
) -> None:
    gone = ev(root, record(evidence_path="docs/nope.txt"))
    assert gone.status == rdc.INVALID and gone.hard_fail
    (root / "docs" / "msg.txt").write_text(MESSAGE + " (edited)", encoding="utf-8")
    assert ev(root, record()).status == rdc.INVALID  # hash no longer matches


def test_verbatim_text_absent_from_the_original_is_owner_authored_and_never_genuine(
    root: Path,
) -> None:
    r = ev(root, record(verbatim_text="我完全同意。"))
    assert r.status == rdc.OWNER_AUTHORED_ONLY and not r.counts_as_genuine
    assert r.hard_fail  # validator role: hard fail
    other = ev(root, record(verbatim_text="我完全同意。", role="exit_reviewer"))
    assert other.status == rdc.OWNER_AUTHORED_ONLY and not other.hard_fail


def test_an_owner_authored_summary_is_never_genuine(root: Path) -> None:
    r = ev(root, record(evidence_kind="owner_authored_summary"))
    assert r.status == rdc.OWNER_AUTHORED_ONLY and r.hard_fail


def test_a_stale_artifact_sha_is_stale(root: Path) -> None:
    (root / "docs" / "worksheet.md").write_bytes(ARTIFACT + b"one more line\n")
    r = ev(root, record())
    assert r.status == rdc.STALE and not r.counts_as_genuine


def test_a_decision_that_conflicts_with_the_text_is_flagged_never_inferred(root: Path) -> None:
    r = ev(root, record(decision="APPROVE", conditions=None))
    assert r.status == rdc.NEEDS_OWNER and "conflicts" in r.reasons[0]
    (root / "docs" / "msg.txt").write_text("已阅读。", encoding="utf-8")
    both = record(
        evidence_sha256=sha("已阅读。".encode()), verbatim_text="已阅读。", decision="APPROVE"
    )
    assert ev(root, both).status == rdc.NEEDS_OWNER  # no explicit conclusion at all


def test_binary_evidence_cannot_be_verified_and_is_not_genuine(root: Path) -> None:
    blob = bytes([0xFF, 0xFE, 0x00, 0x81, 0x80])
    (root / "docs" / "shot.png").write_bytes(blob)
    r = ev(
        root,
        record(
            evidence_path="docs/shot.png", evidence_sha256=sha(blob), evidence_kind="screenshot"
        ),
    )
    assert r.status == rdc.NEEDS_OWNER and r.hard_fail


@pytest.mark.parametrize(
    "mutation",
    [
        {"relayed_by": "someone-else"},
        {"role": "liaison"},
        {"decision": "MAYBE"},
        {"conditions": []},
        {"translation": {"label": "official translation", "text": "x"}},
        {"artifact_sha256": "abc"},
        {"verbatim_text": "  "},
        {"evidence_path": "../outside.txt"},
    ],
)
def test_structural_defects_are_invalid(root: Path, mutation: dict) -> None:  # type: ignore[type-arg]
    assert ev(root, record(**mutation)).status == rdc.INVALID


def test_a_path_that_escapes_the_repository_is_refused(root: Path, tmp_path: Path) -> None:
    outside = tmp_path.parent / "outside_evidence.txt"
    outside.write_text(MESSAGE, encoding="utf-8")
    rel = "../" + outside.name
    r = ev(root, record(evidence_path=rel, evidence_sha256=sha(MESSAGE.encode())))
    assert r.status == rdc.INVALID


def test_the_cli_returns_nonzero_unless_genuine(root: Path, tmp_path: Path, capsys) -> None:  # type: ignore[no-untyped-def]
    import json

    p = tmp_path / "rec.json"
    p.write_text(json.dumps(record()), encoding="utf-8")
    assert rdc.main(["x", str(p), "--repo-root", str(root)]) == 1  # #740 not merged
    assert "VERIFIED_PENDING_740" in capsys.readouterr().out
    assert rdc.main(["x", str(p), "--repo-root", str(root), "--pr740-merged"]) == 0
