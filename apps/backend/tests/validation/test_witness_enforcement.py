"""The production witness gate (R5e).

R5d proved the record CAN be anchored across a separate trust boundary. These tests defend the property
R5d could not: that a governed run cannot be wired with a boundary that does not exist. The reference
signer and filesystem sink satisfy every interface the runner asks for while providing neither
separation nor immutability, and a record witnessed by them looks witnessed.
"""

from __future__ import annotations

import base64

import pytest

from app.validation.chain_witness import (
    AnchorVerifier,
    Ed25519AnchorSigner,
    FileExternalAnchorSink,
    WitnessedTip,
)
from app.validation.witness_config import WitnessConfig, WitnessConfigError, load_witness_config
from app.validation.witness_enforcement import (
    CHALLENGE_SEQUENCE,
    ImmutabilityAttestation,
    WitnessEnforcementError,
    enforce_production_witness,
    load_trusted_verifier,
)
from tests.validation import witness_doubles as doubles

DOUBLES = "tests.validation.witness_doubles"
NONCE = "2026-07-25T00:00:00Z"


@pytest.fixture
def service_key(tmp_path):
    """A key provisioned inside the stand-in signing service; only its PUBLIC bytes are installed."""
    public_bytes = doubles.provision_service_key("svc-1")
    path = tmp_path / "anchor_witness.pub"
    path.write_bytes(public_bytes)
    return {"public_bytes": public_bytes, "path": path}


def _config(service_key, *, profile="PRODUCTION", signer="build_signer", sink="build_sink",
            signer_options=None, sink_options=None, public_key_path=None) -> WitnessConfig:
    return load_witness_config({
        "profile": profile,
        "public_key_path": str(public_key_path or service_key["path"]),
        "signer": {"factory": f"{DOUBLES}:{signer}", "identity": "kms://anchor-witness",
                   "options": signer_options or {}},
        "sink": {"factory": f"{DOUBLES}:{sink}", "identity": "s3://anchors/prod",
                 "options": sink_options or {}},
    })


# ---- the gate accepts a genuinely production-shaped witness -----------------------------------------

def test_a_production_witness_is_accepted_and_evidenced(service_key):
    witness = enforce_production_witness(_config(service_key), nonce=NONCE)

    assert witness.verifier.public_key_id == AnchorVerifier(service_key["public_bytes"]).public_key_id
    assert witness.evidence["profile"] == "PRODUCTION"
    assert witness.evidence["signer"]["key_challenge"]["challenged"] is True
    assert witness.evidence["sink"]["immutability"]["enforced"] is True
    assert witness.evidence["sink"]["immutability"]["source"] == "STORAGE"


def test_the_evidence_records_that_the_key_did_not_come_from_the_signer(service_key):
    """The circularity R5d left open: a verifier obtained from the signer verifies every forgery."""
    witness = enforce_production_witness(_config(service_key), nonce=NONCE)
    assert witness.evidence["verifying_key"]["obtained_from_signer"] is False
    assert witness.evidence["verifying_key"]["source_path"] == str(service_key["path"])


def test_factory_options_are_passed_through(service_key):
    witness = enforce_production_witness(
        _config(service_key, sink_options={"scope": "s3://anchors/alt", "mode": "GOVERNANCE"}),
        nonce=NONCE)
    assert witness.evidence["sink"]["immutability"]["scope"] == "s3://anchors/alt"


# ---- the profile ------------------------------------------------------------------------------------

def test_a_reference_profile_can_never_witness_a_governed_session(service_key):
    with pytest.raises(WitnessEnforcementError, match="development implementations") as exc:
        enforce_production_witness(_config(service_key, profile="REFERENCE"), nonce=NONCE)
    assert exc.value.code == "WITNESS_PROFILE_NOT_PRODUCTION"


def test_the_profile_is_checked_before_the_signer_is_contacted(service_key, monkeypatch):
    """A REFERENCE deployment must be refused by name, not by tripping over a later check."""
    def forbidden(*a, **k):                       # pragma: no cover - must never be reached
        raise AssertionError("the gate resolved a factory for a REFERENCE deployment")

    monkeypatch.setattr("app.validation.witness_enforcement._resolve_factory", forbidden)
    with pytest.raises(WitnessEnforcementError, match="development implementations"):
        enforce_production_witness(_config(service_key, profile="REFERENCE"), nonce=NONCE)


# ---- the reference implementations cannot reach production ------------------------------------------

def test_the_reference_signer_is_refused_even_from_an_unrelated_factory(service_key):
    """The module-name check alone would miss this: the factory lives elsewhere and hands back
    `Ed25519AnchorSigner`. The class marker is what catches it."""
    with pytest.raises(WitnessEnforcementError, match="reference implementation") as exc:
        enforce_production_witness(_config(service_key, signer="build_reference_signer"), nonce=NONCE)
    assert exc.value.code == "WITNESS_SIGNER_NOT_SEPARATELY_CONTROLLED"


def test_the_reference_sink_is_refused_even_from_an_unrelated_factory(service_key, tmp_path):
    with pytest.raises(WitnessEnforcementError, match="reference implementation") as exc:
        enforce_production_witness(
            _config(service_key, sink="build_reference_sink",
                    sink_options={"root": str(tmp_path / "sink")}), nonce=NONCE)
    assert exc.value.code == "WITNESS_SINK_NOT_IMMUTABLE"


def test_both_reference_classes_carry_the_marker():
    """The marker is the general rule — a reference implementation added later is refused without the
    gate being taught about it."""
    assert Ed25519AnchorSigner.IS_REFERENCE_IMPLEMENTATION is True
    assert FileExternalAnchorSink.IS_REFERENCE_IMPLEMENTATION is True


@pytest.mark.parametrize("signer_factory,sink_factory", [
    ("app.validation.chain_witness:Ed25519AnchorSigner", f"{DOUBLES}:build_sink"),
    (f"{DOUBLES}:build_signer", "app.validation.chain_witness:FileExternalAnchorSink"),
])
def test_a_factory_resolving_into_the_reference_module_is_refused_before_import(
        service_key, signer_factory, sink_factory):
    config = load_witness_config({
        "profile": "PRODUCTION", "public_key_path": str(service_key["path"]),
        "signer": {"factory": signer_factory, "identity": "kms://x"},
        "sink": {"factory": sink_factory, "identity": "s3://y"}})
    with pytest.raises(WitnessEnforcementError, match="reference implementations"):
        enforce_production_witness(config, nonce=NONCE)


# ---- the signer holds no key this process can sign with ---------------------------------------------

def test_a_signer_wrapping_a_local_keypair_is_refused(service_key):
    """Structurally the reference signer under a different class name: the store-writer can sign
    anything, so the signature attests to nothing about who authorised the tip."""
    with pytest.raises(WitnessEnforcementError, match="holds a Ed25519PrivateKey in this process") as e:
        enforce_production_witness(_config(service_key, signer="build_wrapper_signer"), nonce=NONCE)
    assert e.value.code == "WITNESS_SIGNER_NOT_SEPARATELY_CONTROLLED"


def test_a_key_hidden_one_container_deep_is_refused(service_key):
    with pytest.raises(WitnessEnforcementError, match="holds a Ed25519PrivateKey"):
        enforce_production_witness(
            _config(service_key, signer="build_nested_wrapper_signer"), nonce=NONCE)


def test_an_object_that_is_not_a_signer_is_refused(service_key):
    with pytest.raises(WitnessEnforcementError, match="does not satisfy the AnchorSigner"):
        enforce_production_witness(_config(service_key, signer="build_not_a_signer"), nonce=NONCE)


def test_a_factory_that_cannot_construct_is_a_refusal_not_a_crash(service_key):
    with pytest.raises(WitnessEnforcementError, match="failed to construct") as exc:
        enforce_production_witness(_config(service_key, signer="build_exploding_signer"), nonce=NONCE)
    assert exc.value.code == "WITNESS_SIGNER_NOT_SEPARATELY_CONTROLLED"


def test_an_unresolvable_factory_is_a_refusal(service_key):
    config = load_witness_config({
        "profile": "PRODUCTION", "public_key_path": str(service_key["path"]),
        "signer": {"factory": "no.such.module:build", "identity": "x"},
        "sink": {"factory": f"{DOUBLES}:build_sink", "identity": "y"}})
    with pytest.raises(WitnessEnforcementError, match="could not be resolved"):
        enforce_production_witness(config, nonce=NONCE)


def test_key_material_in_factory_options_is_refused_at_the_gate_too(service_key):
    """`load_witness_config` scans the declaration; the gate re-scans the options it is about to pass to
    a factory, so a config assembled in code cannot bypass the check."""
    from app.validation.witness_config import WitnessComponentConfig

    config = _config(service_key)
    poisoned = WitnessConfig(
        profile=config.profile, sink=config.sink, public_key_path=config.public_key_path,
        signer=WitnessComponentConfig(factory=f"{DOUBLES}:build_signer", identity="x",
                                      options={"private_key": "abc"}))
    with pytest.raises(WitnessConfigError, match="private signing material"):
        enforce_production_witness(poisoned, nonce=NONCE)


# ---- the signer must hold the DEPLOYMENT-INSTALLED key ----------------------------------------------

def test_a_signer_holding_a_different_key_is_refused(service_key, tmp_path):
    """The substitution R5d could not detect until the first `verify_anchor_consistency` — after a
    session had been evaluated."""
    other = tmp_path / "other.pub"
    other.write_bytes(doubles.provision_service_key("svc-other"))
    with pytest.raises(WitnessEnforcementError, match="does not hold the trusted key") as exc:
        enforce_production_witness(_config(service_key, public_key_path=other), nonce=NONCE)
    assert exc.value.code == "WITNESS_SIGNER_KEY_UNTRUSTED"


def test_an_unreachable_signer_is_refused_before_anything_runs(service_key):
    with pytest.raises(WitnessEnforcementError, match="could not be reached") as exc:
        enforce_production_witness(_config(service_key, signer="build_unreachable_signer"), nonce=NONCE)
    assert exc.value.code == "WITNESS_SIGNER_KEY_UNTRUSTED"


def test_the_challenge_signature_can_never_be_replayed_as_a_real_tip(service_key):
    """`sequence = 0` is outside the committed numbering, which starts at 1, so a captured challenge
    receipt cannot be presented as the witness for an observation."""
    from app.validation.witness_enforcement import CHALLENGE_SESSION

    assert CHALLENGE_SEQUENCE == 0
    with pytest.raises(ValueError):
        # the challenge's session field is deliberately not a date
        __import__("datetime").date.fromisoformat(CHALLENGE_SESSION)


def test_the_challenge_is_deterministic_in_the_nonce(service_key):
    """The caller supplies the nonce (the run timestamp), so the gate is reproducible under test and
    distinct per invocation in production."""
    a = enforce_production_witness(_config(service_key), nonce=NONCE)
    b = enforce_production_witness(_config(service_key), nonce="2026-07-26T00:00:00Z")
    assert a.evidence["signer"]["key_challenge"]["nonce"] == NONCE
    assert b.evidence["signer"]["key_challenge"]["nonce"] == "2026-07-26T00:00:00Z"


# ---- the deployment-installed verifying key ---------------------------------------------------------

def test_a_missing_verifying_key_is_refused(service_key, tmp_path):
    with pytest.raises(WitnessEnforcementError, match="unreadable") as exc:
        enforce_production_witness(
            _config(service_key, public_key_path=tmp_path / "absent.pub"), nonce=NONCE)
    assert exc.value.code == "WITNESS_PUBLIC_KEY_UNAVAILABLE"


def test_the_signers_own_key_is_not_an_acceptable_substitute(service_key, tmp_path):
    with pytest.raises(WitnessEnforcementError, match="not an acceptable substitute"):
        enforce_production_witness(
            _config(service_key, public_key_path=tmp_path / "absent.pub"), nonce=NONCE)


@pytest.mark.parametrize("encode", [
    lambda b: b,
    lambda b: b.hex().encode("ascii"),
    lambda b: base64.b64encode(b),
])
def test_the_key_is_accepted_in_the_encodings_a_deployment_installs(tmp_path, encode):
    public_bytes = doubles.provision_service_key("svc-enc")
    path = tmp_path / "k.pub"
    path.write_bytes(encode(public_bytes))
    assert load_trusted_verifier(path).public_key_id == AnchorVerifier(public_bytes).public_key_id


def test_a_raw_key_written_with_a_trailing_newline_is_still_read(tmp_path):
    """A foot-gun worth absorbing: most tools that write a key file append a newline, and refusing that
    would look like a corrupt key rather than a formatting difference."""
    public_bytes = doubles.provision_service_key("svc-nl")
    path = tmp_path / "k.pub"
    path.write_bytes(public_bytes + b"\n")
    assert load_trusted_verifier(path).public_key_id == AnchorVerifier(public_bytes).public_key_id


def test_a_key_of_the_wrong_length_is_refused_not_truncated(tmp_path):
    path = tmp_path / "short.pub"
    path.write_bytes(b"too short")
    with pytest.raises(WitnessEnforcementError, match="is 9 bytes"):
        load_trusted_verifier(path)


# ---- the sink proves its own immutability -----------------------------------------------------------

def test_a_sink_that_cannot_answer_is_refused(service_key):
    with pytest.raises(WitnessEnforcementError, match="cannot attest its own immutability") as exc:
        enforce_production_witness(_config(service_key, sink="build_silent_sink"), nonce=NONCE)
    assert exc.value.code == "WITNESS_SINK_IMMUTABILITY_UNPROVEN"


def test_a_declared_immutability_is_not_evidence(service_key):
    """"The deployment says the bucket has Object Lock" is not evidence that it does, and the record's
    entire truncation resistance rests on it."""
    with pytest.raises(WitnessEnforcementError, match="not queried from the storage") as exc:
        enforce_production_witness(_config(service_key, sink="build_declared_sink"), nonce=NONCE)
    assert exc.value.code == "WITNESS_SINK_IMMUTABILITY_UNPROVEN"


def test_a_sink_reporting_no_enforcement_is_refused(service_key):
    with pytest.raises(WitnessEnforcementError, match="does NOT enforce write-once") as exc:
        enforce_production_witness(_config(service_key, sink="build_unenforced_sink"), nonce=NONCE)
    assert exc.value.code == "WITNESS_SINK_NOT_IMMUTABLE"


def test_a_sink_that_cannot_be_queried_is_refused(service_key):
    with pytest.raises(WitnessEnforcementError, match="could not be asked"):
        enforce_production_witness(_config(service_key, sink="build_unreachable_sink"), nonce=NONCE)


def test_enforcement_without_a_named_mode_and_scope_is_refused(service_key):
    with pytest.raises(WitnessEnforcementError, match="without naming the mode and scope"):
        enforce_production_witness(_config(service_key, sink="build_unscoped_sink"), nonce=NONCE)


def test_an_attestation_of_the_wrong_type_is_refused(service_key):
    with pytest.raises(WitnessEnforcementError, match="rather than an ImmutabilityAttestation"):
        enforce_production_witness(_config(service_key, sink="build_wrong_attestation_sink"),
                                   nonce=NONCE)


def test_the_attestation_is_published_in_full(service_key):
    attestation = ImmutabilityAttestation(
        enforced=True, mode="COMPLIANCE", scope="s3://anchors/prod", source="STORAGE",
        checked_at="2026-07-25T00:00:00Z", detail="GetObjectLockConfiguration")
    assert attestation.to_open_provenance()["detail"] == "GetObjectLockConfiguration"


# ---- the accepted witness is usable ------------------------------------------------------------------

def test_the_enforced_triple_actually_witnesses_a_tip(service_key):
    """The gate returns working collaborators, not merely approved ones: a tip signed by the enforced
    signer verifies under the enforced verifier and is recorded by the enforced sink."""
    witness = enforce_production_witness(_config(service_key), nonce=NONCE)
    tip = WitnessedTip(sequence=1, session_date="2026-07-24", commit_sha256="a" * 64,
                       anchor_sha256="b" * 64)

    receipt = witness.signer.attest(tip)
    witness.verifier.verify(tip, receipt)
    witness.sink.publish(tip, receipt)

    recorded = witness.sink.read_all()
    assert [t.sequence for t, _ in recorded] == [1]
