# ruff: noqa: F811  (pytest fixtures imported from the rehearsal module are re-requested by name)
"""Acquisition/validation phase: consumes no P3A attempt, grants no strategy capability.

SYNTHETIC. The ACQ capability is accepted by the data layer and refused by every screening,
simulation, statistics and summarising entry point; a cost-aware evaluation opens its P3A attempt
only on a validated, hash-bound acquisition report.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

import pytest

from app.research.range002.governance import errors as gov_errors
from app.research.range002.governance.exposure_ledger import ExposureLedger
from app.research.range002.governance.model import DateRange, Partition, Phase
from app.research.range002.governance.results_guard import authorize, require_capability
from app.research.range002.governance.run_registry import RunRegistry, RunStatus
from app.research.range002.screen.params import extract_params
from app.research.range002.screen.report import summarize
from app.research.range002.screen.simulate import run_screen
from tests.research.range002.governance.conftest import DECIDED_LEDGER
from tests.research.range002.screen.conftest import synth_payload
from tests.research.range002.screen.test_descriptive_run_rehearsal import (
    SEVEN,
    _freeze,
    minutes_root,  # noqa: F401
    rds,
    world,  # noqa: F401
)

ACQ_KW = {"partition": "ACQUISITION", "or_completeness_threshold": 0.5}


def _acq(world: dict[str, Any], **over: Any) -> Any:
    kw = dict(world["kwargs"], **ACQ_KW)
    kw["out_dir"] = world["tmp"] / "acq_out"
    kw.update(over)
    return rds.run(**kw)


def test_acquisition_validates_without_consuming_an_attempt_or_running_the_strategy(
    world: dict[str, Any],
) -> None:
    out = _acq(world)
    v = out.report
    assert v["schema"] == rds.VALIDATION_SCHEMA
    # no fetch ran here, so the identity / price-consistency prerequisites are NOT evaluated and
    # therefore not met: an acquisition that did not validate cannot unlock a performance attempt
    assert v["status"] == rds.STATUS_ACQ_DEFECT and v["all_prerequisites_pass"] is False
    assert v["prerequisites"]["identity_mapping_has_no_unverified"] is False
    assert v["prerequisites"]["price_consistency_no_symbol_over_limit"] is False
    assert v["strategy_results"].startswith("NOT COMPUTED")
    assert "candidates" not in v and "funnel" not in v and "trades" not in json.dumps(v)
    runs = RunRegistry(world["registry_path"]).runs()
    (row,) = runs
    assert row.phase is Phase.ACQ and row.status is RunStatus.COMPLETED
    assert row.capability_issued_seq is not None  # a capability row, but no attempt
    assert v["prerequisites"]["returned_coverage_meets_threshold"] is True
    assert v["prerequisites"]["lookback_sufficient"] is True
    # the capability is dead once closed
    with pytest.raises(gov_errors.InvalidCapabilityError):
        require_capability(out.capability)


def test_acquisition_capability_cannot_screen(world: dict[str, Any]) -> None:
    """Issue an ACQ capability through the real guard and try every kernel entry point."""
    kw = world["kwargs"]
    view, draft = rds._load_spec(kw["spec_path"])
    reg = RunRegistry(kw["registry_path"])
    run_id = reg.open_run(
        phase=Phase.ACQ,
        spec_sha256=view.spec_sha256,
        code_sha=kw["code_sha"],
        data_manifest_sha256="d" * 64,
        partition=Partition.DEVELOPMENT_SELECTION,
        seeds={"acquisition_no_rng": 0},
        exit_candidates=[],
    )
    cap = authorize(
        spec=view,
        phase=Phase.ACQ,
        partition=Partition.DEVELOPMENT_SELECTION,
        run_id=run_id,
        registry=reg,
        exposure_ledger=ExposureLedger.from_text(DECIDED_LEDGER),
        requested_range=DateRange.__call__(
            __import__("datetime").date(2016, 3, 1), __import__("datetime").date(2016, 3, 7)
        ),
    )
    assert cap.phase is Phase.ACQ and cap.citable is False
    with pytest.raises(gov_errors.InvalidCapabilityError, match="acquisition"):
        extract_params(cap, draft)
    with pytest.raises(gov_errors.InvalidCapabilityError, match="acquisition"):
        run_screen(cap, object(), [], 0.01, 1.0)  # type: ignore[arg-type]
    with pytest.raises(gov_errors.InvalidCapabilityError, match="acquisition"):
        summarize(cap, ())
    # the data layer accepts it
    from app.research.range002.data.store_adapter import universe_params_from_draft

    assert universe_params_from_draft(cap, draft) is not None
    assert reg.get_run(run_id).phase is Phase.ACQ


def test_acquisition_cannot_name_the_holdout_or_another_partition() -> None:
    from app.research.range002.governance.model import PHASE_PARTITIONS

    assert PHASE_PARTITIONS[Phase.ACQ] == frozenset({Partition.DEVELOPMENT_SELECTION})


def _theta_world(world: dict[str, Any], tmp: Path) -> dict[str, Any]:
    payload = synth_payload(exits__candidates=copy.deepcopy(SEVEN))
    payload["signal"]["max_cost_to_risk"] = 0.10
    frozen = _freeze(tmp, payload, "frozen_theta.json")
    kw = dict(world["kwargs"], spec_path=frozen, out_dir=tmp / "perf_out")
    return kw


def test_cost_aware_evaluation_needs_a_validated_bound_acquisition(
    world: dict[str, Any], tmp_path: Path
) -> None:
    kw = _theta_world(world, tmp_path)
    with pytest.raises(rds.DescriptiveRunRefusal, match="acquisition-validation"):
        rds.run(**kw)
    assert RunRegistry(world["registry_path"]).runs() == ()  # nothing opened, no attempt


def _passing_report(path: Path, tmp: Path, name: str, **change: Any) -> tuple[Path, str]:
    """A self-consistent copy of a real acquisition report marked as passing (the synthetic world
    has no fetch, so identity/price prerequisites cannot pass on their own)."""
    import hashlib

    doc = json.loads(path.read_text())
    doc["status"] = rds.STATUS_ACQ_VALIDATED
    doc["all_prerequisites_pass"] = True
    doc.update(change)
    out = tmp / name
    out.write_text(json.dumps(doc))
    return out, hashlib.sha256(out.read_bytes()).hexdigest()


def test_validated_acquisition_unlocks_exactly_its_own_bindings(
    world: dict[str, Any], tmp_path: Path
) -> None:
    kw = _theta_world(world, tmp_path)
    acq = rds.run(
        **dict(kw, partition="ACQUISITION", or_completeness_threshold=0.5, out_dir=tmp_path / "a")
    )
    assert acq.status == rds.STATUS_ACQ_DEFECT
    # an acquisition that did not pass cannot unlock the attempt
    with pytest.raises(rds.DescriptiveRunRefusal, match="prerequisites"):
        rds.run(
            **dict(kw, out_dir=tmp_path / "p0"),
            acquisition_validation=acq.report_json,
            acquisition_validation_sha256=acq.report_sha256,
        )
    # a report bound to another store / spec is refused before any registry row
    for k, v in (("minute_bars_sha256", "0" * 64), ("spec_sha256", "1" * 64)):
        p, sha = _passing_report(acq.report_json, tmp_path, f"bad_{k}.json", **{k: v})
        with pytest.raises(rds.DescriptiveRunRefusal, match="refused"):
            rds.run(
                **dict(kw, out_dir=tmp_path / f"p_{k}"),
                acquisition_validation=p,
                acquisition_validation_sha256=sha,
            )
    with pytest.raises(rds.DescriptiveRunRefusal, match="sha256"):
        rds.run(
            **dict(kw, out_dir=tmp_path / "p2"),
            acquisition_validation=acq.report_json,
            acquisition_validation_sha256="0" * 64,
        )
    reg = RunRegistry(world["registry_path"])
    assert [r.phase for r in reg.runs()] == [Phase.ACQ]  # only the ACQ row exists so far
    good, gsha = _passing_report(acq.report_json, tmp_path, "good.json")
    out = rds.run(
        **dict(kw, out_dir=tmp_path / "p3"),
        acquisition_validation=good,
        acquisition_validation_sha256=gsha,
    )
    assert out.report["run"]["phase"] == "P3A"
    consumed = [
        r
        for r in reg.runs()
        if r.phase in (Phase.P3A, Phase.P3B) and r.capability_issued_seq is not None
    ]
    assert [r.run_id for r in consumed] == [out.run_id]  # ONLY the performance run is an attempt


def test_planned_later_phase_run_does_not_block_acquisition_but_prior_exposure_does(
    world: dict[str, Any],
) -> None:
    doc = json.loads(DECIDED_LEDGER)
    base_entry = {
        "start": "2016-03-01",
        "end": "2016-03-07",
        "description": "test",
        "source": "test",
        "observed_by": "test",
    }
    planned = dict(
        base_entry,
        id="planned-p3a",
        kind="planned_run",
        phase="P3A",
        partition="DEVELOPMENT_SELECTION",
        planned_label="x",
    )
    doc["entries"] = [*doc["entries"], planned]
    ledger_path = world["tmp"] / "ledger_planned.json"
    ledger_path.write_text(json.dumps(doc), encoding="utf-8")
    # the synthetic spec binds the DECIDED ledger's sha, so re-bind through a fresh spec
    payload = synth_payload(exits__candidates=copy.deepcopy(SEVEN))
    payload["governance"]["exposure_signed"] = {
        "exposure_ledger_sha256": ExposureLedger.from_text(ledger_path.read_text()).sha256
    }
    frozen = _freeze(world["tmp"], payload, "frozen_planned.json")
    kw = dict(
        world["kwargs"],
        **ACQ_KW,
        spec_path=frozen,
        exposure_ledger_path=ledger_path,
        out_dir=world["tmp"] / "acq_planned",
    )
    assert rds.run(**kw).status in (rds.STATUS_ACQ_DEFECT, rds.STATUS_ACQ_VALIDATED)
    # a seen (prior_exposure) entry over the same window still blocks acquisition
    seen = dict(base_entry, id="seen-1")
    doc["entries"] = [*json.loads(DECIDED_LEDGER)["entries"], seen]
    ledger2 = world["tmp"] / "ledger_seen.json"
    ledger2.write_text(json.dumps(doc), encoding="utf-8")
    payload["governance"]["exposure_signed"] = {
        "exposure_ledger_sha256": ExposureLedger.from_text(ledger2.read_text()).sha256
    }
    frozen2 = _freeze(world["tmp"], payload, "frozen_seen.json")
    kw2 = dict(
        kw, spec_path=frozen2, exposure_ledger_path=ledger2, out_dir=world["tmp"] / "acq_seen"
    )
    with pytest.raises(gov_errors.ExposureOverlapError):
        rds.run(**kw2)
