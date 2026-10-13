# ruff: noqa: F811  (pytest fixtures imported from the rehearsal module are re-requested by name)
"""Prospective missing-minute policy: accounted-for minutes are NO_TRADE evidence, nothing more.

SYNTHETIC. One opening-range minute of one symbol-day is removed from the stored bars; the census
evidence that accounts for it is built by hand with the same schema the classifier writes.
"""

from __future__ import annotations

import copy
import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import duckdb
import pytest

from app.research.range002.spec.hashing import file_sha256
from tests.research.range002.screen.conftest import synth_payload
from tests.research.range002.screen.test_descriptive_run_rehearsal import (
    SEVEN,
    _freeze,
    minutes_root,  # noqa: F401
    rds,
    world,  # noqa: F401
)

DAY = "2016-03-02"  # EST: 09:35 ET == 14:35 UTC
ACCOUNTED = "ACCOUNTED_FOR_POSITIVE"
EMPTY = "ACCOUNTED_FOR_EMPTY_SAME_PROVIDER"


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _remove_or_minute(store: Path, symbol: str = "AAA") -> None:
    con = duckdb.connect(str(store))
    ts = datetime(2016, 3, 2, 14, 35, tzinfo=UTC).replace(tzinfo=None)
    con.execute("DELETE FROM minute_bars WHERE symbol = ? AND ts = ?", [symbol, ts])
    n = con.execute(
        "SELECT count(*) FROM minute_bars WHERE symbol=? AND ts=?", [symbol, ts]
    ).fetchone()
    assert n is not None and n[0] == 0
    con.close()


def _evidence(tmp: Path, klass: str, *, minute: str = "09:35", day: str = DAY) -> dict[str, Any]:
    manifest = {
        "samples": [
            {
                "id": "C1",
                "symbol": "AAA",
                "day": day,
                "missing_minutes": [f"{minute}:00"],
                "control_minutes": ["09:34:00", "09:36:00"],
            }
        ]
    }
    mpath = tmp / "census_manifest.json"
    mpath.write_text(json.dumps(manifest), encoding="utf-8")
    cls = {
        "schema": "range002.census_classification.v1",
        "manifest_sha256": _sha(mpath),
        "rule_source": "test",
        "per_sample": [{"id": "C1", "classes": {minute: klass}}],
    }
    cpath = tmp / "census_classification.json"
    cpath.write_text(json.dumps(cls), encoding="utf-8")
    return {
        "no_trade_evidence": cpath,
        "no_trade_evidence_sha256": _sha(cpath),
        "census_manifest": mpath,
        "census_manifest_sha256": _sha(mpath),
    }


def _acq_kw(world: dict[str, Any], **over: Any) -> dict[str, Any]:
    kw = dict(world["kwargs"], partition="ACQUISITION", or_completeness_threshold=0.9)
    kw["out_dir"] = world["tmp"] / over.pop("out", "acq")
    kw.update(over)
    return kw


def test_accounted_minute_flips_the_or_gate_only_when_evidence_is_supplied(
    world: dict[str, Any],
) -> None:
    _remove_or_minute(world["kwargs"]["minute_bars"])
    base = rds.run(**_acq_kw(world, out="a0"))
    g0 = base.report["or_completeness_gate"]
    assert g0["numerator"] == g0["denominator"] - 2 and g0["meets_threshold"] is False
    ev = _evidence(world["tmp"], ACCOUNTED)
    out = rds.run(**_acq_kw(world, out="a1", **ev, accounted_tiers="positive"))
    g1 = out.report["or_completeness_gate"]
    assert g1["numerator"] == g0["numerator"] + 1 and g1["meets_threshold"] is True
    assert g1["accounted_minutes"]["minutes_accounted_applied"] == 1
    assert out.report["no_trade_evidence_sha256"] == ev["no_trade_evidence_sha256"]
    # the denominator (expected population) is unchanged
    assert g1["denominator"] == g0["denominator"]


def test_empty_same_provider_tier_needs_the_explicit_both_choice(world: dict[str, Any]) -> None:
    _remove_or_minute(world["kwargs"]["minute_bars"])
    ev = _evidence(world["tmp"], EMPTY)
    pos = rds.run(**_acq_kw(world, out="p", **ev, accounted_tiers="positive"))
    assert pos.report["or_completeness_gate"]["accounted_minutes"]["minutes_accounted_applied"] == 0
    assert pos.report["or_completeness_gate"]["meets_threshold"] is False
    both = rds.run(**_acq_kw(world, out="b", **ev, accounted_tiers="both"))
    assert both.report["or_completeness_gate"]["meets_threshold"] is True


def test_evidence_for_a_minute_that_has_a_bar_is_refused(world: dict[str, Any]) -> None:
    # no bar was removed: 09:35 exists in the store, so "accounted-for" contradicts the data
    ev = _evidence(world["tmp"], ACCOUNTED)
    with pytest.raises(rds.DescriptiveRunRefusal, match="stored bar"):
        rds.run(**_acq_kw(world, out="c", **ev, accounted_tiers="positive"))


def test_evidence_needs_binding_and_an_explicit_tier(world: dict[str, Any]) -> None:
    _remove_or_minute(world["kwargs"]["minute_bars"])
    ev = _evidence(world["tmp"], ACCOUNTED)
    with pytest.raises(rds.DescriptiveRunRefusal, match="accounted-tiers"):
        rds.run(**_acq_kw(world, out="d", **ev))
    bad = dict(ev, no_trade_evidence_sha256="0" * 64)
    with pytest.raises(rds.DescriptiveRunRefusal, match="sha256"):
        rds.run(**_acq_kw(world, out="e", **bad, accounted_tiers="positive"))


def test_no_accounting_can_repair_a_day_with_no_valid_bar(world: dict[str, Any]) -> None:
    """A symbol-day whose whole OR is accounted-for still has no actual bar: not a valid OR."""
    store: Path = world["kwargs"]["minute_bars"]
    con = duckdb.connect(str(store))
    con.execute(
        "DELETE FROM minute_bars WHERE symbol = 'AAA' AND ts >= ? AND ts < ?",
        [datetime(2016, 3, 2, 14, 30), datetime(2016, 3, 2, 15, 0)],
    )
    con.close()
    et = ZoneInfo("America/New_York")
    assert et  # the OR window is 09:30..09:59 ET == 14:30..14:59 UTC in March (EST)
    mins = [f"09:{m:02d}" for m in range(30, 60)]
    manifest = {
        "samples": [
            {
                "id": "C1",
                "symbol": "AAA",
                "day": DAY,
                "missing_minutes": [f"{m}:00" for m in mins],
                "control_minutes": ["10:00:00"],
            }
        ]
    }
    mpath = world["tmp"] / "m_all.json"
    mpath.write_text(json.dumps(manifest), encoding="utf-8")
    cls = {
        "schema": "range002.census_classification.v1",
        "manifest_sha256": _sha(mpath),
        "per_sample": [{"id": "C1", "classes": dict.fromkeys(mins, ACCOUNTED)}],
    }
    cpath = world["tmp"] / "c_all.json"
    cpath.write_text(json.dumps(cls), encoding="utf-8")
    ev = {
        "no_trade_evidence": cpath,
        "no_trade_evidence_sha256": _sha(cpath),
        "census_manifest": mpath,
        "census_manifest_sha256": _sha(mpath),
    }
    out = rds.run(**_acq_kw(world, out="all", **ev, accounted_tiers="positive"))
    g = out.report["or_completeness_gate"]
    assert g["accounted_minutes"]["minutes_accounted_applied"] == 30
    assert g["numerator"] == g["denominator"] - 2  # the missing OLD day and the bar-less AAA day


def test_revalidation_carries_original_evidence_and_unlocks_the_evaluation_once(
    world: dict[str, Any], tmp_path: Path
) -> None:
    _remove_or_minute(world["kwargs"]["minute_bars"])
    store: Path = world["kwargs"]["minute_bars"]
    original = {
        "store_sha256": file_sha256(store),
        "binding": {"symbol_mapping_by_provenance": {"UNVERIFIED": 0}},
        "price_consistency_check": {
            "check": "x",
            "what_it_is_not": "x",
            "tolerance": 0.05,
            "max_mismatch_fraction": 0.1,
            "fraction_definition": "x",
            "totals": {},
            "symbols_exceeding_fraction": [],
            "per_symbol_not_passing": {},
            "mismatching_days_on_a_corporate_action_day": 0,
        },
        "actual": {"http_attempts": 1},
    }
    epath = tmp_path / "orig_evidence.json"
    epath.write_text(json.dumps(original), encoding="utf-8")
    ev = _evidence(world["tmp"], ACCOUNTED)
    payload = synth_payload(exits__candidates=copy.deepcopy(SEVEN))
    payload["signal"]["max_cost_to_risk"] = 0.10
    frozen = _freeze(tmp_path, payload, "frozen_theta.json")
    kw = _acq_kw(
        world,
        out="rev",
        spec_path=frozen,
        accounted_tiers="positive",
        carry_acquisition_evidence=epath,
        carry_acquisition_evidence_sha256=_sha(epath),
        **ev,
    )
    val = rds.run(**kw)
    assert val.status == rds.STATUS_ACQ_VALIDATED, val.report["prerequisites"]
    assert val.report["acquisition"]["store_sha256"] == original["store_sha256"]
    # the evaluation refuses without the same evidence, accepts with it
    ekw = dict(
        world["kwargs"],
        spec_path=frozen,
        out_dir=tmp_path / "eval",
        acquisition_validation=val.report_json,
        acquisition_validation_sha256=val.report_sha256,
        or_completeness_threshold=0.9,
    )
    with pytest.raises(rds.DescriptiveRunRefusal, match="evidence differs"):
        rds.run(**ekw)
    out = rds.run(**ekw, **ev, accounted_tiers="positive")
    assert out.report["run"]["phase"] == "P3A"
    assert out.report["or_completeness_gate"]["accounted_minutes"]["minutes_accounted_applied"] == 1
    # a carried evidence file for another store is refused
    bad = dict(original, store_sha256="0" * 64)
    bpath = tmp_path / "bad_evidence.json"
    bpath.write_text(json.dumps(bad), encoding="utf-8")
    with pytest.raises(rds.DescriptiveRunRefusal, match="another store"):
        rds.run(
            **dict(
                kw,
                out_dir=tmp_path / "rev2",
                carry_acquisition_evidence=bpath,
                carry_acquisition_evidence_sha256=_sha(bpath),
            )
        )
