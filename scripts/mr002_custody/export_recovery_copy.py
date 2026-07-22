"""Export the P5-bound evaluator image to a self-contained OCI image-layout archive.

Authorized by the detection-package adjudication of 2026-07-22: External Offline
Recovery Copy. Detection can report that the bound image disappeared; it cannot
restore it. This produces the artifact that can.

The archive is built by walking the OCI graph directly from the registry and
verifying EVERY object against its own digest. Nothing is trusted from the local
Docker daemon, and no rebuild occurs anywhere: the binding is instance identity,
not bit-for-bit reproducibility.

Boundaries honored (see the adjudication):
  - does NOT modify the custody ECR repository (read-only API calls only)
  - does NOT implement Requirement 7 and is not an execution gate
  - does NOT enable S3 Object Lock, apply the proposed IAM role, or begin P6-P13
  - does NOT access validation, OOS, or sealed data
  - does NOT emit encryption keys, passphrases, serial numbers, or physical
    locations; media encryption and physical custody are OWNER actions performed
    after this script runs

Outputs: an OCI layout directory, a .tar archive of it, a machine-readable
inventory of every object, and a post-build verification verdict produced by
the same hardened verifier the custodian runs offline.
"""
import hashlib
import json
import re
import ssl
import sys
import tarfile
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

import boto3

REGION = "us-east-1"
REPOSITORY = "mr002-evaluator-p5"
INDEX = "sha256:60b15568aa5960ee04cf10b8c9b006d2ee702aa815a17384beffc979ed4554c9"
INDEX_MEDIA_TYPE = "application/vnd.oci.image.index.v1+json"


DIGEST_RE = re.compile(r"^sha256:[0-9a-f]{64}$")


def sha256_hex(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def validate_descriptor(desc, where, problems):
    """Strictly validate a REACHABLE OCI descriptor. Returns its digest, or None.

    A descriptor inside the reachable graph must be well-formed, not merely
    dict-shaped. Skipping malformed descriptors silently would let a structurally
    broken archive verify, since an unreachable-but-invalid object is caught by the
    unreferenced check while an unreachable-because-malformed one is not.

    Checks required type, digest syntax, media type, and size. Size-to-content
    agreement is checked later, once the blob is in hand.
    """
    if not isinstance(desc, dict):
        problems.append(f"malformed descriptor at {where}: not an object ({type(desc).__name__})")
        return None
    digest = desc.get("digest")
    if not isinstance(digest, str):
        problems.append(f"malformed descriptor at {where}: digest missing or not a string")
        return None
    if not DIGEST_RE.match(digest):
        problems.append(f"malformed descriptor at {where}: bad digest syntax {digest!r}")
        return None
    if not isinstance(desc.get("mediaType"), str) or not desc["mediaType"]:
        problems.append(f"malformed descriptor at {where}: mediaType missing or not a string")
        return None
    size = desc.get("size")
    if not isinstance(size, int) or isinstance(size, bool) or size < 0:
        problems.append(f"malformed descriptor at {where}: size missing or not a non-negative int")
        return None
    return digest


def _tls_context():
    """OS-trust-store TLS context for blob downloads (ADR 0017).

    The developer workstation runs Norton SSL inspection, whose MITM CA lives in the
    Windows trust store rather than Python's bundled certifi bundle. truststore reads
    the OS store, so verification stays FULLY ENABLED — this does not disable it.

    Scoped deliberately to this one connection rather than using
    truststore.inject_into_ssl(): the global monkeypatch collides with botocore's
    urllib3 context construction and recurses until the stack overflows.
    """
    try:
        import truststore

        return truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    except ImportError:  # pragma: no cover - environments without TLS interception
        return None


def fetch_manifest(ecr, digest: str) -> bytes:
    """Return manifest bytes, verified to hash to `digest`."""
    raw = ecr.batch_get_image(
        repositoryName=REPOSITORY, imageIds=[{"imageDigest": digest}]
    )["images"][0]["imageManifest"].encode()
    actual = sha256_hex(raw)
    if actual != digest:
        raise SystemExit(f"FATAL manifest digest mismatch: expected {digest} got {actual}")
    return raw


def fetch_blob(ecr, digest: str) -> bytes:
    """Return blob bytes, verified to hash to `digest`."""
    url = ecr.get_download_url_for_layer(
        repositoryName=REPOSITORY, layerDigest=digest
    )["downloadUrl"]
    with urllib.request.urlopen(  # noqa: S310 - AWS presigned HTTPS URL
        url, timeout=300, context=_tls_context()
    ) as resp:
        data = resp.read()
    actual = sha256_hex(data)
    if actual != digest:
        raise SystemExit(f"FATAL blob digest mismatch: expected {digest} got {actual}")
    return data


def walk_graph(ecr):
    """Collect every object reachable from the bound index, each digest-verified.

    Returns (objects, inventory) where objects maps digest -> bytes.
    """
    objects, inventory = {}, []

    index_bytes = fetch_manifest(ecr, INDEX)
    objects[INDEX] = index_bytes
    index = json.loads(index_bytes)
    if index.get("mediaType") != INDEX_MEDIA_TYPE:
        raise SystemExit(f"FATAL index media type: {index.get('mediaType')}")
    inventory.append({"digest": INDEX, "kind": "index", "role": "GOVERNING bound object",
                      "media_type": index["mediaType"], "size": len(index_bytes)})

    for desc in index.get("manifests", []):
        mdigest = desc["digest"]
        plat = desc.get("platform", {})
        platform = f"{plat.get('os')}/{plat.get('architecture')}"
        is_attestation = plat.get("os") == "unknown"
        mbytes = fetch_manifest(ecr, mdigest)
        objects[mdigest] = mbytes
        manifest = json.loads(mbytes)
        inventory.append({
            "digest": mdigest, "kind": "manifest", "platform": platform,
            "role": "attestation manifest" if is_attestation else "runtime image manifest",
            "media_type": manifest.get("mediaType"), "size": len(mbytes),
        })

        for kind, desc_list in (("config", [manifest.get("config")]),
                                ("layer", manifest.get("layers", []))):
            for blob_desc in desc_list:
                if not blob_desc:
                    continue
                bdigest = blob_desc["digest"]
                if bdigest in objects:
                    continue
                data = fetch_blob(ecr, bdigest)
                objects[bdigest] = data
                inventory.append({
                    "digest": bdigest, "kind": kind,
                    "media_type": blob_desc.get("mediaType"), "size": len(data),
                    "belongs_to": mdigest,
                })
                print(f"  + {kind:6s} {bdigest[:26]}... {len(data):>10,} bytes", flush=True)

    return objects, inventory


def write_oci_layout(root: Path, objects, index_bytes):
    """Write a standards-conformant OCI image layout."""
    blobs = root / "blobs" / "sha256"
    blobs.mkdir(parents=True, exist_ok=True)
    for digest, data in objects.items():
        (blobs / digest.split(":", 1)[1]).write_bytes(data)

    (root / "oci-layout").write_bytes(
        json.dumps({"imageLayoutVersion": "1.0.0"}).encode())
    (root / "index.json").write_bytes(json.dumps({
        "schemaVersion": 2,
        "mediaType": INDEX_MEDIA_TYPE,
        "manifests": [{
            "mediaType": INDEX_MEDIA_TYPE,
            "digest": INDEX,
            "size": len(index_bytes),
            "annotations": {
                "org.opencontainers.image.ref.name": "mr002-evaluator-p5:qualify-d1e7ffc",
                "com.globalcomplyai.mr002.binding": "P5 §4 governing execution binding",
            },
        }],
    }).encode())


def verify_archive(archive: Path, bound_index: str = INDEX, expected_outer: str | None = None):
    """Verify a recovery archive with NO network and NO AWS access.

    This is what the custodian runs against the removable medium at each review.
    It works on an air-gapped machine. It is NOT an execution gate and does not
    satisfy Requirement 7.

    Implements the custodian review procedure required by the recovery adjudication:
    wrapper hash, every blob PATHNAME checked against its content digest, complete
    reachability traversal from the bound index, rejection of unreferenced objects,
    exact match of the bound semantic digest, a nonzero object-count assertion, and
    explicit failure on missing, duplicated, malformed, or mistyped graph objects.

    A successful extraction is deliberately NOT sufficient to pass.
    """
    problems = []
    outer = "sha256:" + hashlib.sha256(archive.read_bytes()).hexdigest()
    if expected_outer and outer != expected_outer:
        problems.append(f"wrapper hash {outer} != expected {expected_outer}")

    blobs, layout_index, seen_names = {}, None, set()
    with tarfile.open(archive, "r") as tar:
        for member in tar.getmembers():
            if not member.isfile():
                continue
            data = tar.extractfile(member).read()
            # Normalize "./" and backslash forms; the leading-slash assumption is
            # exactly the defect that once made this verifier report an empty archive.
            normalized = member.name.replace("\\", "/")
            while normalized.startswith("./"):
                normalized = normalized[2:]
            normalized = normalized.lstrip("/")

            if normalized.startswith("blobs/sha256/"):
                name = normalized.split("/")[-1]
                actual = sha256_hex(data)
                # The PATHNAME must equal the content digest. Keying solely by the
                # computed hash would silently accept a misnamed blob.
                if actual != f"sha256:{name}":
                    problems.append(f"blob pathname/content mismatch: {normalized} holds {actual}")
                    continue
                if actual in blobs:
                    problems.append(f"duplicate blob object: {actual}")
                blobs[actual] = data
                seen_names.add(actual)
            elif Path(normalized).name == "index.json":
                try:
                    layout_index = json.loads(data)
                except ValueError as exc:
                    problems.append(f"index.json malformed: {exc}")

    top = None
    if layout_index is None:
        problems.append("index.json missing from archive")
    else:
        try:
            top = layout_index["manifests"][0]["digest"]
        except (KeyError, IndexError, TypeError) as exc:
            problems.append(f"index.json has no usable top-level descriptor: {exc}")
    if top is not None and top != bound_index:
        problems.append(f"top-level digest {top} != bound index {bound_index}")

    # (digest, declared_size, declared_media_type, provenance)
    referenced, queue = set(), [(top, None, None, "index.json")] if top else []
    config_blobs = set()
    while queue:
        digest, declared_size, declared_media, where = queue.pop()
        if digest in referenced:
            continue
        referenced.add(digest)
        if digest not in blobs:
            problems.append(f"referenced object absent or corrupt: {digest} (from {where})")
            continue

        data = blobs[digest]
        if declared_size is not None and len(data) != declared_size:
            problems.append(
                f"size disagreement for {digest} (from {where}): "
                f"declared {declared_size}, actual {len(data)}")

        # A config blob is a LEAF. Its top-level "config" key holds container
        # Env/Cmd and is NOT an OCI descriptor; walking it with manifest rules is
        # the type-confusion defect this guard exists to prevent.
        if digest in config_blobs:
            continue

        try:
            doc = json.loads(data)
        except (UnicodeDecodeError, ValueError):
            continue  # opaque layer blob; not a graph node
        if not isinstance(doc, dict):
            continue
        if declared_media and isinstance(doc.get("mediaType"), str) \
                and doc["mediaType"] != declared_media:
            problems.append(
                f"media type disagreement for {digest} (from {where}): "
                f"descriptor says {declared_media}, content says {doc['mediaType']}")

        for field in ("manifests", "layers"):
            entries = doc.get(field)
            if entries is None:
                continue
            if not isinstance(entries, list):
                problems.append(f"malformed {field} in {digest}: not a list")
                continue
            for i, desc in enumerate(entries):
                child = validate_descriptor(desc, f"{digest}.{field}[{i}]", problems)
                if child:
                    queue.append((child, desc["size"], desc["mediaType"], f"{digest}.{field}"))
        if "config" in doc:
            child = validate_descriptor(doc["config"], f"{digest}.config", problems)
            if child:
                config_blobs.add(child)
                queue.append((child, doc["config"]["size"], doc["config"]["mediaType"],
                              f"{digest}.config"))

    if not blobs:
        problems.append("archive contains no verifiable blob objects")
    unreferenced = sorted(set(blobs) - referenced)
    if unreferenced:
        problems.append(f"unreferenced unexpected objects: {unreferenced}")

    return {
        "archive": str(archive),
        "wrapper_digest": outer,
        "semantic_digest": top,
        "bound_identity_matches": top == bound_index,
        "objects_present": len(blobs),
        "present_digests": sorted(blobs),
        "objects_referenced": len(referenced),
        "unreferenced_objects": unreferenced,
        "problems": problems,
        "verdict": "PASS" if not problems else "FAIL",
        "offline": True,
        "satisfies_requirement_7": False,
    }


def verify_offline(archive: Path, expected_outer: str | None = None) -> int:
    result = verify_archive(archive, expected_outer=expected_outer)
    print(f"archive          : {result['archive']}")
    print(f"outer (wrapper)  : {result['wrapper_digest']}")
    print(f"inner (semantic) : {result['semantic_digest']}")
    print(f"objects present  : {result['objects_present']}   "
          f"referenced: {result['objects_referenced']}")
    print(f"bound identity   : {'MATCHES' if result['bound_identity_matches'] else 'DOES NOT MATCH'}")
    for problem in result["problems"]:
        print(f"  ! {problem}")
    print(f"VERDICT: {result['verdict']}  (offline; no network, no AWS; NOT an execution gate)")
    return 0 if result["verdict"] == "PASS" else 1


def main(staging: Path):
    now = datetime.now(timezone.utc)
    staging.mkdir(parents=True, exist_ok=True)
    layout = staging / "mr002-evaluator-p5-oci"
    archive = staging / "mr002-evaluator-p5-recovery.tar"

    print(f"Walking OCI graph from {REPOSITORY} ...", flush=True)
    ecr = boto3.client("ecr", region_name=REGION)
    objects, inventory = walk_graph(ecr)
    print(f"  {len(objects)} objects, all digest-verified", flush=True)

    write_oci_layout(layout, objects, objects[INDEX])

    # Deterministic packaging: zero the mtime/uid/gid/uname/gname that tar would
    # otherwise embed, so re-exporting the same objects reproduces the same outer
    # hash and the owner can independently re-verify the wrapper identity.
    #
    # This is packaging determinism over already-fixed bytes. It is NOT a build
    # reproducibility claim: the P5 binding remains instance identity, and the image
    # must never be rebuilt and assumed equivalent.
    def _deterministic(info: tarfile.TarInfo) -> tarfile.TarInfo:
        info.mtime = 0
        info.uid = info.gid = 0
        info.uname = info.gname = ""
        info.mode = 0o644
        return info

    with tarfile.open(archive, "w", format=tarfile.GNU_FORMAT) as tar:
        for path in sorted(layout.rglob("*")):
            if path.is_file():
                tar.add(path, arcname=str(path.relative_to(layout)).replace("\\", "/"),
                        filter=_deterministic)

    outer = hashlib.sha256(archive.read_bytes()).hexdigest()
    print(f"  archive {archive.name}  {archive.stat().st_size:,} bytes", flush=True)

    # The AUTHORITATIVE post-build gate is the same hardened verifier the custodian
    # runs against the medium — deliberately not a weaker build-time variant, so the
    # archive is never blessed by a check the custodian would not repeat.
    print("Post-build verification (hardened verifier, wrapper hash asserted) ...", flush=True)
    restore = verify_archive(archive, expected_outer=f"sha256:{outer}")
    print(f"  verdict: {restore['verdict']}", flush=True)

    # Additional signal the offline verifier cannot have: the archive's object set
    # must equal exactly what was downloaded and digest-verified from the registry.
    walked, packed = set(objects), set(restore["present_digests"])
    restore["cross_check_against_registry_walk"] = {
        "missing_from_archive": sorted(walked - packed),
        "not_downloaded_from_registry": sorted(packed - walked),
        "verdict": "PASS" if walked == packed else "FAIL",
    }
    if walked != packed:
        restore["verdict"] = "FAIL"
        restore["problems"].append("archive object set differs from the registry walk")
    print(f"  cross-check vs registry walk: "
          f"{restore['cross_check_against_registry_walk']['verdict']}", flush=True)

    manifest_record = {
        "record_type": "MR002_ExternalRecoveryCopy",
        "version": "1.0",
        "created_at": now.isoformat(),
        "scope": "external offline recovery copy of the P5-bound evaluator image; "
                 "NOT an execution gate, NOT a Requirement 7 resolver, authorizes nothing",
        "two_level_identity": {
            "semantic_identity_inner_oci_index": INDEX,
            "wrapper_identity_outer_archive_sha256": f"sha256:{outer}",
            "note": "the INNER index is the governing identity; the outer archive hash "
                    "identifies this particular packaging and is NOT the binding",
        },
        "archive": {
            "filename": archive.name,
            "format": "OCI image layout, GNU tar, uncompressed",
            "size_bytes": archive.stat().st_size,
            "object_count": len(objects),
            "self_contained": True,
        },
        "source": {
            "registry": f"219024422756.dkr.ecr.{REGION}.amazonaws.com/{REPOSITORY}",
            "retrieved_by": "digest, with every manifest and blob verified against its own "
                            "sha256 at download time",
            "rebuild_performed": False,
            "local_daemon_trusted": False,
        },
        "inventory": inventory,
        "post_build_verification": restore,
        # Truthful classification. The workstation archive is NOT promoted to
        # "offline" merely because it sits outside the cloud-sync root.
        "custody_classification": {
            "PRIMARY_CUSTODY_COPY": "ECR by immutable digest — "
                                    f"219024422756.dkr.ecr.{REGION}.amazonaws.com/{REPOSITORY}",
            "STAGED_ONLINE_RECOVERY_COPY": "this archive, on the routinely connected "
                                           "workstation, unencrypted",
            "INDEPENDENT_OFFLINE_RECOVERY_COPY": "NOT YET CREATED",
            "INFORMAL_RUNTIME_COPY": "local Docker cache — NOT CREDITED",
        },
        "boundaries": {
            "modified_custody_repository": False,
            "implements_requirement_7": False,
            "enabled_object_lock": False,
            "applied_proposed_iam_role": False,
            "accessed_validation_or_oos": False,
            "contains_secrets": False,
        },
        "owner_actions_still_required": [
            "encrypt the archive at rest on the destination medium",
            "write to genuinely independent removable media",
            "record media identifier, custodian, and review cadence in the custody record",
            "confirm the medium is normally disconnected",
            "confirm the staging copy is deleted or accepted as a second online copy",
        ],
    }
    (staging / "MR002_ExternalRecoveryCopy_v1.0.json").write_text(
        json.dumps(manifest_record, sort_keys=True, indent=2) + "\n",
        encoding="utf-8", newline="\n")

    print(f"\ninner (semantic) identity : {INDEX}")
    print(f"outer (wrapper) identity  : sha256:{outer}")
    return 0 if restore["verdict"] == "PASS" else 1


if __name__ == "__main__":
    default = Path("C:/LLM-RAG-APP/mr002_recovery_staging")
    if len(sys.argv) > 2 and sys.argv[1] == "--verify":
        expected = sys.argv[3] if len(sys.argv) > 3 else None
        sys.exit(verify_offline(Path(sys.argv[2]), expected_outer=expected))
    sys.exit(main(Path(sys.argv[1]) if len(sys.argv) > 1 else default))
