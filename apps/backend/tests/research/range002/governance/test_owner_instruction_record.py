"""Owner-instruction record (2026-10-12): an explicit between-meeting instruction by the owner is
a decision record of ``record_kind == "owner_instruction"``. It carries the SAME scope/version
binding and gets the SAME checks as a ``meeting_minutes`` record; there is no default kind.

Synthetic fixtures only.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import pytest

from app.research.range002.governance.errors import (
    DecisionMinutesMismatchError,
    DecisionMissingError,
    DecisionNotApprovedError,
    DecisionPartitionError,
    DecisionScopeError,
    ExposureLedgerError,
)
from app.research.range002.governance.exposure_ledger import ExposureLedger
from app.research.range002.governance.model import Partition, Phase
from app.research.range002.governance.results_guard import authorize
from app.research.range002.governance.spec_adapter import to_guard_view
from app.research.range002.spec import decision as decision_module
from app.research.range002.spec.loader import SpecHashMismatchError, SpecSchemaError, load_frozen
from app.research.range002.spec.schema import DecisionRefError
from tests.research.range002.governance.conftest import (
    DECIDED_LEDGER,
    forge_guard_view,
    new_registry,
)
from tests.research.range002.governance.test_spec_integration import _open
from tests.research.range002.spec._fixtures import (
    MINUTES_BYTES,
    MINUTES_RELPATH,
    SYNTH_MANIFEST_PATH,
    complete_payload,
    decision_block,
    set_path,
)

sys.path.insert(0, str(Path(__file__).resolve().parents[4] / "scripts" / "research" / "range002"))
import freeze_spec  # noqa: E402

KINDS = ["meeting_minutes", "owner_instruction"]


def _draft(
    tmp_path: Path, kind: str | None, *, ledger_kind: str = "meeting_minutes", **block: Any
) -> Path:
    _ledger_sha = _ledger(ledger_kind).sha256
    payload = complete_payload(decided=False)
    set_path(payload, "governance.exposure_signed", {"exposure_ledger_sha256": _ledger_sha})
    d = decision_block(**block)
    if kind is None:
        del d["record_kind"]
    else:
        d["record_kind"] = kind
    payload["decision"] = d
    p = tmp_path / "draft.json"
    p.write_text(json.dumps(payload), encoding="utf-8")
    return p


def _freeze(tmp_path: Path, kind: str, **block: Any) -> Path:
    out = tmp_path / "frozen.json"
    ledger_kind = block.pop("ledger_kind", kind)
    draft = _draft(tmp_path, kind, ledger_kind=ledger_kind, **block)
    freeze_spec.freeze(draft, out, manifest_path=SYNTH_MANIFEST_PATH)
    return out


def _ledger(kind: str) -> ExposureLedger:
    doc = json.loads(DECIDED_LEDGER)
    doc["decision"]["record_kind"] = kind
    return ExposureLedger.from_text(json.dumps(doc))


def _authorize(gv: Any, tmp_path: Path, kind: str) -> Any:
    reg = new_registry(tmp_path / "runs.jsonl")
    rid = _open(reg, gv.spec_sha256, Phase.P3A, Partition.DEVELOPMENT_SELECTION)
    return authorize(
        spec=gv,
        phase=Phase.P3A,
        partition=Partition.DEVELOPMENT_SELECTION,
        run_id=rid,
        registry=reg,
        exposure_ledger=_ledger(kind),
    )


@pytest.mark.parametrize("kind", KINDS)
def test_accepted_by_loader_freeze_guard_and_ledger(tmp_path: Path, kind: str) -> None:
    view = load_frozen(_freeze(tmp_path, kind))
    assert view.has_run_decision is True and view.record_kind == kind
    gv = to_guard_view(view)
    assert gv.record_kind == kind
    assert _authorize(gv, tmp_path, kind) is not None
    assert _ledger(kind).require_decision()["record_kind"] == kind


def test_spec_hash_is_independent_of_record_kind(tmp_path: Path) -> None:
    """DecisionRef is outside the hashed payload: the two kinds freeze to the same digest."""
    digests = []
    for kind in KINDS:
        d = tmp_path / kind
        d.mkdir()
        digests.append(load_frozen(_freeze(d, kind, ledger_kind="meeting_minutes")).spec_sha256)
    assert digests[0] == digests[1]


@pytest.mark.parametrize("kind", KINDS)
@pytest.mark.parametrize("outcome", ["revise", "defer", "stop"])
def test_non_approved_refused_identically(tmp_path: Path, kind: str, outcome: str) -> None:
    draft = _draft(tmp_path, kind, decision=outcome)
    with pytest.raises(DecisionRefError):
        freeze_spec.freeze(draft, tmp_path / "f.json", manifest_path=SYNTH_MANIFEST_PATH)
    view = load_frozen(draft)
    assert view.has_run_decision is False
    with pytest.raises(DecisionNotApprovedError):
        _authorize(to_guard_view(view), tmp_path, kind)


@pytest.mark.parametrize("kind", KINDS)
def test_build_only_scope_refused_identically(tmp_path: Path, kind: str) -> None:
    draft = _draft(tmp_path, kind, scope=["build"], partitions=[])
    with pytest.raises(DecisionRefError):
        freeze_spec.freeze(draft, tmp_path / "f.json", manifest_path=SYNTH_MANIFEST_PATH)
    with pytest.raises(DecisionScopeError):
        _authorize(to_guard_view(load_frozen(draft)), tmp_path, kind)


@pytest.mark.parametrize("kind", KINDS)
def test_partition_not_covered_refused_identically(tmp_path: Path, kind: str) -> None:
    gv = to_guard_view(load_frozen(_freeze(tmp_path, kind, partitions=["HOLDOUT"])))
    with pytest.raises(DecisionPartitionError):
        _authorize(gv, tmp_path, kind)


@pytest.mark.parametrize("kind", KINDS)
def test_minutes_edited_after_decision_refused_identically(
    tmp_path: Path, kind: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "root"
    target = root / MINUTES_RELPATH
    target.parent.mkdir(parents=True)
    target.write_bytes(MINUTES_BYTES)
    monkeypatch.setattr(decision_module, "_MINUTES_ROOT", root)
    gv = to_guard_view(load_frozen(_freeze(tmp_path, kind)))
    target.write_bytes(MINUTES_BYTES + b"edited after the decision\n")
    with pytest.raises(DecisionMinutesMismatchError):
        _authorize(gv, tmp_path, kind)


@pytest.mark.parametrize("kind", KINDS)
def test_minutes_hash_mismatch_refused_by_freeze_tool(tmp_path: Path, kind: str) -> None:
    draft = _draft(tmp_path, kind, minutes_sha256="0" * 64)
    with pytest.raises(DecisionRefError):
        freeze_spec.freeze(draft, tmp_path / "f.json", manifest_path=SYNTH_MANIFEST_PATH)


@pytest.mark.parametrize("kind", KINDS)
def test_spec_edited_after_freeze_refused(tmp_path: Path, kind: str) -> None:
    out = _freeze(tmp_path, kind)
    doc = json.loads(out.read_text(encoding="utf-8"))
    doc["universe"]["n"] = 999
    out.write_text(json.dumps(doc), encoding="utf-8")
    with pytest.raises(SpecHashMismatchError):
        load_frozen(out)


@pytest.mark.parametrize("kind", KINDS)
def test_future_decision_date_refused_for_both_kinds(tmp_path: Path, kind: str) -> None:
    draft = _draft(tmp_path, kind, decision_date="2999-01-01")
    with pytest.raises(DecisionRefError, match="future"):
        freeze_spec.freeze(draft, tmp_path / "f.json", manifest_path=SYNTH_MANIFEST_PATH)


@pytest.mark.parametrize("bad", ["owner", "owner-instruction", "MEETING_MINUTES", "", "email"])
def test_unknown_record_kind_refused(tmp_path: Path, bad: str) -> None:
    draft = _draft(tmp_path, bad)
    with pytest.raises(SpecSchemaError):
        load_frozen(draft)
    with pytest.raises(SpecSchemaError):
        freeze_spec.freeze(draft, tmp_path / "f.json", manifest_path=SYNTH_MANIFEST_PATH)
    assert not (tmp_path / "f.json").exists()


def test_missing_record_kind_refused_no_default(tmp_path: Path) -> None:
    draft = _draft(tmp_path, None)
    with pytest.raises(SpecSchemaError, match="record_kind"):
        load_frozen(draft)
    with pytest.raises(SpecSchemaError, match="record_kind"):
        freeze_spec.freeze(draft, tmp_path / "f.json", manifest_path=SYNTH_MANIFEST_PATH)


def test_ledger_unknown_or_missing_record_kind_refused() -> None:
    doc = json.loads(DECIDED_LEDGER)
    doc["decision"]["record_kind"] = "verbal"
    with pytest.raises(ExposureLedgerError):
        ExposureLedger.from_text(json.dumps(doc))
    del doc["decision"]["record_kind"]
    with pytest.raises(ExposureLedgerError):
        ExposureLedger.from_text(json.dumps(doc))


@pytest.mark.parametrize("bad", [None, "owner", ""])
def test_guard_refuses_a_view_carrying_an_unknown_kind(bad: Any, tmp_path: Path) -> None:
    reg = new_registry(tmp_path / "runs.jsonl")
    gv = forge_guard_view(record_kind=bad)
    rid = _open(reg, gv.spec_sha256, Phase.P3A, Partition.DEVELOPMENT_SELECTION)
    with pytest.raises(DecisionMissingError, match="record_kind"):
        authorize(
            spec=gv,
            phase=Phase.P3A,
            partition=Partition.DEVELOPMENT_SELECTION,
            run_id=rid,
            registry=reg,
            exposure_ledger=_ledger("meeting_minutes"),
        )
