from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.research.range002.governance.errors import (
    RegistryIntegrityError,
    RegistryNotEnrolledError,
    RegistryRecordError,
    RunNotRegisteredError,
)
from app.research.range002.governance.model import Partition, Phase
from app.research.range002.governance.run_registry import (
    REGISTRY_PUBLIC_API,
    RunRegistry,
    RunStatus,
)

from .conftest import CODE_SHA, MANIFEST_SHA, SPEC_SHA, new_registry, open_run

AUDIT = "d" * 64


def test_open_writes_row_with_identity_fields(registry: RunRegistry) -> None:
    rid = open_run(registry)
    run = registry.get_run(rid)
    assert run is not None
    assert run.status is RunStatus.OPEN
    assert (run.spec_sha256, run.code_sha, run.data_manifest_sha256) == (
        SPEC_SHA,
        CODE_SHA,
        MANIFEST_SHA,
    )
    assert run.partition is Partition.DEVELOPMENT_SELECTION
    assert dict(run.seeds) == {"bootstrap": 1}
    assert run.exit_candidates == ("E1", "E2a")
    rec = registry.records()[1]  # [0] is the registry_genesis row
    assert rec.payload["k_exit_candidates"] == 2


def test_run_ids_are_deterministic_and_sequential(tmp_path: Path) -> None:
    ids = []
    for name in ("a", "b"):
        reg = new_registry(tmp_path / name / "runs.jsonl")
        ids.append([open_run(reg), open_run(reg)])
    assert ids[0] == ids[1] == ["range002-run-000002", "range002-run-000003"]  # 000001 = genesis


def test_open_close_lifecycle(registry: RunRegistry) -> None:
    rid = open_run(registry)
    registry.mark_capability_issued(rid, attempt_limit=9)  # stands in for authorize()
    registry.close_run(rid, RunStatus.COMPLETED, AUDIT)
    run = registry.get_run(rid)
    assert run is not None and run.status is RunStatus.COMPLETED
    assert run.audit_pack_sha256 == AUDIT
    with pytest.raises(RegistryRecordError, match="already"):
        registry.close_run(rid, RunStatus.FAILED, None)


def test_completed_requires_audit_pack_hash(registry: RunRegistry) -> None:
    rid = open_run(registry)
    registry.mark_capability_issued(rid, attempt_limit=9)
    with pytest.raises(RegistryRecordError):
        registry.close_run(rid, RunStatus.COMPLETED, None)
    with pytest.raises(RegistryRecordError):
        registry.close_run(rid, RunStatus.COMPLETED, "not-hex")
    registry.close_run(rid, RunStatus.FAILED, None)  # failed runs may lack a pack


def test_cannot_close_with_open_or_unknown_run(registry: RunRegistry) -> None:
    rid = open_run(registry)
    with pytest.raises(RegistryRecordError):
        registry.close_run(rid, RunStatus.OPEN, None)
    with pytest.raises(RunNotRegisteredError):
        registry.close_run("nope", RunStatus.FAILED, None)


def test_crash_leaves_open_then_aborted_and_still_counts(
    registry: RunRegistry, tmp_path: Path
) -> None:
    rid = open_run(registry)
    # "crash": process dies; a fresh process reopens the registry
    reopened = RunRegistry(registry.path)
    run = reopened.get_run(rid)
    assert run is not None and run.status is RunStatus.OPEN
    assert reopened.abort_open_runs() == (rid,)
    run = reopened.get_run(rid)
    assert run is not None and run.status is RunStatus.ABORTED
    assert reopened.count_runs() == 1
    assert reopened.count_runs(SPEC_SHA) == 1
    assert reopened.count_runs("e" * 64) == 0
    assert reopened.abort_open_runs() == ()  # idempotent


def test_all_terminal_statuses_count(registry: RunRegistry) -> None:
    for i, status in enumerate((RunStatus.COMPLETED, RunStatus.FAILED, RunStatus.DEFECT)):
        rid = open_run(registry)
        registry.mark_capability_issued(rid, attempt_limit=9)
        registry.close_run(rid, status, f"{i}" * 64)
    open_run(registry)
    assert registry.count_runs() == 4


@pytest.mark.parametrize(
    "kwargs",
    [
        {"spec_sha256": "short"},
        {"code_sha": "ZZ"},
        {"data_manifest_sha256": "1" * 10},
        {"seeds": {}},
        {"seeds": {"a": True}},
        {"seeds": {"a": 1.5}},
        {"seeds": None},
        {"exit_candidates": "E1"},
        {"exit_candidates": [""]},
    ],
)
def test_open_validates_inputs(registry: RunRegistry, kwargs: dict) -> None:
    base: dict = {
        "phase": Phase.P3A,
        "spec_sha256": SPEC_SHA,
        "code_sha": CODE_SHA,
        "data_manifest_sha256": MANIFEST_SHA,
        "partition": Partition.DEVELOPMENT_SELECTION,
        "seeds": {"s": 1},
        "exit_candidates": ["E1"],
    }
    base.update(kwargs)
    with pytest.raises(RegistryRecordError):
        registry.open_run(**base)
    assert registry.count_records() == 1  # only the genesis row: nothing written on refusal


def test_open_rejects_partition_not_valid_for_phase(registry: RunRegistry) -> None:
    with pytest.raises(RegistryRecordError, match="not valid for phase"):
        open_run(registry, Phase.P3A, Partition.HOLDOUT)


def test_find_open_run_mismatches(registry: RunRegistry) -> None:
    rid = open_run(registry)
    ok = {
        "run_id": rid,
        "spec_sha256": SPEC_SHA,
        "phase": Phase.P3A,
        "partition": Partition.DEVELOPMENT_SELECTION,
    }
    assert registry.find_open_run(**ok).run_id == rid  # type: ignore[arg-type]
    with pytest.raises(RunNotRegisteredError):
        registry.find_open_run(**{**ok, "run_id": "missing"})  # type: ignore[arg-type]
    with pytest.raises(RunNotRegisteredError):
        registry.find_open_run(**{**ok, "spec_sha256": "9" * 64})  # type: ignore[arg-type]
    with pytest.raises(RunNotRegisteredError):
        registry.find_open_run(**{**ok, "phase": Phase.P3B})  # type: ignore[arg-type]
    registry.close_run(rid, RunStatus.FAILED, None)
    with pytest.raises(RunNotRegisteredError, match="not OPEN"):
        registry.find_open_run(**ok)  # type: ignore[arg-type]


def test_selection_record_rules(registry: RunRegistry) -> None:
    rid = open_run(registry)
    h = registry.record_selection(rid, {"selected": "E1", "run_id": rid, "spec_sha256": SPEC_SHA})
    assert len(h) == 64
    run = registry.get_run(rid)
    assert run is not None and run.selection_record_seq is not None
    with pytest.raises(RegistryRecordError, match="already"):
        registry.record_selection(rid, {"selected": "E2a", "run_id": rid, "spec_sha256": SPEC_SHA})
    other = open_run(registry, Phase.P3B, Partition.DEVELOPMENT_CONFIRMATION)
    with pytest.raises(RegistryRecordError, match="P3A"):
        registry.record_selection(other, {"x": 1})
    with pytest.raises(RunNotRegisteredError):
        registry.record_selection("nope", {"x": 1})
    third = open_run(registry)
    with pytest.raises(RegistryRecordError, match="empty"):
        registry.record_selection(third, {})
    registry.close_run(third, RunStatus.FAILED, None)
    with pytest.raises(RegistryRecordError, match="not OPEN"):
        registry.record_selection(third, {"x": 1})


# --- tamper detection --------------------------------------------------------


def _lines(path: Path) -> list[str]:
    return path.read_text(encoding="utf-8").splitlines()


def test_edited_record_detected(registry: RunRegistry) -> None:
    open_run(registry)
    open_run(registry)
    lines = _lines(registry.path)
    doc = json.loads(lines[1])  # lines[0] is the genesis row
    doc["payload"]["code_sha"] = "f" * 40
    lines[1] = json.dumps(doc, sort_keys=True, separators=(",", ":"))
    registry.path.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    with pytest.raises(RegistryIntegrityError, match="edited"):
        RunRegistry(registry.path)
    with pytest.raises(RegistryIntegrityError):
        registry.runs()


def test_removed_middle_record_detected(registry: RunRegistry) -> None:
    for _ in range(3):
        open_run(registry)
    lines = _lines(registry.path)
    registry.path.write_text(
        "\n".join([lines[0], lines[1], lines[3]]) + "\n", encoding="utf-8", newline="\n"
    )
    with pytest.raises(RegistryIntegrityError):
        RunRegistry(registry.path)


def test_reordered_records_detected(registry: RunRegistry) -> None:
    for _ in range(2):
        open_run(registry)
    g, a, b = _lines(registry.path)
    registry.path.write_text(f"{g}\n{b}\n{a}\n", encoding="utf-8", newline="\n")
    with pytest.raises(RegistryIntegrityError):
        RunRegistry(registry.path)


def test_rewritten_hash_without_chain_fix_detected(registry: RunRegistry) -> None:
    open_run(registry)
    open_run(registry)
    lines = _lines(registry.path)
    doc = json.loads(lines[1])
    doc["payload"]["seeds"] = {"bootstrap": 2}
    doc.pop("row_hash")
    import hashlib

    doc["row_hash"] = hashlib.sha256(
        json.dumps(doc, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    lines[1] = json.dumps(doc, sort_keys=True, separators=(",", ":"))
    registry.path.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    with pytest.raises(RegistryIntegrityError, match="chains to"):
        RunRegistry(registry.path)


def test_truncated_tail_detected_by_live_handle(registry: RunRegistry) -> None:
    open_run(registry)
    open_run(registry)
    lines = _lines(registry.path)
    registry.path.write_text("\n".join(lines[:2]) + "\n", encoding="utf-8", newline="\n")
    with pytest.raises(RegistryIntegrityError, match="truncated or replaced"):
        registry.runs()
    with pytest.raises(RegistryIntegrityError):
        open_run(registry)


def test_replaced_file_detected(registry: RunRegistry) -> None:
    open_run(registry)
    other = new_registry(registry.path.parent / "elsewhere" / "other.jsonl")
    open_run(other, spec_sha="1" * 64)
    registry.path.write_bytes(other.path.read_bytes())
    with pytest.raises(RegistryIntegrityError):
        registry.runs()


@pytest.mark.parametrize(
    "garbage",
    ["not json\n", "[1,2]\n", '{"schema": 9}\n', '{"schema":1,"seq":1,"prev_hash":"x"}\n'],
)
def test_malformed_lines_fail_closed(tmp_path: Path, garbage: str) -> None:
    p = tmp_path / "bad.jsonl"
    p.write_text(garbage, encoding="utf-8")
    with pytest.raises(RegistryIntegrityError):
        RunRegistry(p)


def test_malformed_kind_or_payload_detected(tmp_path: Path) -> None:
    import hashlib

    body = {
        "schema": 1,
        "seq": 1,
        "kind": 5,
        "recorded_at": "x",
        "prev_hash": "0" * 64,
        "payload": {},
    }
    body["row_hash"] = hashlib.sha256(
        json.dumps(
            {k: v for k, v in body.items() if k != "row_hash"},
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
    ).hexdigest()
    p = tmp_path / "k.jsonl"
    p.write_bytes(json.dumps(body, sort_keys=True, separators=(",", ":")).encode() + b"\n")
    with pytest.raises(RegistryIntegrityError, match="malformed"):
        RunRegistry(p)


def test_concurrent_writer_serialises_without_forking(registry: RunRegistry) -> None:
    """Round 3: a stale handle re-reads under the lock and appends after the other writer."""
    first = open_run(registry)
    second = RunRegistry(registry.path)  # second handle on the same chain
    mid = open_run(second)  # advances the chain
    last = open_run(registry)  # stale view: re-read under the lock, fresh id
    assert len({first, mid, last}) == 3
    assert [r.run_id for r in RunRegistry(registry.path).runs()] == [first, mid, last]


def test_empty_file_is_not_enrolled_and_blank_lines_are_refused(tmp_path: Path) -> None:
    p = tmp_path / "e.jsonl"
    p.write_bytes(b"")
    with pytest.raises(RegistryNotEnrolledError):
        RunRegistry(p)
    assert p.read_bytes() == b""  # opening never writes
    p.write_bytes(b"\n\n")  # round 3: a blank line is an edit, not formatting
    with pytest.raises(RegistryIntegrityError, match="blank"):
        RunRegistry(p)


def test_public_api_is_pinned_and_has_no_delete_path(registry: RunRegistry) -> None:
    public = {n for n in dir(registry) if not n.startswith("_")}
    assert public == REGISTRY_PUBLIC_API
    for banned in ("delete", "remove", "truncate", "rewrite", "update", "clear"):
        assert not hasattr(registry, banned)


def test_head_hash_changes_on_append(registry: RunRegistry) -> None:
    h0 = registry.head_hash
    open_run(registry)
    assert registry.head_hash != h0
