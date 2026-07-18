"""MR-002 Stage-3 — FROZEN launch-attestation VERIFICATION TOOL.

This is the tool named (path + sha256) INSIDE every launch attestation. It verifies the
attestation's Ed25519 signature against the TRUSTED public key and, only on success,
emits the immutable MR002_STAGE3_LAUNCH_VERIFICATION_RECEIPT consumed by
`load_verification_receipt` in the population runner.

It is deliberately minimal and self-contained (json/hashlib/base64/cryptography only) so
its bytes can be frozen: any edit changes its sha256 and invalidates every attestation
that bound the previous hash. It performs, in order, and fails closed on each:

  1. hash the attestation file bytes;
  2. recompute the FROZEN canonical unsigned payload (every field except
     {signature, canonical_signed_payload_sha256}, json.dumps sort_keys compact utf-8)
     and require equality with the attestation's canonical_signed_payload_sha256;
  3. require the attestation's verification_tool_sha256 to equal the sha256 of THIS
     file's own bytes (tool-identity binding — a different tool cannot claim this one);
  4. load the trusted public key, REQUIRE it to be an Ed25519 public key BY TYPE (a PEM
     of any other key type that happens to load is refused — never assigned an identity),
     derive its key id ('ed25519:' + sha256(raw pubkey)), and require equality with the
     attestation's signing_key_id and algorithm 'ed25519';
  5. cryptographically verify the signature over the canonical payload;
  6. publish the receipt via `publish_immutable` (closed key set) and print its sha256.

`publish_immutable` is THE shared atomic no-replace publication primitive for immutable
evidence (owner review 2026-07-18, blocker 4). It lives HERE, in the frozen hash-bound
tool, and the attestation producer imports it FROM this module — one implementation,
owned by the trust root. It never uses os.replace(): the payload is written to an
O_EXCL 0600 temporary file, fsync'd, then published with os.link(tmp, destination) —
which atomically fails with FileExistsError if the destination exists, even if it
appeared AFTER any pre-check — the temporary is then unlinked (deliberate, recorded
cleanup on both success and refusal; the destination is never touched on refusal) and
the parent directory fsync'd (POSIX; unavailable on Windows and skipped there — the
c6a launch host is Linux, where it is enforced).

Exit codes: 0 verified + receipt written; 2 attestation unreadable/malformed;
3 payload-hash mismatch; 4 tool-identity mismatch; 5 key mismatch/not-Ed25519;
6 SIGNATURE INVALID; 7 receipt publication refused or persistence failure.
"""
from __future__ import annotations

import argparse
import base64
import contextlib
import datetime
import hashlib
import json
import os
import sys

RECEIPT_RECORD_TYPE = "MR002_STAGE3_LAUNCH_VERIFICATION_RECEIPT"


class PublicationRefused(Exception):
    """Immutable-evidence publication refused; the destination was not touched."""


def _sha256_file(path: str) -> str:
    with open(path, "rb") as fh:
        return hashlib.sha256(fh.read()).hexdigest()


def _fsync_dir(path: str) -> bool:
    """fsync the directory entry (POSIX). Windows cannot open directories — skipped
    there and reported False; the c6a launch host is Linux, where failure raises."""
    try:
        fd = os.open(path, os.O_RDONLY)
    except OSError:
        if os.name == "nt":
            return False
        raise
    try:
        os.fsync(fd)
    finally:
        os.close(fd)
    return True


def publish_immutable(path: str, data: bytes) -> str:
    """Atomic no-replace publication for record_status: IMMUTABLE artifacts (blocker 4).

    Refuses an existing destination, an existing temporary path, or a symlink at either;
    then publishes via hard link, whose create-if-absent semantics close the
    check-then-replace race: a destination that appears after the pre-checks makes
    os.link fail with FileExistsError and the publication is REFUSED with the competing
    bytes untouched. The temporary file is always unlinked afterwards (recorded
    behavior). Returns the sha256 of the published bytes.
    """
    tmp = path + ".tmp"
    for p, what in ((path, "DESTINATION"), (tmp, "TEMPORARY_PATH")):
        if os.path.islink(p):
            raise PublicationRefused(f"PUBLISH_REFUSED_SYMLINK_{what}:{p}")
        if os.path.lexists(p):
            raise PublicationRefused(f"PUBLISH_REFUSED_EXISTS_{what}:{p}")
    try:
        fd = os.open(tmp, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError as exc:
        raise PublicationRefused(f"PUBLISH_REFUSED_EXISTS_TEMPORARY_PATH:{tmp}") from exc
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(data)
            fh.flush()
            os.fsync(fh.fileno())
        try:
            os.link(tmp, path)  # atomic create-if-absent: the race-closing boundary
        except FileExistsError as exc:
            raise PublicationRefused(f"PUBLISH_REFUSED_EXISTS_DESTINATION:{path}") from exc
    finally:
        with contextlib.suppress(OSError):
            os.unlink(tmp)  # deliberate cleanup on success AND refusal (recorded)
    _fsync_dir(os.path.dirname(os.path.abspath(path)) or ".")
    return hashlib.sha256(data).hexdigest()


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--attestation", required=True)
    ap.add_argument("--trusted-public-key", required=True, help="PEM Ed25519 public key")
    ap.add_argument("--receipt-out", required=True)
    args = ap.parse_args()

    # 1-2: read, parse, recompute the frozen canonical payload
    try:
        attestation_sha256 = _sha256_file(args.attestation)
        with open(args.attestation, encoding="utf-8") as fh:
            d = json.load(fh)
        if d.get("record_type") != "MR002_STAGE3_LAUNCH_ATTESTATION":
            raise ValueError(f"wrong record_type: {d.get('record_type')}")
        signature_b64 = d["signature"]
        claimed_payload_sha = d["canonical_signed_payload_sha256"]
        run_nonce = d["run_nonce"]
    except (OSError, ValueError, KeyError, json.JSONDecodeError) as exc:
        print(f"VERIFY FAIL (attestation unreadable/malformed): {exc}", file=sys.stderr)
        return 2
    unsigned = {k: v for k, v in d.items()
                if k not in ("signature", "canonical_signed_payload_sha256")}
    payload = json.dumps(unsigned, sort_keys=True, separators=(",", ":")).encode("utf-8")
    if hashlib.sha256(payload).hexdigest() != claimed_payload_sha:
        print("VERIFY FAIL: canonical payload hash mismatch", file=sys.stderr)
        return 3

    # 3: tool-identity binding — the attestation must name THIS tool's bytes
    own_sha = _sha256_file(os.path.realpath(__file__))
    if d.get("verification_tool_sha256") != own_sha:
        print(f"VERIFY FAIL: attestation binds verification_tool_sha256="
              f"{d.get('verification_tool_sha256')} but this tool is {own_sha}",
              file=sys.stderr)
        return 4

    # 4: trusted-key identity — Ed25519 REQUIRED BY TYPE, not by successful load
    try:
        from cryptography.hazmat.primitives import serialization
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
        with open(args.trusted_public_key, "rb") as fh:
            pub = serialization.load_pem_public_key(fh.read())
        if not isinstance(pub, Ed25519PublicKey):
            print(f"VERIFY FAIL: trusted key is {type(pub).__name__}, not Ed25519",
                  file=sys.stderr)
            return 5
        raw = pub.public_bytes(encoding=serialization.Encoding.Raw,
                               format=serialization.PublicFormat.Raw)
        trusted_key_id = f"ed25519:{hashlib.sha256(raw).hexdigest()}"
    except (OSError, ValueError) as exc:
        print(f"VERIFY FAIL (trusted key unreadable): {exc}", file=sys.stderr)
        return 5
    if d.get("signature_algorithm") != "ed25519" or d.get("signing_key_id") != trusted_key_id:
        print(f"VERIFY FAIL: attestation key {d.get('signing_key_id')} / "
              f"{d.get('signature_algorithm')} != trusted {trusted_key_id}", file=sys.stderr)
        return 5

    # 5: cryptographic verification over the canonical payload
    try:
        pub.verify(base64.b64decode(signature_b64), payload)
    except Exception as exc:  # noqa: BLE001 - ANY verification failure is terminal
        print(f"VERIFY FAIL: SIGNATURE INVALID: {type(exc).__name__}", file=sys.stderr)
        return 6

    # 6: emit the receipt — closed key set, atomic, fsync'd
    receipt = {
        "record_type": RECEIPT_RECORD_TYPE,
        "version": "1.0",
        "record_status": "IMMUTABLE",
        "verification_exit_status": 0,
        "verification_tool_sha256": own_sha,
        "signing_key_id": trusted_key_id,
        "signature_algorithm": "ed25519",
        "canonical_signed_payload_sha256": claimed_payload_sha,
        "attestation_sha256": attestation_sha256,
        "verified_at": datetime.datetime.now(datetime.UTC).isoformat(timespec="seconds"),
        "run_nonce": run_nonce,
    }
    try:
        data = (json.dumps(receipt, indent=1, sort_keys=True) + "\n").encode("utf-8")
        receipt_sha256 = publish_immutable(args.receipt_out, data)
    except PublicationRefused as exc:
        print(f"VERIFY FAIL (receipt publication refused): {exc}", file=sys.stderr)
        return 7
    except OSError as exc:
        print(f"VERIFY FAIL (receipt not persisted): {exc}", file=sys.stderr)
        return 7
    print(json.dumps({"verified": True, "receipt_path": args.receipt_out,
                      "receipt_sha256": receipt_sha256,
                      "attestation_sha256": attestation_sha256, "run_nonce": run_nonce}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
