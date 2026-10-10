"""Round 5: direct tests of the pre-write verifier and a few small guards (named refusals,
no write)."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.research.range002.governance import errors, hashchain, run_registry
from app.research.range002.governance.model import Partition, Phase
from app.research.range002.governance.run_registry import RunRegistry


def _registry(tmp_path: Path) -> RunRegistry:
    return RunRegistry.enroll_new(tmp_path / "runs.jsonl", enrolled_by="synthetic-test-owner")


def test_pre_write_verifier_rejects_oversize_unparseable_and_inconsistent_lines() -> None:
    draft = hashchain.ChainRecord(1, "k", "t", {"a": 1}, "0" * 64, "")
    rec = hashchain.ChainRecord(1, "k", "t", {"a": 1}, "0" * 64, hashchain._row_hash(draft.body()))
    line = hashchain._line(rec.as_dict()) + "\n"
    hashchain._verify_line_round_trips(line, rec)  # the honest line passes
    with pytest.raises(errors.RegistryPayloadError, match="exceeds"):
        hashchain._verify_line_round_trips("x" * (hashchain.MAX_RECORD_BYTES + 1), rec)
    with pytest.raises(errors.RegistryPayloadError, match="strict reader"):
        hashchain._verify_line_round_trips('{"v": NaN}\n', rec)
    other = hashchain.ChainRecord(1, "k", "t", {"a": 1}, "0" * 64, "e" * 64)
    with pytest.raises(errors.RegistryPayloadError, match="round-trip"):
        hashchain._verify_line_round_trips(line, other)
    with pytest.raises(errors.RegistryPayloadError, match="round-trip"):
        hashchain._verify_line_round_trips("[1]\n", rec)


def test_attempts_consumed_for_an_unknown_run_is_a_named_refusal(tmp_path: Path) -> None:
    reg = _registry(tmp_path)
    with pytest.raises(errors.RunNotRegisteredError):
        reg.attempts_consumed("range002-run-999999")


def test_oversized_selection_record_is_refused_before_writing(tmp_path: Path) -> None:
    from datetime import date

    from app.research.range002.governance.model import DateRange

    reg = _registry(tmp_path)
    rid = reg.open_run(
        phase=Phase.P3A,
        spec_sha256="1" * 64,
        code_sha="b" * 40,
        data_manifest_sha256="c" * 64,
        partition=Partition.DEVELOPMENT_SELECTION,
        seeds={"s": 1},
        exit_candidates=["E1"],
        protected_range=DateRange(date(2016, 1, 1), date(2019, 12, 31)),
    )
    before = reg.path.read_bytes()
    with pytest.raises(errors.RegistryRecordError, match="too large"):
        reg.record_selection(
            rid, {"run_id": rid, "spec_sha256": "1" * 64, "blob": "x" * (600 * 1024)}
        )
    assert reg.path.read_bytes() == before


def test_other_registry_scan_of_a_missing_directory_is_none(tmp_path: Path) -> None:
    assert run_registry._other_registry_in(tmp_path / "does-not-exist") is None
