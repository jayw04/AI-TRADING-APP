"""Round-3 owner rulings: F6 (predecessor evidence), F7 (what consumes the holdout), F8 (window).

Level 1 threat model (accidental misuse, casual bypass). Predecessor evidence is content-bound,
NOT authenticated: nothing signs these artefacts (Level 2, design-only). No recovery workflow
for a consumed holdout exists; none is tested because none is implemented. Synthetic data only.
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any

import pytest

from app.research.range002.governance import errors
from app.research.range002.governance.exposure_ledger import ExposureLedger
from app.research.range002.governance.hashchain import HashChainFile
from app.research.range002.governance.holdout_token import (
    HoldoutToken,
    HoldoutTokenStore,
    TokenState,
)
from app.research.range002.governance.model import DateRange, Partition, Phase
from app.research.range002.governance.results_guard import (
    PredecessorEvidence,
    _check_phase_order,
    authorize,
)
from app.research.range002.governance.run_registry import RunRegistry, RunStatus

from .conftest import (
    CODE_SHA,
    MANIFEST_SHA,
    SIGNED_LEDGER,
    SPEC_SHA,
    SYNTH_GENESIS_ID,
    complete_prereqs,
    complete_run,
    evidence_for,
    make_spec,
    new_registry,
    open_run,
)

LED = ExposureLedger.from_text(SIGNED_LEDGER)
_P5_RANGE = DateRange(date(2026, 9, 1), date(2026, 12, 31))


def _gate(phase: Phase, partition: Partition, reg: RunRegistry, rid: str, **kw: Any) -> Any:
    kw.setdefault("predecessor_evidence", evidence_for(reg))
    return authorize(
        spec=kw.pop("spec", None) or make_spec(),
        phase=phase,
        partition=partition,
        run_id=rid,
        registry=reg,
        exposure_ledger=LED,
        **kw,
    )


def _p3b(reg: RunRegistry, **kw: Any) -> Any:
    rid = open_run(reg, Phase.P3B, Partition.DEVELOPMENT_CONFIRMATION)
    return _gate(Phase.P3B, Partition.DEVELOPMENT_CONFIRMATION, reg, rid, **kw)


def _p5(reg: RunRegistry, **kw: Any) -> Any:
    rid = open_run(reg, Phase.P5, Partition.PAPER)
    return _gate(Phase.P5, Partition.PAPER, reg, rid, requested_range=_P5_RANGE, **kw)


def _holdout(spec: Any, reg: RunRegistry, store: HoldoutTokenStore, rid: str, **kw: Any) -> Any:
    if "holdout_token" not in kw:
        if store.state(spec.spec_sha256) is TokenState.NOT_ISSUED:
            kw["holdout_token"] = store.issue(
                spec.spec_sha256, registry_genesis_id=SYNTH_GENESIS_ID
            )
        else:  # the token already exists (or is spent): present a stand-in the store will judge
            kw["holdout_token"] = HoldoutToken(spec.spec_sha256, "stand-in", SYNTH_GENESIS_ID)
    return _gate(Phase.P4, Partition.HOLDOUT, reg, rid, spec=spec, holdout_store=store, **kw)


# --- F6: registry rows alone do not establish that a predecessor passed -------------------


def test_f6_p5_is_refused_outright_whatever_the_registry_holds(tmp_path: Path) -> None:
    reg = new_registry(tmp_path / "runs.jsonl")
    complete_prereqs(reg, Phase.P5)  # every predecessor completed, with evidence
    with pytest.raises(errors.PaperApprovalNotImplementedError):
        _p5(reg)


def test_f6_p5_rule_requires_a_completed_p4_for_the_same_spec(tmp_path: Path) -> None:
    """The P5 predecessor rule is dead through authorize (P5 is refused) but kept and tested."""
    reg = new_registry(tmp_path / "runs.jsonl")
    complete_prereqs(reg, Phase.P4)
    with pytest.raises(errors.PhaseOrderError, match="P4"):
        _check_phase_order(reg, SPEC_SHA, Phase.P5, [])  # no P4 at all
    p4 = open_run(reg, Phase.P4, Partition.HOLDOUT)
    with pytest.raises(errors.PhaseOrderError):
        _check_phase_order(reg, SPEC_SHA, Phase.P5, [])  # an OPEN P4 is not a completed one
    complete_run(reg, p4)
    with pytest.raises(errors.PredecessorHoldoutNotAuthorizedError):  # completed, never authorized
        _check_phase_order(reg, SPEC_SHA, Phase.P5, evidence_for(reg))


def test_f6_p4_of_another_spec_does_not_count(tmp_path: Path) -> None:
    reg = new_registry(tmp_path / "runs.jsonl")
    complete_prereqs(reg, Phase.P5, "9" * 64)
    with pytest.raises(errors.PhaseOrderError):
        _check_phase_order(reg, SPEC_SHA, Phase.P5, evidence_for(reg))


def test_f6_missing_evidence_is_a_named_refusal(tmp_path: Path) -> None:
    reg = new_registry(tmp_path / "runs.jsonl")
    complete_prereqs(reg, Phase.P3B)
    with pytest.raises(errors.PredecessorEvidenceMissingError):
        _p3b(reg, predecessor_evidence=[])
    with pytest.raises(errors.PredecessorEvidenceMissingError):  # default arg: nothing supplied
        rid = open_run(reg, Phase.P3B, Partition.DEVELOPMENT_CONFIRMATION)
        authorize(
            spec=make_spec(),
            phase=Phase.P3B,
            partition=Partition.DEVELOPMENT_CONFIRMATION,
            run_id=rid,
            registry=reg,
            exposure_ledger=LED,
        )
    assert issubclass(errors.PredecessorEvidenceMissingError, errors.PhaseOrderError)


def test_f6_unreadable_audit_pack_is_missing_evidence(tmp_path: Path) -> None:
    reg = new_registry(tmp_path / "runs.jsonl")
    complete_prereqs(reg, Phase.P3B)
    (ev,) = evidence_for(reg)
    gone = PredecessorEvidence(ev.run_id, tmp_path / "nope.audit", ev.selection_record_path)
    with pytest.raises(errors.PredecessorEvidenceMissingError, match="cannot read"):
        _p3b(reg, predecessor_evidence=[gone])


def test_f6_tampered_audit_pack_is_a_mismatch(tmp_path: Path) -> None:
    reg = new_registry(tmp_path / "runs.jsonl")
    complete_prereqs(reg, Phase.P3B)
    (ev,) = evidence_for(reg)
    ev.audit_pack_path.write_bytes(b"edited after the run was closed")
    with pytest.raises(errors.PredecessorEvidenceMismatchError, match="audit pack"):
        _p3b(reg)


def test_f6_registry_row_with_an_unbacked_digest_is_a_mismatch(tmp_path: Path) -> None:
    """A COMPLETED row whose digest names nothing real: rows alone do not establish a pass."""
    reg = new_registry(tmp_path / "runs.jsonl")
    p3a = open_run(reg)
    reg.record_selection(p3a, {"selected": "E1", "run_id": p3a, "spec_sha256": SPEC_SHA})
    reg.mark_capability_issued(p3a, attempt_limit=9)
    reg.close_run(p3a, RunStatus.COMPLETED, "d" * 64)  # no artefact hashes to this
    pack = tmp_path / "pack.audit"
    pack.write_bytes(b"whatever the caller has")
    sel = tmp_path / "sel.json"
    sel.write_text(json.dumps({"selected": "E1"}), encoding="utf-8")
    with pytest.raises(errors.PredecessorEvidenceMismatchError):
        _p3b(reg, predecessor_evidence=[PredecessorEvidence(p3a, pack, sel)])


def test_f6_tampered_selection_record_is_a_mismatch(tmp_path: Path) -> None:
    reg = new_registry(tmp_path / "runs.jsonl")
    complete_prereqs(reg, Phase.P3B)
    (ev,) = evidence_for(reg)
    assert ev.selection_record_path is not None
    ev.selection_record_path.write_text(json.dumps({"selected": "E2a"}), encoding="utf-8")
    with pytest.raises(errors.PredecessorEvidenceMismatchError, match="selection record"):
        _p3b(reg)


def test_f6_selection_record_hash_is_canonical_json_so_reformatting_is_fine(
    tmp_path: Path,
) -> None:
    reg = new_registry(tmp_path / "runs.jsonl")
    complete_prereqs(reg, Phase.P3B)
    (ev,) = evidence_for(reg)
    assert ev.selection_record_path is not None
    body = json.loads(ev.selection_record_path.read_text(encoding="utf-8"))
    ev.selection_record_path.write_text(
        json.dumps(body, indent=4, sort_keys=True), encoding="utf-8"
    )
    assert _p3b(reg).phase is Phase.P3B


def test_f6_selection_record_not_supplied_or_unreadable(tmp_path: Path) -> None:
    reg = new_registry(tmp_path / "runs.jsonl")
    complete_prereqs(reg, Phase.P3B)
    (ev,) = evidence_for(reg)
    with pytest.raises(errors.PredecessorEvidenceMissingError, match="selection record"):
        _p3b(reg, predecessor_evidence=[PredecessorEvidence(ev.run_id, ev.audit_pack_path)])
    bad = PredecessorEvidence(ev.run_id, ev.audit_pack_path, tmp_path / "nope.json")
    with pytest.raises(errors.PredecessorEvidenceMissingError):
        _p3b(reg, predecessor_evidence=[bad])
    assert ev.selection_record_path is not None
    ev.selection_record_path.write_text('{"a": 1, "a": 2}', encoding="utf-8")  # duplicate keys
    with pytest.raises(errors.PredecessorEvidenceMissingError):
        _p3b(reg)


def test_f6_legacy_selection_row_without_a_digest_cannot_be_verified(tmp_path: Path) -> None:
    path = tmp_path / "runs.jsonl"
    new_registry(path)
    chain = HashChainFile(path)
    chain.append(
        "run_opened",
        {
            "run_id": "range002-run-000001",
            "phase": "P3A",
            "partition": "DEVELOPMENT_SELECTION",
            "spec_sha256": SPEC_SHA,
            "code_sha": CODE_SHA,
            "data_manifest_sha256": MANIFEST_SHA,
            "seeds": {"b": 1},
            "exit_candidates": ["E1"],
            "k_exit_candidates": 1,
        },
    )
    chain.append("selection_record", {"run_id": "range002-run-000001", "record": {"s": 1}})
    reg = RunRegistry(path)
    complete_run(reg, "range002-run-000001")
    sel = tmp_path / "sel.json"
    sel.write_text(json.dumps({"s": 1}), encoding="utf-8")
    (ev,) = evidence_for(reg)
    with pytest.raises(errors.PredecessorEvidenceMismatchError):
        _p3b(reg, predecessor_evidence=[PredecessorEvidence(ev.run_id, ev.audit_pack_path, sel)])


def test_f6_wording_says_content_bound_not_authenticated() -> None:
    assert "not authenticated" in (PredecessorEvidence.__doc__ or "")


# --- F7: only an ISSUED authorization (or uncertain state) consumes the holdout ---------------


def test_f7_rejection_before_authorization_leaves_the_holdout_usable(tmp_path: Path) -> None:
    reg = new_registry(tmp_path / "runs.jsonl")
    store = HoldoutTokenStore(tmp_path / "tokens")
    complete_prereqs(reg, Phase.P4)
    spec = make_spec()
    token = store.issue(SPEC_SHA, registry_genesis_id=SYNTH_GENESIS_ID)
    first = open_run(reg, Phase.P4, Partition.HOLDOUT)
    with pytest.raises(errors.HoldoutTokenInvalidError):  # rejected BEFORE the mark
        _holdout(spec, reg, store, first, holdout_token=None)
    reg.close_run(first, RunStatus.FAILED, None)  # the failed attempt stays on record
    assert reg.get_run(first).holdout_authorized_seq is None  # type: ignore[union-attr]
    assert store.state(SPEC_SHA) is TokenState.ISSUED  # token not burned
    second = open_run(reg, Phase.P4, Partition.HOLDOUT)
    cap = _holdout(spec, reg, store, second, holdout_token=token)
    assert cap.run_id == second
    assert reg.count_runs(SPEC_SHA) >= 4  # failed attempts are counted, never erased


def test_f7_other_pre_authorization_refusals_do_not_block(tmp_path: Path) -> None:
    reg = new_registry(tmp_path / "runs.jsonl")
    store = HoldoutTokenStore(tmp_path / "tokens")
    complete_prereqs(reg, Phase.P4)
    first = open_run(reg, Phase.P4, Partition.HOLDOUT)
    with pytest.raises(errors.PartitionNotAuthorizedError):  # no token store supplied
        _gate(Phase.P4, Partition.HOLDOUT, reg, first)
    reg.close_run(first, RunStatus.ABORTED, None)
    second = open_run(reg, Phase.P4, Partition.HOLDOUT)
    assert _holdout(make_spec(), reg, store, second).partition is Partition.HOLDOUT


def test_f7_failure_after_the_mark_leaves_the_holdout_consumed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    reg = new_registry(tmp_path / "runs.jsonl")
    store = HoldoutTokenStore(tmp_path / "tokens")
    complete_prereqs(reg, Phase.P4)
    first = open_run(reg, Phase.P4, Partition.HOLDOUT)

    def boom(*_a: Any, **_k: Any) -> None:
        raise OSError("disk full while consuming")

    monkeypatch.setattr(HoldoutTokenStore, "consume", boom)
    with pytest.raises(OSError, match="disk full"):
        _holdout(make_spec(), reg, store, first)
    monkeypatch.undo()
    assert reg.get_run(first).holdout_authorized_seq is not None  # type: ignore[union-attr]
    reg.close_run(first, RunStatus.FAILED, None)
    second = open_run(reg, Phase.P4, Partition.HOLDOUT)
    fresh = HoldoutTokenStore(tmp_path / "fresh")  # a brand-new token store is no way out
    with pytest.raises(errors.HoldoutAlreadyOpenedError):
        _holdout(make_spec(), reg, fresh, second)


def test_f7_crash_after_the_mark_leaves_the_holdout_consumed(tmp_path: Path) -> None:
    reg = new_registry(tmp_path / "runs.jsonl")
    complete_prereqs(reg, Phase.P4)
    crashed = open_run(reg, Phase.P4, Partition.HOLDOUT)
    reg.mark_holdout_authorized(crashed)  # ... and the process dies here, run still OPEN
    nxt = open_run(reg, Phase.P4, Partition.HOLDOUT)
    store = HoldoutTokenStore(tmp_path / "tokens")
    with pytest.raises(errors.HoldoutAlreadyOpenedError):
        _holdout(make_spec(), reg, store, nxt)
    reg.abort_open_runs()  # crash recovery closes the rows ...
    third = open_run(reg, Phase.P4, Partition.HOLDOUT)
    with pytest.raises(errors.HoldoutAlreadyOpenedError):  # ... but never restores the window
        _holdout(make_spec(), reg, store, third)


def test_f7_deleting_token_files_or_registry_rows_is_not_a_recovery_path(tmp_path: Path) -> None:
    reg = new_registry(tmp_path / "runs.jsonl")
    tokens = tmp_path / "tokens"
    store = HoldoutTokenStore(tokens)
    complete_prereqs(reg, Phase.P4)
    first = open_run(reg, Phase.P4, Partition.HOLDOUT)
    _holdout(make_spec(), reg, store, first)
    reg.close_run(first, RunStatus.FAILED, None)
    for f in tokens.iterdir():
        f.unlink()  # token directory wiped
    second = open_run(reg, Phase.P4, Partition.HOLDOUT)
    fresh = HoldoutTokenStore(tokens)
    with pytest.raises(errors.HoldoutAlreadyOpenedError):
        _holdout(make_spec(), reg, fresh, second)
    # Removing a row from the middle of the chain is detected by every handle ...
    lines = reg.path.read_bytes().split(b"\n")
    victim = next(i for i, ln in enumerate(lines) if b"holdout_authorized" in ln)
    del lines[victim]
    reg.path.write_bytes(b"\n".join(lines))
    with pytest.raises(errors.RegistryIntegrityError):
        reg.runs()
    with pytest.raises(errors.RegistryIntegrityError):
        RunRegistry(reg.path)
    # ... while truncating only the TAIL is detected by a live handle but not by a fresh one
    # (known limit: external head anchoring is not implemented, owner decision pending).


# --- F8: one opening per protected WINDOW, tracked in RANGE-002's own registry ------------------


def _authorized_first(reg: RunRegistry, store: HoldoutTokenStore) -> str:
    complete_prereqs(reg, Phase.P4)
    first = open_run(reg, Phase.P4, Partition.HOLDOUT)
    _holdout(make_spec(), reg, store, first)
    reg.close_run(first, RunStatus.FAILED, None)
    return first


def test_f8_editing_a_p0_field_cannot_buy_a_second_opening(tmp_path: Path) -> None:
    reg = new_registry(tmp_path / "runs.jsonl")
    _authorized_first(reg, HoldoutTokenStore(tmp_path / "tokens"))
    edited = make_spec(spec_sha256="7" * 64)  # a "new" spec hash over the same holdout window
    complete_prereqs(reg, Phase.P4, "7" * 64)
    second = open_run(reg, Phase.P4, Partition.HOLDOUT, "7" * 64)
    with pytest.raises(errors.HoldoutAlreadyOpenedError, match="window"):
        _holdout(edited, reg, HoldoutTokenStore(tmp_path / "fresh"), second)


def test_f8_independence_reference_cannot_be_validated_so_it_is_refused(tmp_path: Path) -> None:
    reg = new_registry(tmp_path / "runs.jsonl")
    _authorized_first(reg, HoldoutTokenStore(tmp_path / "tokens"))
    edited = make_spec(spec_sha256="7" * 64)
    complete_prereqs(reg, Phase.P4, "7" * 64)
    second = open_run(reg, Phase.P4, Partition.HOLDOUT, "7" * 64)
    with pytest.raises(errors.IndependenceAuthorizationNotAcceptedError, match="never accepted"):
        _holdout(
            edited,
            reg,
            HoldoutTokenStore(tmp_path / "fresh"),
            second,
            independence_authorization="OWNER-APPROVAL-2026-10-09",
        )
    assert issubclass(
        errors.IndependenceAuthorizationNotAcceptedError, errors.HoldoutAlreadyOpenedError
    )


def test_f8_overlapping_but_not_identical_window_also_blocks(tmp_path: Path) -> None:
    reg = new_registry(tmp_path / "runs.jsonl")
    _authorized_first(reg, HoldoutTokenStore(tmp_path / "tokens"))
    part = {
        "development_selection": (date(2016, 1, 1), date(2019, 12, 31)),
        "development_confirmation": (date(2020, 1, 1), date(2021, 12, 31)),
        "holdout": (date(2025, 6, 1), date(2025, 12, 31)),  # overlaps the first window's tail
    }
    spec = make_spec(spec_sha256="6" * 64, partitions=part)
    complete_prereqs(reg, Phase.P4, "6" * 64)
    rng = DateRange(date(2025, 6, 1), date(2025, 12, 31))
    second = open_run(reg, Phase.P4, Partition.HOLDOUT, "6" * 64, holdout_range=rng)
    with pytest.raises(errors.HoldoutAlreadyOpenedError):
        _holdout(spec, reg, HoldoutTokenStore(tmp_path / "t2"), second)


def test_f8_disjoint_window_is_not_blocked(tmp_path: Path) -> None:
    reg = new_registry(tmp_path / "runs.jsonl")
    _authorized_first(reg, HoldoutTokenStore(tmp_path / "tokens"))
    rng = DateRange(date(2028, 1, 1), date(2028, 12, 31))
    part = {
        "development_selection": (date(2016, 1, 1), date(2019, 12, 31)),
        "development_confirmation": (date(2020, 1, 1), date(2021, 12, 31)),
        "holdout": (rng.start, rng.end),
    }
    spec = make_spec(spec_sha256="5" * 64, partitions=part)
    complete_prereqs(reg, Phase.P4, "5" * 64)
    second = open_run(reg, Phase.P4, Partition.HOLDOUT, "5" * 64, holdout_range=rng)
    cap = _holdout(spec, reg, HoldoutTokenStore(tmp_path / "t3"), second)
    assert cap.partition is Partition.HOLDOUT


def test_f8_legacy_authorized_row_without_a_range_blocks_every_window(tmp_path: Path) -> None:
    """Backward check: a chain written before the range was recorded fails closed."""
    path = tmp_path / "runs.jsonl"
    new_registry(path)
    chain = HashChainFile(path)
    chain.append(
        "run_opened",
        {
            "run_id": "range002-run-000001",
            "phase": "P4",
            "partition": "HOLDOUT",
            "spec_sha256": "4" * 64,
            "code_sha": CODE_SHA,
            "data_manifest_sha256": MANIFEST_SHA,
            "seeds": {"b": 1},
            "exit_candidates": ["E1"],
            "k_exit_candidates": 1,
        },
    )
    chain.append("holdout_authorized", {"run_id": "range002-run-000001"})
    reg = RunRegistry(path)
    assert reg.runs()[0].holdout_range is None
    complete_prereqs(reg, Phase.P4)
    rid = open_run(reg, Phase.P4, Partition.HOLDOUT)
    with pytest.raises(errors.HoldoutAlreadyOpenedError):
        _holdout(make_spec(), reg, HoldoutTokenStore(tmp_path / "t"), rid)


def test_f8_holdout_run_must_record_the_spec_window(tmp_path: Path) -> None:
    reg = new_registry(tmp_path / "runs.jsonl")
    with pytest.raises(errors.RegistryRecordError, match="holdout_range"):
        reg.open_run(
            phase=Phase.P4,
            spec_sha256=SPEC_SHA,
            code_sha=CODE_SHA,
            data_manifest_sha256=MANIFEST_SHA,
            partition=Partition.HOLDOUT,
            seeds={"b": 1},
            exit_candidates=["E1"],
        )
    with pytest.raises(errors.RegistryRecordError, match="HOLDOUT runs only"):
        reg.open_run(
            phase=Phase.P3A,
            spec_sha256=SPEC_SHA,
            code_sha=CODE_SHA,
            data_manifest_sha256=MANIFEST_SHA,
            partition=Partition.DEVELOPMENT_SELECTION,
            seeds={"b": 1},
            exit_candidates=["E1"],
            holdout_range=DateRange(date(2030, 1, 1), date(2030, 2, 1)),
        )
    complete_prereqs(reg, Phase.P4)
    wrong = open_run(
        reg,
        Phase.P4,
        Partition.HOLDOUT,
        holdout_range=DateRange(date(2030, 1, 1), date(2030, 2, 1)),
    )
    store = HoldoutTokenStore(tmp_path / "tokens")
    with pytest.raises(errors.RunNotRegisteredError, match="holdout range"):
        _holdout(make_spec(), reg, store, wrong)
