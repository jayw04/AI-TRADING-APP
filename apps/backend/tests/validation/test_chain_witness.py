"""Independent anchor witness primitives (R5d): the separate-boundary signer, the public verifier, and
the external append-only sink."""

from __future__ import annotations

import pytest

from app.validation.chain_witness import (
    Ed25519AnchorSigner,
    FileExternalAnchorSink,
    WitnessedTip,
    WitnessError,
    public_key_id,
)

TIP = WitnessedTip(sequence=1, session_date="2026-07-24", commit_sha256="a" * 64,
                   anchor_sha256="b" * 64)


def test_a_signature_verifies_with_the_public_key():
    signer = Ed25519AnchorSigner.generate(witness_identity="w")
    receipt = signer.attest(TIP)
    signer.verifier().verify(TIP, receipt)             # no raise
    assert receipt.public_key_id == public_key_id(signer.public_bytes())
    assert signer.identity().startswith("w@")


def test_a_signature_over_a_different_tip_is_refused():
    signer = Ed25519AnchorSigner.generate(witness_identity="w")
    receipt = signer.attest(TIP)
    other = WitnessedTip(sequence=1, session_date="2026-07-24", commit_sha256="c" * 64,
                         anchor_sha256="b" * 64)
    with pytest.raises(WitnessError) as ei:
        signer.verifier().verify(other, receipt)
    assert ei.value.code == "ANCHOR_SIGNATURE_INVALID"


def test_a_receipt_from_a_foreign_key_is_refused():
    signer = Ed25519AnchorSigner.generate(witness_identity="w")
    impostor = Ed25519AnchorSigner.generate(witness_identity="x")
    receipt = impostor.attest(TIP)
    with pytest.raises(WitnessError) as ei:
        signer.verifier().verify(TIP, receipt)         # verifier trusts `signer`, not `impostor`
    assert ei.value.code == "ANCHOR_SIGNATURE_INVALID"


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
