"""A-SCREEN O-8(B): the restricted screen profile (SYNTHETIC fixtures only).

What is proved here: the profile has an exact, tested required-field contract; it is inside the
spec hash and bound to the capability; it authorises only (P2, REPLAY_RNG001) and
(P3A, DEVELOPMENT_SELECTION); every other phase is refused by name; the full profile is
unchanged; decision, exposure, genesis and attempt-limit controls still apply. None of this
selects a P0 value or approves anything.
"""

from __future__ import annotations

import copy
import json
import sys
from datetime import date
from pathlib import Path
from typing import Any

import pytest

from app.research.range002.governance import results_guard, spec_adapter
from app.research.range002.governance.errors import (
    PartitionNotAuthorizedError,
    ProfileNotAuthorizedError,
    ProfileNotRecognizedError,
    ReplayRangeOutsideR2Error,
)
from app.research.range002.governance.exposure_ledger import ExposureLedger
from app.research.range002.governance.model import DateRange, Partition, Phase
from app.research.range002.governance.results_guard import authorize, require_capability
from app.research.range002.governance.run_registry import RunStatus
from app.research.range002.governance.spec_adapter import GuardSpecView, to_guard_view
from app.research.range002.spec.hashing import content_sha256
from app.research.range002.spec.loader import (
    SpecSchemaError,
    load_frozen,
    parse_draft,
    spec_sha256,
)
from app.research.range002.spec.schema import (
    SCREEN_V1_EXEMPT,
    SCREEN_V1_REQUIRED,
    SCREEN_V1_REQUIRED_SHA256,
    DecisionRefError,
    UnsetP0FieldsError,
    draft_skeleton,
)
from tests.research.range002.governance.conftest import (
    DECIDED_LEDGER,
    LEDGER_SHA,
    UNDECIDED_LEDGER,
    new_registry,
    open_run,
)
from tests.research.range002.spec._fixtures import (
    SYNTH_MANIFEST_PATH,
    complete_payload,
    set_path,
)

sys.path.insert(0, str(Path(__file__).resolve().parents[4] / "scripts" / "research" / "range002"))
import freeze_spec  # noqa: E402

R2_RANGE = DateRange(date(2026, 1, 2), date(2026, 6, 12))
PROFILE_BLOCK = {
    "name": "screen",
    "version": 1,
    "required_fields_sha256": SCREEN_V1_REQUIRED_SHA256,
}


def screen_payload(*, signed: bool = True) -> dict[str, Any]:
    payload = complete_payload(decided=signed)
    for path in SCREEN_V1_EXEMPT:
        set_path(payload, path, None)
    set_path(payload, "governance.exposure_signed", {"exposure_ledger_sha256": LEDGER_SHA})
    payload["profile"] = copy.deepcopy(PROFILE_BLOCK)
    return payload


def full_payload() -> dict[str, Any]:
    payload = complete_payload(decided=True)
    set_path(payload, "governance.exposure_signed", {"exposure_ledger_sha256": LEDGER_SHA})
    return payload


def freeze(tmp: Path, payload: dict[str, Any], name: str = "s") -> Path:
    draft = tmp / f"{name}_draft.json"
    draft.write_text(json.dumps(payload), encoding="utf-8")
    out = tmp / f"{name}_frozen.json"
    freeze_spec.freeze(draft, out, manifest_path=SYNTH_MANIFEST_PATH)
    return out


def view_for(tmp: Path, payload: dict[str, Any], name: str = "s") -> GuardSpecView:
    return to_guard_view(load_frozen(freeze(tmp, payload, name)))


def ledger() -> ExposureLedger:
    return ExposureLedger.from_text(DECIDED_LEDGER)


def issue(
    view: GuardSpecView,
    tmp: Path,
    phase: Phase,
    partition: Partition,
    **kw: Any,
) -> Any:
    registry = new_registry(tmp / "runs.jsonl")
    run_id = open_run(registry, phase, partition, view.spec_sha256)
    return authorize(
        spec=view,
        phase=phase,
        partition=partition,
        run_id=run_id,
        registry=registry,
        exposure_ledger=ledger(),
        **kw,
    )


# --- the exact contract ---------------------------------------------------------------------


def test_required_and_exempt_partition_the_p0_field_set_exactly() -> None:
    all_p0 = set(parse_draft(draft_skeleton()).unset_p0_fields())
    required, exempt = set(SCREEN_V1_REQUIRED), set(SCREEN_V1_EXEMPT)
    assert required.isdisjoint(exempt)
    assert required | exempt == all_p0, "a new P0 field must be classified required or exempt"
    assert len(SCREEN_V1_REQUIRED) == len(required)  # no duplicates
    assert content_sha256("\n".join(SCREEN_V1_REQUIRED)) or True  # canonical form not used here
    import hashlib

    assert (
        hashlib.sha256("\n".join(SCREEN_V1_REQUIRED).encode()).hexdigest()
        == SCREEN_V1_REQUIRED_SHA256
    )


def test_required_list_covers_everything_that_changes_signals_fills_costs_or_interpretation() -> (
    None
):
    must = {
        "signal.or_completeness_rule",
        "signal.min_or_width_ticks",
        "exit.halfday_offset_min",
        "fill.slippage_model",
        "fill.halt_policy",
        "costs.accounting_mode",
        "costs.components",
        "risk.per_trade_pct",
        "universe.n",
        "data.vendor",
        "data.fetch_mode",
        "exits.candidates",
        "exits.complexity_order",
        "exits.selection.score",
        "exits.selection.tie_tolerance_r",
        "exits.selection.stop_test",
        "p3.criteria",
        "p3.max_p3a_attempts",
        "p3.max_p3b_attempts",
        "governance.exposure_signed",
        "governance.registry_genesis_id",
        "registration.related_programs",
        "gates.basis",
        "gates.trade_unit",
        "stats.bootstrap.method",
        "stats.bootstrap.reps",
        "stats.bootstrap.seed",
        "stats.alpha_one_sided",
        "stats.hypothesis_family",
        "execution.bar_timestamp_convention",
        "execution.crossed_before_arm_policy",
        "execution.order_type",
        "execution.tie_break",
        "execution.vendor_delay_ms",
        "execution.stop_protection_policy",
        "controls.naive_orb.definition",
    }
    assert must <= set(SCREEN_V1_REQUIRED)
    # the role / thesis-signature fields were removed from the spec (meeting-decision migration)
    assert not any(
        p in SCREEN_V1_EXEMPT for p in ("governance.roles", "governance.economic_thesis_sha")
    )
    assert not any(p.startswith("p5.") for p in SCREEN_V1_REQUIRED)


# --- freeze / load ---------------------------------------------------------------------------


def test_screen_spec_freezes_with_exempt_fields_null_and_loads_as_screen(tmp_path: Path) -> None:
    out = freeze(tmp_path, screen_payload())
    view = load_frozen(out)
    assert view.profile == "screen" and view.has_run_decision
    assert json.loads(out.read_text())["profile"] == PROFILE_BLOCK
    assert to_guard_view(view).profile == "screen"


def test_same_content_without_profile_is_the_full_profile_and_refuses(tmp_path: Path) -> None:
    payload = screen_payload()
    del payload["profile"]
    with pytest.raises(UnsetP0FieldsError) as exc:
        freeze(tmp_path, payload)
    assert "diagnostics.taxonomy" in exc.value.fields and "p5.account_id" in exc.value.fields


@pytest.mark.parametrize(
    "path",
    [
        "execution.order_type",
        "exits.candidates",
        "costs.components",
        "fill.halt_policy",
        "governance.registry_genesis_id",
        "p3.max_p3a_attempts",
        "governance.exposure_signed",
    ],
)
def test_missing_required_value_refused_by_name(tmp_path: Path, path: str) -> None:
    payload = screen_payload()
    set_path(payload, path, None)
    with pytest.raises(UnsetP0FieldsError) as exc:
        freeze(tmp_path, payload)
    assert path in exc.value.fields


def test_missing_decision_still_refused(tmp_path: Path) -> None:
    payload = screen_payload()
    payload["decision"] = None
    with pytest.raises(DecisionRefError):
        freeze(tmp_path, payload)


@pytest.mark.parametrize("outcome", ["revise", "defer", "stop"])
def test_screen_spec_with_non_approved_decision_refused_at_freeze(
    tmp_path: Path, outcome: str
) -> None:
    payload = screen_payload()
    payload["decision"]["decision"] = outcome
    with pytest.raises(DecisionRefError):
        freeze(tmp_path, payload)


@pytest.mark.parametrize(
    "mutate",
    [
        lambda b: b.update(name="screen2"),
        lambda b: b.update(version=2),
        lambda b: b.update(required_fields_sha256="0" * 64),
        lambda b: b.pop("required_fields_sha256"),
        lambda b: b.update(extra="x"),
    ],
)
def test_unknown_or_altered_profile_declaration_is_refused(mutate: Any) -> None:
    payload = screen_payload()
    mutate(payload["profile"])
    with pytest.raises(SpecSchemaError):
        parse_draft(payload)


def test_profile_is_inside_the_hash_and_full_hash_is_unchanged() -> None:
    screen = parse_draft(screen_payload())
    as_full = screen_payload()
    del as_full["profile"]
    full_same_content = parse_draft(as_full)
    assert spec_sha256(screen) != spec_sha256(full_same_content)
    # The full profile's hash is exactly the hash of its payload without any profile key.
    payload = full_payload()
    draft = parse_draft(payload)
    expected = {
        k: v for k, v in draft.model_dump(mode="json").items() if k not in ("decision", "profile")
    }
    # an absent optional rule (signal.max_cost_to_risk) is omitted so older hashes are unchanged
    expected["signal"] = {k: v for k, v in expected["signal"].items() if k != "max_cost_to_risk"}
    assert spec_sha256(draft) == content_sha256(expected)
    assert "profile" not in draft.hashable_payload()


def test_full_profile_frozen_file_carries_no_profile_key(tmp_path: Path) -> None:
    out = freeze(tmp_path, full_payload(), "f")
    assert "profile" not in json.loads(out.read_text())
    assert load_frozen(out).profile == "full"


def test_skeleton_is_unchanged_and_has_no_profile() -> None:
    assert "profile" not in draft_skeleton()


# --- guard: allowed pairs, refusals, binding ------------------------------------------------------


def test_screen_spec_authorises_p2_replay_and_p3a_and_binds_profile(tmp_path: Path) -> None:
    view = view_for(tmp_path, screen_payload())
    (tmp_path / "a").mkdir()
    cap = issue(view, tmp_path / "a", Phase.P2, Partition.REPLAY_RNG001, requested_range=R2_RANGE)
    assert cap.profile == "screen" and cap.citable is False
    sub = tmp_path / "b"
    sub.mkdir()
    cap2 = issue(view, sub, Phase.P3A, Partition.DEVELOPMENT_SELECTION)
    assert cap2.profile == "screen" and cap2.citable is True
    assert cap2.date_range == view.partitions.selection
    assert require_capability(cap2) is cap2


@pytest.mark.parametrize(
    ("phase", "partition"),
    [
        (Phase.P3B, Partition.DEVELOPMENT_CONFIRMATION),
        (Phase.P4, Partition.HOLDOUT),
        (Phase.P5, Partition.PAPER),
    ],
)
def test_screen_spec_refused_for_every_other_phase(
    tmp_path: Path, phase: Phase, partition: Partition
) -> None:
    view = view_for(tmp_path, screen_payload())
    registry = new_registry(tmp_path / "runs.jsonl")
    with pytest.raises(ProfileNotAuthorizedError):
        authorize(
            spec=view,
            phase=phase,
            partition=partition,
            run_id="no-such-run",
            registry=registry,
            exposure_ledger=ledger(),
        )


def test_screen_spec_cannot_open_a_partition_its_phase_does_not_allow(tmp_path: Path) -> None:
    view = view_for(tmp_path, screen_payload())
    registry = new_registry(tmp_path / "runs.jsonl")
    with pytest.raises(PartitionNotAuthorizedError):  # closed set is checked first
        authorize(
            spec=view,
            phase=Phase.P3A,
            partition=Partition.HOLDOUT,
            run_id="x",
            registry=registry,
            exposure_ledger=ledger(),
        )


def test_unknown_or_missing_profile_on_a_view_is_refused(tmp_path: Path) -> None:
    good = view_for(tmp_path, screen_payload())
    registry = new_registry(tmp_path / "runs.jsonl")
    for bad in ("screen2", "", None, "FULL"):
        forged = GuardSpecView(
            spec_adapter._ISSUE_VIEW,
            spec_sha256=good.spec_sha256,
            has_run_decision=True,
            decision=good.decision,
            decision_scope=good.decision_scope,
            decision_partitions=good.decision_partitions,
            minutes_path=good.minutes_path,
            minutes_sha256=good.minutes_sha256,
            record_kind=good.record_kind,
            strategy_version=good.strategy_version,
            baseline_id=good.baseline_id,
            partitions=good.partitions,
            p3_criteria=good.p3_criteria,
            exits_candidates=good.exits_candidates,
            exits_selection=good.exits_selection,
            exposed=good.exposed,
            exposure_signed=good.exposure_signed,
            registry_genesis_id=good.registry_genesis_id,
            max_p3a_attempts=good.max_p3a_attempts,
            max_p3b_attempts=good.max_p3b_attempts,
            profile=bad,  # type: ignore[arg-type]
        )
        with pytest.raises(ProfileNotRecognizedError):
            authorize(
                spec=forged,
                phase=Phase.P3A,
                partition=Partition.DEVELOPMENT_SELECTION,
                run_id="x",
                registry=registry,
                exposure_ledger=ledger(),
            )


def test_full_profile_is_unchanged_and_still_reaches_p3a(tmp_path: Path) -> None:
    view = view_for(tmp_path, full_payload(), "f")
    assert view.profile == "full"
    cap = issue(view, tmp_path, Phase.P3A, Partition.DEVELOPMENT_SELECTION)
    assert cap.profile == "full"


def test_date_range_limits_still_apply_to_the_screen_profile(tmp_path: Path) -> None:
    view = view_for(tmp_path, screen_payload())
    (tmp_path / "r").mkdir()
    with pytest.raises(ReplayRangeOutsideR2Error):
        issue(
            view,
            tmp_path / "r",
            Phase.P2,
            Partition.REPLAY_RNG001,
            requested_range=DateRange(date(2026, 8, 3), date(2026, 8, 14)),
        )
    (tmp_path / "p").mkdir()
    with pytest.raises(PartitionNotAuthorizedError):
        issue(
            view,
            tmp_path / "p",
            Phase.P3A,
            Partition.DEVELOPMENT_SELECTION,
            requested_range=DateRange(date(2019, 6, 1), date(2020, 2, 1)),
        )


def test_exposure_ledger_without_decision_still_refused_for_screen_p3a(tmp_path: Path) -> None:
    from app.research.range002.governance.errors import ExposureLedgerDecisionMissingError

    view = view_for(tmp_path, screen_payload())
    registry = new_registry(tmp_path / "runs.jsonl")
    run_id = open_run(registry, Phase.P3A, Partition.DEVELOPMENT_SELECTION, view.spec_sha256)
    with pytest.raises(ExposureLedgerDecisionMissingError):
        authorize(
            spec=view,
            phase=Phase.P3A,
            partition=Partition.DEVELOPMENT_SELECTION,
            run_id=run_id,
            registry=registry,
            exposure_ledger=ExposureLedger.from_text(UNDECIDED_LEDGER),
        )


def test_closed_run_capability_of_a_screen_spec_is_not_reusable(tmp_path: Path) -> None:
    from app.research.range002.governance.errors import InvalidCapabilityError

    view = view_for(tmp_path, screen_payload())
    registry = new_registry(tmp_path / "runs.jsonl")
    run_id = open_run(registry, Phase.P3A, Partition.DEVELOPMENT_SELECTION, view.spec_sha256)
    cap = authorize(
        spec=view,
        phase=Phase.P3A,
        partition=Partition.DEVELOPMENT_SELECTION,
        run_id=run_id,
        registry=registry,
        exposure_ledger=ledger(),
    )
    require_capability(cap)
    registry.close_run(run_id, RunStatus.ABORTED, None)
    with pytest.raises(InvalidCapabilityError):
        require_capability(cap)


def test_screen_p3a_completion_does_not_satisfy_a_full_specs_phase_order(tmp_path: Path) -> None:
    """No automatic conversion: a COMPLETED screen P3A is keyed by the screen spec's hash, so it
    cannot satisfy P3B for the full-profile spec (a different hash)."""
    assert spec_sha256(parse_draft(screen_payload())) != spec_sha256(parse_draft(full_payload()))
    assert {
        (Phase.P2, Partition.REPLAY_RNG001),
        (Phase.P3A, Partition.DEVELOPMENT_SELECTION),
    } == results_guard._SCREEN_PROFILE_ALLOWED
