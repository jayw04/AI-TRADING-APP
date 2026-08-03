"""Structural contract and verifier for the ADR 0043 WS5 **successor** authorization.

Two modes, because two different artifacts need independent verification:

``authorization``
    Validates the successor authorization document's structure and reproduces
    its canonical body SHA-256.

``stage-c-evidence``
    Validates a Stage-C reconciliation artifact together with the process
    outcome observed alongside it.

Why a second verifier at all. ``hash_ws5_authorization.py`` encodes the
*obsolete* two-stage §15 contract (it requires ``### 15.1``/``### 15.2`` and
exactly two fenced operator-record blocks). The successor uses a Stage A-D
model, so reusing that verifier would either force the wrong shape or require
loosening it until it stopped proving anything.

Why evidence validation lives here. Exit code 2 is emitted both by ``argparse``
and by a governed ``REFUSED``. Classifying Stage C from the exit code alone is
therefore unsound, and a rule that lives only in prose is a rule nothing
enforces. This mode makes the exit-code / artifact-presence / disposition
triple a command with an exit status.

Digest terminology, frozen:

``artifact_sha256``
    SHA-256 of the canonical JSON record **before** the ``artifact_sha256``
    field is inserted. This is the runner's existing internal field name; it is
    deliberately NOT renamed, because a rename would require a source change, a
    new image and a new deployable digest for a cosmetic gain.

``evidence_file_sha256``
    SHA-256 of the complete serialized evidence file, supplied externally.

Usage::

    python hash_adr0043_ws5_successor_authorization.py authorization --document <path>
    python hash_adr0043_ws5_successor_authorization.py stage-c-evidence \\
        --artifact <path> --exit-code <n> --evidence-file-sha256 <hex>
    python hash_adr0043_ws5_successor_authorization.py selftest
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

SENTINEL = "<EXCLUDED>"

DOCUMENT_ID = "ADR0043-LIVE-CANARY-WS5-SUCCESSOR-START-001"
EXECUTION_MODE = "ADOPT-CLEAN-UNUSED-RESOURCES"

# --- frozen bindings the document must carry verbatim ------------------------
PRIOR_AUTHORIZATION_SHA = (
    "52b3ff136196e90f0a4d85b92a7280fd19355da64348958fa28706c274ac47ae"
)
PRIOR_DISPOSITION = "REFUSED"
SOURCE_COMMIT = "1880fcdb05e367306e81fa96b355b996f73b7819"
SOURCE_ARCHIVE_SHA256 = (
    "17d24c3ead5ee00029b63b6d8df89cf8122bf078cc227efe6fe539d41731dd7c"
)
SOURCE_OBJECT_VERSION_ID = "dEDhokQBpFY8u9AyF7KM0aHX1wDnEEpu"
DOCKERFILE_SHA256 = "e4ee353aed8abdce98e8ac7881b928dcbb9c30ab1abef04dea0e261ae6be9042"
IMAGE_MANIFEST_DIGEST = (
    "sha256:c0c1b0c48fbb4d4318207f589ee9a64ee795ca34100028bfd84d4d9d81c6a54d"
)
IMAGE_INDEX_DIGEST = (
    "sha256:59f3f26123ca0c19174fefc06575f960bb2c50c555c9eba23b0aaeb22f78071d"
)
BROKER_ACCOUNT_ID = "PA3E97RWHKQZ"
ALPACA_ACCOUNT_ID = "0fa55b0d-74d6-4a61-a361-ab154857cfb5"
CREDENTIAL_KEY_FP = "ffab8796516a"
CREDENTIAL_SECRET_FP = "c2cab6509f1b"
PLATFORM = "linux/arm64"

EVIDENCE_DIR = "/var/lib/adr0043-ws5/evidence"
RESERVED_DB_PATH = "/var/lib/adr0043-ws5/workbench.sqlite"

#: Every resource adopted from the refused attempt, named individually.
ADOPTED_RESOURCES = (
    "i-0fff7076ad461aa9a",
    "vol-0710769fb6981102d",
    "sg-08b1284b33d9159c4",
    "adr0043-canary-ws5-52b3ff136196-role",
    "adr0043-canary-ws5-52b3ff136196-profile",
    "adr0043-canary-ws5-52b3ff136196",
    "adr0043-canary-ws5-52b3ff136196-evidence",
    "adr0043-ws5-evidence-219024422756-us-east-1",
)

STAGE_HEADINGS = ("### Stage A", "### Stage B", "### Stage C", "### Stage D")

#: Clauses whose *absence* has previously produced a governance failure. Each is
#: matched case-insensitively against the hashed body.
REQUIRED_CLAUSES = {
    "prior_refusal_continuity": r"does not amend, cure, reopen, extend or erase",
    "deployable_digest_authoritative": r"only\s+`?sha256:c0c1b0c4[0-9a-f]*`?[^\n]*(deployable|authoritative)",
    "index_not_deployable": r"image index[^\n]*(not|never)[^\n]*(deploy|authoritative)",
    "replacement_checkpoint_closes": r"replacement (is )?closed",
    "regression_allowed": r"return to Stage B",
    "regression_forbidden": r"(account mismatch|credential mismatch)[^\n]*(REFUSED|not eligible)",
    "clock_disclosure": r"does not restart, extend or amend the prior authorization clock",
    "anti_laundering": r"two consecutive REFUSED",
    "evidence_mount": re.escape(EVIDENCE_DIR),
    "no_volume_root_mount": r"volume root (is )?(not|never) mounted",
    "reserved_db_uncreated": r"RESERVED_PATH_NOT_CREATED",
    "stage_c_override": r"python -m app\.brokers\.adr0043_reconcile",
    "default_cmd_never_runs": r"default (image )?`?Cmd`?[^\n]*(never|must not)",
}

# --- Stage-C evidence contract ----------------------------------------------
EVIDENCE_SCHEMA_VERSION = "adr0043-ws5-stage-c/1.0"
DISPOSITION_EXIT = {"READY": 0, "REFUSED": 2, "INCONCLUSIVE": 3}
APPROVED_CALL_ORDER = [
    "GET /v2/account",
    "GET /v2/positions",
    "GET /v2/orders",
    "GET /v2/account/activities",
]
EVIDENCE_REQUIRED_FIELDS = (
    "schema_version",
    "run_id",
    "started_at_utc",
    "completed_at_utc",
    "source_commit",
    "image_manifest_digest",
    "expected_account_id",
    "returned_account_id",
    "credential_key_fingerprint",
    "credential_secret_fingerprint",
    "broker_access_mode",
    "approved_calls_in_order",
    "positions_count",
    "orders_count",
    "activities_count",
    "transport_dispatch_count",
    "mutation_attempt_count",
    "authoritative_start_a_baseline",
    "terminal_disposition",
    "failure_code",
    "artifact_sha256",
)

_HEX40 = re.compile(r"^[0-9a-f]{40}$")
_DIGEST = re.compile(r"^sha256:[0-9a-f]{64}$")
_HEX64 = re.compile(r"^[0-9a-f]{64}$")


class ContractError(ValueError):
    """The artifact does not satisfy the successor contract."""


# ---------------------------------------------------------------------------
# authorization mode
# ---------------------------------------------------------------------------


def extract_body(text: str) -> str:
    """Sections 1-16: from '## 1.' up to (excluding) '## 17.'."""
    lines = text.splitlines()
    try:
        start = next(i for i, ln in enumerate(lines) if ln.startswith("## 1."))
        end = next(i for i, ln in enumerate(lines) if ln.startswith("## 17."))
    except StopIteration:
        raise ContractError(
            "document must contain '## 1.' and '## 17.' headings"
        ) from None
    if end <= start:
        raise ContractError("'## 17.' precedes '## 1.'")
    return "\n".join(lines[start:end])


def _section(body: str, heading: str) -> str:
    lines = body.split("\n")
    start = next((i for i, ln in enumerate(lines) if ln.startswith(heading)), None)
    if start is None:
        raise ContractError(f"required section {heading!r} is absent")
    end = next(
        (i for i, ln in enumerate(lines) if i > start and ln.startswith("## ")),
        len(lines),
    )
    return "\n".join(lines[start:end])


def check_authorization_structure(text: str, body: str) -> None:
    """Fail closed on any deviation from the successor contract."""
    if DOCUMENT_ID not in text:
        raise ContractError(f"document_id {DOCUMENT_ID!r} absent")
    if EXECUTION_MODE not in body:
        raise ContractError(
            f"execution_mode {EXECUTION_MODE!r} absent from the hashed body"
        )

    for label, value in (
        ("prior_authorization_sha", PRIOR_AUTHORIZATION_SHA),
        ("authorized_source_commit", SOURCE_COMMIT),
        ("source_archive_sha256", SOURCE_ARCHIVE_SHA256),
        ("source_object_version_id", SOURCE_OBJECT_VERSION_ID),
        ("Dockerfile_sha256", DOCKERFILE_SHA256),
        ("image_manifest_digest", IMAGE_MANIFEST_DIGEST),
        ("image_index_digest", IMAGE_INDEX_DIGEST),
        ("broker_account_id", BROKER_ACCOUNT_ID),
        ("alpaca_account_id", ALPACA_ACCOUNT_ID),
        ("credential_key_fingerprint", CREDENTIAL_KEY_FP),
        ("credential_secret_fingerprint", CREDENTIAL_SECRET_FP),
        ("platform", PLATFORM),
        ("reserved_database_path", RESERVED_DB_PATH),
    ):
        if value not in body:
            raise ContractError(
                f"required binding {label}={value!r} absent from the hashed body"
            )

    if PRIOR_DISPOSITION not in body:
        raise ContractError("prior terminal disposition REFUSED must be stated")

    stages = _section(body, "## 15.")
    for h in STAGE_HEADINGS:
        if h not in stages:
            raise ContractError(f"stage model incomplete: {h!r} absent from §15")

    for name in ADOPTED_RESOURCES:
        if name not in body:
            raise ContractError(f"adopted resource {name!r} is not named individually")

    for label, pattern in REQUIRED_CLAUSES.items():
        if not re.search(pattern, body, re.IGNORECASE):
            raise ContractError(f"required clause missing: {label}")

    # The index digest must never be described as deployable.
    for m in re.finditer(r"[^\n]*" + re.escape(IMAGE_INDEX_DIGEST) + r"[^\n]*", body):
        line = m.group(0)
        if re.search(r"\bdeployable\b", line, re.I) and not re.search(
            r"not\b", line, re.I
        ):
            raise ContractError("image index digest is described as deployable")


def apply_exclusions(body: str) -> str:
    for key in ("runtime_name", "authorization_sha", "expires_on", "database_identity"):
        body = re.sub(rf"(?m)^(\s*{re.escape(key)}\s*=\s*).*$", rf"\1{SENTINEL}", body)
    return body


def canonicalize(body: str) -> bytes:
    body = body.replace("\r\n", "\n").replace("\r", "\n")
    return (
        "\n".join(ln.rstrip() for ln in body.split("\n")).rstrip("\n").encode("utf-8")
    )


def compute_authorization(path: str | Path) -> str:
    text = Path(path).read_text(encoding="utf-8")
    body = extract_body(text)
    check_authorization_structure(text, body)
    return hashlib.sha256(canonicalize(apply_exclusions(body))).hexdigest()


# ---------------------------------------------------------------------------
# stage-c-evidence mode
# ---------------------------------------------------------------------------


def record_body_sha256(record: dict) -> str:
    """Reproduce ``artifact_sha256``: the record hashed BEFORE that field exists."""
    without = {k: v for k, v in record.items() if k != "artifact_sha256"}
    body = json.dumps(without, indent=2, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(body.encode("utf-8")).hexdigest()


def check_stage_c_evidence(
    record: dict, *, exit_code: int, evidence_file_sha256: str
) -> None:
    """Validate a Stage-C artifact and the outcome observed alongside it."""
    if record.get("schema_version") != EVIDENCE_SCHEMA_VERSION:
        raise ContractError(f"schema_version must be {EVIDENCE_SCHEMA_VERSION!r}")
    missing = [f for f in EVIDENCE_REQUIRED_FIELDS if f not in record]
    if missing:
        raise ContractError(f"missing required evidence fields: {missing}")

    disp = record["terminal_disposition"]
    if disp not in DISPOSITION_EXIT:
        raise ContractError(f"unknown terminal_disposition {disp!r}")
    if exit_code != DISPOSITION_EXIT[disp]:
        raise ContractError(
            f"exit code {exit_code} is inconsistent with disposition {disp} "
            f"(expected {DISPOSITION_EXIT[disp]})"
        )

    if not _HEX40.match(str(record["source_commit"])):
        raise ContractError("source_commit is not 40 lowercase hex characters")
    if not _DIGEST.match(str(record["image_manifest_digest"])):
        raise ContractError("image_manifest_digest is not sha256:<64 hex>")
    if record["image_manifest_digest"] == IMAGE_INDEX_DIGEST:
        raise ContractError(
            "evidence binds the image INDEX digest, not the deployable manifest"
        )

    if record.get("authoritative_start_a_baseline") is not False:
        raise ContractError("authoritative_start_a_baseline must be false")
    if record.get("mutation_attempt_count") != 0:
        raise ContractError(
            f"mutation_attempt_count must be 0, got {record.get('mutation_attempt_count')!r}"
        )

    calls = record.get("approved_calls_in_order") or []
    if calls != APPROVED_CALL_ORDER[: len(calls)]:
        raise ContractError(
            f"approved_calls_in_order deviates from the approved order: {calls}"
        )
    dispatches = record.get("transport_dispatch_count")

    if disp == "READY":
        if calls != APPROVED_CALL_ORDER:
            raise ContractError("READY requires all four approved reads, in order")
        if dispatches != 4:
            raise ContractError(
                f"READY requires exactly 4 dispatches, got {dispatches}"
            )
    elif disp == "REFUSED":
        code = str(record.get("failure_code") or "")
        if "account_identity_mismatch" in code and dispatches != 1:
            raise ContractError(
                f"an identity-mismatch REFUSED must dispatch exactly once, got {dispatches}"
            )
        if (
            code.startswith(
                ("provenance_binding", "unsafe_runtime_posture", "missing_")
            )
            and dispatches != 0
        ):
            raise ContractError(
                f"a pre-dispatch REFUSED must dispatch 0 times, got {dispatches}"
            )

    if not record.get("credential_key_fingerprint") and dispatches not in (0, None):
        raise ContractError("dispatches occurred without a credential fingerprint")

    expected_body = record_body_sha256(record)
    if record.get("artifact_sha256") != expected_body:
        raise ContractError(
            f"record-body digest mismatch: artifact_sha256={record.get('artifact_sha256')} "
            f"recomputed={expected_body}"
        )
    if not _HEX64.match(evidence_file_sha256 or ""):
        raise ContractError("evidence_file_sha256 must be 64 lowercase hex characters")


def verify_evidence_file(
    path: str | Path, *, exit_code: int, evidence_file_sha256: str
) -> dict:
    raw = Path(path).read_bytes()
    actual = hashlib.sha256(raw).hexdigest()
    if actual != (evidence_file_sha256 or "").lower():
        raise ContractError(
            f"evidence file digest mismatch: supplied {evidence_file_sha256}, actual {actual}"
        )
    record = json.loads(raw.decode("utf-8"))
    check_stage_c_evidence(record, exit_code=exit_code, evidence_file_sha256=actual)
    return record


# ---------------------------------------------------------------------------

_FIXTURES = Path(__file__).with_name("fixtures") / "adr0043_ws5_successor"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="mode", required=True)

    a = sub.add_parser("authorization")
    a.add_argument("--document", required=True)

    e = sub.add_parser("stage-c-evidence")
    e.add_argument("--artifact", required=True)
    e.add_argument("--exit-code", type=int, required=True)
    e.add_argument("--evidence-file-sha256", required=True)

    sub.add_parser("selftest")
    args = ap.parse_args(argv)

    try:
        if args.mode == "authorization":
            print(compute_authorization(args.document))
        elif args.mode == "stage-c-evidence":
            rec = verify_evidence_file(
                args.artifact,
                exit_code=args.exit_code,
                evidence_file_sha256=args.evidence_file_sha256.lower(),
            )
            print(f"VALID {rec['terminal_disposition']} run_id={rec['run_id']}")
        else:
            doc = _FIXTURES / "valid_authorization.md"
            print(f"authorization fixture: {compute_authorization(doc)}")
    except ContractError as exc:
        print(f"CONTRACT VIOLATION: {exc}", file=sys.stderr)
        return 3
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
