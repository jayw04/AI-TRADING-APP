"""WP0.2 hash stability: key order, whitespace, float formatting, sensitivity to any change."""

from __future__ import annotations

import copy
import json

import pytest

from app.research.range002.spec.hashing import (
    CanonicalisationError,
    canonical_json,
    content_sha256,
    file_sha256,
)
from app.research.range002.spec.loader import parse_draft, spec_sha256

from ._fixtures import P0_PATHS, complete_payload, get_path, set_path


def test_key_order_does_not_change_canonical_bytes():
    a = {"b": 1, "a": {"y": [1, 2], "x": None}}
    b = {"a": {"x": None, "y": [1, 2]}, "b": 1}
    assert canonical_json(a) == canonical_json(b)
    assert canonical_json(a) == b'{"a":{"x":null,"y":[1,2]},"b":1}'


def test_whitespace_and_key_order_in_the_file_do_not_change_the_spec_hash():
    payload = complete_payload()
    compact = json.dumps(payload, separators=(",", ":"))
    pretty = json.dumps(payload, indent=4, sort_keys=True)
    reversed_keys = json.dumps(dict(reversed(list(payload.items()))), indent=1)
    hashes = {spec_sha256(parse_draft(json.loads(t))) for t in (compact, pretty, reversed_keys)}
    assert len(hashes) == 1


@pytest.mark.parametrize("a,b", [(5, 5.0), (0, -0.0), (1500, 1.5e3), (10, 10.00)])
def test_integral_floats_hash_like_ints(a, b):
    assert canonical_json({"v": a}) == canonical_json({"v": b})


def test_non_integral_floats_use_shortest_round_trip_repr():
    assert canonical_json({"v": 0.1}) == b'{"v":0.1}'
    assert canonical_json({"v": 1.30}) == b'{"v":1.3}'
    assert canonical_json({"v": 1e-7}) == b'{"v":1e-07}'
    # the same value reached through different arithmetic is still a different float; the hash
    # is over the stored value, not over how it was typed.
    assert canonical_json({"v": 0.1 + 0.2}) != canonical_json({"v": 0.3})


def test_float_typed_fields_hash_identically_whether_int_or_float_in_the_file():
    a = complete_payload()
    b = copy.deepcopy(a)
    a["gates"]["pf_base"] = 1.3
    b["gates"]["pf_base"] = 1.30
    a["costs"]["base_bps_per_side"] = 5
    b["costs"]["base_bps_per_side"] = 5.0
    assert spec_sha256(parse_draft(a)) == spec_sha256(parse_draft(b))


@pytest.mark.parametrize("bad", [float("nan"), float("inf"), -float("inf")])
def test_non_finite_numbers_refused(bad):
    with pytest.raises(CanonicalisationError):
        canonical_json({"v": bad})


def test_unsupported_types_and_non_string_keys_refused():
    with pytest.raises(CanonicalisationError):
        canonical_json({"v": {1, 2}})
    with pytest.raises(CanonicalisationError):
        canonical_json({1: "x"})


def test_hash_is_64_hex_and_deterministic():
    h = spec_sha256(parse_draft(complete_payload()))
    assert len(h) == 64 and set(h) <= set("0123456789abcdef")
    assert h == spec_sha256(parse_draft(complete_payload()))
    assert h == content_sha256(parse_draft(complete_payload()).hashable_payload())


def _changed(path: str, old):
    if isinstance(old, bool):
        return not old
    if isinstance(old, int | float):
        return old + 1
    if isinstance(old, str):
        return old + "x"
    return None


@pytest.mark.parametrize("path", P0_PATHS)
def test_changing_any_p0_field_changes_the_hash(path):
    base = complete_payload()
    original = spec_sha256(parse_draft(base))
    edited = copy.deepcopy(base)
    old = get_path(edited, path)
    if path == "exits.candidates":
        edited["exits"]["candidates"][0]["id"] = "Z9"
    elif path == "exits.complexity_order":
        edited["exits"]["complexity_order"] = ["time", "fixed_r", "scale_out", "trailing"]
    elif path == "governance.economic_thesis_sha":
        edited["governance"]["economic_thesis_sha"] = "cd" * 32
    elif path == "governance.registry_genesis_id":
        edited["governance"]["registry_genesis_id"] = "cd" * 16
    elif path == "execution.bar_timestamp_convention":
        edited["execution"]["bar_timestamp_convention"] = "end"
    elif path == "execution.crossed_before_arm_policy":
        edited["execution"]["crossed_before_arm_policy"] = "REQUIRE_RETRACE"
    elif path == "execution.order_type":
        edited["execution"]["order_type"] = "stop_limit"
    elif path == "costs.accounting_mode":
        edited["costs"]["accounting_mode"] = "itemized_additive"
    elif path == "stats.alpha_one_sided":
        edited["stats"]["alpha_one_sided"] = 0.08
    elif path == "stats.bootstrap.confidence_level":
        edited["stats"]["bootstrap"]["confidence_level"] = 0.8
    elif path == "gates.basis":
        edited["gates"]["basis"] = "portfolio_constrained"
    elif isinstance(old, list):
        set_path(edited, path, [*old, "extra"])
    elif isinstance(old, dict):
        set_path(edited, path, {**old, "extra": 1})
    else:
        set_path(edited, path, _changed(path, old))
    assert spec_sha256(parse_draft(edited)) != original, path


def test_changing_a_candidate_param_or_order_changes_the_hash():
    base = complete_payload()
    h = spec_sha256(parse_draft(base))
    p = copy.deepcopy(base)
    p["exits"]["candidates"][1]["params"]["synthetic_k"] = 2.0
    assert spec_sha256(parse_draft(p)) != h
    p = copy.deepcopy(base)
    p["exits"]["candidates"].reverse()
    assert spec_sha256(parse_draft(p)) != h


def test_signoff_is_not_part_of_the_hash():
    a = complete_payload(signed=True)
    b = complete_payload(signed=False)
    assert spec_sha256(parse_draft(a)) == spec_sha256(parse_draft(b))


def test_file_sha256_matches_bytes(tmp_path):
    f = tmp_path / "x.bin"
    f.write_bytes(b"abc")
    assert file_sha256(f) == "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"


# --- serialization semantics shared with the exposure ledger ---------------------------------


def test_loads_strict_rejects_duplicate_keys_nan_and_garbage():
    from app.research.range002.spec.hashing import CanonicalisationError, loads_strict

    assert loads_strict(b'{"a": 1}') == {"a": 1}
    for bad in ('{"a": 1, "a": 2}', '{"a": NaN}', '{"a": Infinity}', "{", "", bytes([0xFF])):
        with pytest.raises(CanonicalisationError):
            loads_strict(bad)


def test_loaded_spec_hash_ignores_formatting():
    import json

    from app.research.range002.spec.hashing import content_sha256, loads_strict

    payload = complete_payload()
    pretty, compact = json.dumps(payload, indent=4), json.dumps(payload, separators=(",", ":"))
    assert content_sha256(loads_strict(pretty)) == content_sha256(loads_strict(compact))
