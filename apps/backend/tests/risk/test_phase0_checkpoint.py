"""WP3 AMD-07 — checkpoint integrity (hermetic; no broker)."""

from __future__ import annotations

import json
from pathlib import Path

from app.risk.loss_control.phase0_checkpoint import (
    REQUIRED_BINDING_FIELDS,
    CheckpointBinding,
    CheckpointRefuseReason,
    assert_no_order_path_imports,
    load_sealed_checkpoint,
    seal_checkpoint,
    verify_checkpoint_envelope,
    write_sealed_checkpoint,
)


def _binding(**over) -> CheckpointBinding:
    base = dict(
        run_id="20260729120000",
        session_id="sess-A",
        account_id=3,
        plan_hash="sha256:plan",
        authorization_id="auth-1",
        loss_control_state="NORMAL",
        loss_control_state_version=4,
        payload={"steps": {"A1": {"done": True}}},
    )
    base.update(over)
    return CheckpointBinding(**base)  # type: ignore[arg-type]


def test_binding_tuple_requires_loss_control_state_version() -> None:
    assert "loss_control_state_version" in REQUIRED_BINDING_FIELDS


def test_seal_and_verify_roundtrip() -> None:
    env = seal_checkpoint(_binding())
    assert env["content_hash"].startswith("sha256:")
    assert "hmac_sha256" not in env
    result = verify_checkpoint_envelope(env)
    assert result.accepted and result.binding is not None
    assert result.binding.loss_control_state_version == 4


def test_hmac_seal_requires_matching_key() -> None:
    key = b"phase0-test-key"
    env = seal_checkpoint(_binding(), hmac_key=key)
    assert env["hmac_sha256"].startswith("hmac-sha256:")
    assert verify_checkpoint_envelope(env, hmac_key=key).accepted
    bad = verify_checkpoint_envelope(env, hmac_key=b"other-key")
    assert not bad.accepted
    assert bad.reason is CheckpointRefuseReason.HMAC_MISMATCH


def test_require_hmac_without_mac_refuses() -> None:
    env = seal_checkpoint(_binding())
    r = verify_checkpoint_envelope(env, require_hmac=True, hmac_key=b"k")
    assert not r.accepted
    assert r.reason is CheckpointRefuseReason.HMAC_REQUIRED


def test_missing_state_version_refused() -> None:
    env = seal_checkpoint(_binding())
    del env["loss_control_state_version"]
    # also drop hash so we exercise binding check first after recompute path —
    # strip hash and leave incomplete binding
    env.pop("content_hash", None)
    r = verify_checkpoint_envelope(env)
    assert not r.accepted
    assert r.reason is CheckpointRefuseReason.MISSING_STATE_VERSION


def test_missing_content_hash_refused() -> None:
    env = seal_checkpoint(_binding())
    del env["content_hash"]
    r = verify_checkpoint_envelope(env)
    assert not r.accepted
    assert r.reason is CheckpointRefuseReason.MISSING_CONTENT_HASH


def test_tampered_contents_valid_filename_refused(tmp_path: Path) -> None:
    """AMD-07 regression: tampered contents, valid filename → refused."""
    path = tmp_path / "adr0043_checkpoint.json"
    write_sealed_checkpoint(path, _binding())
    assert path.name == "adr0043_checkpoint.json"

    blob = json.loads(path.read_text(encoding="utf-8"))
    blob["payload"] = {"steps": {"A1": {"done": True}, "injected": True}}
    path.write_text(json.dumps(blob, indent=2), encoding="utf-8")

    r = load_sealed_checkpoint(path)
    assert not r.accepted
    assert r.reason is CheckpointRefuseReason.TAMPERED_CONTENTS


def test_tampered_state_version_refused(tmp_path: Path) -> None:
    path = tmp_path / "adr0043_checkpoint.json"
    write_sealed_checkpoint(path, _binding(loss_control_state_version=4))
    blob = json.loads(path.read_text(encoding="utf-8"))
    blob["loss_control_state_version"] = 99
    path.write_text(json.dumps(blob), encoding="utf-8")
    r = load_sealed_checkpoint(path)
    assert not r.accepted
    assert r.reason is CheckpointRefuseReason.TAMPERED_CONTENTS


def test_corrupted_json_refused(tmp_path: Path) -> None:
    path = tmp_path / "adr0043_checkpoint.json"
    path.write_text("{not-json", encoding="utf-8")
    r = load_sealed_checkpoint(path)
    assert not r.accepted
    assert r.reason is CheckpointRefuseReason.CORRUPTED_JSON


def test_cross_session_reuse_refused() -> None:
    env = seal_checkpoint(_binding(session_id="sess-A"))
    r = verify_checkpoint_envelope(env, expected_session_id="sess-B")
    assert not r.accepted
    assert r.reason is CheckpointRefuseReason.CROSS_SESSION_REUSE


def test_same_session_accepted() -> None:
    env = seal_checkpoint(_binding(session_id="sess-A"))
    assert verify_checkpoint_envelope(env, expected_session_id="sess-A").accepted


def test_no_order_path_imports() -> None:
    assert_no_order_path_imports()
