"""CREDENTIAL-ROTATION-TOOL-CUSTODY-001 — guarantees for scripts/rotate_user_passwords.py.

The script is loaded directly (scripts/ isn't a package). Each test names the
property it would fail on: secret material on stdout/stderr/log, a secret
accepted on argv, a shared rotate/verify entry point, or a write from verify.
"""

from __future__ import annotations

import argparse
import ast
import importlib.util
import json
import logging
import re
from pathlib import Path

import pytest

from app.auth.passwords import verify_password

# apps/backend/tests/scripts/<this> -> parents[4] is the repo root; the tool lives in root scripts/.
_SCRIPT = Path(__file__).resolve().parents[4] / "scripts" / "rotate_user_passwords.py"
_spec = importlib.util.spec_from_file_location("rotate_user_passwords", _SCRIPT)
assert _spec is not None and _spec.loader is not None
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)

_BCRYPT_HASH = re.compile(r"\$2[aby]\$\d\d\$[./A-Za-z0-9]{53}")


def _rotate(tmp_path: Path, users: str = "6,7") -> tuple[Path, Path, int]:
    out = tmp_path / "certs" / "workbench_logins.md"
    hp = tmp_path / "certs" / ".rotation_hashes.json"
    rc = _mod.main(
        [
            "rotate",
            "--users",
            users,
            "--reason",
            "test",
            "--out",
            str(out),
            "--hashes-out",
            str(hp),
        ]
    )
    return out, hp, rc


def _secrets_of(out: Path, hp: Path) -> tuple[list[str], list[str]]:
    plaintexts = list(_mod.parse_credential_file(out.read_text(encoding="utf-8")).values())
    hashes = list(json.loads(hp.read_text(encoding="utf-8")).values())
    return plaintexts, hashes


def _calls_in(func: ast.FunctionDef) -> set[str | None]:
    return {
        (n.func.attr if isinstance(n.func, ast.Attribute) else getattr(n.func, "id", None))
        for n in ast.walk(func)
        if isinstance(n, ast.Call)
    }


# ---------------------------------------------------------------- rotate: behaviour


def test_rotate_writes_file_and_hashes_that_the_backend_verifies(tmp_path: Path) -> None:
    out, hp, rc = _rotate(tmp_path)
    assert rc == 0
    plaintexts, hashes = _secrets_of(out, hp)
    assert len(plaintexts) == 2 and len(hashes) == 2
    creds = _mod.parse_credential_file(out.read_text(encoding="utf-8"))
    stored = json.loads(hp.read_text(encoding="utf-8"))
    for uid, pw in creds.items():
        assert verify_password(pw, stored[uid]), "hash must be what the login route verifies"


def test_rotate_requires_explicit_users_and_reason(tmp_path: Path) -> None:
    out = tmp_path / "certs" / "x.md"
    with pytest.raises(SystemExit):  # --users is required: no "rotate everyone" default
        _mod.main(["rotate", "--reason", "r", "--out", str(out)])
    with pytest.raises(SystemExit):
        _mod.main(["rotate", "--users", "6", "--out", str(out)])
    assert not out.exists()


def test_rotate_refuses_unknown_user_and_outside_certs(tmp_path: Path) -> None:
    out = tmp_path / "certs" / "x.md"
    hp = tmp_path / "certs" / "h.json"
    rc = _mod.main(
        ["rotate", "--users", "6,99", "--reason", "r", "--out", str(out), "--hashes-out", str(hp)]
    )
    assert rc == 2
    assert not out.exists() and not hp.exists()
    elsewhere = tmp_path / "not-certs" / "x.md"
    rc = _mod.main(
        [
            "rotate",
            "--users",
            "6",
            "--reason",
            "r",
            "--out",
            str(elsewhere),
            "--hashes-out",
            str(hp),
        ]
    )
    assert rc == 2
    assert not elsewhere.exists() and not hp.exists()


# ---------------------------------------------------------------- no secret output


def test_rotate_emits_no_plaintext_and_no_hash_on_stdout_or_stderr(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    out, hp, rc = _rotate(tmp_path)
    assert rc == 0
    captured = capsys.readouterr()
    text = captured.out + captured.err
    plaintexts, hashes = _secrets_of(out, hp)
    for pw in plaintexts:
        assert pw not in text
    for h in hashes:
        assert h not in text
    assert not _BCRYPT_HASH.search(text), "no bcrypt-shaped string may be printed"
    assert "fingerprint" in text  # the only identifier that is printed


def test_verify_emits_no_plaintext_and_no_hash(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    out, hp, _ = _rotate(tmp_path)
    capsys.readouterr()
    rc = _mod.main(["verify", "--stored-hashes", str(hp), "--credentials", str(out)])
    assert rc == 0
    text = capsys.readouterr().out
    plaintexts, hashes = _secrets_of(out, hp)
    assert all(pw not in text for pw in plaintexts)
    assert all(h not in text for h in hashes)
    assert not _BCRYPT_HASH.search(text)
    assert text.count("VERIFIED") == 2


def test_no_log_lines_at_all(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.DEBUG)
    out, hp, _ = _rotate(tmp_path)
    _mod.main(["verify", "--stored-hashes", str(hp), "--credentials", str(out)])
    assert caplog.records == [], "the tool must not log (a log line is a second copy)"


# ---------------------------------------------------------------- no argv plaintext


def test_no_argv_option_accepts_a_secret() -> None:
    parser = _mod.build_parser()
    subparsers = next(a for a in parser._actions if isinstance(a, argparse._SubParsersAction))
    allowed_hash_paths = {"--stored-hashes", "--hashes-out"}  # paths to hash FILES, never values
    for sp in subparsers.choices.values():
        for action in sp._actions:
            for opt in action.option_strings:
                bare = opt.lower().replace("-", "")
                looks_secret = re.search(r"pass|secret|token|key|hash", bare) is not None
                assert not looks_secret or opt in allowed_hash_paths, (
                    f"{opt} looks like it would take secret material on the command line"
                )
    assert "--password" not in parser.format_help()


# ---------------------------------------------------------------- separate entry points


def test_rotate_and_verify_are_distinct_entry_points_and_verify_writes_nothing(
    tmp_path: Path,
) -> None:
    tree = ast.parse(_SCRIPT.read_text(encoding="utf-8"))
    funcs = {n.name: n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)}
    assert "cmd_rotate" in funcs and "cmd_verify" in funcs
    assert _calls_in(funcs["cmd_verify"]).isdisjoint(
        {
            "write_text",
            "write_bytes",
            "open",
            "replace",
            "mkdir",
            "write_credentials_file",
            "hash_password",
            "generate_password",
            "cmd_rotate",
        }
    ), "verify must be read-only and must not reach the rotation path"
    assert _calls_in(funcs["cmd_rotate"]).isdisjoint({"cmd_verify", "verify_password"})

    # Behavioural half: verify against a tampered stored hash reports MISMATCH and changes no file.
    out, hp, _ = _rotate(tmp_path, users="6")
    before = {p: p.read_bytes() for p in (out, hp)}
    tampered = tmp_path / "certs" / "stored.json"
    stored = json.loads(hp.read_text(encoding="utf-8"))
    stored["6"] = _mod.hash_password("not-the-password")
    tampered.write_text(json.dumps(stored), encoding="utf-8")
    rc = _mod.main(["verify", "--stored-hashes", str(tampered), "--credentials", str(out)])
    assert rc == 1
    assert {p: p.read_bytes() for p in (out, hp)} == before


def test_verify_reports_missing_stored_hash(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    out, hp, _ = _rotate(tmp_path, users="6,7")
    partial = tmp_path / "certs" / "partial.json"
    partial.write_text(
        json.dumps({"6": json.loads(hp.read_text(encoding="utf-8"))["6"]}), encoding="utf-8"
    )
    capsys.readouterr()
    assert _mod.main(["verify", "--stored-hashes", str(partial), "--credentials", str(out)]) == 1
    assert "user 7: NO STORED HASH" in capsys.readouterr().out
