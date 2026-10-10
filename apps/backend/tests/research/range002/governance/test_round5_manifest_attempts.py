"""Round 5 N-A / N-B at the results guard (synthetic manifests, synthetic specs).

N-A: registry genesis == spec genesis == OWNER-APPROVED manifest genesis. The reviewer proof of
concept (a new directory + a re-enrolled registry + a re-freeze with a new genesis re-opens a used
holdout window) must be refused by the manifest. N-B: P3A / P3B attempts are counted per
(registry genesis, phase, protected window) across ALL spec hashes, consumed when governed
authorization is issued (``capability_issued``), limits only from the manifest.

The limits are about governed EVALUATION RUNS (one authorized run evaluates all frozen exit
candidates and baselines together); they are not trade-count minimums.
Level 1 only: a copied registry keeps its genesis (Level 2 limitation, pinned below).
"""

from __future__ import annotations

import inspect
import shutil
import threading
from datetime import date
from pathlib import Path
from typing import Any

import pytest

from app.research.range002.governance import errors
from app.research.range002.governance import results_guard as rg
from app.research.range002.governance.exposure_ledger import ExposureLedger
from app.research.range002.governance.hashchain import HashChainFile
from app.research.range002.governance.holdout_token import HoldoutTokenStore
from app.research.range002.governance.model import DateRange, Partition, Phase
from app.research.range002.governance.results_guard import authorize
from app.research.range002.governance.run_registry import RunRegistry, RunStatus
from app.research.range002.spec.manifest import (
    ManifestGenesisMismatchError,
    ManifestLimitMismatchError,
    ManifestNotApprovedError,
    load_manifest,
)
from tests.research.range002.spec._fixtures import (
    OTHER_GENESIS_ID,
    SYNTH_GENESIS_ID,
    SYNTH_MANIFEST_PATH,
    complete_payload,
    set_path,
)

from .conftest import (
    CODE_SHA,
    LEDGER_SHA,
    MANIFEST_SHA,
    SIGNED_LEDGER,
    SPEC_SHA,
    _default_guard_fields,
    complete_prereqs,
    forge_guard_view,
    new_registry,
    open_run,
    use_manifest,
)

LEDGER = ExposureLedger.from_text(SIGNED_LEDGER)
P3A, SEL = Phase.P3A, Partition.DEVELOPMENT_SELECTION
OTHER_SPEC = "8" * 64


def auth(
    spec: Any, reg: RunRegistry, rid: str, phase: Phase = P3A, part: Partition = SEL, **kw: Any
):
    return authorize(
        spec=spec,
        phase=phase,
        partition=part,
        run_id=rid,
        registry=reg,
        exposure_ledger=LEDGER,
        **kw,
    )


def _spec(**changes: Any):
    return forge_guard_view(**changes)


# =============================================================================================
# N-A -- owner-approved manifest
# =============================================================================================


def test_authorize_has_no_manifest_parameter() -> None:
    """The fixed-path manifest cannot be swapped by a caller: there is no parameter for it."""
    assert not any("manifest" in name for name in inspect.signature(authorize).parameters)


def test_committed_unset_manifest_refuses_authorize_and_writes_nothing(tmp_path: Path) -> None:
    reg = new_registry(tmp_path / "runs.jsonl")
    rid = open_run(reg)
    rg._MANIFEST_PATH = None  # production default: the committed manifest, which ships UNSET
    count = reg.count_records()
    with pytest.raises(ManifestNotApprovedError):
        auth(_spec(), reg, rid)
    assert reg.count_records() == count


@pytest.mark.parametrize(
    "overrides",
    [
        {"approved_registry_genesis_id": None, "approved_by": None, "approved_on": None},
    ],
)
def test_unapproved_manifest_refuses_every_partition(tmp_path: Path, overrides: dict) -> None:
    reg = new_registry(tmp_path / "runs.jsonl")
    use_manifest(tmp_path, **overrides)
    with pytest.raises(ManifestNotApprovedError):
        auth(_spec(), reg, open_run(reg))
    rid2 = open_run(reg, Phase.P2, Partition.REPLAY_RNG001)
    with pytest.raises(ManifestNotApprovedError):
        auth(
            _spec(), reg, rid2, Phase.P2, Partition.REPLAY_RNG001,
            requested_range=DateRange(date(2026, 2, 1), date(2026, 2, 28)),
        )  # fmt: skip


def test_reviewer_poc_a_new_directory_and_a_new_genesis_cannot_reopen_a_used_holdout(
    tmp_path: Path,
) -> None:
    """(a) Re-enroll in a new dir + re-freeze with the new genesis cannot reopen the used window."""
    old = new_registry(tmp_path / "old" / "runs.jsonl")
    complete_prereqs(old, Phase.P4)
    store = HoldoutTokenStore(tmp_path / "tokens_old")
    first = open_run(old, Phase.P4, Partition.HOLDOUT)
    auth(
        _spec(), old, first, Phase.P4, Partition.HOLDOUT,
        holdout_store=store,
        holdout_token=store.issue(SPEC_SHA, registry_genesis_id=SYNTH_GENESIS_ID),
        predecessor_evidence=_evidence(old),
    )  # fmt: skip
    # the casual bypass: a brand-new directory, a freshly enrolled registry (new genesis)...
    fresh = RunRegistry.enroll_new(tmp_path / "new_dir" / "runs.jsonl", enrolled_by="someone")
    assert fresh.genesis_id != SYNTH_GENESIS_ID
    # ... and a spec re-frozen with the new genesis, plus a fresh token store for it
    complete_prereqs(fresh, Phase.P4)
    store2 = HoldoutTokenStore(tmp_path / "tokens_new")
    second = open_run(fresh, Phase.P4, Partition.HOLDOUT)
    spec_new = _spec(registry_genesis_id=fresh.genesis_id)
    count = fresh.count_records()
    with pytest.raises(ManifestGenesisMismatchError):
        auth(
            spec_new, fresh, second, Phase.P4, Partition.HOLDOUT,
            holdout_store=store2,
            holdout_token=store2.issue(SPEC_SHA, registry_genesis_id=fresh.genesis_id),
            predecessor_evidence=_evidence(fresh),
        )  # fmt: skip
    assert fresh.count_records() == count  # no holdout_authorized row, nothing consumed
    # ... and re-freezing that spec is refused by freeze_spec against the approved manifest
    import sys

    sys.path.insert(
        0, str(Path(__file__).resolve().parents[4] / "scripts" / "research" / "range002")
    )
    import freeze_spec

    payload = complete_payload()
    set_path(payload, "governance.registry_genesis_id", fresh.genesis_id)
    draft = tmp_path / "draft.json"
    import json

    draft.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ManifestGenesisMismatchError):
        freeze_spec.freeze(draft, tmp_path / "frozen.json", manifest_path=SYNTH_MANIFEST_PATH)
    assert not (tmp_path / "frozen.json").exists()


def _evidence(reg: RunRegistry):
    from .conftest import evidence_for

    return evidence_for(reg)


def test_fresh_worktree_copying_the_spec_has_no_approved_registry(tmp_path: Path) -> None:
    """A fresh worktree enrolls its own registry: its genesis matches neither the spec nor the
    manifest, so nothing authorizes there."""
    fresh = RunRegistry.enroll_new(tmp_path / "wt" / "runs.jsonl", enrolled_by="agent")
    rid = open_run(fresh)
    with pytest.raises(errors.RegistryGenesisMismatchError):
        auth(_spec(), fresh, rid)
    with pytest.raises(ManifestGenesisMismatchError):
        auth(_spec(registry_genesis_id=fresh.genesis_id), fresh, rid)
    assert fresh.get_run(rid).capability_issued_seq is None  # type: ignore[union-attr]


def test_registry_equal_to_manifest_but_spec_naming_another_genesis_is_refused(
    tmp_path: Path,
) -> None:
    reg = new_registry(tmp_path / "runs.jsonl")
    with pytest.raises(errors.RegistryGenesisMismatchError):
        auth(_spec(registry_genesis_id=OTHER_GENESIS_ID), reg, open_run(reg))
    with pytest.raises(errors.RegistryGenesisMismatchError):
        auth(_spec(registry_genesis_id=None), reg, open_run(reg))


def test_manifest_changed_by_the_owner_is_what_moves_the_binding(tmp_path: Path) -> None:
    """The only way to approve another genesis is to change the (reviewed, committed) manifest."""
    fresh = RunRegistry.enroll_new(tmp_path / "wt" / "runs.jsonl", enrolled_by="owner")
    rid = open_run(fresh)
    spec = _spec(registry_genesis_id=fresh.genesis_id)
    with pytest.raises(ManifestGenesisMismatchError):
        auth(spec, fresh, rid)
    use_manifest(tmp_path, approved_registry_genesis_id=fresh.genesis_id)
    assert auth(spec, fresh, rid).run_id == rid


def test_level2_limitation_a_copied_registry_keeps_its_genesis(tmp_path: Path) -> None:
    """PINNED LIMITATION (Level 2, design-only): a byte-for-byte COPY of the approved registry has
    the approved genesis id, so the manifest check cannot tell it from the original. Detecting
    that needs an external anchor (signed or remotely held head); not implemented."""
    reg = new_registry(tmp_path / "a" / "runs.jsonl")
    rid = open_run(reg)
    (tmp_path / "b").mkdir()
    copy = tmp_path / "b" / "runs.jsonl"
    shutil.copyfile(reg.path, copy)
    clone = RunRegistry(copy)
    assert clone.genesis_id == reg.genesis_id == SYNTH_GENESIS_ID
    assert auth(_spec(), clone, rid).run_id == rid  # authorizes: documented, not defended


def test_manifest_sha256_is_recorded_in_the_capability_row(tmp_path: Path) -> None:
    reg = new_registry(tmp_path / "runs.jsonl")
    rid = open_run(reg)
    auth(_spec(), reg, rid)
    run = reg.get_run(rid)
    row = next(r for r in reg.records() if r.seq == run.capability_issued_seq)  # type: ignore[union-attr]
    assert row.payload["manifest_sha256"] == load_manifest(SYNTH_MANIFEST_PATH).sha256
    other = tmp_path / "m2.json"
    use_manifest(tmp_path, p3a=7)
    assert load_manifest(rg._MANIFEST_PATH).sha256 != load_manifest(SYNTH_MANIFEST_PATH).sha256
    del other


def test_spec_limits_must_equal_the_preregistered_manifest_limits(tmp_path: Path) -> None:
    reg = new_registry(tmp_path / "runs.jsonl")
    rid = open_run(reg)
    count = reg.count_records()
    with pytest.raises(ManifestLimitMismatchError):
        auth(_spec(max_p3a_attempts=2), reg, rid)  # manifest says 9
    with pytest.raises(ManifestLimitMismatchError):
        auth(_spec(max_p3b_attempts=2), reg, rid)
    assert reg.count_records() == count


@pytest.mark.parametrize("which", ["p3a", "p3b"])
def test_null_manifest_limit_refuses_both_phases(tmp_path: Path, which: str) -> None:
    reg = new_registry(tmp_path / "runs.jsonl")
    use_manifest(tmp_path, **{which: None})
    rid = open_run(reg)
    with pytest.raises(ManifestNotApprovedError):
        auth(_spec(), reg, rid)
    assert reg.get_run(rid).capability_issued_seq is None  # type: ignore[union-attr]


# =============================================================================================
# N-B -- attempt accounting
# =============================================================================================


def test_reviewer_poc_b_editing_a_p0_field_and_refreezing_does_not_reset_the_budget(
    tmp_path: Path,
) -> None:
    """(b) Same window, different spec hash (a changed P0 field), same registry: ONE budget."""
    use_manifest(tmp_path, p3a=2)
    reg = new_registry(tmp_path / "runs.jsonl")
    spec_a = _spec(max_p3a_attempts=2)
    spec_b = _spec(max_p3a_attempts=2, spec_sha256=OTHER_SPEC)  # P0 edit => new spec hash
    a1 = open_run(reg)
    b1 = open_run(reg, spec_sha=OTHER_SPEC)
    a2 = open_run(reg)
    b2 = open_run(reg, spec_sha=OTHER_SPEC)
    auth(spec_a, reg, a1)
    auth(spec_b, reg, b1)  # the other spec hash draws on the SAME budget
    count = reg.count_records()
    for spec, rid in ((spec_a, a2), (spec_b, b2)):
        with pytest.raises(errors.AttemptLimitExceededError):
            auth(spec, reg, rid)
    assert reg.count_records() == count


def test_code_version_change_does_not_reset_the_budget(tmp_path: Path) -> None:
    use_manifest(tmp_path, p3a=1)
    reg = new_registry(tmp_path / "runs.jsonl")
    spec = _spec(max_p3a_attempts=1)
    first = open_run(reg)
    auth(spec, reg, first)
    other_code = reg.open_run(
        phase=P3A, spec_sha256=SPEC_SHA, code_sha="d" * 40, data_manifest_sha256=MANIFEST_SHA,
        partition=SEL, seeds={"bootstrap": 2}, exit_candidates=["E1"],
        protected_range=DateRange(date(2016, 1, 1), date(2019, 12, 31)),
    )  # fmt: skip
    with pytest.raises(errors.AttemptLimitExceededError):
        auth(spec, reg, other_code)


def test_an_overlapping_but_shifted_window_shares_the_budget(tmp_path: Path) -> None:
    use_manifest(tmp_path, p3a=1)
    reg = new_registry(tmp_path / "runs.jsonl")
    spec = _spec(max_p3a_attempts=1)
    auth(spec, reg, open_run(reg))
    fields = _default_guard_fields(__import__("json").dumps({"exposure_ledger_sha256": LEDGER_SHA}))
    parts = dict(fields["partitions"])
    parts["development_selection"] = (date(2016, 3, 1), date(2019, 12, 31))  # shifted, overlaps
    shifted = _spec(partitions=parts, max_p3a_attempts=1)
    rid = open_run(reg, protected_range=DateRange(*parts["development_selection"]))
    with pytest.raises(errors.AttemptLimitExceededError):
        auth(shifted, reg, rid)


def test_a_run_opened_for_another_window_than_the_specs_is_refused(tmp_path: Path) -> None:
    reg = new_registry(tmp_path / "runs.jsonl")
    rid = open_run(reg, protected_range=DateRange(date(2010, 1, 1), date(2010, 12, 31)))
    with pytest.raises(errors.RunNotRegisteredError, match="protected window"):
        auth(_spec(), reg, rid)


def test_open_run_requires_the_protected_window_for_p3(tmp_path: Path) -> None:
    reg = new_registry(tmp_path / "runs.jsonl")
    before = reg.path.read_bytes()
    with pytest.raises(errors.RegistryRecordError, match="protected"):
        reg.open_run(
            phase=P3A, spec_sha256=SPEC_SHA, code_sha=CODE_SHA, data_manifest_sha256=MANIFEST_SHA,
            partition=SEL, seeds={"s": 1}, exit_candidates=["E1"],
        )  # fmt: skip
    with pytest.raises(errors.RegistryRecordError, match="P3A / P3B"):
        reg.open_run(
            phase=Phase.P4, spec_sha256=SPEC_SHA, code_sha=CODE_SHA,
            data_manifest_sha256=MANIFEST_SHA, partition=Partition.HOLDOUT, seeds={"s": 1},
            exit_candidates=["E1"], holdout_range=DateRange(date(2022, 1, 1), date(2025, 12, 31)),
            protected_range=DateRange(date(2016, 1, 1), date(2019, 12, 31)),
        )  # fmt: skip
    assert reg.path.read_bytes() == before


def test_duplicate_authorization_of_the_same_run_is_refused(tmp_path: Path) -> None:
    reg = new_registry(tmp_path / "runs.jsonl")
    rid = open_run(reg)
    auth(_spec(), reg, rid)
    count = reg.count_records()
    with pytest.raises(errors.CapabilityAlreadyIssuedError):
        auth(_spec(), reg, rid)
    with pytest.raises(errors.CapabilityAlreadyIssuedError):
        reg.mark_capability_issued(rid, attempt_limit=9)
    assert reg.count_records() == count
    assert reg.attempts_consumed(open_run(reg)) == 1  # one authorization, not two


def test_a_refused_request_consumes_nothing(tmp_path: Path) -> None:
    use_manifest(tmp_path, p3a=1)
    reg = new_registry(tmp_path / "runs.jsonl")
    spec = _spec(max_p3a_attempts=1)
    rid = open_run(reg)
    with pytest.raises(errors.PartitionNotAuthorizedError):  # refused BEFORE authorization
        auth(spec, reg, rid, requested_range=DateRange(date(2000, 1, 1), date(2000, 1, 2)))
    with pytest.raises(errors.IndependenceAuthorizationNotAcceptedError):
        auth(spec, reg, rid, independence_authorization="x")
    assert reg.attempts_consumed(rid) == 0
    assert auth(spec, reg, rid).run_id == rid  # the only attempt is still available


def test_opened_but_never_authorized_runs_consume_nothing(tmp_path: Path) -> None:
    use_manifest(tmp_path, p3a=1)
    reg = new_registry(tmp_path / "runs.jsonl")
    spec = _spec(max_p3a_attempts=1)
    abandoned = [open_run(reg) for _ in range(4)]
    for rid in abandoned:
        reg.close_run(rid, RunStatus.ABORTED, None)  # aborted BEFORE authorization
    fresh = open_run(reg)
    assert reg.attempts_consumed(fresh) == 0
    assert auth(spec, reg, fresh).run_id == fresh


def test_a_failed_run_after_authorization_still_counts_and_there_is_no_reset(
    tmp_path: Path,
) -> None:
    use_manifest(tmp_path, p3a=1)
    reg = new_registry(tmp_path / "runs.jsonl")
    spec = _spec(max_p3a_attempts=1)
    first = open_run(reg)
    auth(spec, reg, first)
    reg.close_run(first, RunStatus.FAILED, None)
    for _ in range(3):  # re-opening under new run ids, aborting, retrying: nothing resets
        rid = open_run(reg)
        with pytest.raises(errors.AttemptLimitExceededError):
            auth(spec, reg, rid)
        reg.close_run(rid, RunStatus.ABORTED, None)
    assert reg.attempts_consumed(open_run(reg)) == 1


def test_deleting_a_row_or_truncating_does_not_quietly_refund_an_attempt(tmp_path: Path) -> None:
    use_manifest(tmp_path, p3a=1)
    reg = new_registry(tmp_path / "runs.jsonl")
    spec = _spec(max_p3a_attempts=1)
    first = open_run(reg)
    auth(spec, reg, first)
    nxt = open_run(reg)
    lines = reg.path.read_bytes().split(b"\n")
    # (i) remove the capability_issued row from the middle of the chain: the chain breaks
    cap_index = next(i for i, ln in enumerate(lines) if b'"capability_issued"' in ln)
    tampered = tmp_path / "tampered.jsonl"
    tampered.write_bytes(b"\n".join(ln for i, ln in enumerate(lines) if i != cap_index))
    with pytest.raises(errors.RegistryIntegrityError):
        RunRegistry(tampered)
    # (ii) a handle that has already seen the row refuses to append onto a truncated file
    reg.path.write_bytes(b"\n".join(lines[:cap_index]) + b"\n")
    with pytest.raises(errors.RegistryIntegrityError):
        auth(spec, reg, nxt)
    # NOTE (Level 2, documented, not tested as defended): a FRESH handle on a tail-truncated
    # file sees a valid shorter chain; external anchoring of the head is design-only.


def test_concurrent_authorizations_cannot_both_take_the_last_attempt(tmp_path: Path) -> None:
    use_manifest(tmp_path, p3a=1)
    reg = new_registry(tmp_path / "runs.jsonl")
    spec = _spec(max_p3a_attempts=1)
    rids = [open_run(reg) for _ in range(6)]
    handles = [RunRegistry(reg.path) for _ in rids]  # independent handles, stale views
    barrier = threading.Barrier(len(rids))
    outcomes: list[str] = []

    def work(handle: RunRegistry, rid: str) -> None:
        barrier.wait()
        try:
            auth(spec, handle, rid)
            outcomes.append("ok")
        except errors.AttemptLimitExceededError:
            outcomes.append("refused")
        except BaseException as exc:  # pragma: no cover
            outcomes.append(repr(exc))

    threads = [
        threading.Thread(target=work, args=(h, r)) for h, r in zip(handles, rids, strict=True)
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert sorted(outcomes) == ["ok"] + ["refused"] * 5
    HashChainFile(reg.path)  # chain still valid


def test_p3b_has_its_own_window_and_budget(tmp_path: Path) -> None:
    use_manifest(tmp_path, p3a=1, p3b=1)
    reg = new_registry(tmp_path / "runs.jsonl")
    spec = _spec(max_p3a_attempts=1, max_p3b_attempts=1)
    auth(spec, reg, open_run(reg))  # P3A budget used
    complete_prereqs(reg, Phase.P3B)  # (adds its own COMPLETED P3A row for phase order)
    b1 = open_run(reg, Phase.P3B, Partition.DEVELOPMENT_CONFIRMATION)
    auth(
        spec,
        reg,
        b1,
        Phase.P3B,
        Partition.DEVELOPMENT_CONFIRMATION,
        predecessor_evidence=_evidence(reg),
    )
    b2 = open_run(reg, Phase.P3B, Partition.DEVELOPMENT_CONFIRMATION)
    with pytest.raises(errors.AttemptLimitExceededError):
        auth(
            spec,
            reg,
            b2,
            Phase.P3B,
            Partition.DEVELOPMENT_CONFIRMATION,
            predecessor_evidence=_evidence(reg),
        )


def test_registry_level_limit_is_required_and_checked_atomically(tmp_path: Path) -> None:
    reg = new_registry(tmp_path / "runs.jsonl")
    rid = open_run(reg)
    with pytest.raises(errors.AttemptLimitNotSetError):
        reg.mark_capability_issued(rid)  # no limit supplied for a P3A run: fail closed
    assert reg.get_run(rid).capability_issued_seq is None  # type: ignore[union-attr]
    other = open_run(reg, spec_sha=OTHER_SPEC)
    reg.mark_capability_issued(other, attempt_limit=1)
    with pytest.raises(errors.AttemptLimitExceededError):
        reg.mark_capability_issued(rid, attempt_limit=1)
    reg.mark_capability_issued(rid, attempt_limit=2)
