"""The two checks with different authority: startup enforcement and host-side attestation.

They answer different questions and neither substitutes for the other:

  * `verify_runtime_code_identity` (in-container, before migrations) proves *the code executing now
    equals the code this image claims it was built with*. A wrong image passes it, describing itself
    correctly — so it is integrity enforcement, never deployment provenance.
  * `derive_runtime_code_digest_from_tar` (host-side, from `docker cp`) derives the running code
    WITHOUT executing container userland, which is what makes it independent evidence.
"""

from __future__ import annotations

import importlib.util
import io
import json
import subprocess
import sys
import tarfile
from pathlib import Path

import pytest

from app.validation.deployment_identity import (
    CODE_DIGEST_SCHEMA,
    DeploymentEvidenceMismatch,
    DeploymentIdentityError,
    code_identity,
    derive_runtime_code_digest,
)

SCRIPTS = Path(__file__).resolve().parents[2] / "scripts"


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _tree(root: Path, files: dict[str, str]) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    for relative, body in files.items():
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(body, encoding="utf-8")
    return root


def _docker_cp_tar(root: Path) -> bytes:
    """Mimic `docker cp <c>:/app/app -`: a tar whose entries are rooted at `app/`."""
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w") as archive:
        archive.add(root, arcname="app")
    return buffer.getvalue()


# ── startup enforcement ──────────────────────────────────────────────────────────────────────────

@pytest.fixture
def image(tmp_path):
    code = _tree(tmp_path / "app", {"main.py": "V = 1\n", "pkg/mod.py": "X = 2\n"})
    identity = tmp_path / "BUILD_CODE_IDENTITY.json"
    identity.write_text(json.dumps({
        "schema": CODE_DIGEST_SCHEMA, "code_digest": derive_runtime_code_digest(code),
        "measured_root": "/app/app"}), encoding="utf-8")
    return {"code": code, "identity": identity}


def test_startup_passes_when_the_running_code_is_the_built_code(image):
    gate = _load("verify_runtime_code_identity")
    assert gate.verify(image["identity"], image["code"]).startswith("sha256:")


def test_startup_refuses_when_the_running_code_was_edited(image):
    gate = _load("verify_runtime_code_identity")
    (image["code"] / "main.py").write_text("V = 999\n", encoding="utf-8")
    with pytest.raises(DeploymentIdentityError, match="RUNTIME CODE MISMATCH"):
        gate.verify(image["identity"], image["code"])


def test_startup_refuses_an_image_with_no_baked_identity(image):
    gate = _load("verify_runtime_code_identity")
    image["identity"].unlink()
    with pytest.raises(DeploymentIdentityError, match="no baked code identity"):
        gate.verify(image["identity"], image["code"])


def test_startup_refuses_a_foreign_canonicalization(image):
    """Comparing digests produced by different algorithms would be meaningless, so refuse."""
    gate = _load("verify_runtime_code_identity")
    payload = json.loads(image["identity"].read_text(encoding="utf-8"))
    payload["schema"] = "some-other-scheme/9"
    image["identity"].write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(DeploymentIdentityError, match="schema"):
        gate.verify(image["identity"], image["code"])


def test_startup_refuses_a_malformed_expected_digest(image):
    gate = _load("verify_runtime_code_identity")
    payload = json.loads(image["identity"].read_text(encoding="utf-8"))
    payload["code_digest"] = "not-a-digest"
    image["identity"].write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(DeploymentIdentityError, match="no usable code_digest"):
        gate.verify(image["identity"], image["code"])


def test_startup_cannot_be_satisfied_from_the_environment(image, monkeypatch):
    """★ The expected value is baked, never supplied. An operator facing a mismatch on a capture
    morning must not be able to resolve it by changing the assertion."""
    gate = _load("verify_runtime_code_identity")
    (image["code"] / "main.py").write_text("V = 5\n", encoding="utf-8")
    for name in ("WORKBENCH_CODE_DIGEST", "CODE_DIGEST", "BUILD_CODE_DIGEST"):
        monkeypatch.setenv(name, derive_runtime_code_digest(image["code"]))
    with pytest.raises(DeploymentIdentityError, match="RUNTIME CODE MISMATCH"):
        gate.verify(image["identity"], image["code"])


def test_the_bake_and_the_gate_agree(tmp_path, monkeypatch):
    """The build-time writer and the boot-time reader must be two ends of one contract."""
    code = _tree(tmp_path / "app", {"a.py": "A = 1\n"})
    baker = _load("bake_code_identity")
    identity = tmp_path / "BUILD_CODE_IDENTITY.json"
    monkeypatch.setattr(baker, "CODE_ROOT", code)
    monkeypatch.setattr(baker, "IDENTITY_PATH", identity)
    assert baker.main() == 0
    gate = _load("verify_runtime_code_identity")
    assert gate.verify(identity, code) == derive_runtime_code_digest(code)


# ── host-side attestation ────────────────────────────────────────────────────────────────────────

def test_the_host_derives_the_same_value_from_a_docker_cp_stream(tmp_path):
    """★ The attestation property: the host reaches the runtime's identity without running its code."""
    code = _tree(tmp_path / "app", {"main.py": "V = 1\n", "pkg/mod.py": "X = 2\n"})
    attest = _load("derive_runtime_code_digest_from_tar")
    entries = attest.entries_from_tar(io.BytesIO(_docker_cp_tar(code)))
    assert code_identity(entries) == derive_runtime_code_digest(code)


def test_the_host_ignores_out_of_scope_files(tmp_path):
    code = _tree(tmp_path / "app", {"main.py": "V = 1\n"})
    before = derive_runtime_code_digest(code)
    (code / "notes.md").write_text("prose\n", encoding="utf-8")
    (code / "__pycache__").mkdir()
    (code / "__pycache__" / "main.pyc").write_bytes(b"\x00compiled")
    attest = _load("derive_runtime_code_digest_from_tar")
    entries = attest.entries_from_tar(io.BytesIO(_docker_cp_tar(code)))
    assert code_identity(entries) == before


def test_the_host_refuses_an_empty_scope(tmp_path):
    code = _tree(tmp_path / "app", {"notes.md": "no code here\n"})
    attest = _load("derive_runtime_code_digest_from_tar")
    with pytest.raises(attest.RuntimeAttestationError, match="no measured files"):
        attest.entries_from_tar(io.BytesIO(_docker_cp_tar(code)))


def test_the_host_refuses_a_duplicate_entry(tmp_path):
    """Two entries for one name means the identity depends on which copy you kept."""
    attest = _load("derive_runtime_code_digest_from_tar")
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w") as archive:
        for body in (b"A = 1\n", b"A = 2\n"):
            info = tarfile.TarInfo("app/dup.py")
            info.size = len(body)
            archive.addfile(info, io.BytesIO(body))
    with pytest.raises(attest.RuntimeAttestationError, match="duplicate"):
        attest.entries_from_tar(io.BytesIO(buffer.getvalue()))


def test_the_host_refuses_path_traversal(tmp_path):
    attest = _load("derive_runtime_code_digest_from_tar")
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w") as archive:
        body = b"X = 1\n"
        info = tarfile.TarInfo("app/../../escape.py")
        info.size = len(body)
        archive.addfile(info, io.BytesIO(body))
    with pytest.raises(attest.RuntimeAttestationError, match="traversal"):
        attest.entries_from_tar(io.BytesIO(buffer.getvalue()))


def test_the_host_refuses_an_in_scope_symlink(tmp_path):
    """★ Executable indirection inside the measured set is refused, not skipped."""
    attest = _load("derive_runtime_code_digest_from_tar")
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w") as archive:
        body = b"X = 1\n"
        real = tarfile.TarInfo("app/real.py")
        real.size = len(body)
        archive.addfile(real, io.BytesIO(body))
        link = tarfile.TarInfo("app/shim.py")
        link.type = tarfile.SYMTYPE
        link.linkname = "real.py"
        archive.addfile(link)
    with pytest.raises(attest.RuntimeAttestationError, match="link"):
        attest.entries_from_tar(io.BytesIO(buffer.getvalue()))


def test_the_host_refuses_a_special_file_in_scope(tmp_path):
    attest = _load("derive_runtime_code_digest_from_tar")
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w") as archive:
        info = tarfile.TarInfo("app/weird.py")
        info.type = tarfile.FIFOTYPE
        archive.addfile(info)
    with pytest.raises(attest.RuntimeAttestationError, match="special file"):
        attest.entries_from_tar(io.BytesIO(buffer.getvalue()))


def test_the_tree_collector_also_refuses_an_in_scope_symlink(tmp_path):
    """Both collectors must agree on symlink semantics, or host and container disagree by design."""
    code = _tree(tmp_path / "app", {"real.py": "X = 1\n"})
    try:
        (code / "shim.py").symlink_to(code / "real.py")
    except (OSError, NotImplementedError):
        pytest.skip("symlink creation not permitted on this platform")
    with pytest.raises(DeploymentEvidenceMismatch, match="symlink"):
        derive_runtime_code_digest(code)


def test_the_host_helper_exits_nonzero_on_failure(tmp_path):
    """Fail closed at the process boundary too — Gate 6 reads the exit status."""
    code = _tree(tmp_path / "app", {"notes.md": "no code\n"})
    archive = tmp_path / "cp.tar"
    archive.write_bytes(_docker_cp_tar(code))
    result = subprocess.run(
        (sys.executable, str(SCRIPTS / "derive_runtime_code_digest_from_tar.py"),
         "--from-file", str(archive)), capture_output=True, text=True)
    assert result.returncode == 1
    assert "FAILED" in result.stderr
