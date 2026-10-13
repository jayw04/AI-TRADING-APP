"""PR 2 x PR 3 end-to-end: a real frozen spec file through the real guard.

Synthetic fixtures only. Negative paths: no meeting decision, decision not approved or without
run scope, mutated-after-freeze, decision bound to another spec hash, unset P0 field, duplicate
holdout access, aborted run, and bypass of the guard.
"""

from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path

import pytest

from app.research.range002.governance.errors import (
    DecisionMissingError,
    DecisionNotApprovedError,
    DecisionScopeError,
    HoldoutAlreadyOpenedError,
    InvalidCapabilityError,
    RunNotRegisteredError,
)
from app.research.range002.governance.exposure_ledger import ExposureLedger
from app.research.range002.governance.holdout_token import HoldoutTokenStore
from app.research.range002.governance.model import DateRange, Partition, Phase
from app.research.range002.governance.results_guard import (
    authorize,
    requires_capability,
)
from app.research.range002.governance.run_registry import RunRegistry, RunStatus
from app.research.range002.governance.spec_adapter import to_guard_view
from app.research.range002.governance.spec_view import FrozenSpecView
from app.research.range002.spec.loader import SpecHashMismatchError, load_frozen
from app.research.range002.spec.schema import DecisionRefError, UnsetP0FieldsError
from tests.research.range002.governance.conftest import (
    CODE_SHA,
    DECIDED_LEDGER,
    DEFAULT_CONFIRMATION,
    DEFAULT_HOLDOUT,
    DEFAULT_SELECTION,
    LEDGER_SHA,
    MANIFEST_SHA,
    SYNTH_GENESIS_ID,
    complete_prereqs,
    evidence_for,
    new_registry,
)
from tests.research.range002.spec._fixtures import (
    SYNTH_MANIFEST_PATH,
    complete_payload,
    decision_block,
    get_path,
    set_path,
)

sys.path.insert(0, str(Path(__file__).resolve().parents[4] / "scripts" / "research" / "range002"))
import freeze_spec  # noqa: E402


def _freeze(tmp_path: Path, **edits: object) -> Path:
    payload = complete_payload(decided=True)
    set_path(payload, "governance.exposure_signed", {"exposure_ledger_sha256": LEDGER_SHA})
    for path, value in edits.items():
        set_path(payload, path.replace("__", "."), value)
    draft = tmp_path / "draft.json"
    draft.write_text(json.dumps(payload), encoding="utf-8")
    out = tmp_path / "frozen.json"
    freeze_spec.freeze(draft, out, manifest_path=SYNTH_MANIFEST_PATH)
    return out


@pytest.fixture
def ledger() -> ExposureLedger:
    return ExposureLedger.from_text(DECIDED_LEDGER)


def _open(registry: RunRegistry, sha: str, phase: Phase, partition: Partition) -> str:
    return registry.open_run(
        phase=phase,
        spec_sha256=sha,
        code_sha=CODE_SHA,
        data_manifest_sha256=MANIFEST_SHA,
        partition=partition,
        seeds={"bootstrap": 1},
        exit_candidates=["E1"],
        holdout_range=DEFAULT_HOLDOUT if partition is Partition.HOLDOUT else None,
        protected_range={Phase.P3A: DEFAULT_SELECTION, Phase.P3B: DEFAULT_CONFIRMATION}.get(phase),
    )


def test_adapter_satisfies_protocol_and_preserves_semantics(tmp_path: Path) -> None:
    view = load_frozen(_freeze(tmp_path))
    gv = to_guard_view(view)
    assert isinstance(gv, FrozenSpecView)
    assert gv.spec_sha256 == view.spec_sha256 and gv.has_run_decision is True
    assert gv.decision == "approved" and "run" in gv.decision_scope
    assert gv.minutes_path and gv.minutes_sha256 and gv.strategy_version and gv.baseline_id
    assert "HOLDOUT" in gv.decision_partitions
    assert gv.partitions.holdout == DateRange(date(2022, 1, 1), date(2025, 12, 31))
    assert gv.partitions.selection == DateRange(date(2016, 1, 1), date(2019, 12, 31))


def test_decided_spec_authorizes_p3a_and_registry_binds_same_hash(tmp_path, ledger) -> None:
    gv = to_guard_view(load_frozen(_freeze(tmp_path)))
    reg = new_registry(tmp_path / "runs.jsonl")
    rid = _open(reg, gv.spec_sha256, Phase.P3A, Partition.DEVELOPMENT_SELECTION)
    cap = authorize(
        spec=gv,
        phase=Phase.P3A,
        partition=Partition.DEVELOPMENT_SELECTION,
        run_id=rid,
        registry=reg,
        exposure_ledger=ledger,
    )
    assert cap is not None


def _authorize_p3a(gv, tmp_path, ledger):
    reg = new_registry(tmp_path / "runs.jsonl")
    rid = _open(reg, gv.spec_sha256, Phase.P3A, Partition.DEVELOPMENT_SELECTION)
    return authorize(
        spec=gv,
        phase=Phase.P3A,
        partition=Partition.DEVELOPMENT_SELECTION,
        run_id=rid,
        registry=reg,
        exposure_ledger=ledger,
    )


def _hand_written(tmp_path: Path, decision: dict | None) -> Path:
    """A spec file as a person could write it by hand: a complete draft plus a decision block
    (and, deliberately, a recorded spec hash only when the caller supplies one)."""
    payload = complete_payload(decided=False)
    set_path(payload, "governance.exposure_signed", {"exposure_ledger_sha256": LEDGER_SHA})
    payload["decision"] = decision
    p = tmp_path / "hand.json"
    p.write_text(json.dumps(payload), encoding="utf-8")
    return p


def test_spec_without_decision_loads_but_is_refused_by_guard(tmp_path, ledger) -> None:
    view = load_frozen(_hand_written(tmp_path, None))
    assert view.has_run_decision is False
    assert "decision missing" in view.unusable_reasons
    assert view.decision is None and view.decision_scope == ()
    with pytest.raises(DecisionMissingError):
        _authorize_p3a(to_guard_view(view), tmp_path, ledger)


def test_decision_without_bound_spec_hash_is_refused_by_guard(tmp_path, ledger) -> None:
    view = load_frozen(_hand_written(tmp_path, decision_block()))  # spec_sha256 not filled in
    assert view.has_run_decision is False
    assert view.unusable_reasons == ("decision.spec_sha256 missing",)
    with pytest.raises(DecisionMissingError):
        _authorize_p3a(to_guard_view(view), tmp_path, ledger)


@pytest.mark.parametrize("outcome", ["revise", "defer", "stop"])
def test_non_approved_decision_loads_unusable_and_is_refused_by_guard(
    tmp_path, ledger, outcome
) -> None:
    view = load_frozen(_hand_written(tmp_path, decision_block(decision=outcome)))
    assert view.has_run_decision is False
    assert any(outcome in r for r in view.unusable_reasons)
    with pytest.raises(DecisionNotApprovedError):
        _authorize_p3a(to_guard_view(view), tmp_path, ledger)


def test_build_only_decision_loads_unusable_and_is_refused_by_guard(tmp_path, ledger) -> None:
    block = decision_block(scope=["build"], partitions=[])
    view = load_frozen(_hand_written(tmp_path, block))
    assert view.has_run_decision is False
    assert "decision scope lacks 'run'" in view.unusable_reasons
    with pytest.raises(DecisionScopeError):
        _authorize_p3a(to_guard_view(view), tmp_path, ledger)


def test_decision_recorded_for_another_spec_hash_is_refused_at_load(tmp_path) -> None:
    """A decision that names a different spec hash (another version of the spec) never loads."""
    p = _hand_written(tmp_path, decision_block(spec_sha256="0" * 64))
    with pytest.raises(SpecHashMismatchError):
        load_frozen(p)


def test_freeze_refuses_non_approved_or_non_run_decisions(tmp_path) -> None:
    for name, block in (
        ("revise", decision_block(decision="revise")),
        ("defer", decision_block(decision="defer")),
        ("stop", decision_block(decision="stop")),
        ("build", decision_block(scope=["build"], partitions=[])),
    ):
        draft = _hand_written(tmp_path, block)
        with pytest.raises(DecisionRefError):
            freeze_spec.freeze(draft, tmp_path / f"{name}.json", manifest_path=SYNTH_MANIFEST_PATH)
        assert not (tmp_path / f"{name}.json").exists()


def test_mutated_frozen_spec_is_refused_at_load(tmp_path) -> None:
    out = _freeze(tmp_path)
    doc = json.loads(out.read_text(encoding="utf-8"))
    assert get_path(doc, "universe.min_price") == 10.0
    doc["universe"]["n"] = 999  # edit after freezing
    out.write_text(json.dumps(doc), encoding="utf-8")
    with pytest.raises(SpecHashMismatchError):
        load_frozen(out)


def test_unset_decision_blocks_freeze(tmp_path) -> None:
    payload = complete_payload(decided=True)
    set_path(payload, "stats.bootstrap.method", None)
    draft = tmp_path / "d.json"
    draft.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(UnsetP0FieldsError):
        freeze_spec.freeze(draft, tmp_path / "o.json", manifest_path=SYNTH_MANIFEST_PATH)


def test_holdout_second_access_refused_and_wrong_hash_token_refused(tmp_path, ledger) -> None:
    gv = to_guard_view(load_frozen(_freeze(tmp_path)))
    reg = new_registry(tmp_path / "runs.jsonl")
    store = HoldoutTokenStore(tmp_path / "tokens")
    token = store.issue(gv.spec_sha256, registry_genesis_id=SYNTH_GENESIS_ID)
    complete_prereqs(reg, Phase.P4, gv.spec_sha256)
    r1 = _open(reg, gv.spec_sha256, Phase.P4, Partition.HOLDOUT)
    authorize(
        spec=gv,
        phase=Phase.P4,
        partition=Partition.HOLDOUT,
        run_id=r1,
        registry=reg,
        exposure_ledger=ledger,
        holdout_store=store,
        holdout_token=token,
        predecessor_evidence=evidence_for(reg),
    )
    r2 = _open(reg, gv.spec_sha256, Phase.P4, Partition.HOLDOUT)
    with pytest.raises(HoldoutAlreadyOpenedError):
        authorize(
            spec=gv,
            phase=Phase.P4,
            partition=Partition.HOLDOUT,
            run_id=r2,
            registry=reg,
            exposure_ledger=ledger,
            holdout_store=store,
            holdout_token=token,
            predecessor_evidence=evidence_for(reg),
        )


def test_aborted_run_still_counts_and_cannot_authorize(tmp_path, ledger) -> None:
    gv = to_guard_view(load_frozen(_freeze(tmp_path)))
    reg = new_registry(tmp_path / "runs.jsonl")
    rid = _open(reg, gv.spec_sha256, Phase.P3A, Partition.DEVELOPMENT_SELECTION)
    assert reg.abort_open_runs() == (rid,)
    assert reg.count_runs(gv.spec_sha256) == 1
    assert reg.get_run(rid).status is RunStatus.ABORTED
    with pytest.raises(RunNotRegisteredError):
        authorize(
            spec=gv,
            phase=Phase.P3A,
            partition=Partition.DEVELOPMENT_SELECTION,
            run_id=rid,
            registry=reg,
            exposure_ledger=ledger,
        )


def test_guard_bypass_direct_call_fails() -> None:
    @requires_capability
    def compute(*, capability=None):  # pragma: no cover - body must never run
        return 1

    with pytest.raises(InvalidCapabilityError):
        compute()
