#!/usr/bin/env python3
"""ADR-0043 D-BOX freeze-manifest readiness gate and body-hash verifier.

Governed path: ``apps/backend/scripts/adr0043_dbox_freeze_manifest.py``

Operations (local / isolated harness; never submits broker orders)::

    python apps/backend/scripts/adr0043_dbox_freeze_manifest.py check \\
        --manifest path/to/freeze_manifest.json

    python apps/backend/scripts/adr0043_dbox_freeze_manifest.py body-hash \\
        --manifest path/to/freeze_manifest.json

    python apps/backend/scripts/adr0043_dbox_freeze_manifest.py verify-seal \\
        --manifest path/to/sealed_freeze_manifest.json

Canonicalization: RFC 8785 JSON Canonicalization Scheme (JCS), UTF-8 no BOM,
final newline excluded. Hash algorithm: SHA-256 over the canonical
``manifest_body`` only (the ``seal`` envelope is not hashed).

Exit codes: 0 = ready / verify ok; 1 = not ready or verify fail; 2 = usage/IO error.

Does not import OrderRouter, broker adapters, or live order-path modules.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any

PLACEHOLDER_RE = re.compile(
    r"(?i)\b(REQUIRED_FILL|TBD|TODO|FIXME|FILL_ME|CHANGEME|LOCAL_UNPUBLISHED|"
    r"PENDING_[A-Z0-9_]+|ISOLATED_HARNESS_REQUIRED|PENDING_FROM_ISOLATED_CHECKOUT|"
    r"PENDING_JULY24_FROZEN_DIGEST_LOOKUP|PENDING_ISOLATED_ENV_PIN|"
    r"PENDING_CLEAN_CHECKOUT_AT_SEAL|PENDING_BIND_BEFORE_SEAL)\b"
)
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
UTC_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")

LOAD_BEARING = ("CORR-06", "O1", "O2", "O3", "O4-A", "O4-B", "O5")

CANONICALIZATION = "RFC8785-JCS"
HASH_ALGORITHM = "sha256"
ENCODING = "UTF-8-no-BOM"
FINAL_NEWLINE = "excluded"


# --- RFC 8785 JCS (subset: no IEEE floats; integers only as JSON numbers) ---


def _jcs_escape(s: str) -> str:
    out: list[str] = ['"']
    for ch in s:
        o = ord(ch)
        if ch == '"':
            out.append('\\"')
        elif ch == "\\":
            out.append("\\\\")
        elif ch == "\b":
            out.append("\\b")
        elif ch == "\f":
            out.append("\\f")
        elif ch == "\n":
            out.append("\\n")
        elif ch == "\r":
            out.append("\\r")
        elif ch == "\t":
            out.append("\\t")
        elif o < 0x20:
            out.append(f"\\u{o:04x}")
        else:
            out.append(ch)
    out.append('"')
    return "".join(out)


def _jcs_encode(value: Any) -> str:
    if value is None:
        return "null"
    if value is True:
        return "true"
    if value is False:
        return "false"
    if isinstance(value, bool):  # pragma: no cover
        return "true" if value else "false"
    if isinstance(value, int) and not isinstance(value, bool):
        return str(value)
    if isinstance(value, float):
        raise ValueError(
            "RFC8785-JCS seal body must not contain IEEE floats; use strings"
        )
    if isinstance(value, str):
        return _jcs_escape(value)
    if isinstance(value, list):
        return "[" + ",".join(_jcs_encode(v) for v in value) + "]"
    if isinstance(value, dict):
        items = sorted(value.items(), key=lambda kv: kv[0].encode("utf-16-be"))
        inner = ",".join(
            f"{_jcs_escape(k)}:{_jcs_encode(v)}" for k, v in items
        )
        return "{" + inner + "}"
    raise TypeError(f"unsupported JSON type for JCS: {type(value)!r}")


def canonical_manifest_body_bytes(body: dict[str, Any]) -> bytes:
    return _jcs_encode(body).encode("utf-8")


def body_sha256(body: dict[str, Any]) -> str:
    return hashlib.sha256(canonical_manifest_body_bytes(body)).hexdigest()


def _walk_strings(obj: Any, path: str = "$") -> list[tuple[str, str]]:
    found: list[tuple[str, str]] = []
    if isinstance(obj, str):
        found.append((path, obj))
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            found.extend(_walk_strings(v, f"{path}[{i}]"))
    elif isinstance(obj, dict):
        for k, v in obj.items():
            found.extend(_walk_strings(v, f"{path}.{k}"))
    return found


def readiness_check(doc: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if "manifest_body" not in doc or "seal" not in doc:
        return ["missing manifest_body or seal envelope"]

    body = doc["manifest_body"]
    seal = doc["seal"]

    if not isinstance(body, dict) or not isinstance(seal, dict):
        return ["manifest_body and seal must be objects"]

    for path, s in _walk_strings(body):
        if PLACEHOLDER_RE.search(s):
            errors.append(f"placeholder string at {path}: {s[:80]!r}")

    def walk_nulls(obj: Any, path: str = "$") -> None:
        if obj is None:
            if path.startswith("$.seal."):
                return
            errors.append(f"prohibited null at {path}")
            return
        if isinstance(obj, list):
            for i, v in enumerate(obj):
                walk_nulls(v, f"{path}[{i}]")
        elif isinstance(obj, dict):
            for k, v in obj.items():
                walk_nulls(v, f"{path}.{k}")

    walk_nulls(body, "$.manifest_body")

    anchors = (
        body.get("o5_live_fill_anchors", {}).get("anchors")
        if isinstance(body.get("o5_live_fill_anchors"), dict)
        else None
    )
    if anchors is None:
        errors.append("missing o5_live_fill_anchors.anchors")
    elif not isinstance(anchors, list):
        errors.append("o5_live_fill_anchors.anchors must be an array")
    else:
        for i, a in enumerate(anchors):
            if not isinstance(a, dict):
                errors.append(f"anchor[{i}] must be object")
                continue
            if a.get("anchor_id") in (None, "") or (
                isinstance(a.get("anchor_id"), str)
                and PLACEHOLDER_RE.search(a["anchor_id"])
            ):
                errors.append(
                    f"placeholder/synthetic O5 anchor at anchors[{i}] — "
                    "use [] if none"
                )
            if a.get("sha256") is not None and not SHA256_RE.match(
                str(a["sha256"])
            ):
                errors.append(f"anchors[{i}].sha256 malformed SHA-256")

    reads = (
        body.get("permitted_broker_reads", {}).get("operations")
        if isinstance(body.get("permitted_broker_reads"), dict)
        else None
    )
    if reads is None:
        errors.append("missing permitted_broker_reads.operations")
    elif not isinstance(reads, list):
        errors.append("permitted_broker_reads.operations must be an array")
    else:
        for i, op in enumerate(reads):
            if not isinstance(op, dict):
                errors.append(f"broker read[{i}] must be object")
                continue
            proof = op.get("side_effect_free_proof")
            if not proof or (
                isinstance(proof, str) and PLACEHOLDER_RE.search(proof)
            ):
                errors.append(
                    f"broker read[{i}] missing side-effect-free proof"
                )

    datasets = body.get("datasets", {}).get("entries")
    if not isinstance(datasets, list) or len(datasets) < 1:
        errors.append("datasets.entries must be a non-empty array")
    else:
        for i, ds in enumerate(datasets):
            if not isinstance(ds, dict):
                errors.append(f"datasets.entries[{i}] must be object")
                continue
            loc = ds.get("storage")
            if loc == "s3":
                if not ds.get("s3_version_id") or not SHA256_RE.match(
                    str(ds.get("sha256", ""))
                ):
                    errors.append(
                        f"datasets.entries[{i}] S3 requires version_id + sha256"
                    )
                if str(ds.get("s3_version_id", "")).lower() in {
                    "latest",
                    "",
                }:
                    errors.append(
                        f"datasets.entries[{i}] unversioned/latest S3 forbidden"
                    )
            elif loc == "local_sealed":
                for req in ("path", "size_bytes", "sha256", "sealed_archive_id"):
                    if ds.get(req) in (None, ""):
                        errors.append(
                            f"datasets.entries[{i}] local_sealed missing {req}"
                        )
                if ds.get("sha256") and not SHA256_RE.match(str(ds["sha256"])):
                    errors.append(f"datasets.entries[{i}] malformed sha256")
            else:
                errors.append(
                    f"datasets.entries[{i}].storage must be 's3' or 'local_sealed'"
                )

    writes = body.get("permitted_writes", {}).get("operations")
    if not isinstance(writes, list):
        errors.append("permitted_writes.operations must be an array")
    else:
        for i, w in enumerate(writes):
            if not isinstance(w, dict):
                continue
            targets = w.get("targets")
            if w.get("kind") in {
                "account_3_test_state",
                "account_3_checkpoint",
            } and (not isinstance(targets, list) or len(targets) < 1):
                errors.append(
                    f"permitted_writes.operations[{i}] requires non-empty targets[]"
                )

    gp = body.get("gate_packages", {})
    criteria = gp.get("pass_criteria") if isinstance(gp, dict) else None
    if not isinstance(criteria, dict):
        errors.append("gate_packages.pass_criteria missing")
    else:
        for gate in LOAD_BEARING:
            c = criteria.get(gate)
            if not isinstance(c, dict):
                errors.append(f"pass_criteria.{gate} must be structured object")
                continue
            for req in (
                "required_inputs",
                "protocol_ids",
                "required_checks",
                "maximum_failures",
                "inconclusive_conditions",
                "required_artifacts",
                "evaluator_version",
                "adjudicator_role",
                "reruns_allowed",
                "failed_attempt_preservation",
            ):
                if req not in c:
                    errors.append(f"pass_criteria.{gate} missing {req}")
            for list_key in (
                "required_inputs",
                "protocol_ids",
                "required_checks",
                "required_artifacts",
            ):
                val = c.get(list_key)
                if isinstance(val, list):
                    if list_key != "required_inputs" and len(val) < 1:
                        errors.append(
                            f"pass_criteria.{gate}.{list_key} empty"
                        )
                    for item in val:
                        if isinstance(item, str) and PLACEHOLDER_RE.search(item):
                            errors.append(
                                f"pass_criteria.{gate}.{list_key} placeholder"
                            )
            if gate in {"O4-A", "O4-B"}:
                for req in ("observation_set_id", "replay_boundary"):
                    v = c.get(req)
                    if v is None or v == "" or (
                        isinstance(v, str) and PLACEHOLDER_RE.search(v)
                    ):
                        errors.append(
                            f"pass_criteria.{gate} missing bound {req}"
                        )
            if gate == "O5":
                for req in (
                    "clopper_pearson_confidence",
                    "clopper_pearson_acceptance_bound",
                ):
                    v = c.get(req)
                    if not v or (
                        isinstance(v, str) and PLACEHOLDER_RE.search(v)
                    ):
                        errors.append(f"pass_criteria.O5 missing {req}")

    sb = body.get("schema_binding")
    if not isinstance(sb, dict):
        errors.append("schema_binding missing")
    else:
        for req in ("path", "commit", "sha256"):
            if not sb.get(req) or (
                isinstance(sb.get(req), str)
                and PLACEHOLDER_RE.search(str(sb[req]))
            ):
                errors.append(f"schema_binding.{req} incomplete")
        if sb.get("sha256") and not SHA256_RE.match(str(sb["sha256"])):
            errors.append("schema_binding.sha256 malformed")

    tools = body.get("code_and_tools", {})
    vs = (
        tools.get("freeze_manifest_validator")
        if isinstance(tools, dict)
        else None
    )
    if not isinstance(vs, dict):
        errors.append("code_and_tools.freeze_manifest_validator missing")
    else:
        for req in ("path", "commit", "sha256"):
            if not vs.get(req) or (
                isinstance(vs.get(req), str)
                and PLACEHOLDER_RE.search(str(vs[req]))
            ):
                errors.append(
                    f"code_and_tools.freeze_manifest_validator.{req} incomplete"
                )

    status = seal.get("manifest_status")
    if status == "SEALED":
        if not seal.get("body_sha256") or not SHA256_RE.match(
            str(seal["body_sha256"])
        ):
            errors.append("SEALED requires seal.body_sha256")
        if not seal.get("sealed_at_utc") or not UTC_RE.match(
            str(seal["sealed_at_utc"])
        ):
            errors.append("SEALED requires seal.sealed_at_utc RFC3339Z")
        expected = body_sha256(body)
        if seal.get("body_sha256") != expected:
            errors.append(
                f"body_sha256 mismatch: seal has {seal.get('body_sha256')}, "
                f"recomputed {expected}"
            )

    return errors


def load_manifest(path: Path) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8")
    if text.startswith("\ufeff"):
        raise ValueError("manifest must be UTF-8 without BOM")
    return json.loads(text)


def cmd_check(path: Path) -> int:
    try:
        doc = load_manifest(path)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    errs = readiness_check(doc)
    report = {
        "manifest": str(path),
        "ready_to_seal": len(errs) == 0,
        "error_count": len(errs),
        "errors": errs,
        "canonicalization": CANONICALIZATION,
        "hash_algorithm": HASH_ALGORITHM,
        "encoding": ENCODING,
        "final_newline": FINAL_NEWLINE,
        "recomputed_body_sha256": body_sha256(doc["manifest_body"])
        if "manifest_body" in doc
        else None,
    }
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if not errs else 1


def cmd_body_hash(path: Path) -> int:
    try:
        doc = load_manifest(path)
        h = body_sha256(doc["manifest_body"])
    except (OSError, ValueError, json.JSONDecodeError, KeyError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    print(h)
    return 0


def cmd_verify_seal(path: Path) -> int:
    try:
        doc = load_manifest(path)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    seal = doc.get("seal") or {}
    if seal.get("manifest_status") != "SEALED":
        print("ERROR: manifest_status is not SEALED", file=sys.stderr)
        return 1
    errs = readiness_check(doc)
    if errs:
        print(json.dumps({"ok": False, "errors": errs}, indent=2))
        return 1
    print(
        json.dumps(
            {
                "ok": True,
                "body_sha256": seal.get("body_sha256"),
                "sealed_at_utc": seal.get("sealed_at_utc"),
                "canonicalization": CANONICALIZATION,
            },
            indent=2,
        )
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest="cmd", required=True)
    for name in ("check", "body-hash", "verify-seal"):
        sp = sub.add_parser(name)
        sp.add_argument("--manifest", type=Path, required=True)
    args = p.parse_args(argv)
    if args.cmd == "check":
        return cmd_check(args.manifest)
    if args.cmd == "body-hash":
        return cmd_body_hash(args.manifest)
    if args.cmd == "verify-seal":
        return cmd_verify_seal(args.manifest)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
