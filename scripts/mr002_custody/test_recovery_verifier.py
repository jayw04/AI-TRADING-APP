"""Regression tests for the MR-002 recovery-archive verifier.

The recovery adjudication requires explicit regression tests for the two verifier
defects disclosed during development, because both were false-assurance risks
rather than incidental bugs:

  1. ARCHIVE PATH-NORMALIZATION — a verifier checking the wrong path namespace
     found nothing, and with weaker assertions would have accepted an empty result.
  2. DESCRIPTOR TYPE-CONFUSION — not every JSON object with a "config" key is an
     OCI graph node. Configuration blobs must not be walked using manifest/index
     rules.

The remaining tests cover the custodian review procedure: a successful extraction
must NOT be sufficient to pass.

No AWS access, no network, no real archive required — every case is synthesized.
"""
import hashlib
import importlib
import importlib.util
import json
import pathlib
import sys
import tarfile

import pytest

from export_recovery_copy import INDEX_MEDIA_TYPE, verify_archive


def digest_of(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def build_archive(tmp_path, blobs, index_doc, *, prefix="", extra=None):
    """Pack blobs into an OCI-layout tar. `blobs` maps digest -> bytes."""
    archive = tmp_path / "recovery.tar"
    layout = tmp_path / "layout"
    (layout / "blobs" / "sha256").mkdir(parents=True, exist_ok=True)
    for digest, data in blobs.items():
        (layout / "blobs" / "sha256" / digest.split(":", 1)[1]).write_bytes(data)
    (layout / "oci-layout").write_bytes(json.dumps({"imageLayoutVersion": "1.0.0"}).encode())
    (layout / "index.json").write_bytes(json.dumps(index_doc).encode())
    for name, data in (extra or {}).items():
        (layout / name).write_bytes(data)

    with tarfile.open(archive, "w") as tar:
        for path in sorted(layout.rglob("*")):
            if path.is_file():
                arc = prefix + str(path.relative_to(layout)).replace("\\", "/")
                tar.add(path, arcname=arc)
    return archive


@pytest.fixture
def graph():
    """A minimal but realistic index -> manifest -> {config, layer} graph.

    The config blob deliberately carries its own top-level "config" key, exactly
    as a real OCI image configuration does.
    """
    layer = b"\x1f\x8b\x08 not-really-gzip but opaque bytes"
    config = json.dumps({
        "architecture": "amd64", "os": "linux",
        "config": {"Env": ["PATH=/usr/bin"], "Cmd": ["/bin/sh"]},  # NOT a descriptor
        "rootfs": {"type": "layers", "diff_ids": [digest_of(layer)]},
    }).encode()
    manifest = json.dumps({
        "schemaVersion": 2,
        "mediaType": "application/vnd.oci.image.manifest.v1+json",
        "config": {"mediaType": "application/vnd.oci.image.config.v1+json",
                   "digest": digest_of(config), "size": len(config)},
        "layers": [{"mediaType": "application/vnd.oci.image.layer.v1.tar+gzip",
                    "digest": digest_of(layer), "size": len(layer)}],
    }).encode()
    index = json.dumps({
        "schemaVersion": 2, "mediaType": INDEX_MEDIA_TYPE,
        "manifests": [{"mediaType": "application/vnd.oci.image.manifest.v1+json",
                       "digest": digest_of(manifest), "size": len(manifest),
                       "platform": {"os": "linux", "architecture": "amd64"}}],
    }).encode()
    blobs = {digest_of(index): index, digest_of(manifest): manifest,
             digest_of(config): config, digest_of(layer): layer}
    return blobs, digest_of(index), {
        "schemaVersion": 2, "mediaType": INDEX_MEDIA_TYPE,
        "manifests": [{"mediaType": INDEX_MEDIA_TYPE, "digest": digest_of(index),
                       "size": len(index)}],
    }


def test_healthy_archive_passes(tmp_path, graph):
    blobs, top, index_doc = graph
    result = verify_archive(build_archive(tmp_path, blobs, index_doc), bound_index=top)
    assert result["verdict"] == "PASS", result["problems"]
    assert result["objects_present"] == 4
    assert result["objects_referenced"] == 4


# --- REGRESSION: defect 1, archive path normalization ------------------------

@pytest.mark.parametrize("prefix", ["", "./"])
def test_regression_path_normalization_variants(tmp_path, graph, prefix):
    """Relative and './'-prefixed arcnames must both be recognized.

    The original defect required a LEADING SLASH, matched nothing, and reported
    every object missing.
    """
    blobs, top, index_doc = graph
    result = verify_archive(
        build_archive(tmp_path, blobs, index_doc, prefix=prefix), bound_index=top)
    assert result["verdict"] == "PASS", result["problems"]
    assert result["objects_present"] == 4


def test_regression_empty_archive_never_passes(tmp_path, graph):
    """The false-assurance case: nothing found must FAIL, never vacuously pass."""
    _, top, index_doc = graph
    result = verify_archive(build_archive(tmp_path, {}, index_doc), bound_index=top)
    assert result["verdict"] == "FAIL"
    assert any("no verifiable blob objects" in p for p in result["problems"])


# --- REGRESSION: defect 2, descriptor type confusion -------------------------

def test_regression_config_blob_is_not_walked_as_a_descriptor_graph(tmp_path, graph):
    """An image config's "config" key (Env/Cmd) must not be followed as a node.

    The original defect raised KeyError: 'digest' on exactly this shape.
    """
    blobs, top, index_doc = graph
    result = verify_archive(build_archive(tmp_path, blobs, index_doc), bound_index=top)
    assert result["verdict"] == "PASS", result["problems"]


def test_regression_malformed_descriptor_inside_reachable_graph_is_rejected(tmp_path, graph):
    """Malformed descriptors must be rejected ON THEIR OWN MERITS.

    The earlier version of this test passed only because the junk object was
    UNREFERENCED — the unreferenced-object check caught it, while a malformed
    descriptor inside the reachable graph would have been silently skipped. Here the
    manifest itself is rewritten so the bad descriptors are genuinely reachable.
    """
    blobs, _, _ = graph
    layer = next(v for v in blobs.values() if not v.startswith(b"{"))
    config = next(v for v in blobs.values()
                  if v.startswith(b"{") and b"rootfs" in v)
    bad_manifest = json.dumps({
        "schemaVersion": 2,
        "mediaType": "application/vnd.oci.image.manifest.v1+json",
        "config": {"mediaType": "application/vnd.oci.image.config.v1+json",
                   "digest": digest_of(config), "size": len(config)},
        "layers": [
            {"digest": digest_of(layer), "size": len(layer)},          # no mediaType
            {"mediaType": "x", "digest": "not-a-digest", "size": 1},   # bad digest syntax
            {"mediaType": "x", "digest": digest_of(layer)},            # no size
            "a string",                                                # not an object
        ],
    }).encode()
    index = json.dumps({
        "schemaVersion": 2, "mediaType": INDEX_MEDIA_TYPE,
        "manifests": [{"mediaType": "application/vnd.oci.image.manifest.v1+json",
                       "digest": digest_of(bad_manifest), "size": len(bad_manifest)}],
    }).encode()
    packed = {digest_of(index): index, digest_of(bad_manifest): bad_manifest,
              digest_of(config): config, digest_of(layer): layer}
    index_doc = {"schemaVersion": 2, "mediaType": INDEX_MEDIA_TYPE,
                 "manifests": [{"mediaType": INDEX_MEDIA_TYPE, "digest": digest_of(index),
                                "size": len(index)}]}

    result = verify_archive(build_archive(tmp_path, packed, index_doc),
                            bound_index=digest_of(index))
    assert result["verdict"] == "FAIL"
    malformed = [p for p in result["problems"] if "malformed descriptor" in p]
    assert len(malformed) == 4, result["problems"]
    assert any("mediaType missing" in p for p in malformed)
    assert any("bad digest syntax" in p for p in malformed)
    assert any("size missing" in p for p in malformed)
    assert any("not an object" in p for p in malformed)


def test_size_to_content_disagreement_is_rejected(tmp_path, graph):
    """A descriptor whose declared size contradicts the blob must fail."""
    blobs, _, _ = graph
    layer = next(v for v in blobs.values() if not v.startswith(b"{"))
    config = next(v for v in blobs.values() if v.startswith(b"{") and b"rootfs" in v)
    manifest = json.dumps({
        "schemaVersion": 2,
        "mediaType": "application/vnd.oci.image.manifest.v1+json",
        "config": {"mediaType": "application/vnd.oci.image.config.v1+json",
                   "digest": digest_of(config), "size": len(config)},
        "layers": [{"mediaType": "application/vnd.oci.image.layer.v1.tar+gzip",
                    "digest": digest_of(layer), "size": len(layer) + 999}],
    }).encode()
    index = json.dumps({
        "schemaVersion": 2, "mediaType": INDEX_MEDIA_TYPE,
        "manifests": [{"mediaType": "application/vnd.oci.image.manifest.v1+json",
                       "digest": digest_of(manifest), "size": len(manifest)}],
    }).encode()
    packed = {digest_of(index): index, digest_of(manifest): manifest,
              digest_of(config): config, digest_of(layer): layer}
    index_doc = {"schemaVersion": 2, "mediaType": INDEX_MEDIA_TYPE,
                 "manifests": [{"mediaType": INDEX_MEDIA_TYPE, "digest": digest_of(index),
                                "size": len(index)}]}
    result = verify_archive(build_archive(tmp_path, packed, index_doc),
                            bound_index=digest_of(index))
    assert result["verdict"] == "FAIL"
    assert any("size disagreement" in p for p in result["problems"])


def test_media_type_disagreement_is_rejected(tmp_path, graph):
    """Descriptor mediaType must agree with the content's own mediaType."""
    blobs, top, _ = graph
    manifest_digest = next(
        d for d, v in blobs.items()
        if v.startswith(b"{") and b'"layers"' in v)
    manifest = blobs[manifest_digest]
    index = json.dumps({
        "schemaVersion": 2, "mediaType": INDEX_MEDIA_TYPE,
        "manifests": [{"mediaType": INDEX_MEDIA_TYPE,  # wrong: content says manifest
                       "digest": manifest_digest, "size": len(manifest)}],
    }).encode()
    packed = {d: v for d, v in blobs.items() if d != top}
    packed[digest_of(index)] = index
    index_doc = {"schemaVersion": 2, "mediaType": INDEX_MEDIA_TYPE,
                 "manifests": [{"mediaType": INDEX_MEDIA_TYPE, "digest": digest_of(index),
                                "size": len(index)}]}
    result = verify_archive(build_archive(tmp_path, packed, index_doc),
                            bound_index=digest_of(index))
    assert result["verdict"] == "FAIL"
    assert any("media type disagreement" in p for p in result["problems"])


# --- custodian review procedure ----------------------------------------------

def test_misnamed_blob_is_rejected(tmp_path, graph):
    """Pathname must equal content digest; keying only by content would hide this."""
    blobs, top, index_doc = graph
    layer_digest = next(d for d, v in blobs.items() if not v.startswith(b"{"))
    corrupted = dict(blobs)
    corrupted["sha256:" + "ff" * 32] = corrupted.pop(layer_digest)
    result = verify_archive(build_archive(tmp_path, corrupted, index_doc), bound_index=top)
    assert result["verdict"] == "FAIL"
    assert any("pathname/content mismatch" in p for p in result["problems"])


def test_unreferenced_object_is_rejected(tmp_path, graph):
    blobs, top, index_doc = graph
    extra = b"an object nothing points at"
    result = verify_archive(
        build_archive(tmp_path, {**blobs, digest_of(extra): extra}, index_doc),
        bound_index=top)
    assert result["verdict"] == "FAIL"
    assert any("unreferenced" in p for p in result["problems"])


def test_missing_referenced_object_is_rejected(tmp_path, graph):
    blobs, top, index_doc = graph
    layer_digest = next(d for d, v in blobs.items() if not v.startswith(b"{"))
    pruned = {d: v for d, v in blobs.items() if d != layer_digest}
    result = verify_archive(build_archive(tmp_path, pruned, index_doc), bound_index=top)
    assert result["verdict"] == "FAIL"
    assert any("absent or corrupt" in p for p in result["problems"])


def test_wrong_bound_identity_is_rejected(tmp_path, graph):
    """An otherwise-perfect archive of the WRONG image must fail."""
    blobs, top, index_doc = graph
    result = verify_archive(build_archive(tmp_path, blobs, index_doc),
                            bound_index="sha256:" + "ab" * 32)
    assert result["verdict"] == "FAIL"
    assert not result["bound_identity_matches"]
    assert any("!= bound index" in p for p in result["problems"])


def test_wrapper_hash_mismatch_is_rejected(tmp_path, graph):
    blobs, top, index_doc = graph
    archive = build_archive(tmp_path, blobs, index_doc)
    result = verify_archive(archive, bound_index=top,
                            expected_outer="sha256:" + "cd" * 32)
    assert result["verdict"] == "FAIL"
    assert any("wrapper hash" in p for p in result["problems"])


def test_missing_index_json_is_rejected(tmp_path, graph):
    blobs, top, _ = graph
    archive = tmp_path / "noindex.tar"
    with tarfile.open(archive, "w") as tar:
        for digest, data in blobs.items():
            path = tmp_path / digest.split(":", 1)[1]
            path.write_bytes(data)
            tar.add(path, arcname=f"blobs/sha256/{digest.split(':', 1)[1]}")
    result = verify_archive(archive, bound_index=top)
    assert result["verdict"] == "FAIL"
    assert any("index.json missing" in p for p in result["problems"])


def test_verifier_never_claims_to_satisfy_requirement_7(tmp_path, graph):
    blobs, top, index_doc = graph
    result = verify_archive(build_archive(tmp_path, blobs, index_doc), bound_index=top)
    assert result["satisfies_requirement_7"] is False
    assert result["offline"] is True


class _BlockAWSSDK:
    """Meta-path finder that makes the AWS SDK unimportable, as on an air-gapped box."""

    BLOCKED = ("boto3", "botocore")

    def find_module(self, fullname, path=None):  # pragma: no cover - legacy protocol
        return None

    def find_spec(self, fullname, path=None, target=None):
        if fullname.split(".")[0] in self.BLOCKED:
            raise ModuleNotFoundError(f"No module named {fullname!r}", name=fullname)
        return None


def test_offline_verification_does_not_require_the_aws_sdk(tmp_path, graph):
    """The custodian's air-gapped review must not depend on boto3 being installed.

    Invariant 4 of the recovery submission says the offline verifier never requires
    registry access. A module-scope `import boto3` violated that in spirit and in
    fact: on a genuinely clean machine the --verify path failed at IMPORT, before
    any verification logic ran, so the one procedure the custodian performs against
    the medium was unavailable exactly where it is most needed.

    This reimports the module from source with the SDK blocked and runs a full
    verification through it, so the guarantee holds even in an environment where
    boto3 happens to be installed.
    """
    blobs, top, index_doc = graph
    archive = build_archive(tmp_path, blobs, index_doc)

    source = pathlib.Path(__file__).resolve().parent / "export_recovery_copy.py"
    blocker = _BlockAWSSDK()
    sys.meta_path.insert(0, blocker)
    saved = {name: sys.modules.pop(name) for name in list(sys.modules)
             if name.split(".")[0] in _BlockAWSSDK.BLOCKED}
    try:
        with pytest.raises(ModuleNotFoundError):
            importlib.import_module("boto3")

        spec = importlib.util.spec_from_file_location("_export_recovery_copy_no_aws", source)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)  # would raise if boto3 were imported at module scope

        result = module.verify_archive(archive, bound_index=top)
    finally:
        sys.meta_path.remove(blocker)
        sys.modules.update(saved)

    assert result["verdict"] == "PASS"
    assert result["offline"] is True


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
