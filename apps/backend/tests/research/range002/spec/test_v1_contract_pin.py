"""Regression pins for the CURRENT RANGE-002 spec contract (spec_version 1).

These tests record what the merged v1 contract does today: the parse contract (strict types,
closed key sets, required keys), the content that the spec hash covers, and the unset-leaf rule.
They are change detectors only. They are not an approval of any architecture, any proposed P5
contract or any decision value; any deliberate change to the v1 contract needs its own decision.

Synthetic fixtures only (``_fixtures.complete_payload``). Digest-free: no test compares anything to
a stored hash. Where a hash is used, two hashes computed in the same process are compared to each
other. The P5 constants asserted below (60 days, 100 trades, 1.5 cost ratio) are the EXISTING v1
behavior; they are not newly approved P5 policy, and the newer 120-day requirement remains an
unadopted proposal.
"""

from __future__ import annotations

import copy
from typing import Any

import pytest

from app.research.range002.spec.loader import SpecSchemaError, parse_draft, spec_sha256
from app.research.range002.spec.schema import (
    P5,
    DraftSpec,
    FrozenSpec,
    UnsetP0FieldsError,
    draft_skeleton,
)

from ._fixtures import complete_payload, get_path, set_path


def _dict_nodes(node: dict[str, Any], path: str = "") -> list[str]:
    """Dotted paths of every dict node of the skeleton ('' is the root). The skeleton's dict
    nodes are exactly the model nodes; open P0 values are None there."""
    out = [path]
    for key, value in node.items():
        if isinstance(value, dict) and value:
            out.extend(_dict_nodes(value, f"{path}.{key}" if path else key))
    return out


def _node(payload: dict[str, Any], path: str) -> dict[str, Any]:
    return payload if path == "" else get_path(payload, path)


def _dotted(path: str, key: str) -> str:
    return f"{path}.{key}" if path else key


def _problems(payload: Any) -> tuple[str, ...]:
    with pytest.raises(SpecSchemaError) as info:
        parse_draft(payload)
    return info.value.problems


def _names(problems: tuple[str, ...]) -> list[str]:
    return [p.split(": ", 1)[0] for p in problems]


_SKELETON_NODES = _dict_nodes(draft_skeleton())


# ---- G-01: spec_version accepts only the integer 1 ------------------------------------------


@pytest.mark.parametrize("bad", [2, 0, -1, 1.0, False, None, "1", True])
def test_spec_version_rejects_everything_but_the_int_one(bad):
    payload = complete_payload()
    set_path(payload, "spec_version", bad)
    assert "spec_version" in _names(_problems(payload))


def test_spec_version_key_is_required():
    payload = complete_payload()
    del payload["spec_version"]
    assert "spec_version" in _names(_problems(payload))


def test_spec_version_accepts_the_int_one_and_keeps_its_type():
    spec = parse_draft(complete_payload())
    assert spec.spec_version == 1
    assert type(spec.spec_version) is int


# ---- G-02: unknown keys are rejected at every model node ------------------------------------


def test_the_node_walk_is_not_vacuous():
    # Guards the parametrization below: it must cover the nodes that matter.
    expected = {"", "p5", "data", "risk", "controls.random_entry", "governance", "signoff"}
    assert expected <= set(_SKELETON_NODES)
    assert len(_SKELETON_NODES) >= 20


@pytest.mark.parametrize("node_path", _SKELETON_NODES)
def test_unknown_key_is_rejected_at_every_model_node(node_path):
    payload = complete_payload()
    _node(payload, node_path)["surprise_key"] = 1
    assert _dotted(node_path, "surprise_key") in _names(_problems(payload))


# ---- G-03: every key of every model node is required ----------------------------------------


def _every_key() -> list[tuple[str, str]]:
    skeleton = draft_skeleton()
    return [(path, key) for path in _SKELETON_NODES for key in _node(skeleton, path)]


def test_the_required_key_walk_is_not_empty():
    assert len(_every_key()) > 100


@pytest.mark.parametrize(("node_path", "key"), _every_key())
def test_missing_key_is_reported_under_its_dotted_name(node_path, key):
    payload = draft_skeleton()
    del _node(payload, node_path)[key]
    assert _dotted(node_path, key) in _names(_problems(payload))


# ---- G-04: the current v1 P5 shape and constants --------------------------------------------


def test_p5_field_set_is_exactly_the_current_v1_set():
    assert set(P5.model_fields) == {
        "account_id",
        "min_days",
        "min_trades",
        "max_cost_ratio",
        "degradation_tolerance",
        "cost_ratio_contract",
        "shadow_acceptance",
    }


def test_p5_constants_are_the_existing_v1_values():
    # Existing v1 behavior only. Not a decision about DEP-9 or about any P5 value.
    p5 = draft_skeleton()["p5"]
    assert p5["min_days"] == 60
    assert p5["min_trades"] == 100
    assert p5["max_cost_ratio"] == 1.5
    assert p5["account_id"] is None


def test_skeleton_and_complete_payload_parse_with_the_v1_p5_block():
    for payload in (draft_skeleton(), complete_payload()):
        spec = parse_draft(payload)
        assert (spec.p5.min_days, spec.p5.min_trades, spec.p5.max_cost_ratio) == (60, 100, 1.5)


# ---- G-04b: the v1 P5 constants as CONTRACT behavior (historical v1 pins) -------------------
# HISTORICAL v1 compatibility pins: parse_draft rejects any p5 value other than the three fixed
# v1 constants. They record today's behavior; they are not adopted v2/P5 policy, and the 120-day
# proposal stays unadopted.


@pytest.mark.parametrize(
    ("field", "bad"),
    [
        ("min_days", 59),
        ("min_days", 61),
        ("min_days", 120),
        ("min_days", 0),
        ("min_trades", 99),
        ("min_trades", 101),
        ("min_trades", 0),
        ("max_cost_ratio", 1.4),
        ("max_cost_ratio", 1.6),
        ("max_cost_ratio", 0.0),
    ],
)
def test_p5_fixed_constants_reject_any_other_value_in_v1(field, bad):
    payload = complete_payload()
    set_path(payload, f"p5.{field}", bad)
    assert f"p5.{field}" in _names(_problems(payload))


@pytest.mark.parametrize(
    ("field", "bad"),
    [
        ("min_days", 60.0),
        ("min_days", "60"),
        ("min_days", None),
        ("min_trades", 100.0),
        ("min_trades", "100"),
        ("min_trades", None),
        ("max_cost_ratio", "1.5"),
        ("max_cost_ratio", None),
    ],
)
def test_p5_fixed_constants_are_type_strict_in_v1(field, bad):
    # Existing strict-model behavior: no lax coercion of the right number in the wrong type.
    payload = complete_payload()
    set_path(payload, f"p5.{field}", bad)
    assert f"p5.{field}" in _names(_problems(payload))


@pytest.mark.parametrize("field", ["min_days", "min_trades", "max_cost_ratio"])
def test_p5_fixed_constants_are_required_keys_in_v1(field):
    payload = complete_payload()
    del payload["p5"][field]
    assert f"p5.{field}" in _names(_problems(payload))


def test_p5_wrong_constants_are_all_reported_together_in_v1():
    payload = complete_payload()
    set_path(payload, "p5.min_days", 61)
    set_path(payload, "p5.min_trades", 101)
    set_path(payload, "p5.max_cost_ratio", 1.6)
    names = _names(_problems(payload))
    assert {"p5.min_days", "p5.min_trades", "p5.max_cost_ratio"} <= set(names)


def test_p5_constants_do_not_perturb_other_fields_when_correct_in_v1():
    payload = complete_payload()
    set_path(payload, "p5.min_days", 60)
    set_path(payload, "p5.min_trades", 100)
    set_path(payload, "p5.max_cost_ratio", 1.5)
    assert parse_draft(payload).p5.min_days == 60


# ---- G-05: the hashed content is everything except the sign-off block -----------------------


def test_hashable_payload_excludes_exactly_signoff():
    spec = parse_draft(complete_payload())
    payload = spec.hashable_payload()
    assert set(payload) == set(DraftSpec.model_fields) - {"signoff"}
    assert "signoff" not in payload
    for key in ("program", "spec_version", "p5", "governance"):
        assert key in payload


def test_hashable_payload_does_not_mutate_the_spec():
    spec = parse_draft(complete_payload())
    before = spec.model_dump(mode="json")
    spec.hashable_payload()
    assert spec.model_dump(mode="json") == before
    assert spec.signoff.owner == "SYNTH-OWNER"


def test_spec_hash_ignores_every_signoff_field():
    base = spec_sha256(parse_draft(complete_payload()))
    changes = {
        "signoff.owner": "OTHER-OWNER",
        "signoff.trading_expert": "OTHER-EXPERT",
        "signoff.independent_validator": "OTHER-VALIDATOR",
        "signoff.date": "2001-02-03",
        "signoff.spec_sha256": "cd" * 32,
    }
    for path, value in changes.items():
        payload = complete_payload()
        set_path(payload, path, value)
        assert spec_sha256(parse_draft(payload)) == base, path
    assert spec_sha256(parse_draft(complete_payload(signed=False))) == base


def test_spec_hash_covers_non_signoff_content():
    base = spec_sha256(parse_draft(complete_payload()))
    for path, value in (("p5.degradation_tolerance", "OTHER"), ("universe.n", 4)):
        payload = complete_payload()
        set_path(payload, path, value)
        assert spec_sha256(parse_draft(payload)) != base, path


# ---- G-06: the unset-leaf rule and registration.trial_ledger_id -----------------------------


def test_unsigned_complete_draft_has_no_unset_p0_fields_and_freezes():
    spec = parse_draft(complete_payload(signed=False))
    assert spec.unset_p0_fields() == []
    FrozenSpec.from_draft(spec)


def test_trial_ledger_id_is_hashed_even_though_it_is_not_a_p0_leaf():
    base_spec = parse_draft(complete_payload())
    assert "registration.trial_ledger_id" not in base_spec.unset_p0_fields()
    payload = complete_payload()
    set_path(payload, "registration.trial_ledger_id", "SYNTH-LEDGER")
    changed = parse_draft(payload)
    assert "registration.trial_ledger_id" not in changed.unset_p0_fields()
    assert spec_sha256(changed) != spec_sha256(base_spec)


def test_skeleton_unset_list_is_sorted_and_excludes_signoff_and_ledger_id():
    unset = parse_draft(draft_skeleton()).unset_p0_fields()
    assert unset
    assert unset == sorted(unset)
    assert "registration.trial_ledger_id" not in unset
    assert not any(path.split(".")[0] == "signoff" for path in unset)


# ---- G-06b: freeze refusal while P0 leaves are unset (historical v1 behavior) ---------------


def test_freezing_the_skeleton_is_refused_and_names_every_unset_leaf():
    spec = parse_draft(draft_skeleton())
    unset = spec.unset_p0_fields()
    assert unset
    with pytest.raises(UnsetP0FieldsError) as info:
        FrozenSpec.from_draft(spec)
    assert list(info.value.fields) == unset
    assert str(len(unset)) in str(info.value)
    assert all(leaf in str(info.value) for leaf in unset)


def test_unset_error_is_a_value_error_and_direct_construction_is_refused_too():
    assert issubclass(UnsetP0FieldsError, ValueError)
    with pytest.raises(UnsetP0FieldsError):
        FrozenSpec(parse_draft(draft_skeleton()))


def test_the_skeleton_unset_leaves_include_the_p5_leaves():
    unset = parse_draft(draft_skeleton()).unset_p0_fields()
    assert "p5.account_id" in unset
    assert any(path.startswith("p5.") for path in unset)


@pytest.mark.parametrize(
    "leaf",
    ["p5.account_id", "p5.degradation_tolerance", "p5.cost_ratio_contract", "p5.shadow_acceptance"],
)
def test_a_single_unset_p5_leaf_alone_blocks_the_freeze(leaf):
    payload = complete_payload(signed=False)
    set_path(payload, leaf, None)
    spec = parse_draft(payload)
    assert spec.unset_p0_fields() == [leaf]
    with pytest.raises(UnsetP0FieldsError) as info:
        FrozenSpec.from_draft(spec)
    assert info.value.fields == (leaf,)
    assert leaf in str(info.value)


def test_a_single_unset_non_p5_leaf_alone_blocks_the_freeze():
    payload = complete_payload(signed=False)
    set_path(payload, "governance.economic_thesis_sha", None)
    spec = parse_draft(payload)
    with pytest.raises(UnsetP0FieldsError) as info:
        FrozenSpec.from_draft(spec)
    assert info.value.fields == ("governance.economic_thesis_sha",)


def test_a_complete_draft_freezes_and_exposes_the_same_draft():
    spec = parse_draft(complete_payload(signed=False))
    frozen = FrozenSpec.from_draft(spec)
    assert frozen.draft is spec
    with pytest.raises(AttributeError):
        frozen.draft = spec  # type: ignore[misc]


# ---- G-07: the SpecSchemaError contract -----------------------------------------------------


def test_spec_schema_error_is_a_value_error():
    assert issubclass(SpecSchemaError, ValueError)


def test_problems_are_a_sorted_tuple_of_dotted_name_messages():
    payload = complete_payload()
    set_path(payload, "universe.n", "not-an-int")
    payload["p5"]["surprise_key"] = 1
    del payload["gates"]["win_rate"]
    problems = _problems(payload)
    assert isinstance(problems, tuple)
    assert all(isinstance(p, str) for p in problems)
    assert list(problems) == sorted(problems)
    assert all(": " in p for p in problems)


def test_all_simultaneous_defects_are_reported_in_one_error():
    payload = complete_payload()
    set_path(payload, "universe.n", "not-an-int")
    payload["p5"]["surprise_key"] = 1
    del payload["gates"]["win_rate"]
    names = _names(_problems(payload))
    assert {"universe.n", "p5.surprise_key", "gates.win_rate"} <= set(names)


@pytest.mark.parametrize("payload", [[], "x", 3, None])
def test_non_object_payloads_raise_the_schema_error(payload):
    with pytest.raises(SpecSchemaError):
        parse_draft(copy.deepcopy(payload))
