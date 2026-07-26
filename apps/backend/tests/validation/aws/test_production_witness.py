"""The Step 4D harness — the parts provable without AWS.

Same discipline as the Step 4C tests: what is testable here is the harness's *refusals and shapes*.
Stubbing the calls Step 4D exists to prove would be a test that proves the stub — 4A and 4B already
cover the adapters against `Stubber`, and 4C established that stubs are not sufficient for the
questions a deployment asks.

The load-bearing test in this file is the operational-prefix refusal. Under ADR 0047 the witness bucket
is COMPLIANCE-locked for 2555 days, so a synthetic receipt published to `witness/` would be a permanent
sequence-1 record in the production chain with no remedy of any kind. That is the one mistake this
harness must be structurally incapable of making.
"""

from __future__ import annotations

import json
import os
import platform
from pathlib import Path

import pytest

from app.validation.aws.production_witness import (
    OPERATIONAL_PREFIX,
    PREFLIGHT_PREFIX,
    REQUIRED_LOCK_MODE,
    REQUIRED_RETENTION_DAYS,
    SYNTHETIC_SESSION,
    PreflightError,
    _case,
    _with_endpoint,
    _write_bundle,
    main,
    run_preflight,
    synthetic_tip,
    witness_config,
)
from app.validation.witness_config import WitnessProfile
from app.validation.witness_platform import PLATFORM_UNSUPPORTED, PlatformUnsupported
from app.validation.witness_protocol import ALGORITHM_ECDSA_SHA256_P256

KEY_ARN = "arn:aws:kms:us-east-1:219024422756:key/1a2b3c4d-5e6f-4a1b-8c2d-3e4f5a6b7c8d"
BUCKET = "workbench-witness-forward-validation-219024422756"
LINUX = platform.system() == "Linux" and os.name == "posix"


# ── the operational prefix is unreachable from here ──────────────────────────────────────────────────

@pytest.mark.parametrize("prefix", [OPERATIONAL_PREFIX, f"/{OPERATIONAL_PREFIX}",
                                    f"{OPERATIONAL_PREFIX}/", f"/{OPERATIONAL_PREFIX}/"])
def test_preflight_refuses_to_publish_synthetic_evidence_to_the_operational_prefix(prefix, tmp_path):
    """The refusal fires BEFORE any AWS client is constructed, which is why this test needs no stub.

    Slash variants are parametrized because the sink canonicalizes prefixes by stripping separators —
    a guard comparing raw strings would let `witness/` through and poison the chain irreversibly.
    """
    with pytest.raises(PreflightError) as exc:
        run_preflight(key_arn=KEY_ARN, bucket=BUCKET, region="us-east-1",
                      public_key_path=tmp_path / "witness.pub", trusted_root=tmp_path,
                      prefix=prefix)
    assert exc.value.code == "WITNESS_SINK_STORAGE_MISBOUND"
    assert "COMPLIANCE" in str(exc.value) or "could never be removed" in str(exc.value)


def test_the_default_prefix_is_the_preflight_one_and_they_are_distinct():
    assert PREFLIGHT_PREFIX != OPERATIONAL_PREFIX
    assert PREFLIGHT_PREFIX == "preflight" and OPERATIONAL_PREFIX == "witness"


# ── the synthetic tip cannot be mistaken for an observation ──────────────────────────────────────────

def test_the_synthetic_tip_is_self_evidently_not_a_trading_session():
    tip = synthetic_tip()
    assert tip.session_date == SYNTHETIC_SESSION == "0001-01-01"
    assert tip.commit_sha256 != tip.anchor_sha256
    assert len(tip.commit_sha256) == 64 and len(tip.anchor_sha256) == 64


def test_the_synthetic_tip_is_deterministic():
    """It must be, or the idempotency case could never republish stored bytes across invocations."""
    assert synthetic_tip().commit_sha256 == synthetic_tip().commit_sha256


def test_the_step_4d_marker_differs_from_the_step_4c_one():
    """Two steps' synthetic receipts must not collide if they ever share a bucket."""
    from app.validation.aws.integration_proof import synthetic_tip as step4c_tip

    assert synthetic_tip().commit_sha256 != step4c_tip().commit_sha256


# ── the governed configuration is the real one ───────────────────────────────────────────────────────

def test_the_config_goes_through_the_real_loader(tmp_path):
    config = witness_config(key_arn=KEY_ARN, bucket=BUCKET, prefix=PREFLIGHT_PREFIX,
                            region="us-east-1", public_key_path=tmp_path / "witness.pub",
                            trusted_root=tmp_path)
    assert config.profile is WitnessProfile.PRODUCTION
    assert config.algorithm == ALGORITHM_ECDSA_SHA256_P256
    assert config.key_id == KEY_ARN
    assert config.sink.identity == f"s3://{BUCKET}/{PREFLIGHT_PREFIX}"
    assert config.signer.factory == "app.validation.aws.kms_signer:build_kms_anchor_signer"


def test_the_config_carries_no_credential_material(tmp_path):
    """`load_witness_config` refuses key material by name and value; this pins that the harness does
    not hand it any to refuse."""
    config = witness_config(key_arn=KEY_ARN, bucket=BUCKET, prefix=PREFLIGHT_PREFIX,
                            region="us-east-1", public_key_path=tmp_path / "witness.pub",
                            trusted_root=tmp_path)
    blob = json.dumps({"signer": config.signer.options, "sink": config.sink.options}).lower()
    for forbidden in ("access_key", "secret", "credential", "token", "password"):
        assert forbidden not in blob


# ── the ratified storage policy is exact ─────────────────────────────────────────────────────────────

def test_the_governed_retention_matches_what_adr_0047_ratified():
    """A drifted constant here would make the preflight pass against a bucket nobody approved."""
    assert REQUIRED_LOCK_MODE == "COMPLIANCE"
    assert REQUIRED_RETENTION_DAYS == 2555


# ── the platform boundary is checked before anything happens ─────────────────────────────────────────

@pytest.mark.skipif(LINUX, reason="the refusal is asserted on the unsupported platform")
@pytest.mark.parametrize("command", ["attest", "install-key", "preflight", "negatives"])
def test_every_subcommand_refuses_on_this_non_linux_host(command, tmp_path):
    """No monkeypatching: the developer's Windows box is actually refused, before any client exists."""
    argv = {
        "attest": ["attest", "--key-arn", KEY_ARN, "--bucket", BUCKET, "--region", "us-east-1"],
        "install-key": ["install-key", "--key-arn", KEY_ARN, "--path", str(tmp_path / "k.der")],
        "preflight": ["preflight", "--key-arn", KEY_ARN, "--bucket", BUCKET, "--region", "us-east-1",
                      "--public-key-path", str(tmp_path / "k.der"), "--trusted-root", str(tmp_path)],
        "negatives": ["negatives", "--key-arn", KEY_ARN, "--bucket", BUCKET, "--region", "us-east-1",
                      "--public-key-path", str(tmp_path / "k.der"), "--trusted-root", str(tmp_path)],
    }[command] + ["--out", str(tmp_path / "out.json")]

    with pytest.raises(PlatformUnsupported) as exc:
        main(argv)
    assert exc.value.code == PLATFORM_UNSUPPORTED
    assert not (tmp_path / "out.json").exists(), "the refusal must precede any output"


# ── the negative-case recorder ───────────────────────────────────────────────────────────────────────

def test_an_operation_that_is_not_refused_is_recorded_as_a_failure():
    """The battery's whole value is that it records what happened, not what was hoped."""
    outcome = _case("N-example", "SOME_CODE", lambda: None)
    assert outcome["refused"] is False and outcome["matched"] is False
    assert outcome["observed_code"] is None


def test_a_refusal_with_the_wrong_code_is_recorded_refused_but_unmatched():
    from app.validation.witness_protocol import WitnessError

    def _raise():
        raise WitnessError("nope", code="A_DIFFERENT_CODE")

    outcome = _case("N-example", "EXPECTED_CODE", _raise)
    assert outcome["refused"] is True and outcome["matched"] is False
    assert outcome["observed_code"] == "A_DIFFERENT_CODE"


def test_an_untyped_failure_is_still_recorded_as_evidence():
    def _raise():
        raise ZeroDivisionError("boom")

    outcome = _case("N-example", "EXPECTED_CODE", _raise)
    assert outcome["refused"] is True and outcome["observed_code"] == "ZeroDivisionError"


# ── the endpoint override must not leak ──────────────────────────────────────────────────────────────

def test_the_endpoint_override_is_restored_even_when_the_call_raises(monkeypatch):
    """A leaked override would silently invalidate every case after it, and the battery would report
    refusals it did not earn."""
    monkeypatch.delenv("AWS_ENDPOINT_URL_KMS", raising=False)

    def _boom():
        assert os.environ["AWS_ENDPOINT_URL_KMS"] == "https://127.0.0.1:1"
        raise RuntimeError("as expected")

    with pytest.raises(RuntimeError):
        _with_endpoint("KMS", "https://127.0.0.1:1", _boom)
    assert "AWS_ENDPOINT_URL_KMS" not in os.environ


def test_the_endpoint_override_restores_a_pre_existing_value(monkeypatch):
    monkeypatch.setenv("AWS_ENDPOINT_URL_S3", "https://example.invalid")
    _with_endpoint("S3", "https://127.0.0.1:1", lambda: None)
    assert os.environ["AWS_ENDPOINT_URL_S3"] == "https://example.invalid"


# ── the bundle is hashed over the bytes actually written ─────────────────────────────────────────────

def test_the_bundle_digest_covers_the_exact_bytes_on_disk(tmp_path):
    import hashlib

    out = tmp_path / "evidence.json"
    digest = _write_bundle(out, {"step": "4D", "outcome": "PASS"})
    assert digest == hashlib.sha256(out.read_bytes()).hexdigest()

    sidecar = Path(str(out) + ".sha256")
    assert sidecar.exists() and digest in sidecar.read_text()


def test_the_bundle_is_canonically_ordered_so_two_runs_diff_meaningfully(tmp_path):
    a = _write_bundle(tmp_path / "a.json", {"b": 1, "a": 2})
    b = _write_bundle(tmp_path / "b.json", {"a": 2, "b": 1})
    assert a == b


# ── the harness provisions nothing ───────────────────────────────────────────────────────────────────

def test_the_harness_cannot_provision():
    """ADR 0047 (4) keeps the witness contract at eight actions. A create call here would need a ninth,
    and the role would then be able to make the resources whose properties it is meant to attest."""
    source = Path(__file__).resolve().parents[3] / "app" / "validation" / "aws" / "production_witness.py"
    text = source.read_text(encoding="utf-8")
    for forbidden in ("create_key(", "create_bucket(", "delete_object(", "delete_bucket(",
                      "put_object_lock_configuration(", "put_bucket_versioning(",
                      "schedule_key_deletion("):
        assert forbidden not in text, f"the 4D harness must not call {forbidden}"
