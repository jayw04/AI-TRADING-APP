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
  inspect) echo "stub-inspect-value"; exit 0 ;;
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
        env.setdefault("STUB_CREDS", "present")
        env.setdefault("STUB_LATCH", "pass")
        env.setdefault("STUB_SIZE_GB", "58")
        env.setdefault("STUB_AVAIL_GB", "27")
        env.setdefault("STUB_SAMPLERS", "0")
        env.update({k: str(v) for k, v in overrides.items()})
        return subprocess.run(
            [bash, str(SCRIPT)], capture_output=True, text=True, timeout=120, env=env
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
    assert "=== READY - all five gates pass ===" in r.stdout
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


def test_control_is_read_only_no_repair_paths():
    """The control reports; it must never mutate or self-heal."""
    body = SCRIPT.read_text(encoding="utf-8")
    for mutating in ("docker cp", "systemctl start", "systemctl restart", "rm -", "> $ROOT_HOST"):
        assert mutating not in body, f"preflight must not perform {mutating!r}"


def test_universe_pin_is_not_overridable_by_environment():
    """A pin that an env var can relax is not a control."""
    body = SCRIPT.read_text(encoding="utf-8")
    assert "UNIVERSE_SHA=0c57bd71" in body
    assert "UNIVERSE_SHA=${" not in body
