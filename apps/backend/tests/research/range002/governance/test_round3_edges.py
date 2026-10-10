"""Round-3 edge refusals that keep governance coverage at 100%. Synthetic data only."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.research.range002.governance import errors
from app.research.range002.governance.exposure_ledger import ExposureLedger
from app.research.range002.governance.hashchain import HashChainFile, read_chain
from app.research.range002.governance.model import Partition, Phase
from app.research.range002.governance.results_guard import authorize
from app.research.range002.governance.run_registry import RunRegistry

from .conftest import (
    CODE_SHA,
    MANIFEST_SHA,
    SIGNED_LEDGER,
    SPEC_SHA,
    complete_prereqs,
    make_spec,
    new_registry,
    open_run,
)


def test_ledger_attributes_cannot_be_deleted() -> None:
    led = ExposureLedger.from_text(SIGNED_LEDGER)
    with pytest.raises(AttributeError):
        del led._sha256


def test_non_utf8_chain_is_refused(tmp_path: Path) -> None:
    path = tmp_path / "c.jsonl"
    path.write_bytes(b"\xff\xfe\n")
    with pytest.raises(errors.RegistryIntegrityError, match="UTF-8"):
        read_chain(path)


def test_wrong_schema_in_canonical_form_is_refused(tmp_path: Path) -> None:
    path = tmp_path / "c.jsonl"
    path.write_bytes(b'{"schema":9}\n')
    with pytest.raises(errors.RegistryIntegrityError, match="schema"):
        read_chain(path)


def test_non_evidence_object_in_predecessor_evidence_is_refused(tmp_path: Path) -> None:
    reg = new_registry(tmp_path / "runs.jsonl")
    complete_prereqs(reg, Phase.P3B)
    rid = open_run(reg, Phase.P3B, Partition.DEVELOPMENT_CONFIRMATION)
    with pytest.raises(errors.PredecessorEvidenceMissingError, match="PredecessorEvidence"):
        authorize(
            spec=make_spec(),
            phase=Phase.P3B,
            partition=Partition.DEVELOPMENT_CONFIRMATION,
            run_id=rid,
            registry=reg,
            exposure_ledger=ExposureLedger.from_text(SIGNED_LEDGER),
            predecessor_evidence=["not evidence"],  # type: ignore[list-item]
        )


def test_selection_record_must_be_canonical_json(tmp_path: Path) -> None:
    reg = new_registry(tmp_path / "runs.jsonl")
    rid = open_run(reg)
    with pytest.raises(errors.RegistryRecordError, match="canonical"):
        reg.record_selection(rid, {"x": object()})
    with pytest.raises(errors.RegistryRecordError, match="canonical"):
        reg.record_selection(rid, {"x": float("nan")})


def test_mark_rechecks_the_window_under_the_lock(tmp_path: Path) -> None:
    """Two handles that both passed the pre-check cannot both be marked for one window."""
    a = new_registry(tmp_path / "runs.jsonl")
    b = RunRegistry(tmp_path / "runs.jsonl")
    first = open_run(a, Phase.P4, Partition.HOLDOUT)
    second = open_run(b, Phase.P4, Partition.HOLDOUT)
    a.mark_holdout_authorized(first)
    with pytest.raises(errors.HoldoutAlreadyOpenedError, match="window"):
        b.mark_holdout_authorized(second)  # stale handle: the check runs on the fresh chain


def _raw_open(rid: str, **extra: object) -> dict[str, object]:
    return {
        "run_id": rid,
        "phase": "P4",
        "partition": "HOLDOUT",
        "spec_sha256": SPEC_SHA,
        "code_sha": CODE_SHA,
        "data_manifest_sha256": MANIFEST_SHA,
        "seeds": {"b": 1},
        "exit_candidates": ["E1"],
        "k_exit_candidates": 1,
        **extra,
    }


def test_malformed_recorded_window_is_an_integrity_error(tmp_path: Path) -> None:
    new_registry(tmp_path / "runs.jsonl")
    chain = HashChainFile(tmp_path / "runs.jsonl")
    chain.append("run_opened", _raw_open("r1", holdout_start="2022-01-01"))  # end missing
    with pytest.raises(errors.RegistryIntegrityError, match="holdout window"):
        RunRegistry(tmp_path / "runs.jsonl").runs()


def test_row_for_an_unknown_run_is_an_integrity_error(tmp_path: Path) -> None:
    new_registry(tmp_path / "runs.jsonl")
    chain = HashChainFile(tmp_path / "runs.jsonl")
    chain.append("run_closed", {"run_id": "ghost", "status": "ABORTED", "audit_pack_sha256": None})
    with pytest.raises(errors.RegistryIntegrityError, match="unknown run_id"):
        RunRegistry(tmp_path / "runs.jsonl").runs()
