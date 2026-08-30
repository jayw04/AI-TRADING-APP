"""Run the generic versioned-provisioner bash harness under pytest so CI exercises it.

The harness (``deploy/aws/tests/test_provision_versioned_s3.sh``) fakes aws/docker/curl and drives
the real provisioner through every refusal, staging, authorization-gate and rollback path, and
asserts that ``provision-adr0043-validation.sh`` keeps its own semantics. It is POSIX bash +
python3 + coreutils; it runs in CI (Linux) and is skipped on Windows/where bash is absent. When it
runs, a non-zero exit fails this test with the harness output attached.

The manifest-content assertions below need no shell, so they run everywhere: they are the ones that
would catch an edited manifest silently changing the approved artifact identity.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[4]
HARNESS = REPO_ROOT / "deploy" / "aws" / "tests" / "test_provision_versioned_s3.sh"
AWSDIR = REPO_ROOT / "deploy" / "aws"
CONTROL = AWSDIR / "manifests" / "DEPLOY_CONTROL.json"
FACTOR_MANIFEST = AWSDIR / "manifests" / "factor_repair_b94838b6.json"

# The owner-designated tuple. A change to any of these is a change to the approved artifact and
# must be a reviewed manifest edit, never an accident.
APPROVED = {
    "deployed_repository_commit": "b94838b6aa611e02982b3d1ae5ca5333b5f1d80e",
    "adr0043_implementation_commit": "38f40b46906fc91497049924f7a62e7384d67653",
    "bucket": "workbench-backups-219024422756",
    "key": "bootstrap/factor-repair/b94838b6-code.tgz",
    "version_id": "5NVWUcMwH_PfHw1k6MiwJH6ohtjT8Vyz",
    "sha256": "1d49259a505037d408ed6c1781109180d4e5ea680793c16c90201a7195ca1684",
    "bytes": 6879138,
    "code_digest": "sha256:a52823f3bf4e7c919c0a549508230d9de66700042837ab4e9eb02fb98e320a7a",
}


@pytest.mark.skipif(
    sys.platform.startswith("win"), reason="bash harness runs on POSIX/CI, not Windows"
)
@pytest.mark.skipif(shutil.which("bash") is None, reason="bash unavailable")
@pytest.mark.skipif(shutil.which("python3") is None, reason="python3 unavailable to the harness")
def test_versioned_provisioner_bash_harness_passes():
    assert HARNESS.exists(), f"harness missing at {HARNESS}"
    result = subprocess.run(["bash", str(HARNESS)], capture_output=True, text=True, timeout=300)
    assert result.returncode == 0, f"provisioner harness failed:\n{result.stdout}\n{result.stderr}"
    assert "0 failed" in result.stdout


def test_frozen_manifest_binds_the_designated_tuple():
    """⛔ The approved artifact identity is exactly the owner-designated tuple."""
    m = json.loads(FACTOR_MANIFEST.read_text(encoding="utf-8"))
    assert m["schema"] == "versioned-deploy/1"
    for field, expected in APPROVED.items():
        assert m[field] == expected, f"{field} drifted from the designated tuple"


def test_control_record_bounds_manifest_selection():
    """Selection is by name from a committed allowlist — not an operator-supplied path."""
    ctl = json.loads(CONTROL.read_text(encoding="utf-8"))
    assert ctl["schema"] == "versioned-deploy-control/1"
    assert ctl["allowed_manifests"] == ["factor_repair_b94838b6"]
    for name in ctl["allowed_manifests"]:
        assert (AWSDIR / "manifests" / f"{name}.json").exists(), (
            f"allowlisted {name} has no manifest"
        )


def test_legacy_key_is_forbidden_and_adr0043_prefix_is_not_borrowed():
    """The legacy mutable artifact is refused, and this control never claims ADR-0043 authority."""
    ctl = json.loads(CONTROL.read_text(encoding="utf-8"))
    assert "bootstrap/code.tgz" in ctl["forbidden_keys"]
    assert not any(p.startswith("adr0043/") for p in ctl["allowed_key_prefixes"])
    m = json.loads(FACTOR_MANIFEST.read_text(encoding="utf-8"))
    assert any(m["key"].startswith(p) for p in ctl["allowed_key_prefixes"])
    assert m["key"] not in ctl["forbidden_keys"]


def test_the_adr0043_provisioner_and_manifest_are_not_repurposed():
    """⛔ An ADR-0043 control must not become the authority for an unrelated deployment."""
    adr_prov = (AWSDIR / "provision-adr0043-validation.sh").read_text(encoding="utf-8")
    adr_manifest = json.loads(
        (AWSDIR / "adr0043_validation_deploy.json").read_text(encoding="utf-8")
    )
    generic = (AWSDIR / "provision-versioned-s3.sh").read_text(encoding="utf-8")

    # the ADR-0043 path keeps its own prefix guard, latch and fixed manifest
    assert "adr0043/*) : ;;" in adr_prov
    assert "ADR0043_MIGRATION_AUTHORIZED" in adr_prov
    assert "adr0043_validation_deploy.json" in adr_prov
    assert adr_manifest["key"].startswith("adr0043/")

    # The generic path never READS the ADR-0043 manifest. Comments are stripped before checking:
    # the generic provisioner's header names that manifest precisely to document that it does NOT
    # use it, and that explanation must not be mistaken for a reference to it.
    code = "\n".join(ln for ln in generic.splitlines() if not ln.lstrip().startswith("#"))
    assert "adr0043_validation_deploy" not in code
    assert "VERSIONED_DEPLOY_AUTHORIZED" in code


def test_generic_provisioner_keeps_the_hardened_properties():
    """The mechanics carried forward are the reason this path is acceptable at all."""
    src = (AWSDIR / "provision-versioned-s3.sh").read_text(encoding="utf-8")
    for probe in (
        "--version-id",  # exact object version, never key-only
        "verify_deploy_object.py",  # size+sha before extraction, marker after staging
        "BEFORE extraction",
        ".staging.",  # staged, never over the running tree
        "VERIFIED — NO SWAP, NO START",  # default flow performs no swap
        "ROLLBACK_OK",
        "ROLLBACK_FAILED",
    ):
        assert probe in src, f"hardened property missing from the generic provisioner: {probe}"
