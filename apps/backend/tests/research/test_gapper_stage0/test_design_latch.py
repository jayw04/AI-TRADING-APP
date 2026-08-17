"""Design latch: match / mismatch / superseded / missing, and frozen constants."""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from app.research.gapper_stage0 import design_latch
from app.research.gapper_stage0.design_latch import (
    APPROVED_DESIGN_SHA256,
    SUPERSEDED_SHA256,
    DesignArtifactMissingError,
    DesignHashMismatchError,
    SupersededDesignError,
    latch_design,
    sha256_of_file,
)


def test_frozen_constants_are_the_approval_record_values() -> None:
    # Freeze test: these are the approval identity anchor (record v1.0) —
    # changing either requires a NEW owner approval record, not a code edit.
    assert (
        APPROVED_DESIGN_SHA256 == "2706c4dc406ac19350781db180c315c7f9f38f4c1c8ba9fe8466e9658873d73d"
    )
    assert SUPERSEDED_SHA256 == "84913de09363bb52786d6ca93917920239533d889e4651c90f8004c07d08e993"
    assert APPROVED_DESIGN_SHA256 != SUPERSEDED_SHA256


def test_sha256_of_file(tmp_path: Path) -> None:
    p = tmp_path / "x.bin"
    p.write_bytes(b"gapper stage0")
    assert sha256_of_file(p) == hashlib.sha256(b"gapper stage0").hexdigest()


def test_missing_artifact_is_a_distinct_clear_error(tmp_path: Path) -> None:
    with pytest.raises(DesignArtifactMissingError, match="design artifact not present"):
        latch_design(tmp_path / "nope.docx")


def test_mismatch_rejected(tmp_path: Path) -> None:
    p = tmp_path / "design.docx"
    p.write_bytes(b"some other bytes entirely")
    with pytest.raises(DesignHashMismatchError, match="not the approved"):
        latch_design(p)


def test_superseded_hard_rejected_distinctly(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Mechanism test: a file hashing to the superseded constant must raise the
    # DISTINCT superseded error, not the generic mismatch. We cannot fabricate
    # bytes with the real superseded hash, so the constant is pointed at this
    # file's hash to exercise the code path.
    p = tmp_path / "design.docx"
    p.write_bytes(b"round-2 superseded artifact")
    monkeypatch.setattr(design_latch, "SUPERSEDED_SHA256", sha256_of_file(p))
    with pytest.raises(SupersededDesignError, match="SUPERSEDED"):
        latch_design(p)


def test_match_returns_digest(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # Mechanism test for the accept path (same substitution rationale as above).
    p = tmp_path / "design.docx"
    p.write_bytes(b"approved artifact bytes")
    digest = sha256_of_file(p)
    monkeypatch.setattr(design_latch, "APPROVED_DESIGN_SHA256", digest)
    assert latch_design(p) == digest
