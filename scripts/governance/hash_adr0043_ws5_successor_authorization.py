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

EXPIRATION_RULE = "authorization_effective_at + 336 hours exactly"

#: Terms that must never appear in an expiration-rule field. Scoped to those fields
#: only: the historical reference to the PRIOR authorization's Chicago ceiling is
#: legitimate and must not false-positive.
EXPIRATION_FORBIDDEN = (
    "ending 23:59:59",
    "end of day",
    "calendar day",
    "calendar days",
    "America/Chicago",
)

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
    "utc_authoritative": r"UTC timestamps are authoritative",
    "no_end_of_day": r"No end-of-day rounding or extension is permitted",
    "withdrawal_state": r"OWNER_APPROVAL_WITHDRAWN_BEFORE_EFFECTIVENESS",
    "withdrawal_not_refusal": r"consumes refusal count\s*=\s*no",
    "two_withdrawal_review": r"two consecutive pre-effectiveness owner-approval withdrawals",
    "operator_cannot_choose_expiry": r"may not select, shorten, extend, round, or otherwise redefine",
    "owner_revocation_preserved": r"early revocation ends authority",
    "closure_first_event": r"closes at the first occurrence of any listed closure event",
    "closure_under_this_authorization": r"under this effective successor authorization",
    "ephemeral_not_closure": r"Prior ephemeral image-verification gates do not constitute a closure event",
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

    _check_expiration_statements(body)
    # Section 17 sits OUTSIDE sections 1-16, so it must be read from the full
    # document. Reading it from `body` silently no-opped this check.
    _check_stated_exclusions(text)


#: Excluded from the NORMATIVE body hash only because they are self-referential or
#: do not exist at freeze time. Everything else operational is bound by the
#: binding manifest (§4C) and by the body itself.
#:
#: The prior authorization also excluded ``runtime_name`` and ``database_identity``
#: because there they were derived-from-hash and named-after-creation respectively.
#: In the successor both are fixed known values, so excluding them would leave the
#: published identity not binding them. They are NOT excluded here.
NORMATIVE_EXCLUSIONS = ("authorization_sha", "expires_on")


def _check_expiration_statements(body: str) -> None:
    """Every expiration statement must be the exact-duration rule, and hashed.

    The prior rule was deterministic but granted up to ~24h beyond the intended
    336-hour maximum, so end-of-day and calendar-day forms are refused here.

    The rule must also be stated under a key that survives `apply_exclusions`.
    Exclusion is by key name, so a rule written as ``expires_on = ...`` inside
    sections 1-16 is blanked before hashing and the rule becomes unbound while
    the document still claims it is hashed. That defect was caught in review of
    the first cut of amendment-1; this refuses its reintroduction.
    """
    saw_hashed_rule = False
    for line in body.split("\n"):
        low = line.lower()
        is_expiry_field = (
            "expiration_rule" in low
            or "expires_on" in low
            or "absolute_expiration" in low
        )
        if not is_expiry_field:
            continue
        for bad in EXPIRATION_FORBIDDEN:
            if bad.lower() in low:
                raise ContractError(
                    f"expiration field contains forbidden term {bad!r}: {line.strip()!r}"
                )
        stated = re.match(r"^\s*expiration_rule\s*=\s*(.*?)\s*$", line)
        if stated:
            saw_hashed_rule = True
            if stated.group(1) != EXPIRATION_RULE:
                raise ContractError(
                    f"expiration_rule must be {EXPIRATION_RULE!r}, "
                    f"got {stated.group(1)!r}"
                )
        if re.match(r"^\s*expires_on\s*=", line) and re.search(
            r"\bhours?\b|\bdays?\b", low
        ):
            raise ContractError(
                "an expiration rule is stated under the excluded key 'expires_on', "
                "which is blanked before hashing; state it as 'expiration_rule' so "
                f"it is bound by the body hash: {line.strip()!r}"
            )
    if not saw_hashed_rule:
        raise ContractError(
            "sections 1-16 state no hashed 'expiration_rule'; the expiration rule "
            "must be bound by the body hash"
        )
    if "336 hours exactly" not in body:
        raise ContractError(
            "the exact-duration expiration rule (336 hours exactly) is absent"
        )


def _check_stated_exclusions(text: str) -> None:
    """The document's stated exclusions must equal the verifier's actual set.

    Finding 8 of the pre-effectiveness sweep: the document claimed
    database_identity was excluded while the verifier bound it. A document that
    contradicts its own enforcement mechanism is a defect even when the verifier
    is authoritative.
    """
    if "## 17." not in text:
        raise ContractError("section 17 (hash computation) is absent")
    section = text.split("## 17.", 1)[1].split("## 18.", 1)[0]
    for name in NORMATIVE_EXCLUSIONS:
        if name not in section:
            raise ContractError(f"section 17 does not state exclusion {name!r}")
    if "database_identity" in section and "not** excluded" not in section:
        raise ContractError(
            "section 17 still describes database_identity as excluded; it is bound by the manifest"
        )


def apply_exclusions(body: str) -> str:
    for key in NORMATIVE_EXCLUSIONS:
        body = re.sub(rf"(?m)^(\s*{re.escape(key)}\s*=\s*).*$", rf"\1{SENTINEL}", body)
    return body


def canonicalize(body: str) -> bytes:
    body = body.replace("\r\n", "\n").replace("\r", "\n")
    return (
        "\n".join(ln.rstrip() for ln in body.split("\n")).rstrip("\n").encode("utf-8")
    )


#: Every key the §4C manifest must define. Extraction is by key from the document;
#: a missing or duplicated key is a contract violation, never a silent skip.
BINDING_KEYS = (
    "document_id",
    "execution_mode",
    "prior_authorization_sha",
    "prior_disposition",
    "runtime_instance",
    "data_volume",
    "security_group",
    "iam_role",
    "instance_profile",
    "runtime_stack",
    "evidence_stack",
    "ecr_repository",
    "evidence_bucket",
    "runtime_name",
    "broker_account_id",
    "alpaca_account_id",
    "credential_key_fingerprint",
    "credential_secret_fingerprint",
    "credential_name_prefix",
    "authorized_source_commit",
    "source_archive_sha256",
    "source_object_version_id",
    "dockerfile_sha256",
    "image_manifest_digest",
    "image_index_digest",
    "image_config_digest",
    "platform",
    "evidence_directory",
    "database_identity",
    "reserved_database_path",
    "initial_database_state",
    "broker_access_mode",
    "strategy_execution_enabled",
    "scheduler_enabled",
    "alpaca_startup_enabled",
    "container_restart_policy",
    "permitted_endpoints",
    "expiration_rule",
    "effectiveness_precondition",
)


def extract_bindings(body: str) -> dict[str, str]:
    """Read every §4C binding value **from the document**.

    Extraction rather than assertion is the whole point: a hardcoded expectation
    proves the verifier's opinion, not the document's content. What is hashed is
    what the document says.
    """
    section = _section(body, "### 4C.")
    found: dict[str, str] = {}
    for key in BINDING_KEYS:
        matches = re.findall(rf"(?m)^{re.escape(key)}\s*=\s*(.+?)\s*$", section)
        if not matches:
            raise ContractError(f"binding manifest is missing required key {key!r}")
        if len(matches) > 1:
            raise ContractError(
                f"binding manifest defines {key!r} {len(matches)} times"
            )
        found[key] = matches[0]
    return found


def binding_manifest_bytes(bindings: dict[str, str]) -> bytes:
    """Deterministic, ordered serialization of the frozen bindings."""
    return "\n".join(f"{k}={bindings[k]}" for k in BINDING_KEYS).encode("utf-8")


def compute_identity(path: str | Path) -> dict[str, str]:
    """Return the three digests that together form the authorization identity."""
    text = Path(path).read_text(encoding="utf-8")
    body = extract_body(text)
    check_authorization_structure(text, body)
    bindings = extract_bindings(body)
    _check_binding_values(bindings)
    normative = hashlib.sha256(canonicalize(apply_exclusions(body))).hexdigest()
    manifest = hashlib.sha256(binding_manifest_bytes(bindings)).hexdigest()
    authorization = hashlib.sha256((normative + manifest).encode("utf-8")).hexdigest()
    return {
        "normative_body_sha256": normative,
        "binding_manifest_sha256": manifest,
        "authorization_sha256": authorization,
    }


def _check_binding_values(b: dict[str, str]) -> None:
    """Refuse a manifest whose values are wrong, in addition to hashing them."""
    expected = {
        "document_id": DOCUMENT_ID,
        "execution_mode": EXECUTION_MODE,
        "prior_authorization_sha": PRIOR_AUTHORIZATION_SHA,
        "prior_disposition": PRIOR_DISPOSITION,
        "broker_account_id": BROKER_ACCOUNT_ID,
        "alpaca_account_id": ALPACA_ACCOUNT_ID,
        "credential_key_fingerprint": CREDENTIAL_KEY_FP,
        "credential_secret_fingerprint": CREDENTIAL_SECRET_FP,
        "authorized_source_commit": SOURCE_COMMIT,
        "source_archive_sha256": SOURCE_ARCHIVE_SHA256,
        "source_object_version_id": SOURCE_OBJECT_VERSION_ID,
        "dockerfile_sha256": DOCKERFILE_SHA256,
        "image_manifest_digest": IMAGE_MANIFEST_DIGEST,
        "image_index_digest": IMAGE_INDEX_DIGEST,
        "platform": PLATFORM,
        "evidence_directory": EVIDENCE_DIR,
        "reserved_database_path": RESERVED_DB_PATH,
        "broker_access_mode": "read_only",
        "strategy_execution_enabled": "false",
        "scheduler_enabled": "false",
        "alpaca_startup_enabled": "false",
        "container_restart_policy": "no",
        "initial_database_state": "RESERVED_PATH_NOT_CREATED",
        "expiration_rule": EXPIRATION_RULE,
    }
    for key, want in expected.items():
        if b[key] != want:
            raise ContractError(f"binding {key}={b[key]!r} must be {want!r}")
    if b["image_manifest_digest"] == b["image_index_digest"]:
        raise ContractError("deployable manifest digest equals the index digest")
    if b["database_identity"] != f"{b['data_volume']} :: {b['reserved_database_path']}":
        raise ContractError(
            "database_identity is inconsistent with data_volume/reserved path"
        )
    if (
        not b["evidence_directory"].startswith("/var/lib/adr0043-ws5/")
        or b["evidence_directory"].rstrip("/") == "/var/lib/adr0043-ws5"
    ):
        raise ContractError(
            "evidence_directory must be a subdirectory, not the volume root"
        )


def compute_authorization(path: str | Path) -> str:
    return compute_identity(path)["authorization_sha256"]


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
            ids = compute_identity(args.document)
            for k in (
                "normative_body_sha256",
                "binding_manifest_sha256",
                "authorization_sha256",
            ):
                print(f"{k} = {ids[k]}")
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
