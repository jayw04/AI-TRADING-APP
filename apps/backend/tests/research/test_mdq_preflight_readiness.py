"""Regression tests for the MDQ-001 acquisition-readiness preflight control.

The 2026-08-24 capture non-event happened because a preflight checked only the
remembered leg (free space) while a different gate -- absent acquisition
credentials -- was the one that fail-closed. These tests pin the properties
that make the replacement control trustworthy:

  * the gate chain runs in the collector's real order;
  * ANY required gate failing yields NOT READY / exit 1;
  * gate 3 is NOT EVALUABLE (not "pass", not "skipped") when gate 2 prevents
    identity resolution;
  * no secret value is ever printed;
  * the governed universe pin cannot be satisfied by a mismatching artifact.

The container, disk and process interactions are stubbed on PATH. The universe
artifact is NOT stubbed -- the tests use the repository's real governed file,
so the pin is exercised rather than weakened.
"""

from __future__ import annotations

import pathlib
import shutil
import subprocess

import pytest

# apps/backend/tests/research/this_file.py -> repo root is parents[4]
ROOT = pathlib.Path(__file__).resolve().parents[4]
SCRIPT = ROOT / "apps" / "backend" / "scripts" / "mdq_preflight_readiness.sh"
GOVERNED_UNIVERSE = ROOT / "apps" / "backend" / "config" / "mdq_phase_a_universe_symbols.json"

# The pin the deployed wrapper and the script both carry.
UNIVERSE_SHA = "0c57bd71c0b73565328ec27036c6573f11b87594acb49ca461458a7d947f88d4"


def _resolve_bash() -> str | None:
    """Find a bash that can actually execute a script.

    Mirrors test_adr_0002_invariant / test_isolation_invariants: a stub `bash`
    on PATH (e.g. a WSL launcher) returns success without running anything and
    produces spurious failures, so probe before trusting it.
    """
    candidates = [
        shutil.which("bash"),
        r"C:\Program Files\Git\bin\bash.exe",
        r"C:\Program Files\Git\usr\bin\bash.exe",
        "/bin/bash",
        "/usr/bin/bash",
    ]
    for candidate in candidates:
        if not candidate or not pathlib.Path(candidate).exists():
            continue
        try:
            probe = subprocess.run(
                [candidate, "-c", "printf ok"],
                capture_output=True,
                text=True,
                timeout=30,
            )
        except (OSError, subprocess.TimeoutExpired):
            continue
        if probe.returncode == 0 and "ok" in (probe.stdout or ""):
            return candidate
    return None


def _write_exec(path: pathlib.Path, body: str) -> None:
    path.write_text(body, encoding="utf-8", newline="\n")
    path.chmod(0o755)


@pytest.fixture
def rig(tmp_path: pathlib.Path):
    """Build a stubbed environment: real universe artifact, fake docker/df/pgrep."""
    root_host = tmp_path / "data"
    (root_host / "mdq_config").mkdir(parents=True)

    # The REAL governed artifact, LF-normalised (the pin is over LF bytes).
    universe = GOVERNED_UNIVERSE.read_bytes().replace(b"\r\n", b"\n")
    (root_host / "mdq_config" / "mdq_phase_a_universe_symbols.json").write_bytes(universe)

    stub_bin = tmp_path / "bin"
    stub_bin.mkdir()

    _write_exec(
        stub_bin / "docker",
        """#!/bin/sh
# args: exec <container> sh -c <script> | exec <container> python -c <py> | inspect ...
case "$1" in
  cp) cat "$STUB_CP_TAR"; exit 0 ;;
  inspect)
    for a in "$@"; do
      case "$a" in
        *.Id*)      echo "$STUB_CONTAINER_ID"; exit 0 ;;
        *.Image*)   echo "$STUB_IMAGE_ID"; exit 0 ;;
        *.Created*) echo "2026-08-26T20:23:48Z"; exit 0 ;;
      esac
    done
    echo "stub-inspect-value"; exit 0 ;;
esac
for a in "$@"; do
  case "$a" in
    python) MODE=python ;;
    sh) MODE=${MODE:-sh} ;;
  esac
done
if [ "$MODE" = "python" ]; then
  if [ "$STUB_LATCH" = "pass" ]; then
    echo "pinned_fingerprint b56421a28128"
    echo "pinned_account PA3BGKRLH2AP"
    echo "resolved_fingerprint b56421a28128"
    echo "latch PASS PA3BGKRLH2AP"
  else
    echo "pinned_fingerprint b56421a28128"
    echo "pinned_account PA3BGKRLH2AP"
    echo "resolved_fingerprint 5b6f39e5198d"
    echo "latch FAIL IdentityError credential fingerprint 5b6f39e5198d != pinned b56421a28128"
  fi
  exit 0
fi
if [ "$STUB_CREDS" = "present" ]; then
  echo "ALPACA_PAPER_6_API_KEY SET 26"
  echo "ALPACA_PAPER_6_API_SECRET SET 44"
else
  echo "ALPACA_PAPER_6_API_KEY ABSENT"
  echo "ALPACA_PAPER_6_API_SECRET ABSENT"
fi
exit 0
""",
    )

    _write_exec(
        stub_bin / "df",
        """#!/bin/sh
unit=1G
for a in "$@"; do
  case "$a" in
    -B1G) unit=1G ;;
    -B1) unit=1 ;;
    --output=size) FIELD=size ;;
    --output=avail) FIELD=avail ;;
  esac
done
if [ "$unit" = "1G" ]; then
  if [ "$FIELD" = "size" ]; then echo "Size"; echo "$STUB_SIZE_GB";
  else echo "Avail"; echo "$STUB_AVAIL_GB"; fi
else
  if [ "$FIELD" = "size" ]; then echo "Size"; echo "$(( STUB_SIZE_GB * 1073741824 ))";
  else echo "Avail"; echo "$(( STUB_AVAIL_GB * 1073741824 ))"; fi
fi
exit 0
""",
    )

    _write_exec(
        stub_bin / "pgrep",
        """#!/bin/sh
echo "${STUB_SAMPLERS:-0}"
exit 0
""",
    )

    # ---- gate 6 fixture: a self-consistent deployment tuple -------------------------------------
    # Gate 6 is fail-closed by version, so the healthy stub must satisfy it or every other test would
    # be asserting against a NOT READY run for an unrelated reason.
    import hashlib
    import json as _json
    import sys as _sys
    import tarfile as _tarfile

    _sys.path.insert(0, str(SCRIPT.resolve().parents[1]))
    from app.validation.deployment_identity import derive_runtime_code_digest

    app_dir = tmp_path / "opt_app"
    (app_dir / "apps/backend/scripts").mkdir(parents=True)
    # ⭐ Nothing points Gate 6 at a helper: it resolves its own sibling, so the tests exercise the REAL
    # attestation implementation through the same version-bound path production uses.

    container_code = tmp_path / "container_app"
    (container_code / "validation").mkdir(parents=True)
    (container_code / "main.py").write_text("V = 1\n", encoding="utf-8")
    (container_code / "validation" / "thing.py").write_text("X = 2\n", encoding="utf-8")
    code_digest = derive_runtime_code_digest(container_code)

    # `docker cp <c>:/app/app -` roots its entries at `app/`.
    cp_tar = tmp_path / "cp.tar"
    with _tarfile.open(cp_tar, "w") as _archive:
        _archive.add(container_code, arcname="app")

    stub_commit = "c" * 40
    stub_container_id = "stubcontainerid0000000000000000000000000000000000000000000000000"
    stub_image_id = "sha256:" + "e" * 64

    marker = app_dir / "DEPLOYED_BUILD_INFO.json"
    marker.write_text(_json.dumps({
        "schema": "workbench-deployed-build-info/2",
        "commit": stub_commit, "tree_clean": True, "code_digest": code_digest,
    }, indent=2, sort_keys=True), encoding="utf-8")

    (app_dir / "DEPLOYMENT_RUNTIME_MANIFEST.json").write_text(_json.dumps({
        "schema": "workbench-deployment-runtime-manifest/1",
        "commit": stub_commit, "code_digest": code_digest,
        "image_digest": stub_image_id, "container_id": stub_container_id,
        "container_created": "2026-08-26T20:23:48Z",
        "build_info_sha256": hashlib.sha256(marker.read_bytes()).hexdigest(),
        "deployed_at_utc": "2026-08-26T20:24:00Z",
    }, indent=2, sort_keys=True), encoding="utf-8")

    def run(**overrides) -> subprocess.CompletedProcess[str]:
        bash = _resolve_bash()
        if bash is None:
            pytest.skip("no usable bash on PATH")
        import os

        env = dict(os.environ)
        env["PATH"] = f"{stub_bin}{os.pathsep}{env['PATH']}"
        env["MDQ_ROOT_HOST"] = str(root_host)
        env["MDQ_CONTAINER"] = "stub-container"
        env["MDQ_DEPLOY_SHA_FILE"] = str(tmp_path / "nonexistent-sha")
        env["MDQ_ENV_FILE"] = str(tmp_path / "nonexistent-env")
        env["MDQ_APP_DIR"] = str(app_dir)
        env["STUB_CP_TAR"] = str(cp_tar)
        env["STUB_CONTAINER_ID"] = stub_container_id
        env["STUB_IMAGE_ID"] = stub_image_id
        env.setdefault("STUB_CREDS", "present")
        env.setdefault("STUB_LATCH", "pass")
        env.setdefault("STUB_SIZE_GB", "58")
        env.setdefault("STUB_AVAIL_GB", "27")
        env.setdefault("STUB_SAMPLERS", "0")
        # Pop argv BEFORE folding overrides into the environment, or it lands there as a stray var.
        argv = overrides.pop("_argv", [])
        env.update({k: str(v) for k, v in overrides.items()})
        return subprocess.run(
            [bash, str(SCRIPT), *argv], capture_output=True, text=True, timeout=120, env=env
        )

    run.root_host = root_host  # type: ignore[attr-defined]
    return run


def test_script_exists_and_is_posix_sh():
    assert SCRIPT.is_file(), f"missing preflight control at {SCRIPT}"
    assert SCRIPT.read_bytes().startswith(b"#!/bin/sh")


def test_governed_universe_artifact_still_matches_the_pin():
    """If this fails, the pin in the script and the artifact have diverged."""
    import hashlib

    lf = GOVERNED_UNIVERSE.read_bytes().replace(b"\r\n", b"\n")
    assert hashlib.sha256(lf).hexdigest() == UNIVERSE_SHA


def test_all_gates_pass_is_ready(rig):
    r = rig()
    assert r.returncode == 0, r.stdout
    # Gate 6 is governing and fail-closed by version, so a healthy deployment is a SIX-gate READY.
    # There is deliberately no switch that would let five gates print READY.
    assert "=== READY - all six gates pass ===" in r.stdout
    for gate in ("[1]", "[2]", "[3]", "[4]", "[5]"):
        assert gate in r.stdout
    assert "NOT READY" not in r.stdout


def test_gate_order_is_the_collectors_real_order(rig):
    r = rig()
    out = r.stdout
    positions = [out.index(f"[{i}]") for i in range(1, 6)]
    assert positions == sorted(positions), "gates must run in order 1..5"
    assert out.index("UNIVERSE PIN") < out.index("ACQUISITION CREDENTIAL PRESENCE")
    assert out.index("ACQUISITION CREDENTIAL PRESENCE") < out.index("ACCOUNT-IDENTITY LATCH")
    assert out.index("ACCOUNT-IDENTITY LATCH") < out.index("FREE-SPACE FLOOR")
    assert out.index("FREE-SPACE FLOOR") < out.index("SINGLE-INSTANCE STATE")


def test_missing_credential_fails_and_makes_latch_not_evaluable(rig):
    """The exact 2026-08-24 failure."""
    r = rig(STUB_CREDS="absent")
    assert r.returncode == 1
    assert "ALPACA_PAPER_6_API_KEY ABSENT" in r.stdout
    assert "NOT EVALUABLE" in r.stdout, "gate 3 must not silently pass or skip"
    assert "latch PASS" not in r.stdout
    assert "NOT READY" in r.stdout


def test_missing_credential_warns_against_unnumbered_substitution(rig):
    """Substituting the unnumbered pair is a governance change, not a repair."""
    r = rig(STUB_CREDS="absent")
    assert "DO NOT substitute the unnumbered ALPACA_PAPER_* pair" in r.stdout


def test_wrong_fingerprint_fails_the_latch(rig):
    r = rig(STUB_LATCH="fail")
    assert r.returncode == 1
    assert "latch FAIL" in r.stdout
    assert "resolved credential is not the pinned acquisition identity" in r.stdout
    assert "NOT READY" in r.stdout


def test_universe_pin_mismatch_fails(rig):
    target = rig.root_host / "mdq_config" / "mdq_phase_a_universe_symbols.json"
    target.write_bytes(b'["AAPL"]\n')
    r = rig()
    assert r.returncode == 1
    assert "pin mismatch" in r.stdout
    assert "NOT READY" in r.stdout


def test_absent_universe_artifact_fails(rig):
    (rig.root_host / "mdq_config" / "mdq_phase_a_universe_symbols.json").unlink()
    r = rig()
    assert r.returncode == 1
    assert "universe artifact absent" in r.stdout


def test_disk_breach_fails(rig):
    """58 GiB volume -> floor = 58/5 = 11; avail 10 breaches."""
    r = rig(STUB_AVAIL_GB="10")
    assert r.returncode == 1
    assert "floor breach" in r.stdout
    assert "floor=11" in r.stdout
    assert "NOT READY" in r.stdout


def test_disk_floor_uses_integer_division_and_ten_gib_minimum(rig):
    """A small volume pins the floor at the fixed 10 GiB leg, not size/5."""
    r = rig(STUB_SIZE_GB="29", STUB_AVAIL_GB="11")
    assert "floor=10" in r.stdout, r.stdout
    assert r.returncode == 0


def test_sampler_already_running_fails(rig):
    r = rig(STUB_SAMPLERS="1")
    assert r.returncode == 1
    assert "conflicting sampler" in r.stdout
    assert "NOT READY" in r.stdout


def test_any_single_gate_failure_yields_not_ready(rig):
    """No gate is advisory: each one alone flips the overall verdict."""
    for overrides in (
        {"STUB_CREDS": "absent"},
        {"STUB_LATCH": "fail"},
        {"STUB_AVAIL_GB": "10"},
        {"STUB_SAMPLERS": "2"},
    ):
        r = rig(**overrides)
        assert r.returncode == 1, f"{overrides} should fail-close: {r.stdout}"
        assert "NOT READY" in r.stdout


def test_no_secret_material_is_printed(rig):
    """Only presence/length and the non-secret fingerprint form may appear."""
    r = rig()
    out = r.stdout
    assert "SET 26" in out and "SET 44" in out
    # The fingerprint is the sanctioned non-secret form; raw key/secret are not.
    assert "b56421a28128" in out
    for forbidden in ("APCA-API-SECRET-KEY", "api_secret=", "-----BEGIN"):
        assert forbidden not in out


def _script_body() -> str:
    return SCRIPT.read_text(encoding="utf-8")


def _executable_lines(body: str) -> list[str]:
    """Lines that actually run — comments explain the rules and must not be mistaken for breaking them."""
    return [line for line in body.splitlines() if not line.lstrip().startswith("#")]


def _gate6_block(body: str) -> str:
    start = body.index("gate 6 ")
    end = body.index("# ------------------------------------------------------------- context ------")
    return body[start:end]


def test_control_is_read_only_no_repair_paths():
    """The control reports; it must never mutate or self-heal."""
    body = _script_body()
    for mutating in ("systemctl start", "systemctl restart", "rm -", "> $ROOT_HOST"):
        assert mutating not in body, f"preflight must not perform {mutating!r}"


def test_every_docker_cp_is_the_read_only_out_form():
    """`docker cp` was previously banned outright as a mutating verb, which was the right instinct:
    its usual direction writes INTO a container. Gate 6 needs the opposite direction --
    `docker cp <container>:/app/app -` streams bytes OUT to stdout and touches nothing.

    So the ban is narrowed rather than dropped: every executable occurrence must be the
    container-to-stdout form. A `docker cp` whose destination is a container path is still a repair path.
    """
    import re
    occurrences = [line for line in _executable_lines(_script_body()) if "docker cp" in line]
    assert occurrences, "gate 6 should read the runtime via docker cp"
    for line in occurrences:
        assert re.search(r'docker cp "\$CONTAINER":\S+ -', line), (
            f"docker cp must be the read-only container-to-stdout form, got: {line!r}")


def test_gate6_derives_the_runtime_code_without_executing_container_userland():
    """The attestation must not ask the suspect to describe itself: a wrong or hostile image carries
    wrong code AND a matching self-description, so `docker exec ... sha256sum` would look perfect.

    Scoped to Gate 6 deliberately. Gates 2 and 3 legitimately use `docker exec` to read the container's
    environment and broker identity -- those are questions only the container can answer, and they are
    not the question Gate 6 asks.
    """
    gate6 = _gate6_block(_script_body())
    assert "docker cp" in gate6
    for line in _executable_lines(gate6):
        assert "docker exec" not in line, (
            f"gate 6 must derive runtime code via the daemon, not container userland: {line!r}")


def test_universe_pin_is_not_overridable_by_environment():
    """A pin that an env var can relax is not a control."""
    body = SCRIPT.read_text(encoding="utf-8")
    assert "UNIVERSE_SHA=0c57bd71" in body
    assert "UNIVERSE_SHA=${" not in body


# ---- gate 6: the deployment/runtime identity attestation ----------------------------------------
#
# These are the tests that would have failed on 2026-08-26. Each mutates ONE leg of the tuple.


def test_gate6_passes_on_a_reconciled_deployment(rig):
    result = rig()
    assert result.returncode == 0, result.stdout
    assert "all six gates pass" in result.stdout
    assert "RESULT: PASS - build marker == deploy manifest == running runtime" in result.stdout
    # ★ The PASS line enters a governed operational transcript, so it must not assert a fact the gate
    # never tested. Gate 6 reconciles artifacts; it does not establish organizational approval.
    assert "approved ==" not in result.stdout
    assert "approved commit" not in result.stdout


def test_gate6_is_not_switchable_off(rig):
    """★ There must be no environment switch that makes the integrity gate stop counting. A default-off
    flag is silent degradation: the repair deploys, someone forgets the flag, READY keeps printing."""
    body = SCRIPT.read_text(encoding="utf-8")
    assert "MDQ_GATE6_REQUIRED" not in body
    assert "advisory" not in body.lower() or "NON-GOVERNING" in body


def test_gate6_catches_an_unrecorded_container_recreation(rig, tmp_path):
    """★ THE 2026-08-26 SHAPE. The container was replaced; nothing recorded it. Every declaration still
    agrees with every other declaration — only the running container id disagrees."""
    result = rig(STUB_CONTAINER_ID="a" * 64)
    assert result.returncode == 1
    assert "deploy-manifest container != running container" in result.stdout
    assert "NOT READY" in result.stdout


def test_gate6_catches_an_unrecorded_image_rebuild(rig):
    result = rig(STUB_IMAGE_ID="sha256:" + "9" * 64)
    assert result.returncode == 1
    assert "deploy-manifest image != running image" in result.stdout


def test_gate6_catches_running_code_that_is_not_the_deployed_code(rig, tmp_path):
    """The declarations are untouched and mutually consistent; only the bytes in the container moved."""
    import tarfile as _t
    hacked = tmp_path / "hacked_app"
    (hacked / "validation").mkdir(parents=True)
    (hacked / "main.py").write_text("V = 999\n", encoding="utf-8")
    (hacked / "validation" / "thing.py").write_text("X = 2\n", encoding="utf-8")
    tar = tmp_path / "hacked.tar"
    with _t.open(tar, "w") as archive:
        archive.add(hacked, arcname="app")
    result = rig(STUB_CP_TAR=str(tar))
    assert result.returncode == 1
    assert "deploy-manifest code_digest != HOST-DERIVED running code" in result.stdout


def test_gate6_catches_a_missing_deploy_manifest(rig, tmp_path):
    """A deploy that never recorded what it made cannot be reconciled, and must not read as ready."""
    empty = tmp_path / "empty_app_dir"
    empty.mkdir()
    result = rig(MDQ_APP_DIR=str(empty))
    assert result.returncode == 1
    assert "deploy manifest   : ABSENT" in result.stdout


def test_gate6_catches_a_swapped_marker(rig, tmp_path):
    """★ A valid marker from one attempt paired with a valid manifest from another. Every field-by-field
    comparison still agrees; only the manifest's hash-binding of the marker exposes it."""
    import json as _json
    import shutil as _shutil
    app_dir = tmp_path / "swapped_app"
    _shutil.copytree(tmp_path / "opt_app", app_dir)
    marker = app_dir / "DEPLOYED_BUILD_INFO.json"
    payload = _json.loads(marker.read_text(encoding="utf-8"))
    payload["builder"] = "a-different-attempt"          # same commit, same code_digest, different bytes
    marker.write_text(_json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    result = rig(MDQ_APP_DIR=str(app_dir))
    assert result.returncode == 1
    assert "written against a DIFFERENT build marker" in result.stdout


def test_gate6_treats_deploy_src_sha_as_corroborating_only(rig, tmp_path):
    """The legacy file may never again be sufficient by itself — on 2026-08-26 it read 'unchanged'
    while the runtime had already moved. Disagreement is a failure, agreement is not proof."""
    stale = tmp_path / "stale_sha"
    stale.write_text("0" * 40 + "\n", encoding="utf-8")
    result = rig(MDQ_DEPLOY_SHA_FILE=str(stale))
    assert result.returncode == 1
    assert "legacy .deploy_src_sha" in result.stdout


def test_diagnostic_mode_can_never_declare_readiness(rig):
    """The escape hatch for exercising this against a legacy box must not be able to produce a
    governed verdict, or it becomes the switch it was meant to replace."""
    result = rig(_argv=["--diagnostic"])
    assert "NON-GOVERNING" in result.stdout
    assert "=== READY" not in result.stdout


def test_gate6_catches_a_container_created_mismatch(rig, tmp_path):
    """The creation stamp is recorded, so it must be reconciled — otherwise a manifest transplanted
    from a different container's lifetime reconciles on every other field."""
    import json as _json
    import shutil as _shutil
    app_dir = tmp_path / "restamped_app"
    _shutil.copytree(tmp_path / "opt_app", app_dir)
    manifest = app_dir / "DEPLOYMENT_RUNTIME_MANIFEST.json"
    payload = _json.loads(manifest.read_text(encoding="utf-8"))
    payload["container_created"] = "2020-01-01T00:00:00Z"
    manifest.write_text(_json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    result = rig(MDQ_APP_DIR=str(app_dir))
    assert result.returncode == 1
    assert "container_created" in result.stdout


def test_the_attestation_helper_is_not_caller_supplied(rig):
    """★ The one source that must not be caller-assertable must not be caller-assertable.

    An earlier revision resolved the helper through `${MDQ_ATTEST_HELPER:-...}` "for tests". That was a
    hole straight through the amendment: a governed run could point the load-bearing host derivation at
    a script that just prints the expected digest.
    """
    body = SCRIPT.read_text(encoding="utf-8")
    executable = [line for line in body.splitlines() if not line.lstrip().startswith("#")]
    for line in executable:
        assert "MDQ_ATTEST_HELPER" not in line, (
            f"the attestation helper must be version-bound, not caller-supplied: {line!r}")
    assert 'ATTEST_HELPER="$SCRIPT_DIR/derive_runtime_code_digest_from_tar.py"' in body


def test_setting_the_override_cannot_change_a_governed_result(rig, tmp_path):
    """Belt and braces: even if someone exports it, the governed run must ignore it."""
    liar = tmp_path / "liar.py"
    liar.write_text("print('sha256:' + 'f' * 64)\n", encoding="utf-8")
    result = rig(MDQ_ATTEST_HELPER=str(liar))
    assert result.returncode == 0, result.stdout
    assert "f" * 64 not in result.stdout


def test_operational_entrypoints_are_committed_executable():
    """★ The runbook invokes these directly and `git archive` preserves modes, so a 100644 entrypoint
    makes the documented production sequence permission-fail on the box."""
    import subprocess as _sp
    repo = SCRIPT.resolve().parents[3]
    entrypoints = (
        "apps/backend/scripts/mdq_preflight_readiness.sh",
        "deploy/aws/write-deployment-manifest.sh",
        "deploy/aws/build-deploy-archive.sh",
    )
    listing = _sp.run(("git", "ls-files", "-s", *entrypoints), cwd=repo,
                      capture_output=True, text=True)
    assert listing.returncode == 0, listing.stderr
    seen = {}
    for line in listing.stdout.splitlines():
        mode, _rest = line.split(" ", 1)
        seen[line.split("\t")[-1]] = mode
    for path in entrypoints:
        assert seen.get(path) == "100755", (
            f"{path} is committed as {seen.get(path)}; the runbook runs it directly and git archive "
            f"preserves the mode, so it must be 100755")
