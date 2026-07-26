"""The Step 4C harness — the parts provable without AWS.

What is testable here is the harness's *refusals and shapes*: that it will not provision without an
explicit retention decision, that it refuses a non-Linux host before touching anything, that the
synthetic tip cannot be mistaken for a real observation, and that the governed configuration it builds
is the real one rather than a hand-rolled `WitnessConfig`.

The AWS behaviour itself is deliberately NOT stubbed here. Stubbing the very calls Step 4C exists to
prove would be a test that proves the stub — 4A and 4B already cover the adapters against `Stubber`,
and the whole point of 4C is that stubs are not sufficient.
"""

from __future__ import annotations

import json
import os
import platform

import pytest

from app.validation.aws.integration_proof import (
    RETENTION_MODES,
    SYNTHETIC_SESSION,
    ProofError,
    instance_identity,
    main,
    provision,
    synthetic_tip,
    witness_config,
)
from app.validation.aws.platform_guard import PLATFORM_UNSUPPORTED, PlatformUnsupported
from app.validation.witness_config import WitnessConfigError, WitnessProfile

KEY_ARN = "arn:aws:kms:us-east-1:219024422756:key/1a2b3c4d-5e6f-4a1b-8c2d-3e4f5a6b7c8d"
LINUX = platform.system() == "Linux" and os.name == "posix"


# ── the retention decision cannot be made by omission ────────────────────────────────────────────────

@pytest.mark.parametrize("mode", ["", "compliance", "WORM", "NONE", None])
def test_provision_refuses_an_unrecognised_retention_mode(mode):
    with pytest.raises(ProofError) as exc:
        provision(bucket="b", region="us-east-1", retention_mode=mode, retention_days=1,
                  description="d")
    assert exc.value.code == "STEP4C_RETENTION_UNSPECIFIED"


@pytest.mark.parametrize("days", [0, -1, None, "1", 1.5])
def test_provision_refuses_a_missing_or_invalid_retention_period(days):
    with pytest.raises(ProofError) as exc:
        provision(bucket="b", region="us-east-1", retention_mode="COMPLIANCE", retention_days=days,
                  description="d")
    assert exc.value.code == "STEP4C_RETENTION_UNSPECIFIED"


def test_the_cli_makes_retention_a_required_argument(capsys):
    """No default anywhere: argparse must refuse the call, not fill one in."""
    with pytest.raises(SystemExit):
        main(["provision", "--bucket", "b", "--region", "us-east-1", "--out", "x.json"])
    assert "retention" in capsys.readouterr().err.lower()


def test_both_retention_modes_are_offered_and_nothing_else():
    assert RETENTION_MODES == ("COMPLIANCE", "GOVERNANCE")


# ── the platform boundary is checked before anything happens ─────────────────────────────────────────

@pytest.mark.skipif(LINUX, reason="the refusal is asserted on the unsupported platform")
def test_every_subcommand_refuses_on_this_non_linux_host(tmp_path):
    """Not a simulated platform: this really is Windows, and every entry point must stop here.

    If it did not, a run would provision a KMS key and an Object-Locked bucket and only then hit the
    issue-#522 recursion inside botocore — leaving real infrastructure behind, some of it undeletable
    until retention expires.
    """
    invocations = [
        ["provision", "--bucket", "b", "--region", "us-east-1", "--retention-mode", "COMPLIANCE",
         "--retention-days", "1", "--out", str(tmp_path / "o.json")],
        ["install-key", "--key-arn", KEY_ARN, "--path", str(tmp_path / "k.der"),
         "--out", str(tmp_path / "o.json")],
        ["prove", "--key-arn", KEY_ARN, "--bucket", "b", "--prefix", "p", "--region", "us-east-1",
         "--public-key-path", str(tmp_path / "k.der"), "--trusted-root", str(tmp_path),
         "--out", str(tmp_path / "o.json")],
    ]
    for argv in invocations:
        with pytest.raises(PlatformUnsupported) as exc:
            main(argv)
        assert exc.value.code == PLATFORM_UNSUPPORTED
    assert list(tmp_path.iterdir()) == []         # nothing was created before the refusal


# ── the synthetic tip is unmistakably synthetic ──────────────────────────────────────────────────────

def test_the_synthetic_tip_is_deterministic_and_not_a_trading_date():
    tip = synthetic_tip()
    assert tip == synthetic_tip()                 # same bytes on every run
    assert tip.session_date == SYNTHETIC_SESSION == "0001-01-01"
    assert tip.sequence == 1
    assert len(tip.commit_sha256) == 64 and len(tip.anchor_sha256) == 64
    assert tip.commit_sha256 != tip.anchor_sha256


def test_the_synthetic_tip_cannot_collide_with_a_real_session():
    """A reader auditing the witness bucket must be able to tell this apart from an observation."""
    year = int(synthetic_tip().session_date.split("-")[0])
    assert year < 1900


# ── the governed configuration is the real one ───────────────────────────────────────────────────────

def test_the_config_is_production_profile_and_names_the_real_factories(tmp_path):
    config = witness_config(key_arn=KEY_ARN, bucket="anchors", prefix="mr002/x",
                            region="us-east-1", public_key_path=tmp_path / "k.der",
                            trusted_root=tmp_path)
    assert config.profile is WitnessProfile.PRODUCTION
    assert config.key_id == KEY_ARN
    assert config.signer.factory == "app.validation.aws.kms_signer:build_kms_anchor_signer"
    assert config.sink.factory == "app.validation.aws.s3_sink:build_s3_object_lock_sink"
    # The sink's declared identity must equal what the adapter will report, or the gate refuses.
    assert config.sink.identity == "s3://anchors/mr002/x"


def test_the_config_passes_the_witness_identity_the_factory_actually_receives(tmp_path):
    """`_resolve_factory` passes only `options` — a signer identity outside it never arrives."""
    config = witness_config(key_arn=KEY_ARN, bucket="b", prefix="p", region="us-east-1",
                            public_key_path=tmp_path / "k.der", trusted_root=tmp_path)
    assert config.signer.options["witness_identity"] == config.signer.identity
    assert config.signer.options["key_arn"] == KEY_ARN


def test_the_config_carries_no_credentials(tmp_path):
    """Routed through the real loader, so the private-key-material scan runs over it."""
    config = witness_config(key_arn=KEY_ARN, bucket="b", prefix="p", region="us-east-1",
                            public_key_path=tmp_path / "k.der", trusted_root=tmp_path)
    for options in (config.signer.options, config.sink.options):
        assert not any(k.lower() in {"secret", "credentials", "access_key"} for k in options)


def test_a_config_carrying_credentials_would_be_refused(tmp_path):
    """Proves the scan is live on this path, not merely absent by luck."""
    from app.validation.witness_config import load_witness_config

    with pytest.raises(WitnessConfigError) as exc:
        load_witness_config({
            "profile": "PRODUCTION", "algorithm": "ECDSA_SHA_256_P256", "key_id": KEY_ARN,
            "public_key_path": str(tmp_path / "k.der"),
            "signer": {"factory": "app.validation.aws.kms_signer:build_kms_anchor_signer",
                       "identity": "x", "options": {"key_arn": KEY_ARN, "access_key": "AKIA"}},
            "sink": {"factory": "app.validation.aws.s3_sink:build_s3_object_lock_sink",
                     "identity": "s3://b", "options": {}},
        })
    assert exc.value.code == "WITNESS_PRIVATE_KEY_IN_CONFIG"


# ── instance identity is recorded, never required ────────────────────────────────────────────────────

def test_instance_identity_is_empty_off_ec2():
    """No EC2 metadata service here, so it must degrade to {} rather than hang or raise."""
    assert instance_identity() == {}


# ── the evidence bundle ──────────────────────────────────────────────────────────────────────────────

@pytest.mark.skipif(not LINUX, reason="bundle writing is only reached past the platform gate")
def test_the_bundle_is_canonical_json(tmp_path):
    from app.validation.aws.integration_proof import _write_bundle

    path = tmp_path / "nested" / "evidence.json"
    _write_bundle(path, {"b": 2, "a": 1})
    text = path.read_text(encoding="utf-8")
    assert json.loads(text) == {"a": 1, "b": 2}
    assert text.index('"a"') < text.index('"b"')  # sorted, so two bundles diff meaningfully
