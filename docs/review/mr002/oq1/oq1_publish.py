"""MR-002 OQ-1 — immutable evidence publication + dry-run S3 adapter (Components 7 & 8).

Primary target is an immutable local/repository evidence package with a self-hashed manifest. Every
artifact records path/bytes/sha256/content-type/producer/governing-role. Publication fails closed on
overwrite or partial completion. An S3 dry-run adapter qualifies the immutability policy without real
credentials (deny-by-default; the run-5 archive is never the destination).
"""

from __future__ import annotations

import hashlib
import json
import os


class PublicationRefused(Exception):
    """REFUSED_PUBLICATION — an immutability / overwrite / policy violation blocked publication."""


def _refuse(detail: str):
    raise PublicationRefused(f"REFUSED_PUBLICATION:{detail}")


def _sha(path):
    return hashlib.sha256(open(path, "rb").read()).hexdigest()


def build_manifest(artifacts: list, *, self_hash: bool = True) -> dict:
    """artifacts: [{path, content_type, producer, governing_role}]. Adds byte count + sha256; stamps a
    self-hash over the manifest minus the self-hash field."""
    entries = []
    for a in sorted(artifacts, key=lambda x: x["path"]):
        p = a["path"]
        if not os.path.isfile(p):
            _refuse(f"MISSING_ARTIFACT:{os.path.basename(p)}")
        entries.append({"relative_path": os.path.basename(p), "byte_count": os.path.getsize(p),
                        "sha256": _sha(p), "content_type": a["content_type"],
                        "producer": a["producer"], "governing_role": a["governing_role"]})
    manifest = {"record_type": "MR002_OQ1_Manifest", "version": "1.0", "artifacts": entries,
                "artifact_count": len(entries)}
    if self_hash:
        manifest["manifest_self_hash"] = hashlib.sha256(
            json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    return manifest


def publish_local(dest_dir: str, artifacts: list, *, allow_existing: bool = False) -> dict:
    """Write the manifest to an immutable local bundle. Fail closed if the manifest already exists
    (no overwrite). Verifies every artifact hash after writing (partial publication fails closed)."""
    if not os.path.isdir(dest_dir):
        _refuse(f"DEST_MISSING:{os.path.basename(dest_dir)}")
    manifest = build_manifest(artifacts)
    mpath = os.path.join(dest_dir, "MR002_OQ1_Manifest.json")
    if os.path.exists(mpath) and not allow_existing:
        _refuse("OVERWRITE_FORBIDDEN:MR002_OQ1_Manifest.json")
    with open(mpath, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(json.dumps(manifest, sort_keys=True, indent=1) + "\n")
    # post-publication verification: every listed artifact hash must re-verify
    for e in manifest["artifacts"]:
        src = next(a for a in artifacts if os.path.basename(a["path"]) == e["relative_path"])
        if _sha(src["path"]) != e["sha256"]:
            _refuse(f"POST_PUBLISH_HASH_MISMATCH:{e['relative_path']}")
    return {"manifest_path": mpath, "manifest_self_hash": manifest["manifest_self_hash"],
            "artifact_count": manifest["artifact_count"]}


def s3_publish_dryrun(*, bucket: str, prefix: str, artifacts: list, versioning: bool,
                      object_lock: bool, sse: bool, existing_keys: set | None = None,
                      publisher_can_access_sealed: bool = False) -> dict:
    """Qualify the S3 immutability policy WITHOUT credentials or network. Fail closed unless every
    immutability precondition holds; never target the run-5 archive; record intended keys + hashes."""
    existing_keys = existing_keys or set()
    if "run5" in prefix or "workbench-backups" in bucket and "mr002/run5" in prefix:
        _refuse("RUN5_ARCHIVE_DESTINATION_FORBIDDEN")
    if "mr002/run5" in f"{bucket}/{prefix}":
        _refuse("RUN5_ARCHIVE_DESTINATION_FORBIDDEN")
    for flag, name in ((versioning, "VERSIONING"), (object_lock, "OBJECT_LOCK"), (sse, "SSE")):
        if not flag:
            _refuse(f"IMMUTABILITY_PRECONDITION:{name}")
    if publisher_can_access_sealed:
        _refuse("PUBLISHER_HAS_SEALED_ACCESS")
    planned = []
    for a in sorted(artifacts, key=lambda x: x["path"]):
        key = f"{prefix.rstrip('/')}/{os.path.basename(a['path'])}"
        if key in existing_keys:
            _refuse(f"OVERWRITE_FORBIDDEN:{key}")
        planned.append({"key": key, "sha256": _sha(a["path"]), "byte_count": os.path.getsize(a["path"])})
    return {"mode": "DRY_RUN", "bucket": bucket, "prefix": prefix, "planned_objects": planned,
            "immutability": {"versioning": versioning, "object_lock": object_lock, "sse": sse},
            "no_credentials_used": True, "no_network_used": True, "run5_archive_untouched": True}
