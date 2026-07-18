"""MR-002 Stage-3 — launcher tooling tests (Phase B assembly, 2026-07-18).

Proves the NEW launcher-side tools (attestation producer, frozen verification tool,
final-test-report generator) produce artifacts the FROZEN loaders accept, and that every
tamper/wrong-key path fails closed. Expanded per the owner's launcher-tool reviews
(2026-07-18): blocker 1 (immutable artifacts refuse overwrite), blocker 2 (output-mount
identity derived from the argv, never merely asserted), blocker 3 (closed launch-command
grammar enforced at produce AND exec), blocker 4 (atomic no-replace publication via the
shared hard-link primitive — race at the publication boundary refused), blocker 5
(governed-input binding: signed hashes ↔ ro mounts at fixed /inputs destinations ↔
MR002_* env values ↔ the very host bytes hashed; re-hashed again at exec), plus explicit
Ed25519 key-type enforcement and 0600 private-key creation. The frozen implementation
files are untouched — these tests exercise the frozen loaders as consumers only.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from scripts import mr002_stage3_attestation_verify as verify_mod
from scripts import mr002_stage3_launch_attestation as att
from scripts import mr002_stage3_population_runner as run
from scripts.mr002_stage3_final_test_report import build_report

VERIFY_TOOL = Path(att.__file__).parent / "mr002_stage3_attestation_verify.py"
IMAGE = "sha256:" + "c" * 64
OUT_SRC = "/data/mr002/out"
OUT_IDENTITY = f"{OUT_SRC}:/out:rw"
IN_SRC_DIR = "/data/mr002/inputs"
KWARG_BY_ART = {"authorization": "authorization_path", "pins": "expected_pins_path",
                "manifest": "source_manifest_path", "package": "execution_package_path"}


def governed_mount_tokens(input_srcs: dict[str, str] | None = None,
                          drop: str | None = None, mode: str = "ro") -> list[str]:
    """--mount tokens for the four governed inputs; override src per kwarg name."""
    toks: list[str] = []
    for _, _, dst, kwarg in att.GOVERNED_INPUTS:
        if kwarg == drop:
            continue
        src = (input_srcs or {}).get(kwarg, f"{IN_SRC_DIR}/{dst.rsplit('/', 1)[1]}")
        toks += ["--mount", f"type=bind,src={src},dst={dst},{mode}"]
    return toks


def artifact_mount_tokens(artifact_srcs: dict[str, str] | None = None,
                          drop: str | None = None) -> list[str]:
    """--mount tokens for the five runner-required artifact paths; override src per env key."""
    toks: list[str] = []
    for env_key, dst in att.GOVERNED_ARTIFACT_ENV.items():
        if env_key == drop:
            continue
        src = (artifact_srcs or {}).get(env_key, f"{IN_SRC_DIR}/{dst.rsplit('/', 1)[1]}")
        toks += ["--mount", f"type=bind,src={src},dst={dst},ro"]
    return toks


def governed_env_tokens(override: dict[str, str] | None = None) -> list[str]:
    vals = {k: dst for _, k, dst, _ in att.GOVERNED_INPUTS}
    vals.update(att.GOVERNED_ARTIFACT_ENV)
    return [f"--env={k}={(override or {}).get(k, v)}" for k, v in vals.items()]


def good_argv(*, image: str = IMAGE, out_spec: str | None = None,
              repo_spec: str = "type=bind,src=/data/mr002/repo,dst=/work,ro",
              input_srcs: dict[str, str] | None = None, drop_input: str | None = None,
              input_mode: str = "ro", artifact_srcs: dict[str, str] | None = None,
              drop_artifact: str | None = None, governed_env: dict[str, str] | None = None,
              countersign_sha: str = "e" * 64,
              pythonpath: str | None = att.PYTHONPATH_APPROVED,
              env_extra: list[str] | None = None, command: list[str] | None = None,
              extra_opts: list[str] | None = None) -> list[str]:
    """The canonical closed-grammar ATTESTED TEMPLATE argv (blocker 8: it must NOT carry
    the launcher-derived MR002_EXECUTION_BINDING_SHA256), with targeted override points."""
    out_spec = out_spec if out_spec is not None else f"type=bind,src={OUT_SRC},dst=/out,rw"
    argv = ["docker", "run", "--rm", "--network=none",
            "--mount", repo_spec, "--mount", out_spec]
    argv += governed_mount_tokens(input_srcs, drop=drop_input, mode=input_mode)
    argv += artifact_mount_tokens(artifact_srcs, drop=drop_artifact)
    argv += ["--env=OPENBLAS_CORETYPE=HASWELL", "--env=OPENBLAS_NUM_THREADS=1",
             "--env=OMP_NUM_THREADS=1", "--env=MKL_NUM_THREADS=1"]
    argv += governed_env_tokens(governed_env)
    argv += [f"--env=MR002_EXECUTION_COUNTERSIGN_SHA256={countersign_sha}"]
    if pythonpath is not None:
        argv += [f"--env=PYTHONPATH={pythonpath}"]
    argv += ["--workdir=/work/apps/backend"]
    argv += env_extra or []
    argv += extra_opts or []
    argv += [image]
    argv += command if command is not None else ["python", att.REGISTERED_ENTRYPOINT]
    return argv


def _sha(path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _posix(p) -> str:
    return str(p).replace("\\", "/")


@pytest.fixture()
def keypair(tmp_path):
    priv = tmp_path / "keys" / "launcher_ed25519.pem"
    pub = tmp_path / "keys" / "launcher_ed25519.pub.pem"
    kid = att.generate_keypair(str(priv), str(pub))
    return priv, pub, kid


def _stub_artifacts(tmp_path) -> dict:
    arts = {}
    for name in ("authorization", "pins", "manifest", "package", "binding"):
        p = tmp_path / f"{name}.json"
        p.write_text(json.dumps({"stub": name}), encoding="utf-8")
        arts[name] = p
    return arts


def _stub_input_srcs(arts) -> dict[str, str]:
    """Map each governed-input kwarg to the actual stub file so binding validates."""
    return {kwarg: _posix(arts[name]) for name, kwarg in KWARG_BY_ART.items()}


def argv_for(arts, **kw) -> list[str]:
    """Canonical template argv wired to the stub artifacts (real srcs + real countersign
    hash channel; no binding hash — that field is launcher-derived at exec)."""
    kw.setdefault("input_srcs", _stub_input_srcs(arts))
    kw.setdefault("countersign_sha", _sha(arts["authorization"]))
    kw.setdefault("artifact_srcs", {"MR002_EXECUTION_BINDING": _posix(arts["binding"])})
    return good_argv(**kw)


def _make_binding(produced, receipt_path):
    """Assemble the Phase-B execution binding AFTER the attestation and receipt exist —
    the real construction order — with real artifact hashes, written to the attested
    mount source. Accepted by the frozen `load_execution_binding`."""
    arts = produced["arts"]
    b = {
        "record_type": "MR002_STAGE3_EXECUTION_BINDING", "version": "1.0",
        "record_status": "IMMUTABLE", "countersigned_by": "Jay Wang (owner)",
        "countersigned_date": "2026-07-18", "repository": "jayw04/AI-TRADING-APP",
        "decision": "EXECUTION_PACKAGE_COUNTERSIGNED", "execution_authorized": True,
        "scope": "MR002_STAGE3_CLEAN_SUCCESSOR_ONLY",
        "implementation_manifest_sha256": _sha(arts["manifest"]),
        "realism_pass_sha256": "1" * 64,
        "final_test_report_sha256": "2" * 64,
        "execution_package_sha256": _sha(arts["package"]),
        "expected_pins_sha256": _sha(arts["pins"]),
        "authorization_sha256": _sha(arts["authorization"]),
        "launch_attestation_sha256": _sha(produced["path"]),
        "launch_verification_receipt_sha256": _sha(receipt_path),
        "bound_commit": "a" * 40, "bound_tree": "b" * 40,
        "image_digest": IMAGE, "oci_config_digest": IMAGE,
    }
    data = (json.dumps(b, indent=1, sort_keys=True) + "\n").encode("utf-8")
    arts["binding"].write_bytes(data)  # the attested /inputs mount source
    return arts["binding"]


def _exec_args(produced, receipt, binding):
    return type("A", (), {"attestation": str(produced["path"]), "receipt": str(receipt),
                          "binding": str(binding)})()


def _build(tmp_path, priv, *, argv=None, arts=None, output_mount=OUT_IDENTITY,
           image_digest=IMAGE):
    arts = arts if arts is not None else _stub_artifacts(tmp_path)
    if argv is None:
        argv = argv_for(arts)
    return att.build_attestation(
        authorization_path=str(arts["authorization"]), expected_pins_path=str(arts["pins"]),
        source_manifest_path=str(arts["manifest"]), execution_package_path=str(arts["package"]),
        bound_commit="a" * 40, bound_tree="b" * 40,
        image_digest=image_digest, oci_config_digest=IMAGE,
        exact_command_argv=argv,
        output_mount_identity=output_mount, private_key_path=str(priv),
        verification_tool_path=str(VERIFY_TOOL)), arts


@pytest.fixture()
def produced(tmp_path, keypair):
    priv, pub, kid = keypair
    doc, arts = _build(tmp_path, priv)
    path = tmp_path / "attestation.json"
    data = (json.dumps(doc, indent=1, sort_keys=True) + "\n").encode("utf-8")
    path.write_bytes(data)
    return {"path": path, "doc": doc, "arts": arts, "priv": priv, "pub": pub, "kid": kid,
            "tmp": tmp_path}


# ── attestation producer × frozen loader ─────────────────────────────────────────────────────────
def test_attestation_roundtrip_accepted_by_frozen_loader(produced):
    loaded = run.load_launch_attestation(str(produced["path"]), _sha(produced["path"]))
    assert loaded["signing_key_id"] == produced["kid"]
    # observed hashes, not trusted ones
    assert loaded["authorization_sha256"] == _sha(produced["arts"]["authorization"])
    assert loaded["verification_tool_sha256"] == _sha(VERIFY_TOOL)
    assert json.loads(loaded["exact_command"])[0] == "docker"
    assert loaded["output_mount_identity"] == OUT_IDENTITY


def test_attestation_tamper_refused_by_frozen_loader(produced):
    d = json.loads(produced["path"].read_text(encoding="utf-8"))
    d["launcher_identity"] = "someone else"
    tampered = produced["tmp"] / "tampered.json"
    tampered.write_text(json.dumps(d, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    with pytest.raises(run.Stage3RunRefused, match="ATTESTATION_PAYLOAD_HASH_MISMATCH"):
        run.load_launch_attestation(str(tampered), _sha(tampered))


# ── frozen verification tool × frozen receipt loader ─────────────────────────────────────────────
def _run_verify(attestation, pubkey, receipt):
    return subprocess.run(
        [sys.executable, str(VERIFY_TOOL), "--attestation", str(attestation),
         "--trusted-public-key", str(pubkey), "--receipt-out", str(receipt)],
        capture_output=True, text=True, check=False)


def test_verify_tool_receipt_accepted_by_frozen_loader(produced):
    receipt = produced["tmp"] / "receipt.json"
    res = _run_verify(produced["path"], produced["pub"], receipt)
    assert res.returncode == 0, res.stderr
    attestation = run.load_launch_attestation(str(produced["path"]), _sha(produced["path"]))
    loaded = run.load_verification_receipt(str(receipt), _sha(receipt),
                                           _sha(produced["path"]), attestation=attestation)
    assert loaded["verification_exit_status"] == 0
    assert loaded["run_nonce"] == attestation["run_nonce"]          # cycle-9 blocker 5
    assert loaded["verification_tool_sha256"] == _sha(VERIFY_TOOL)  # cycle-9 blocker 7


def test_verify_tool_rejects_wrong_key(produced, tmp_path):
    other_pub = tmp_path / "other.pub.pem"
    att.generate_keypair(str(tmp_path / "other.pem"), str(other_pub))
    receipt = produced["tmp"] / "receipt_wrongkey.json"
    res = _run_verify(produced["path"], other_pub, receipt)
    assert res.returncode == 5
    assert not receipt.exists()


def test_verify_tool_rejects_tampered_attestation(produced):
    d = json.loads(produced["path"].read_text(encoding="utf-8"))
    d["exact_command"] = json.dumps(["rm", "-rf", "/"])
    tampered = produced["tmp"] / "tampered2.json"
    tampered.write_text(json.dumps(d, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    receipt = produced["tmp"] / "receipt_tampered.json"
    res = _run_verify(tampered, produced["pub"], receipt)
    assert res.returncode == 3
    assert not receipt.exists()


def test_verify_tool_rejects_forged_signature(produced):
    d = json.loads(produced["path"].read_text(encoding="utf-8"))
    sig = bytearray(base64.b64decode(d["signature"]))
    sig[0] ^= 0xFF
    d["signature"] = base64.b64encode(bytes(sig)).decode("ascii")
    forged = produced["tmp"] / "forged.json"
    forged.write_text(json.dumps(d, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    receipt = produced["tmp"] / "receipt_forged.json"
    res = _run_verify(forged, produced["pub"], receipt)
    assert res.returncode == 6
    assert not receipt.exists()


# ── blocker 1: immutable artifacts refuse overwrite (shared primitive pre-checks) ────────────────
def test_blocker1_existing_destination_refused(tmp_path):
    dest = tmp_path / "attestation.json"
    dest.write_bytes(b"ORIGINAL IMMUTABLE BYTES")
    with pytest.raises(verify_mod.PublicationRefused, match="PUBLISH_REFUSED_EXISTS_DESTINATION"):
        verify_mod.publish_immutable(str(dest), b"replacement")
    assert dest.read_bytes() == b"ORIGINAL IMMUTABLE BYTES"
    assert not (tmp_path / "attestation.json.tmp").exists()


def test_blocker1_existing_tmp_path_refused(tmp_path):
    dest = tmp_path / "attestation.json"
    tmp = tmp_path / "attestation.json.tmp"
    tmp.write_bytes(b"STALE TMP")
    with pytest.raises(verify_mod.PublicationRefused,
                       match="PUBLISH_REFUSED_EXISTS_TEMPORARY_PATH"):
        verify_mod.publish_immutable(str(dest), b"data")
    assert tmp.read_bytes() == b"STALE TMP"
    assert not dest.exists()


def test_blocker1_symlink_destination_refused(tmp_path):
    dest = tmp_path / "attestation.json"
    os.symlink(str(tmp_path / "elsewhere.json"), str(dest))  # dangling symlink
    with pytest.raises(verify_mod.PublicationRefused, match="PUBLISH_REFUSED_SYMLINK_DESTINATION"):
        verify_mod.publish_immutable(str(dest), b"data")
    assert not (tmp_path / "elsewhere.json").exists()  # nothing written through the link


def test_blocker1_existing_receipt_destination_refused(produced):
    receipt = produced["tmp"] / "receipt_twice.json"
    first = _run_verify(produced["path"], produced["pub"], receipt)
    assert first.returncode == 0, first.stderr
    original = receipt.read_bytes()
    second = _run_verify(produced["path"], produced["pub"], receipt)
    assert second.returncode == 7
    assert "PUBLISH_REFUSED_EXISTS_DESTINATION" in second.stderr
    assert receipt.read_bytes() == original


def test_blocker1_receipt_symlink_destination_refused(produced):
    receipt = produced["tmp"] / "receipt_link.json"
    os.symlink(str(produced["tmp"] / "elsewhere.json"), str(receipt))
    res = _run_verify(produced["path"], produced["pub"], receipt)
    assert res.returncode == 7
    assert not (produced["tmp"] / "elsewhere.json").exists()


# ── blocker 4: atomic no-replace publication (the race at the publication boundary) ──────────────
def test_blocker4_destination_appearing_after_prechecks_refused(tmp_path, monkeypatch):
    """The exact race: the destination is created AFTER every pre-check, immediately
    before the publication instant. os.link's create-if-absent semantics must refuse,
    and the competing bytes must remain unchanged."""
    dest = tmp_path / "attestation.json"
    real_link = os.link

    def _racing_link(src, dst, **kw):
        Path(dst).write_bytes(b"COMPETING WRITER BYTES")  # the race winner
        return real_link(src, dst, **kw)

    monkeypatch.setattr(verify_mod.os, "link", _racing_link)
    with pytest.raises(verify_mod.PublicationRefused, match="PUBLISH_REFUSED_EXISTS_DESTINATION"):
        verify_mod.publish_immutable(str(dest), b"attempted publication")
    assert dest.read_bytes() == b"COMPETING WRITER BYTES"   # competitor untouched
    assert not (tmp_path / "attestation.json.tmp").exists()  # tmp deliberately cleaned


def test_blocker4_successful_publication_exact_bytes_tmp_removed(tmp_path):
    dest = tmp_path / "receipt.json"
    payload = b'{"record_status": "IMMUTABLE"}\n'
    sha = verify_mod.publish_immutable(str(dest), payload)
    assert dest.read_bytes() == payload
    assert sha == hashlib.sha256(payload).hexdigest()
    assert not (tmp_path / "receipt.json.tmp").exists()


def test_blocker4_publication_failure_no_partial_destination(tmp_path, monkeypatch):
    """If the publication step itself fails, no partial destination may exist and the
    temporary is deliberately cleaned (recorded behavior in the primitive's docstring)."""
    dest = tmp_path / "attestation.json"

    def _failing_link(src, dst, **kw):
        raise OSError("simulated link failure")

    monkeypatch.setattr(verify_mod.os, "link", _failing_link)
    with pytest.raises(OSError, match="simulated link failure"):
        verify_mod.publish_immutable(str(dest), b"data")
    assert not dest.exists()                                 # no partial destination
    assert not (tmp_path / "attestation.json.tmp").exists()  # deliberate cleanup


def test_blocker4_producer_uses_shared_primitive(tmp_path, keypair, monkeypatch):
    """produce() publishes through verify_mod.publish_immutable — one implementation,
    owned by the frozen trust root, not a producer-local near-copy."""
    priv, _, _ = keypair
    doc, arts = _build(tmp_path, priv)
    called = {}
    real_publish = verify_mod.publish_immutable

    def _spy(path, data):
        called["path"] = path
        return real_publish(path, data)

    monkeypatch.setattr(verify_mod, "publish_immutable", _spy)
    out = tmp_path / "produced_attestation.json"
    args = type("A", (), {
        "authorization": str(arts["authorization"]), "expected_pins": str(arts["pins"]),
        "source_manifest": str(arts["manifest"]), "execution_package": str(arts["package"]),
        "bound_commit": "a" * 40, "bound_tree": "b" * 40,
        "image_digest": IMAGE, "oci_config_digest": IMAGE,
        "exact_command_argv": json.dumps(argv_for(arts)),
        "output_mount": OUT_IDENTITY, "private_key": str(priv),
        "verification_tool": str(VERIFY_TOOL), "launcher_identity": None,
        "run_nonce": None, "out": str(out)})()
    assert att.produce(args) == 0
    assert called["path"] == str(out)
    # and a second produce to the SAME path refuses through the same primitive
    assert att.produce(args) == 2


# ── blocker 2: output-mount identity derived from the argv, not asserted ─────────────────────────
def test_blocker2_canonical_output_mount_accepted(tmp_path, keypair):
    priv, _, _ = keypair
    doc, _ = _build(tmp_path, priv)
    assert doc["output_mount_identity"] == OUT_IDENTITY  # derived == claimed


def test_blocker2_claimed_mount_differs_from_argv_refused(tmp_path, keypair):
    priv, _, _ = keypair
    with pytest.raises(att.LaunchValidationError, match="OUTPUT_MOUNT_IDENTITY_MISMATCH"):
        _build(tmp_path, priv, output_mount="/data/OTHER/dir:/out:rw")


def test_blocker2_missing_out_mount_refused(tmp_path, keypair):
    priv, _, _ = keypair
    argv = good_argv()
    out_idx = argv.index(f"type=bind,src={OUT_SRC},dst=/out,rw")
    del argv[out_idx - 1:out_idx + 1]  # remove the '--mount <out spec>' pair
    with pytest.raises(att.LaunchValidationError, match="OUTPUT_MOUNT_COUNT_NOT_ONE:0"):
        _build(tmp_path, priv, argv=argv)


def test_blocker2_duplicate_out_mounts_refused(tmp_path, keypair):
    priv, _, _ = keypair
    argv = good_argv(extra_opts=["--mount", "type=bind,src=/data/other,dst=/out,rw"])
    with pytest.raises(att.LaunchValidationError, match="OUTPUT_MOUNT_COUNT_NOT_ONE:2"):
        _build(tmp_path, priv, argv=argv)


def test_blocker2_relative_host_source_refused(tmp_path, keypair):
    priv, _, _ = keypair
    argv = good_argv(out_spec="type=bind,src=relative/out,dst=/out,rw")
    with pytest.raises(att.LaunchValidationError, match="MOUNT_SRC_NOT_ABSOLUTE"):
        _build(tmp_path, priv, argv=argv)


def test_blocker2_readonly_out_mount_refused(tmp_path, keypair):
    priv, _, _ = keypair
    argv = good_argv(out_spec=f"type=bind,src={OUT_SRC},dst=/out,ro")
    with pytest.raises(att.LaunchValidationError, match="OUTPUT_MOUNT_NOT_EXPLICITLY_RW"):
        _build(tmp_path, priv, argv=argv)


def test_blocker2_out_mount_mode_not_explicit_refused(tmp_path, keypair):
    priv, _, _ = keypair
    argv = good_argv(out_spec=f"type=bind,src={OUT_SRC},dst=/out")  # no explicit rw
    with pytest.raises(att.LaunchValidationError, match="OUTPUT_MOUNT_NOT_EXPLICITLY_RW"):
        _build(tmp_path, priv, argv=argv)


# ── blocker 3: closed launch-command grammar, enforced at produce AND exec ───────────────────────
@pytest.mark.parametrize(("argv_kwargs", "match"), [
    ({"extra_opts": ["--privileged"]}, "PRIVILEGED_FORBIDDEN"),
    ({"extra_opts": ["--cap-add=SYS_ADMIN"]}, "OPTION_NOT_IN_CLOSED_GRAMMAR"),
    ({"repo_spec": "type=bind,src=/var/run/docker.sock,dst=/var/run/docker.sock,ro"},
     "MOUNT_DOCKER_SOCKET_FORBIDDEN"),
    ({"repo_spec": "type=bind,src=/data/mr002/repo,dst=/work,rw"}, "INPUT_MOUNT_NOT_READONLY"),
    ({"repo_spec": "type=volume,src=/data/mr002/repo,dst=/work,ro"}, "MOUNT_NOT_BIND"),
    ({"command": ["bash", "-c", "python runner.py"]}, "CONTAINER_COMMAND_NOT_ALLOWED"),
    ({"command": ["sh", "-c", "echo hi"]}, "CONTAINER_COMMAND_NOT_ALLOWED"),
])
def test_blocker3_unsafe_argv_refused(argv_kwargs, match):
    with pytest.raises(att.LaunchValidationError, match=match):
        att.validate_launch_argv(good_argv(**argv_kwargs), image_digest=IMAGE)


def test_blocker3_network_none_required():
    argv = [t for t in good_argv() if t != "--network=none"]
    with pytest.raises(att.LaunchValidationError, match="NETWORK_NONE_REQUIRED"):
        att.validate_launch_argv(argv, image_digest=IMAGE)
    argv2 = [("--network=host" if t == "--network=none" else t) for t in good_argv()]
    with pytest.raises(att.LaunchValidationError, match="NETWORK_NOT_NONE"):
        att.validate_launch_argv(argv2, image_digest=IMAGE)


def test_blocker3_volume_style_mount_refused():
    argv = good_argv(extra_opts=["-v", "/data/x:/x:ro"])
    with pytest.raises(att.LaunchValidationError, match="VOLUME_STYLE_MOUNT_FORBIDDEN"):
        att.validate_launch_argv(argv, image_digest=IMAGE)


def test_blocker3_mutable_tag_image_refused():
    with pytest.raises(att.LaunchValidationError, match="IMAGE_NOT_PINNED_TO_DIGEST"):
        att.validate_launch_argv(good_argv(image="mr002-stage3-qual:3.0"), image_digest=IMAGE)
    # a full digest that does not match the attested image_digest is also refused
    with pytest.raises(att.LaunchValidationError, match="IMAGE_NOT_PINNED_TO_DIGEST"):
        att.validate_launch_argv(good_argv(image="sha256:" + "d" * 64), image_digest=IMAGE)
    # <name>@<attested digest> is the one acceptable named form
    assert att.validate_launch_argv(good_argv(image=f"mr002-stage3-qual@{IMAGE}"),
                                    image_digest=IMAGE) == OUT_IDENTITY


def test_blocker3_required_env_missing_refused():
    argv = [t for t in good_argv() if t != "--env=OPENBLAS_CORETYPE=HASWELL"]
    with pytest.raises(att.LaunchValidationError,
                       match="REQUIRED_ENV_MISSING_OR_WRONG:OPENBLAS_CORETYPE"):
        att.validate_launch_argv(argv, image_digest=IMAGE)
    argv2 = [t.replace("HASWELL", "SKYLAKEX") for t in good_argv()]
    with pytest.raises(att.LaunchValidationError, match="REQUIRED_ENV_MISSING_OR_WRONG"):
        att.validate_launch_argv(argv2, image_digest=IMAGE)


def test_blocker3_env_key_outside_allowlist_refused():
    argv = good_argv(env_extra=["--env=LD_PRELOAD=/tmp/evil.so"])
    with pytest.raises(att.LaunchValidationError, match="ENV_KEY_NOT_ALLOWED:LD_PRELOAD"):
        att.validate_launch_argv(argv, image_digest=IMAGE)


def test_blocker3_produce_refuses_unsafe_argv_before_signing(tmp_path, keypair):
    priv, _, _ = keypair
    with pytest.raises(att.LaunchValidationError, match="PRIVILEGED_FORBIDDEN"):
        _build(tmp_path, priv, argv=good_argv(extra_opts=["--privileged"]))


def test_blocker3_exec_refuses_signed_but_unsafe_command(produced, monkeypatch):
    """A cryptographically VALID attestation over an operationally unsafe argv must be
    refused by exec BEFORE any process is spawned (the launch boundary itself)."""
    from cryptography.hazmat.primitives import serialization
    d = dict(produced["doc"])
    d["exact_command"] = json.dumps(good_argv(extra_opts=["--privileged"]))
    for k in ("signature", "canonical_signed_payload_sha256"):
        d.pop(k)
    key = serialization.load_pem_private_key(produced["priv"].read_bytes(), password=None)
    payload = att.canonical_payload(d)
    d["canonical_signed_payload_sha256"] = hashlib.sha256(payload).hexdigest()
    d["signature"] = base64.b64encode(key.sign(payload)).decode("ascii")
    unsafe = produced["tmp"] / "unsafe_attestation.json"
    unsafe.write_text(json.dumps(d, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    # the frozen loader and the verification tool both accept it — the signature IS valid
    run.load_launch_attestation(str(unsafe), _sha(unsafe))
    receipt = produced["tmp"] / "unsafe_receipt.json"
    assert _run_verify(unsafe, produced["pub"], receipt).returncode == 0
    # ...but exec refuses on the closed grammar, without spawning anything
    def _no_spawn(*a, **k):
        raise AssertionError("exec_attested spawned a process for an unsafe command")
    monkeypatch.setattr(att.subprocess, "run", _no_spawn)
    unsafe_args = type("A", (), {"attestation": str(unsafe), "receipt": str(receipt),
                                 "binding": str(produced["arts"]["binding"])})()
    assert att.exec_attested(unsafe_args) == 2


def test_blocker3_exec_runs_validated_command(produced, monkeypatch):
    receipt = produced["tmp"] / "receipt_exec.json"
    assert _run_verify(produced["path"], produced["pub"], receipt).returncode == 0
    binding = _make_binding(produced, receipt)
    seen = {}
    def _spawn(argv, check):
        seen["argv"] = argv
        return type("R", (), {"returncode": 0})()
    monkeypatch.setattr(att.subprocess, "run", _spawn)
    assert att.exec_attested(_exec_args(produced, receipt, binding)) == 0
    # the executed argv is the attested template + exactly the one derived field
    template = json.loads(produced["doc"]["exact_command"])
    derived = f"--env={att.DERIVED_BINDING_ENV_KEY}={_sha(binding)}"
    assert seen["argv"].count(derived) == 1
    idx = seen["argv"].index(derived)
    assert seen["argv"][:idx] + seen["argv"][idx + 1:] == template


# ── blocker 5: governed-input binding (signed hashes ↔ mounts ↔ env ↔ consumed bytes) ────────────
def test_blocker5_valid_canonical_four_artifact_command(tmp_path, keypair):
    """The canonical command with all four governed inputs correctly bound is ACCEPTED,
    and the derived sources map 1:1 to the mounted files."""
    priv, _, _ = keypair
    doc, arts = _build(tmp_path, priv)
    srcs = att.governed_input_sources(json.loads(doc["exact_command"]), image_digest=IMAGE)
    by_kwarg = _stub_input_srcs(arts)
    expected = {env_key: by_kwarg[kwarg] for _, env_key, _, kwarg in att.GOVERNED_INPUTS}
    assert srcs == expected
    for hash_field, env_key, _, _ in att.GOVERNED_INPUTS:
        assert doc[hash_field] == _sha(srcs[env_key])  # signed hash == mounted bytes


@pytest.mark.parametrize("kwarg", sorted(KWARG_BY_ART.values()))
def test_blocker5_mount_source_mismatch_refused_per_artifact(tmp_path, keypair, kwarg):
    """For EVERY governed artifact: hashing host file A while mounting host file B at its
    fixed destination is refused."""
    priv, _, _ = keypair
    arts = _stub_artifacts(tmp_path)
    other = tmp_path / "other.json"
    other.write_text("{\"stub\": \"other\"}", encoding="utf-8")
    srcs = _stub_input_srcs(arts)
    srcs[kwarg] = _posix(other)  # mounted file != hashed file
    with pytest.raises(att.LaunchValidationError, match="GOVERNED_INPUT_SOURCE_MISMATCH"):
        _build(tmp_path, priv, argv=argv_for(arts, input_srcs=srcs), arts=arts)


def test_blocker5_missing_governed_mount_refused(tmp_path, keypair):
    priv, _, _ = keypair
    argv = good_argv(drop_input="expected_pins_path")
    with pytest.raises(att.LaunchValidationError,
                       match="GOVERNED_INPUT_MOUNT_MISSING:/inputs/expected_pins.json"):
        _build(tmp_path, priv, argv=argv)


def test_blocker5_writable_governed_mount_refused(tmp_path, keypair):
    priv, _, _ = keypair
    argv = good_argv(input_mode="rw")
    with pytest.raises(att.LaunchValidationError, match="INPUT_MOUNT_NOT_READONLY"):
        _build(tmp_path, priv, argv=argv)


def test_blocker5_duplicate_destination_refused():
    argv = good_argv(extra_opts=[
        "--mount", "type=bind,src=/data/second/authorization.json,dst=/inputs/authorization.json,ro"])
    with pytest.raises(att.LaunchValidationError,
                       match="MOUNT_DST_DUPLICATE:/inputs/authorization.json"):
        att.validate_launch_argv(argv, image_digest=IMAGE)


def test_blocker5_env_path_mismatch_refused():
    argv = good_argv(governed_env={"MR002_EXPECTED_PINS": "/inputs/wrong.json"})
    with pytest.raises(att.LaunchValidationError,
                       match="GOVERNED_ENV_MISSING_OR_WRONG:MR002_EXPECTED_PINS"):
        att.validate_launch_argv(argv, image_digest=IMAGE)


def test_blocker5_inputs_shadow_mount_refused():
    argv = good_argv(extra_opts=["--mount", "type=bind,src=/data/shadow,dst=/inputs,ro"])
    with pytest.raises(att.LaunchValidationError, match="INPUTS_SHADOW_MOUNT_FORBIDDEN:/inputs"):
        att.validate_launch_argv(argv, image_digest=IMAGE)


def test_blocker5_governed_input_under_output_mount_refused():
    srcs = {"authorization_path": f"{OUT_SRC}/authorization.json"}
    argv = good_argv(input_srcs=srcs)
    with pytest.raises(att.LaunchValidationError, match="GOVERNED_INPUT_UNDER_OUTPUT_MOUNT"):
        att.validate_launch_argv(argv, image_digest=IMAGE)


def test_blocker5_symlink_governed_source_refused(tmp_path, keypair):
    priv, _, _ = keypair
    arts = _stub_artifacts(tmp_path)
    link = tmp_path / "authorization_link.json"
    os.symlink(str(arts["authorization"]), str(link))
    srcs = _stub_input_srcs(arts)
    srcs["authorization_path"] = _posix(link)
    with pytest.raises(att.LaunchValidationError, match="GOVERNED_INPUT_SYMLINK_SOURCE"):
        _build(tmp_path, priv, argv=argv_for(arts, input_srcs=srcs), arts=arts)


def test_blocker5_exec_refuses_substituted_input_bytes(produced, monkeypatch):
    """After a valid attestation, the mounted governed file's bytes change: exec must
    re-hash the attested mount source and refuse — the signature alone is not enough."""
    receipt = produced["tmp"] / "receipt_subst.json"
    assert _run_verify(produced["path"], produced["pub"], receipt).returncode == 0
    binding = _make_binding(produced, receipt)
    produced["arts"]["pins"].write_text("{\"stub\": \"SUBSTITUTED\"}", encoding="utf-8")
    def _no_spawn(*a, **k):
        raise AssertionError("exec_attested spawned despite substituted input bytes")
    monkeypatch.setattr(att.subprocess, "run", _no_spawn)
    assert att.exec_attested(_exec_args(produced, receipt, binding)) == 2


# ── blocker 6: finite environment grammar (no MR002_* wildcard) ──────────────────────────────────
def test_blocker6_unknown_mr002_env_refused():
    argv = good_argv(env_extra=["--env=MR002_SOMETHING=/tmp/unreviewed"])
    with pytest.raises(att.LaunchValidationError, match="ENV_KEY_NOT_ALLOWED:MR002_SOMETHING"):
        att.validate_launch_argv(argv, image_digest=IMAGE)


def test_blocker6_duplicate_governed_env_refused():
    argv = good_argv(env_extra=["--env=MR002_EXPECTED_PINS=/inputs/expected_pins.json"])
    with pytest.raises(att.LaunchValidationError, match="ENV_KEY_DUPLICATE:MR002_EXPECTED_PINS"):
        att.validate_launch_argv(argv, image_digest=IMAGE)


def test_blocker6_pythonpath_rules():
    # exact approved value accepted (the canonical form)
    assert att.validate_launch_argv(good_argv(), image_digest=IMAGE) == OUT_IDENTITY
    # absent refused — the registered runner imports app.research.mr002.* with no
    # sys.path bootstrap, so PYTHONPATH is demonstrably required (pinned by design)
    with pytest.raises(att.LaunchValidationError,
                       match="REQUIRED_ENV_MISSING_OR_WRONG:PYTHONPATH=None"):
        att.validate_launch_argv(good_argv(pythonpath=None), image_digest=IMAGE)
    # unexpected value refused
    with pytest.raises(att.LaunchValidationError,
                       match="REQUIRED_ENV_MISSING_OR_WRONG:PYTHONPATH=/tmp/evil"):
        att.validate_launch_argv(good_argv(pythonpath="/tmp/evil"), image_digest=IMAGE)


def test_blocker6_mr002_out_refused():
    """Alternate output/checkpoint locations are refused — the runner uses its default
    under the governed rw /out mount."""
    argv = good_argv(env_extra=["--env=MR002_OUT=/tmp/alternate"])
    with pytest.raises(att.LaunchValidationError, match="ENV_KEY_NOT_ALLOWED:MR002_OUT"):
        att.validate_launch_argv(argv, image_digest=IMAGE)


def test_blocker6_sha_channel_not_hex_refused():
    argv = good_argv(countersign_sha="not-a-hash")
    with pytest.raises(att.LaunchValidationError,
                       match="ENV_NOT_HEX64:MR002_EXECUTION_COUNTERSIGN_SHA256"):
        att.validate_launch_argv(argv, image_digest=IMAGE)
    argv2 = good_argv(countersign_sha="E" * 64)  # uppercase is not canonical hex
    with pytest.raises(att.LaunchValidationError,
                       match="ENV_NOT_HEX64:MR002_EXECUTION_COUNTERSIGN_SHA256"):
        att.validate_launch_argv(argv2, image_digest=IMAGE)


def test_blocker6_artifact_env_wrong_path_refused():
    argv = good_argv(governed_env={"MR002_REALISM_PASS": "/inputs/other.json"})
    with pytest.raises(att.LaunchValidationError,
                       match="GOVERNED_ENV_MISSING_OR_WRONG:MR002_REALISM_PASS"):
        att.validate_launch_argv(argv, image_digest=IMAGE)


def test_blocker6_artifact_mount_missing_refused():
    argv = good_argv(drop_artifact="MR002_REALISM_PASS")
    with pytest.raises(att.LaunchValidationError,
                       match="GOVERNED_INPUT_MOUNT_MISSING:/inputs/realism_pass.json"):
        att.validate_launch_argv(argv, image_digest=IMAGE)


def test_blocker6_produce_countersign_sha_mismatch_refused(tmp_path, keypair):
    """A countersign hash channel that does not equal the OBSERVED authorization hash is
    refused before signing — the channel cannot diverge from the attested artifact."""
    priv, _, _ = keypair
    arts = _stub_artifacts(tmp_path)
    argv = argv_for(arts, countersign_sha="e" * 64)  # valid format, wrong value
    with pytest.raises(att.LaunchValidationError, match="ENV_COUNTERSIGN_SHA_MISMATCH"):
        _build(tmp_path, priv, argv=argv, arts=arts)


# ── blocker 8: the binding-hash cycle — template + one launcher-derived field ────────────────────
def test_blocker8_attestation_template_carries_no_binding_hash(produced):
    """Attestation production requires no binding hash: the signed template must not
    contain the launcher-derived key, and supplying one is refused as an unknown key."""
    template = json.loads(produced["doc"]["exact_command"])
    assert not any(att.DERIVED_BINDING_ENV_KEY in t for t in template)
    argv = good_argv(env_extra=[f"--env={att.DERIVED_BINDING_ENV_KEY}={'e' * 64}"])
    with pytest.raises(att.LaunchValidationError,
                       match=f"ENV_KEY_NOT_ALLOWED:{att.DERIVED_BINDING_ENV_KEY}"):
        att.validate_launch_argv(argv, image_digest=IMAGE)


def test_blocker8_operator_supplied_binding_hash_refused_at_produce(tmp_path, keypair):
    priv, _, _ = keypair
    arts = _stub_artifacts(tmp_path)
    argv = argv_for(arts, env_extra=[f"--env={att.DERIVED_BINDING_ENV_KEY}={'e' * 64}"])
    with pytest.raises(att.LaunchValidationError,
                       match=f"ENV_KEY_NOT_ALLOWED:{att.DERIVED_BINDING_ENV_KEY}"):
        _build(tmp_path, priv, argv=argv, arts=arts)


def test_blocker8_operator_supplied_binding_hash_refused_at_exec(produced, monkeypatch):
    """A cryptographically VALID attestation whose template smuggles an operator-supplied
    binding hash is refused at exec before any spawn."""
    from cryptography.hazmat.primitives import serialization
    d = dict(produced["doc"])
    template = json.loads(d["exact_command"])
    idx = template.index("--workdir=/work/apps/backend")
    template.insert(idx, f"--env={att.DERIVED_BINDING_ENV_KEY}={'e' * 64}")
    d["exact_command"] = json.dumps(template)
    for k in ("signature", "canonical_signed_payload_sha256"):
        d.pop(k)
    key = serialization.load_pem_private_key(produced["priv"].read_bytes(), password=None)
    payload = att.canonical_payload(d)
    d["canonical_signed_payload_sha256"] = hashlib.sha256(payload).hexdigest()
    d["signature"] = base64.b64encode(key.sign(payload)).decode("ascii")
    smuggled = produced["tmp"] / "smuggled_attestation.json"
    smuggled.write_text(json.dumps(d, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    receipt = produced["tmp"] / "receipt_smuggled.json"
    assert _run_verify(smuggled, produced["pub"], receipt).returncode == 0
    def _no_spawn(*a, **k):
        raise AssertionError("exec spawned despite operator-supplied binding hash")
    monkeypatch.setattr(att.subprocess, "run", _no_spawn)
    args = type("A", (), {"attestation": str(smuggled), "receipt": str(receipt),
                          "binding": str(produced["arts"]["binding"])})()
    assert att.exec_attested(args) == 2


def test_blocker8_end_to_end_construction_order(produced, monkeypatch):
    """The real sequence with real artifact hashes: authorization (pre-existing stub) →
    attestation → receipt → execution binding (assembled AFTER both, binding their actual
    hashes) → exec validation. The derived hash comes from the actual mounted bytes and
    is injected exactly once; the executed argv differs from the attested template by
    only that field."""
    receipt = produced["tmp"] / "receipt_e2e.json"
    assert _run_verify(produced["path"], produced["pub"], receipt).returncode == 0
    binding = _make_binding(produced, receipt)  # only NOW constructible — no cycle
    seen = {}
    def _spawn(argv, check):
        seen["argv"] = argv
        return type("R", (), {"returncode": 0})()
    monkeypatch.setattr(att.subprocess, "run", _spawn)
    assert att.exec_attested(_exec_args(produced, receipt, binding)) == 0
    template = json.loads(produced["doc"]["exact_command"])
    derived = f"--env={att.DERIVED_BINDING_ENV_KEY}={_sha(binding)}"
    assert seen["argv"].count(derived) == 1                       # injected exactly once
    idx = seen["argv"].index(derived)
    assert seen["argv"][:idx] + seen["argv"][idx + 1:] == template  # only that field


def test_blocker8_substituted_binding_mount_bytes_refused(produced, monkeypatch):
    """The injected hash must correspond to the bytes at the attested mount source: if
    the mounted copy diverges from the --binding bytes, exec refuses."""
    receipt = produced["tmp"] / "receipt_bsub.json"
    assert _run_verify(produced["path"], produced["pub"], receipt).returncode == 0
    binding = _make_binding(produced, receipt)
    real_bytes = binding.read_bytes()
    aside = produced["tmp"] / "binding_aside.json"
    aside.write_bytes(real_bytes)                      # --binding keeps the real bytes
    binding.write_text("{\"stub\": \"SUBSTITUTED\"}", encoding="utf-8")  # mounted copy diverges
    def _no_spawn(*a, **k):
        raise AssertionError("exec spawned despite substituted mounted binding bytes")
    monkeypatch.setattr(att.subprocess, "run", _no_spawn)
    assert att.exec_attested(_exec_args(produced, receipt, aside)) == 2


def test_blocker8_tampered_binding_cross_validation_refused(produced, monkeypatch):
    """A binding whose attestation hash does not match the actual attestation bytes is
    refused by the exec cross-validation (the frozen loader's schema alone would pass)."""
    receipt = produced["tmp"] / "receipt_btamper.json"
    assert _run_verify(produced["path"], produced["pub"], receipt).returncode == 0
    binding = _make_binding(produced, receipt)
    b = json.loads(binding.read_text(encoding="utf-8"))
    b["launch_attestation_sha256"] = "f" * 64
    binding.write_text(json.dumps(b, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    def _no_spawn(*a, **k):
        raise AssertionError("exec spawned despite tampered binding cross-hashes")
    monkeypatch.setattr(att.subprocess, "run", _no_spawn)
    assert att.exec_attested(_exec_args(produced, receipt, binding)) == 2


# ── blocker 7: the container command is closed to the exact registered entrypoint ────────────────
def test_blocker7_exact_registered_command_accepted():
    assert att.validate_launch_argv(good_argv(), image_digest=IMAGE) == OUT_IDENTITY
    assert att.validate_launch_argv(
        good_argv(command=["python3", att.REGISTERED_ENTRYPOINT]),
        image_digest=IMAGE) == OUT_IDENTITY


@pytest.mark.parametrize(("command", "match"), [
    (["python", "-c", "print(1)"], "CONTAINER_COMMAND_NOT_REGISTERED"),
    (["python", "-m", "scripts.mr002_stage3_population_runner"],
     "CONTAINER_COMMAND_NOT_REGISTERED"),
    (["python", "scripts/unrelated_script.py"], "CONTAINER_COMMAND_NOT_REGISTERED"),
    (["python", "scripts/mr002_stage3_population_runner.py", "--unreviewed-option"],
     "CONTAINER_COMMAND_NOT_REGISTERED"),
    (["python", "scripts/mr002_stage3_population_runner.py", "--window=validation"],
     "CONTAINER_COMMAND_NOT_REGISTERED"),
    (["python", "scripts/mr002_stage3_population_runner.py", "extra_positional"],
     "CONTAINER_COMMAND_NOT_REGISTERED"),
])
def test_blocker7_non_registered_commands_refused(command, match):
    with pytest.raises(att.LaunchValidationError, match=match):
        att.validate_launch_argv(good_argv(command=command), image_digest=IMAGE)


# ── hardening: explicit Ed25519 key-type enforcement + 0600 private key ──────────────────────────
def _rsa_keypair(tmp_path):
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    priv = tmp_path / "rsa.pem"
    pub = tmp_path / "rsa.pub.pem"
    priv.write_bytes(key.private_bytes(
        encoding=serialization.Encoding.PEM, format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption()))
    pub.write_bytes(key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo))
    return priv, pub


def test_hardening_rsa_private_key_refused_by_producer(tmp_path):
    priv, _ = _rsa_keypair(tmp_path)
    with pytest.raises(att.LaunchValidationError, match="PRIVATE_KEY_NOT_ED25519"):
        _build(tmp_path, priv)


def test_hardening_rsa_public_key_refused_by_verifier(produced, tmp_path):
    _, rsa_pub = _rsa_keypair(tmp_path)
    receipt = produced["tmp"] / "receipt_rsa.json"
    res = _run_verify(produced["path"], rsa_pub, receipt)
    assert res.returncode == 5
    assert "not Ed25519" in res.stderr
    assert not receipt.exists()


def test_hardening_rsa_public_key_refused_for_key_id(tmp_path):
    _, rsa_pub = _rsa_keypair(tmp_path)
    with pytest.raises(att.LaunchValidationError, match="PUBLIC_KEY_NOT_ED25519"):
        att.key_id_for_public_pem(rsa_pub.read_bytes())


def test_hardening_private_key_created_mode_0600(tmp_path, monkeypatch):
    captured = {}
    real_open = os.open
    def _capture(path, flags, mode=0o777):
        if str(path).endswith("launcher_ed25519.pem"):
            captured["mode"] = mode
            captured["excl"] = bool(flags & os.O_EXCL)
        return real_open(path, flags, mode)
    monkeypatch.setattr(os, "open", _capture)
    att.generate_keypair(str(tmp_path / "k" / "launcher_ed25519.pem"),
                         str(tmp_path / "k" / "launcher_ed25519.pub.pem"))
    assert captured == {"mode": 0o600, "excl": True}


def test_hardening_keygen_refuses_existing_symlink(tmp_path):
    priv = tmp_path / "keys" / "launcher_ed25519.pem"
    priv.parent.mkdir()
    os.symlink(str(tmp_path / "elsewhere.pem"), str(priv))  # dangling symlink
    with pytest.raises(SystemExit, match="REFUSED"):
        att.generate_keypair(str(priv), str(tmp_path / "keys" / "pub.pem"))


# ── final-test-report generator × frozen loader ──────────────────────────────────────────────────
def _synthetic_outcomes(fail_one: bool = False) -> dict[str, str]:
    outcomes = {}
    for mod in run.FINAL_REPORT_REQUIRED_MODULES:
        for i in range(30):
            outcomes[f"{mod}::test_synth_{i}"] = "passed"
    outcomes[run.PRODUCTION_BINDING_TEST_ID] = "passed"
    if fail_one:
        outcomes[next(iter(outcomes))] = "failed"
    return outcomes


def _identities(arts) -> dict:
    return {"bound_commit": "a" * 40, "bound_tree": "b" * 40,
            "image_digest": IMAGE, "oci_config_digest": IMAGE,
            "source_manifest_sha256": _sha(arts["manifest"]),
            "expected_pins_sha256": _sha(arts["pins"]),
            "execution_package_sha256": _sha(arts["package"]),
            "working_tree_dirty": False}


def _binding_view(ids: dict) -> dict:
    b = {k: ids[k] for k in ("bound_commit", "bound_tree", "image_digest", "oci_config_digest",
                             "expected_pins_sha256", "execution_package_sha256")}
    b["implementation_manifest_sha256"] = ids["source_manifest_sha256"]
    return b


def test_final_report_accepted_by_frozen_loader(produced, tmp_path):
    ids = _identities(produced["arts"])
    doc = build_report(outcomes=_synthetic_outcomes(), exit_code=0, identities=ids)
    assert doc["admissible_as_final"] is True
    assert doc["collected_passed"] == len(doc["test_results"])
    path = tmp_path / "report.json"
    path.write_text(json.dumps(doc, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    loaded = run.load_final_test_report(str(path), _sha(path), binding=_binding_view(ids))
    assert loaded["production_binding_outcome"] == "passed"


def test_final_report_failed_test_refused(produced, tmp_path):
    ids = _identities(produced["arts"])
    doc = build_report(outcomes=_synthetic_outcomes(fail_one=True), exit_code=1, identities=ids)
    assert doc["admissible_as_final"] is False
    path = tmp_path / "report_fail.json"
    path.write_text(json.dumps(doc, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    with pytest.raises(run.Stage3RunRefused):
        run.load_final_test_report(str(path), _sha(path))


def test_final_report_dirty_tree_refused(produced, tmp_path):
    ids = _identities(produced["arts"])
    ids["working_tree_dirty"] = True
    doc = build_report(outcomes=_synthetic_outcomes(), exit_code=0, identities=ids)
    assert doc["admissible_as_final"] is False
    path = tmp_path / "report_dirty.json"
    path.write_text(json.dumps(doc, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    with pytest.raises(run.Stage3RunRefused, match="TEST_REPORT_DIRTY_TREE"):
        run.load_final_test_report(str(path), _sha(path))
