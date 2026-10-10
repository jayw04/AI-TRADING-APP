from __future__ import annotations

import copy
import pickle
from datetime import date
from typing import Any

import pytest

from app.research.range002.governance.errors import (
    ExposureLedgerNotSignedError,
    ExposureOverlapError,
    HoldoutAlreadyOpenedError,
    HoldoutTokenInvalidError,
    InvalidCapabilityError,
    PaperApprovalNotImplementedError,
    PaperRangeNotAfterR2Error,
    PartitionNotAuthorizedError,
    RunNotRegisteredError,
    SpecIncompleteError,
    SpecNotFrozenError,
    SpecNotSignedError,
    SpecViewNotTrustedError,
)
from app.research.range002.governance.exposure_ledger import ExposureLedger
from app.research.range002.governance.holdout_token import HoldoutTokenStore, TokenState
from app.research.range002.governance.model import (
    R2_EXCLUDED_WINDOW,
    DateRange,
    Partition,
    Phase,
)
from app.research.range002.governance.results_guard import (
    ResultsCapability,
    _check_free_range,
    authorize,
    require_capability,
    requires_capability,
)
from app.research.range002.governance.run_registry import RunRegistry, RunStatus
from app.research.range002.governance.spec_adapter import GuardSpecView

from .conftest import (
    SPEC_SHA,
    SYNTH_GENESIS_ID,
    UNSIGNED_LEDGER,
    complete_prereqs,
    evidence_for,
    make_spec,
    new_registry,
    open_run,
    spec_for,
)


def go(
    spec: Any,
    registry: RunRegistry,
    ledger: ExposureLedger,
    phase: Phase = Phase.P3A,
    partition: Partition = Partition.DEVELOPMENT_SELECTION,
    run_id: str | None = None,
    **kw: Any,
) -> ResultsCapability:
    sha = getattr(spec, "spec_sha256", SPEC_SHA)
    if not (isinstance(sha, str) and len(sha) == 64 and sha == sha.lower()):
        sha = SPEC_SHA
    if phase in (Phase.P3B, Phase.P4, Phase.P5):
        complete_prereqs(registry, phase, sha)
    rid = run_id or open_run(registry, phase, partition, sha)
    kw.setdefault("predecessor_evidence", evidence_for(registry))
    return authorize(
        spec=spec,
        phase=phase,
        partition=partition,
        run_id=rid,
        registry=registry,
        exposure_ledger=ledger,
        **kw,
    )


# --- happy paths ---------------------------------------------------------------


def test_p3a_authorized(spec: GuardSpecView, registry: RunRegistry, ledger: ExposureLedger) -> None:
    cap = go(spec, registry, ledger)
    assert cap.spec_sha256 == SPEC_SHA
    assert cap.partition is Partition.DEVELOPMENT_SELECTION
    assert cap.phase is Phase.P3A
    assert cap.citable is True
    assert cap.date_range == spec.partitions.selection
    assert cap.exposure_ledger_sha256 == ledger.sha256
    assert require_capability(cap) is cap


def test_p3b_authorized_and_paper_refused_outright(
    spec: GuardSpecView, registry: RunRegistry, ledger: ExposureLedger
) -> None:
    cap = go(spec, registry, ledger, Phase.P3B, Partition.DEVELOPMENT_CONFIRMATION)
    assert cap.partition is Partition.DEVELOPMENT_CONFIRMATION
    # Round 4 (N2f): owner approval before paper is Level 2 design-only, so P5 is refused even
    # with every other precondition in place (completed P3A/P3B/P4, valid range).
    with pytest.raises(PaperApprovalNotImplementedError):
        go(
            spec,
            registry,
            ledger,
            Phase.P5,
            Partition.PAPER,
            requested_range=DateRange(date(2026, 9, 1), date(2026, 12, 31)),
        )


def test_subrange_allowed_and_recorded(
    spec: GuardSpecView, registry: RunRegistry, ledger: ExposureLedger
) -> None:
    sub = DateRange(date(2017, 1, 1), date(2017, 6, 30))
    assert go(spec, registry, ledger, requested_range=sub).date_range == sub


def test_determinism_same_inputs_same_capability_fields(
    spec: GuardSpecView, tmp_path: Any, ledger: ExposureLedger
) -> None:
    caps = []
    for name in ("x", "y"):
        reg = new_registry(tmp_path / name / "runs.jsonl")
        caps.append(go(spec, reg, ledger))
    a, b = caps
    for f in ("spec_sha256", "phase", "partition", "run_id", "date_range", "citable"):
        assert getattr(a, f) == getattr(b, f)


def test_determinism_refusals_repeat(
    spec: GuardSpecView, registry: RunRegistry, ledger: ExposureLedger
) -> None:
    bad = make_spec(is_signed=False)
    for _ in range(3):
        with pytest.raises(SpecNotSignedError):
            go(bad, registry, ledger)


# --- (a) frozen and signed -----------------------------------------------------


@pytest.mark.parametrize("sha", ["", "xyz", "A" * 64, "a" * 63, None, 5])
def test_unfrozen_spec_refused(
    spec: GuardSpecView, registry: RunRegistry, ledger: ExposureLedger, sha: Any
) -> None:
    with pytest.raises(SpecNotFrozenError):
        go(make_spec(spec_sha256=sha), registry, ledger, run_id="whatever")


@pytest.mark.parametrize("signed", [False, None, "yes", 1])
def test_unsigned_spec_refused(
    spec: GuardSpecView, registry: RunRegistry, ledger: ExposureLedger, signed: Any
) -> None:
    with pytest.raises(SpecNotSignedError):
        go(make_spec(is_signed=signed), registry, ledger, run_id="whatever")


def test_missing_attributes_fail_closed(registry: RunRegistry, ledger: ExposureLedger) -> None:
    class Bare:  # not a spec at all
        pass

    with pytest.raises(SpecViewNotTrustedError):
        go(Bare(), registry, ledger, run_id="x")
    with pytest.raises(SpecViewNotTrustedError):
        go(None, registry, ledger, run_id="x")


# --- (b) partition / phase -----------------------------------------------------


def test_unknown_partition_or_phase_refused(
    spec: GuardSpecView, registry: RunRegistry, ledger: ExposureLedger
) -> None:
    with pytest.raises(PartitionNotAuthorizedError):
        go(spec, registry, ledger, partition="TEST_SET", run_id="x")  # type: ignore[arg-type]
    with pytest.raises(PartitionNotAuthorizedError):
        go(spec, registry, ledger, phase="P9", run_id="x")  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("phase", "partition"),
    [
        (Phase.P3A, Partition.HOLDOUT),
        (Phase.P3A, Partition.DEVELOPMENT_CONFIRMATION),
        (Phase.P3B, Partition.DEVELOPMENT_SELECTION),
        (Phase.P4, Partition.DEVELOPMENT_SELECTION),
        (Phase.P5, Partition.HOLDOUT),
        (Phase.P2, Partition.DEVELOPMENT_SELECTION),
        (Phase.P3A, Partition.REPLAY_RNG001),
    ],
)
def test_partition_not_authorized_for_phase(
    spec: GuardSpecView,
    registry: RunRegistry,
    ledger: ExposureLedger,
    phase: Phase,
    partition: Partition,
) -> None:
    with pytest.raises(PartitionNotAuthorizedError, match="not authorized for phase"):
        go(spec, registry, ledger, phase, partition, run_id="x")


def test_requested_range_outside_spec_partition_refused(
    spec: GuardSpecView, registry: RunRegistry, ledger: ExposureLedger
) -> None:
    out = DateRange(date(2019, 6, 1), date(2020, 6, 1))
    with pytest.raises(PartitionNotAuthorizedError, match="outside"):
        go(spec, registry, ledger, requested_range=out)


def test_ranged_less_partitions_need_explicit_range(
    spec: GuardSpecView, registry: RunRegistry, ledger: ExposureLedger
) -> None:
    with pytest.raises(PartitionNotAuthorizedError, match="requested_range"):
        go(spec, registry, ledger, Phase.P2, Partition.REPLAY_RNG001)


# --- (f) development criteria --------------------------------------------------


@pytest.mark.parametrize("missing", ["p3_criteria", "exits_candidates", "exits_selection"])
@pytest.mark.parametrize(
    ("phase", "partition"),
    [
        (Phase.P3A, Partition.DEVELOPMENT_SELECTION),
        (Phase.P3B, Partition.DEVELOPMENT_CONFIRMATION),
    ],
)
def test_development_refused_while_criteria_unset(
    spec: GuardSpecView,
    registry: RunRegistry,
    ledger: ExposureLedger,
    missing: str,
    phase: Phase,
    partition: Partition,
) -> None:
    with pytest.raises(SpecIncompleteError, match=missing):
        go(make_spec(**{missing: None}), registry, ledger, phase, partition)


# --- (c) exposure ----------------------------------------------------------------


def test_r2_window_never_authorized_even_if_spec_and_ledger_are_silent(
    registry: RunRegistry,
) -> None:
    empty_signed = ExposureLedger.from_text(
        '{"schema_version": 1, "signoff": {"signed_by": "s", "signed_on": "2026-10-01"},'
        ' "entries": []}'
    )
    spec = spec_for(empty_signed, exposed_windows=())
    rng = DateRange(R2_EXCLUDED_WINDOW.start, R2_EXCLUDED_WINDOW.end)
    with pytest.raises((ExposureOverlapError, PartitionNotAuthorizedError)):
        go(
            spec,
            registry,
            empty_signed,
            Phase.P3A,
            Partition.DEVELOPMENT_SELECTION,
            requested_range=rng,
        )
    # PAPER is refused outright now (N2f); its range bound stays as defence in depth and is
    # exercised directly: a start on the R2 end date is refused as not-strictly-after
    with pytest.raises(PaperRangeNotAfterR2Error, match="R2"):
        _check_free_range(spec, Partition.PAPER, DateRange(date(2026, 7, 31), date(2026, 8, 31)))


def test_spec_exposed_range_refused(registry: RunRegistry, ledger: ExposureLedger) -> None:
    spec = make_spec(exposed_windows=((date(2017, 3, 1), date(2017, 3, 31)),))
    with pytest.raises(ExposureOverlapError, match="spec's exposed"):
        go(spec, registry, ledger)


def test_ledger_overlap_refused_including_holdout_contact(
    registry: RunRegistry,
) -> None:
    led = ExposureLedger.from_text(
        '{"schema_version": 1, "signoff": {"signed_by": "s", "signed_on": "2026-10-01"},'
        ' "entries": [{"id": "holdout-contact", "start": "2023-05-01", "end": "2023-05-02",'
        ' "description": "d", "source": "s", "observed_by": "o"}]}'
    )
    with pytest.raises(ExposureOverlapError, match="holdout-contact"):
        go(spec_for(led), registry, led, Phase.P4, Partition.HOLDOUT)


def test_unsigned_exposure_ledger_refused(spec: GuardSpecView, registry: RunRegistry) -> None:
    with pytest.raises(ExposureLedgerNotSignedError):
        go(spec, registry, ExposureLedger.from_text(UNSIGNED_LEDGER))


def test_replay_rng001_allowed_on_exposed_data_but_never_citable(
    spec: GuardSpecView, registry: RunRegistry
) -> None:
    unsigned = ExposureLedger.from_text(UNSIGNED_LEDGER)  # not even consulted
    cap = go(
        spec,
        registry,
        unsigned,
        Phase.P2,
        Partition.REPLAY_RNG001,
        requested_range=DateRange(date(2026, 1, 2), date(2026, 6, 12)),
    )
    assert cap.citable is False
    assert cap.exposure_ledger_sha256 is None
    assert "citable=False" in repr(cap)


def test_replay_still_requires_registry_row_and_signed_spec(
    spec: GuardSpecView, registry: RunRegistry, ledger: ExposureLedger
) -> None:
    rng = DateRange(date(2026, 1, 2), date(2026, 6, 12))
    with pytest.raises(RunNotRegisteredError):
        go(
            spec,
            registry,
            ledger,
            Phase.P2,
            Partition.REPLAY_RNG001,
            run_id="none",
            requested_range=rng,
        )
    with pytest.raises(SpecNotSignedError):
        go(
            make_spec(is_signed=False),
            registry,
            ledger,
            Phase.P2,
            Partition.REPLAY_RNG001,
            run_id="none",
            requested_range=rng,
        )


# --- (d) registry row first ------------------------------------------------------


def test_unregistered_run_refused(
    spec: GuardSpecView, registry: RunRegistry, ledger: ExposureLedger
) -> None:
    with pytest.raises(RunNotRegisteredError):
        go(spec, registry, ledger, run_id="range002-run-000001")


def test_closed_run_and_mismatched_row_refused(
    spec: GuardSpecView, registry: RunRegistry, ledger: ExposureLedger
) -> None:
    rid = open_run(registry)
    registry.close_run(rid, RunStatus.FAILED, None)
    with pytest.raises(RunNotRegisteredError, match="not OPEN"):
        go(spec, registry, ledger, run_id=rid)
    other_spec_row = open_run(registry, spec_sha="9" * 64)
    with pytest.raises(RunNotRegisteredError, match="does not match"):
        go(spec, registry, ledger, run_id=other_spec_row)
    wrong_part = open_run(registry, Phase.P3B, Partition.DEVELOPMENT_CONFIRMATION)
    with pytest.raises(RunNotRegisteredError, match="does not match"):
        go(spec, registry, ledger, run_id=wrong_part)


# --- (e) holdout -----------------------------------------------------------------


def holdout(
    spec: GuardSpecView,
    registry: RunRegistry,
    ledger: ExposureLedger,
    store: HoldoutTokenStore | None,
    token: object,
    run_id: str | None = None,
) -> ResultsCapability:
    return go(
        spec,
        registry,
        ledger,
        Phase.P4,
        Partition.HOLDOUT,
        run_id=run_id,
        holdout_store=store,
        holdout_token=token,
    )


def test_holdout_requires_store_and_token(
    spec: GuardSpecView, registry: RunRegistry, ledger: ExposureLedger, store: HoldoutTokenStore
) -> None:
    complete_prereqs(registry, Phase.P4)
    rid = open_run(registry, Phase.P4, Partition.HOLDOUT)
    with pytest.raises(PartitionNotAuthorizedError, match="HoldoutTokenStore"):
        holdout(spec, registry, ledger, None, None, run_id=rid)
    with pytest.raises(HoldoutTokenInvalidError):
        holdout(spec, registry, ledger, store, None, run_id=rid)  # store but no token
    assert store.state(SPEC_SHA) is TokenState.NOT_ISSUED


def test_holdout_consumes_token_once(
    spec: GuardSpecView, registry: RunRegistry, ledger: ExposureLedger, store: HoldoutTokenStore
) -> None:
    tok = store.issue(SPEC_SHA, registry_genesis_id=SYNTH_GENESIS_ID)
    cap = holdout(spec, registry, ledger, store, tok)
    assert cap.partition is Partition.HOLDOUT
    assert store.state(SPEC_SHA) is TokenState.CONSUMED
    with pytest.raises(HoldoutAlreadyOpenedError):
        holdout(spec, registry, ledger, store, tok)


def test_earlier_refusal_does_not_burn_token(
    spec: GuardSpecView, registry: RunRegistry, ledger: ExposureLedger, store: HoldoutTokenStore
) -> None:
    tok = store.issue(SPEC_SHA, registry_genesis_id=SYNTH_GENESIS_ID)
    with pytest.raises(RunNotRegisteredError):
        holdout(spec, registry, ledger, store, tok, run_id="unregistered")
    assert store.state(SPEC_SHA) is TokenState.ISSUED
    assert holdout(spec, registry, ledger, store, tok).citable


def test_token_for_other_spec_refused(
    spec: GuardSpecView, registry: RunRegistry, ledger: ExposureLedger, store: HoldoutTokenStore
) -> None:
    other = store.issue("9" * 64, registry_genesis_id=SYNTH_GENESIS_ID)
    with pytest.raises(HoldoutTokenInvalidError):
        holdout(spec, registry, ledger, store, other)


def test_crash_mid_consume_yields_no_capability_and_no_second_opening(
    spec: GuardSpecView,
    registry: RunRegistry,
    ledger: ExposureLedger,
    store: HoldoutTokenStore,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tok = store.issue(SPEC_SHA, registry_genesis_id=SYNTH_GENESIS_ID)

    def boom(*a: object, **k: object) -> None:
        raise RuntimeError("crash")

    monkeypatch.setattr(store, "commit_consume", boom)
    with pytest.raises(RuntimeError):
        holdout(spec, registry, ledger, store, tok)
    monkeypatch.undo()
    with pytest.raises(HoldoutAlreadyOpenedError):
        holdout(spec, registry, ledger, store, tok)


# --- capability object -----------------------------------------------------------


def test_capability_constructor_is_closed() -> None:
    with pytest.raises(InvalidCapabilityError):
        ResultsCapability(
            object(),
            spec_sha256=SPEC_SHA,
            phase=Phase.P3A,
            partition=Partition.DEVELOPMENT_SELECTION,
            run_id="r",
            date_range=DateRange(date(2016, 1, 1), date(2016, 1, 2)),
            citable=True,
            exposure_ledger_sha256=None,
            evidence_digests=(),
        )


def test_capability_is_immutable_and_uncopyable(
    spec: GuardSpecView, registry: RunRegistry, ledger: ExposureLedger
) -> None:
    cap = go(spec, registry, ledger)
    with pytest.raises(InvalidCapabilityError):
        cap.citable = False
    with pytest.raises(InvalidCapabilityError):
        del cap.run_id
    for fn in (copy.copy, copy.deepcopy, pickle.dumps):
        with pytest.raises(InvalidCapabilityError):
            fn(cap)


def test_forged_capabilities_do_not_validate(
    spec: GuardSpecView, registry: RunRegistry, ledger: ExposureLedger
) -> None:
    real = go(spec, registry, ledger)
    forged = object.__new__(ResultsCapability)
    for name in ("spec_sha256", "phase", "partition", "run_id", "date_range", "citable"):
        object.__setattr__(forged, name, getattr(real, name))
    object.__setattr__(forged, "_nonce", "0" * 32)
    for bad in (None, "token", object(), forged, {"spec_sha256": SPEC_SHA}):
        with pytest.raises(InvalidCapabilityError):
            require_capability(bad)
    # an instance with no nonce at all
    with pytest.raises(InvalidCapabilityError):
        require_capability(object.__new__(ResultsCapability))


# --- requires_capability: direct compute-entry calls fail -------------------------


@requires_capability
def _compute(data: int, *, capability: ResultsCapability) -> int:
    return data * 2


@requires_capability
def _compute_positional(capability: ResultsCapability, data: int) -> int:
    return data + 1


def test_direct_call_without_capability_fails() -> None:
    with pytest.raises(InvalidCapabilityError):
        _compute(1)  # type: ignore[call-arg]
    with pytest.raises(InvalidCapabilityError):
        _compute(1, capability=None)  # type: ignore[arg-type]
    with pytest.raises(InvalidCapabilityError):
        _compute(1, capability="trust me")  # type: ignore[arg-type]
    with pytest.raises(InvalidCapabilityError):
        _compute_positional(None, 1)  # type: ignore[arg-type]
    with pytest.raises(InvalidCapabilityError):
        _compute(1, 2, 3)  # type: ignore[call-arg,arg-type]  # bad call shape


def test_call_with_valid_capability_runs(
    spec: GuardSpecView, registry: RunRegistry, ledger: ExposureLedger
) -> None:
    cap = go(spec, registry, ledger)
    assert _compute(21, capability=cap) == 42
    assert _compute_positional(cap, 1) == 2
    assert _compute.__requires_capability__ is True  # type: ignore[attr-defined]


def test_decorator_rejects_function_without_capability_parameter() -> None:
    with pytest.raises(TypeError, match="capability"):

        @requires_capability
        def nope(x: int) -> int:
            return x
