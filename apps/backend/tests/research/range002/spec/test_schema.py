"""WP0.2 schema tests: required-but-nullable P0 fields, fixed values, exits block, partitions."""

from __future__ import annotations

import copy
from datetime import date

import pytest
from pydantic import BaseModel

from app.research.range002.spec import schema as schema_mod
from app.research.range002.spec.loader import SpecSchemaError, parse_draft
from app.research.range002.spec.schema import (
    DraftSpec,
    FrozenSpec,
    UnsetP0FieldsError,
    draft_skeleton,
    validate_partition_layout,
)

from ._fixtures import CANDIDATES, P0_PATHS, complete_payload, get_path, set_path


def _problems(payload: dict) -> str:
    with pytest.raises(SpecSchemaError) as ei:
        parse_draft(payload)
    return " | ".join(ei.value.problems)


def _all_models() -> list[type[BaseModel]]:
    return [
        obj
        for obj in vars(schema_mod).values()
        if isinstance(obj, type)
        and issubclass(obj, BaseModel)
        and obj.__module__ == schema_mod.__name__
    ]


def test_no_field_has_a_default():
    # Rule R9: a developer-chosen default would be a silent decision.
    for model in _all_models():
        for name, field in model.model_fields.items():
            assert field.is_required(), f"{model.__name__}.{name} has a default"


def test_every_model_forbids_extra_keys():
    for model in _all_models():
        assert model.model_config.get("extra") == "forbid", model.__name__


def test_skeleton_is_a_valid_draft_with_every_p0_unset():
    draft = parse_draft(draft_skeleton())
    unset = draft.unset_p0_fields()
    assert set(unset) == set(P0_PATHS)
    assert "registration.trial_ledger_id" not in unset  # run_registry's, not a P0 decision
    assert not any(p.startswith("signoff") for p in unset)


def test_skeleton_leaves_open_decisions_null():
    sk = draft_skeleton()
    assert sk["stats"]["bootstrap"]["method"] is None  # ruling C11
    assert sk["gates"]["win_rate"] is None  # rulings C3 / D10
    assert sk["exits"]["candidates"] is None
    assert sk["p3"]["criteria"] is None


@pytest.mark.parametrize("path", ["gates.win_rate", "stats.bootstrap.method", "p3.criteria"])
def test_missing_p0_key_is_a_named_error(path):
    payload = draft_skeleton()
    parent, key = path.rsplit(".", 1)
    del get_path(payload, parent)[key]
    assert path in _problems(payload)


def test_unknown_keys_rejected_at_every_level():
    for path in ("", "universe", "exits", "exits.selection", "exits.selection.eligibility"):
        payload = draft_skeleton()
        node = get_path(payload, path) if path else payload
        node["surprise"] = 1
        assert "surprise" in _problems(payload)


def test_candidate_unknown_key_rejected():
    payload = complete_payload()
    payload["exits"]["candidates"][0]["extra"] = 1
    assert "extra" in _problems(payload)


def test_unset_p0_fields_error_names_every_field():
    payload = complete_payload()
    for path in ("gates.win_rate", "exits.selection.score", "stats.bootstrap.method"):
        set_path(payload, path, None)
    with pytest.raises(UnsetP0FieldsError) as ei:
        FrozenSpec.from_draft(parse_draft(payload))
    assert set(ei.value.fields) == {
        "gates.win_rate",
        "exits.selection.score",
        "stats.bootstrap.method",
    }
    assert "gates.win_rate" in str(ei.value)


def test_blank_open_values_count_as_unset():
    payload = complete_payload()
    set_path(payload, "gates.win_rate", "  ")
    set_path(payload, "costs.components", [])
    set_path(payload, "governance.roles", {"owner": None})
    unset = parse_draft(payload).unset_p0_fields()
    assert "gates.win_rate" in unset and "costs.components" in unset
    assert "governance.roles.owner" in unset


def test_complete_synthetic_spec_freezes():
    FrozenSpec.from_draft(parse_draft(complete_payload()))


@pytest.mark.parametrize(
    "path,bad",
    [
        ("data.feed", "iex"),
        ("universe.min_price", 11.0),
        ("universe.rebuild", "daily"),
        ("costs.base_bps_per_side", 6),
        ("costs.stress_bps_per_side", 10),
        ("gates.min_trades", 100),
        ("gates.pf_base", 1.2),
        ("gates.redundancy_corr_max", 0.9),
        ("p5.min_days", 30),
        ("p5.min_trades", 50),
        ("p5.max_cost_ratio", 2.0),
        ("exit.eod_flat", "15:50:00"),
        ("signal.entry_window", ["10:00:00", "15:00:00"]),
        ("signal.tick_offset", 2),
        ("gates.stress_mean_positive", False),
    ],
)
def test_fixed_skeleton_values_cannot_be_altered(path, bad):
    payload = draft_skeleton()
    set_path(payload, path, bad)
    assert path in _problems(payload)


@pytest.mark.parametrize(
    "path,bad",
    [
        ("stats.alpha_one_sided", 1.5),
        ("stats.alpha_one_sided", 0),
        ("stats.bootstrap.confidence_level", 1.0),
        ("stats.bootstrap.ci_type", "  "),
        ("universe.n", 0),
        ("risk.per_trade_pct", -1),
        ("execution.vendor_delay_ms", -1),
        ("execution.order_type", "market"),
        ("governance.economic_thesis_sha", "xyz"),
        ("stats.bootstrap.method", " "),
    ],
)
def test_p0_values_that_are_set_are_sanity_checked(path, bad):
    payload = draft_skeleton()
    set_path(payload, path, bad)
    assert path in _problems(payload)


# ---- exits (Addendum A1) ----


def _with_candidates(cands):
    payload = complete_payload()
    payload["exits"]["candidates"] = cands
    return payload


def test_eight_candidates_ok_nine_rejected():
    ok = [{"id": f"E{i}", "family": "time", "params": {}} for i in range(8)]
    parse_draft(_with_candidates(ok))
    ok.append({"id": "E8", "family": "time", "params": {}})
    assert "1..8" in _problems(_with_candidates(ok))


def test_empty_candidate_list_rejected():
    assert "1..8" in _problems(_with_candidates([]))


def test_unknown_family_rejected():
    bad = copy.deepcopy(CANDIDATES)
    bad[0]["family"] = "vwap_trail"
    assert "family" in _problems(_with_candidates(bad))


def test_duplicate_ids_rejected():
    bad = copy.deepcopy(CANDIDATES)
    bad[1]["id"] = "X1"
    assert "duplicate candidate id" in _problems(_with_candidates(bad))


def test_bad_candidate_id_rejected():
    bad = copy.deepcopy(CANDIDATES)
    bad[0]["id"] = "has space"
    assert "id" in _problems(_with_candidates(bad))


def test_all_four_families_accepted():
    cands = [
        {"id": "A", "family": "time", "params": {}},
        {"id": "B", "family": "fixed_r", "params": {"k": 2}},
        {"id": "C", "family": "trailing", "params": {"t": 1.5}},
        {"id": "D", "family": "scale_out", "params": {"frac": 0.5}},
    ]
    parse_draft(_with_candidates(cands))


def test_complexity_order_must_rank_every_candidate_family():
    payload = complete_payload()
    payload["exits"]["complexity_order"] = ["time"]
    assert "complexity_order does not rank" in _problems(payload)


def test_complexity_order_rejects_repeats_and_unknown_families():
    payload = complete_payload()
    payload["exits"]["complexity_order"] = ["time", "time"]
    assert "complexity_order" in _problems(payload)
    payload["exits"]["complexity_order"] = ["time", "magic"]
    assert "complexity_order" in _problems(payload)


def test_missing_selection_block_or_field_rejected_in_draft():
    payload = complete_payload()
    del payload["exits"]["selection"]
    assert "exits.selection" in _problems(payload)
    payload = complete_payload()
    del payload["exits"]["selection"]["tie_tolerance_r"]
    assert "exits.selection.tie_tolerance_r" in _problems(payload)


@pytest.mark.parametrize(
    "field",
    [
        "score",
        "tie_tolerance_r",
        "eligibility.min_trades",
        "eligibility.min_pf",
        "stop_test",
    ],
)
def test_missing_selection_field_rejected_at_freeze_time(field):
    payload = complete_payload()
    set_path(payload["exits"]["selection"], field, None)
    with pytest.raises(UnsetP0FieldsError) as ei:
        FrozenSpec.from_draft(parse_draft(payload))
    assert f"exits.selection.{field}" in ei.value.fields


def test_candidates_null_blocks_freeze():
    payload = complete_payload()
    payload["exits"]["candidates"] = None
    with pytest.raises(UnsetP0FieldsError) as ei:
        FrozenSpec.from_draft(parse_draft(payload))
    assert "exits.candidates" in ei.value.fields


# ---- partitions ----


def test_partitions_parse_to_dates():
    p = parse_draft(draft_skeleton()).partitions
    assert p.holdout == (date(2022, 1, 1), date(2025, 12, 31))
    assert p.exposed == ((date(2026, 1, 1), date(2026, 7, 31)),)


def test_partition_value_edits_rejected():
    payload = draft_skeleton()
    payload["partitions"]["holdout"] = ["2021-06-01", "2025-12-31"]  # overlaps P3b
    assert "partitions.holdout" in _problems(payload)


def test_missing_exposed_window_rejected():
    payload = draft_skeleton()
    payload["partitions"]["exposed"] = []
    assert "partitions.exposed" in _problems(payload)


def test_layout_validator_rejects_overlap_reversal_and_misorder():
    d = date
    validate_partition_layout(
        [("a", d(2016, 1, 1), d(2016, 12, 31)), ("b", d(2017, 1, 1), d(2017, 2, 1))]
    )
    with pytest.raises(ValueError, match="overlaps"):
        validate_partition_layout(
            [("a", d(2016, 1, 1), d(2016, 12, 31)), ("b", d(2016, 12, 31), d(2017, 2, 1))]
        )
    with pytest.raises(ValueError, match="overlaps or precedes"):
        validate_partition_layout(
            [("a", d(2018, 1, 1), d(2018, 12, 31)), ("b", d(2016, 1, 1), d(2016, 2, 1))]
        )
    with pytest.raises(ValueError, match="after end"):
        validate_partition_layout([("a", d(2018, 1, 1), d(2017, 12, 31))])


def test_draft_spec_is_immutable():
    draft = parse_draft(draft_skeleton())
    with pytest.raises(Exception):  # noqa: B017 - pydantic ValidationError on frozen assignment
        draft.program = "X"  # type: ignore[misc,assignment]


def test_non_finite_numbers_rejected():
    payload = complete_payload()
    payload["exits"]["candidates"][1]["params"]["synthetic_k"] = float("inf")
    assert "params" in _problems(payload)
    assert isinstance(parse_draft(complete_payload()), DraftSpec)
