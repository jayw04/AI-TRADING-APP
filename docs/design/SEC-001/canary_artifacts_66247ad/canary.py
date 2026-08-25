"""SEC-001 V3 — Defect-F governed canary. ONE accession, ONE request.

Ruling 7C transition condition: F closes only if the governed canary demonstrates the
bound on the real ignored-Range 200 case, proving BOUNDED TRANSPORT CONSUMPTION rather
than a bounded artifact written after a full network read.
"""
import hashlib
import json
import os
import sys
import time

sys.path.insert(0, "/opt/epoch/code2/site")
sys.path.insert(0, "/opt/epoch/code2/apps/backend")

os.environ.setdefault("SEC_EDGAR_USER_AGENT", "GlobalComplyAI LLC jay.w0416@gmail.com")
os.environ.setdefault("SEC_EDGAR_RATE_LIMIT_PER_SEC", "1")

import httpcore  # noqa: E402
import httpx  # noqa: E402
from httpcore._sync.http11 import HTTP11Connection  # noqa: E402

from app.altdata.sec.client import EdgarClient  # noqa: E402
from app.altdata.sec001_v3 import policy  # noqa: E402
from app.altdata.sec001_v3.fetch import RecordingTransport  # noqa: E402

ACCESSION = "0000065984-14-000065"
URL = (
    "https://www.sec.gov/Archives/edgar/data/65984/"
    "000006598414000065/0000065984-14-000065.txt"
)
KNOWN_ENTITY_BYTES = 422_424_674
HEADER_CLOSE_OFFSET = 6_195
RANGE = policy.LEGACY_HEADER_RANGE  # bytes=0-4095

rec = RecordingTransport()
t0 = time.monotonic()
err = None
text = None
try:
    with EdgarClient(transport=rec) as client:
        text = client.get_text(
            URL,
            headers={
                "Range": RANGE,
                "Accept-Encoding": policy.RANGED_ACCEPT_ENCODING,  # identity
            },
        )
except Exception as exc:  # noqa: BLE001
    err = f"{type(exc).__name__}: {exc}"
elapsed = time.monotonic() - t0

cap = rec.last
out = {
    "canary": "SEC001_V3_DEFECT_F",
    "implementation_commit": "66247ad17f0e38a5f6c67ac11d74891b0e45fd3e",
    "accession": ACCESSION,
    "url": URL,
    "known_entity_bytes": KNOWN_ENTITY_BYTES,
    "sec_header_close_offset": HEADER_CLOSE_OFFSET,
    "request": {"Range": RANGE, "Accept-Encoding": policy.RANGED_ACCEPT_ENCODING},
    "dependencies": {
        "httpx": httpx.__version__,
        "httpcore": httpcore.__version__,
        "READ_NUM_BYTES": HTTP11Connection.READ_NUM_BYTES,
    },
    "policy": {
        "RESPONSE_CONSUMPTION_CEILING_BYTES": policy.RESPONSE_CONSUMPTION_CEILING_BYTES,
        "CONSUMPTION_STOP_THRESHOLD_BYTES": policy.CONSUMPTION_STOP_THRESHOLD_BYTES,
        "MAX_UPSTREAM_CHUNK_BYTES": policy.MAX_UPSTREAM_CHUNK_BYTES,
    },
    "gate5": {
        "TERMINAL_RESERVE_BYTES": policy.TERMINAL_RESERVE_BYTES,
        "PREARTIFACT_FREE_REQUIRED_BYTES": policy.PREARTIFACT_FREE_REQUIRED_BYTES,
    },
    "elapsed_seconds": round(elapsed, 3),
    "error": err,
}

if cap is not None:
    body_sha = hashlib.sha256(cap.body).hexdigest()
    out["observed"] = {
        "http_status": cap.status,
        "range_class": cap.range_class,
        "range_honored": cap.range_honored,
        "response_content_length": cap.response_content_length,
        "content_range": cap.content_range,
        "content_encoding": cap.content_encoding,
        "request_accept_encoding": cap.request_accept_encoding,
        "wire_bytes_consumed": cap.wire_bytes_consumed,
        "wire_consumed_sha256": cap.wire_consumed_sha256,
        "wire_truncated_at_ceiling": cap.wire_truncated_at_ceiling,
        "retained_body_bytes": len(cap.body),
        "retained_body_sha256": body_sha,
        "decode_ok": cap.decode_ok,
        "decode_error": cap.decode_error,
    }

    # ---- assertions -------------------------------------------------------------
    a = {}
    a["A_hard_ceiling"] = cap.wire_bytes_consumed <= policy.RESPONSE_CONSUMPTION_CEILING_BYTES
    a["B_far_below_entity"] = cap.wire_bytes_consumed < KNOWN_ENTITY_BYTES
    a["C_remainder_not_drained"] = (
        cap.wire_bytes_consumed < KNOWN_ENTITY_BYTES * 0.01
    )
    a["D_incremental_digest_binds_consumed"] = (
        cap.wire_consumed_sha256 == hashlib.sha256(cap.wire).hexdigest()
        and len(cap.wire) == cap.wire_bytes_consumed
    )
    a["E_explicit_classification"] = cap.range_class in (
        policy.RANGE_CLASS_200_IGNORED,
        policy.RANGE_CLASS_206_VALIDATED,
    )
    a["F_decode_ok"] = cap.decode_ok
    # Did we actually exercise the Defect-F condition?
    a["G_defect_f_condition_observed"] = (
        cap.status == 200 and cap.range_class == policy.RANGE_CLASS_200_IGNORED
    )
    # Was the decision reachable within what we consumed?
    a["H_sec_header_within_consumed"] = b"</SEC-HEADER>" in cap.body
    a["I_sic_present"] = b"STANDARD INDUSTRIAL CLASSIFICATION" in cap.body
    out["assertions"] = a

    core = all(v for k, v in a.items() if k != "G_defect_f_condition_observed")
    if not a["G_defect_f_condition_observed"]:
        out["verdict"] = "NON_DISPOSITIVE"
        out["verdict_reason"] = (
            "the server did not return the ignored-Range 200 condition; a valid 206 "
            "alone cannot close Defect F"
        )
    elif core:
        out["verdict"] = "PASS"
        out["verdict_reason"] = (
            "real ignored-Range 200 observed, classified explicitly, and actual wire "
            "consumption bounded within the governed ceiling"
        )
    else:
        out["verdict"] = "FAIL"
        out["verdict_reason"] = "one or more governed assertions failed"
else:
    out["verdict"] = "NON_DISPOSITIVE"
    out["verdict_reason"] = f"no capture recorded; error={err}"

print(json.dumps(out, indent=2, sort_keys=True))
with open("/opt/epoch/canary2_result.json", "w") as fh:
    json.dump(out, fh, indent=2, sort_keys=True)
