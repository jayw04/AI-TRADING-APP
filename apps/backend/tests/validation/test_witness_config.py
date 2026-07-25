"""The governed witness declaration (R5e).

What these defend: the deployment — not the caller — says what the anchor trust boundary is, the
declaration is complete enough to attribute, and it never hands the runner a key it can sign with.
"""

from __future__ import annotations

import base64

import pytest

from app.validation.witness_config import (
    WitnessConfigError,
    WitnessProfile,
    assert_no_private_key_material,
    load_witness_config,
)

GOOD = {
    "profile": "PRODUCTION",
    "public_key_path": "/etc/workbench/anchor_witness.pub",
    "signer": {"factory": "deployment.witness:build_signer", "identity": "kms://anchor-witness",
               "options": {"key_arn": "arn:aws:kms:us-east-1:1:key/abc", "region": "us-east-1"}},
    "sink": {"factory": "deployment.witness:build_sink", "identity": "s3://anchors/prod",
             "options": {"bucket": "anchors", "prefix": "prod"}},
}


def _without(block: dict, *path: str) -> dict:
    out = {k: (dict(v) if isinstance(v, dict) else v) for k, v in block.items()}
    cursor = out
    for key in path[:-1]:
        cursor = cursor[key]
    cursor.pop(path[-1], None)
    return out


# ---- the block is required and must be complete -----------------------------------------------------

def test_a_complete_declaration_parses():
    config = load_witness_config(GOOD)
    assert config.profile is WitnessProfile.PRODUCTION
    assert config.signer.factory == "deployment.witness:build_signer"
    assert config.sink.identity == "s3://anchors/prod"
    assert str(config.public_key_path).endswith("anchor_witness.pub")


@pytest.mark.parametrize("absent", [None, ""])
def test_a_deployment_without_a_witness_block_cannot_run(absent):
    with pytest.raises(WitnessConfigError, match="cannot independently witness") as exc:
        load_witness_config(absent)
    assert exc.value.code == "WITNESS_CONFIG_INCOMPLETE"


def test_the_block_must_be_an_object():
    with pytest.raises(WitnessConfigError, match="must be an object"):
        load_witness_config("PRODUCTION")


@pytest.mark.parametrize("path", [("signer",), ("sink",)])
def test_each_component_is_required(path):
    with pytest.raises(WitnessConfigError, match=f"witness.{path[0]} must be an object"):
        load_witness_config(_without(GOOD, *path))


@pytest.mark.parametrize("component", ["signer", "sink"])
@pytest.mark.parametrize("field", ["factory", "identity"])
def test_each_component_must_name_itself(component, field):
    """An unnamed component cannot be attributed in the record."""
    with pytest.raises(WitnessConfigError, match="must declare both"):
        load_witness_config(_without(GOOD, component, field))


def test_a_factory_must_be_a_module_callable_reference():
    bad = {**GOOD, "signer": {**GOOD["signer"], "factory": "not-a-reference"}}
    with pytest.raises(WitnessConfigError, match="module:callable"):
        load_witness_config(bad)


def test_component_options_must_be_an_object():
    bad = {**GOOD, "sink": {**GOOD["sink"], "options": ["bucket"]}}
    with pytest.raises(WitnessConfigError, match="options must be an object"):
        load_witness_config(bad)


def test_an_unknown_profile_is_refused():
    with pytest.raises(WitnessConfigError, match="unknown witness.profile"):
        load_witness_config({**GOOD, "profile": "TRUSTED"})


def test_the_reference_profile_parses_so_the_gate_can_name_it():
    """REFERENCE is a legitimate development declaration; refusing it is the ENFORCEMENT gate's job, and
    it can only name what the deployment declared if parsing succeeds first."""
    assert load_witness_config({**GOOD, "profile": "REFERENCE"}).profile is WitnessProfile.REFERENCE


# ---- the verifying key is the deployment's, not the signer's ----------------------------------------

def test_the_verifying_key_path_is_required():
    with pytest.raises(WitnessConfigError, match="public_key_path is required") as exc:
        load_witness_config(_without(GOOD, "public_key_path"))
    assert exc.value.code == "WITNESS_CONFIG_INCOMPLETE"


def test_the_reason_the_key_is_configured_separately_is_recorded():
    """The refusal explains the circularity it prevents — a substituted signer supplying its own key."""
    with pytest.raises(WitnessConfigError, match="obtained from the signer"):
        load_witness_config(_without(GOOD, "public_key_path"))


# ---- no signing material reaches the runner ---------------------------------------------------------

@pytest.mark.parametrize("name", [
    "private_key", "signer_private_key", "passphrase", "password", "seed",
    "secret_key", "secret_access_key", "secretAccessKey", "key_material", "PRIVATE_KEY",
])
def test_a_configuration_naming_signing_material_is_refused(name):
    bad = {**GOOD, "signer": {**GOOD["signer"], "options": {name: "whatever"}}}
    with pytest.raises(WitnessConfigError, match="private signing material") as exc:
        load_witness_config(bad)
    assert exc.value.code == "WITNESS_PRIVATE_KEY_IN_CONFIG"


@pytest.mark.parametrize("name", [
    "secret", "secrets", "access_key", "credential", "credentials", "private_bytes", "signing_key",
    "key_bytes", "d", "p", "q", "dp", "dq", "qi", "k",
])
def test_fields_that_ARE_the_material_are_refused_by_exact_name(name):
    """JWK private components and the bare secret names. `secret_arn` and `credentials_profile` stay
    configurable because they name where custody lives — see the test below."""
    bad = {**GOOD, "sink": {**GOOD["sink"], "options": {name: "x"}}}
    with pytest.raises(WitnessConfigError, match="names private signing material") as exc:
        load_witness_config(bad)
    assert exc.value.code == "WITNESS_PRIVATE_KEY_IN_CONFIG"


# ---- raw key material under an innocuous field name (the check that closes the name-only gap) --------

def _seed_forms():
    seed = bytes(range(32))
    return {
        "base64 ed25519 seed": base64.b64encode(seed).decode("ascii"),
        "urlsafe base64 seed": base64.urlsafe_b64encode(seed).decode("ascii").rstrip("="),
        "64-char hex seed": seed.hex(),
        "uppercase hex seed": seed.hex().upper(),
        "hex with whitespace": " ".join(seed.hex()[i:i + 8] for i in range(0, 64, 8)),
        "64-byte hex material": (seed + seed).hex(),
        "48-byte base64 material": base64.b64encode(seed + seed[:16]).decode("ascii"),
    }


@pytest.mark.parametrize("label,value", sorted(_seed_forms().items()))
@pytest.mark.parametrize("field", ["credential_blob", "blob", "material", "handle", "opaque"])
def test_raw_key_material_under_an_innocuous_name_is_refused(label, value, field):
    """A base64 Ed25519 seed under `credential_blob` carries exactly as much signing power as one under
    `private_key`. Name-based detection alone is not a control."""
    bad = {**GOOD, "signer": {**GOOD["signer"], "options": {field: value}}}
    with pytest.raises(WitnessConfigError, match="key material") as exc:
        load_witness_config(bad)
    assert exc.value.code == "WITNESS_PRIVATE_KEY_IN_CONFIG"
    assert label                                   # the parametrisation names the encoding under test


def test_key_material_is_refused_before_any_factory_is_imported(monkeypatch):
    """The refusal must precede import: a factory that is reached has already been handed the value."""
    import importlib

    def forbidden(*a, **k):                        # pragma: no cover - must never be reached
        raise AssertionError("a factory was imported despite key material in the configuration")

    monkeypatch.setattr(importlib, "import_module", forbidden)
    bad = {**GOOD, "signer": {**GOOD["signer"],
                              "options": {"credential_blob": base64.b64encode(bytes(32)).decode()}}}
    with pytest.raises(WitnessConfigError, match="key material"):
        load_witness_config(bad)


def test_a_byte_array_of_a_private_key_length_is_refused():
    bad = {**GOOD, "signer": {**GOOD["signer"], "options": {"octets": list(range(32))}}}
    with pytest.raises(WitnessConfigError, match="32-byte array of key material"):
        load_witness_config(bad)


@pytest.mark.parametrize("value", [
    "arn:aws:kms:us-east-1:123456789012:key/1234abcd-12ab-34cd-56ef-1234567890ab",
    "s3://workbench-anchors/prod",
    "https://signer.internal:8443/sign",
    "us-east-1", "anchors", "prod/witness", "svc-1",
])
def test_ordinary_configuration_values_are_not_mistaken_for_key_material(value):
    """The check must leave the production shape configurable: ARNs, URIs, regions, buckets, handles."""
    assert_no_private_key_material({"endpoint": value})


@pytest.mark.parametrize("name", ["image_digest", "artifact_sha256", "bundle_checksum", "etag"])
def test_a_content_address_named_as_one_is_still_configurable(name):
    """64 hex characters are legitimately a digest. The narrow escape is by field name, and it is only
    an escape for the hex lengths a content address takes."""
    assert_no_private_key_material({name: "a" * 64})


def test_the_digest_escape_does_not_extend_to_base64_material():
    with pytest.raises(WitnessConfigError, match="key material"):
        assert_no_private_key_material({"image_digest": base64.b64encode(bytes(range(32))).decode()})


def test_key_material_nested_anywhere_in_the_block_is_found():
    seed = base64.b64encode(bytes(range(32))).decode("ascii")
    with pytest.raises(WitnessConfigError, match="key material"):
        assert_no_private_key_material({"sink": {"options": {"pool": [{"entry": seed}]}}})


def test_an_openssh_private_key_header_is_refused():
    key = "-----BEGIN OPENSSH PRIVATE KEY-----\nb3BlbnNz\n-----END OPENSSH PRIVATE KEY-----"
    with pytest.raises(WitnessConfigError, match="inline PEM private key"):
        assert_no_private_key_material({"blob": key})


def test_an_inline_pem_private_key_is_refused_under_any_key_name():
    pem = "-----BEGIN PRIVATE KEY-----\nMC4CAQ...\n-----END PRIVATE KEY-----"
    bad = {**GOOD, "sink": {**GOOD["sink"], "options": {"harmless_blob": pem}}}
    with pytest.raises(WitnessConfigError, match="inline PEM private key") as exc:
        load_witness_config(bad)
    assert exc.value.code == "WITNESS_PRIVATE_KEY_IN_CONFIG"


def test_pem_material_nested_in_a_list_is_refused():
    pem = "-----BEGIN OPENSSH PRIVATE KEY-----\nabc\n-----END OPENSSH PRIVATE KEY-----"
    with pytest.raises(WitnessConfigError, match="inline PEM private key"):
        assert_no_private_key_material({"a": [{"b": pem}]})


@pytest.mark.parametrize("name", [
    "key_arn", "kms_key_id", "role_arn", "credentials_profile", "secret_arn", "public_key_path",
])
def test_naming_where_a_secret_LIVES_is_not_the_same_as_holding_it(name):
    """A KMS ARN, an IAM role or a Secrets Manager reference points at externally-held custody. Refusing
    those would make the production shape unconfigurable while preventing nothing."""
    assert_no_private_key_material({name: "arn:aws:iam::1:role/anchor-witness"})


def test_the_scan_runs_before_any_factory_is_named():
    """Key material is refused even when the rest of the block is unparseable — the scan precedes shape
    validation so a malformed config cannot smuggle a key past it."""
    with pytest.raises(WitnessConfigError, match="private signing material"):
        load_witness_config({"private_key": "abc"})


# ---- evidence does not leak the declaration's values -------------------------------------------------

def test_open_provenance_summarises_options_by_key_not_value():
    """The evidence is published into the readiness report; option VALUES are not copied into it."""
    provenance = load_witness_config(GOOD).to_open_provenance()
    assert provenance["signer"]["option_keys"] == ["key_arn", "region"]
    assert "arn:aws:kms:us-east-1:1:key/abc" not in str(provenance)
    assert provenance["profile"] == "PRODUCTION"
