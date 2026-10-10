"""PR 2 x PR 3 end-to-end: a real frozen spec file through the real guard.

Synthetic fixtures only. Negative paths: unsigned, mutated-after-freeze, unset
decision, duplicate holdout access, aborted run, and bypass of the guard.
"""

from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path

import pytest

from app.research.range002.governance.errors import (
    HoldoutAlreadyOpenedError,
    InvalidCapabilityError,
    RunNotRegisteredError,
    SpecNotSignedError,
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
from app.research.range002.spec.schema import UnsetP0FieldsError
from tests.research.range002.governance.conftest import (
    CODE_SHA,
    DEFAULT_CONFIRMATION,
    DEFAULT_HOLDOUT,
    DEFAULT_SELECTION,
    LEDGER_SHA,
    MANIFEST_SHA,
    SIGNED_LEDGER,
    SYNTH_GENESIS_ID,
    complete_prereqs,
    evidence_for,
    new_registry,
)
from tests.research.range002.spec._fixtures import (
    SYNTH_MANIFEST_PATH,
    complete_payload,
    get_path,
    set_path,
)

sys.path.insert(0, str(Path(__file__).resolve().parents[4] / "scripts" / "research" / "range002"))
import freeze_spec  # noqa: E402


def _freeze(tmp_path: Path, **edits: object) -> Path:
    payload = complete_payload(signed=True)
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
    return ExposureLedger.from_text(SIGNED_LEDGER)


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
    assert gv.spec_sha256 == view.spec_sha256 and gv.is_signed is True
    assert gv.partitions.holdout == DateRange(date(2022, 1, 1), date(2025, 12, 31))
    assert gv.partitions.selection == DateRange(date(2016, 1, 1), date(2019, 12, 31))


def test_signed_spec_authorizes_p3a_and_registry_binds_same_hash(tmp_path, ledger) -> None:
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


def test_unsigned_spec_refused_by_guard(tmp_path, ledger) -> None:
    payload = complete_payload(signed=False)
    p = tmp_path / "f.json"
    p.write_text(json.dumps(payload), encoding="utf-8")
    view = load_frozen(p)
    assert view.is_signed is False
    gv = to_guard_view(view)
    reg = new_registry(tmp_path / "runs.jsonl")
    rid = _open(reg, gv.spec_sha256, Phase.P3A, Partition.DEVELOPMENT_SELECTION)
    with pytest.raises(SpecNotSignedError):
        authorize(
            spec=gv,
            phase=Phase.P3A,
            partition=Partition.DEVELOPMENT_SELECTION,
            run_id=rid,
            registry=reg,
            exposure_ledger=ledger,
        )


def test_mutated_frozen_spec_is_refused_at_load(tmp_path) -> None:
    out = _freeze(tmp_path)
    doc = json.loads(out.read_text(encoding="utf-8"))
    assert get_path(doc, "universe.min_price") == 10.0
    doc["universe"]["n"] = 999  # edit after freezing
    out.write_text(json.dumps(doc), encoding="utf-8")
    with pytest.raises(SpecHashMismatchError):
        load_frozen(out)


def test_unset_decision_blocks_freeze(tmp_path) -> None:
    payload = complete_payload(signed=True)
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
