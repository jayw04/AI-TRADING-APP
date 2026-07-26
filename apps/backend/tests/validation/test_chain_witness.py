"""Independent anchor witness primitives (R5d): the separate-boundary signer, the public verifier, and
the external append-only sink."""

from __future__ import annotations

import pytest

from app.validation.chain_witness import (
    Ed25519AnchorSigner,
    FileExternalAnchorSink,
    WitnessedTip,
    WitnessError,
)
from app.validation.witness_protocol import (
    ALGORITHM_ED25519,
    PROTOCOL_VERSION,
    fingerprint_public_key,
)

TIP = WitnessedTip(sequence=1, session_date="2026-07-24", commit_sha256="a" * 64,
                   anchor_sha256="b" * 64)


def test_a_signature_verifies_with_the_public_key():
    signer = Ed25519AnchorSigner.generate(witness_identity="w")
    receipt = signer.attest(TIP)
    signer.verifier().verify(TIP, receipt)             # no raise
    # v2: the FULL fingerprint, not the retired 64-bit `public_key_id`.
    assert receipt.public_key_fingerprint == fingerprint_public_key(signer.public_bytes())
    assert len(receipt.public_key_fingerprint) == 64
    assert receipt.protocol_version == PROTOCOL_VERSION
    assert receipt.algorithm == ALGORITHM_ED25519
    assert signer.identity().startswith("w@")


def test_a_signature_over_a_different_tip_is_refused():
    signer = Ed25519AnchorSigner.generate(witness_identity="w")
    receipt = signer.attest(TIP)
    other = WitnessedTip(sequence=1, session_date="2026-07-24", commit_sha256="c" * 64,
                         anchor_sha256="b" * 64)
    with pytest.raises(WitnessError) as ei:
        signer.verifier().verify(other, receipt)
    # v2 refuses EARLIER and more precisely than v1 did. A different tip produces a different
    # envelope, so the recomputed digest no longer matches the one the receipt records — the record
    # does not reconstruct. That is a different operational finding from a signature that is
    # mathematically invalid, and it is reported as such.
    assert ei.value.code == "WITNESS_MESSAGE_DIGEST_MISMATCH"


def test_a_receipt_from_a_foreign_key_is_refused():
    signer = Ed25519AnchorSigner.generate(witness_identity="w")
    impostor = Ed25519AnchorSigner.generate(witness_identity="x")
    receipt = impostor.attest(TIP)
    with pytest.raises(WitnessError) as ei:
        signer.verifier().verify(TIP, receipt)         # verifier trusts `signer`, not `impostor`
    # v2 refuses on IDENTITY before cryptography: a foreign key means the receipt's
    # fingerprint disagrees with the installed one, which is a mismatch rather than a bad
    # signature. The operator learns which of the two actually happened.
    assert ei.value.code == "WITNESS_KEY_IDENTITY_MISMATCH"


def test_the_external_sink_persists_and_reads_back(tmp_path):
    signer = Ed25519AnchorSigner.generate(witness_identity="w")
    sink = FileExternalAnchorSink(tmp_path / "ext", identity="ext")
    receipt = signer.attest(TIP)
    sink.publish(TIP, receipt)
    back = sink.read_all()
    assert len(back) == 1
    tip2, receipt2 = back[0]
    assert tip2 == TIP and receipt2 == receipt


def test_the_external_sink_is_append_only(tmp_path):
    """Re-publishing the SAME tip is idempotent; a DIFFERENT tip at the same sequence is refused — the
    sink never rewrites a recorded witness."""
    signer = Ed25519AnchorSigner.generate(witness_identity="w")
    sink = FileExternalAnchorSink(tmp_path / "ext", identity="ext")
    sink.publish(TIP, signer.attest(TIP))
    sink.publish(TIP, signer.attest(TIP))              # idempotent — same tip
    assert len(sink.read_all()) == 1

    conflicting = WitnessedTip(sequence=1, session_date="2026-07-24", commit_sha256="d" * 64,
                               anchor_sha256="b" * 64)
    with pytest.raises(WitnessError) as ei:
        sink.publish(conflicting, signer.attest(conflicting))
    assert ei.value.code == "EXTERNAL_WITNESS_DIVERGES"


def test_the_external_sink_reads_in_sequence_order(tmp_path):
    signer = Ed25519AnchorSigner.generate(witness_identity="w")
    sink = FileExternalAnchorSink(tmp_path / "ext", identity="ext")
    tips = [WitnessedTip(sequence=i, session_date=f"2026-07-{20 + i:02d}",
                         commit_sha256=f"{i:064d}", anchor_sha256="b" * 64) for i in (3, 1, 2)]
    for t in tips:
        sink.publish(t, signer.attest(t))
    assert [t.sequence for t, _ in sink.read_all()] == [1, 2, 3]
