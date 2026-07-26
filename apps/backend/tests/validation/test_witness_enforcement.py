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
from app.validation.witness_enforcement import (  # noqa: I001
    CHALLENGE_SEQUENCE,
    ImmutabilityAttestation,
    WitnessEnforcementError,
    _can_enforce_path_guarantees,
    build_trusted_verifier,
    enforce_production_witness,
)
from app.validation.witness_protocol import fingerprint_public_key
from tests.validation import witness_doubles as doubles

DOUBLES = "tests.validation.witness_doubles"
NONCE = "2026-07-25T00:00:00Z"
KEY_ARN = "arn:aws:kms:us-east-1:219024422756:key/1234abcd"


# R5e-2 closed the key path with POSIX-only guarantees — ownership, O_NOFOLLOW, and dir_fd-relative
# opens — and made a PRODUCTION witness FAIL CLOSED where they cannot be established. Windows can
# establish none of them, so every test that drives the real gate is meaningless there and is skipped
# rather than weakened. Linux CI runs all of them; see the R5e-2 submission for the exact counts.
POSIX_ONLY = pytest.mark.skipif(
    not _can_enforce_path_guarantees(),
    reason="a PRODUCTION witness requires POSIX ownership/no-follow guarantees; the gate fails closed "
           "here by design, so exercising it on this platform would test nothing")


@pytest.fixture
def service_key(tmp_path):
    """A key provisioned inside the stand-in signing service; only its PUBLIC bytes are installed.

    `root` is the trusted root the config declares. It must be `tmp_path` itself, NOT an ancestor:
    pytest's temporary directories live under a world-writable `/tmp`, which the key-path walk correctly
    refuses. A deployment names the root it actually governs for exactly this reason.
    """
    if not _can_enforce_path_guarantees():
        pytest.skip("PRODUCTION witness enforcement requires POSIX; it fails closed here by design")
    # P-256 DER SPKI, exactly as KMS GetPublicKey returns it. An Ed25519 key here would be refused at
    # config load, because PRODUCTION pins ECDSA_SHA_256_P256 (ADR 0045) — so a production-gate test
    # must be driven by production-shaped material or it would test nothing.
    public_bytes = doubles.provision_p256_service_key("svc-1")
    path = tmp_path / "anchor_witness.pub"
    path.write_bytes(public_bytes)
    return {"public_bytes": public_bytes, "path": path, "root": tmp_path}


def _config(service_key, *, profile="PRODUCTION", signer="build_p256_signer", sink="build_sink",
            signer_options=None, sink_options=None, public_key_path=None,
            sink_identity="s3://anchors/prod", trusted_root=None) -> WitnessConfig:
    return load_witness_config({
        "profile": profile,
        "algorithm": "ECDSA_SHA_256_P256",
        "key_id": KEY_ARN,
        "trusted_root": str(trusted_root or service_key["root"]),
        "public_key_path": str(public_key_path or service_key["path"]),
        "signer": {"factory": f"{DOUBLES}:{signer}", "identity": "kms://anchor-witness",
                   "options": signer_options if signer_options is not None
                   else {"handle": "svc-1", "key_arn": KEY_ARN}},
        "sink": {"factory": f"{DOUBLES}:{sink}", "identity": sink_identity,
                 "options": sink_options or {}},
    })


# ---- the gate accepts a genuinely production-shaped witness -----------------------------------------

def test_a_production_witness_is_accepted_and_evidenced(service_key):
    witness = enforce_production_witness(_config(service_key), nonce=NONCE)

    assert witness.verifier.public_key_fingerprint == fingerprint_public_key(
        service_key["public_bytes"])
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
        _config(service_key, sink_identity="s3://anchors/alt",
                sink_options={"scope": "s3://anchors/alt", "mode": "GOVERNANCE"}),
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
    # a PASSING p256 signer, so the refusal under test is the SINK's reference module,
    # not the signer failing an unrelated key challenge first.
    (f"{DOUBLES}:build_p256_signer", "app.validation.chain_witness:FileExternalAnchorSink"),
])
def test_a_factory_resolving_into_the_reference_module_is_refused_before_import(
        service_key, signer_factory, sink_factory):
    config = load_witness_config({
        "profile": "PRODUCTION", "trusted_root": str(service_key["root"]),
        "algorithm": "ECDSA_SHA_256_P256", "key_id": KEY_ARN,
        "public_key_path": str(service_key["path"]),
        "signer": {"factory": signer_factory, "identity": "kms://x",
                   "options": {"handle": "svc-1", "key_arn": KEY_ARN}
                   if "p256" in signer_factory else {}},
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
        "profile": "PRODUCTION", "trusted_root": str(service_key["root"]),
        "algorithm": "ECDSA_SHA_256_P256", "key_id": KEY_ARN,
        "public_key_path": str(service_key["path"]),
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
        # Carried deliberately. Omitting it defaults the key-path walk to the filesystem root, and on
        # any ordinary Linux box `/tmp` is mode 0o1777 — so the walk refuses (correctly) before this
        # test reaches the key-material scan it is actually about. Linux CI caught exactly that.
        trusted_root=config.trusted_root,
        # Same reasoning as trusted_root: without the pinned algorithm the verifier defaults to
        # Ed25519 and refuses the 91-byte P-256 SPKI before reaching the key-material scan.
        algorithm=config.algorithm, key_id=config.key_id,
        signer=WitnessComponentConfig(factory=f"{DOUBLES}:build_signer", identity="x",
                                      options={"private_key": "abc"}))
    with pytest.raises(WitnessConfigError, match="private signing material"):
        enforce_production_witness(poisoned, nonce=NONCE)


# ---- the signer must hold the DEPLOYMENT-INSTALLED key ----------------------------------------------

def test_a_signer_holding_a_different_key_is_refused(service_key, tmp_path):
    """The substitution R5d could not detect until the first `verify_anchor_consistency` — after a
    session had been evaluated."""
    other = tmp_path / "other.pub"
    other.write_bytes(doubles.provision_p256_service_key("svc-other"))
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
    assert (build_trusted_verifier(path.read_bytes(), source=str(path)).public_key_fingerprint
            == AnchorVerifier(public_bytes).public_key_fingerprint)


def test_a_raw_key_written_with_a_trailing_newline_is_still_read(tmp_path):
    """A foot-gun worth absorbing: most tools that write a key file append a newline, and refusing that
    would look like a corrupt key rather than a formatting difference."""
    public_bytes = doubles.provision_service_key("svc-nl")
    path = tmp_path / "k.pub"
    path.write_bytes(public_bytes + b"\n")
    assert (build_trusted_verifier(path.read_bytes(), source=str(path)).public_key_fingerprint
            == AnchorVerifier(public_bytes).public_key_fingerprint)


def test_a_key_of_the_wrong_length_is_refused_not_truncated(tmp_path):
    path = tmp_path / "short.pub"
    path.write_bytes(b"too short")
    with pytest.raises(WitnessEnforcementError, match="is 9 bytes"):
        build_trusted_verifier(path.read_bytes(), source=str(path))


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


# ---- the attestation is bound to the storage that actually publishes --------------------------------

def test_a_sink_attesting_one_bucket_and_publishing_to_another_is_refused(service_key):
    """The ordinary wiring error the other checks cannot see: Object Lock verified on bucket A, tips
    written to bucket B. `enforced=True`, `source=STORAGE`, mode and scope all impeccable — and the
    record's truncation resistance rests on storage anyone can truncate."""
    with pytest.raises(WitnessEnforcementError, match="storage identities disagree") as exc:
        enforce_production_witness(_config(service_key, sink="build_split_storage_sink"), nonce=NONCE)
    assert exc.value.code == "WITNESS_SINK_STORAGE_MISBOUND"
    assert "s3://anchors/scratch" in str(exc.value)


def test_an_attestation_that_names_no_storage_is_refused(service_key):
    with pytest.raises(WitnessEnforcementError, match="without naming WHICH storage") as exc:
        enforce_production_witness(
            _config(service_key, sink="build_unbound_attestation_sink"), nonce=NONCE)
    assert exc.value.code == "WITNESS_SINK_STORAGE_MISBOUND"


def test_a_sink_that_cannot_report_its_publication_storage_is_refused(service_key):
    with pytest.raises(WitnessEnforcementError, match="cannot report the storage") as exc:
        enforce_production_witness(
            _config(service_key, sink="build_no_publication_identity_sink"), nonce=NONCE)
    assert exc.value.code == "WITNESS_SINK_STORAGE_MISBOUND"


def test_an_unreachable_publication_client_is_a_refusal_not_a_crash(service_key):
    with pytest.raises(WitnessEnforcementError, match="could not report its publication storage") as e:
        enforce_production_witness(
            _config(service_key, sink="build_unreportable_publication_sink"), nonce=NONCE)
    assert e.value.code == "WITNESS_SINK_STORAGE_MISBOUND"


def test_a_sink_publishing_to_storage_the_deployment_did_not_declare_is_refused(service_key):
    """The declared identity is one of the four that must agree, so an adapter silently pointed at
    different storage than the governed configuration names cannot pass."""
    with pytest.raises(WitnessEnforcementError, match="storage identities disagree"):
        enforce_production_witness(
            _config(service_key, sink_identity="s3://anchors/declared"), nonce=NONCE)


def test_all_four_identities_are_recorded_when_they_agree(service_key):
    witness = enforce_production_witness(_config(service_key), nonce=NONCE)
    immutability = witness.evidence["sink"]["immutability"]
    assert immutability["storage_identity"] == "s3://anchors/prod"
    assert witness.evidence["sink"]["reported_identity"] == "s3://anchors/prod"
    assert witness.evidence["sink"]["identity"] == "s3://anchors/prod"


def test_the_attestation_is_published_in_full(service_key):
    attestation = ImmutabilityAttestation(
        enforced=True, mode="COMPLIANCE", scope="s3://anchors/prod", source="STORAGE",
        checked_at="2026-07-25T00:00:00Z", storage_identity="s3://anchors/prod",
        detail="GetObjectLockConfiguration")
    provenance = attestation.to_open_provenance()
    assert provenance["detail"] == "GetObjectLockConfiguration"
    assert provenance["storage_identity"] == "s3://anchors/prod"


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


# ---- raw-key decoding boundaries (hotfix: strip() ate legitimate key bytes) --------------------------
#
# `_decode_public_key` tolerated a trailing newline with `blob.strip(b"\r\n\t ")`. `strip` removes ANY
# leading/trailing byte in that set, and a raw Ed25519 key is uniformly distributed binary — so whenever
# the key's own first or last byte was `\r`, `\n`, `\t` or space (4 of 256 values), real key material
# was consumed and a valid key was refused as "33 bytes". Measured at 3.10% over 2000 generated keys,
# which is why it presented as a rare CI flake rather than a bug.
#
# Every boundary case below uses a DETERMINISTIC key. Behaviour that depends on which key you happened
# to generate is exactly what allowed this to reach main.

_FILLER = bytes(range(1, 32))                      # 31 bytes, none of them whitespace-valued


def _key_ending(final: int) -> bytes:
    key = _FILLER + bytes([final])
    assert len(key) == 32
    return key


def _key_starting(first: int) -> bytes:
    key = bytes([first]) + _FILLER
    assert len(key) == 32
    return key


def test_a_raw_key_ending_in_lf_survives_an_appended_lf():
    """The exact case that broke: the key's own last byte is 0x0A, and the file adds another."""
    from app.validation.witness_enforcement import _decode_public_key

    key = _key_ending(0x0A)
    assert _decode_public_key(key + b"\n") == key


def test_a_raw_key_ending_in_cr_survives_an_appended_crlf():
    from app.validation.witness_enforcement import _decode_public_key

    key = _key_ending(0x0D)
    assert _decode_public_key(key + b"\r\n") == key


@pytest.mark.parametrize("final", [0x09, 0x0A, 0x0D, 0x20], ids=["tab", "lf", "cr", "space"])
def test_every_whitespace_valued_final_byte_survives_an_appended_lf(final):
    """The full corpus of bytes the old strip set would have eaten from the end."""
    from app.validation.witness_enforcement import _decode_public_key

    key = _key_ending(final)
    assert _decode_public_key(key + b"\n") == key


@pytest.mark.parametrize("first", [0x09, 0x0A, 0x0D, 0x20], ids=["tab", "lf", "cr", "space"])
def test_a_whitespace_valued_leading_byte_is_preserved(first):
    """`strip` works on BOTH ends, so a key merely starting with one of these was also corrupted."""
    from app.validation.witness_enforcement import _decode_public_key

    key = _key_starting(first)
    assert _decode_public_key(key) == key
    assert _decode_public_key(key + b"\n") == key


def test_a_raw_key_ending_in_space_or_tab_is_preserved_without_a_terminator():
    """Space and tab are valid key bytes and are NOT accepted as terminators."""
    from app.validation.witness_enforcement import _decode_public_key

    for final in (0x20, 0x09):
        key = _key_ending(final)
        assert _decode_public_key(key) == key


def test_a_33_byte_blob_without_an_lf_terminator_is_not_truncated():
    """Only an exact trailing LF is a terminator. A 33-byte blob ending in anything else is not a
    32-byte key with a newline, and must not be silently cut down to one."""
    from app.validation.witness_enforcement import _decode_public_key

    blob = _FILLER + bytes([0x41, 0x42])           # 33 bytes, ends 'B'
    assert _decode_public_key(blob) != blob[:32]
    assert len(_decode_public_key(blob)) != 32


def test_a_34_byte_blob_without_an_exact_crlf_terminator_is_not_truncated():
    from app.validation.witness_enforcement import _decode_public_key

    blob = _FILLER + bytes([0x41, 0x0A, 0x0D])     # 34 bytes, ends LF CR (not CR LF)
    assert len(_decode_public_key(blob)) != 32


def test_a_raw_key_ending_in_lf_with_an_appended_lf_is_resolved_deterministically(tmp_path):
    """Genuinely ambiguous at the byte level: 33 bytes ending LF could be a 32-byte key plus a
    terminator, or a 33-byte blob. The shape rule resolves it as key-plus-terminator, and what matters
    is that the resolution is DETERMINISTIC rather than dependent on the key material — the old
    `strip()` decided based on the key's own bytes, which is how it corrupted ~1 key in 32."""
    from app.validation.witness_enforcement import _decode_public_key

    key = _key_ending(0x0A)
    assert _decode_public_key(key + b"\n") == key          # resolved as key + terminator


def test_the_decoder_is_deterministic_across_generated_keys():
    """The integration check the boundary tests replace: no generated key may decode wrongly.

    Under the old implementation this failed for ~3.1% of keys.
    """
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

    from app.validation.witness_enforcement import _decode_public_key

    for _ in range(500):
        pub = Ed25519PrivateKey.generate().public_key().public_bytes_raw()
        assert _decode_public_key(pub) == pub
        assert _decode_public_key(pub + b"\n") == pub
        assert _decode_public_key(pub + b"\r\n") == pub
