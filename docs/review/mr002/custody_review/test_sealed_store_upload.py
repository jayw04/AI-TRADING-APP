"""Tests for WP-D — the sealed-store upload.

The uploader has one job beyond copying bytes: never create a read event on a
sealed prefix. Everything else is digest discipline. Both are tested against a
stub S3 client, so nothing here touches AWS.
"""

from __future__ import annotations

import base64
import importlib.util
import json
import sys
from pathlib import Path

import pytest

MODULE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(MODULE_DIR))


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, MODULE_DIR / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


U = _load("sealed_store_upload")


class StubS3:
    """Records calls. Any read method is an attribute error, which is the point."""

    def __init__(self, *, corrupt=False, no_version=False):
        self.calls = []
        self._corrupt = corrupt
        self._no_version = no_version

    def put_object(self, **kwargs):
        self.calls.append(kwargs)
        checksum = kwargs["ChecksumSHA256"]
        if self._corrupt:
            checksum = base64.b64encode(b"\x00" * 32).decode("ascii")
        response = {"ChecksumSHA256": checksum}
        if not self._no_version:
            response["VersionId"] = "v-" + kwargs["Key"].replace("/", "-")
        return response


@pytest.fixture()
def staged(tmp_path):
    path = tmp_path / "validation" / "prices.parquet"
    path.parent.mkdir(parents=True)
    path.write_bytes(b"partition-bytes")
    return path


def _sha(path: Path) -> str:
    return U.sha256_file(str(path))


def test_upload_sends_the_expected_server_side_checksum(staged):
    client = StubS3()
    result = U.upload_object(client, "b", "validation/prices.parquet", staged, _sha(staged))
    sent = client.calls[0]
    assert sent["ChecksumAlgorithm"] == "SHA256"
    assert sent["ChecksumSHA256"] == base64.b64encode(bytes.fromhex(_sha(staged))).decode()
    assert result["server_validated"] is True
    assert result["version_id"]


def test_local_digest_drift_refuses_before_any_put(staged):
    """If the staged file no longer matches the verified export, uploading it would put
    unverified bytes behind the seal."""
    client = StubS3()
    with pytest.raises(U.UploadRefused) as exc:
        U.upload_object(client, "b", "validation/prices.parquet", staged, "f" * 64)
    assert "local_digest_drift" in str(exc.value)
    assert client.calls == []


def test_service_checksum_disagreement_refuses(staged):
    client = StubS3(corrupt=True)
    with pytest.raises(U.UploadRefused) as exc:
        U.upload_object(client, "b", "validation/prices.parquet", staged, _sha(staged))
    assert "service_checksum_mismatch" in str(exc.value)


def test_missing_version_id_refuses(staged):
    """Without a version the object cannot be pinned, so the seal cannot be re-verified."""
    client = StubS3(no_version=True)
    with pytest.raises(U.UploadRefused) as exc:
        U.upload_object(client, "b", "validation/prices.parquet", staged, _sha(staged))
    assert "no_version_id" in str(exc.value)


def test_upload_module_issues_no_read_call():
    """The P7 trap: one GetObject on the validation prefix before authorization would be
    permanent in CloudTrail."""
    source = (MODULE_DIR / "sealed_store_upload.py").read_text(encoding="utf-8")
    for forbidden in ("get_object", "head_object", "download_file", "download_fileobj",
                      "list_objects", "get_object_attributes"):
        assert f".{forbidden}(" not in source


def test_manifest_binds_the_export_and_p6_identities(staged, tmp_path):
    client = StubS3()
    export_manifest = {
        "record_type": "MR002_SealedStoreExportManifest",
        "manifest_identity_sha256": "a" * 64,
        "bound_p6_commitment_identity_sha256": "b" * 64,
        "objects": {"validation/prices.parquet": {"object_sha256": _sha(staged)}},
    }
    uploaded = U.upload_store(client, export_manifest, staged.parents[1], "bucket")
    manifest = U.build_manifest(
        uploaded, export_manifest, bucket="bucket", custodian="c", authority="a",
        produced_at="2026-08-11T00:00:00Z",
    )
    assert manifest["bound_export_manifest_identity_sha256"] == "a" * 64
    assert manifest["bound_p6_commitment_identity_sha256"] == "b" * 64
    assert manifest["every_object_server_validated"] is True
    assert manifest["cloudtrail_data_events_enabled_before_upload"] is True


def test_manifest_grants_nothing(staged):
    client = StubS3()
    export_manifest = {
        "record_type": "MR002_SealedStoreExportManifest",
        "manifest_identity_sha256": "a" * 64,
        "bound_p6_commitment_identity_sha256": "b" * 64,
        "objects": {"validation/prices.parquet": {"object_sha256": _sha(staged)}},
    }
    uploaded = U.upload_store(client, export_manifest, staged.parents[1], "bucket")
    manifest = U.build_manifest(
        uploaded, export_manifest, bucket="bucket", custodian="c", authority="a",
        produced_at="2026-08-11T00:00:00Z",
    )
    assert "validation_authorization remains false" in manifest["boundary"]
    assert "OOS remains under DENY" in manifest["boundary"]


def test_manifest_identity_changes_with_content(staged):
    client = StubS3()
    export_manifest = {
        "record_type": "MR002_SealedStoreExportManifest",
        "manifest_identity_sha256": "a" * 64,
        "bound_p6_commitment_identity_sha256": "b" * 64,
        "objects": {"validation/prices.parquet": {"object_sha256": _sha(staged)}},
    }
    uploaded = U.upload_store(client, export_manifest, staged.parents[1], "bucket")
    args = {"bucket": "bucket", "custodian": "c", "authority": "a",
            "produced_at": "2026-08-11T00:00:00Z"}
    first = U.build_manifest(uploaded, export_manifest, **args)
    mutated = json.loads(json.dumps(uploaded))
    mutated["validation/prices.parquet"]["version_id"] = "tampered"
    second = U.build_manifest(mutated, export_manifest, **args)
    assert first["manifest_identity_sha256"] != second["manifest_identity_sha256"]


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
