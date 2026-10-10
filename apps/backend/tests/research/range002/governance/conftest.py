"""Synthetic fixtures only. Nothing here is a real RANGE-002 spec or ledger value.

Specs reach the guard through the SAME path as production: a synthetic frozen file is written
by ``freeze_spec.freeze`` and loaded by ``load_frozen`` (the only minter of a trusted
``SpecView``), then ``to_guard_view``. ``forge_guard_view`` is a test-only escape hatch that
uses the adapter's private token; it exists solely to exercise the guard's defensive branches
(a malformed sha, an unset D17/D19 field, odd ``is_signed`` values, a different spec hash) that
the real load path cannot produce here. Production code has no equivalent.
"""

from __future__ import annotations

import hashlib
import json
import sys
import tempfile
from collections.abc import Iterator
from datetime import date
from functools import cache
from pathlib import Path
from typing import Any
from unittest import mock

import pytest

from app.research.range002.governance import results_guard, run_registry, spec_adapter
from app.research.range002.governance.evidence import audit_pack_header
from app.research.range002.governance.exposure_ledger import ExposureLedger
from app.research.range002.governance.holdout_token import HoldoutToken, HoldoutTokenStore
from app.research.range002.governance.model import DateRange, Partition, Phase
from app.research.range002.governance.results_guard import PredecessorEvidence
from app.research.range002.governance.run_registry import RunRegistry, RunStatus
from app.research.range002.governance.spec_adapter import GuardSpecView, to_guard_view
from app.research.range002.spec.loader import SpecSchemaError, SpecView, load_frozen
from app.research.range002.spec.schema import UnsetP0FieldsError
from tests.research.range002.spec._fixtures import (
    SYNTH_GENESIS_ID,
    SYNTH_MANIFEST_PATH,
    SYNTH_P3A_LIMIT,
    SYNTH_P3B_LIMIT,
    complete_payload,
    set_path,
)

sys.path.insert(0, str(Path(__file__).resolve().parents[4] / "scripts" / "research" / "range002"))
import freeze_spec  # noqa: E402

CODE_SHA = "b" * 40
MANIFEST_SHA = "c" * 64
DEFAULT_HOLDOUT = DateRange(date(2022, 1, 1), date(2025, 12, 31))
DEFAULT_SELECTION = DateRange(*[date.fromisoformat(d) for d in ("2016-01-01", "2019-12-31")])
DEFAULT_CONFIRMATION = DateRange(*[date.fromisoformat(d) for d in ("2020-01-01", "2021-12-31")])

_LEDGER_DOC = {
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
SIGNED_LEDGER = json.dumps(_LEDGER_DOC, indent=2)
UNSIGNED_LEDGER = json.dumps({**_LEDGER_DOC, "signoff": None}, indent=2)

LEDGER_SHA = ExposureLedger.from_text(SIGNED_LEDGER).sha256
_DEFAULT_BINDING = json.dumps({"exposure_ledger_sha256": LEDGER_SHA})


_DEFAULT = object()


def load_synthetic_view(
    directory: Path, *, signed: bool = True, exposure_signed: Any = _DEFAULT
) -> SpecView:
    """Write a synthetic spec file and load it with the REAL loader (``load_frozen``)."""
    payload = complete_payload(signed=signed)
    binding = (
        {"exposure_ledger_sha256": LEDGER_SHA} if exposure_signed is _DEFAULT else exposure_signed
    )
    set_path(payload, "governance.exposure_signed", binding)
    draft = directory / "draft.json"
    draft.write_text(json.dumps(payload), encoding="utf-8")
    if not signed:
        return load_frozen(draft)
    out = directory / "frozen.json"
    freeze_spec.freeze(draft, out, manifest_path=SYNTH_MANIFEST_PATH)
    return load_frozen(out)


@cache
def _default_guard_fields(exposure_json: str) -> dict[str, Any]:
    with tempfile.TemporaryDirectory() as tmp:
        view = load_synthetic_view(Path(tmp), exposure_signed=json.loads(exposure_json))
        gv = to_guard_view(view)
    return {
        "spec_sha256": gv.spec_sha256,
        "is_signed": gv.is_signed,
        "partitions": {
            "development_selection": (gv.partitions.selection.start, gv.partitions.selection.end),
            "development_confirmation": (
                gv.partitions.confirmation.start,
                gv.partitions.confirmation.end,
            ),
            "holdout": (gv.partitions.holdout.start, gv.partitions.holdout.end),
        },
        "exposed_windows": tuple((w.start, w.end) for w in gv.exposed),
        "p3_criteria": gv.p3_criteria,
        "exits_candidates": gv.exits_candidates,
        "exits_selection": gv.exits_selection,
        "exposure_signed": gv.exposure_signed,
        "registry_genesis_id": gv.registry_genesis_id,
        "max_p3a_attempts": gv.max_p3a_attempts,
        "max_p3b_attempts": gv.max_p3b_attempts,
    }


def new_registry(path: Path, *, genesis_id: str = SYNTH_GENESIS_ID) -> RunRegistry:
    """TEST-ONLY: enroll a registry whose genesis id is the synthetic spec's.

    Production ``RunRegistry.enroll_new`` always draws a ``uuid.uuid4()`` id. The id source is
    patched only for the duration of this call so the synthetic frozen spec (whose
    ``governance.registry_genesis_id`` is a fixed constant) matches. A test that needs a
    NON-matching registry calls ``RunRegistry.enroll_new`` directly.
    """
    with mock.patch.object(run_registry, "_new_genesis_id", return_value=genesis_id):
        return RunRegistry.enroll_new(path, enrolled_by="synthetic-test-owner")


SPEC_SHA: str = _default_guard_fields(_DEFAULT_BINDING)["spec_sha256"]


def forge_guard_view(**changes: Any) -> GuardSpecView:
    """TEST-ONLY: a GuardSpecView with arbitrary fields, minted with the adapter's private token.

    Defaults are the real synthetic spec's fields; ``changes`` use the ``SpecView`` field names.
    """
    fields = dict(_default_guard_fields(_DEFAULT_BINDING))
    fields.update(changes)
    parts = fields["partitions"]
    return GuardSpecView(
        spec_adapter._ISSUE_VIEW,
        spec_sha256=fields["spec_sha256"],
        is_signed=fields["is_signed"],
        partitions=spec_adapter._Partitions(
            selection=DateRange(*parts["development_selection"]),
            confirmation=DateRange(*parts["development_confirmation"]),
            holdout=DateRange(*parts["holdout"]),
        ),
        p3_criteria=fields["p3_criteria"],
        exits_candidates=fields["exits_candidates"],
        exits_selection=fields["exits_selection"],
        exposed=tuple(DateRange(s, e) for s, e in fields["exposed_windows"]),
        exposure_signed=fields["exposure_signed"],
        registry_genesis_id=fields["registry_genesis_id"],
        max_p3a_attempts=fields["max_p3a_attempts"],
        max_p3b_attempts=fields["max_p3b_attempts"],
    )


def make_spec(**changes: Any) -> GuardSpecView:
    """A synthetic spec. Only ``exposure_signed`` varies through the real load path; every other
    override goes through the test-only :func:`forge_guard_view`."""
    if not changes:
        return forge_guard_view()
    if set(changes) == {"exposure_signed"}:
        try:
            with tempfile.TemporaryDirectory() as tmp:
                return to_guard_view(
                    load_synthetic_view(Path(tmp), exposure_signed=changes["exposure_signed"])
                )
        except (UnsetP0FieldsError, SpecSchemaError):
            pass  # a binding the real schema refuses: exercise the guard's own check instead
    return forge_guard_view(**changes)


def spec_for(ledger: ExposureLedger, **changes: Any) -> GuardSpecView:
    """A synthetic spec whose exposure binding names ``ledger``."""
    return make_spec(exposure_signed={"exposure_ledger_sha256": ledger.sha256}, **changes)


@pytest.fixture(autouse=True)
def synthetic_manifest() -> Iterator[Path]:
    """Point the guard's private test seam at the synthetic APPROVED manifest. Production reads
    only the committed (unset) manifest; a test wanting that state sets the seam to None itself.
    Set directly (not via monkeypatch) so a test's ``monkeypatch.undo()`` does not unset it."""
    saved = results_guard._MANIFEST_PATH
    results_guard._MANIFEST_PATH = SYNTH_MANIFEST_PATH
    try:
        yield SYNTH_MANIFEST_PATH
    finally:
        results_guard._MANIFEST_PATH = saved


def use_manifest(
    directory: Path,
    *,
    p3a: int | None = SYNTH_P3A_LIMIT,
    p3b: int | None = SYNTH_P3B_LIMIT,
    **kw: Any,
) -> Path:
    """Write a synthetic manifest (default: approved SYNTH genesis) with the given limits and point
    the guard's test seam at it for the rest of the test (the autouse fixture restores it)."""
    from tests.research.range002.spec._fixtures import synthetic_manifest_payload, write_manifest

    payload = synthetic_manifest_payload(p3_attempt_limits={"p3a": p3a, "p3b": p3b}, **kw)
    path = write_manifest(directory / "manifest_override.json", payload)
    results_guard._MANIFEST_PATH = path
    return path


@pytest.fixture
def spec() -> GuardSpecView:
    with tempfile.TemporaryDirectory() as tmp:
        return to_guard_view(load_synthetic_view(Path(tmp)))


@pytest.fixture
def ledger() -> ExposureLedger:
    return ExposureLedger.from_text(SIGNED_LEDGER)


@pytest.fixture
def registry(tmp_path: Path) -> RunRegistry:
    return new_registry(tmp_path / "runs.jsonl")


@pytest.fixture
def store(tmp_path: Path) -> HoldoutTokenStore:
    return HoldoutTokenStore(tmp_path / "tokens")


def issue_token(store: HoldoutTokenStore, spec_sha: str = "") -> HoldoutToken:
    """Issue the single holdout token for ``spec_sha`` (default: the synthetic spec) paired with
    the synthetic registry genesis id."""
    return store.issue(spec_sha or SPEC_SHA, registry_genesis_id=SYNTH_GENESIS_ID)


def open_run(
    registry: RunRegistry,
    phase: Phase = Phase.P3A,
    partition: Partition = Partition.DEVELOPMENT_SELECTION,
    spec_sha: str = SPEC_SHA,
    holdout_range: DateRange | None = None,
    protected_range: DateRange | None = None,
) -> str:
    if partition is Partition.HOLDOUT and holdout_range is None:
        holdout_range = DEFAULT_HOLDOUT
    if phase is Phase.P3A and protected_range is None:
        protected_range = DEFAULT_SELECTION
    if phase is Phase.P3B and protected_range is None:
        protected_range = DEFAULT_CONFIRMATION
    return registry.open_run(
        phase=phase,
        spec_sha256=spec_sha,
        code_sha=CODE_SHA,
        data_manifest_sha256=MANIFEST_SHA,
        partition=partition,
        seeds={"bootstrap": 1},
        exit_candidates=["E1", "E2a"],
        holdout_range=holdout_range,
        protected_range=protected_range,
    )


def _evidence_dir(registry: RunRegistry) -> Path:
    directory = registry.path.parent / "evidence"
    directory.mkdir(exist_ok=True)
    return directory


def complete_run(
    registry: RunRegistry, run_id: str, selection: dict[str, Any] | None = None
) -> None:
    """Close ``run_id`` COMPLETED with a real audit-pack file (and selection record file).

    The pack embeds the round-4 header (run id + spec hash); the selection record is bound to
    its run the same way. ``mark_capability_issued`` stands in for the ``authorize`` call that
    a real run would have made (``close_run(COMPLETED)`` refuses a run with no such row).
    """
    directory = _evidence_dir(registry)
    run = registry.get_run(run_id)
    assert run is not None
    pack = audit_pack_header(run_id, run.spec_sha256) + f"synthetic audit pack {run_id}".encode()
    (directory / f"{run_id}.audit").write_bytes(pack)
    if selection is not None:
        body = {**selection, "run_id": run_id, "spec_sha256": run.spec_sha256}
        registry.record_selection(run_id, body)
        (directory / f"{run_id}.selection.json").write_text(json.dumps(body), encoding="utf-8")
    if run.capability_issued_seq is None:
        registry.mark_capability_issued(
            run_id, attempt_limit=SYNTH_P3A_LIMIT if run.phase is Phase.P3A else SYNTH_P3B_LIMIT
        )
    registry.close_run(run_id, RunStatus.COMPLETED, hashlib.sha256(pack).hexdigest())


def evidence_for(registry: RunRegistry) -> list[PredecessorEvidence]:
    """Evidence files for every COMPLETED run that has them on disk (the guard filters by spec)."""
    directory = _evidence_dir(registry)
    out: list[PredecessorEvidence] = []
    for run in registry.runs():
        audit = directory / f"{run.run_id}.audit"
        if run.status is RunStatus.COMPLETED and audit.exists():
            sel = directory / f"{run.run_id}.selection.json"
            out.append(PredecessorEvidence(run.run_id, audit, sel if sel.exists() else None))
    return out


def complete_prereqs(registry: RunRegistry, upto: Phase, spec_sha: str = SPEC_SHA) -> None:
    """Idempotently put registry rows AND evidence files for phase order in place: a COMPLETED P3A
    with a selection record; for P4/P5 also a COMPLETED P3B; for P5 also a COMPLETED P4."""
    runs = [r for r in registry.runs() if r.spec_sha256 == spec_sha]

    def have(phase: Phase) -> bool:
        return any(
            r.phase is phase
            and r.status is RunStatus.COMPLETED
            and (phase is not Phase.P3A or r.selection_record_seq is not None)
            for r in runs
        )

    if not have(Phase.P3A):
        p3a = open_run(registry, Phase.P3A, Partition.DEVELOPMENT_SELECTION, spec_sha)
        complete_run(registry, p3a, {"selected": "E1"})
    if upto in (Phase.P4, Phase.P5) and not have(Phase.P3B):
        p3b = open_run(registry, Phase.P3B, Partition.DEVELOPMENT_CONFIRMATION, spec_sha)
        complete_run(registry, p3b)
    if upto is Phase.P5 and not have(Phase.P4):
        p4 = open_run(registry, Phase.P4, Partition.HOLDOUT, spec_sha)
        complete_run(registry, p4)
