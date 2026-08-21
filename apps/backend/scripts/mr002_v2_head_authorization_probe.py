"""MR-002 — the LIVE half of gate 11: six metadata-only authorization probes.

Owner ruling 2026-08-21. Runs during an authorized latch cycle, AFTER credential acquisition and
BEFORE any content read. If all six succeed, the indivisible content-read sequence may begin. If
even one is denied or resolves unexpectedly, the caller restores the latch 7->8 immediately, seals
a PRE-READ failure, and does not launch the evaluation. Validation-2 stays UNCONSUMED either way.

WHY A HEAD IS A SUFFICIENT PROOF AND NOT A PROXY
    A pinned-version HeadObject and a pinned-version GetObject authorize under the SAME action,
    s3:GetObjectVersion, against the same resource ARN with the same s3:VersionId condition key.
    The probe therefore receives the EXACT authorization decision the content read would receive.
    It differs in one respect only: no body is transferred. That is what puts it on the safe side
    of the consumption boundary, and it is why the 2026-08-21 resource-policy defect would have
    been caught here.

WHY THIS IS NOT CONSUMPTION
    The program has always counted HeadObject as an ATTEMPT, never as exposure -- the seven denied
    HeadObject events in the pre-opening access history were counted exactly that way. Consumption
    is defined by the first successful VALIDATION CONTENT read. No content is requested here.

STRUCTURAL SAFETY, NOT A PROMISE
    The S3 client handed to the probe has every body-returning operation replaced by a raiser, so
    this file CANNOT read an object even if it were edited to try. `--network=none` is not
    available to it (it must reach S3), so the guard is the substitute for that safety.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time

sys.path.insert(0, "/work/apps/backend")

BUCKET = "workbench-mr002-sealed-219024422756"
READER_ROLE = "arn:aws:iam::219024422756:role/mr002-validation-reader"
SESSION_NAME = "mr002-v2-head-authorization-probe"
ZERO = "0" * 64
FORBIDDEN = ("get_object", "download_file", "download_fileobj", "copy", "copy_object",
             "select_object_content", "get_object_torrent")

# Registered key -> (VersionId, sha256-over-content, bytes). The sha256 is NOT verifiable here by
# construction: verifying it would require the content. It is carried so the record states what
# remains unverified rather than implying it was checked.
REGISTERED = {
    "oos/actions.parquet": ("F6m6am6cBahBd95p41C1.aAVmYd8GuNG",
                            "a08c0ed6ba6c6609e67c501a938e0245277e11c82f3d7242e7e2683790acb100",
                            57069),
    "oos/anchors.parquet": ("RsJZG3TkDXvNPERJhZVanJ.Vqg8_dulw",
                            "5095149d39d26c7af19de3814a7178e93bf3cc3ab87f92512991a81e64013dc9",
                            177252),
    "oos/etf_prices.parquet": ("Z3OsUeuucMYIl2v9JDoVNDx1nw.0avDj",
                               "f53f448312f94820d76aad80f378a53ea2b9104654cbb7c69bb82363b2a5da15",
                               67010),
    "oos/prices.parquet": ("1ope9PR._oR303.EbZNGPVlIJRy.SZbA",
                           "0f45ddc58170bd1131b9820576080eae861dff65b716bc3f03d08fb284f29e9a",
                           16173068),
    "oos/sic_observations.parquet": ("DPhtWW3Pca3TKtSa1LOnGKA.yrZ98EIt",
                                     "176a84bc155b5ec8c24444e091b19a78b97c0d31c0da606f22eca44"
                                     "ace7e12cf",
                                     138814),
    "oos/universe.parquet": ("0gaqJ9TuECc3U_zar99sqls2UHRDnkkY",
                             "4c1a2b2e876f7ffdd1f651e5c99079d5fe045e74003af556c3c8b3273d746e0d",
                             111278),
}


class ContentReadAttempted(RuntimeError):
    """The probe tried to obtain object content. It must not, and it cannot."""


class _MetadataOnlyClient:
    """Delegates head_object only. Every body-returning operation raises."""

    def __init__(self, inner):
        self._inner = inner

    def head_object(self, **kw):
        return self._inner.head_object(**kw)

    def __getattr__(self, name):
        if name in FORBIDDEN:
            raise ContentReadAttempted(
                "the metadata-only probe attempted %r. This probe runs BEFORE the consumption "
                "boundary and may never request content." % name)
        raise AttributeError(
            "the metadata-only probe exposes head_object only; %r is not available" % name)


def _journal(path, rows):
    prev = ZERO
    out = []
    for i, r in enumerate(rows, start=1):
        row = dict(r)
        row["sequence"] = i
        row["prev_hash"] = prev
        row["at_utc"] = row.get("at_utc") or time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        row["row_hash"] = hashlib.sha256(
            ("%s|%s|%s|%s" % (row["sequence"], row["kind"], row.get("object_id", ""), prev)
             ).encode()).hexdigest()
        prev = row["row_hash"]
        out.append(row)
    with open(path, "w", encoding="ascii", newline="\n") as fh:
        for row in out:
            fh.write(json.dumps(row, sort_keys=True) + "\n")
        fh.flush()
        os.fsync(fh.fileno())
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--latch-release-epoch", type=float, default=None)
    ap.add_argument("--journal", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    import boto3
    from app.research.mr002.phase3c.credential_readiness import acquire_reader_credentials

    rows = [{"kind": "probe_opened", "bucket": BUCKET, "objects_declared": len(REGISTERED),
             "content_reads_possible": False,
             "purpose": "live authorization decision only, no body"}]

    creds, readiness = acquire_reader_credentials(
        boto3.client("sts"), READER_ROLE, SESSION_NAME,
        latch_release_epoch=args.latch_release_epoch)
    caller = boto3.client(
        "sts", aws_access_key_id=creds["AccessKeyId"],
        aws_secret_access_key=creds["SecretAccessKey"],
        aws_session_token=creds["SessionToken"]).get_caller_identity()["Arn"]

    s3 = _MetadataOnlyClient(boto3.client(
        "s3", aws_access_key_id=creds["AccessKeyId"],
        aws_secret_access_key=creds["SecretAccessKey"],
        aws_session_token=creds["SessionToken"]))

    results, ok = [], 0
    for key in sorted(REGISTERED):
        vid, sha, size = REGISTERED[key]
        rows.append({"kind": "head_intent", "object_id": key, "version_id": vid})
        try:
            r = s3.head_object(Bucket=BUCKET, Key=key, VersionId=vid)
        except Exception as exc:                          # noqa: BLE001 — a denial is a RESULT
            code = getattr(exc, "response", {}).get("Error", {}).get("Code", type(exc).__name__)
            results.append({"key": key, "version_id": vid, "authorized": False, "error": code,
                            "detail": str(exc)[:240]})
            rows.append({"kind": "head_denied", "object_id": key, "version_id": vid,
                         "error": code})
            continue
        echoed = r.get("VersionId")
        length = r.get("ContentLength")
        # metadata-only identity corroboration. It is NOT the sha256 commitment, and is never
        # presented as one — the content hash remains unverified until the governed read.
        agrees = (echoed == vid) and (length == size)
        results.append({"key": key, "version_id": vid, "authorized": True,
                        "version_id_echoed": echoed, "content_length": length,
                        "registered_bytes": size, "metadata_agrees": agrees,
                        "sha256_registered": sha, "sha256_verified": False})
        rows.append({"kind": "head_authorized", "object_id": key, "version_id": vid,
                     "metadata_agrees": agrees})
        if agrees:
            ok += 1

    all_ok = ok == len(REGISTERED)
    rows.append({"kind": "terminal",
                 "disposition": "AUTHORIZED" if all_ok else "REFUSED",
                 "authorized_objects": ok, "declared_objects": len(REGISTERED),
                 "content_reads": 0})
    jrows = _journal(args.journal, rows)

    report = {
        "record_type": "MR002_Validation2_HeadAuthorizationProbe",
        "version": "1.0",
        "gate": "gate 11, live half",
        "bucket": BUCKET,
        "reader_caller_identity": caller,
        "credential_readiness": readiness,
        "objects": results,
        "authorized_objects": ok,
        "declared_objects": len(REGISTERED),
        "content_reads": 0,
        "read_verified_rows": 0,
        "body_bytes_transferred": 0,
        "sha256_commitments_verified": False,
        "sha256_note": "the six content commitments CANNOT be verified by a metadata-only probe "
                       "and were not. They are verified by the governed read, inside the "
                       "indivisible sequence, after this gate passes.",
        "journal_rows": len(jrows),
        "journal_chain_head": jrows[-1]["row_hash"],
        "verdict": "AUTHORIZED — the content-read sequence may begin" if all_ok
                   else "REFUSED — restore the latch, seal a PRE-READ failure, do not launch",
        "consumption": "NONE. Validation-2 remains UNCONSUMED; no content was requested.",
    }
    with open(args.out, "w", encoding="ascii", newline="\n") as fh:
        fh.write(json.dumps(report, sort_keys=True, indent=1, ensure_ascii=True) + "\n")

    print(json.dumps({"verdict": report["verdict"], "authorized": ok,
                      "declared": len(REGISTERED), "content_reads": 0}, indent=1))
    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())
