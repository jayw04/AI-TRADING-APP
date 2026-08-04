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
import os
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

#: The authorized successor account. Non-secret, and deliberately NOT staged into
#: the credential file — it is governed by §8 configuration.
ACCOUNT = "PA3E97RWHKQZ"

AUTH_SHA = "9845c6dfb78ee1435ecb101ca5388f2dd32447921a89cacbf31a2570c19325d8"
INSTANCE = "i-0fff7076ad461aa9a"

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


def _verify_body(text: str) -> str:
    start = text.index("cmd_verify() {")
    return text[start : text.index('\ncase "${1:-}"', start)]


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
    assert _const(script, "AUTHORIZATION_SHA") == AUTH_SHA
    assert _const(script, "EXPECTED_INSTANCE") == INSTANCE


def test_the_authorized_account_is_pinned_but_never_staged(script):
    """§8 governs the account binding; the credential file carries secret material
    only. The script must know the authorized account in order to REFUSE a
    disagreeing one, without ever writing it alongside the secret."""
    assert _const(script, "EXPECTED_ACCOUNT_ID") == ACCOUNT
    assert _const(script, "ENV_ACCOUNT") == "ADR0043_SUCCESSOR_CANARY_ACCOUNT_ID"
    # The staging writer emits exactly the two secret entries and nothing else.
    stage = script[script.index("cmd_stage() {") : script.index("cmd_verify() {")]
    assert stage.count("printf '%s=%s\\n'") == 2
    assert "ENV_ACCOUNT" not in stage


def test_stage_creates_root_owned_private_paths(script):
    """The functional harness runs unprivileged and cannot reproduce root
    ownership, so pin it in the text instead: both directories 0700 root:root,
    both files 0600 root:root. ``verify`` re-checks the real thing on the host."""
    stage = script[script.index("cmd_stage() {") : script.index("cmd_verify() {")]
    assert stage.count("install -d -o root -g root -m 0700") == 2
    assert stage.count("chown root:root") == 2
    assert 'chmod 0600 "$tmp"' in stage
    assert 'chmod 0600 "$RECEIPT_FILE"' in stage


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


def test_no_nul_glob_trap_in_the_guard(script):
    r"""``$'\0'`` expands to the EMPTY string, so a ``*$'\0'*`` case degrades to
    ``**`` and would reject every value including the correct one. NUL is covered
    structurally instead: a bash variable cannot hold one."""
    code = [ln for ln in script.splitlines() if not ln.lstrip().startswith("#")]
    assert "$'\\0'" not in "\n".join(code)  # the rationale comment may name it


def test_locale_is_pinned(script):
    """Glob character ranges and ``sort`` order are locale-sensitive; the guard
    must mean the same thing on every host."""
    assert "export LC_ALL=C" in script


def test_no_real_credential_material_in_this_test_file():
    """Guards the guard: a future edit must not paste a live value in here."""
    body = Path(__file__).read_text(encoding="utf-8")
    assert not re.search(r"\bPK[A-Z0-9]{18,}\b", body), "an Alpaca-shaped key is present"


# --------------------------------------------------------------- functional

_BASH = shutil.which("bash")
needs_bash = pytest.mark.skipif(_BASH is None, reason="bash unavailable")


def _harness(tmp_path: Path, *, drivable_stage: bool = False) -> Path:
    """Copy the script with the root gate, instance gate, paths and expected
    fingerprints redirected, so the real logic runs against synthetic credentials.

    ``drivable_stage`` additionally replaces the two /dev/tty prompts with reads
    from the environment, which is the only way to exercise the character guard
    without an interactive terminal. Nothing else about ``stage`` is altered.
    """
    src = _SCRIPT.read_text(encoding="utf-8")
    src = src.replace(
        "readonly CREDENTIAL_DIR='/etc/adr0043'", f"readonly CREDENTIAL_DIR='{tmp_path}/etc'"
    )
    src = src.replace(
        "readonly RECEIPT_DIR='/var/lib/adr0043'", f"readonly RECEIPT_DIR='{tmp_path}/var'"
    )
    src = src.replace("[ \"$(id -u)\" -eq 0 ] || die 'must run as root (use sudo)'", "return 0")
    src = src.replace(
        "require_instance() {\n  local tok id", "require_instance() {\n  return 0\n  local tok id"
    )
    src = src.replace(
        f"readonly EXPECTED_KEY_FP='{KEY_FP}'", f"readonly EXPECTED_KEY_FP='{_fp(FAKE_KEY)}'"
    )
    src = src.replace(
        f"readonly EXPECTED_SECRET_FP='{SECRET_FP}'",
        f"readonly EXPECTED_SECRET_FP='{_fp(FAKE_SECRET)}'",
    )
    if drivable_stage:
        src = src.replace(
            "  [ -r /dev/tty ] || die 'no controlling terminal; run this in an interactive session'",
            "  :",
        )
        # The tests run unprivileged (and on Windows, where directory modes are
        # not settable at all), so root ownership and 0700 cannot be reproduced
        # here. Those are asserted statically below, and re-checked by `verify`
        # against the real file on the real host.
        src = src.replace("install -d -o root -g root -m 0700", "mkdir -p")
        src = src.replace("chown root:root ", ": ")
        src = src.replace("chmod 0700 ", ": ")
        src = re.sub(
            r"^  read -r -s -p 'Successor API key: '.*$",
            '  api_key="$TEST_KEY"',
            src,
            flags=re.M,
        )
        src = re.sub(
            r"^  read -r -s -p 'Successor API secret: '.*$",
            '  api_secret="$TEST_SECRET"',
            src,
            flags=re.M,
        )
    p = tmp_path / "harness.sh"
    p.write_text(src, encoding="utf-8")
    return p


GOOD = (
    f"ADR0043_SUCCESSOR_CANARY_ALPACA_API_KEY={FAKE_KEY}\n"
    f"ADR0043_SUCCESSOR_CANARY_ALPACA_API_SECRET={FAKE_SECRET}\n"
)

RECEIPT = (
    "checkpoint=B4\n"
    "result=B4_PASS\n"
    f"key_fingerprint={_fp(FAKE_KEY)}\n"
    f"secret_fingerprint={_fp(FAKE_SECRET)}\n"
    f"authorization_sha={AUTH_SHA}\n"
    f"instance_id={INSTANCE}\n"
    "broker_access_performed=false\n"
    "container_created=false\n"
)


def _write_cred(tmp_path: Path, body: str, receipt: str | None = RECEIPT) -> None:
    d = tmp_path / "etc"
    d.mkdir(parents=True, exist_ok=True)
    os.chmod(d, 0o700)
    (d / "successor-canary.env").write_text(body, encoding="utf-8")
    if receipt is not None:
        v = tmp_path / "var"
        v.mkdir(parents=True, exist_ok=True)
        (v / "B4_CREDENTIAL_STAGED").write_text(receipt, encoding="utf-8")


def _verify(tmp_path: Path, account: str | None = ACCOUNT):
    env = dict(os.environ)
    env.pop("WORKBENCH_BROKER_EXPECTED_ACCOUNT_ID", None)
    env.pop("ADR0043_SUCCESSOR_CANARY_ACCOUNT_ID", None)
    if account is not None:
        env["ADR0043_SUCCESSOR_CANARY_ACCOUNT_ID"] = account
    return subprocess.run(  # noqa: S603
        [_BASH, str(_harness(tmp_path)), "verify"], capture_output=True, text=True, env=env
    )


def _stage(tmp_path: Path, key: str, secret: str):
    env = dict(os.environ, TEST_KEY=key, TEST_SECRET=secret)
    return subprocess.run(  # noqa: S603
        [_BASH, str(_harness(tmp_path, drivable_stage=True)), "stage"],
        capture_output=True,
        text=True,
        env=env,
    )


# ------------------------------------------------------- character guard


@needs_bash
@pytest.mark.parametrize(
    ("value", "reason"),
    [
        ("", "empty"),
        ("AB=CD", "contains '='"),
        ("AB CD", "unaccepted character"),
        (" ABCD", "leading or trailing whitespace"),
        ("ABCD ", "leading or trailing whitespace"),
        ("\tABCD", "leading or trailing whitespace"),
        ("AB\tCD", "unaccepted character"),
        ("AB\nCD", "newline or carriage return"),
        ("AB\rCD", "newline or carriage return"),
        ("AB'CD", "quote or backslash"),
        ('AB"CD', "quote or backslash"),
        ("AB\\CD", "quote or backslash"),
        ("AB;CD", "unaccepted character"),
        ("AB$CD", "unaccepted character"),
        ("AB`CD", "unaccepted character"),
        ("ABéCD", "unaccepted character"),
    ],
)
def test_stage_refuses_unaccepted_credential_values(tmp_path, value, reason):
    """The env-file parser performs no shell interpretation, so the hazard is
    silent corruption, not injection: a newline splits the entry and a '=' moves
    the key/value boundary. Every rejection must leave nothing staged."""
    r = _stage(tmp_path, value, FAKE_SECRET)
    assert r.returncode != 0
    assert reason in r.stderr
    assert "nothing staged" in r.stderr
    assert not (tmp_path / "etc" / "successor-canary.env").exists()


@needs_bash
def test_stage_refuses_an_unaccepted_secret_too(tmp_path):
    """The guard must apply to both entries, not only the first."""
    r = _stage(tmp_path, FAKE_KEY, "AB=CD")
    assert r.returncode != 0
    assert "api secret" in r.stderr
    assert not (tmp_path / "etc" / "successor-canary.env").exists()


@needs_bash
def test_stage_accepts_credential_shaped_values(tmp_path):
    """Real Alpaca key material is alphanumeric with base64-ish punctuation. The
    guard must not be so tight that it locks the owner out at the checkpoint."""
    r = _stage(tmp_path, FAKE_KEY, FAKE_SECRET)
    assert r.returncode == 0, r.stderr
    assert "B4_PASS" in r.stdout
    staged = (tmp_path / "etc" / "successor-canary.env").read_text(encoding="utf-8")
    assert staged == GOOD


@needs_bash
def test_stage_writes_nothing_on_a_fingerprint_mismatch(tmp_path):
    r = _stage(tmp_path, FAKE_KEY, "a-different-value")
    assert r.returncode != 0
    assert "FINGERPRINT MISMATCH" in r.stderr
    assert "key=ok secret=BAD" in r.stderr
    assert not (tmp_path / "etc" / "successor-canary.env").exists()


@needs_bash
def test_stage_never_emits_a_credential_value(tmp_path):
    r = _stage(tmp_path, FAKE_KEY, "a-different-value")
    assert FAKE_KEY not in r.stdout + r.stderr
    assert "a-different-value" not in r.stdout + r.stderr


@needs_bash
def test_the_staged_receipt_carries_no_credential_value(tmp_path):
    _stage(tmp_path, FAKE_KEY, FAKE_SECRET)
    receipt = (tmp_path / "var" / "B4_CREDENTIAL_STAGED").read_text(encoding="utf-8")
    assert FAKE_KEY not in receipt
    assert FAKE_SECRET not in receipt
    assert f"authorization_sha={AUTH_SHA}" in receipt
    assert "broker_access_performed=false" in receipt
    assert "ADR0043_SUCCESSOR_CANARY_ACCOUNT_ID" not in receipt


# --------------------------------------------------------------- verify


@needs_bash
def test_verify_passes_on_a_correctly_staged_file(tmp_path):
    _write_cred(tmp_path, GOOD)
    r = _verify(tmp_path)
    assert "key_fingerprint_matches=true" in r.stdout
    assert "secret_fingerprint_matches=true" in r.stdout
    assert "credential_line_count=2" in r.stdout
    assert "duplicate_names=none" in r.stdout
    assert "account_id_matches_authorized=true" in r.stdout
    assert "broker_access_performed=false" in r.stdout
    assert "container_created=false" in r.stdout


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
    assert "B4_VERIFICATION_FAILED" in r.stderr


@needs_bash
def test_verify_fails_on_an_extra_name(tmp_path):
    _write_cred(tmp_path, GOOD + f"SOME_OTHER_CREDENTIAL_NAME={FAKE_KEY}\n")
    r = _verify(tmp_path)
    assert r.returncode != 0
    assert "unexpected credential names present" in r.stderr


@needs_bash
def test_verify_fails_on_a_duplicate_key(tmp_path):
    """Two entries for the same name: ``--env-file`` silently takes the last, so
    the fingerprint the owner confirmed need not be the one Stage C uses."""
    dup = f"ADR0043_SUCCESSOR_CANARY_ALPACA_API_KEY={FAKE_KEY}\n"
    _write_cred(tmp_path, GOOD + dup)
    r = _verify(tmp_path)
    assert r.returncode != 0
    assert "duplicate credential keys present" in r.stderr


@needs_bash
def test_verify_fails_when_the_account_id_is_in_the_credential_file(tmp_path):
    """The credential file carries secret material only; §8 governs the binding."""
    _write_cred(tmp_path, GOOD + f"ADR0043_SUCCESSOR_CANARY_ACCOUNT_ID={ACCOUNT}\n")
    r = _verify(tmp_path)
    assert r.returncode != 0
    assert "account id present in the credential file" in r.stderr


@needs_bash
def test_verify_fails_when_the_account_binding_is_absent(tmp_path):
    """Fail closed: an unresolvable §8 binding is a stop, never a default."""
    _write_cred(tmp_path, GOOD)
    r = _verify(tmp_path, account=None)
    assert r.returncode != 0
    assert "account_id_source=UNRESOLVED" in r.stdout
    assert "disagrees with the authorized account" in r.stderr


@needs_bash
def test_verify_fails_when_the_account_binding_disagrees(tmp_path):
    """The canary's account is the realistic wrong value — it is still tagged on
    this runtime as provenance."""
    _write_cred(tmp_path, GOOD)
    r = _verify(tmp_path, account="PA34USW0Q8UO")
    assert r.returncode != 0
    assert "account_id_matches_authorized=false" in r.stdout
    assert "disagrees with the authorized account" in r.stderr


@needs_bash
def test_verify_fails_when_the_receipt_is_absent(tmp_path):
    _write_cred(tmp_path, GOOD, receipt=None)
    r = _verify(tmp_path)
    assert r.returncode != 0
    assert "staging receipt absent" in r.stderr


@needs_bash
def test_verify_fails_when_a_credential_value_leaked_into_the_receipt(tmp_path):
    _write_cred(tmp_path, GOOD, receipt=RECEIPT + f"stray={FAKE_SECRET}\n")
    r = _verify(tmp_path)
    assert r.returncode != 0
    assert "a credential value appears in the receipt" in r.stderr


@needs_bash
def test_verify_fails_when_the_receipt_binds_another_authorization(tmp_path):
    _write_cred(tmp_path, GOOD, receipt=RECEIPT.replace(AUTH_SHA, "0" * 64))
    r = _verify(tmp_path)
    assert r.returncode != 0
    assert "authorization_sha does not match" in r.stderr


@needs_bash
def test_verify_fails_when_the_receipt_claims_broker_access(tmp_path):
    _write_cred(
        tmp_path,
        GOOD,
        receipt=RECEIPT.replace("broker_access_performed=false", "broker_access_performed=true"),
    )
    r = _verify(tmp_path)
    assert r.returncode != 0
    assert "does not assert that no broker request was made" in r.stderr


@needs_bash
def test_verify_emits_no_credential_values(tmp_path):
    _write_cred(tmp_path, GOOD)
    r = _verify(tmp_path)
    assert FAKE_KEY not in r.stdout + r.stderr
    assert FAKE_SECRET not in r.stdout + r.stderr


@needs_bash
def test_verify_does_not_remediate(tmp_path):
    """§ the authorization does not permit rewriting or deleting the credential on
    a failed check, so a failing verify must leave the file byte-identical."""
    bad = GOOD.replace(FAKE_SECRET, "a-different-value")
    _write_cred(tmp_path, bad)
    before = (tmp_path / "etc" / "successor-canary.env").read_bytes()
    r = _verify(tmp_path)
    assert r.returncode != 0
    assert (tmp_path / "etc" / "successor-canary.env").read_bytes() == before
    assert "nothing was rewritten or deleted" in r.stderr


def test_verify_makes_no_broker_or_container_call(script):
    """Statically: the verify path must contain no network or container verb."""
    body = _verify_body(script)
    for verb in ("curl ", "docker", "aws ", "wget", "nc "):
        assert verb not in body, f"verify must not invoke {verb.strip()}"


def test_verify_checks_the_instance_binding(script):
    """A §10 identity mismatch stops the run; verify must re-establish it rather
    than inherit the staging run's assertion."""
    assert "require_instance" in _verify_body(script)
