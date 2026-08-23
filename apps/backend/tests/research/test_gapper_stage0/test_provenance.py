"""Provenance: stamp construction, validation, write-class discipline."""

from __future__ import annotations

import pytest

from app.research.gapper_stage0 import __version__
from app.research.gapper_stage0.provenance import (
    HARNESS_WRITE_CLASS,
    WRITE_CLASSES,
    ProvenanceError,
    make_provenance,
    stamp,
    validate_provenance,
)


def _prov(**overrides: str) -> dict[str, str]:
    base = dict(
        created_at="2026-08-17T12:00:00+00:00",
        source_artifact="docs/design/Gapper/GAPPER_Research_Design_v2_1_1.docx",
        source_sha256="2706c4dc406ac19350781db180c315c7f9f38f4c1c8ba9fe8466e9658873d73d",
        run_id="abc123",
    )
    base.update(overrides)
    return make_provenance(**base)  # type: ignore[arg-type]


def test_write_class_vocabulary_and_harness_class() -> None:
    assert {"collection", "reconstruction", "backfill", "repair", "manual"} == WRITE_CLASSES
    assert HARNESS_WRITE_CLASS == "reconstruction"


def test_make_provenance_defaults() -> None:
    p = _prov()
    assert p["write_class"] == "reconstruction"
    assert p["code_version"] == __version__


def test_make_provenance_rejects_unknown_write_class_and_empty_fields() -> None:
    with pytest.raises(ProvenanceError, match="write_class"):
        make_provenance(
            created_at="t",
            source_artifact="a",
            source_sha256="s",
            run_id="r",
            write_class="vibes",
        )
    with pytest.raises(ProvenanceError, match="non-empty"):
        make_provenance(created_at="", source_artifact="a", source_sha256="s", run_id="r")


def test_stamp_and_validate_round_trip() -> None:
    out = stamp({"schema": "x", "value": 1}, _prov())
    validate_provenance(out)  # no raise
    assert out["value"] == 1


def test_unstamped_output_is_invalid() -> None:
    with pytest.raises(ProvenanceError, match="unstamped"):
        validate_provenance({"schema": "x"})


def test_incomplete_stamp_is_invalid() -> None:
    out = stamp({}, _prov())
    del out["provenance"]["run_id"]
    with pytest.raises(ProvenanceError, match="run_id"):
        validate_provenance(out)


def test_wrong_write_class_for_harness_output_is_invalid() -> None:
    # 'collection' is a legal class generally but not for a harness output.
    out = stamp({}, _prov(write_class="collection"))
    with pytest.raises(ProvenanceError, match="reconstruction"):
        validate_provenance(out)


def test_stamp_does_not_mutate_the_original() -> None:
    original: dict = {"a": 1}
    stamped = stamp(original, _prov())
    assert "provenance" not in original
    assert "provenance" in stamped
