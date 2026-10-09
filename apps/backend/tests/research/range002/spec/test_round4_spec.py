"""Round-4 spec/schema/loader/freeze hardening (Level 1 only: accidental misuse, casual bypass).

Synthetic fixtures only. Nothing here chooses a RANGE-002 decision value.
"""

from __future__ import annotations

import copy
import dataclasses
import json
import pickle
from datetime import date
from pathlib import Path
from types import MappingProxyType

import pytest

from app.research.range002.spec import loader
from app.research.range002.spec.loader import (
    SpecSchemaError,
    SpecViewNotCopyableError,
    is_loader_minted,
    load_frozen,
    parse_draft,
)
from app.research.range002.spec.schema import (
    FrozenSpec,
    UnsetP0FieldsError,
    draft_skeleton,
)

from ._fixtures import SYNTH_GENESIS_ID, complete_payload, set_path
from .test_freeze import cli

GENESIS_32 = "0123456789abcdef" * 2  # legacy 32-hex shape: now REJECTED
GENESIS_64 = "ab" * 32  # legacy 64-hex shape: now REJECTED


def _problems(payload: dict) -> str:
    with pytest.raises(SpecSchemaError) as ei:
        parse_draft(payload)
    return str(ei.value)


# ---- N1(b): governance.registry_genesis_id ---------------------------------------------------


def test_skeleton_has_registry_genesis_id_unset_and_freeze_names_it():
    skeleton = draft_skeleton()
    assert skeleton["governance"]["registry_genesis_id"] is None
    unset = parse_draft(skeleton).unset_p0_fields()
    assert "governance.registry_genesis_id" in unset
    payload = complete_payload()
    set_path(payload, "governance.registry_genesis_id", None)
    with pytest.raises(UnsetP0FieldsError) as ei:
        FrozenSpec.from_draft(parse_draft(payload))
    assert "governance.registry_genesis_id" in ei.value.fields


def test_registry_genesis_id_key_is_required_not_defaulted():
    payload = complete_payload()
    del payload["governance"]["registry_genesis_id"]
    assert "governance.registry_genesis_id" in _problems(payload)


@pytest.mark.parametrize(
    "bad",
    [
        "xyz",
        "",
        12345,
        GENESIS_32,  # the legacy hex shapes are no longer accepted
        GENESIS_64,
        SYNTH_GENESIS_ID.upper(),  # not lowercase
        SYNTH_GENESIS_ID.replace("-", ""),  # no hyphens
        "{" + SYNTH_GENESIS_ID + "}",
        "urn:uuid:" + SYNTH_GENESIS_ID,
        " " + SYNTH_GENESIS_ID,
        SYNTH_GENESIS_ID + "\n",
        "5eed5eed-5eed-1eed-9eed-5eed5eed5eed",  # version 1, not 4
        "5eed5eed-5eed-4eed-1eed-5eed5eed5eed",  # bad variant
        "00000000-0000-0000-0000-000000000000",  # nil UUID
    ],
)
def test_registry_genesis_id_rejects_malformed_values(bad):
    payload = complete_payload()
    set_path(payload, "governance.registry_genesis_id", bad)
    assert "governance.registry_genesis_id" in _problems(payload)


@pytest.mark.parametrize("good", [SYNTH_GENESIS_ID, "0badc0de-0bad-4ade-8bad-0badc0de0bad"])
def test_registry_genesis_id_accepts_canonical_uuid4(good):
    payload = complete_payload()
    set_path(payload, "governance.registry_genesis_id", good)
    FrozenSpec.from_draft(parse_draft(payload))


def test_registry_genesis_id_is_in_the_spec_hash():
    a = complete_payload()
    b = complete_payload()
    set_path(b, "governance.registry_genesis_id", "0badc0de-0bad-4ade-8bad-0badc0de0bad")
    assert loader.spec_sha256(parse_draft(a)) != loader.spec_sha256(parse_draft(b))


def test_view_carries_registry_genesis_id(tmp_path):
    view = _minted(tmp_path)
    assert isinstance(view.registry_genesis_id, str) and view.registry_genesis_id


# ---- N2(e): attempt limits --------------------------------------------------------------------


@pytest.mark.parametrize("field", ["max_p3a_attempts", "max_p3b_attempts"])
def test_attempt_limit_fields_are_unset_in_skeleton_and_required_at_freeze(field):
    assert draft_skeleton()["p3"][field] is None
    assert f"p3.{field}" in parse_draft(draft_skeleton()).unset_p0_fields()
    payload = complete_payload()
    set_path(payload, f"p3.{field}", None)
    with pytest.raises(UnsetP0FieldsError) as ei:
        FrozenSpec.from_draft(parse_draft(payload))
    assert f"p3.{field}" in ei.value.fields


@pytest.mark.parametrize("field", ["max_p3a_attempts", "max_p3b_attempts"])
@pytest.mark.parametrize("bad", [0, -1, 2.5, "3", True])
def test_attempt_limit_fields_reject_non_positive_or_non_int(field, bad):
    payload = complete_payload()
    set_path(payload, f"p3.{field}", bad)
    with pytest.raises((SpecSchemaError, ValueError)):
        parse_draft(payload)


@pytest.mark.parametrize("field", ["max_p3a_attempts", "max_p3b_attempts"])
@pytest.mark.parametrize("bad", [10_001, 10**9])
def test_attempt_limit_fields_reject_values_above_the_technical_bound(field, bad):
    payload = complete_payload()
    set_path(payload, f"p3.{field}", bad)
    with pytest.raises((SpecSchemaError, ValueError)):
        parse_draft(payload)


@pytest.mark.parametrize("field", ["max_p3a_attempts", "max_p3b_attempts"])
def test_attempt_limit_at_the_technical_bound_still_validates(field):
    from app.research.range002.spec.limits import MAX_ATTEMPT_LIMIT

    payload = complete_payload()
    set_path(payload, f"p3.{field}", MAX_ATTEMPT_LIMIT)
    assert getattr(parse_draft(payload).p3, field) == MAX_ATTEMPT_LIMIT


@pytest.mark.parametrize("field", ["max_p3a_attempts", "max_p3b_attempts"])
def test_attempt_limit_key_is_required_not_defaulted(field):
    payload = complete_payload()
    del payload["p3"][field]
    assert f"p3.{field}" in _problems(payload)


def test_view_carries_attempt_limits(tmp_path):
    view = _minted(tmp_path)
    assert isinstance(view.max_p3a_attempts, int) and isinstance(view.max_p3b_attempts, int)


# ---- N4: deep-frozen view values ---------------------------------------------------------------


def _draft_view(payload: dict):
    draft = parse_draft(payload)
    view = loader._build_view(draft, spec_sha256="a" * 64, unusable_reasons=())
    return draft, view


def _plain(value):
    if isinstance(value, MappingProxyType):
        return {k: _plain(v) for k, v in value.items()}
    if isinstance(value, tuple | list):
        return [_plain(v) for v in value]
    return value


def test_view_values_are_immutable_and_independent_of_the_draft_dicts():
    payload = complete_payload()
    set_path(payload, "p3.criteria", {"k": [1, {"deep": [2]}]})
    set_path(payload, "governance.exposure_signed", {"exposure_ledger_sha256": "a" * 64, "n": [1]})
    draft, view = _draft_view(payload)

    assert isinstance(view.p3_criteria, MappingProxyType)
    assert isinstance(view.p3_criteria["k"], tuple)
    assert isinstance(view.p3_criteria["k"][1], MappingProxyType)
    with pytest.raises(TypeError):
        view.p3_criteria["new"] = 1  # type: ignore[index]
    with pytest.raises(TypeError):
        view.exposure_signed["x"] = 1  # type: ignore[index]
    assert isinstance(view.exposure_signed["n"], tuple)

    before = json.dumps(_plain(view.p3_criteria), sort_keys=True)
    before_exp = json.dumps(_plain(view.exposure_signed), sort_keys=True)
    # mutate the ORIGINAL dicts the draft still owns: the view must not move
    draft.p3.criteria["k"].append("MUTATED")  # type: ignore[union-attr,index]
    draft.p3.criteria["k"][1]["deep"].append("MUTATED")  # type: ignore[union-attr,index]
    draft.governance.exposure_signed["exposure_ledger_sha256"] = "b" * 64  # type: ignore[index]
    draft.governance.exposure_signed["n"].append("MUTATED")  # type: ignore[union-attr,index]
    assert json.dumps(_plain(view.p3_criteria), sort_keys=True) == before
    assert json.dumps(_plain(view.exposure_signed), sort_keys=True) == before_exp


def test_view_exit_candidates_and_selection_are_deep_frozen():
    draft, view = _draft_view(complete_payload())
    assert view.exits_candidates is not None and view.exits_selection is not None
    first = view.exits_candidates[0]
    assert isinstance(first, MappingProxyType) and isinstance(first["params"], MappingProxyType)
    with pytest.raises(TypeError):
        first["params"]["x"] = 1  # type: ignore[index]
    draft.exits.candidates[1].params["synthetic_k"] = 99.0  # type: ignore[index]
    assert view.exits_candidates[1]["params"]["synthetic_k"] == 1.0
    assert isinstance(view.exits_selection, MappingProxyType)


def test_deep_freeze_leaves_none_and_scalars_alone():
    from app.research.range002.spec.immutable import deep_freeze

    assert deep_freeze(None) is None
    assert deep_freeze(3) == 3 and deep_freeze("s") == "s" and deep_freeze(True) is True
    assert deep_freeze(date(2020, 1, 1)) == date(2020, 1, 1)
    assert deep_freeze([1, [2]]) == (1, (2,))
    frozen = deep_freeze({"a": {"b": [1]}})
    assert deep_freeze(frozen) == frozen and isinstance(frozen["a"], MappingProxyType)


def test_deep_freeze_refuses_unknown_object_types():
    from app.research.range002.spec.immutable import deep_freeze

    with pytest.raises(TypeError):
        deep_freeze(object())


# ---- N4: minted markers are non-copyable ---------------------------------------------------------


def _minted(tmp_path):
    payload = complete_payload()
    draft = tmp_path / "d.json"
    draft.write_text(json.dumps(payload), encoding="utf-8")
    out = tmp_path / "f.json"
    cli.freeze(draft, out)
    return load_frozen(out)


def test_minted_specview_cannot_be_copied_deepcopied_or_pickled(tmp_path):
    view = _minted(tmp_path)
    assert is_loader_minted(view)
    for attempt in (copy.copy, copy.deepcopy, pickle.dumps):
        with pytest.raises(SpecViewNotCopyableError):
            attempt(view)
    assert not is_loader_minted(dataclasses.replace(view))


# ---- N8: a failed round trip removes the written file ---------------------------------------------


def test_freeze_removes_the_file_when_the_round_trip_load_raises(tmp_path, monkeypatch):
    draft = tmp_path / "d.json"
    draft.write_text(json.dumps(complete_payload()), encoding="utf-8")
    out = tmp_path / "f.json"

    def boom(_path):
        raise SpecSchemaError(["synthetic round-trip failure"])

    monkeypatch.setattr(cli, "load_frozen", boom)
    with pytest.raises(SpecSchemaError):
        cli.freeze(draft, out)
    assert not out.exists()


def test_freeze_removes_the_file_when_the_round_trip_is_unsigned(tmp_path, monkeypatch):
    draft = tmp_path / "d.json"
    draft.write_text(json.dumps(complete_payload()), encoding="utf-8")
    out = tmp_path / "f.json"
    real = cli.load_frozen
    monkeypatch.setattr(cli, "load_frozen", lambda p: dataclasses.replace(real(p), is_signed=False))
    with pytest.raises(RuntimeError):
        cli.freeze(draft, out)
    assert not out.exists()


def test_freeze_failure_cleanup_tolerates_the_file_already_gone(tmp_path, monkeypatch):
    draft = tmp_path / "d.json"
    draft.write_text(json.dumps(complete_payload()), encoding="utf-8")
    out = tmp_path / "f.json"

    def boom(path):
        Path(path).unlink()
        raise SpecSchemaError(["gone"])

    monkeypatch.setattr(cli, "load_frozen", boom)
    with pytest.raises(SpecSchemaError):
        cli.freeze(draft, out)
