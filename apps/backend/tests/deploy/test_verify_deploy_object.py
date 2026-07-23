"""ADR-0043 deploy object verifier — checksum/size/marker enforcement, both directions.

The hardened validation-box provisioner calls this before it extracts or swaps anything, so every
failure mode must be caught here: wrong bytes, wrong sha, wrong deployed commit, wrong ADR-0043
implementation, governed-paths-match not true, and a missing/malformed marker. The approved object
passes; anything else is refused.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[4]
GUARD = REPO_ROOT / "deploy" / "aws" / "verify_deploy_object.py"
_spec = importlib.util.spec_from_file_location("verify_deploy_object", GUARD)
mod = importlib.util.module_from_spec(_spec)
assert _spec and _spec.loader
sys.modules["verify_deploy_object"] = mod
_spec.loader.exec_module(mod)

DEPLOYED = "b0058bf335628f8dbde09a93915314f3a1f7743b"
IMPL = "ea6db6e6d5dc338196ffca9919a7a2e2643e1f6c"


def _obj(tmp_path: Path, body: bytes) -> tuple[Path, str, int]:
    p = tmp_path / "code.tgz"
    p.write_bytes(body)
    return p, hashlib.sha256(body).hexdigest(), len(body)


# ---------------------------------------------------------------------------- download identity


def test_download_matching_sha_and_bytes_passes(tmp_path):
    p, sha, n = _obj(tmp_path, b"the approved artifact bytes")
    assert mod.verify_download(p, sha, n) == []


def test_download_wrong_sha_is_refused(tmp_path):
    p, sha, n = _obj(tmp_path, b"approved")
    v = mod.verify_download(p, "0" * 64, n)
    assert v and "sha256" in v[0]


def test_download_wrong_bytes_is_refused(tmp_path):
    p, sha, n = _obj(tmp_path, b"approved")
    v = mod.verify_download(p, sha, n + 1)
    assert any("byte size" in x for x in v)


def test_download_truncated_body_is_refused(tmp_path):
    """A wrong VersionId or truncated download yields different bytes AND sha — both caught."""
    p, sha, n = _obj(tmp_path, b"approved-full-body")
    p.write_bytes(b"approved")  # shorter, different content
    v = mod.verify_download(p, sha, n)
    assert any("byte size" in x for x in v) and any("sha256" in x for x in v)


def test_download_missing_file_is_refused(tmp_path):
    v = mod.verify_download(tmp_path / "nope.tgz", "0" * 64, 1)
    assert v and "not found" in v[0]


def test_sha_is_case_insensitive(tmp_path):
    p, sha, n = _obj(tmp_path, b"x")
    assert mod.verify_download(p, sha.upper(), n) == []


# ---------------------------------------------------------------------------- marker provenance


def _marker(tmp_path: Path, **over) -> Path:
    doc = {
        "deployed_repository_commit": DEPLOYED,
        "adr0043_implementation_commit": IMPL,
        "adr0043_governed_paths_match": True,
    }
    doc.update(over)
    p = tmp_path / "DEPLOYED_BUILD_INFO.json"
    p.write_text(json.dumps(doc), encoding="utf-8")
    return p


def test_marker_matching_the_approved_identities_passes(tmp_path):
    assert mod.verify_marker(_marker(tmp_path), DEPLOYED, IMPL) == []


def test_marker_wrong_deployed_commit_is_refused(tmp_path):
    v = mod.verify_marker(_marker(tmp_path, deployed_repository_commit="dead" * 10), DEPLOYED, IMPL)
    assert any("deployed_repository_commit" in x for x in v)


def test_marker_wrong_impl_commit_is_refused(tmp_path):
    v = mod.verify_marker(_marker(tmp_path, adr0043_implementation_commit="dead" * 10), DEPLOYED, IMPL)
    assert any("adr0043_implementation_commit" in x for x in v)


@pytest.mark.parametrize("bad", [False, "true", 1, None])
def test_marker_governed_paths_match_not_true_is_refused(tmp_path, bad):
    v = mod.verify_marker(_marker(tmp_path, adr0043_governed_paths_match=bad), DEPLOYED, IMPL)
    assert any("governed_paths_match" in x for x in v)


def test_marker_missing_file_is_refused(tmp_path):
    v = mod.verify_marker(tmp_path / "absent.json", DEPLOYED, IMPL)
    assert v and "missing" in v[0]


def test_marker_malformed_json_is_refused(tmp_path):
    p = tmp_path / "DEPLOYED_BUILD_INFO.json"
    p.write_text("{ not json", encoding="utf-8")
    v = mod.verify_marker(p, DEPLOYED, IMPL)
    assert v and "not valid JSON" in v[0]


# ---------------------------------------------------------------------------- CLI exit codes


def test_cli_download_ok_exit_zero(tmp_path, capsys):
    p, sha, n = _obj(tmp_path, b"ok")
    rc = mod.main(["download", "--path", str(p), "--sha256", sha, "--bytes", str(n)])
    assert rc == 0


def test_cli_download_mismatch_exit_one(tmp_path):
    p, sha, n = _obj(tmp_path, b"ok")
    rc = mod.main(["download", "--path", str(p), "--sha256", "0" * 64, "--bytes", str(n)])
    assert rc == 1


def test_cli_marker_ok_exit_zero(tmp_path):
    rc = mod.main(["marker", "--marker", str(_marker(tmp_path)),
                   "--deployed-commit", DEPLOYED, "--impl-commit", IMPL])
    assert rc == 0


def test_cli_marker_mismatch_exit_one(tmp_path):
    rc = mod.main(["marker", "--marker", str(_marker(tmp_path, adr0043_governed_paths_match=False)),
                   "--deployed-commit", DEPLOYED, "--impl-commit", IMPL])
    assert rc == 1
