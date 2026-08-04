"""Contract tests for the ADR 0043 WS5 B4 credential-staging script.

B4 is the one checkpoint a human performs by hand, so the script's constants must
be pinned to the governed sources rather than transcribed and hoped over:

- the credential NAMES must equal ``app/brokers/adr0043_reconcile.py``'s ``ENV_KEY``
  / ``ENV_SECRET`` — the runner reads those exact names, and §2 prohibits
  ``ALPACA_PAPER_7_*`` as the runtime credential name;
- the FINGERPRINT ALGORITHM must equal that module's ``_fingerprint`` (sha256 hex
  truncated to 12), not a lookalike;
- the expected fingerprints must equal the ones the effective authorization pins.

⚠ **No real credential material appears in this file.** The functional tests
rewrite the harness's expected fingerprints to those of synthetic values, so the
logic is exercised end to end without a live key or secret ever entering the
repository. The real ``stage`` path prompts on /dev/tty and is exercised only by
the owner, which is the entire point of the checkpoint.
"""

from __future__ import annotations

import hashlib
import re
import shutil
import subprocess
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[4]
_SCRIPT = _REPO_ROOT / "deploy" / "aws" / "adr0043" / "stage-successor-credential.sh"
_RUNNER = _REPO_ROOT / "apps" / "backend" / "app" / "brokers" / "adr0043_reconcile.py"

pytestmark = pytest.mark.skipif(not _SCRIPT.exists(), reason="B4 staging script absent")

#: The governed fingerprints. These are one-way digests, not credential material.
KEY_FP = "ffab8796516a"
SECRET_FP = "c2cab6509f1b"

#: Synthetic stand-ins used by the functional tests. Never the real credential.
FAKE_KEY = "SYNTHETIC_TEST_KEY_NOT_A_CREDENTIAL"
FAKE_SECRET = "SYNTHETIC_TEST_SECRET_NOT_A_CREDENTIAL"


def _fp(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()[:12]


@pytest.fixture(scope="module")
def script() -> str:
    return _SCRIPT.read_text(encoding="utf-8")


def _const(text: str, name: str) -> str:
    m = re.search(rf"^readonly {re.escape(name)}='([^']*)'", text, re.M)
    assert m, f"constant {name} not found"
    return m.group(1)


# ------------------------------------------------------------------ pinning


def test_credential_names_match_the_governed_runner(script):
    """The runner reads these exact names. A typo here stages a credential the
    Stage-C process never sees, and the run fails as a missing-credential refusal
    rather than as the configuration error it actually is."""
    runner = _RUNNER.read_text(encoding="utf-8")
    for const in ("ENV_KEY", "ENV_SECRET"):
        expected = re.search(rf'^{const} = "([^"]+)"', runner, re.M)
        assert expected, f"{const} not found in the runner"
        assert _const(script, const) == expected.group(1)


def test_the_prohibited_credential_name_appears_nowhere(script):
    """§2 forbids ALPACA_PAPER_7_* as the RUNTIME credential name."""
    for line in script.splitlines():
        if line.lstrip().startswith("#"):
            continue  # the rationale comment may name it
        assert "ALPACA_PAPER_7" not in line


def test_expected_fingerprints_match_the_authorization(script):
    assert _const(script, "EXPECTED_KEY_FP") == KEY_FP
    assert _const(script, "EXPECTED_SECRET_FP") == SECRET_FP


def test_bound_to_the_effective_authorization_and_instance(script):
    assert _const(script, "AUTHORIZATION_SHA") == (
        "9845c6dfb78ee1435ecb101ca5388f2dd32447921a89cacbf31a2570c19325d8"
    )
    assert _const(script, "EXPECTED_INSTANCE") == "i-0fff7076ad461aa9a"


def test_fingerprint_algorithm_matches_the_governed_implementation():
    """sha256 hex truncated to 12 — app/brokers/adr0043_reconcile.py::_fingerprint.

    Pinned against a neutral vector, never against the real credential.
    """
    runner = _RUNNER.read_text(encoding="utf-8")
    assert "hashlib.sha256(value.encode()).hexdigest()[:12]" in runner
    assert _fp("abc") == "ba7816bf8f01"


def test_secrets_are_never_taken_from_arguments_or_environment(script):
    """The prompt must come from /dev/tty with echo disabled. ``read -s`` is the
    echo-disabling flag; losing it would echo the secret into session output."""
    assert "read -r -s -p 'Successor API key: '" in script
    assert "read -r -s -p 'Successor API secret: '" in script
    assert script.count("</dev/tty") >= 2


def test_values_are_written_raw_not_shell_quoted(script):
    """``docker --env-file`` parses KEY=VALUE literally, so %q would embed quoting
    characters INTO the credential."""
    assert "printf '%s=%s\\n'" in script
    assert "%q" not in script


def test_no_real_credential_material_in_this_test_file():
    """Guards the guard: a future edit must not paste a live value in here."""
    body = Path(__file__).read_text(encoding="utf-8")
    assert not re.search(r"\bPK[A-Z0-9]{18,}\b", body), "an Alpaca-shaped key is present"


# --------------------------------------------------------------- functional

_BASH = shutil.which("bash")
needs_bash = pytest.mark.skipif(_BASH is None, reason="bash unavailable")


def _harness(tmp_path: Path) -> Path:
    """Copy the script with the root gate, paths and expected fingerprints
    redirected, so the real logic runs against synthetic credentials."""
    src = _SCRIPT.read_text(encoding="utf-8")
    src = src.replace(
        "readonly CREDENTIAL_DIR='/etc/adr0043'", f"readonly CREDENTIAL_DIR='{tmp_path}/etc'"
    )
    src = src.replace(
        "readonly RECEIPT_DIR='/var/lib/adr0043'", f"readonly RECEIPT_DIR='{tmp_path}/var'"
    )
    src = src.replace("[ \"$(id -u)\" -eq 0 ] || die 'must run as root (use sudo)'", "return 0")
    src = src.replace(
        f"readonly EXPECTED_KEY_FP='{KEY_FP}'", f"readonly EXPECTED_KEY_FP='{_fp(FAKE_KEY)}'"
    )
    src = src.replace(
        f"readonly EXPECTED_SECRET_FP='{SECRET_FP}'",
        f"readonly EXPECTED_SECRET_FP='{_fp(FAKE_SECRET)}'",
    )
    p = tmp_path / "harness.sh"
    p.write_text(src, encoding="utf-8")
    return p


def _write_cred(tmp_path: Path, body: str) -> None:
    d = tmp_path / "etc"
    d.mkdir(parents=True, exist_ok=True)
    (d / "successor-canary.env").write_text(body, encoding="utf-8")


def _verify(tmp_path: Path):
    return subprocess.run(  # noqa: S603
        [_BASH, str(_harness(tmp_path)), "verify"], capture_output=True, text=True
    )


GOOD = (
    f"ADR0043_SUCCESSOR_CANARY_ALPACA_API_KEY={FAKE_KEY}\n"
    f"ADR0043_SUCCESSOR_CANARY_ALPACA_API_SECRET={FAKE_SECRET}\n"
)


@needs_bash
def test_verify_passes_on_a_correctly_staged_file(tmp_path):
    _write_cred(tmp_path, GOOD)
    r = _verify(tmp_path)
    assert "key_fingerprint_matches=true" in r.stdout
    assert "secret_fingerprint_matches=true" in r.stdout
    assert "credential_line_count=2" in r.stdout


@needs_bash
def test_verify_fails_when_absent(tmp_path):
    r = _verify(tmp_path)
    assert r.returncode != 0
    assert "B4_NOT_STAGED" in r.stderr


@needs_bash
def test_verify_fails_on_a_wrong_secret(tmp_path):
    _write_cred(tmp_path, GOOD.replace(FAKE_SECRET, "a-different-value"))
    r = _verify(tmp_path)
    assert r.returncode != 0
    assert "secret_fingerprint_matches=false" in r.stdout


@needs_bash
def test_verify_fails_on_an_extra_name(tmp_path):
    _write_cred(tmp_path, GOOD + f"SOME_OTHER_CREDENTIAL_NAME={FAKE_KEY}\n")
    r = _verify(tmp_path)
    assert r.returncode != 0
    assert "unexpected credential names present" in r.stderr


@needs_bash
def test_verify_emits_no_credential_values(tmp_path):
    _write_cred(tmp_path, GOOD)
    r = _verify(tmp_path)
    assert FAKE_KEY not in r.stdout + r.stderr
    assert FAKE_SECRET not in r.stdout + r.stderr
