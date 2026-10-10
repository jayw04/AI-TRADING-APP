"""Round-4 governance hardening (Level 1 only: accidental misuse, casual bypass, crashes,
concurrency, wrong paths). Synthetic data only.

Level 2 (signed approvals, an execution boundary, external anchoring) is design-only; nothing
here claims otherwise. Each section is one review item (N1 ... N8).
"""

from __future__ import annotations

import gc
import hashlib
import json
import os
from datetime import date
from pathlib import Path
from typing import Any

import pytest

from app.research.range002.governance import errors, run_registry
from app.research.range002.governance import results_guard as rg
from app.research.range002.governance.evidence import (
    AUDIT_PACK_FORMAT,
    audit_pack_header,
    parse_audit_pack_header,
)
from app.research.range002.governance.exposure_ledger import ExposureLedger
from app.research.range002.governance.hashchain import HashChainFile
from app.research.range002.governance.holdout_token import HoldoutTokenStore, TokenState
from app.research.range002.governance.model import DateRange, Partition, Phase
from app.research.range002.governance.results_guard import (
    PredecessorEvidence,
    _check_phase_order,
    authorize,
    require_capability,
)
from app.research.range002.governance.run_registry import (
    RunRegistry,
    RunStatus,
    holdout_conflict,
)
from app.research.range002.spec.genesis import is_canonical_uuid4
from app.research.range002.spec.hashing import content_sha256
from app.research.range002.spec.manifest import load_manifest
from tests.research.range002.spec._fixtures import SYNTH_MANIFEST_PATH  # noqa: E402

from .conftest import (
    CODE_SHA,
    MANIFEST_SHA,
    SPEC_SHA,
    SYNTH_GENESIS_ID,
    complete_prereqs,
    complete_run,
    evidence_for,
    forge_guard_view,
    issue_token,
    make_spec,
    new_registry,
    open_run,
    use_manifest,
)

LEDGER = ExposureLedger.from_text(
    json.dumps(
        {
            "schema_version": 1,
            "signoff": {"signed_by": "synthetic-owner", "signed_on": "2026-10-01"},
            "entries": [
                {
                    "id": "syn-rng001-window",
                    "start": "2026-01-02",
                    "end": "2026-06-12",
                    "description": "synthetic entry",
                    "source": "synthetic",
                    "observed_by": "synthetic",
                }
            ],
        }
    )
)
OTHER_GENESIS = "9a9a9a9a-9a9a-4a9a-9a9a-9a9a9a9a9a9a"


def auth(
    spec: Any, reg: RunRegistry, phase: Phase, partition: Partition, rid: str, **kw: Any
) -> rg.ResultsCapability:
    kw.setdefault("predecessor_evidence", evidence_for(reg))
    return authorize(
        spec=spec,
        phase=phase,
        partition=partition,
        run_id=rid,
        registry=reg,
        exposure_ledger=LEDGER,
        **kw,
    )


def p3a_cap(reg: RunRegistry, spec: Any = None) -> tuple[str, rg.ResultsCapability]:
    rid = open_run(reg)
    return rid, auth(spec or make_spec(), reg, Phase.P3A, Partition.DEVELOPMENT_SELECTION, rid)


# =============================================================================================
# N3 -- independence_authorization is refused first, always, before any state is touched
# =============================================================================================


def test_n3_independence_authorization_refused_even_with_no_conflict(tmp_path: Path) -> None:
    reg = new_registry(tmp_path / "runs.jsonl")
    store = HoldoutTokenStore(tmp_path / "tokens")
    complete_prereqs(reg, Phase.P4)
    rid = open_run(reg, Phase.P4, Partition.HOLDOUT)
    token = issue_token(store)
    records_before, head_before = reg.count_records(), reg.head_hash
    assert holdout_conflict(reg.runs(), reg.get_run(rid)) is None  # no conflict exists
    with pytest.raises(errors.IndependenceAuthorizationNotAcceptedError):
        auth(
            make_spec(),
            reg,
            Phase.P4,
            Partition.HOLDOUT,
            rid,
            holdout_store=store,
            holdout_token=token,
            independence_authorization="OWNER-APPROVAL",
        )
    # nothing written, token unburned, run still unauthorized
    assert (reg.count_records(), reg.head_hash) == (records_before, head_before)
    assert store.state(SPEC_SHA) is TokenState.ISSUED
    run = reg.get_run(rid)
    assert run is not None and run.holdout_authorized_seq is None
    assert run.capability_issued_seq is None
    # and without the argument the very same call succeeds (the token really was unburned)
    cap = auth(
        make_spec(), reg, Phase.P4, Partition.HOLDOUT, rid, holdout_store=store, holdout_token=token
    )
    assert cap.partition is Partition.HOLDOUT


def test_n3_independence_authorization_refused_before_spec_checks(tmp_path: Path) -> None:
    """It is the very first check: a bad spec does not get to mask it."""
    reg = new_registry(tmp_path / "runs.jsonl")
    with pytest.raises(errors.IndependenceAuthorizationNotAcceptedError):
        authorize(
            spec=object(),  # type: ignore[arg-type]
            phase=Phase.P3A,
            partition=Partition.DEVELOPMENT_SELECTION,
            run_id="x",
            registry=reg,
            exposure_ledger=LEDGER,
            independence_authorization="anything",
        )


# =============================================================================================
# N1 -- registry genesis identity
# =============================================================================================


def test_n1_opening_a_missing_registry_fails_closed_and_creates_nothing(tmp_path: Path) -> None:
    path = tmp_path / "sub" / "runs.jsonl"
    with pytest.raises(errors.RegistryNotEnrolledError):
        RunRegistry(path)
    assert not path.exists() and not path.parent.exists()  # not even the directory


def test_n1_opening_an_empty_registry_fails_closed_and_writes_nothing(tmp_path: Path) -> None:
    path = tmp_path / "runs.jsonl"
    path.write_bytes(b"")
    with pytest.raises(errors.RegistryNotEnrolledError):
        RunRegistry(path)
    assert path.read_bytes() == b""


def test_n1_a_chain_whose_first_row_is_not_a_genesis_is_not_enrolled(tmp_path: Path) -> None:
    path = tmp_path / "runs.jsonl"
    HashChainFile(path).append("run_opened", {"run_id": "r1"})
    with pytest.raises(errors.RegistryNotEnrolledError):
        RunRegistry(path)


@pytest.mark.parametrize(
    "payload",
    [
        {"marker": "wrong", "genesis_id": "a" * 32, "enrollment": {}},
        {"marker": run_registry.REGISTRY_MARKER, "genesis_id": "short", "enrollment": {}},
        {"marker": run_registry.REGISTRY_MARKER, "genesis_id": "a" * 32, "enrollment": "x"},
        {
            "marker": run_registry.REGISTRY_MARKER,
            "genesis_id": "a" * 32,
            "enrollment": {"enrolled_by": 1, "enrolled_at_utc": "t"},
        },
        {
            "marker": run_registry.REGISTRY_MARKER,
            "genesis_id": "a" * 32,
            "enrollment": {"enrolled_by": "o", "enrolled_at_utc": None},
        },
    ],
)
def test_n1_a_malformed_genesis_row_is_an_integrity_error(
    tmp_path: Path, payload: dict[str, Any]
) -> None:
    path = tmp_path / "runs.jsonl"
    HashChainFile(path).append(run_registry.KIND_GENESIS, payload)
    with pytest.raises(errors.RegistryIntegrityError, match="malformed"):
        RunRegistry(path)


def test_n1_enroll_new_creates_a_uuid4_genesis_with_an_enrollment_record(
    tmp_path: Path,
) -> None:
    a = RunRegistry.enroll_new(tmp_path / "a" / "runs.jsonl", enrolled_by="  Jay (typed)  ")
    b = RunRegistry.enroll_new(tmp_path / "b" / "runs.jsonl", enrolled_by="Jay")
    assert is_canonical_uuid4(a.genesis_id) and is_canonical_uuid4(b.genesis_id)
    assert a.genesis_id != b.genesis_id  # random, not derived from anything shared
    enrollment = a.enrollment
    assert enrollment["enrolled_by"] == "Jay (typed)"
    assert enrollment["authenticated"] is False  # free text, unauthenticated
    assert enrollment["enrolled_at_utc"].endswith("+00:00")
    assert RunRegistry(a.path).genesis_id == a.genesis_id  # reopening keeps the identity
    assert a.records()[0].kind == run_registry.KIND_GENESIS and a.count_runs() == 0


def test_n1_enroll_new_refuses_an_existing_file_even_an_empty_one(tmp_path: Path) -> None:
    path = tmp_path / "runs.jsonl"
    path.write_bytes(b"")
    with pytest.raises(errors.RegistryEnrollmentError, match="already exists"):
        RunRegistry.enroll_new(path, enrolled_by="Jay")
    assert path.read_bytes() == b""
    real = new_registry(tmp_path / "real" / "runs.jsonl")
    before = real.path.read_bytes()
    with pytest.raises(errors.RegistryEnrollmentError):
        RunRegistry.enroll_new(real.path, enrolled_by="Jay")  # no overwrite of a live registry
    assert real.path.read_bytes() == before


@pytest.mark.parametrize("who", ["", "   ", None, 7])
def test_n1_enroll_new_requires_an_enrolled_by_text(tmp_path: Path, who: Any) -> None:
    with pytest.raises(errors.RegistryEnrollmentError):
        RunRegistry.enroll_new(tmp_path / "runs.jsonl", enrolled_by=who)
    assert not (tmp_path / "runs.jsonl").exists()


def test_n1_enroll_new_refuses_a_directory_that_already_holds_a_registry(tmp_path: Path) -> None:
    first = new_registry(tmp_path / "runs.jsonl")
    with pytest.raises(errors.RegistryEnrollmentError, match="already contains"):
        RunRegistry.enroll_new(tmp_path / "replacement.jsonl", enrolled_by="Jay")
    assert not (tmp_path / "replacement.jsonl").exists()
    # the marker is content, not a file name: a renamed registry still blocks
    first.path.rename(tmp_path / "renamed.bin")
    with pytest.raises(errors.RegistryEnrollmentError, match="renamed.bin"):
        RunRegistry.enroll_new(tmp_path / "runs.jsonl", enrolled_by="Jay")


def test_n1_directory_scan_ignores_files_that_are_not_registries(tmp_path: Path) -> None:
    (tmp_path / "notes.txt").write_text("hello\n", encoding="utf-8")
    (tmp_path / "data.json").write_text('{"kind": "registry_genesis"}\n', encoding="utf-8")
    (tmp_path / "list.json").write_text("[1, 2]\n", encoding="utf-8")
    (tmp_path / "binary.bin").write_bytes(b"\xff\xfe\x00\x01")
    (tmp_path / "subdir").mkdir()
    reg = RunRegistry.enroll_new(tmp_path / "runs.jsonl", enrolled_by="Jay")
    assert reg.genesis_id


def test_n1_enroll_new_lost_race_for_the_file_name_is_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    real_open = os.open

    def boom(path: Any, *a: Any, **k: Any) -> int:
        if Path(path).name == "runs.jsonl":  # only the registry file; the namespace lock opens
            raise FileExistsError("raced")
        return real_open(path, *a, **k)

    monkeypatch.setattr(run_registry.os, "open", boom)
    with pytest.raises(errors.RegistryEnrollmentError, match="concurrently"):
        RunRegistry.enroll_new(tmp_path / "runs.jsonl", enrolled_by="Jay")


def test_n1_a_failed_genesis_append_leaves_no_half_enrolled_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def boom(self: HashChainFile, *_a: Any, **_k: Any) -> None:
        raise errors.RegistryIntegrityError("synthetic lock timeout")

    monkeypatch.setattr(HashChainFile, "append", boom)
    path = tmp_path / "runs.jsonl"
    with pytest.raises(errors.RegistryIntegrityError):
        RunRegistry.enroll_new(path, enrolled_by="Jay")
    assert not path.exists()


def test_n1_a_second_genesis_row_is_an_integrity_error(tmp_path: Path) -> None:
    reg = new_registry(tmp_path / "runs.jsonl")
    HashChainFile(reg.path).append(run_registry.KIND_GENESIS, dict(reg.records()[0].payload))
    with pytest.raises(errors.RegistryIntegrityError, match="second registry_genesis"):
        reg.runs()


def test_n1_authorize_refuses_a_spec_that_names_another_registry(tmp_path: Path) -> None:
    reg = new_registry(tmp_path / "runs.jsonl")
    rid = open_run(reg)
    count = reg.count_records()
    for genesis in (OTHER_GENESIS, None):
        spec = forge_guard_view(registry_genesis_id=genesis)
        with pytest.raises(errors.RegistryGenesisMismatchError):
            auth(spec, reg, Phase.P3A, Partition.DEVELOPMENT_SELECTION, rid)
    assert reg.count_records() == count  # a refusal writes nothing


@pytest.mark.parametrize(
    ("phase", "partition"),
    [
        (Phase.P2, Partition.REPLAY_RNG001),
        (Phase.P3A, Partition.DEVELOPMENT_SELECTION),
        (Phase.P3B, Partition.DEVELOPMENT_CONFIRMATION),
        (Phase.P4, Partition.HOLDOUT),
        (Phase.P5, Partition.PAPER),
    ],
)
def test_n1_genesis_is_verified_for_every_partition(
    tmp_path: Path, phase: Phase, partition: Partition
) -> None:
    reg = new_registry(tmp_path / "runs.jsonl")
    rid = open_run(reg, phase, partition)
    with pytest.raises(errors.RegistryGenesisMismatchError):
        auth(
            forge_guard_view(registry_genesis_id=OTHER_GENESIS),
            reg,
            phase,
            partition,
            rid,
            requested_range=DateRange(date(2026, 2, 1), date(2026, 2, 28)),
        )


def test_n1_only_the_registry_the_spec_names_authorizes(tmp_path: Path) -> None:
    """(f) Two registries, one spec: the matching genesis authorizes, the other is refused."""
    right = new_registry(tmp_path / "right" / "runs.jsonl")
    wrong = RunRegistry.enroll_new(tmp_path / "wrong" / "runs.jsonl", enrolled_by="Jay")
    assert right.genesis_id != wrong.genesis_id
    spec = make_spec()
    rid_wrong = open_run(wrong)
    with pytest.raises(errors.RegistryGenesisMismatchError):
        auth(spec, wrong, Phase.P3A, Partition.DEVELOPMENT_SELECTION, rid_wrong)
    rid_right = open_run(right)
    assert auth(spec, right, Phase.P3A, Partition.DEVELOPMENT_SELECTION, rid_right).run_id


def test_n1_a_replacement_registry_is_never_auto_enrolled_and_cannot_authorize(
    tmp_path: Path,
) -> None:
    """(e) The original registry is lost (fresh worktree): nothing creates a replacement, and a
    deliberately re-enrolled one carries a new random genesis the frozen spec does not name."""
    fresh_worktree = tmp_path / "fresh-worktree" / "registry" / "runs.jsonl"
    with pytest.raises(errors.RegistryNotEnrolledError):
        RunRegistry(fresh_worktree)  # nothing to authorize against: constructing it fails
    assert not fresh_worktree.exists()
    replacement = RunRegistry.enroll_new(fresh_worktree, enrolled_by="Jay")
    rid = open_run(replacement)
    with pytest.raises(errors.RegistryGenesisMismatchError):
        auth(make_spec(), replacement, Phase.P3A, Partition.DEVELOPMENT_SELECTION, rid)


def test_n1_a_registry_file_replaced_under_a_live_handle_is_refused(tmp_path: Path) -> None:
    reg = new_registry(tmp_path / "a" / "runs.jsonl")
    rid = open_run(reg)
    other = RunRegistry.enroll_new(tmp_path / "b" / "runs.jsonl", enrolled_by="Jay")
    reg.path.write_bytes(other.path.read_bytes())  # reinitialized under the live handle
    with pytest.raises(errors.RegistryIntegrityError):
        auth(make_spec(), reg, Phase.P3A, Partition.DEVELOPMENT_SELECTION, rid)


def test_n1_token_file_records_the_genesis_and_a_mismatching_pairing_is_refused(
    tmp_path: Path,
) -> None:
    store = HoldoutTokenStore(tmp_path / "tokens")
    token = store.issue(SPEC_SHA, registry_genesis_id=SYNTH_GENESIS_ID)
    stored = json.loads((tmp_path / "tokens" / f"{SPEC_SHA}.token.json").read_text("utf-8"))
    assert stored["registry_genesis_id"] == SYNTH_GENESIS_ID
    with pytest.raises(errors.RegistryGenesisMismatchError):
        store.validate_unused(token, SPEC_SHA, OTHER_GENESIS)  # token vs another registry
    path = tmp_path / "tokens" / f"{SPEC_SHA}.token.json"
    stored["registry_genesis_id"] = OTHER_GENESIS  # the file itself paired with another registry
    path.write_text(json.dumps(stored), encoding="utf-8")
    with pytest.raises(errors.RegistryGenesisMismatchError, match="token store"):
        store.validate_unused(token, SPEC_SHA, SYNTH_GENESIS_ID)


@pytest.mark.parametrize("bad", ["", "xyz", "A" * 32, "a" * 31, None, 5])
def test_n1_token_issue_requires_a_valid_genesis_id(tmp_path: Path, bad: Any) -> None:
    store = HoldoutTokenStore(tmp_path / "tokens")
    with pytest.raises(errors.HoldoutTokenInvalidError):
        store.issue(SPEC_SHA, registry_genesis_id=bad)
    assert store.state(SPEC_SHA) is TokenState.NOT_ISSUED


def test_n1_authorize_refuses_a_token_store_issued_for_another_registry_and_keeps_it(
    tmp_path: Path,
) -> None:
    reg = new_registry(tmp_path / "runs.jsonl")
    store = HoldoutTokenStore(tmp_path / "tokens")
    complete_prereqs(reg, Phase.P4)
    rid = open_run(reg, Phase.P4, Partition.HOLDOUT)
    foreign = store.issue(SPEC_SHA, registry_genesis_id=OTHER_GENESIS)
    with pytest.raises(errors.RegistryGenesisMismatchError):
        auth(
            make_spec(), reg, Phase.P4, Partition.HOLDOUT, rid, holdout_store=store,
            holdout_token=foreign,
        )  # fmt: skip
    run = reg.get_run(rid)
    assert run is not None and run.holdout_authorized_seq is None  # nothing marked
    assert store.state(SPEC_SHA) is TokenState.ISSUED  # token not burned


def test_n1_consume_intent_must_name_the_same_registry(tmp_path: Path) -> None:
    store = HoldoutTokenStore(tmp_path / "tokens")
    token = store.issue(SPEC_SHA, registry_genesis_id=SYNTH_GENESIS_ID)
    store.begin_consume(token, "run-1")
    intent = tmp_path / "tokens" / f"{SPEC_SHA}.intent.json"
    doc = json.loads(intent.read_text("utf-8"))
    assert doc["registry_genesis_id"] == SYNTH_GENESIS_ID
    doc["registry_genesis_id"] = OTHER_GENESIS
    intent.write_text(json.dumps(doc), encoding="utf-8")
    with pytest.raises(errors.HoldoutTokenInvalidError):
        store.commit_consume(token, "run-1")


# =============================================================================================
# N2a -- capability_issued rows; COMPLETED needs one
# =============================================================================================


def test_n2a_close_completed_refuses_a_run_the_guard_never_authorized(tmp_path: Path) -> None:
    reg = new_registry(tmp_path / "runs.jsonl")
    rid = open_run(reg)
    with pytest.raises(errors.CapabilityNotIssuedError):
        reg.close_run(rid, RunStatus.COMPLETED, "a" * 64)
    run = reg.get_run(rid)
    assert run is not None and run.status is RunStatus.OPEN  # nothing was written
    reg.close_run(rid, RunStatus.FAILED, None)  # FAILED / ABORTED / DEFECT need no capability
    assert issubclass(errors.CapabilityNotIssuedError, errors.RegistryRecordError)


def test_n2a_authorize_writes_the_row_before_returning_for_every_partition(
    tmp_path: Path,
) -> None:
    reg = new_registry(tmp_path / "runs.jsonl")
    store = HoldoutTokenStore(tmp_path / "tokens")
    spec = make_spec()

    rid2 = open_run(reg, Phase.P2, Partition.REPLAY_RNG001)
    cap2 = auth(
        spec, reg, Phase.P2, Partition.REPLAY_RNG001, rid2,
        requested_range=DateRange(date(2026, 2, 1), date(2026, 2, 28)),
    )  # fmt: skip
    rid3a, cap3a = p3a_cap(reg)
    complete_run(reg, rid3a, {"selected": "E1"})
    rid3b = open_run(reg, Phase.P3B, Partition.DEVELOPMENT_CONFIRMATION)
    cap3b = auth(spec, reg, Phase.P3B, Partition.DEVELOPMENT_CONFIRMATION, rid3b)
    complete_run(reg, rid3b)
    rid4 = open_run(reg, Phase.P4, Partition.HOLDOUT)
    cap4 = auth(
        spec, reg, Phase.P4, Partition.HOLDOUT, rid4,
        holdout_store=store, holdout_token=issue_token(store),
    )  # fmt: skip
    for cap in (cap2, cap3a, cap3b, cap4):
        run = reg.get_run(cap.run_id)
        assert run is not None and run.capability_issued_seq is not None
        row = next(r for r in reg.records() if r.seq == run.capability_issued_seq)
        assert row.kind == run_registry.KIND_CAPABILITY
        assert row.payload["manifest_sha256"] == load_manifest(SYNTH_MANIFEST_PATH).sha256
        assert dict(row.payload) | {"evidence": None, "manifest_sha256": None} == {
            "run_id": cap.run_id,
            "phase": cap.phase.value,
            "partition": cap.partition.value,
            "spec_sha256": cap.spec_sha256,
            "evidence": None,
            "manifest_sha256": None,
        }
    # the row exists, so closing COMPLETED now works for a guard-authorized run
    complete_run(reg, rid4)


def test_n2a_no_capability_is_returned_if_the_row_cannot_be_written(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    reg = new_registry(tmp_path / "runs.jsonl")
    rid = open_run(reg)

    def boom(self: RunRegistry, *_a: Any, **_k: Any) -> str:
        raise errors.RegistryIntegrityError("synthetic write failure")

    monkeypatch.setattr(RunRegistry, "mark_capability_issued", boom)
    before = len(rg._BOUND_REGISTRIES)
    with pytest.raises(errors.RegistryIntegrityError):
        auth(make_spec(), reg, Phase.P3A, Partition.DEVELOPMENT_SELECTION, rid)
    assert len(rg._BOUND_REGISTRIES) == before  # no capability was bound or returned


def test_n2a_capability_row_requires_an_open_run(tmp_path: Path) -> None:
    reg = new_registry(tmp_path / "runs.jsonl")
    rid = open_run(reg)
    reg.close_run(rid, RunStatus.FAILED, None)
    with pytest.raises(errors.RegistryRecordError, match="not OPEN"):
        reg.mark_capability_issued(rid, attempt_limit=9)
    with pytest.raises(errors.RunNotRegisteredError):
        reg.mark_capability_issued("ghost")


def test_n2a_close_of_an_unknown_run_is_a_named_refusal(tmp_path: Path) -> None:
    reg = new_registry(tmp_path / "runs.jsonl")
    with pytest.raises(errors.RunNotRegisteredError):
        reg.close_run("ghost", RunStatus.FAILED, None)


# =============================================================================================
# N2b -- a P4 predecessor must have been authorized to open the holdout
# =============================================================================================


def test_n2b_a_completed_p4_without_a_holdout_authorization_is_not_a_predecessor(
    tmp_path: Path,
) -> None:
    reg = new_registry(tmp_path / "runs.jsonl")
    complete_prereqs(reg, Phase.P5)  # P4 completed via the guard-less helper: never authorized
    with pytest.raises(errors.PredecessorHoldoutNotAuthorizedError) as ei:
        _check_phase_order(reg, SPEC_SHA, Phase.P5, evidence_for(reg))
    assert isinstance(ei.value, errors.PhaseOrderError)


def test_n2b_an_authorized_completed_p4_satisfies_the_rule_and_is_digest_verified(
    tmp_path: Path,
) -> None:
    reg = new_registry(tmp_path / "runs.jsonl")
    complete_prereqs(reg, Phase.P4)
    p4 = open_run(reg, Phase.P4, Partition.HOLDOUT)
    reg.mark_holdout_authorized(p4)
    complete_run(reg, p4)
    ((run_id, audit, selection),) = _check_phase_order(reg, SPEC_SHA, Phase.P5, evidence_for(reg))
    assert run_id == p4 and selection is None
    pack = reg.path.parent / "evidence" / f"{p4}.audit"
    assert audit == hashlib.sha256(pack.read_bytes()).hexdigest()


# =============================================================================================
# N2c -- evidence is bound to its run; reuse is refused
# =============================================================================================


def test_n2c_audit_pack_header_roundtrip_and_format() -> None:
    line = audit_pack_header("range002-run-000002", SPEC_SHA)
    assert line.endswith(b"\n") and line.count(b"\n") == 1
    assert json.loads(line) == {
        "format": AUDIT_PACK_FORMAT,
        "run_id": "range002-run-000002",
        "spec_sha256": SPEC_SHA,
        "version": 1,
    }
    assert parse_audit_pack_header(line + b"body bytes\nmore") == ("range002-run-000002", SPEC_SHA)


@pytest.mark.parametrize(
    "raw",
    [
        b"no newline at all",
        b"\xff\xfe\n",
        b"not json\n",
        b"[1, 2]\n",
        b'{"format":"x"}\n',
        json.dumps(
            {"format": "wrong", "run_id": "r", "spec_sha256": SPEC_SHA, "version": 1},
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
        + b"\n",
        json.dumps(
            {"format": AUDIT_PACK_FORMAT, "run_id": "r", "spec_sha256": SPEC_SHA, "version": 2},
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
        + b"\n",
        json.dumps(
            {"format": AUDIT_PACK_FORMAT, "run_id": "r", "spec_sha256": SPEC_SHA, "version": True},
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
        + b"\n",
        json.dumps(
            {"format": AUDIT_PACK_FORMAT, "run_id": "", "spec_sha256": SPEC_SHA, "version": 1},
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
        + b"\n",
        json.dumps(
            {"format": AUDIT_PACK_FORMAT, "run_id": 3, "spec_sha256": SPEC_SHA, "version": 1},
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
        + b"\n",
        json.dumps(
            {"format": AUDIT_PACK_FORMAT, "run_id": "r", "spec_sha256": "short", "version": 1},
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
        + b"\n",
        # valid content, non-canonical text (spaces): refused
        json.dumps(
            {"format": AUDIT_PACK_FORMAT, "run_id": "r", "spec_sha256": SPEC_SHA, "version": 1}
        ).encode()
        + b"\n",
    ],
)
def test_n2c_malformed_audit_pack_headers_are_refused(raw: bytes) -> None:
    with pytest.raises(errors.PredecessorEvidenceBindingError):
        parse_audit_pack_header(raw)


@pytest.mark.parametrize(("rid", "sha"), [("", SPEC_SHA), (3, SPEC_SHA), ("r", "short"), ("r", 5)])
def test_n2c_audit_pack_header_builder_validates(rid: Any, sha: Any) -> None:
    with pytest.raises(errors.PredecessorEvidenceBindingError):
        audit_pack_header(rid, sha)


def _p3a_with_pack(reg: RunRegistry, header_run_id: str | None, header_spec: str = SPEC_SHA) -> Any:
    """A P3A run completed with an audit pack whose header names ``header_run_id``."""
    rid = open_run(reg)
    directory = reg.path.parent / "evidence"
    directory.mkdir(exist_ok=True)
    body = {"selected": "E1", "run_id": rid, "spec_sha256": SPEC_SHA}
    reg.record_selection(rid, body)
    sel = directory / f"{rid}.selection.json"
    sel.write_text(json.dumps(body), encoding="utf-8")
    header = b"" if header_run_id is None else audit_pack_header(header_run_id, header_spec)
    pack = header + f"pack body {rid}".encode()
    audit = directory / f"{rid}.audit"
    audit.write_bytes(pack)
    reg.mark_capability_issued(rid, attempt_limit=9)
    reg.close_run(rid, RunStatus.COMPLETED, hashlib.sha256(pack).hexdigest())
    return PredecessorEvidence(rid, audit, sel)


def _p3b_attempt(reg: RunRegistry, evidence: Any) -> rg.ResultsCapability:
    rid = open_run(reg, Phase.P3B, Partition.DEVELOPMENT_CONFIRMATION)
    return auth(
        make_spec(), reg, Phase.P3B, Partition.DEVELOPMENT_CONFIRMATION, rid,
        predecessor_evidence=[evidence],
    )  # fmt: skip


def test_n2c_a_pack_written_for_another_run_is_refused_as_evidence(tmp_path: Path) -> None:
    reg = new_registry(tmp_path / "runs.jsonl")
    other = open_run(reg)  # a different run whose id the header will claim
    evidence = _p3a_with_pack(reg, header_run_id=other)
    with pytest.raises(errors.PredecessorEvidenceBindingError, match="different run id"):
        _p3b_attempt(reg, evidence)
    assert issubclass(
        errors.PredecessorEvidenceBindingError, errors.PredecessorEvidenceMismatchError
    )


def test_n2c_a_pack_written_for_another_spec_is_refused_as_evidence(tmp_path: Path) -> None:
    reg = new_registry(tmp_path / "runs.jsonl")
    rid_guess = f"range002-run-{reg.count_records() + 1:06d}"  # the run id the next open allocates
    evidence = _p3a_with_pack(reg, header_run_id=rid_guess, header_spec="7" * 64)
    assert evidence.run_id == rid_guess
    with pytest.raises(errors.PredecessorEvidenceBindingError):
        _p3b_attempt(reg, evidence)


def test_n2c_a_pack_with_no_header_is_refused_as_evidence(tmp_path: Path) -> None:
    reg = new_registry(tmp_path / "runs.jsonl")
    evidence = _p3a_with_pack(reg, header_run_id=None)
    with pytest.raises(errors.PredecessorEvidenceBindingError):
        _p3b_attempt(reg, evidence)


def test_n2c_a_correctly_bound_pack_is_accepted(tmp_path: Path) -> None:
    reg = new_registry(tmp_path / "runs.jsonl")
    rid_guess = f"range002-run-{reg.count_records() + 1:06d}"
    evidence = _p3a_with_pack(reg, header_run_id=rid_guess)
    assert _p3b_attempt(reg, evidence).phase is Phase.P3B


def test_n2c_second_run_cannot_close_with_an_already_used_audit_pack_digest(
    tmp_path: Path,
) -> None:
    reg = new_registry(tmp_path / "runs.jsonl")
    first, second = open_run(reg), open_run(reg)
    reg.mark_capability_issued(first, attempt_limit=9)
    reg.mark_capability_issued(second, attempt_limit=9)
    reg.close_run(first, RunStatus.COMPLETED, "c" * 64)
    with pytest.raises(errors.EvidenceReuseError, match="reuse"):
        reg.close_run(second, RunStatus.COMPLETED, "c" * 64)
    with pytest.raises(errors.EvidenceReuseError):  # even as a FAILED run's recorded digest
        reg.close_run(second, RunStatus.FAILED, "c" * 64)
    reg.close_run(second, RunStatus.FAILED, None)  # no digest, no reuse
    assert issubclass(errors.EvidenceReuseError, errors.RegistryRecordError)


def test_n2c_selection_record_must_embed_its_own_run_and_spec(tmp_path: Path) -> None:
    reg = new_registry(tmp_path / "runs.jsonl")
    a, b = open_run(reg), open_run(reg)
    for body in (
        {"selected": "E1"},
        {"selected": "E1", "run_id": b, "spec_sha256": SPEC_SHA},
        {"selected": "E1", "run_id": a, "spec_sha256": "7" * 64},
    ):
        with pytest.raises(errors.RegistryRecordError, match="embed"):
            reg.record_selection(a, body)
    reg.record_selection(a, {"selected": "E1", "run_id": a, "spec_sha256": SPEC_SHA})


def test_n2c_selection_record_digest_cannot_be_reused_by_a_second_run(tmp_path: Path) -> None:
    reg = new_registry(tmp_path / "runs.jsonl")
    a, b = open_run(reg), open_run(reg)
    body_b = {"selected": "E1", "run_id": b, "spec_sha256": SPEC_SHA}
    # a forged earlier row (raw chain access, the unit-test stand-in for a copied record)
    # already carries the digest run b's record will have
    HashChainFile(reg.path).append(
        run_registry.KIND_SELECTION,
        {"run_id": a, "record": body_b, "record_sha256": content_sha256(body_b)},
    )
    with pytest.raises(errors.EvidenceReuseError, match="selection record digest"):
        reg.record_selection(b, body_b)


def _raw_selection_run(reg: RunRegistry, body: Any) -> PredecessorEvidence:
    """A COMPLETED P3A whose registry selection digest is that of ``body`` (raw rows), however
    ``body`` relates to the run -- the stand-in for a record copied from somewhere else."""
    rid = open_run(reg)
    directory = reg.path.parent / "evidence"
    directory.mkdir(exist_ok=True)
    HashChainFile(reg.path).append(
        run_registry.KIND_SELECTION,
        {"run_id": rid, "record": {"x": 1}, "record_sha256": content_sha256(body)},
    )
    sel = directory / f"{rid}.selection.json"
    sel.write_text(json.dumps(body), encoding="utf-8")
    pack = audit_pack_header(rid, SPEC_SHA) + b"body"
    audit = directory / f"{rid}.audit"
    audit.write_bytes(pack)
    reg.mark_capability_issued(rid, attempt_limit=9)
    reg.close_run(rid, RunStatus.COMPLETED, hashlib.sha256(pack).hexdigest())
    return PredecessorEvidence(rid, audit, sel)


@pytest.mark.parametrize(
    "make_body",
    [
        lambda rid: {"run_id": "range002-run-999999", "spec_sha256": SPEC_SHA},  # another run
        lambda rid: {"run_id": rid, "spec_sha256": "7" * 64},  # another spec
        lambda rid: [1, 2, 3],  # not an object
    ],
)
def test_n2c_selection_record_content_must_name_the_predecessor(tmp_path: Path, make_body: Any):
    reg = new_registry(tmp_path / "runs.jsonl")
    rid_guess = f"range002-run-{reg.count_records() + 1:06d}"
    evidence = _raw_selection_run(reg, make_body(rid_guess))
    assert evidence.run_id == rid_guess
    with pytest.raises(errors.PredecessorEvidenceBindingError, match="selection record"):
        _p3b_attempt(reg, evidence)


def test_n2c_unparseable_selection_record_is_missing_evidence(tmp_path: Path) -> None:
    reg = new_registry(tmp_path / "runs.jsonl")
    complete_prereqs(reg, Phase.P3B)
    (ev,) = evidence_for(reg)
    assert ev.selection_record_path is not None
    ev.selection_record_path.write_text('{"a": 1, "a": 2}', encoding="utf-8")
    with pytest.raises(errors.PredecessorEvidenceMissingError, match="cannot parse"):
        _p3b_attempt(reg, ev)


# =============================================================================================
# N2d -- the capability records the evidence digests it verified; files are re-read each time
# =============================================================================================


def test_n2d_capability_and_row_record_the_verified_evidence_digests(tmp_path: Path) -> None:
    reg = new_registry(tmp_path / "runs.jsonl")
    complete_prereqs(reg, Phase.P3B)
    (ev,) = evidence_for(reg)
    run = reg.get_run(ev.run_id)
    assert run is not None
    rid = open_run(reg, Phase.P3B, Partition.DEVELOPMENT_CONFIRMATION)
    cap = auth(
        make_spec(), reg, Phase.P3B, Partition.DEVELOPMENT_CONFIRMATION, rid,
        predecessor_evidence=[ev],
    )  # fmt: skip
    assert cap.evidence_digests == (
        (ev.run_id, run.audit_pack_sha256, run.selection_record_sha256),
    )
    crun = reg.get_run(rid)
    assert crun is not None
    row = next(r for r in reg.records() if r.seq == crun.capability_issued_seq)
    assert row.payload["evidence"] == [
        {
            "run_id": ev.run_id,
            "audit_pack_sha256": run.audit_pack_sha256,
            "selection_record_sha256": run.selection_record_sha256,
        }
    ]
    # a phase with no predecessors records none
    _, cap3a = p3a_cap(reg)
    assert cap3a.evidence_digests == ()


def test_n2d_evidence_files_are_reverified_on_every_authorize(tmp_path: Path) -> None:
    reg = new_registry(tmp_path / "runs.jsonl")
    complete_prereqs(reg, Phase.P3B)
    (ev,) = evidence_for(reg)
    first = open_run(reg, Phase.P3B, Partition.DEVELOPMENT_CONFIRMATION)
    auth(
        make_spec(), reg, Phase.P3B, Partition.DEVELOPMENT_CONFIRMATION, first,
        predecessor_evidence=[ev],
    )  # fmt: skip
    ev.audit_pack_path.write_bytes(ev.audit_pack_path.read_bytes() + b" tampered after")
    second = open_run(reg, Phase.P3B, Partition.DEVELOPMENT_CONFIRMATION)
    with pytest.raises(errors.PredecessorEvidenceMismatchError):
        auth(
            make_spec(), reg, Phase.P3B, Partition.DEVELOPMENT_CONFIRMATION, second,
            predecessor_evidence=[ev],
        )  # fmt: skip


def test_n2d_a_predecessor_with_no_capability_row_does_not_count(tmp_path: Path) -> None:
    """COMPLETED rows written without the guard (a raw chain) are not valid predecessors."""
    reg = new_registry(tmp_path / "runs.jsonl")
    rid = open_run(reg)
    HashChainFile(reg.path).append(
        run_registry.KIND_SELECTION,
        {"run_id": rid, "record": {"x": 1}, "record_sha256": "e" * 64},
    )
    HashChainFile(reg.path).append(
        run_registry.KIND_CLOSED,
        {"run_id": rid, "status": "COMPLETED", "audit_pack_sha256": "f" * 64},
    )
    with pytest.raises(errors.PhaseOrderError, match="COMPLETED P3A"):
        _check_phase_order(reg, SPEC_SHA, Phase.P3B, [])


# =============================================================================================
# N2e -- attempt limits
# =============================================================================================


@pytest.mark.parametrize(
    ("phase", "partition", "field"),
    [
        (Phase.P3A, Partition.DEVELOPMENT_SELECTION, "max_p3a_attempts"),
        (Phase.P3B, Partition.DEVELOPMENT_CONFIRMATION, "max_p3b_attempts"),
    ],
)
@pytest.mark.parametrize("bad", [None, 0, -1, True, 2.5, "3"])
def test_n2e_unset_or_invalid_attempt_limit_refuses(
    tmp_path: Path, phase: Phase, partition: Partition, field: str, bad: Any
) -> None:
    reg = new_registry(tmp_path / "runs.jsonl")
    if phase is Phase.P3B:
        complete_prereqs(reg, Phase.P3B)
    rid = open_run(reg, phase, partition)
    count = reg.count_records()
    with pytest.raises(errors.AttemptLimitNotSetError, match=field):
        auth(forge_guard_view(**{field: bad}), reg, phase, partition, rid)
    assert reg.count_records() == count  # nothing written by a refusal


def test_n2e_the_run_after_the_limit_is_refused_whatever_happened_to_earlier_ones(
    tmp_path: Path,
) -> None:
    use_manifest(tmp_path, p3a=2)
    reg = new_registry(tmp_path / "runs.jsonl")
    spec = forge_guard_view(max_p3a_attempts=2)
    first, second, third = open_run(reg), open_run(reg), open_run(reg)
    auth(spec, reg, Phase.P3A, Partition.DEVELOPMENT_SELECTION, first)
    reg.close_run(first, RunStatus.FAILED, None)  # failed AFTER authorization still counts
    auth(spec, reg, Phase.P3A, Partition.DEVELOPMENT_SELECTION, second)
    reg.close_run(second, RunStatus.ABORTED, None)  # aborted AFTER authorization still counts
    count = reg.count_records()
    with pytest.raises(errors.AttemptLimitExceededError, match="exhausted"):
        auth(spec, reg, Phase.P3A, Partition.DEVELOPMENT_SELECTION, third)
    assert reg.count_records() == count  # a refused request consumes and writes nothing
    assert issubclass(errors.AttemptLimitExceededError, errors.AttemptLimitError)


def test_n2e_only_authorization_consumes_an_attempt_not_opening(tmp_path: Path) -> None:
    use_manifest(tmp_path, p3a=2)
    reg = new_registry(tmp_path / "runs.jsonl")
    spec = forge_guard_view(max_p3a_attempts=2)
    runs = [open_run(reg) for _ in range(5)]  # opened, never authorized: consume nothing
    assert reg.attempts_consumed(runs[0]) == 0
    assert auth(spec, reg, Phase.P3A, Partition.DEVELOPMENT_SELECTION, runs[4]).run_id == runs[4]
    assert auth(spec, reg, Phase.P3A, Partition.DEVELOPMENT_SELECTION, runs[1]).run_id == runs[1]
    with pytest.raises(errors.AttemptLimitExceededError):
        auth(spec, reg, Phase.P3A, Partition.DEVELOPMENT_SELECTION, runs[0])


def test_n2e_other_specs_and_disjoint_windows_share_the_budget_other_phases_do_not(
    tmp_path: Path,
) -> None:
    """Round 6 (NF7, owner ruling): REWRITTEN. The round-4/5 rule gave a disjoint protected window
    its own budget; the old assertion (an authorization in a disjoint window does not count) now
    fails. Budgets are per (registry genesis, phase) across ALL windows and spec hashes."""
    use_manifest(tmp_path, p3a=2)
    reg = new_registry(tmp_path / "runs.jsonl")
    spec = forge_guard_view(max_p3a_attempts=2)
    other = open_run(reg, spec_sha="8" * 64)  # another spec hash, same window: SHARES the budget
    reg.mark_capability_issued(other, attempt_limit=2)
    open_run(reg, Phase.P3B, Partition.DEVELOPMENT_CONFIRMATION)  # another phase: separate
    elsewhere = open_run(reg, protected_range=DateRange(date(2010, 1, 1), date(2010, 6, 30)))
    reg.mark_capability_issued(elsewhere, attempt_limit=2)  # disjoint window: SAME budget (2 of 2)
    rid = open_run(reg)
    with pytest.raises(errors.AttemptLimitExceededError):
        auth(spec, reg, Phase.P3A, Partition.DEVELOPMENT_SELECTION, rid)


def test_n2e_limits_do_not_apply_to_other_phases(tmp_path: Path) -> None:
    reg = new_registry(tmp_path / "runs.jsonl")
    spec = forge_guard_view(max_p3a_attempts=None, max_p3b_attempts=None)
    rid = open_run(reg, Phase.P2, Partition.REPLAY_RNG001)
    cap = auth(
        spec, reg, Phase.P2, Partition.REPLAY_RNG001, rid,
        requested_range=DateRange(date(2026, 2, 1), date(2026, 2, 28)),
    )  # fmt: skip
    assert cap.phase is Phase.P2


# =============================================================================================
# N2f -- P5 is refused outright
# =============================================================================================


def test_n2f_p5_is_refused_with_every_precondition_in_place_and_nothing_is_written(
    tmp_path: Path,
) -> None:
    reg = new_registry(tmp_path / "runs.jsonl")
    complete_prereqs(reg, Phase.P5)
    p4 = open_run(reg, Phase.P4, Partition.HOLDOUT)
    reg.mark_holdout_authorized(p4)
    complete_run(reg, p4)
    rid = open_run(reg, Phase.P5, Partition.PAPER)
    count = reg.count_records()
    with pytest.raises(errors.PaperApprovalNotImplementedError, match="Level 2"):
        auth(
            make_spec(), reg, Phase.P5, Partition.PAPER, rid,
            requested_range=DateRange(date(2026, 9, 1), date(2026, 12, 31)),
        )  # fmt: skip
    assert reg.count_records() == count
    # there is no way to pass an approval reference at all
    with pytest.raises(TypeError):
        authorize(  # type: ignore[call-arg]
            spec=make_spec(), phase=Phase.P5, partition=Partition.PAPER, run_id=rid,
            registry=reg, exposure_ledger=LEDGER, approval_reference="ab" * 32,
        )  # fmt: skip


# =============================================================================================
# N4 -- deep-frozen guard view
# =============================================================================================


def test_n4_guard_view_values_are_deep_frozen_copies() -> None:
    criteria: dict[str, Any] = {"k": [1, {"deep": [2]}]}
    exposure: dict[str, Any] = {"exposure_ledger_sha256": "a" * 64, "n": [1]}
    spec = forge_guard_view(p3_criteria=criteria, exposure_signed=exposure)
    criteria["k"].append("MUTATED")
    criteria["k"][1]["deep"].append("MUTATED")
    exposure["exposure_ledger_sha256"] = "b" * 64
    exposure["n"].append("MUTATED")
    assert spec.p3_criteria["k"][0] == 1 and len(spec.p3_criteria["k"]) == 2
    assert spec.p3_criteria["k"][1]["deep"] == (2,)
    assert spec.exposure_signed["exposure_ledger_sha256"] == "a" * 64
    assert spec.exposure_signed["n"] == (1,)
    with pytest.raises(TypeError):
        spec.p3_criteria["x"] = 1
    with pytest.raises(TypeError):
        spec.exposure_signed["x"] = 1
    with pytest.raises(AttributeError):
        spec.exposure_signed = {}  # type: ignore[misc]


def test_n4_exit_values_in_the_guard_view_are_deep_frozen() -> None:
    cands = [{"id": "X1", "params": {"a": 1}}]
    spec = forge_guard_view(exits_candidates=cands, exits_selection={"score": "s"})
    cands[0]["params"]["a"] = 99
    assert spec.exits_candidates[0]["params"]["a"] == 1
    with pytest.raises(TypeError):
        spec.exits_selection["score"] = "t"


# =============================================================================================
# N7 -- legacy windowless HOLDOUT rows
# =============================================================================================


def _legacy_holdout(reg: RunRegistry, rid: str, *, authorized: bool, status: str | None) -> None:
    chain = HashChainFile(reg.path)
    chain.append(
        run_registry.KIND_OPENED,
        {
            "run_id": rid,
            "phase": "P4",
            "partition": "HOLDOUT",
            "spec_sha256": "4" * 64,
            "code_sha": CODE_SHA,
            "data_manifest_sha256": MANIFEST_SHA,
            "seeds": {"b": 1},
            "exit_candidates": ["E1"],
            "k_exit_candidates": 1,
        },  # no holdout_start / holdout_end: written before the window was recorded
    )
    if authorized:
        chain.append(run_registry.KIND_HOLDOUT_AUTH, {"run_id": rid})
    if status is not None:
        chain.append(
            run_registry.KIND_CLOSED,
            {
                "run_id": rid,
                "status": status,
                "audit_pack_sha256": "d" * 64 if status == "COMPLETED" else None,
            },
        )


def _blocked(reg: RunRegistry) -> bool:
    new = open_run(reg, Phase.P4, Partition.HOLDOUT)
    run = reg.get_run(new)
    assert run is not None
    return holdout_conflict(reg.runs(), run) is not None


def test_n7_a_completed_windowless_holdout_row_blocks_every_window_even_unmarked(
    tmp_path: Path,
) -> None:
    reg = new_registry(tmp_path / "runs.jsonl")
    _legacy_holdout(reg, "legacy-1", authorized=False, status="COMPLETED")
    assert _blocked(reg)


def test_n7_a_marked_windowless_holdout_row_blocks_whatever_its_status(tmp_path: Path) -> None:
    for status in (None, "FAILED", "ABORTED", "DEFECT", "COMPLETED"):
        reg = new_registry(tmp_path / f"{status}" / "runs.jsonl")
        _legacy_holdout(reg, "legacy-1", authorized=True, status=status)
        assert _blocked(reg), status


def test_n7_an_unmarked_uncompleted_windowless_row_blocks_nothing(tmp_path: Path) -> None:
    for status in (None, "FAILED", "ABORTED", "DEFECT"):
        reg = new_registry(tmp_path / f"{status}" / "runs.jsonl")
        _legacy_holdout(reg, "legacy-1", authorized=False, status=status)
        assert not _blocked(reg), status


def test_n7_docstrings_state_exactly_when_a_windowless_row_blocks() -> None:
    doc = holdout_conflict.__doc__ or ""
    assert "authorization mark OR its status is COMPLETED" in doc
    assert "legacy" in (rg.__doc__ or "") and "authorization mark or is COMPLETED" in (
        rg.__doc__ or ""
    )


# =============================================================================================
# N5 / N6 -- documentation statements
# =============================================================================================


def test_n5_docs_list_the_lints_known_bypasses() -> None:
    doc = rg.__doc__ or ""
    for phrase in (
        "DEVELOPER SAFEGUARD",
        "not an adversary-resistant boundary",
        "private lambda",
        "dict (or other container) of",
        "aliased imports",
        "scripts/",
    ):
        assert phrase in doc, phrase


def test_n6_torn_tail_and_missing_newline_messages_say_recovery_is_not_implemented(
    tmp_path: Path,
) -> None:
    note = "fail closed; owner-authorized recovery procedure required (not implemented)"
    reg = new_registry(tmp_path / "runs.jsonl")
    open_run(reg)
    good = reg.path.read_bytes()
    # (1) a valid chain that merely lacks the final newline: the writer refuses to append
    reg.path.write_bytes(good.rstrip(b"\n"))
    with pytest.raises(errors.ChainNotNewlineTerminatedError, match="not implemented") as ei:
        open_run(reg)
    assert note in str(ei.value)
    # (2) a torn tail (half a record): the reader refuses, with the same statement
    reg.path.write_bytes(good + good[: len(good) // 3].rstrip(b"\n"))
    with pytest.raises(errors.RegistryIntegrityError) as ei2:
        RunRegistry(reg.path)
    assert note in str(ei2.value) and "torn tail" in str(ei2.value)
    # no repair path exists: nothing was rewritten
    assert reg.path.read_bytes() == good + good[: len(good) // 3].rstrip(b"\n")


# =============================================================================================
# N8 -- bound registries do not grow without bound
# =============================================================================================


def test_n8_bound_registries_release_dead_capabilities(tmp_path: Path) -> None:
    reg = new_registry(tmp_path / "runs.jsonl")
    gc.collect()
    baseline = len(rg._BOUND_REGISTRIES)
    caps = []
    for _ in range(5):
        caps.append(p3a_cap(reg)[1])
    assert len(rg._BOUND_REGISTRIES) == baseline + 5
    live = caps[0]
    run_id = live.run_id
    del caps
    gc.collect()
    assert len(rg._BOUND_REGISTRIES) == baseline + 1  # only the one still referenced
    assert require_capability(live).run_id == run_id  # semantics unchanged for a live one


def test_n8_a_lookalike_with_a_copied_nonce_does_not_validate(tmp_path: Path) -> None:
    reg = new_registry(tmp_path / "runs.jsonl")
    _, cap = p3a_cap(reg)

    class LookAlike:
        _nonce = cap._nonce
        run_id = cap.run_id
        spec_sha256 = cap.spec_sha256
        phase = cap.phase
        partition = cap.partition

    with pytest.raises(errors.InvalidCapabilityError):
        require_capability(LookAlike())
    with pytest.raises(errors.InvalidCapabilityError):
        require_capability(None)
    assert os.path.exists(reg.path)  # (the registry is untouched by refusals)
