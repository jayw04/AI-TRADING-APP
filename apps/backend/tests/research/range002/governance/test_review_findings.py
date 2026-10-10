"""Adversarial-review findings H1, H2, H3, M2, M5, L3: each has a negative test here.

Synthetic fixtures only. Every spec goes through ``SpecView`` -> ``to_guard_view`` (the same
public factory path as production).
"""

from __future__ import annotations

import copy
import pickle
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from types import MappingProxyType
from typing import Any

import pytest

from app.research.range002.governance.errors import (
    ExposureBindingError,
    ExposureOverlapError,
    HoldoutAlreadyOpenedError,
    InvalidCapabilityError,
    PaperApprovalNotImplementedError,
    PaperRangeNotAfterR2Error,
    PartitionNotAuthorizedError,
    PhaseOrderError,
    RangeOverlapsPartitionError,
    ReplayRangeOutsideR2Error,
    SpecIncompleteError,
    SpecViewNotTrustedError,
)
from app.research.range002.governance.exposure_ledger import ExposureLedger
from app.research.range002.governance.holdout_token import HoldoutTokenStore
from app.research.range002.governance.model import DateRange, Partition, Phase
from app.research.range002.governance.results_guard import (
    ResultsCapability,
    _check_free_range,
    authorize,
    require_capability,
)
from app.research.range002.governance.run_registry import RunRegistry, RunStatus
from app.research.range002.governance.spec_adapter import GuardSpecView

from .conftest import (
    LEDGER_SHA,
    SPEC_SHA,
    SYNTH_GENESIS_ID,
    complete_prereqs,
    evidence_for,
    make_spec,
    new_registry,
    open_run,
)


def auth(
    spec: Any,
    registry: RunRegistry,
    ledger: ExposureLedger,
    phase: Phase,
    partition: Partition,
    run_id: str,
    **kw: Any,
) -> ResultsCapability:
    if type(registry) is RunRegistry:
        kw.setdefault("predecessor_evidence", evidence_for(registry))
    return authorize(
        spec=spec,
        phase=phase,
        partition=partition,
        run_id=run_id,
        registry=registry,
        exposure_ledger=ledger,
        **kw,
    )


def holdout_run(registry: RunRegistry) -> str:
    complete_prereqs(registry, Phase.P4)
    return open_run(registry, Phase.P4, Partition.HOLDOUT)


# --- H1: the registry is the sole authority on the holdout -----------------------


def test_h1_two_token_dirs_do_not_allow_two_openings(
    spec: GuardSpecView, registry: RunRegistry, ledger: ExposureLedger, tmp_path: Path
) -> None:
    store_a = HoldoutTokenStore(tmp_path / "tokens_a")
    store_b = HoldoutTokenStore(tmp_path / "tokens_b")
    first = holdout_run(registry)
    auth(
        spec, registry, ledger, Phase.P4, Partition.HOLDOUT, first,
        holdout_store=store_a, holdout_token=store_a.issue(SPEC_SHA, registry_genesis_id=SYNTH_GENESIS_ID),
    )  # fmt: skip
    second = open_run(registry, Phase.P4, Partition.HOLDOUT)
    with pytest.raises(HoldoutAlreadyOpenedError, match="registry already holds"):
        auth(
            spec, registry, ledger, Phase.P4, Partition.HOLDOUT, second,
            holdout_store=store_b, holdout_token=store_b.issue(SPEC_SHA, registry_genesis_id=SYNTH_GENESIS_ID),
        )  # fmt: skip


def test_h1_deleting_token_files_does_not_reenable_opening(
    spec: GuardSpecView, registry: RunRegistry, ledger: ExposureLedger, tmp_path: Path
) -> None:
    tokens = tmp_path / "tokens"
    store = HoldoutTokenStore(tokens)
    first = holdout_run(registry)
    auth(
        spec, registry, ledger, Phase.P4, Partition.HOLDOUT, first,
        holdout_store=store, holdout_token=store.issue(SPEC_SHA, registry_genesis_id=SYNTH_GENESIS_ID),
    )  # fmt: skip
    for f in tokens.iterdir():
        f.unlink()  # operator (or attacker) wipes the token directory
    fresh = HoldoutTokenStore(tokens)
    second = open_run(registry, Phase.P4, Partition.HOLDOUT)
    with pytest.raises(HoldoutAlreadyOpenedError):
        auth(
            spec, registry, ledger, Phase.P4, Partition.HOLDOUT, second,
            holdout_store=fresh, holdout_token=fresh.issue(SPEC_SHA, registry_genesis_id=SYNTH_GENESIS_ID),
        )  # fmt: skip
    # ... and re-authorizing the very same run with a new token dir is refused too
    other = HoldoutTokenStore(tmp_path / "tokens_other")
    with pytest.raises(HoldoutAlreadyOpenedError, match="already authorized"):
        auth(
            spec, registry, ledger, Phase.P4, Partition.HOLDOUT, first,
            holdout_store=other, holdout_token=other.issue(SPEC_SHA, registry_genesis_id=SYNTH_GENESIS_ID),
        )  # fmt: skip


def test_h1_an_aborted_after_authorization_holdout_run_still_blocks_a_new_one(
    spec: GuardSpecView, registry: RunRegistry, ledger: ExposureLedger, store: HoldoutTokenStore
) -> None:
    dead = holdout_run(registry)
    auth(
        spec, registry, ledger, Phase.P4, Partition.HOLDOUT, dead,
        holdout_store=store, holdout_token=store.issue(SPEC_SHA, registry_genesis_id=SYNTH_GENESIS_ID),
    )  # fmt: skip
    registry.close_run(dead, RunStatus.ABORTED, None)  # authorization was issued: stays consumed
    nxt = open_run(registry, Phase.P4, Partition.HOLDOUT)
    fresh = HoldoutTokenStore(registry.path.parent / "fresh_tokens")
    with pytest.raises(HoldoutAlreadyOpenedError):
        auth(
            spec, registry, ledger, Phase.P4, Partition.HOLDOUT, nxt,
            holdout_store=fresh, holdout_token=fresh.issue(SPEC_SHA, registry_genesis_id=SYNTH_GENESIS_ID),
        )  # fmt: skip


def test_h1_other_specs_disjoint_holdout_window_does_not_block(
    registry: RunRegistry, ledger: ExposureLedger, store: HoldoutTokenStore
) -> None:
    """Round 3: only an OVERLAPPING window of another spec blocks; a disjoint one does not."""
    first = holdout_run(registry)
    auth(
        make_spec(), registry, ledger, Phase.P4, Partition.HOLDOUT, first,
        holdout_store=store, holdout_token=store.issue(SPEC_SHA, registry_genesis_id=SYNTH_GENESIS_ID),
    )  # fmt: skip
    other_sha = "7" * 64
    rng = DateRange(date(2028, 1, 1), date(2028, 12, 31))
    part = {
        "development_selection": (date(2016, 1, 1), date(2019, 12, 31)),
        "development_confirmation": (date(2020, 1, 1), date(2021, 12, 31)),
        "holdout": (rng.start, rng.end),
    }
    complete_prereqs(registry, Phase.P4, other_sha)
    rid = open_run(registry, Phase.P4, Partition.HOLDOUT, other_sha, holdout_range=rng)
    cap = auth(
        make_spec(spec_sha256=other_sha, partitions=part), registry, ledger,
        Phase.P4, Partition.HOLDOUT, rid,
        holdout_store=store, holdout_token=store.issue(other_sha, registry_genesis_id=SYNTH_GENESIS_ID),
    )  # fmt: skip
    assert cap.spec_sha256 == other_sha


def test_h1_mark_requires_an_open_holdout_run_once(registry: RunRegistry) -> None:
    from app.research.range002.governance.errors import (
        RegistryRecordError,
        RunNotRegisteredError,
    )

    with pytest.raises(RunNotRegisteredError):
        registry.mark_holdout_authorized("nope")
    dev = open_run(registry)
    with pytest.raises(RegistryRecordError, match="HOLDOUT"):
        registry.mark_holdout_authorized(dev)
    rid = holdout_run(registry)
    registry.mark_holdout_authorized(rid)
    with pytest.raises(RegistryRecordError, match="already"):
        registry.mark_holdout_authorized(rid)
    registry.close_run(rid, RunStatus.FAILED, None)
    with pytest.raises(RegistryRecordError, match="not OPEN"):
        registry.mark_holdout_authorized(rid)


# --- H2: PAPER / REPLAY ranges are bounded ----------------------------------------


@pytest.mark.parametrize(
    "rng",
    [
        DateRange(date(2025, 6, 1), date(2026, 9, 1)),  # overlaps the holdout
        DateRange(date(2021, 12, 1), date(2022, 1, 1)),  # straddles confirmation/holdout
        DateRange(date(2018, 1, 1), date(2018, 2, 1)),  # inside selection
        DateRange(date(2020, 6, 1), date(2020, 6, 2)),  # inside confirmation
    ],
)
def test_h2_paper_overlapping_a_spec_partition_refused(spec: GuardSpecView, rng: DateRange) -> None:
    # P5 is refused outright through authorize (N2f); the range bound is defence in depth
    # kept for a future approval mechanism and is exercised directly.
    with pytest.raises(RangeOverlapsPartitionError):
        _check_free_range(spec, Partition.PAPER, rng)


def test_h2_paper_must_start_strictly_after_r2_end(spec: GuardSpecView) -> None:
    for start in (date(2026, 1, 1), date(2026, 7, 31)):
        with pytest.raises(PaperRangeNotAfterR2Error):
            _check_free_range(spec, Partition.PAPER, DateRange(start, date(2026, 12, 31)))
    _check_free_range(spec, Partition.PAPER, DateRange(date(2026, 8, 1), date(2026, 12, 31)))


@pytest.mark.parametrize(
    "rng",
    [
        DateRange(date(2026, 1, 1), date(2026, 8, 1)),  # ends after R2
        DateRange(date(2026, 7, 1), date(2026, 8, 15)),  # ends after R2
        DateRange(date(2026, 8, 1), date(2026, 9, 1)),  # entirely after R2
    ],
)
def test_h2_replay_must_lie_within_r2(
    spec: GuardSpecView, registry: RunRegistry, ledger: ExposureLedger, rng: DateRange
) -> None:
    rid = open_run(registry, Phase.P2, Partition.REPLAY_RNG001)
    with pytest.raises(ReplayRangeOutsideR2Error):
        auth(spec, registry, ledger, Phase.P2, Partition.REPLAY_RNG001, rid, requested_range=rng)


def test_h2_replay_overlapping_a_spec_partition_refused(
    registry: RunRegistry, ledger: ExposureLedger
) -> None:
    # a (synthetic) spec whose holdout reaches into the R2 window
    spec = make_spec(
        partitions=MappingProxyType(
            {
                "development_selection": (date(2016, 1, 1), date(2019, 12, 31)),
                "development_confirmation": (date(2020, 1, 1), date(2021, 12, 31)),
                "holdout": (date(2022, 1, 1), date(2026, 3, 1)),
            }
        )
    )
    rid = open_run(registry, Phase.P2, Partition.REPLAY_RNG001)
    with pytest.raises(RangeOverlapsPartitionError):
        auth(
            spec, registry, ledger, Phase.P2, Partition.REPLAY_RNG001, rid,
            requested_range=DateRange(date(2026, 1, 2), date(2026, 6, 12)),
        )  # fmt: skip
    # the R2 exposure check still bites a development/holdout range that reaches into R2
    complete_prereqs(registry, Phase.P4)
    hid = open_run(registry, Phase.P4, Partition.HOLDOUT)
    with pytest.raises(ExposureOverlapError, match="R2"):
        auth(spec, registry, ledger, Phase.P4, Partition.HOLDOUT, hid)


def test_h2_requested_range_must_be_a_daterange(
    spec: GuardSpecView, registry: RunRegistry, ledger: ExposureLedger
) -> None:
    rid = open_run(registry)
    for bad in ((date(2017, 1, 1), date(2017, 2, 1)), "2017", 5):
        with pytest.raises(PartitionNotAuthorizedError, match="DateRange"):
            auth(
                spec, registry, ledger, Phase.P3A, Partition.DEVELOPMENT_SELECTION, rid,
                requested_range=bad,
            )  # fmt: skip


# --- H3: only the factory-built view; exposure-ledger binding ----------------------


def test_h3_duck_typed_look_alike_is_refused(
    spec: GuardSpecView, registry: RunRegistry, ledger: ExposureLedger
) -> None:
    @dataclass(frozen=True)
    class LookAlike:
        spec_sha256: str = SPEC_SHA
        is_signed: bool = True
        partitions: Any = spec.partitions
        p3_criteria: Any = "x"
        exits_candidates: Any = "x"
        exits_selection: Any = "x"
        exposed: Any = ()
        exposure_signed: Any = None

    rid = open_run(registry)
    for fake in (LookAlike(), object(), None, {"spec_sha256": SPEC_SHA}):
        with pytest.raises(SpecViewNotTrustedError):
            auth(fake, registry, ledger, Phase.P3A, Partition.DEVELOPMENT_SELECTION, rid)


def test_h3_subclass_and_direct_construction_are_refused(
    spec: GuardSpecView, registry: RunRegistry, ledger: ExposureLedger
) -> None:
    with pytest.raises(SpecViewNotTrustedError):
        GuardSpecView(  # type: ignore[call-arg]
            object(), spec_sha256=SPEC_SHA, is_signed=True, partitions=spec.partitions,
            p3_criteria=1, exits_candidates=1, exits_selection=1, exposed=(),
            exposure_signed=None, registry_genesis_id=None, max_p3a_attempts=None,
            max_p3b_attempts=None,
        )  # fmt: skip
    with pytest.raises(TypeError):

        class Sub(GuardSpecView):  # type: ignore[misc]  # @final
            pass

        Sub()  # pragma: no cover


def test_h3_view_is_immutable_and_uncopyable(spec: GuardSpecView) -> None:
    with pytest.raises(AttributeError):
        spec.is_signed = False  # type: ignore[misc]
    with pytest.raises(AttributeError):
        del spec.spec_sha256
    with pytest.raises(AttributeError):
        spec.partitions.holdout = DateRange(date(2030, 1, 1), date(2030, 1, 2))  # type: ignore[misc]
    for fn in (copy.copy, copy.deepcopy, pickle.dumps):
        with pytest.raises(SpecViewNotTrustedError):
            fn(spec)


@pytest.mark.parametrize(
    "record",
    [
        None,
        {},
        {"synthetic": "SYNTH"},  # the shape other tests use for "set but unbound"
        {"exposure_ledger_sha256": None},
        {"exposure_ledger_sha256": "XYZ"},
        {"exposure_ledger_sha256": "A" * 64},  # not lowercase hex
        {"exposure_ledger_sha256": "0" * 64},  # well-formed but a different ledger
        ["exposure_ledger_sha256", LEDGER_SHA],
        LEDGER_SHA,
    ],
)
def test_h3_exposure_binding_absent_or_mismatched_refused(
    registry: RunRegistry, ledger: ExposureLedger, record: Any
) -> None:
    rid = open_run(registry)
    with pytest.raises(ExposureBindingError):
        auth(
            make_spec(exposure_signed=record), registry, ledger,
            Phase.P3A, Partition.DEVELOPMENT_SELECTION, rid,
        )  # fmt: skip


def test_h3_a_different_signed_ledger_is_refused_even_if_well_formed(
    spec: GuardSpecView, registry: RunRegistry
) -> None:
    other = ExposureLedger.from_text(
        '{"schema_version": 1, "signoff": {"signed_by": "s", "signed_on": "2026-10-01"},'
        ' "entries": []}'
    )
    assert other.sha256 != LEDGER_SHA
    rid = open_run(registry)
    with pytest.raises(ExposureBindingError, match="binds exposure ledger"):
        auth(spec, registry, other, Phase.P3A, Partition.DEVELOPMENT_SELECTION, rid)


# --- M2: a capability dies with its run ---------------------------------------------


def _live_cap(
    spec: GuardSpecView, registry: RunRegistry, ledger: ExposureLedger
) -> tuple[ResultsCapability, str]:
    rid = open_run(registry)
    cap = auth(spec, registry, ledger, Phase.P3A, Partition.DEVELOPMENT_SELECTION, rid)
    return cap, rid


@pytest.mark.parametrize(
    "status", [RunStatus.COMPLETED, RunStatus.FAILED, RunStatus.DEFECT, RunStatus.ABORTED]
)
def test_m2_capability_rejected_once_the_run_is_closed(
    spec: GuardSpecView, registry: RunRegistry, ledger: ExposureLedger, status: RunStatus
) -> None:
    cap, rid = _live_cap(spec, registry, ledger)
    assert require_capability(cap) is cap
    registry.close_run(rid, status, "f" * 64 if status is RunStatus.COMPLETED else None)
    with pytest.raises(InvalidCapabilityError, match="no longer valid"):
        require_capability(cap)


def test_m2_capability_rejected_after_abort_open_runs(
    spec: GuardSpecView, registry: RunRegistry, ledger: ExposureLedger
) -> None:
    cap, _ = _live_cap(spec, registry, ledger)
    registry.abort_open_runs()
    with pytest.raises(InvalidCapabilityError):
        require_capability(cap)


def test_m2_capability_is_single_run_scoped(
    spec: GuardSpecView, registry: RunRegistry, ledger: ExposureLedger
) -> None:
    cap_a, rid_a = _live_cap(spec, registry, ledger)
    cap_b, _ = _live_cap(spec, registry, ledger)
    registry.close_run(rid_a, RunStatus.FAILED, None)
    with pytest.raises(InvalidCapabilityError):
        require_capability(cap_a)
    assert require_capability(cap_b) is cap_b  # the other run's capability is unaffected


def test_m2_capability_not_valid_against_a_registry_that_lacks_the_run(
    spec: GuardSpecView, registry: RunRegistry, ledger: ExposureLedger, tmp_path: Path
) -> None:
    from app.research.range002.governance import results_guard as rg

    cap, _ = _live_cap(spec, registry, ledger)
    empty = new_registry(tmp_path / "elsewhere" / "other.jsonl")
    # simulate a capability whose bound registry has no such run row
    rg._BOUND_REGISTRIES[cap] = empty  # noqa: SLF001
    try:
        with pytest.raises(InvalidCapabilityError):
            require_capability(cap)
    finally:
        rg._BOUND_REGISTRIES[cap] = registry  # noqa: SLF001


# --- M5: check (f) for HOLDOUT; phase order from registry rows -----------------------


@pytest.mark.parametrize("missing", ["p3_criteria", "exits_candidates", "exits_selection"])
def test_m5_holdout_refused_while_criteria_unset(
    registry: RunRegistry, ledger: ExposureLedger, store: HoldoutTokenStore, missing: str
) -> None:
    rid = holdout_run(registry)
    with pytest.raises(SpecIncompleteError, match=missing):
        auth(
            make_spec(**{missing: None}), registry, ledger, Phase.P4, Partition.HOLDOUT, rid,
            holdout_store=store, holdout_token=store.issue(SPEC_SHA, registry_genesis_id=SYNTH_GENESIS_ID),
        )  # fmt: skip


def test_m5_p3b_requires_completed_p3a_with_selection_record(
    spec: GuardSpecView, registry: RunRegistry, ledger: ExposureLedger
) -> None:
    def p3b() -> str:
        return open_run(registry, Phase.P3B, Partition.DEVELOPMENT_CONFIRMATION)

    with pytest.raises(PhaseOrderError, match="P3A"):  # nothing at all
        auth(spec, registry, ledger, Phase.P3B, Partition.DEVELOPMENT_CONFIRMATION, p3b())
    p3a = open_run(registry)  # still OPEN
    registry.record_selection(p3a, {"selected": "E1", "run_id": p3a, "spec_sha256": SPEC_SHA})
    with pytest.raises(PhaseOrderError):
        auth(spec, registry, ledger, Phase.P3B, Partition.DEVELOPMENT_CONFIRMATION, p3b())
    registry.close_run(p3a, RunStatus.FAILED, None)  # closed but not COMPLETED
    with pytest.raises(PhaseOrderError):
        auth(spec, registry, ledger, Phase.P3B, Partition.DEVELOPMENT_CONFIRMATION, p3b())
    no_record = open_run(registry)  # COMPLETED but without a selection record
    registry.mark_capability_issued(no_record, attempt_limit=9)
    registry.close_run(no_record, RunStatus.COMPLETED, "d" * 64)
    with pytest.raises(PhaseOrderError):
        auth(spec, registry, ledger, Phase.P3B, Partition.DEVELOPMENT_CONFIRMATION, p3b())
    complete_prereqs(registry, Phase.P3B)
    assert auth(
        spec, registry, ledger, Phase.P3B, Partition.DEVELOPMENT_CONFIRMATION, p3b()
    ).citable


def test_m5_prereqs_of_another_spec_do_not_count(
    spec: GuardSpecView, registry: RunRegistry, ledger: ExposureLedger
) -> None:
    complete_prereqs(registry, Phase.P4, "8" * 64)
    rid = open_run(registry, Phase.P3B, Partition.DEVELOPMENT_CONFIRMATION)
    with pytest.raises(PhaseOrderError):
        auth(spec, registry, ledger, Phase.P3B, Partition.DEVELOPMENT_CONFIRMATION, rid)


def test_m5_p4_requires_completed_p3b_as_well(
    spec: GuardSpecView, registry: RunRegistry, ledger: ExposureLedger, store: HoldoutTokenStore
) -> None:
    kw = {"holdout_store": store}
    rid = open_run(registry, Phase.P4, Partition.HOLDOUT)
    with pytest.raises(PhaseOrderError, match="P3A"):
        auth(spec, registry, ledger, Phase.P4, Partition.HOLDOUT, rid, **kw)
    complete_prereqs(registry, Phase.P3B)  # P3A only
    with pytest.raises(PhaseOrderError, match="P3B"):
        auth(spec, registry, ledger, Phase.P4, Partition.HOLDOUT, rid, **kw)
    assert store.state(SPEC_SHA).value == "NOT_ISSUED"  # a phase refusal never touches tokens
    complete_prereqs(registry, Phase.P4)
    cap = auth(
        spec, registry, ledger, Phase.P4, Partition.HOLDOUT, rid,
        holdout_store=store, holdout_token=store.issue(SPEC_SHA, registry_genesis_id=SYNTH_GENESIS_ID),
    )  # fmt: skip
    assert cap.partition is Partition.HOLDOUT


def test_m5_p2_has_no_phase_prerequisite_and_p5_is_refused_outright(
    spec: GuardSpecView, registry: RunRegistry, ledger: ExposureLedger
) -> None:
    rid2 = open_run(registry, Phase.P2, Partition.REPLAY_RNG001)
    assert not auth(
        spec, registry, ledger, Phase.P2, Partition.REPLAY_RNG001, rid2,
        requested_range=DateRange(date(2026, 2, 1), date(2026, 2, 28)),
    ).citable  # fmt: skip
    complete_prereqs(registry, Phase.P5)
    rid = open_run(registry, Phase.P5, Partition.PAPER)
    with pytest.raises(PaperApprovalNotImplementedError):
        auth(
            spec, registry, ledger, Phase.P5, Partition.PAPER, rid,
            requested_range=DateRange(date(2026, 9, 1), date(2026, 12, 31)),
        )  # fmt: skip


# --- L3: DateRange is dates only -----------------------------------------------------


@pytest.mark.parametrize(
    "bound",
    [datetime(2020, 1, 1, 9, 30), datetime(2020, 1, 1), "2020-01-01", None, 20200101],
)
def test_l3_daterange_rejects_datetime_and_non_dates(bound: Any) -> None:
    with pytest.raises(TypeError):
        DateRange(bound, date(2020, 2, 1))
    with pytest.raises(TypeError):
        DateRange(date(2019, 1, 1), bound)
