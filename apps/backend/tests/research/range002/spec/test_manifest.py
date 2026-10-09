"""Round 5 N-A (spec side): the owner-approved governance manifest and the freeze gate on it.

Synthetic manifests only. The COMMITTED manifest must stay UNSET until the owner approves it
through a reviewed git change; ``test_committed_manifest_*`` is the CI-checkable consistency test.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.research.range002.spec.hashing import CanonicalisationError, loads_strict
from app.research.range002.spec.manifest import (
    DEFAULT_MANIFEST_PATH,
    MANIFEST_RELPATH,
    ManifestGenesisMismatchError,
    ManifestInvalidError,
    ManifestLimitMismatchError,
    ManifestMissingError,
    ManifestNotApprovedError,
    load_manifest,
    parse_manifest,
)

from ._fixtures import (
    OTHER_GENESIS_ID,
    SYNTH_GENESIS_ID,
    complete_payload,
    make_symlink,
    set_path,
    synthetic_manifest_payload,
    write_manifest,
)
from .test_freeze import raw_cli


def _draft(tmp_path: Path, payload: dict) -> Path:
    p = tmp_path / "draft.json"
    p.write_text(json.dumps(payload), encoding="utf-8")
    return p


def _freeze_rc(tmp_path, manifest: Path | None, payload=None):
    out = tmp_path / "frozen.json"
    rc = raw_cli.main(
        [str(_draft(tmp_path, payload or complete_payload())), "--out", str(out)],
        manifest_path=manifest,
    )
    return rc, out


# ---- committed manifest ---------------------------------------------------------------------


def test_committed_manifest_exists_parses_and_state_is_consistent():
    assert DEFAULT_MANIFEST_PATH.name == "RANGE-002_governance_manifest.json"
    assert DEFAULT_MANIFEST_PATH.as_posix().endswith(MANIFEST_RELPATH)
    assert DEFAULT_MANIFEST_PATH.is_file(), "committed governance manifest is missing"
    assert b"\r" not in DEFAULT_MANIFEST_PATH.read_bytes()
    m = load_manifest()  # strict JSON + exact-key schema + all-or-nothing approval consistency
    assert len(m.sha256) == 64
    if m.is_genesis_approved:
        assert m.approved_registry_genesis_id and m.approved_by and m.approved_on
    else:
        assert m.approved_registry_genesis_id is None
        assert m.approved_by is None and m.approved_on is None
        with pytest.raises(ManifestNotApprovedError):
            m.require_genesis()


def test_committed_manifest_is_unset_until_owner_approves():
    """Pins the shipped state: a session must not approve a genesis or invent limits. When the
    owner approves, this test is updated in the same reviewed change."""
    m = load_manifest()
    assert m.approved_registry_genesis_id is None
    assert (m.max_p3a_attempts, m.max_p3b_attempts) == (None, None)


# ---- parsing --------------------------------------------------------------------------------


def test_loader_reads_the_fixed_path_by_default(monkeypatch, tmp_path):
    import app.research.range002.spec.manifest as mod

    monkeypatch.setattr(mod, "DEFAULT_MANIFEST_PATH", write_manifest(tmp_path / "m.json"))
    assert load_manifest().approved_registry_genesis_id == SYNTH_GENESIS_ID


def test_manifest_hash_ignores_key_order_and_whitespace(tmp_path):
    a = write_manifest(tmp_path / "a.json")
    payload = synthetic_manifest_payload()
    b = tmp_path / "b.json"
    b.write_text(json.dumps(dict(reversed(list(payload.items()))), indent=4), encoding="utf-8")
    ma, mb = load_manifest(a), load_manifest(b)
    assert ma.sha256 == mb.sha256 and ma.max_p3a_attempts == 9
    changed = write_manifest(
        tmp_path / "c.json", synthetic_manifest_payload(p3_attempt_limits={"p3a": 1, "p3b": 8})
    )
    assert load_manifest(changed).sha256 != ma.sha256


@pytest.mark.parametrize(
    "bad",
    [
        {"approved_registry_genesis_id": "ABC"},
        {"approved_registry_genesis_id": "ab" * 16},  # legacy 32-hex shape
        {"approved_registry_genesis_id": SYNTH_GENESIS_ID.upper()},
        {"approved_registry_genesis_id": SYNTH_GENESIS_ID.replace("-", "")},
        {"approved_registry_genesis_id": "5eed5eed-5eed-1eed-9eed-5eed5eed5eed"},  # not v4
        {"approved_registry_genesis_id": 7},
        {"approved_by": "  "},
        {"approved_by": None},  # genesis set but no approver: half-approved
        {"approved_on": None},
        {"approved_on": "2999-01-01"},  # future
        {"approved_on": "not-a-date"},
        {"approved_on": 20000101},
        {"schema_version": 2},
        {"schema_version": True},
        {"p3_attempt_limits": {"p3a": 0, "p3b": 8}},
        {"p3_attempt_limits": {"p3a": True, "p3b": 8}},
        {"p3_attempt_limits": {"p3a": 2.0, "p3b": 8}},
        {"p3_attempt_limits": {"p3a": "3", "p3b": 8}},
        {"p3_attempt_limits": {"p3a": 3}},
        {"p3_attempt_limits": {"p3a": 3, "p3b": 3, "p3c": 3}},
        {"p3_attempt_limits": [3, 3]},
        {"notes": None},
        {"surprise": 1},
    ],
)
def test_invalid_manifests_refused(tmp_path, bad):
    with pytest.raises(ManifestInvalidError):
        load_manifest(write_manifest(tmp_path / "m.json", synthetic_manifest_payload(**bad)))


def test_half_approved_other_direction_refused(tmp_path):
    payload = synthetic_manifest_payload(approved_registry_genesis_id=None)
    with pytest.raises(ManifestInvalidError, match="all null"):
        load_manifest(write_manifest(tmp_path / "m.json", payload))


def test_missing_key_and_non_object_refused(tmp_path):
    payload = synthetic_manifest_payload()
    del payload["notes"]
    with pytest.raises(ManifestInvalidError, match="missing"):
        load_manifest(write_manifest(tmp_path / "m.json", payload))
    with pytest.raises(ManifestInvalidError):
        parse_manifest([1])


def test_missing_oversize_and_directory_refused(tmp_path):
    with pytest.raises(ManifestMissingError):
        load_manifest(tmp_path / "nope.json")
    with pytest.raises(ManifestMissingError):
        load_manifest(tmp_path)  # a directory
    big = tmp_path / "big.json"
    big.write_text(" " * (70 * 1024) + "{}", encoding="utf-8")
    with pytest.raises(ManifestMissingError, match="exceeds"):
        load_manifest(big)


def test_symlinked_manifest_refused(tmp_path):
    real = write_manifest(tmp_path / "real.json")
    link = tmp_path / "link.json"
    make_symlink(link, real)
    with pytest.raises(ManifestMissingError):
        load_manifest(link)


def test_unreadable_manifest_is_a_named_refusal(tmp_path, monkeypatch):
    real = write_manifest(tmp_path / "real.json")

    def boom(self):
        raise OSError("denied")

    monkeypatch.setattr(Path, "read_bytes", boom)
    with pytest.raises(ManifestMissingError, match="unreadable"):
        load_manifest(real)


def test_symlink_branch_without_real_symlinks(tmp_path, monkeypatch):
    real = write_manifest(tmp_path / "real.json")
    monkeypatch.setattr(Path, "is_symlink", lambda self: self == real)
    with pytest.raises(ManifestMissingError):
        load_manifest(real)


@pytest.mark.parametrize(
    "raw",
    [
        b"{not json",
        b'{"schema_version": 1, "schema_version": 1}',  # duplicate key
        b'{"schema_version": NaN}',
        b'{"schema_version": 1e999}',
        b"",
        b"\xff\xfe",
    ],
)
def test_non_strict_json_refused(tmp_path, raw):
    p = tmp_path / "m.json"
    p.write_bytes(raw)
    with pytest.raises(ManifestInvalidError):
        load_manifest(p)


def test_unset_manifest_loads_but_every_require_refuses(tmp_path):
    payload = synthetic_manifest_payload(
        approved_registry_genesis_id=None,
        approved_by=None,
        approved_on=None,
        p3_attempt_limits={"p3a": None, "p3b": None},
    )
    m = load_manifest(write_manifest(tmp_path / "m.json", payload))
    with pytest.raises(ManifestNotApprovedError):
        m.require_genesis()
    with pytest.raises(ManifestNotApprovedError):
        m.require_limits()
    with pytest.raises(ManifestNotApprovedError):
        m.check_genesis(SYNTH_GENESIS_ID, what="spec")  # null never matches anything
    with pytest.raises(ManifestNotApprovedError):
        m.check_genesis(None, what="spec")  # null == null must NOT pass
    with pytest.raises(ManifestNotApprovedError):
        m.check_limits(None, None)


def test_check_helpers_name_the_mismatch(tmp_path):
    m = load_manifest(write_manifest(tmp_path / "m.json"))
    m.check_genesis(SYNTH_GENESIS_ID, what="spec")
    m.check_limits(9, 8)
    with pytest.raises(ManifestGenesisMismatchError):
        m.check_genesis("ab" * 16, what="registry")
    with pytest.raises(ManifestGenesisMismatchError):
        m.check_genesis(None, what="registry")
    with pytest.raises(ManifestLimitMismatchError):
        m.check_limits(10, 8)
    with pytest.raises(ManifestLimitMismatchError):
        m.check_limits(9, None)


# ---- freeze_spec gate -----------------------------------------------------------------------


def test_freeze_refuses_when_manifest_missing(tmp_path, capsys):
    rc, out = _freeze_rc(tmp_path, tmp_path / "absent.json")
    assert rc == 2 and not out.exists()
    assert "manifest" in capsys.readouterr().err


def test_freeze_refuses_with_the_committed_unset_manifest(tmp_path, capsys):
    """The default (production) path is the committed, UNSET manifest: freezing must refuse."""
    rc, out = _freeze_rc(tmp_path, None)
    assert rc == 2 and not out.exists()
    assert "no owner-approved registry genesis" in capsys.readouterr().err


def test_freeze_refuses_unapproved_genesis_and_null_limits(tmp_path):
    for i, payload in enumerate(
        [
            synthetic_manifest_payload(
                approved_registry_genesis_id=None, approved_by=None, approved_on=None
            ),
            synthetic_manifest_payload(p3_attempt_limits={"p3a": None, "p3b": 8}),
            synthetic_manifest_payload(p3_attempt_limits={"p3a": 9, "p3b": None}),
        ]
    ):
        d = tmp_path / str(i)
        d.mkdir()
        rc, out = _freeze_rc(d, write_manifest(d / "m.json", payload))
        assert rc == 2 and not out.exists()


def test_freeze_refuses_spec_genesis_differing_from_manifest(tmp_path, capsys):
    payload = complete_payload()
    set_path(payload, "governance.registry_genesis_id", OTHER_GENESIS_ID)
    rc, out = _freeze_rc(tmp_path, write_manifest(tmp_path / "m.json"), payload)
    assert rc == 2 and not out.exists()
    assert "owner-approved manifest genesis" in capsys.readouterr().err


@pytest.mark.parametrize("which", ["max_p3a_attempts", "max_p3b_attempts"])
def test_freeze_refuses_spec_limits_differing_from_manifest(tmp_path, capsys, which):
    payload = complete_payload()
    set_path(payload, f"p3.{which}", 99)
    rc, out = _freeze_rc(tmp_path, write_manifest(tmp_path / "m.json"), payload)
    assert rc == 2 and not out.exists()
    assert "pre-registered" in capsys.readouterr().err


def test_freeze_succeeds_with_matching_manifest(tmp_path):
    rc, out = _freeze_rc(tmp_path, write_manifest(tmp_path / "m.json"))
    assert rc == 0 and out.exists()


def test_manifest_gate_runs_before_any_write(tmp_path):
    rc, out = _freeze_rc(tmp_path, tmp_path / "absent.json")
    assert rc == 2 and not out.exists()


def test_cli_has_no_manifest_path_argument(capsys):
    """Production callers cannot point the freeze tool at a different manifest."""
    with pytest.raises(SystemExit):
        raw_cli.main(["--manifest", "x.json"])
    assert "unrecognized arguments" in capsys.readouterr().err


def test_new_genesis_id_is_canonical_uuid4_and_unique():
    from app.research.range002.spec.genesis import is_canonical_uuid4, new_genesis_id

    ids = {new_genesis_id() for _ in range(50)}
    assert len(ids) == 50 and all(is_canonical_uuid4(i) for i in ids)
    assert not is_canonical_uuid4(None) and not is_canonical_uuid4(b"x")


# ---- loads_strict overflow (reviewer Info) -------------------------------------------------


@pytest.mark.parametrize("text", ["1e999", "-1e999", '{"a": 1e999}', "[1e400]", '{"a": -1E999}'])
def test_loads_strict_refuses_float_overflow_to_infinity(text):
    with pytest.raises(CanonicalisationError, match="non-finite"):
        loads_strict(text)


def test_loads_strict_still_accepts_ordinary_floats():
    assert loads_strict("[1.5, 1e3, 0.0, -2.5e-3]") == [1.5, 1000.0, 0.0, -0.0025]
